"""Assistant — Module 6 du document complémentaire (sept. 2026).

Principe imposé : Utilisateur -> Rôle -> Permissions -> Module -> Données.
Avant de répondre quoi que ce soit, on vérifie que le rôle de la personne
connectée a le droit de voir la catégorie d'information demandée. Si oui,
la réponse est construite uniquement à partir des données que CETTE
personne a le droit de voir (jamais une requête globale non filtrée).
Si non, la phrase de refus est renvoyée strictement telle qu'exigée,
sans variante.

Ceci fonctionne sans IA générative (mode actuel, aucun coût) : la
question est reconnue par mots-clés parmi un petit ensemble d'intentions
prises en charge. Si une vraie clé API est configurée plus tard
(ANTHROPIC_API_KEY dans .env), `repondre()` est le seul endroit à
modifier pour brancher un vrai modèle — le contrôle de permissions
resterait strictement identique, appliqué AVANT tout appel au modèle.
"""

import re
import unicodedata

from app.models.eleve import Eleve
from app.models.user import User
from app.services.moyennes import moyenne_eleve, a_reussi
from app.services.cycles import cycle_du_role, classe_dans_le_cycle
from app.services.statistiques import stats_reussite, stats_financieres

REFUS = "Je suis désolé de ne pouvoir vous aider, vous n'avez pas accès à ces informations."


def _normaliser(texte):
    """Minuscules, sans accents — pour un matching de mots-clés robuste."""
    texte = texte.lower()
    texte = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in texte if not unicodedata.combining(c))


# Modules que chaque rôle a le droit d'interroger via l'assistant — copie
# fidèle des permissions déjà appliquées ailleurs dans l'app (Finances,
# Statistiques, Notes...), jamais une règle inventée pour l'occasion.
MODULES_PAR_ROLE = {
    "developpeur": {"*"},
    "fondateur": {"finances", "statistiques", "effectifs", "caisse"},
    "administrateur_general": {"finances", "statistiques", "effectifs", "caisse"},
    "directeur_primaire": {"statistiques", "effectifs"},
    "directeur_college": {"statistiques", "effectifs"},
    "comptable": {"finances", "caisse", "statistiques"},
    "secretaire": {"effectifs", "demandes"},
    "responsable_pedagogique": {"statistiques", "effectifs"},
    "enseignant": {"mes_classes"},
    "parent": {"mon_enfant"},
}


def _a_le_module(role, module):
    modules = MODULES_PAR_ROLE.get(role, set())
    return "*" in modules or module in modules


def _intent_effectif(user):
    eleves = Eleve.query.filter_by(actif=True).all()
    cycle = cycle_du_role(user.role)
    if cycle:
        eleves = [e for e in eleves if classe_dans_le_cycle(e.classe, cycle)]
    return f"Effectif actuel : {len(eleves)} élève(s)."


def _intent_statistiques(user):
    annee = Eleve.annee_scolaire_courante()
    eleves = Eleve.query.filter_by(actif=True).all()
    cycle = cycle_du_role(user.role)
    if cycle:
        eleves = [e for e in eleves if classe_dans_le_cycle(e.classe, cycle)]
    stats = stats_reussite(eleves, annee)
    if stats["nb_avec_notes"] == 0:
        return "Aucun élève n'a encore de notes enregistrées cette année."
    return (
        f"Moyenne générale : {stats['moyenne_generale']}. "
        f"Taux de réussite : {stats['taux_reussite']} %. "
        f"Taux d'échec : {stats['taux_echec']} % "
        f"(sur {stats['nb_avec_notes']} élève(s) ayant des notes)."
    )


def _intent_finances(user):
    annee = Eleve.annee_scolaire_courante()
    eleves = Eleve.query.filter_by(actif=True).all()
    fin = stats_financieres(eleves, annee)
    return (
        f"Total à recouvrer : {fin['total_a_recouvrer']:.0f}. "
        f"Total encaissé : {fin['total_encaisse']:.0f}. "
        f"Solde à recouvrer : {fin['solde_a_recouvrer']:.0f} "
        f"(taux de recouvrement : {fin['taux_recouvrement']:.1f} %)."
    )


def _intent_demandes(user):
    n = User.query.filter_by(statut="en_attente").count()
    if n == 0:
        return "Aucune demande de compte en attente pour l'instant."
    return f"{n} demande(s) de compte en attente de validation."


def _intent_mes_classes(user):
    profil = user.profil_enseignant
    if not profil or not profil.affectations:
        return "Tu n'as pas encore de classe attribuée."
    classes = sorted({a.classe.nom for a in profil.affectations})
    return "Tes classes : " + ", ".join(classes) + "."


def _intent_mon_enfant_solde(user):
    if not user.enfants:
        return "Aucun enfant n'est encore lié à ton compte."
    lignes = []
    for e in user.enfants:
        annee = Eleve.annee_scolaire_courante()
        fin = stats_financieres([e], annee)
        lignes.append(f"{e.nom_complet} : solde restant {fin['solde_a_recouvrer']:.0f}")
    return " ; ".join(lignes) + "."


def _intent_mon_enfant_moyenne(user):
    if not user.enfants:
        return "Aucun enfant n'est encore lié à ton compte."
    annee = Eleve.annee_scolaire_courante()
    lignes = []
    for e in user.enfants:
        moyenne = moyenne_eleve(e, annee)
        if moyenne is None:
            lignes.append(f"{e.nom_complet} : pas encore de notes cette année")
        else:
            statut = "admissible" if a_reussi(e, annee) else "sous le seuil requis"
            lignes.append(f"{e.nom_complet} : moyenne {moyenne} ({statut})")
    return " ; ".join(lignes) + "."


# (mots-clés normalisés sans accents, module requis, fonction de réponse)
INTENTIONS = [
    (["effectif", "combien d'eleves", "combien deleves", "nombre d'eleves"], "effectifs", _intent_effectif),
    (["taux de reussite", "taux d'echec", "moyenne generale", "statistique"], "statistiques", _intent_statistiques),
    (["solde a recouvrer", "total encaisse", "recouvrement", "finances de l'ecole"], "finances", _intent_finances),
    (["demande en attente", "demandes en attente", "compte en attente"], "demandes", _intent_demandes),
    (["mes classes", "ma classe", "dans quelles classes"], "mes_classes", _intent_mes_classes),
    (["solde de mon enfant", "solde mon enfant", "combien je dois", "reste a payer"], "mon_enfant", _intent_mon_enfant_solde),
    (["moyenne de mon enfant", "note de mon enfant", "notes de mon enfant"], "mon_enfant", _intent_mon_enfant_moyenne),
]


def questions_suggerees(role):
    """Pour l'écran : n'affiche que des exemples que CE rôle a le droit
    de poser (évite de suggérer une question qui sera de toute façon
    refusée)."""
    vues = set()
    suggestions = []
    for mots_cles, module, _ in INTENTIONS:
        if module in vues or not _a_le_module(role, module):
            continue
        vues.add(module)
        suggestions.append(mots_cles[0])
    return suggestions


def repondre(user, question):
    """Utilisateur -> Rôle -> Permissions -> Module -> Données.
    Retourne toujours une chaîne de texte."""
    q = _normaliser(question)

    for mots_cles, module, handler in INTENTIONS:
        if any(_normaliser(mc) in q for mc in mots_cles):
            if not _a_le_module(user.role, module):
                return REFUS
            return handler(user)

    # Question non reconnue : ce n'est pas un refus de permission, on ne
    # doit donc pas renvoyer la phrase de refus (qui affirmerait à tort
    # un problème de droits) — on explique plutôt ce qu'on sait faire.
    exemples = questions_suggerees(user.role)
    if exemples:
        return (
            "Je ne sais pas encore répondre à ce type de question. "
            "Voici ce que je peux faire pour toi : " + " / ".join(exemples)
        )
    return "Je ne sais pas encore répondre à ce type de question."

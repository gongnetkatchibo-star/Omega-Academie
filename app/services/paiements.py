from app.extensions import db
from app.models.eleve import Eleve
from app.models.paiement import Paiement, LIBELLES_ECHEANCE, ECHEANCES, ECHEANCE_ANNEXE
from app.models.mouvement_caisse import MouvementCaisse, TYPE_SCOLARITE_AUTO


def _contexte_frais(annee):
    """Dates limites et frais annexes de l'année, lus une seule fois par
    requête (le résumé est calculé pour beaucoup d'élèves d'affilée)."""
    from flask import g, has_app_context
    from app.models.frais_annexe import FraisAnnexe
    from app.models.parametre import ParametreEtablissement

    cache = g.setdefault("_contexte_frais", {}) if has_app_context() else {}
    if annee not in cache:
        parametre = ParametreEtablissement.query.first()
        courante = annee == Eleve.annee_scolaire_courante()
        cache[annee] = {
            "dates": {
                ech: (getattr(parametre, f"date_limite_{ech}", None) if parametre and courante else None)
                for ech in ECHEANCES
            },
            "annexes": FraisAnnexe.query.filter_by(annee_scolaire=annee).order_by(FraisAnnexe.id).all(),
        }
    return cache[annee]


def resume_paiements(eleve, annee=None, classe=None):
    """Montant attendu/payé détaillé par échéance, plus un statut global.
    Partagé par Finances et Statistiques — un seul calcul, jamais deux
    définitions différentes du même chiffre.

    Tient compte de la remise de l'élève, des dates limites (ce qui reste
    dû après la date est « en retard ») et des frais annexes de sa classe.

    `classe` (optionnel) : à préciser pour une année passée, où la classe
    actuelle de l'élève (eleve.classe) n'est plus celle de l'année
    consultée — sinon les montants attendus seraient faux."""
    from app.services.temps import aujourd_hui

    annee = annee or Eleve.annee_scolaire_courante()
    classe = classe or eleve.classe
    contexte = _contexte_frais(annee)
    jour = aujourd_hui()
    remise = min(max(eleve.remise_pourcent or 0, 0), 100)

    def apres_remise(montant):
        return round((montant or 0) * (100 - remise) / 100)

    attendu_par_echeance = {
        "inscription": apres_remise(classe.frais_inscription),
        "tranche_1": apres_remise(classe.frais_tranche1),
        "tranche_2": apres_remise(classe.frais_tranche2),
    }
    paiements_annee = [p for p in eleve.paiements if p.annee_scolaire == annee]
    paye_par_echeance = {ech: 0 for ech in ECHEANCES}
    paye_par_annexe = {}
    for p in paiements_annee:
        if p.echeance == ECHEANCE_ANNEXE:
            paye_par_annexe[p.frais_annexe_id] = paye_par_annexe.get(p.frais_annexe_id, 0) + p.montant
        else:
            paye_par_echeance[p.echeance] = paye_par_echeance.get(p.echeance, 0) + p.montant

    def ligne(cle, libelle, attendu, paye, date_limite):
        reste = max(0, attendu - paye)
        return {
            "cle": cle, "libelle": libelle, "attendu": attendu, "paye": paye, "reste": reste,
            "date_limite": date_limite, "en_retard": bool(date_limite and date_limite < jour and reste > 0),
        }

    echeances = [
        ligne(ech, LIBELLES_ECHEANCE[ech], attendu_par_echeance[ech], paye_par_echeance[ech], contexte["dates"][ech])
        for ech in ECHEANCES
    ]
    annexes = [
        ligne(f"annexe_{f.id}", f.libelle, f.montant, paye_par_annexe.get(f.id, 0), f.date_limite)
        for f in contexte["annexes"] if f.classe_id in (None, classe.id)
    ]

    du = sum(l["attendu"] for l in echeances + annexes)
    paye = sum(l["paye"] for l in echeances + annexes)
    solde = max(0, du - paye)
    statut = "PAYÉ" if solde == 0 else ("IMPAYÉ" if paye == 0 else "PARTIEL")
    retard = sum(l["reste"] for l in echeances + annexes if l["en_retard"])

    return {
        "echeances": echeances, "annexes": annexes, "du": du, "paye": paye, "solde": solde, "statut": statut,
        "retard": retard, "remise": remise,
    }


def analyser_echeance(valeur, eleve):
    """Valeur du formulaire → (echeance, frais annexe ou None), ou None
    si elle ne correspond à rien de payable par cet élève."""
    from app.models.frais_annexe import FraisAnnexe

    if valeur in ECHEANCES:
        return valeur, None
    if valeur and valeur.startswith("annexe_") and valeur[7:].isdigit():
        frais = FraisAnnexe.query.get(int(valeur[7:]))
        if frais and frais.classe_id in (None, eleve.classe_id):
            return ECHEANCE_ANNEXE, frais
    return None


def enregistrer_paiement(eleve, montant, mode, echeance, utilisateur, reference=None, frais_annexe=None):
    """Point d'entrée UNIQUE pour enregistrer un paiement de scolarité,
    utilisé à la fois par Finances et par le formulaire officiel de Caisse.

    Fait deux choses de façon atomique :
    1. Crée le Paiement (référence/reçu généré automatiquement — jamais
       saisi à la main).
    2. Crée la ligne correspondante dans la Caisse (Option A validée avec
       la direction, sept. 2026) : toute échéance encaissée apparaît
       immédiatement dans l'historique de caisse, sans ressaisie, avec
       l'élève, le mode, la date, l'utilisateur et la référence.

    Ni l'un ni l'autre appelant n'a besoin de connaître ces détails —
    évite que Finances et Caisse se désynchronisent avec le temps.
    """
    numero_recu = Paiement.generer_numero_recu()

    paiement = Paiement(
        eleve_id=eleve.id, montant=montant, mode=mode, echeance=echeance,
        numero_recu=numero_recu, reference=(reference or None),
        annee_scolaire=Eleve.annee_scolaire_courante(),
        enregistre_par_id=utilisateur.id,
        frais_annexe_id=frais_annexe.id if frais_annexe else None,
    )
    db.session.add(paiement)
    db.session.flush()  # pour obtenir paiement.id avant de lier la ligne de caisse

    parent_txt = f" — parent(s) : {', '.join(p.nom_complet for p in eleve.parents)}" if eleve.parents else ""
    mouvement = MouvementCaisse(
        date=paiement.date_paiement.date(),
        type=TYPE_SCOLARITE_AUTO,
        reference=numero_recu,
        libelle=(
            f"{frais_annexe.libelle} — {eleve.nom_complet}{parent_txt}" if frais_annexe
            else f"Scolarité — {eleve.nom_complet} ({LIBELLES_ECHEANCE[echeance]}){parent_txt}"
        ),
        recette=montant,
        depense=0,
        responsable_id=utilisateur.id,
        eleve_id=eleve.id,
        origine_module="finances",
        origine_id=paiement.id,
        automatique=True,
    )
    db.session.add(mouvement)
    db.session.commit()

    from app.services.notifications import notifier_paiement
    notifier_paiement(paiement, eleve)

    return paiement

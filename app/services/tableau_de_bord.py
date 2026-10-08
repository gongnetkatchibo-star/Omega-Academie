"""Chiffres du tableau de bord de la direction (oct. 2026).

Chaque bloc n'est calculé que si le rôle a accès au module concerné
(même matrice de permissions que le menu) : un secrétaire voit les
effectifs et les absences, pas l'argent. Les montants viennent du même
calcul que Finances et Statistiques (resume_paiements), jamais d'un
calcul parallèle."""

from collections import Counter, defaultdict
from datetime import date

from app.models.eleve import Eleve
from app.models.classe import Classe
from app.models.paiement import Paiement, ECHEANCES
from app.services.modules_par_defaut import ROLES_PAR_DEFAUT
from app.services.permissions import role_a_acces
from app.services.temps import maintenant

NB_CLASSES_RECOUVREMENT = 7
NB_DERNIERS_PAIEMENTS = 5
SEUIL_RECOUVREMENT_BON = 70
SEUIL_RECOUVREMENT_A_SUIVRE = 50

LIBELLES_MODE = {"especes": "Espèces", "mobile_money": "Mobile Money", "virement_bancaire": "Virement"}


def _a_acces(role, module):
    return role_a_acces(role, module, ROLES_PAR_DEFAUT.get(module, []))


def etat_recouvrement(taux):
    """(classe CSS, libellé) du badge d'une classe selon son taux."""
    if taux >= SEUIL_RECOUVREMENT_BON:
        return "badge-ok", "Bon"
    if taux >= SEUIL_RECOUVREMENT_A_SUIVRE:
        return "badge-attention", "À suivre"
    return "badge-critique", "Critique"


def _debut_mois(jour, decalage_annees=0):
    return date(jour.year - decalage_annees, jour.month, 1)


def _bloc_finances(eleves, annee, classes):
    from app.services.paiements import resumes_paiements
    from app.services.statistiques import stats_financieres

    resumes = resumes_paiements(eleves, annee)
    totaux = stats_financieres(eleves, annee, resumes=resumes)

    # Échéancier : attendu et encaissé par échéance, pour toute l'école.
    echeancier = []
    for i, cle in enumerate(ECHEANCES):
        attendu = sum(r["echeances"][i]["attendu"] for r in resumes.values())
        paye = sum(min(r["echeances"][i]["paye"], r["echeances"][i]["attendu"]) for r in resumes.values())
        premier = next(iter(resumes.values()), None)
        echeancier.append({
            "cle": cle,
            "libelle": premier["echeances"][i]["libelle"] if premier else cle,
            "date_limite": premier["echeances"][i]["date_limite"] if premier else None,
            "attendu": attendu,
            "paye": paye,
            "taux": round(paye / attendu * 100) if attendu else 0,
        })
    plus_grand = max((e["attendu"] for e in echeancier), default=0)
    for e in echeancier:
        e["largeur"] = round(e["attendu"] / plus_grand * 100, 1) if plus_grand else 0

    # Recouvrement par classe : part du total dû déjà payée.
    par_classe = defaultdict(lambda: {"effectif": 0, "du": 0, "solde": 0})
    for e in eleves:
        ligne = par_classe[e.classe_id]
        ligne["effectif"] += 1
        ligne["du"] += resumes[e.id]["du"]
        ligne["solde"] += resumes[e.id]["solde"]
    lignes_classes = []
    for classe in classes:
        ligne = par_classe.get(classe.id)
        if not ligne or not ligne["du"]:
            continue
        taux = round((ligne["du"] - ligne["solde"]) / ligne["du"] * 100)
        badge, etat = etat_recouvrement(taux)
        lignes_classes.append({
            "classe": classe, "effectif": ligne["effectif"], "taux": taux,
            "reste": ligne["solde"], "badge": badge, "etat": etat,
        })
    lignes_classes.sort(key=lambda l: l["taux"])

    jour = maintenant().date()
    encaisse_mois = _somme_paiements(_debut_mois(jour), jour)
    try:
        debut_an_passe = _debut_mois(jour, 1)
        fin_an_passe = jour.replace(year=jour.year - 1)
    except ValueError:  # 29 février
        fin_an_passe = date(jour.year - 1, jour.month, 28)
    encaisse_mois_an_passe = _somme_paiements(debut_an_passe, fin_an_passe)
    evolution = (
        round((encaisse_mois - encaisse_mois_an_passe) / encaisse_mois_an_passe * 100)
        if encaisse_mois_an_passe else None
    )

    derniers = (
        Paiement.query.order_by(Paiement.date_paiement.desc(), Paiement.id.desc())
        .limit(NB_DERNIERS_PAIEMENTS).all()
    )

    return {
        "encaisse_mois": encaisse_mois,
        "evolution_mois": evolution,
        "taux_recouvrement": round(totaux["taux_recouvrement"]),
        "reste_a_recouvrer": totaux["solde_a_recouvrer"],
        "echeancier": echeancier,
        "classes": lignes_classes[:NB_CLASSES_RECOUVREMENT],
        "nb_classes_masquees": max(0, len(lignes_classes) - NB_CLASSES_RECOUVREMENT),
        "derniers_paiements": derniers,
        "familles_en_retard": sum(1 for r in resumes.values() if r["retard"] > 0),
    }


def _somme_paiements(debut, fin):
    from datetime import datetime, time
    from sqlalchemy import func

    total = (
        Paiement.query.with_entities(func.coalesce(func.sum(Paiement.montant), 0))
        .filter(Paiement.date_paiement >= datetime.combine(debut, time.min))
        .filter(Paiement.date_paiement <= datetime.combine(fin, time.max))
        .scalar()
    )
    return total or 0


def _bloc_absences(eleves, classes):
    from app.models.absence import Absence

    jour = maintenant().date()
    absences = Absence.query.filter_by(date=jour).all()
    ids_eleves = {e.id for e in eleves}
    absences = [a for a in absences if a.eleve_id in ids_eleves]
    absents = {a.eleve_id for a in absences}
    non_justifies = {a.eleve_id for a in absences if not a.justifiee}

    effectif_par_classe = Counter(e.classe_id for e in eleves)
    absents_par_classe = Counter()
    for eleve_id, classe_id in {(a.eleve_id, a.classe_id) for a in absences}:
        absents_par_classe[classe_id] += 1
    par_classe = [
        {"classe": c, "absents": absents_par_classe[c.id], "effectif": effectif_par_classe[c.id]}
        for c in classes if absents_par_classe[c.id]
    ]
    par_classe.sort(key=lambda l: l["absents"], reverse=True)
    return {
        "absents": len(absents),
        "non_justifies": len(non_justifies),
        "par_classe": par_classe,
    }


def _taches(role, eleves, finances):
    """Ce qui attend une action, du plus urgent au moins urgent. Une
    ligne n'apparaît que si elle compte au moins un élément."""
    from app.models.user import User

    taches = []
    if finances and finances["familles_en_retard"]:
        taches.append({
            "nombre": finances["familles_en_retard"], "niveau": "critique",
            "titre": "Familles en retard de paiement", "detail": "Une échéance dépassée n'est pas soldée",
            "endpoint": "finances.liste", "params": {"retard": 1},
        })
    if _a_acces(role, "alertes"):
        from app.services.alertes import eleves_absences_frequentes
        nb = len(eleves_absences_frequentes(eleves))
        if nb:
            taches.append({
                "nombre": nb, "niveau": "critique", "titre": "Élèves en alerte",
                "detail": "Absences non justifiées répétées", "endpoint": "alertes.tableau", "params": {},
            })
    if _a_acces(role, "absences"):
        from app.services.temps import aujourd_hui
        from app.services.whatsapp import absences_a_prevenir
        nb = sum(1 for a in absences_a_prevenir(aujourd_hui(), {e.id for e in eleves}) if not a["envoi"])
        if nb:
            taches.append({
                "nombre": nb, "niveau": "attention", "titre": "Parents à prévenir",
                "detail": "Absences non justifiées du jour, à signaler sur WhatsApp",
                "endpoint": "relances.index", "params": {},
            })
    if _a_acces(role, "secretariat"):
        nb = User.query.filter_by(statut="en_attente").count()
        if nb:
            taches.append({
                "nombre": nb, "niveau": "attention", "titre": "Comptes à valider",
                "detail": "Demandes d'inscription en attente", "endpoint": "secretariat.demandes", "params": {},
            })
    if _a_acces(role, "messagerie"):
        from app.models.message import Message
        nb = (
            Message.query.filter(Message.lu_par_ecole.is_(False), Message.auteur_id == Message.parent_id)
            .with_entities(Message.parent_id).distinct().count()
        )
        if nb:
            taches.append({
                "nombre": nb, "niveau": "info", "titre": "Messages de parents",
                "detail": "Conversations avec un message non lu", "endpoint": "messagerie.index", "params": {},
            })
    return taches


def donnees_tableau_de_bord(user):
    """Tout ce qu'affiche le tableau de bord pour ce compte, ou None si
    le rôle n'a accès à aucun des blocs (parent, élève, enseignant…)."""
    from app.services.tenant import ecole_courante

    if ecole_courante() is None:
        return None
    role = user.role
    voit_finances = _a_acces(role, "finances")
    voit_effectifs = _a_acces(role, "eleves") or _a_acces(role, "statistiques")
    voit_absences = _a_acces(role, "absences")
    if not (voit_finances or voit_effectifs or voit_absences):
        return None

    annee = Eleve.annee_scolaire_courante()
    classes = Classe.query.filter_by(annee_scolaire=annee).order_by(Classe.niveau, Classe.nom).all()
    ids_classes = [c.id for c in classes]
    eleves = (
        Eleve.query.filter(Eleve.actif.is_(True), Eleve.classe_id.in_(ids_classes)).all()
        if ids_classes else []
    )

    finances = _bloc_finances(eleves, annee, classes) if voit_finances and eleves else None
    effectifs = None
    if voit_effectifs:
        effectifs = {
            "total": len(eleves),
            "filles": sum(1 for e in eleves if e.sexe == "F"),
            "garcons": sum(1 for e in eleves if e.sexe == "M"),
            "classes": len(classes),
        }
    absences = _bloc_absences(eleves, classes) if voit_absences else None

    return {
        "annee": annee,
        "finances": finances,
        "effectifs": effectifs,
        "absences": absences,
        "taches": _taches(role, eleves, finances),
        "libelles_mode": LIBELLES_MODE,
    }

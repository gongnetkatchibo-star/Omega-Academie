"""Calculs statistiques partagés — utilisés par le module Statistiques ET
par l'Assistant, pour ne jamais avoir deux définitions différentes du
même chiffre (même principe que app/services/moyennes.py)."""

from app.models.eleve import Eleve
from app.models.paiement import Paiement
from app.services.moyennes import moyenne_eleve, a_reussi


def stats_reussite(eleves, annee):
    """Moyenne générale + taux de réussite/échec pour un ensemble
    d'élèves — seuls ceux ayant au moins une note comptent (on ne peut
    pas juger un élève sans notes)."""
    moyennes = []
    reussites = 0
    echecs = 0
    for e in eleves:
        moyenne = moyenne_eleve(e, annee)
        if moyenne is None:
            continue
        moyennes.append(moyenne)
        if a_reussi(e, annee):
            reussites += 1
        else:
            echecs += 1

    nb_notes = len(moyennes)
    return {
        "nb_avec_notes": nb_notes,
        "moyenne_generale": round(sum(moyennes) / nb_notes, 2) if nb_notes else None,
        "taux_reussite": round(reussites / nb_notes * 100, 1) if nb_notes else None,
        "taux_echec": round(echecs / nb_notes * 100, 1) if nb_notes else None,
    }


def tableau_par_sexe(eleves, annee):
    """Tableau à double entrée (indicateur x sexe) : effectif, taux de
    réussite et taux d'échec, ventilés Garçons / Filles / Total —
    demandé par la direction pour chaque écran de statistiques."""
    colonnes = {
        "Garçons": [e for e in eleves if e.sexe == "M"],
        "Filles": [e for e in eleves if e.sexe == "F"],
        "Total": eleves,
    }
    resultat = {}
    for colonne, groupe in colonnes.items():
        s = stats_reussite(groupe, annee)
        resultat[colonne] = {
            "effectif": len(groupe),
            "taux_reussite": s["taux_reussite"],
            "taux_echec": s["taux_echec"],
        }
    return resultat


def stats_financieres(eleves, annee, classe_de=None):
    """`classe_de` (optionnel) : dict {eleve_id: Classe} à utiliser à la
    place de `eleve.classe` — indispensable pour une année passée, où la
    classe actuelle de l'élève n'est plus celle de l'année consultée."""
    def classe_de_l_eleve(e):
        return classe_de[e.id] if classe_de else e.classe

    total_a_recouvrer = sum(classe_de_l_eleve(e).frais_annuel for e in eleves if classe_de_l_eleve(e))
    eleve_ids = {e.id for e in eleves}
    total_encaisse = sum(
        p.montant for p in Paiement.query.filter_by(annee_scolaire=annee).all()
        if p.eleve_id in eleve_ids
    )
    solde_a_recouvrer = max(0, total_a_recouvrer - total_encaisse)
    taux_recouvrement = (total_encaisse / total_a_recouvrer * 100) if total_a_recouvrer else 0
    return {
        "total_a_recouvrer": total_a_recouvrer,
        "total_encaisse": total_encaisse,
        "solde_a_recouvrer": solde_a_recouvrer,
        "taux_recouvrement": taux_recouvrement,
    }


LIBELLES_FILTRE_FINANCE = {
    "inscription_seule": "A réglé seulement l'inscription",
    "inscription_t1": "A réglé Inscription + Tranche 1",
    "solde": "A soldé la totalité des frais",
}


def stats_finance_par_tranche(eleves, annee, classe_de=None):
    """Statistiques financières ventilées par échéance (Inscription,
    Tranche 1, Tranche 2) — même principe que le tableau par sexe, mais
    pour l'argent (document complémentaire, sept. 2026)."""
    from app.services.paiements import resume_paiements

    resumes = {e.id: resume_paiements(e, annee, classe=(classe_de[e.id] if classe_de else None)) for e in eleves}
    par_tranche = {}
    for i, cle in enumerate(["inscription", "tranche_1", "tranche_2"]):
        attendu = sum(r["echeances"][i]["attendu"] for r in resumes.values())
        paye = sum(r["echeances"][i]["paye"] for r in resumes.values())
        par_tranche[cle] = {
            "libelle": resumes[eleves[0].id]["echeances"][i]["libelle"] if eleves else cle,
            "attendu": attendu, "paye": paye, "solde": max(0, attendu - paye),
            "taux": round(paye / attendu * 100, 1) if attendu else 0,
        }
    return par_tranche, resumes


def filtrer_eleves_par_situation(eleves, annee, filtre, classe_de=None):
    """Retourne les élèves correspondant à un filtre de situation de
    paiement — chaque liste est ensuite téléchargeable telle quelle."""
    from app.services.paiements import resume_paiements

    resultat = []
    for e in eleves:
        r = resume_paiements(e, annee, classe=(classe_de[e.id] if classe_de else None))
        paye = {ech["cle"]: ech["paye"] >= ech["attendu"] and ech["attendu"] > 0 for ech in r["echeances"]}
        if filtre == "inscription_seule" and paye["inscription"] and not paye["tranche_1"] and not paye["tranche_2"]:
            resultat.append(e)
        elif filtre == "inscription_t1" and paye["inscription"] and paye["tranche_1"] and not paye["tranche_2"]:
            resultat.append(e)
        elif filtre == "solde" and r["statut"] == "PAYÉ":
            resultat.append(e)
    return resultat

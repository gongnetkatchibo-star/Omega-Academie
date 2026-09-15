from app.extensions import db
from app.models.eleve import Eleve
from app.models.paiement import Paiement, LIBELLES_ECHEANCE, ECHEANCES
from app.models.mouvement_caisse import MouvementCaisse, TYPE_SCOLARITE_AUTO


def resume_paiements(eleve, annee=None, classe=None):
    """Reproduit la logique de la feuille SUIVI de la fiche 2026-2027 :
    montant attendu/payé détaillé par échéance, plus un statut global.
    Partagé par Finances et Statistiques — un seul calcul, jamais deux
    définitions différentes du même chiffre.

    `classe` (optionnel) : à préciser pour une année passée, où la classe
    actuelle de l'élève (eleve.classe) n'est plus celle de l'année
    consultée — sinon les montants attendus seraient faux."""
    annee = annee or Eleve.annee_scolaire_courante()
    classe = classe or eleve.classe
    attendu_par_echeance = {
        "inscription": classe.frais_inscription or 0,
        "tranche_1": classe.frais_tranche1 or 0,
        "tranche_2": classe.frais_tranche2 or 0,
    }
    paiements_annee = [p for p in eleve.paiements if p.annee_scolaire == annee]
    paye_par_echeance = {ech: 0 for ech in ECHEANCES}
    for p in paiements_annee:
        paye_par_echeance[p.echeance] = paye_par_echeance.get(p.echeance, 0) + p.montant

    echeances = [
        {
            "cle": ech, "libelle": LIBELLES_ECHEANCE[ech],
            "attendu": attendu_par_echeance[ech], "paye": paye_par_echeance[ech],
        }
        for ech in ECHEANCES
    ]

    du = sum(attendu_par_echeance.values())
    paye = sum(paye_par_echeance.values())
    solde = max(0, du - paye)
    statut = "PAYÉ" if solde == 0 else ("IMPAYÉ" if paye == 0 else "PARTIEL")

    return {"echeances": echeances, "du": du, "paye": paye, "solde": solde, "statut": statut}


def enregistrer_paiement(eleve, montant, mode, echeance, utilisateur, reference=None):
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
    )
    db.session.add(paiement)
    db.session.flush()  # pour obtenir paiement.id avant de lier la ligne de caisse

    parent_txt = f" — parent(s) : {', '.join(p.nom_complet for p in eleve.parents)}" if eleve.parents else ""
    mouvement = MouvementCaisse(
        date=paiement.date_paiement.date(),
        type=TYPE_SCOLARITE_AUTO,
        reference=numero_recu,
        libelle=f"Scolarité — {eleve.nom_complet} ({LIBELLES_ECHEANCE[echeance]}){parent_txt}",
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

from app.extensions import db
from app.models.eleve import Eleve
from app.models.paiement import Paiement, LIBELLES_ECHEANCE, ECHEANCES, ECHEANCE_ANNEXE
from app.models.mouvement_caisse import MouvementCaisse, TYPE_SCOLARITE_AUTO, TYPE_ANNULATION


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


def resumes_paiements(eleves, annee=None, classe_de=None):
    """{eleve_id: résumé} pour toute une liste d'élèves : les paiements
    de l'année sont lus en une fois, au lieu d'une requête par élève.
    `classe_de` : {eleve_id: Classe} pour une année passée (voir
    resume_paiements)."""
    from collections import defaultdict

    eleves = list(eleves)
    annee = annee or Eleve.annee_scolaire_courante()
    requete = Paiement.query.filter_by(annee_scolaire=annee)
    if len(eleves) <= 500:
        requete = requete.filter(Paiement.eleve_id.in_([e.id for e in eleves]))
    par_eleve = defaultdict(list)
    for paiement in requete.all():
        par_eleve[paiement.eleve_id].append(paiement)
    return {
        e.id: resume_paiements(
            e, annee, classe=(classe_de[e.id] if classe_de else None), paiements=par_eleve.get(e.id, []),
        )
        for e in eleves
    }


def resume_paiements(eleve, annee=None, classe=None, paiements=None):
    """Montant attendu/payé détaillé par échéance, plus un statut global.
    Partagé par Finances et Statistiques — un seul calcul, jamais deux
    définitions différentes du même chiffre.

    Tient compte de la remise de l'élève, des dates limites (ce qui reste
    dû après la date est « en retard ») et des frais annexes de sa classe.

    `classe` (optionnel) : à préciser pour une année passée, où la classe
    actuelle de l'élève (eleve.classe) n'est plus celle de l'année
    consultée — sinon les montants attendus seraient faux.
    `paiements` (optionnel) : paiements de l'élève pour cette année, déjà
    lus (voir resumes_paiements)."""
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
    paiements_annee = (
        paiements if paiements is not None else [p for p in eleve.paiements if p.annee_scolaire == annee]
    )
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


def date_cloture():
    from app.models.parametre import ParametreEtablissement

    parametre = ParametreEtablissement.query.first()
    return parametre.date_cloture_caisse if parametre else None


def periode_close(une_date):
    """Message d'erreur si la caisse est arrêtée à cette date, sinon None."""
    cloture = date_cloture()
    if cloture and une_date and une_date <= cloture:
        return f"La caisse est clôturée jusqu'au {cloture.strftime('%d/%m/%Y')} : cette période ne peut plus être modifiée."
    return None


def reste_a_payer(eleve, echeance, frais_annexe=None, annee=None, sauf_paiement=None):
    """Ce qui reste dû sur une échéance (ou un frais annexe), sans compter
    `sauf_paiement` (celui qu'on est en train de corriger)."""
    annee = annee or Eleve.annee_scolaire_courante()
    classe = eleve.classe
    if annee != eleve.classe.annee_scolaire:
        from app.models.historique import HistoriqueScolaire
        h = (HistoriqueScolaire.query.filter_by(eleve_id=eleve.id, annee_scolaire=annee)
             .order_by(HistoriqueScolaire.id.desc()).first())
        classe = h.classe if h and h.classe else classe
    paiements = [p for p in Paiement.query.filter_by(eleve_id=eleve.id, annee_scolaire=annee).all()
                 if sauf_paiement is None or p.id != sauf_paiement.id]
    resume = resume_paiements(eleve, annee, classe=classe, paiements=paiements)
    cle = f"annexe_{frais_annexe.id}" if frais_annexe else echeance
    for ligne in resume["echeances"] + resume["annexes"]:
        if ligne["cle"] == cle:
            return ligne["reste"]
    return 0


def controler_montant(eleve, echeance, frais_annexe, montant, annee=None, sauf_paiement=None):
    """Message d'erreur si le montant dépasse ce qui reste dû, sinon None."""
    reste = reste_a_payer(eleve, echeance, frais_annexe, annee, sauf_paiement)
    if montant > reste:
        from app.services.notifications import montant_fcfa
        if reste <= 0:
            return "Cette échéance est déjà entièrement payée : choisis une autre échéance."
        return f"Le montant dépasse ce qui reste dû sur cette échéance ({montant_fcfa(reste)})."
    return None


def annuler_recus(mouvement_id):
    """Le reçu déjà remis s'affiche « annulé » sur la page de vérification."""
    from app.models.document_verifiable import DocumentVerifiable

    DocumentVerifiable.query.filter_by(cle_objet=f"recu:{mouvement_id}", annule=False).update({"annule": True})


def contrepasser(mouvement, motif, utilisateur):
    """Annule une ligne de caisse sans l'effacer : elle reste, marquée
    « annulée », et une écriture inverse datée d'aujourd'hui remet le
    solde d'aplomb. Rien ne disparaît du registre."""
    from app.services.temps import aujourd_hui

    mouvement.origine_module = f"{mouvement.origine_module or 'caisse'}_annule"[:30]
    if "[annulé]" not in mouvement.libelle:
        mouvement.libelle = f"{mouvement.libelle} [annulé]"[:200]
    inverse = MouvementCaisse(
        date=aujourd_hui(), type=TYPE_ANNULATION, reference=(f"ANN-{mouvement.reference or mouvement.id}")[:60],
        libelle=f"Annulation : {mouvement.libelle.replace(' [annulé]', '')}"[:200],
        recette=mouvement.depense or 0, depense=mouvement.recette or 0,
        observation=(motif or "")[:300] or None, responsable_id=utilisateur.id, eleve_id=mouvement.eleve_id,
        origine_module="annulation", origine_id=mouvement.id, automatique=True,
    )
    db.session.add(inverse)
    annuler_recus(mouvement.id)
    return inverse


def analyser_echeance(valeur, eleve):
    """Valeur du formulaire → (echeance, frais annexe ou None), ou None
    si elle ne correspond à rien de payable par cet élève."""
    from app.models.frais_annexe import FraisAnnexe

    if valeur in ECHEANCES:
        return valeur, None
    if valeur and valeur.startswith("annexe_") and valeur[7:].isdigit():
        frais = db.session.get(FraisAnnexe, int(valeur[7:]))
        if frais and frais.classe_id in (None, eleve.classe_id) and frais.annee_scolaire == eleve.classe.annee_scolaire:
            return ECHEANCE_ANNEXE, frais
    return None


def enregistrer_paiement(eleve, montant, mode, echeance, utilisateur, reference=None, frais_annexe=None, annee=None):
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
        annee_scolaire=annee or Eleve.annee_scolaire_courante(),
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
            else f"Scolarité — {eleve.nom_complet} ({LIBELLES_ECHEANCE[echeance]}"
                 f"{', ' + annee if annee and annee != Eleve.annee_scolaire_courante() else ''}){parent_txt}"
        )[:200],
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


def arrieres(eleve):
    """[(année, résumé)] des années passées où il reste quelque chose à
    payer, d'après les classes fréquentées (historique scolaire)."""
    from app.models.historique import HistoriqueScolaire

    courante = Eleve.annee_scolaire_courante()
    resultat = []
    vues = set()
    for h in HistoriqueScolaire.query.filter_by(eleve_id=eleve.id).order_by(HistoriqueScolaire.annee_scolaire.desc()).all():
        if h.annee_scolaire >= courante or h.annee_scolaire in vues or h.classe is None:
            continue
        vues.add(h.annee_scolaire)
        resume = resume_paiements(eleve, h.annee_scolaire, classe=h.classe)
        if resume["solde"] > 0:
            resultat.append((h.annee_scolaire, resume))
    return resultat

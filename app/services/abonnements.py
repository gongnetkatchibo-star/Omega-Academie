"""Abonnements des écoles et factures de la plateforme (oct. 2026).

Chaque école a son propre réglage, choisi avec elle : prix par élève ou
forfait, montant en FCFA, rythme (mensuel, trimestriel, annuel). Une
facture couvre une période ; elle est due au début de la période. Après
15 jours de retard, la console signale l'école « à suspendre » — la
suspension reste toujours une décision de l'administrateur."""

import calendar
import io
from datetime import date, timedelta

from sqlalchemy import func, select

from app.extensions import db
from app.models.gouvernance import (
    Facture, MODES_FACTURATION, PERIODICITES, JOURS_DE_GRACE, STATUTS_FACTURE, MODES_REGLEMENT,
)
from app.services.temps import aujourd_hui

TOUS = {"tous_etablissements": True}


def ajouter_mois(jour, mois):
    total = jour.month - 1 + mois
    annee, mois_final = jour.year + total // 12, total % 12 + 1
    return date(annee, mois_final, min(jour.day, calendar.monthrange(annee, mois_final)[1]))


def nombre_eleves_actifs(ecole_id):
    from app.models.eleve import Eleve

    return db.session.execute(
        select(func.count()).select_from(Eleve).where(Eleve.ecole_id == ecole_id, Eleve.actif.is_(True)),
        execution_options=TOUS,
    ).scalar() or 0


def factures_de(ecole_id):
    return Facture.query.filter_by(ecole_id=ecole_id).order_by(Facture.date_emission.desc(), Facture.id.desc()).all()


def etat(ecole):
    """Ce que montrent la console et l'espace de l'école."""
    impayees = Facture.query.filter_by(ecole_id=ecole.id, statut="emise").order_by(Facture.date_echeance).all()
    retard = max((f.jours_de_retard for f in impayees), default=0)
    du = sum(f.montant for f in impayees)
    facturee = bool(ecole.mode_facturation and ecole.tarif)
    if not facturee:
        niveau, libelle = "neutre", "Non facturée"
    elif retard > JOURS_DE_GRACE:
        niveau, libelle = "critique", f"Impayé depuis {retard} jours — à suspendre ?"
    elif retard > 0:
        niveau, libelle = "attention", f"En retard de {retard} jour(s)"
    elif impayees:
        niveau, libelle = "attention", "Facture à payer"
    else:
        niveau, libelle = "ok", "À jour"
    return {
        "facturee": facturee, "impayees": impayees, "du": du, "retard": retard, "niveau": niveau, "libelle": libelle,
        "a_suspendre": facturee and retard > JOURS_DE_GRACE, "formule": libelle_formule(ecole),
        "prochaine_periode": ecole.date_echeance,
    }


def libelle_formule(ecole):
    if not (ecole.mode_facturation and ecole.tarif):
        return "Aucune formule"
    periode = PERIODICITES.get(ecole.periodicite or "annuel", ("Annuel", 12))[0].lower()
    from app.services.notifications import montant_fcfa
    base = (f"{montant_fcfa(ecole.tarif)} par élève" if ecole.mode_facturation == "par_eleve"
            else f"Forfait de {montant_fcfa(ecole.tarif)}")
    return f"{ecole.nom_formule + ' — ' if ecole.nom_formule else ''}{base}, {periode}"


def proposition(ecole):
    """Facture de la prochaine période, sans l'enregistrer."""
    debut = ecole.date_echeance or aujourd_hui()
    mois = PERIODICITES.get(ecole.periodicite or "annuel", ("Annuel", 12))[1]
    fin = ajouter_mois(debut, mois) - timedelta(days=1)
    quantite = nombre_eleves_actifs(ecole.id) if ecole.mode_facturation == "par_eleve" else 1
    prix = int(ecole.tarif or 0)
    return {
        "periode_debut": debut, "periode_fin": fin, "quantite": quantite, "prix_unitaire": prix,
        "montant": quantite * prix, "date_echeance": max(debut, aujourd_hui()),
        "libelle": (f"Abonnement {ecole.nom_formule + ' ' if ecole.nom_formule else ''}— "
                    f"{'élèves inscrits' if ecole.mode_facturation == 'par_eleve' else 'forfait'} "
                    f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}")[:200],
    }


def _numero(annee):
    prefixe = f"FAC-{annee}-"
    existants = [n for (n,) in db.session.query(Facture.numero).filter(Facture.numero.like(prefixe + "%")).all()]
    suivant = max((int(n[len(prefixe):]) for n in existants if n[len(prefixe):].isdigit()), default=0) + 1
    return f"{prefixe}{suivant:04d}"


def emettre(ecole, quantite=None, note=None):
    """Enregistre la facture de la prochaine période et avance l'échéance
    de l'école d'une période."""
    p = proposition(ecole)
    if quantite is not None and quantite >= 0:
        p["quantite"], p["montant"] = quantite, quantite * p["prix_unitaire"]
    facture = Facture(
        ecole_id=ecole.id, numero=_numero(aujourd_hui().year), date_emission=aujourd_hui(),
        date_echeance=p["date_echeance"], periode_debut=p["periode_debut"], periode_fin=p["periode_fin"],
        libelle=p["libelle"], quantite=p["quantite"], prix_unitaire=p["prix_unitaire"], montant=p["montant"],
        note=(note or "")[:300] or None,
    )
    db.session.add(facture)
    ecole.date_echeance = p["periode_fin"] + timedelta(days=1)
    return facture


def destinataires_direction(ecole_id):
    from app.models.user import User

    return [
        u.email for u in db.session.execute(
            select(User).where(User.ecole_id == ecole_id, User.statut == "actif",
                               User.role.in_(("fondateur", "administrateur_general"))),
            execution_options=TOUS,
        ).scalars().all() if u.email and not u.email.endswith(".local")
    ]


def notifier_facture(facture):
    from flask import url_for
    from app.services.notifications import notifier, montant_fcfa

    destinataires = destinataires_direction(facture.ecole_id)
    if facture.ecole.contact_email:
        destinataires.append(facture.ecole.contact_email)
    if not destinataires:
        return False
    return notifier(
        sorted(set(destinataires)), f"Facture {facture.numero} — {facture.ecole.nom}",
        (
            f"Bonjour,\n\nLa facture {facture.numero} de votre abonnement est disponible :\n"
            f"{facture.libelle}\nMontant : {montant_fcfa(facture.montant)}, à régler avant le "
            f"{facture.date_echeance:%d/%m/%Y}.\n\nRetrouvez-la dans « Administration › Abonnement » :\n"
            f"{url_for('gouvernance.abonnement', _external=True)}\n\nL'administration de la plateforme"
        ),
    )


def facture_pdf(facture, nom_plateforme, contact_plateforme=None):
    """PDF de la facture (reportlab, sans dépendre de l'école courante)."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from app.services.notifications import montant_fcfa

    def t(texte):
        return str(texte or "").replace(" ", " ").replace(" ", " ").encode("cp1252", "replace").decode("cp1252")

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=A4)
    c.setTitle(t(f"Facture {facture.numero}"))
    largeur, hauteur = A4
    bleu = HexColor("#0F5FA6")
    c.setFillColor(bleu)
    c.rect(0, hauteur - 32 * mm, largeur, 32 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, hauteur - 18 * mm, t(nom_plateforme))
    c.setFont("Helvetica", 10)
    if contact_plateforme:
        c.drawString(20 * mm, hauteur - 25 * mm, t(contact_plateforme))
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(largeur - 20 * mm, hauteur - 18 * mm, t(f"FACTURE {facture.numero}"))
    c.setFont("Helvetica", 10)
    c.drawRightString(largeur - 20 * mm, hauteur - 25 * mm, t(f"Émise le {facture.date_emission:%d/%m/%Y}"))

    c.setFillColorRGB(0, 0, 0)
    y = hauteur - 48 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Facturé à")
    c.setFont("Helvetica", 11)
    ecole = facture.ecole
    for ligne in [ecole.nom, ", ".join(v for v in (ecole.ville, ecole.pays) if v), ecole.contact_nom, ecole.contact_telephone, ecole.contact_email]:
        if ligne:
            y -= 6 * mm
            c.drawString(20 * mm, y, t(ligne))

    y -= 16 * mm
    c.setFillColor(HexColor("#F2F7FB"))
    c.rect(20 * mm, y - 2 * mm, largeur - 40 * mm, 9 * mm, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(23 * mm, y + 1 * mm, "Désignation")
    c.drawRightString(132 * mm, y + 1 * mm, "Quantité")
    c.drawRightString(160 * mm, y + 1 * mm, "Prix unitaire")
    c.drawRightString(largeur - 23 * mm, y + 1 * mm, "Montant")
    y -= 10 * mm
    c.setFont("Helvetica", 10)
    libelle = t(facture.libelle)
    while c.stringWidth(libelle, "Helvetica", 10) > 85 * mm:
        libelle = libelle[:-2]
    c.drawString(23 * mm, y, libelle)
    c.drawRightString(132 * mm, y, str(facture.quantite))
    c.drawRightString(160 * mm, y, t(montant_fcfa(facture.prix_unitaire)))
    c.drawRightString(largeur - 23 * mm, y, t(montant_fcfa(facture.montant)))
    y -= 6 * mm
    c.setStrokeColor(HexColor("#D5DFE8"))
    c.line(20 * mm, y, largeur - 20 * mm, y)
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(largeur - 23 * mm, y, t(f"Total : {montant_fcfa(facture.montant)}"))

    y -= 16 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, t(f"Période couverte : du {facture.periode_debut:%d/%m/%Y} au {facture.periode_fin:%d/%m/%Y}"))
    y -= 6 * mm
    c.drawString(20 * mm, y, t(f"À régler avant le : {facture.date_echeance:%d/%m/%Y}"))
    y -= 6 * mm
    statut = STATUTS_FACTURE.get(facture.statut, facture.statut)
    if facture.statut == "payee" and facture.date_paiement:
        statut += f" le {facture.date_paiement:%d/%m/%Y}" + (
            f" ({MODES_REGLEMENT.get(facture.mode_reglement, facture.mode_reglement)}"
            f"{', réf. ' + facture.reference_reglement if facture.reference_reglement else ''})" if facture.mode_reglement else "")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, t(f"Statut : {statut}"))
    if facture.note:
        y -= 8 * mm
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, y, t(facture.note))
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#5B6775"))
    c.drawCentredString(largeur / 2, 12 * mm, t(f"{nom_plateforme} — facture générée par la plateforme"))
    c.showPage()
    c.save()
    return tampon.getvalue()

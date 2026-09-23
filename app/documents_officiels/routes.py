from flask import render_template, make_response
from flask_login import login_required

from app.models.eleve import Eleve
from app.documents_officiels import documents_officiels_bp
from app.utils import roles_required, html_vers_pdf
from app.services.documents_officiels import (
    numero_reference, lieu_et_date_officiels, contexte_entete_officiel,
)
from app.services.journal import journaliser
from app.extensions import db

ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]


@documents_officiels_bp.route("/eleve/<int:eleve_id>/certificat")
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def certificat_scolarite(eleve_id):
    """Certificat de scolarité — atteste qu'un élève est bien inscrit
    pour l'année en cours. Numéro et date générés automatiquement,
    jamais saisis à la main (sept. 2026)."""
    eleve = Eleve.query.get_or_404(eleve_id)
    numero = numero_reference("CERT")
    journaliser("generation_certificat_scolarite", details=f"{eleve.nom_complet} — {numero}", cible_type="Eleve", cible_id=eleve.id)
    db.session.commit()

    from app.models.parametre import ParametreEtablissement
    parametre = ParametreEtablissement.get()

    html = render_template(
        "documents_officiels/certificat_scolarite.html",
        eleve=eleve, numero=numero, lieu_et_date=lieu_et_date_officiels(), parametre=parametre,
        **contexte_entete_officiel(),
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename=certificat_scolarite_{eleve.matricule}.pdf"
    return reponse


@documents_officiels_bp.route("/eleve/<int:eleve_id>/attestation")
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def attestation_frequentation(eleve_id):
    """Attestation de fréquentation — version plus courte que le
    certificat, pour les cas où une simple confirmation suffit."""
    eleve = Eleve.query.get_or_404(eleve_id)
    numero = numero_reference("ATTEST")
    journaliser("generation_attestation_frequentation", details=f"{eleve.nom_complet} — {numero}", cible_type="Eleve", cible_id=eleve.id)
    db.session.commit()

    from app.models.parametre import ParametreEtablissement
    parametre = ParametreEtablissement.get()

    html = render_template(
        "documents_officiels/attestation_frequentation.html",
        eleve=eleve, numero=numero, lieu_et_date=lieu_et_date_officiels(), parametre=parametre,
        **contexte_entete_officiel(),
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename=attestation_frequentation_{eleve.matricule}.pdf"
    return reponse

from flask import render_template, make_response, request
from flask_login import login_required

from app.models.eleve import Eleve
from app.models.parametre import ParametreEtablissement
from app.documents_officiels import documents_officiels_bp
from app.utils import roles_required, html_vers_pdf
from app.services.documents_officiels import (
    numero_reference, contexte_entete_officiel,
)
from app.services.journal import journaliser
from app.extensions import db

ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]

DOCUMENTS = {
    "certificat": ("CERT", "Certificat de scolarité", "documents_officiels/certificat_scolarite.html", "certificat_scolarite"),
    "attestation": ("ATTEST", "Attestation de fréquentation", "documents_officiels/attestation_frequentation.html", "attestation_frequentation"),
}


def signataire_depuis_formulaire():
    """Signataire saisi juste avant la génération (pré-rempli avec les
    paramètres de l'établissement)."""
    parametre = ParametreEtablissement.get()
    genre = request.form.get("signataire_genre") or parametre.genre_directeur or "M"
    return {
        "nom": request.form.get("signataire_nom", "").strip() or (parametre.nom_directeur or ""),
        "qualite": request.form.get("signataire_qualite", "").strip() or (parametre.titre_directeur or "Directeur"),
        "genre": genre if genre in ("M", "F") else "M",
    }


def _generer(eleve_id, type_doc):
    code, libelle, modele, prefixe_fichier = DOCUMENTS[type_doc]
    eleve = Eleve.query.get_or_404(eleve_id)

    if request.method == "GET":
        return render_template(
            "documents_officiels/preparer.html",
            eleve=eleve, libelle=libelle, parametre=ParametreEtablissement.get(),
        )

    signataire = signataire_depuis_formulaire()
    numero = numero_reference(code)
    journaliser(f"generation_{prefixe_fichier}", details=f"{eleve.nom_complet} — {numero}", cible_type="Eleve", cible_id=eleve.id)
    db.session.commit()

    contexte = contexte_entete_officiel()
    contexte["signataire"] = signataire
    html = render_template(modele, eleve=eleve, numero=numero, **contexte)
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename={prefixe_fichier}_{eleve.matricule}.pdf"
    return reponse


@documents_officiels_bp.route("/eleve/<int:eleve_id>/certificat", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def certificat_scolarite(eleve_id):
    return _generer(eleve_id, "certificat")


@documents_officiels_bp.route("/eleve/<int:eleve_id>/attestation", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def attestation_frequentation(eleve_id):
    return _generer(eleve_id, "attestation")

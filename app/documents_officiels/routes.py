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
    eleve = db.get_or_404(Eleve, eleve_id)

    if request.method == "GET":
        return render_template(
            "documents_officiels/preparer.html",
            eleve=eleve, libelle=libelle, parametre=ParametreEtablissement.get(),
        )

    from app.services.verification import emettre_document_eleve, bloc_verification

    signataire = signataire_depuis_formulaire()
    numero = numero_reference(code)
    journaliser(f"generation_{prefixe_fichier}", details=f"{eleve.nom_complet} — {numero}", cible_type="Eleve", cible_id=eleve.id)
    document = emettre_document_eleve(type_doc, eleve, numero, signataire)
    db.session.commit()

    contexte = contexte_entete_officiel()
    contexte["signataire"] = signataire
    contexte["verification"] = bloc_verification(document)
    html = render_template(modele, eleve=eleve, numero=numero, **contexte)
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename={prefixe_fichier}_{eleve.matricule}.pdf"
    return reponse


@documents_officiels_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def index():
    """Entrée du menu : retrouver un élève et éditer ses documents."""
    from flask_login import current_user
    from app.models.classe import Classe
    from app.services.cycles import cycle_du_role, filtrer_par_cycle
    from app.services.pagination import paginer

    terme = request.args.get("q", "").strip()
    classes = filtrer_par_cycle(Classe.query.all(), cycle_du_role(current_user.role))
    requete = Eleve.query.filter(Eleve.actif.is_(True), Eleve.classe_id.in_([c.id for c in classes]))
    if terme:
        motif = f"%{terme}%"
        requete = requete.filter(db.or_(Eleve.nom_complet.ilike(motif), Eleve.matricule.ilike(motif)))
    page = paginer(requete.order_by(Eleve.nom_complet))
    return render_template("documents_officiels/index.html", page=page, terme=terme)


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

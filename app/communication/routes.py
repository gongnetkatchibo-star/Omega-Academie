import os
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, send_from_directory, current_app, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.annonce import Annonce, DESTINATAIRES, DESTINATAIRES_ENSEIGNANT
from app.communication import communication_bp
from app.utils import roles_required

ROLES_GESTION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "secretaire", "enseignant"]


def _dossier_upload():
    dossier = os.path.join(current_app.instance_path, "communication")
    os.makedirs(dossier, exist_ok=True)
    return dossier


@communication_bp.route("/")
@login_required
def liste():
    if current_user.role == "developpeur":
        annonces = Annonce.query.order_by(Annonce.date_publication.desc()).all()
    else:
        annonces = Annonce.query.filter(
            (Annonce.destinataire == "tous") | (Annonce.destinataire == current_user.role)
        ).order_by(Annonce.date_publication.desc()).all()
    return render_template("communication/liste.html", annonces=annonces)


@communication_bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="communication")
def nouvelle():
    destinataires_disponibles = (
        DESTINATAIRES_ENSEIGNANT if current_user.role == "enseignant" else DESTINATAIRES
    )

    if request.method == "POST":
        titre = request.form.get("titre", "").strip()
        contenu = request.form.get("contenu", "").strip()
        destinataire = request.form.get("destinataire")
        fichier = request.files.get("fichier")

        if not titre or not contenu or destinataire not in destinataires_disponibles:
            # Le deuxieme test bloque aussi un enseignant qui tenterait de
            # forcer "tous" en modifiant le formulaire (controle serveur,
            # pas seulement l'option masquee cote client).
            flash("Merci de remplir tous les champs (et de choisir un destinataire autorisé).", "error")
            return render_template("communication/nouvelle.html", destinataires=destinataires_disponibles)

        nom_unique = None
        if fichier and fichier.filename:
            nom_securise = secure_filename(fichier.filename)
            nom_unique = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{nom_securise}"
            fichier.save(os.path.join(_dossier_upload(), nom_unique))

        annonce = Annonce(
            titre=titre, contenu=contenu, destinataire=destinataire,
            nom_fichier=nom_unique, auteur_id=current_user.id,
        )
        db.session.add(annonce)
        db.session.commit()

        from app.services.notifications import notifier_annonce
        notifier_annonce(annonce)

        flash("Annonce publiée.", "info")
        return redirect(url_for("communication.liste"))

    return render_template("communication/nouvelle.html", destinataires=destinataires_disponibles)


@communication_bp.route("/<int:annonce_id>/fichier")
@login_required
def telecharger(annonce_id):
    annonce = Annonce.query.get_or_404(annonce_id)
    if current_user.role != "developpeur" and annonce.destinataire != "tous" and annonce.destinataire != current_user.role:
        abort(403)
    if not annonce.nom_fichier:
        abort(404)
    return send_from_directory(_dossier_upload(), annonce.nom_fichier, as_attachment=True)

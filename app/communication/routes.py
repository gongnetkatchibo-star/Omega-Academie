import os
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, send_from_directory, current_app, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.annonce import Annonce, DESTINATAIRES, DESTINATAIRES_ENSEIGNANT
from app.communication import communication_bp
from app.utils import roles_required, EXTENSIONS_PIECE_JOINTE, extension_autorisee

ROLES_GESTION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "secretaire", "enseignant"]


def _dossier_upload():
    dossier = os.path.join(current_app.instance_path, "communication")
    os.makedirs(dossier, exist_ok=True)
    return dossier


@communication_bp.route("/")
@login_required
def liste():
    if current_user.role == "developpeur":
        requete = Annonce.query
    else:
        requete = Annonce.query.filter(
            (Annonce.destinataire == "tous") | (Annonce.destinataire == current_user.role)
        )

    filtre_date_str = request.args.get("date", "").strip()
    filtre_mois = request.args.get("mois", type=int)
    filtre_annee = request.args.get("annee", type=int)

    filtre_date = None
    if filtre_date_str:
        try:
            filtre_date = datetime.strptime(filtre_date_str, "%Y-%m-%d").date()
            requete = requete.filter(db.func.date(Annonce.date_publication) == filtre_date)
        except ValueError:
            pass
    if filtre_mois:
        requete = requete.filter(db.extract("month", Annonce.date_publication) == filtre_mois)
    if filtre_annee:
        requete = requete.filter(db.extract("year", Annonce.date_publication) == filtre_annee)

    annonces = requete.order_by(Annonce.date_publication.desc()).all()

    toutes_les_annees = {a.date_publication.year for a in Annonce.query.all()}
    annee_courante = datetime.utcnow().year
    annees_disponibles = sorted(toutes_les_annees | {annee_courante}, reverse=True)

    return render_template(
        "communication/liste.html", annonces=annonces,
        filtre_date=filtre_date_str, filtre_mois=filtre_mois, filtre_annee=filtre_annee,
        annees_disponibles=annees_disponibles,
        mois_libelles=["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"],
    )


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

        if fichier and fichier.filename and not extension_autorisee(fichier.filename, EXTENSIONS_PIECE_JOINTE):
            flash("Type de pièce jointe non autorisé (document ou image uniquement).", "error")
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


@communication_bp.route("/<int:annonce_id>")
@login_required
def detail(annonce_id):
    """Page d'une seule annonce — cible du lien « Voir plus » envoyé par
    email (sept. 2026). Si la personne n'est pas connectée, elle est
    d'abord renvoyée vers la connexion, puis ramenée ici."""
    annonce = Annonce.query.get_or_404(annonce_id)

    destinee_a_moi = annonce.destinataire in ("tous", current_user.role)
    if not destinee_a_moi and current_user.role != "developpeur":
        abort(403)

    return render_template("communication/detail.html", annonce=annonce)


@communication_bp.route("/<int:annonce_id>/supprimer", methods=["POST"])
@login_required
def supprimer(annonce_id):
    annonce = Annonce.query.get_or_404(annonce_id)

    # Volontairement PAS la même liste que pour publier (ROLES_GESTION
    # inclut "enseignant" en général) — ici, un enseignant ne peut
    # supprimer QUE sa propre annonce, jamais celle d'un collègue.
    ROLES_SUPPRESSION_LIBRE = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "secretaire"]
    est_auteur = annonce.auteur_id == current_user.id
    if current_user.role not in ROLES_SUPPRESSION_LIBRE and not (current_user.role == "enseignant" and est_auteur):
        abort(403)

    if annonce.nom_fichier:
        chemin = os.path.join(_dossier_upload(), annonce.nom_fichier)
        if os.path.exists(chemin):
            os.remove(chemin)

    db.session.delete(annonce)
    db.session.commit()
    flash("Annonce supprimée.", "info")
    return redirect(url_for("communication.liste"))


@communication_bp.route("/<int:annonce_id>/fichier")
@login_required
def telecharger(annonce_id):
    annonce = Annonce.query.get_or_404(annonce_id)
    if current_user.role != "developpeur" and annonce.destinataire != "tous" and annonce.destinataire != current_user.role:
        abort(403)
    if not annonce.nom_fichier:
        abort(404)
    return send_from_directory(_dossier_upload(), annonce.nom_fichier, as_attachment=True)

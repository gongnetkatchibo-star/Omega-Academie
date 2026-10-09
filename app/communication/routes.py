import io
import os
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, send_from_directory, send_file, current_app, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.annonce import Annonce, DESTINATAIRES, DESTINATAIRES_ENSEIGNANT, LIBELLES_DESTINATAIRE
from app.communication import communication_bp
from app.utils import roles_required, EXTENSIONS_PIECE_JOINTE, extension_autorisee
from app.services.temps import maintenant

ROLES_GESTION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "secretaire", "enseignant"]

# Direction et secrétariat voient (et peuvent retirer) toutes les
# annonces de l'école, y compris celles adressées aux parents ou aux
# élèves : ce sont eux qui les publient et qui en répondent.
ROLES_TOUT_VOIR = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "secretaire"]


def _dossier_upload():
    """Ancien emplacement des pièces jointes (sur le disque). Les
    nouvelles sont enregistrées en base, avec l'annonce."""
    dossier = os.path.join(current_app.instance_path, "communication")
    os.makedirs(dossier, exist_ok=True)
    return dossier


def _voit_tout():
    return current_user.role == "developpeur" or current_user.role in ROLES_TOUT_VOIR


def _publics():
    """Destinataires dont fait partie le compte connecté. Tout compte
    auquel un enfant est rattaché reçoit aussi les annonces aux parents
    (un enseignant ou un comptable peut être parent d'élève)."""
    publics = {"tous", current_user.role}
    if current_user.enfants:
        publics.add("parent")
    return publics


def _peut_lire(annonce):
    return _voit_tout() or annonce.destinataire in _publics() or annonce.auteur_id == current_user.id


@communication_bp.route("/")
@login_required
def liste():
    requete = Annonce.query
    if not _voit_tout():
        # Ce qui m'est adressé, plus ce que j'ai moi-même publié.
        requete = requete.filter(db.or_(
            Annonce.destinataire.in_(_publics()), Annonce.auteur_id == current_user.id,
        ))

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

    toutes_les_annees = {
        int(annee) for (annee,) in
        db.session.query(db.extract("year", Annonce.date_publication)).distinct() if annee
    }
    annee_courante = maintenant().year
    annees_disponibles = sorted(toutes_les_annees | {annee_courante}, reverse=True)

    return render_template(
        "communication/liste.html", annonces=annonces,
        filtre_date=filtre_date_str, filtre_mois=filtre_mois, filtre_annee=filtre_annee,
        annees_disponibles=annees_disponibles, libelles_destinataire=LIBELLES_DESTINATAIRE,
        mois_libelles=["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"],
    )


@communication_bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="communication")
def nouvelle():
    destinataires_disponibles = (
        DESTINATAIRES_ENSEIGNANT if current_user.role == "enseignant" else DESTINATAIRES
    )

    def formulaire():
        return render_template(
            "communication/nouvelle.html", destinataires=destinataires_disponibles,
            libelles_destinataire=LIBELLES_DESTINATAIRE,
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
            return formulaire()

        if fichier and fichier.filename and not extension_autorisee(fichier.filename, EXTENSIONS_PIECE_JOINTE):
            flash("Type de pièce jointe non autorisé (document ou image uniquement).", "error")
            return formulaire()

        annonce = Annonce(titre=titre, contenu=contenu, destinataire=destinataire, auteur_id=current_user.id)
        if fichier and fichier.filename:
            # La pièce jointe est enregistrée en base, avec l'annonce :
            # elle fait ainsi partie des sauvegardes de l'école.
            annonce.nom_fichier = secure_filename(fichier.filename)[:255] or "piece_jointe"
            annonce.fichier = fichier.read()
            annonce.fichier_mime = (fichier.mimetype or "application/octet-stream")[:100]
        db.session.add(annonce)
        db.session.commit()

        from app.services.notifications import notifier_annonce
        notifier_annonce(annonce)

        flash("Annonce publiée.", "info")
        return redirect(url_for("communication.liste"))

    return formulaire()


@communication_bp.route("/<int:annonce_id>")
@login_required
def detail(annonce_id):
    """Page d'une seule annonce — cible du lien « Voir plus » envoyé par
    email (sept. 2026). Si la personne n'est pas connectée, elle est
    d'abord renvoyée vers la connexion, puis ramenée ici."""
    annonce = db.get_or_404(Annonce, annonce_id)
    if not _peut_lire(annonce):
        abort(403)
    return render_template("communication/detail.html", annonce=annonce, libelles_destinataire=LIBELLES_DESTINATAIRE)


@communication_bp.route("/<int:annonce_id>/supprimer", methods=["POST"])
@login_required
def supprimer(annonce_id):
    annonce = db.get_or_404(Annonce, annonce_id)

    # Volontairement PAS la même liste que pour publier (ROLES_GESTION
    # inclut "enseignant" en général) — ici, un enseignant ne peut
    # supprimer QUE sa propre annonce, jamais celle d'un collègue.
    est_auteur = annonce.auteur_id == current_user.id
    if current_user.role not in ROLES_TOUT_VOIR and not (current_user.role == "enseignant" and est_auteur):
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
    annonce = db.get_or_404(Annonce, annonce_id)
    if not _peut_lire(annonce):
        abort(403)
    if not annonce.nom_fichier:
        abort(404)
    if annonce.fichier:
        # Toujours en téléchargement, jamais affichée dans la page : un
        # fichier envoyé par un utilisateur ne s'exécute pas dans le site.
        return send_file(
            io.BytesIO(annonce.fichier), as_attachment=True, download_name=annonce.nom_fichier,
            mimetype=annonce.fichier_mime or "application/octet-stream",
        )
    # Pièce jointe d'avant l'enregistrement en base : encore sur le disque.
    return send_from_directory(_dossier_upload(), annonce.nom_fichier, as_attachment=True)

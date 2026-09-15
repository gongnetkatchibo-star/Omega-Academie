import os
import io
import zipfile
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, send_from_directory, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.ressource import Ressource, TYPES_RESSOURCE
from app.bibliotheque import bibliotheque_bp
from app.utils import roles_required

ROLES_GESTION = ["bibliothecaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "enseignant"]


def _dossier_upload():
    dossier = os.path.join(current_app.instance_path, "bibliotheque")
    os.makedirs(dossier, exist_ok=True)
    return dossier


@bibliotheque_bp.route("/")
@login_required
def liste():
    type_filtre = request.args.get("type")
    requete = Ressource.query
    if type_filtre:
        requete = requete.filter_by(type=type_filtre)
    ressources = requete.order_by(Ressource.date_ajout.desc()).all()
    return render_template(
        "bibliotheque/liste.html", ressources=ressources, types=TYPES_RESSOURCE, type_filtre=type_filtre
    )


@bibliotheque_bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="bibliotheque")
def nouvelle():
    if request.method == "POST":
        titre = request.form.get("titre", "").strip()
        type_ = request.form.get("type")
        matiere = request.form.get("matiere", "").strip()
        description = request.form.get("description", "").strip()
        fichier = request.files.get("fichier")

        if not titre or type_ not in TYPES_RESSOURCE or not fichier or fichier.filename == "":
            flash("Merci de remplir le titre, le type et de choisir un fichier.", "error")
            return render_template("bibliotheque/nouvelle.html", types=TYPES_RESSOURCE)

        nom_securise = secure_filename(fichier.filename)
        nom_unique = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{nom_securise}"
        fichier.save(os.path.join(_dossier_upload(), nom_unique))

        db.session.add(Ressource(
            titre=titre, type=type_, matiere=matiere or None, description=description or None,
            nom_fichier=nom_unique, ajoute_par_id=current_user.id,
        ))
        db.session.commit()
        flash("Ressource ajoutée.", "info")
        return redirect(url_for("bibliotheque.liste"))

    return render_template("bibliotheque/nouvelle.html", types=TYPES_RESSOURCE)


@bibliotheque_bp.route("/<int:ressource_id>/telecharger")
@login_required
def telecharger(ressource_id):
    ressource = Ressource.query.get_or_404(ressource_id)
    return send_from_directory(
        _dossier_upload(), ressource.nom_fichier, as_attachment=True, download_name=ressource.titre
    )


@bibliotheque_bp.route("/importer", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="bibliotheque")
def importer():
    """Import en masse : chaque fichier sélectionné devient une ressource
    distincte (titre = nom du fichier), pour ne pas les ajouter un par un
    quand il y en a beaucoup."""
    if request.method == "POST":
        type_ = request.form.get("type")
        matiere = request.form.get("matiere", "").strip()
        fichiers = request.files.getlist("fichiers")

        if type_ not in TYPES_RESSOURCE or not fichiers or all(f.filename == "" for f in fichiers):
            flash("Merci de choisir un type et au moins un fichier.", "error")
            return render_template("bibliotheque/importer.html", types=TYPES_RESSOURCE)

        nb_importes = 0
        for fichier in fichiers:
            if not fichier or fichier.filename == "":
                continue
            nom_securise = secure_filename(fichier.filename)
            nom_unique = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{nom_securise}"
            fichier.save(os.path.join(_dossier_upload(), nom_unique))
            titre = os.path.splitext(nom_securise)[0]
            db.session.add(Ressource(
                titre=titre, type=type_, matiere=matiere or None,
                nom_fichier=nom_unique, ajoute_par_id=current_user.id,
            ))
            nb_importes += 1

        db.session.commit()
        flash(f"{nb_importes} fichier(s) importé(s).", "info")
        return redirect(url_for("bibliotheque.liste"))

    return render_template("bibliotheque/importer.html", types=TYPES_RESSOURCE)


@bibliotheque_bp.route("/exporter")
@login_required
@roles_required(*ROLES_GESTION, module="bibliotheque")
def exporter():
    """Télécharge toutes les ressources (ou celles du type filtré) en un
    seul fichier ZIP — pour récupérer/sauvegarder tout d'un coup."""
    type_filtre = request.args.get("type")
    requete = Ressource.query
    if type_filtre:
        requete = requete.filter_by(type=type_filtre)
    ressources = requete.all()

    if not ressources:
        flash("Aucune ressource à exporter.", "error")
        return redirect(url_for("bibliotheque.liste"))

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        noms_utilises = set()
        for r in ressources:
            chemin = os.path.join(_dossier_upload(), r.nom_fichier)
            if not os.path.exists(chemin):
                continue
            extension = os.path.splitext(r.nom_fichier)[1]
            nom_dans_zip = f"{r.titre}{extension}"
            # Évite d'écraser un fichier si deux ressources ont le même titre.
            base_nom = nom_dans_zip
            compteur = 1
            while nom_dans_zip in noms_utilises:
                nom_dans_zip = f"{os.path.splitext(base_nom)[0]}_{compteur}{extension}"
                compteur += 1
            noms_utilises.add(nom_dans_zip)
            archive.write(chemin, arcname=nom_dans_zip)

    tampon.seek(0)
    nom_zip = f"bibliotheque_{type_filtre}.zip" if type_filtre else "bibliotheque_complete.zip"
    return send_file(tampon, as_attachment=True, download_name=nom_zip, mimetype="application/zip")

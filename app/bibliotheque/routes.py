import io
import zipfile

from flask import render_template, redirect, url_for, flash, request, send_file, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.ressource import Ressource, TYPES_RESSOURCE
from app.bibliotheque import bibliotheque_bp
from app.utils import roles_required, EXTENSIONS_BIBLIOTHEQUE, extension_autorisee
from app.services.journal import journaliser

ROLES_GESTION = ["bibliothecaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "enseignant"]


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
        verrouillee = request.form.get("consultation_sur_place") == "on"

        if not titre or type_ not in TYPES_RESSOURCE or not fichier or fichier.filename == "":
            flash("Merci de remplir le titre, le type et de choisir un fichier.", "error")
            return render_template("bibliotheque/nouvelle.html", types=TYPES_RESSOURCE)

        if not extension_autorisee(fichier.filename, EXTENSIONS_BIBLIOTHEQUE):
            flash("Type de fichier non autorisé (document, image ou vidéo uniquement).", "error")
            return render_template("bibliotheque/nouvelle.html", types=TYPES_RESSOURCE)

        nom_securise = secure_filename(fichier.filename)
        db.session.add(Ressource(
            titre=titre, type=type_, matiere=matiere or None, description=description or None,
            nom_fichier=nom_securise, contenu=fichier.read(), type_mime=fichier.mimetype,
            ajoute_par_id=current_user.id, consultation_sur_place=verrouillee,
        ))
        db.session.commit()
        flash("Ressource ajoutée.", "info")
        return redirect(url_for("bibliotheque.liste"))

    return render_template("bibliotheque/nouvelle.html", types=TYPES_RESSOURCE)


@bibliotheque_bp.route("/<int:ressource_id>/telecharger")
@login_required
def telecharger(ressource_id):
    ressource = Ressource.query.get_or_404(ressource_id)

    if not ressource.contenu:
        flash("Ce fichier n'est plus disponible — il a été ajouté avant la mise en place du stockage permanent. Merci de le réimporter.", "error")
        return redirect(url_for("bibliotheque.liste"))

    tampon = io.BytesIO(ressource.contenu)
    if ressource.consultation_sur_place:
        # Verrouillée par le bibliothécaire : consultable en ligne
        # (ouverture dans le navigateur), mais jamais enregistrable
        # comme un vrai téléchargement (sept. 2026).
        return send_file(tampon, mimetype=ressource.type_mime, as_attachment=False, download_name=ressource.nom_fichier)
    return send_file(tampon, mimetype=ressource.type_mime, as_attachment=True, download_name=ressource.nom_fichier)


@bibliotheque_bp.route("/<int:ressource_id>/verrouiller", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="bibliotheque")
def basculer_verrouillage(ressource_id):
    ressource = Ressource.query.get_or_404(ressource_id)
    ressource.consultation_sur_place = not ressource.consultation_sur_place
    db.session.commit()
    etat = "verrouillée (consultation sur place)" if ressource.consultation_sur_place else "déverrouillée (téléchargeable)"
    flash(f"« {ressource.titre} » est maintenant {etat}.", "info")
    return redirect(url_for("bibliotheque.liste"))


@bibliotheque_bp.route("/<int:ressource_id>/supprimer", methods=["POST"])
@login_required
def supprimer(ressource_id):
    """Le bibliothécaire et la direction peuvent supprimer n'importe
    quelle ressource ; un enseignant ne peut supprimer que celles qu'il
    a lui-même ajoutées (même logique que les annonces, sept. 2026)."""
    ressource = Ressource.query.get_or_404(ressource_id)

    ROLES_SUPPRESSION_LIBRE = ["bibliothecaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "developpeur"]
    est_auteur = ressource.ajoute_par_id == current_user.id
    if current_user.role not in ROLES_SUPPRESSION_LIBRE and not (current_user.role == "enseignant" and est_auteur):
        abort(403)

    titre = ressource.titre
    journaliser("suppression_ressource", details=titre, cible_type="Ressource", cible_id=ressource.id)
    db.session.delete(ressource)
    db.session.commit()
    flash(f"« {titre} » supprimée de la bibliothèque.", "info")
    return redirect(url_for("bibliotheque.liste"))


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
        verrouillee = request.form.get("consultation_sur_place") == "on"

        if type_ not in TYPES_RESSOURCE or not fichiers or all(f.filename == "" for f in fichiers):
            flash("Merci de choisir un type et au moins un fichier.", "error")
            return render_template("bibliotheque/importer.html", types=TYPES_RESSOURCE)

        nb_importes = 0
        nb_rejetes = 0
        for fichier in fichiers:
            if not fichier or fichier.filename == "":
                continue
            if not extension_autorisee(fichier.filename, EXTENSIONS_BIBLIOTHEQUE):
                nb_rejetes += 1
                continue
            nom_securise = secure_filename(fichier.filename)
            titre = nom_securise.rsplit(".", 1)[0]
            db.session.add(Ressource(
                titre=titre, type=type_, matiere=matiere or None,
                nom_fichier=nom_securise, contenu=fichier.read(), type_mime=fichier.mimetype,
                ajoute_par_id=current_user.id, consultation_sur_place=verrouillee,
            ))
            nb_importes += 1

        db.session.commit()
        message = f"{nb_importes} fichier(s) importé(s)."
        if nb_rejetes:
            message += f" {nb_rejetes} fichier(s) rejeté(s) (type non autorisé)."
        flash(message, "info")
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
    # Une ressource verrouillée (consultation sur place) ne sort jamais
    # dans un export groupé — sinon le verrouillage individuel ne
    # servirait à rien (sept. 2026).
    ressources = requete.filter_by(consultation_sur_place=False).all()
    ressources = [r for r in ressources if r.contenu]

    if not ressources:
        flash("Aucune ressource téléchargeable à exporter (les ressources verrouillées ou sans fichier ne sont jamais incluses).", "error")
        return redirect(url_for("bibliotheque.liste"))

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        noms_utilises = set()
        for r in ressources:
            extension = ("." + r.nom_fichier.rsplit(".", 1)[1]) if "." in r.nom_fichier else ""
            nom_dans_zip = f"{r.titre}{extension}"
            base_nom = nom_dans_zip
            compteur = 1
            while nom_dans_zip in noms_utilises:
                nom_dans_zip = f"{base_nom.rsplit('.', 1)[0]}_{compteur}{extension}"
                compteur += 1
            noms_utilises.add(nom_dans_zip)
            archive.writestr(nom_dans_zip, r.contenu)

    tampon.seek(0)
    nom_zip = f"bibliotheque_{type_filtre}.zip" if type_filtre else "bibliotheque_complete.zip"
    return send_file(tampon, as_attachment=True, download_name=nom_zip, mimetype="application/zip")

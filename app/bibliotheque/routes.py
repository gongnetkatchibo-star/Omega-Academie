import io
import zipfile

from flask import render_template, redirect, url_for, flash, request, send_file, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.ressource import Ressource, TYPES_RESSOURCE, LIBELLES_TYPE, PUBLICS_RESSOURCE
from app.bibliotheque import bibliotheque_bp
from app.utils import roles_required, EXTENSIONS_BIBLIOTHEQUE, extension_autorisee, nom_fichier_sur, type_mime_sur
from app.services.journal import journaliser

ROLES_GESTION = ["bibliothecaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "enseignant"]
# Seuls eux verrouillent ou déverrouillent une ressource qu'ils n'ont pas
# ajoutée (un enseignant ne lève pas le verrou du bibliothécaire).
ROLES_RESPONSABLES = ["bibliothecaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "developpeur"]


def _voit_ressources_du_personnel():
    return current_user.role not in ("parent", "eleve")


def _ressources_visibles():
    requete = Ressource.query
    if not _voit_ressources_du_personnel():
        requete = requete.filter(Ressource.public == "tous")
    return requete


def _contexte_formulaire():
    return {"types": TYPES_RESSOURCE, "libelles_type": LIBELLES_TYPE, "publics": PUBLICS_RESSOURCE}


def _lire_fichier(fichier, deja_reserve=0):
    """(contenu, None) ou (None, message d'erreur)."""
    from app.services.stockage import place_disponible

    contenu = fichier.read()
    if not contenu:
        return None, f"« {fichier.filename} » est vide."
    erreur = place_disponible(len(contenu) + deja_reserve)
    return (None, erreur) if erreur else (contenu, None)


@bibliotheque_bp.route("/")
@login_required
def liste():
    from app.services.pagination import paginer

    type_filtre = request.args.get("type")
    terme = request.args.get("q", "").strip()
    requete = _ressources_visibles()
    if type_filtre in TYPES_RESSOURCE:
        requete = requete.filter_by(type=type_filtre)
    if terme:
        motif = f"%{terme}%"
        requete = requete.filter(db.or_(Ressource.titre.ilike(motif), Ressource.matiere.ilike(motif), Ressource.description.ilike(motif)))
    page = paginer(requete.order_by(Ressource.date_ajout.desc()))
    return render_template(
        "bibliotheque/liste.html", ressources=page, page=page, type_filtre=type_filtre, terme=terme,
        responsable=current_user.role in ROLES_RESPONSABLES, **_contexte_formulaire(),
    )


@bibliotheque_bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="bibliotheque")
def nouvelle():
    if request.method == "POST":
        titre = request.form.get("titre", "").strip()[:150]
        type_ = request.form.get("type")
        matiere = request.form.get("matiere", "").strip()[:80]
        description = request.form.get("description", "").strip()[:1000]
        public = request.form.get("public") if request.form.get("public") in PUBLICS_RESSOURCE else "tous"
        fichier = request.files.get("fichier")
        verrouillee = request.form.get("consultation_sur_place") == "on"

        if not titre or type_ not in TYPES_RESSOURCE or not fichier or fichier.filename == "":
            flash("Merci de remplir le titre, le type et de choisir un fichier.", "error")
            return render_template("bibliotheque/nouvelle.html", **_contexte_formulaire())

        if not extension_autorisee(fichier.filename, EXTENSIONS_BIBLIOTHEQUE):
            flash("Type de fichier non autorisé (document, image ou vidéo uniquement).", "error")
            return render_template("bibliotheque/nouvelle.html", **_contexte_formulaire())

        contenu, erreur = _lire_fichier(fichier)
        if erreur:
            flash(erreur, "error")
            return render_template("bibliotheque/nouvelle.html", **_contexte_formulaire())
        nom_securise = nom_fichier_sur(fichier.filename)
        db.session.add(Ressource(
            titre=titre, type=type_, matiere=matiere or None, description=description or None,
            nom_fichier=nom_securise, contenu=contenu, type_mime=type_mime_sur(nom_securise),
            ajoute_par_id=current_user.id, consultation_sur_place=verrouillee, public=public,
        ))
        journaliser("ajout_ressource", details=titre)
        db.session.commit()
        flash("Ressource ajoutée.", "info")
        return redirect(url_for("bibliotheque.liste"))

    return render_template("bibliotheque/nouvelle.html", **_contexte_formulaire())


@bibliotheque_bp.route("/<int:ressource_id>/telecharger")
@login_required
def telecharger(ressource_id):
    ressource = db.get_or_404(Ressource, ressource_id)
    if ressource.public != "tous" and not _voit_ressources_du_personnel():
        abort(404)

    if not ressource.contenu:
        flash("Ce fichier n'est plus disponible — il a été ajouté avant la mise en place du stockage permanent. Merci de le réimporter.", "error")
        return redirect(url_for("bibliotheque.liste"))

    tampon = io.BytesIO(ressource.contenu)
    if ressource.consultation_sur_place:
        # Verrouillée par le bibliothécaire : consultable en ligne
        # (ouverture dans le navigateur), mais jamais enregistrable
        # comme un vrai téléchargement (sept. 2026).
        reponse = send_file(tampon, mimetype=type_mime_sur(ressource.nom_fichier), as_attachment=False,
                            download_name=ressource.nom_fichier)
        # Ouvert dans le navigateur : sans script, isolé du reste du site.
        reponse.headers["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'"
        # Jamais gardée sur l'appareil (ni par le navigateur, ni par
        # l'application hors ligne). Cela décourage la copie, sans
        # l'empêcher tout à fait : une page affichée peut toujours être
        # photographiée.
        reponse.headers["Cache-Control"] = "no-store"
        return reponse
    return send_file(tampon, mimetype=type_mime_sur(ressource.nom_fichier), as_attachment=True,
                     download_name=ressource.nom_fichier)


@bibliotheque_bp.route("/<int:ressource_id>/verrouiller", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="bibliotheque")
def basculer_verrouillage(ressource_id):
    ressource = db.get_or_404(Ressource, ressource_id)
    if current_user.role not in ROLES_RESPONSABLES and ressource.ajoute_par_id != current_user.id:
        abort(403)
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
    ressource = db.get_or_404(Ressource, ressource_id)

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
            return render_template("bibliotheque/importer.html", **_contexte_formulaire())

        public = request.form.get("public") if request.form.get("public") in PUBLICS_RESSOURCE else "tous"
        nb_importes = 0
        refus = []
        reserve = 0
        for fichier in fichiers:
            if not fichier or fichier.filename == "":
                continue
            if not extension_autorisee(fichier.filename, EXTENSIONS_BIBLIOTHEQUE):
                refus.append(f"{fichier.filename} (type non autorisé)")
                continue
            contenu, erreur = _lire_fichier(fichier, reserve)
            if erreur:
                refus.append(f"{fichier.filename} ({erreur})")
                continue
            reserve += len(contenu)
            nom_securise = nom_fichier_sur(fichier.filename)
            titre = fichier.filename.rsplit(".", 1)[0][:150] or nom_securise.rsplit(".", 1)[0]
            db.session.add(Ressource(
                titre=titre, type=type_, matiere=matiere[:80] or None,
                nom_fichier=nom_securise, contenu=contenu, type_mime=type_mime_sur(nom_securise),
                ajoute_par_id=current_user.id, consultation_sur_place=verrouillee, public=public,
            ))
            nb_importes += 1

        if nb_importes:
            journaliser("import_ressources", details=f"{nb_importes} fichier(s)")
        db.session.commit()
        flash(f"{nb_importes} fichier(s) importé(s).", "info")
        for ligne in refus[:10]:
            flash(f"Refusé : {ligne}", "error")
        return redirect(url_for("bibliotheque.liste"))

    return render_template("bibliotheque/importer.html", **_contexte_formulaire())


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
    ids = [i for (i,) in requete.filter_by(consultation_sur_place=False).with_entities(Ressource.id).all()]
    if not ids:
        flash("Aucune ressource téléchargeable à exporter (les ressources verrouillées ne sont jamais incluses).", "error")
        return redirect(url_for("bibliotheque.liste"))

    import tempfile
    from sqlalchemy import select
    # L'archive s'écrit sur le disque au fur et à mesure (un fichier à la
    # fois en mémoire) : une grosse bibliothèque n'épuise pas la mémoire.
    tampon = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        noms_utilises = set()
        for ressource_id in ids:
            titre, nom_fichier, contenu = db.session.execute(
                select(Ressource.titre, Ressource.nom_fichier, Ressource.contenu).where(Ressource.id == ressource_id)
            ).one()
            if not contenu:
                continue
            extension = ("." + nom_fichier.rsplit(".", 1)[1]) if "." in nom_fichier else ""
            base = nom_fichier_sur(f"{titre}{extension}").rsplit(".", 1)[0] if extension else nom_fichier_sur(titre)
            nom_dans_zip, compteur = f"{base}{extension}", 1
            while nom_dans_zip in noms_utilises:
                nom_dans_zip = f"{base}_{compteur}{extension}"
                compteur += 1
            noms_utilises.add(nom_dans_zip)
            archive.writestr(nom_dans_zip, contenu)
            del contenu

    tampon.seek(0)
    nom_zip = f"bibliotheque_{type_filtre}.zip" if type_filtre in TYPES_RESSOURCE else "bibliotheque_complete.zip"
    return send_file(tampon, as_attachment=True, download_name=nom_zip, mimetype="application/zip")

from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.eleve import Eleve, STATUTS_DOSSIER, MAX_PARENTS_PAR_ELEVE, MOTIFS_DEPART, LIBELLES_MOTIF_DEPART
from app.services.moyennes import moyenne_eleve, a_reussi, seuil_reussite_pour_classe
from app.models.historique import HistoriqueScolaire
from app.models.user import User
from app.eleves import eleves_bp
from app.utils import roles_required, export_csv, export_xlsx, export_pdf_liste
from app.services.cycles import cycle_du_role, filtrer_par_cycle, classe_dans_le_cycle, exiger_classe_du_cycle
from app.services.whatsapp import contacts as contacts_whatsapp
from app.services.temps import maintenant

ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]
ROLES_LECTURE = ROLES_GESTION + ["enseignant"]


@eleves_bp.route("/")
@login_required
@roles_required(*ROLES_LECTURE)
def liste():
    from app.services.pagination import paginer

    classe_id = request.args.get("classe_id", type=int)
    terme = request.args.get("q", "").strip()
    requete = Eleve.query.filter_by(actif=True)
    if classe_id:
        requete = requete.filter_by(classe_id=classe_id)
    if terme:
        motif = f"%{terme}%"
        requete = requete.filter(db.or_(Eleve.nom_complet.ilike(motif), Eleve.matricule.ilike(motif)))
    classes = Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau).all()

    cycle = cycle_du_role(current_user.role)
    if cycle:
        du_cycle = [c.id for c in filtrer_par_cycle(Classe.query.all(), cycle)]
        requete = requete.filter(Eleve.classe_id.in_(du_cycle))
        classes = filtrer_par_cycle(classes, cycle)

    if current_user.role == "enseignant":
        from app.services.suivi_eleve import classes_de_l_enseignant
        mes_classes = classes_de_l_enseignant()
        requete = requete.filter(Eleve.classe_id.in_(mes_classes))
        classes = [c for c in classes if c.id in mes_classes]

    page = paginer(requete.order_by(Eleve.nom_complet))
    return render_template("eleves/liste.html", page=page, classes=classes, classe_id=classe_id, terme=terme)


def _classes_importables():
    return filtrer_par_cycle(
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau, Classe.nom).all(),
        cycle_du_role(current_user.role),
    )


@eleves_bp.route("/importer/modele")
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def importer_modele():
    from flask import send_file
    from app.services.import_eleves import modele_excel

    return send_file(
        modele_excel(_classes_importables()), as_attachment=True, download_name="modele_import_eleves.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@eleves_bp.route("/importer", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def importer():
    """Import Excel : tout le fichier est contrôlé avant d'écrire quoi
    que ce soit ; à la moindre erreur, rien n'est importé."""
    from app.services.import_eleves import lire_fichier, importer as importer_lignes
    from app.services.journal import journaliser

    classes = _classes_importables()
    erreurs = []
    if request.method == "POST":
        fichier = request.files.get("fichier")
        if not fichier or not fichier.filename:
            erreurs = ["Choisis le fichier Excel à importer."]
        elif not fichier.filename.lower().endswith(".xlsx"):
            erreurs = ["Le fichier doit être au format Excel (.xlsx)."]
        else:
            lignes, erreurs = lire_fichier(fichier.stream, classes)
            if not erreurs:
                crees, deja = importer_lignes(lignes)
                journaliser("import_eleves", details=f"{crees} élève(s) importé(s), {deja} déjà présent(s)")
                db.session.commit()
                message = f"{crees} élève(s) importé(s)."
                if deja:
                    message += f" {deja} déjà présent(s) dans leur classe, laissé(s) tel(s) quel(s)."
                flash(message, "info")
                return redirect(url_for("eleves.liste"))
    return render_template("eleves/importer.html", classes=classes, erreurs=erreurs)


def _lignes_export_eleves(classe_id=None, cycle=None):
    requete = Eleve.query.filter_by(actif=True)
    if classe_id:
        requete = requete.filter_by(classe_id=classe_id)
    from sqlalchemy.orm import selectinload
    # Parents chargés en une fois (sinon une requête par élève).
    eleves = requete.options(selectinload(Eleve.parents)).order_by(Eleve.nom_complet).all()
    if cycle:
        eleves = [e for e in eleves if classe_dans_le_cycle(e.classe, cycle)]
    entetes = ["Matricule", "Nom complet", "Genre", "Classe", "Téléphone parent", "Statut dossier", "Parent(s) lié(s)"]
    lignes = [
        (
            e.matricule, e.nom_complet, e.sexe or "—", e.classe.nom,
            e.telephone_parent or "—", e.statut_dossier,
            ", ".join(p.nom_complet for p in e.parents) if e.parents else "—",
        )
        for e in eleves
    ]
    return entetes, lignes


@eleves_bp.route("/export/<fmt>")
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def export(fmt):
    classe_id = request.args.get("classe_id", type=int)
    classe_obj = db.session.get(Classe, classe_id) if classe_id else None
    sous_titre = f"Classe : {classe_obj.nom}" if classe_obj else "Toutes classes"
    nom_fichier = f"eleves_{classe_obj.nom}" if classe_obj else "eleves_toutes_classes"
    entetes, lignes = _lignes_export_eleves(classe_id, cycle=cycle_du_role(current_user.role))

    if fmt == "csv":
        return export_csv(entetes, lignes, nom_fichier)
    if fmt == "xlsx":
        return export_xlsx(entetes, lignes, nom_fichier, "Élèves")
    if fmt == "pdf":
        return export_pdf_liste("Liste des élèves", sous_titre, entetes, lignes, nom_fichier)
    flash("Format d'export inconnu.", "error")
    return redirect(url_for("eleves.liste"))


CHAMPS_DOSSIER = {
    "lieu_naissance": 120, "nationalite": 60, "adresse": 200, "nom_pere": 120, "nom_mere": 120,
    "personne_urgence": 120, "telephone_urgence": 30, "ecole_origine": 150,
}


def _appliquer_dossier(eleve):
    """Renseigne les champs du dossier et la photo depuis le formulaire.
    Retourne un message d'erreur, ou None."""
    from app.services.images_ecole import photo_identite

    for champ, longueur in CHAMPS_DOSSIER.items():
        setattr(eleve, champ, request.form.get(champ, "").strip()[:longueur] or None)
    contenu, resultat = photo_identite(request.files.get("photo"))
    if contenu:
        eleve.photo, eleve.photo_mime = contenu, resultat
    elif resultat:
        return resultat
    if request.form.get("retirer_photo") == "on":
        eleve.photo, eleve.photo_mime = None, None
    return None


def _peut_voir(eleve):
    est_lie_comme_parent = current_user in eleve.parents
    est_soi_meme = current_user.role == "eleve" and eleve.user_id == current_user.id
    if est_lie_comme_parent or est_soi_meme or current_user.role == "developpeur":
        return True
    if current_user.role not in ROLES_LECTURE:
        return False
    if current_user.role == "enseignant":
        # Comme pour les bulletins, les absences et le cahier de textes :
        # un enseignant ne consulte que les dossiers de ses propres classes.
        from app.services.suivi_eleve import classes_de_l_enseignant
        return eleve.classe_id in classes_de_l_enseignant()
    # Un directeur de cycle ne voit que les élèves de son cycle.
    cycle = cycle_du_role(current_user.role)
    return not cycle or classe_dans_le_cycle(eleve.classe, cycle)


@eleves_bp.route("/<int:eleve_id>/photo")
@login_required
def photo(eleve_id):
    from flask import Response

    eleve = db.get_or_404(Eleve, eleve_id)
    if not _peut_voir(eleve) or not eleve.photo:
        abort(404)
    reponse = Response(eleve.photo, mimetype=eleve.photo_mime or "image/jpeg")
    reponse.headers["Cache-Control"] = "private, max-age=300"
    return reponse


def _cle_de_fichier(texte):
    """« oa26-cm2-004.JPG », « Oa26 CM2 004 » → « OA26CM2004 » : de quoi
    reconnaître un matricule ou un nom quelle que soit la façon de l'écrire."""
    import unicodedata

    sans_accents = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in sans_accents.upper() if ch.isalnum())


def _eleves_des_photos(classe_id=None):
    """Élèves dont la personne connectée peut gérer la photo."""
    classes = filtrer_par_cycle(Classe.query.all(), cycle_du_role(current_user.role))
    ids = [c.id for c in classes]
    if classe_id:
        ids = [i for i in ids if i == classe_id]
    return Eleve.query.filter(Eleve.actif.is_(True), Eleve.classe_id.in_(ids)) if ids else Eleve.query.filter(db.false())


def _veut_du_json():
    return request.headers.get("X-Requested-With") == "fetch"


@eleves_bp.route("/photos")
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def photos():
    """Photos d'une classe : une case par élève, à prendre ou à choisir
    depuis le téléphone, ou plusieurs fichiers d'un coup."""
    classes = filtrer_par_cycle(
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau, Classe.nom).all(),
        cycle_du_role(current_user.role),
    )
    classe_id = request.args.get("classe_id", type=int)
    classe = next((c for c in classes if c.id == classe_id), None)
    eleves = _eleves_des_photos(classe.id).order_by(Eleve.nom_complet).all() if classe else []
    return render_template(
        "eleves/photos.html", classes=classes, classe=classe, eleves=eleves,
        sans_photo=sum(1 for e in eleves if not e.photo_mime),
    )


@eleves_bp.route("/<int:eleve_id>/photo", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def enregistrer_photo(eleve_id):
    from app.services.images_ecole import photo_identite
    from app.services.journal import journaliser

    eleve = _eleves_des_photos().filter(Eleve.id == eleve_id).first_or_404()
    contenu, resultat = photo_identite(request.files.get("photo"))
    erreur = None if contenu else (resultat or "Aucune photo reçue.")
    if contenu:
        eleve.photo, eleve.photo_mime = contenu, resultat
        journaliser("photo_eleve", details=eleve.nom_complet, cible_type="Eleve", cible_id=eleve.id)
        db.session.commit()
    if _veut_du_json():
        return ({"ok": True, "eleve_id": eleve.id}, 200) if contenu else ({"ok": False, "message": erreur}, 400)
    flash(erreur or f"Photo de {eleve.nom_complet} enregistrée.", "error" if erreur else "info")
    return redirect(url_for("eleves.photos", classe_id=eleve.classe_id))


@eleves_bp.route("/photos/importer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def importer_photos():
    """Plusieurs photos d'un coup : chaque fichier porte le matricule de
    l'élève (ou son nom complet, s'il est unique dans l'école)."""
    import os
    from app.services.images_ecole import photo_identite
    from app.services.journal import journaliser

    classe_id = request.form.get("classe_id", type=int)
    eleves = _eleves_des_photos().all()
    par_matricule = {_cle_de_fichier(e.matricule): e for e in eleves}
    par_nom = {}
    for e in eleves:
        par_nom.setdefault(_cle_de_fichier(e.nom_complet), []).append(e)

    rangees, refusees = [], []
    for fichier in request.files.getlist("photos"):
        if not fichier or not fichier.filename:
            continue
        nom = os.path.basename(fichier.filename.replace("\\", "/"))
        cle = _cle_de_fichier(os.path.splitext(nom)[0])
        eleve = par_matricule.get(cle)
        if eleve is None:
            homonymes = par_nom.get(cle, [])
            if len(homonymes) > 1:
                refusees.append((nom, "plusieurs élèves portent ce nom : nomme le fichier avec le matricule"))
                continue
            eleve = homonymes[0] if homonymes else None
        if eleve is None:
            refusees.append((nom, "aucun élève avec ce matricule ou ce nom"))
            continue
        contenu, resultat = photo_identite(fichier)
        if not contenu:
            refusees.append((nom, (resultat or "fichier vide").replace("Photo refusée : ", "")))
            continue
        eleve.photo, eleve.photo_mime = contenu, resultat
        rangees.append((nom, eleve))
    if rangees:
        journaliser("import_photos_eleves", details=f"{len(rangees)} photo(s)")
        db.session.commit()

    if _veut_du_json():
        return {
            "rangees": [{"fichier": nom, "eleve_id": e.id, "eleve": e.nom_complet} for nom, e in rangees],
            "refusees": [{"fichier": nom, "raison": raison} for nom, raison in refusees],
        }
    if rangees:
        flash(f"{len(rangees)} photo(s) rangée(s) dans les dossiers.", "info")
    for nom, raison in refusees[:15]:
        flash(f"{nom} : {raison}.", "error")
    if not rangees and not refusees:
        flash("Aucun fichier reçu.", "error")
    return redirect(url_for("eleves.photos", classe_id=classe_id))


@eleves_bp.route("/<int:eleve_id>/modifier", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def modifier(eleve_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    if not classe_dans_le_cycle(eleve.classe, cycle_du_role(current_user.role)):
        abort(403)

    if request.method == "POST":
        nom_complet = request.form.get("nom_complet", "").strip()
        sexe = request.form.get("sexe")
        date_str = request.form.get("date_naissance", "")
        erreur = None
        date_naissance = None
        if date_str:
            try:
                date_naissance = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                erreur = "Date de naissance invalide."
        if not nom_complet:
            erreur = "Le nom est obligatoire."
        if not erreur:
            eleve.nom_complet = nom_complet[:120]
            eleve.sexe = sexe if sexe in ("M", "F") else None
            eleve.date_naissance = date_naissance
            eleve.telephone_parent = request.form.get("telephone_parent", "").strip()[:30] or None
            erreur = _appliquer_dossier(eleve)
        if erreur:
            db.session.rollback()
            flash(erreur, "error")
        else:
            eleve.actualiser_statut_dossier()
            if eleve.compte:
                eleve.compte.nom_complet = eleve.nom_complet
            from app.services.journal import journaliser
            journaliser("modification_eleve", details=eleve.nom_complet, cible_type="Eleve", cible_id=eleve.id)
            db.session.commit()
            flash("Dossier mis à jour.", "info")
            return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    return render_template("eleves/modifier.html", eleve=eleve)


@eleves_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def nouveau():
    # On n'inscrit un nouvel élève que dans une classe de l'année en
    # cours — les classes des années passées restent consultables mais
    # ne doivent jamais recevoir de nouvelle inscription.
    classes = filtrer_par_cycle(
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau).all(),
        cycle_du_role(current_user.role),
    )

    if request.method == "POST":
        nom_complet = request.form.get("nom_complet", "").strip()[:120]
        classe_id = request.form.get("classe_id", type=int)
        date_naissance_str = request.form.get("date_naissance", "")
        sexe = request.form.get("sexe")
        telephone_parent = request.form.get("telephone_parent", "").strip()

        if not nom_complet or not classe_id:
            flash("Le nom et la classe sont obligatoires.", "error")
            return render_template("eleves/nouveau.html", classes=classes)

        date_naissance = None
        if date_naissance_str:
            try:
                date_naissance = datetime.strptime(date_naissance_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Date de naissance invalide.", "error")
                return render_template("eleves/nouveau.html", classes=classes)
            if date_naissance >= maintenant().date() or date_naissance.year < 1950:
                flash("Date de naissance invalide.", "error")
                return render_template("eleves/nouveau.html", classes=classes)

        # Seulement une classe de l'année en cours et du cycle de la personne.
        classe = next((c for c in classes if c.id == classe_id), None)
        if classe is None:
            flash("Classe introuvable.", "error")
            return render_template("eleves/nouveau.html", classes=classes)
        from app.services.numeros import normaliser_numero_ecole
        telephone_parent = normaliser_numero_ecole(telephone_parent)
        eleve = Eleve(
            matricule=Eleve.generer_matricule(classe),
            nom_complet=nom_complet,
            classe_id=classe_id,
            date_naissance=date_naissance,
            sexe=sexe if sexe in ("M", "F") else None,
            telephone_parent=telephone_parent or None,
        )
        erreur_dossier = _appliquer_dossier(eleve)
        if erreur_dossier:
            flash(erreur_dossier, "error")
            return render_template("eleves/nouveau.html", classes=classes)
        db.session.add(eleve)
        db.session.flush()

        eleve.actualiser_statut_dossier()
        db.session.add(HistoriqueScolaire(
            eleve_id=eleve.id,
            classe_id=classe_id,
            annee_scolaire=Eleve.annee_scolaire_courante(),
            resultat="en_cours",
        ))
        db.session.commit()

        flash(
            f"Élève inscrit avec le matricule {eleve.matricule}. "
            f"L'élève peut créer son compte avec ce matricule et sa date de naissance.",
            "info",
        )
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    return render_template("eleves/nouveau.html", classes=classes)


@eleves_bp.route("/<int:eleve_id>")
@login_required
def detail(eleve_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    # Accès basé sur la relation, pas sur le rôle : n'importe quel compte
    # (personnel compris) peut être parent d'un élève. Le personnel de
    # gestion voit toujours tout ; les autres doivent être un parent lié.
    if not _peut_voir(eleve):
        abort(403)
    classe_superieure = Classe.query.filter_by(niveau=eleve.classe.niveau + 1, annee_scolaire=eleve.classe.annee_scolaire).first()
    parents_disponibles = (
        # Tout le personnel peut être parent (décision de la direction,
        # sept. 2026) — on ne filtre plus sur role="parent". Seul un
        # compte élève ne peut pas être le parent de lui-même.
        User.query.filter(User.statut == "actif", User.role != "eleve").order_by(User.nom_complet).all()
        if (current_user.role in ROLES_GESTION or current_user.role == "developpeur") else []
    )
    from app.services.permissions import role_a_acces
    annee = Eleve.annee_scolaire_courante()
    moyenne = moyenne_eleve(eleve, annee)
    classes_reintegration = (
        filtrer_par_cycle(Classe.query.filter_by(annee_scolaire=annee).order_by(Classe.niveau, Classe.nom).all(),
                          cycle_du_role(current_user.role))
        if not eleve.actif and role_a_acces(current_user.role, "eleves", ROLES_GESTION) else []
    )
    from app.models.livre import Pret
    livres_empruntes = Pret.query.filter_by(eleve_id=eleve.id, date_retour=None).all()
    return render_template(
        "eleves/detail.html", motifs_depart=MOTIFS_DEPART, livres_empruntes=livres_empruntes, classes_reintegration=classes_reintegration,
        aujourd_hui=maintenant().date(), eleve=eleve, classe_superieure=classe_superieure,
        parents_disponibles=parents_disponibles, statuts_dossier=STATUTS_DOSSIER,
        max_parents=MAX_PARENTS_PAR_ELEVE, moyenne=moyenne,
        reussite=a_reussi(eleve, annee), seuil=seuil_reussite_pour_classe(eleve.classe),
        contacts_whatsapp=contacts_whatsapp(eleve),
    )


@eleves_bp.route("/anciens")
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def anciens():
    """Élèves partis : radiés (transfert, abandon…) ou sortants en fin
    d'année. Leur dossier reste consultable et réintégrable."""
    from app.services.pagination import paginer

    terme = request.args.get("q", "").strip()
    requete = Eleve.query.filter_by(actif=False)
    if terme:
        motif = f"%{terme}%"
        requete = requete.filter(db.or_(Eleve.nom_complet.ilike(motif), Eleve.matricule.ilike(motif)))
    cycle = cycle_du_role(current_user.role)
    if cycle:
        requete = requete.filter(Eleve.classe_id.in_([c.id for c in filtrer_par_cycle(Classe.query.all(), cycle)]))
    page = paginer(requete.order_by(Eleve.date_depart.desc().nulls_last(), Eleve.nom_complet))
    return render_template("eleves/anciens.html", page=page, terme=terme)


@eleves_bp.route("/<int:eleve_id>/radier", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def radier(eleve_id):
    from app.services.suivi_eleve import date_du_formulaire
    from app.services.journal import journaliser

    eleve = db.get_or_404(Eleve, eleve_id)
    if not classe_dans_le_cycle(eleve.classe, cycle_du_role(current_user.role)):
        abort(403)
    motif = request.form.get("motif_depart", "")
    if not eleve.actif or motif not in LIBELLES_MOTIF_DEPART:
        flash("Choisis le motif du départ.", "error")
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))
    eleve.actif = False
    eleve.date_depart = date_du_formulaire("date_depart")
    eleve.motif_depart = motif
    eleve.details_depart = request.form.get("details_depart", "").strip()[:250] or None
    eleve.ecole_destination = request.form.get("ecole_destination", "").strip()[:150] or None
    journaliser("radiation_eleve", details=f"{eleve.nom_complet} — {LIBELLES_MOTIF_DEPART[motif]}",
                cible_type="Eleve", cible_id=eleve.id)
    db.session.commit()
    flash("Départ enregistré. Le dossier reste dans « Anciens élèves ».", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))


@eleves_bp.route("/<int:eleve_id>/reintegrer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def reintegrer(eleve_id):
    from app.services.journal import journaliser

    eleve = db.get_or_404(Eleve, eleve_id)
    cycle = cycle_du_role(current_user.role)
    if not classe_dans_le_cycle(eleve.classe, cycle):
        abort(403)
    annee = Eleve.annee_scolaire_courante()
    classe = db.session.get(Classe, request.form.get("classe_id", type=int) or 0)
    if eleve.actif or classe is None or classe.annee_scolaire != annee or not classe_dans_le_cycle(classe, cycle):
        flash("Choisis une classe de l'année en cours.", "error")
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))
    if classe.id != eleve.classe_id or not any(h.annee_scolaire == annee for h in eleve.historique):
        db.session.add(HistoriqueScolaire(eleve_id=eleve.id, classe_id=classe.id, annee_scolaire=annee, resultat="en_cours"))
    eleve.classe_id = classe.id
    eleve.actif = True
    eleve.date_depart = eleve.motif_depart = eleve.details_depart = eleve.ecole_destination = None
    journaliser("reintegration_eleve", details=f"{eleve.nom_complet} — {classe.nom}", cible_type="Eleve", cible_id=eleve.id)
    db.session.commit()
    flash("Élève réintégré.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))


@eleves_bp.route("/<int:eleve_id>/parent/ajouter", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def ajouter_parent(eleve_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    exiger_classe_du_cycle(eleve.classe)
    parent_id = request.form.get("parent_id", type=int)

    # Tout compte actif peut être lié comme parent (personnel compris),
    # sauf un compte élève (ne peut pas être son propre parent).
    parent = User.query.filter(User.id == parent_id, User.statut == "actif", User.role != "eleve").first()
    if not parent:
        flash("Compte introuvable ou pas encore actif.", "error")
    elif parent.id == current_user.id:
        flash("Tu ne peux pas te lier toi-même à un élève : un autre membre de la direction ou du secrétariat doit le faire.", "error")
    elif parent in eleve.parents:
        flash(f"{parent.nom_complet} est déjà lié à {eleve.nom_complet}.", "error")
    elif len(eleve.parents) >= MAX_PARENTS_PAR_ELEVE:
        flash(f"Un élève ne peut avoir plus de {MAX_PARENTS_PAR_ELEVE} parents liés. Retire d'abord un parent existant.", "error")
    else:
        eleve.parents.append(parent)
        # Le dossier se complète automatiquement avec les informations du
        # parent (téléphone) — pas de ressaisie (décision de la
        # direction, sept. 2026).
        if not eleve.telephone_parent and parent.telephone:
            eleve.telephone_parent = parent.telephone
        eleve.actualiser_statut_dossier()
        from app.services.journal import journaliser
        journaliser("liaison_parent", details=f"{parent.nom_complet} → {eleve.nom_complet}", cible_type="Eleve", cible_id=eleve.id)
        db.session.commit()
        flash(f"{parent.nom_complet} est maintenant lié à {eleve.nom_complet}.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))


@eleves_bp.route("/<int:eleve_id>/parent/<int:parent_id>/retirer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def retirer_parent(eleve_id, parent_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    exiger_classe_du_cycle(eleve.classe)
    parent = db.get_or_404(User, parent_id)
    if parent in eleve.parents:
        eleve.parents.remove(parent)
        eleve.actualiser_statut_dossier()
        from app.services.journal import journaliser
        journaliser("retrait_parent", details=f"{parent.nom_complet} ← {eleve.nom_complet}", cible_type="Eleve", cible_id=eleve.id)
        db.session.commit()
        flash(f"{parent.nom_complet} délié de {eleve.nom_complet}.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))


def _suffixe(nom):
    """« 6e A » → « A », « CM2 » → « » : ce qui distingue les classes d'un même niveau."""
    morceaux = (nom or "").split(maxsplit=1)
    return morceaux[1].strip().upper() if len(morceaux) > 1 else ""


def _classe_choisie(candidates, choix_id, origine):
    """La classe choisie si elle est parmi les candidates ; sinon celle qui
    porte le même suffixe que la classe d'origine ; sinon la première."""
    if not candidates:
        return None
    for c in candidates:
        if c.id == choix_id:
            return c
    meme_suffixe = [c for c in candidates if _suffixe(c.nom) == _suffixe(origine.nom) and (c.serie or None) == (origine.serie or None)]
    return (meme_suffixe or [c for c in candidates if _suffixe(c.nom) == _suffixe(origine.nom)] or candidates)[0]


DECISIONS_PASSAGE = {
    "admis": "Passe en classe supérieure", "redouble": "Redouble",
    "sortant": "Quitte l'école (fin de cycle)", "rester": "Ne pas déplacer",
}


@eleves_bp.route("/passage-de-classe", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def passage_en_masse():
    """Fin d'année : toute une classe passe dans les classes de l'année
    suivante. La décision de chaque élève est proposée d'après sa moyenne
    annuelle, et reste modifiable avant d'appliquer."""
    from app.services.bulletins import bulletins_de_la_classe

    cycle = cycle_du_role(current_user.role)
    toutes = filtrer_par_cycle(Classe.query.order_by(Classe.annee_scolaire.desc(), Classe.niveau, Classe.nom).all(), cycle)
    classe = next((c for c in toutes if c.id == request.values.get("classe_id", type=int)), None)
    if classe is None:
        from sqlalchemy import func
        effectifs = dict(
            db.session.query(Eleve.classe_id, func.count(Eleve.id)).filter(Eleve.actif.is_(True)).group_by(Eleve.classe_id).all()
        )
        avec_eleves = [c for c in toutes if effectifs.get(c.id)]
        return render_template("eleves/passage_en_masse.html", classe=None, classes=avec_eleves)

    annees_suivantes = sorted({c.annee_scolaire for c in toutes if c.annee_scolaire > classe.annee_scolaire})
    annee_cible = request.values.get("annee_cible") or (annees_suivantes[0] if annees_suivantes else None)
    if annee_cible not in annees_suivantes:
        annee_cible = None
    # Classes d'arrivée possibles ; la direction choisit (6e A → 5e A ou 5e B).
    candidates_sup = filtrer_par_cycle(
        Classe.query.filter_by(niveau=classe.niveau + 1, annee_scolaire=annee_cible).order_by(Classe.nom).all(), cycle,
    ) if annee_cible else []
    candidates_meme = Classe.query.filter_by(niveau=classe.niveau, annee_scolaire=annee_cible).order_by(Classe.nom).all() if annee_cible else []
    superieure = _classe_choisie(candidates_sup, request.values.get("dest_admis", type=int), classe)
    meme_niveau = _classe_choisie(candidates_meme, request.values.get("dest_redouble", type=int), classe)

    eleves = Eleve.query.filter_by(classe_id=classe.id, actif=True).order_by(Eleve.nom_complet).all()
    calcul = bulletins_de_la_classe(classe, "AN", classe.annee_scolaire)

    def proposition(eleve):
        bulletin = calcul["bulletins"].get(eleve.id)
        if bulletin is None:
            return "rester"
        if bulletin["moyenne"] < calcul["seuil"]:
            return "redouble"
        return "admis" if superieure else "sortant"

    if request.method == "POST" and annee_cible:
        bilan = {"admis": 0, "redouble": 0, "sortant": 0}
        for eleve in eleves:
            decision = request.form.get(f"decision_{eleve.id}", "rester")
            destination = {"admis": superieure, "redouble": meme_niveau}.get(decision)
            if decision not in bilan or (decision != "sortant" and destination is None):
                continue
            historique = (
                HistoriqueScolaire.query.filter_by(eleve_id=eleve.id, classe_id=classe.id)
                .order_by(HistoriqueScolaire.id.desc()).first()
            )
            if historique:
                historique.resultat = "echec" if decision == "redouble" else "admis"
            if decision == "sortant":
                eleve.actif = False
                eleve.date_depart = maintenant().date()
            else:
                eleve.classe_id = destination.id
                db.session.add(HistoriqueScolaire(
                    eleve_id=eleve.id, classe_id=destination.id, annee_scolaire=annee_cible, resultat="en_cours",
                ))
            bilan[decision] += 1
        from app.services.journal import journaliser
        journaliser("passage_en_masse", details=(
            f"{classe.nom} {classe.annee_scolaire} vers {annee_cible} : {bilan['admis']} admis, "
            f"{bilan['redouble']} redoublant(s), {bilan['sortant']} sortant(s)"
        ), cible_type="Classe", cible_id=classe.id)
        db.session.commit()
        flash(
            f"{classe.nom} : {bilan['admis']} élève(s) en classe supérieure, {bilan['redouble']} redoublant(s), "
            f"{bilan['sortant']} sortant(s).", "info",
        )
        return redirect(url_for("eleves.passage_en_masse"))

    return render_template(
        "eleves/passage_en_masse.html", classe=classe, eleves=eleves, calcul=calcul, annee_cible=annee_cible,
        annees_suivantes=annees_suivantes, superieure=superieure, meme_niveau=meme_niveau,
        candidates_sup=candidates_sup, candidates_meme=candidates_meme,
        propositions={e.id: proposition(e) for e in eleves}, decisions=DECISIONS_PASSAGE,
    )


@eleves_bp.route("/<int:eleve_id>/passage", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def passage(eleve_id):
    """Passage d'un seul élève vers la classe supérieure de l'année
    suivante (comme le passage en masse), d'après sa moyenne annuelle."""
    eleve = db.get_or_404(Eleve, eleve_id)
    classe_actuelle = exiger_classe_du_cycle(eleve.classe)
    annee = classe_actuelle.annee_scolaire

    suivantes = sorted({c.annee_scolaire for c in Classe.query.filter(Classe.annee_scolaire > annee).all()})
    if not suivantes:
        flash("L'année scolaire suivante n'existe pas encore : démarre-la depuis « Classes », puis reviens ici.", "error")
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))
    candidates = Classe.query.filter_by(niveau=classe_actuelle.niveau + 1, annee_scolaire=suivantes[0]).order_by(Classe.nom).all()
    classe_suivante = _classe_choisie(candidates, None, classe_actuelle)
    if not classe_suivante:
        flash("Aucune classe supérieure n'existe dans l'année suivante.", "error")
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    # Admission automatique selon la moyenne (document complémentaire,
    # sept. 2026) : Primaire >= 5/10, Collège >= 10/20.
    moyenne = moyenne_eleve(eleve, annee)
    reussite = a_reussi(eleve, annee)

    dernier_historique = (
        HistoriqueScolaire.query.filter_by(eleve_id=eleve.id, classe_id=classe_actuelle.id)
        .order_by(HistoriqueScolaire.id.desc())
        .first()
    )

    if reussite is None:
        flash(
            f"Impossible de déterminer l'admission automatiquement : aucune note "
            f"enregistrée pour {eleve.nom_complet} cette année. Saisis d'abord ses notes.",
            "error",
        )
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    if not reussite:
        if dernier_historique:
            dernier_historique.resultat = "echec"
        db.session.commit()
        flash(
            f"{eleve.nom_complet} n'atteint pas la moyenne requise ({moyenne} — "
            f"seuil {seuil_reussite_pour_classe(classe_actuelle)}) : utilise « Passage de classe » "
            f"pour l'inscrire comme redoublant dans l'année suivante.",
            "error",
        )
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    if dernier_historique:
        dernier_historique.resultat = "admis"

    eleve.classe_id = classe_suivante.id
    db.session.add(HistoriqueScolaire(
        eleve_id=eleve.id,
        classe_id=classe_suivante.id,
        annee_scolaire=suivantes[0],
        resultat="en_cours",
    ))
    db.session.commit()
    flash(f"Admission automatique validée (moyenne {moyenne}) — {eleve.nom_complet} passe en {classe_suivante.nom}.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))

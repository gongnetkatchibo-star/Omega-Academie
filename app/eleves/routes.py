from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.eleve import Eleve, STATUTS_DOSSIER, MAX_PARENTS_PAR_ELEVE
from app.services.moyennes import moyenne_eleve, a_reussi, seuil_reussite_pour_classe
from app.models.historique import HistoriqueScolaire
from app.models.user import User
from app.eleves import eleves_bp
from app.utils import roles_required, export_csv, export_xlsx, export_pdf_liste
from app.services.cycles import cycle_du_role, filtrer_par_cycle, classe_dans_le_cycle
from app.services.whatsapp import contacts as contacts_whatsapp

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
    classes = Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau).all()

    if request.method == "POST":
        nom_complet = request.form.get("nom_complet", "").strip()
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
                pass

        classe = db.session.get(Classe, classe_id)
        if classe is None:
            flash("Classe introuvable.", "error")
            return render_template("eleves/nouveau.html", classes=classes)
        eleve = Eleve(
            matricule=Eleve.generer_matricule(classe),
            nom_complet=nom_complet,
            classe_id=classe_id,
            date_naissance=date_naissance,
            sexe=sexe,
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
    annee = Eleve.annee_scolaire_courante()
    moyenne = moyenne_eleve(eleve, annee)
    return render_template(
        "eleves/detail.html", eleve=eleve, classe_superieure=classe_superieure,
        parents_disponibles=parents_disponibles, statuts_dossier=STATUTS_DOSSIER,
        max_parents=MAX_PARENTS_PAR_ELEVE, moyenne=moyenne,
        reussite=a_reussi(eleve, annee), seuil=seuil_reussite_pour_classe(eleve.classe),
        contacts_whatsapp=contacts_whatsapp(eleve),
    )


@eleves_bp.route("/<int:eleve_id>/parent/ajouter", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def ajouter_parent(eleve_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    parent_id = request.form.get("parent_id", type=int)

    # Tout compte actif peut être lié comme parent (personnel compris),
    # sauf un compte élève (ne peut pas être son propre parent).
    parent = User.query.filter(User.id == parent_id, User.statut == "actif", User.role != "eleve").first()
    if not parent:
        flash("Compte introuvable ou pas encore actif.", "error")
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
        db.session.commit()
        flash(f"{parent.nom_complet} est maintenant lié à {eleve.nom_complet}.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))


@eleves_bp.route("/<int:eleve_id>/parent/<int:parent_id>/retirer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def retirer_parent(eleve_id, parent_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    parent = db.get_or_404(User, parent_id)
    if parent in eleve.parents:
        eleve.parents.remove(parent)
        eleve.actualiser_statut_dossier()
        db.session.commit()
        flash(f"{parent.nom_complet} délié de {eleve.nom_complet}.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))


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
        avec_eleves = [c for c in toutes if Eleve.query.filter_by(classe_id=c.id, actif=True).count()]
        return render_template("eleves/passage_en_masse.html", classe=None, classes=avec_eleves)

    annees_suivantes = sorted({c.annee_scolaire for c in toutes if c.annee_scolaire > classe.annee_scolaire})
    annee_cible = request.values.get("annee_cible") or (annees_suivantes[0] if annees_suivantes else None)
    if annee_cible not in annees_suivantes:
        annee_cible = None
    superieure = Classe.query.filter_by(niveau=classe.niveau + 1, annee_scolaire=annee_cible).order_by(Classe.nom).first() if annee_cible else None
    meme_niveau = Classe.query.filter_by(niveau=classe.niveau, annee_scolaire=annee_cible).order_by(Classe.nom).first() if annee_cible else None

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
        propositions={e.id: proposition(e) for e in eleves}, decisions=DECISIONS_PASSAGE,
    )


@eleves_bp.route("/<int:eleve_id>/passage", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def passage(eleve_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    classe_actuelle = eleve.classe
    annee = Eleve.annee_scolaire_courante()

    classe_suivante = Classe.query.filter_by(niveau=classe_actuelle.niveau + 1, annee_scolaire=classe_actuelle.annee_scolaire).first()
    if not classe_suivante:
        flash("Aucune classe supérieure n'est encore définie après cette classe.", "error")
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    # Admission automatique selon la moyenne (document complémentaire,
    # sept. 2026) : Primaire >= 5/10, Collège >= 10/20. Le secrétariat ne
    # décide plus lui-même — le système calcule et applique le critère.
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
            f"seuil {seuil_reussite_pour_classe(classe_actuelle)}) : il/elle redouble "
            f"{classe_actuelle.nom}, pas de passage en classe supérieure.",
            "error",
        )
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    if dernier_historique:
        dernier_historique.resultat = "admis"

    eleve.classe_id = classe_suivante.id
    db.session.add(HistoriqueScolaire(
        eleve_id=eleve.id,
        classe_id=classe_suivante.id,
        annee_scolaire=annee,
        resultat="en_cours",
    ))
    db.session.commit()
    flash(f"Admission automatique validée (moyenne {moyenne}) — {eleve.nom_complet} passe en {classe_suivante.nom}.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))

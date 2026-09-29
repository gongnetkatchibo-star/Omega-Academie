"""Console de l'administrateur de la plateforme (rôle « developpeur ») :
créer, modifier, suspendre les établissements et entrer dans l'un d'eux."""

from functools import wraps

from flask import render_template, redirect, url_for, flash, request, session, abort, Response
from flask_login import login_required, current_user
from sqlalchemy import func, select

from app.extensions import db
from app.models.ecole import Ecole
from app.models.user import User
from app.models.eleve import Eleve
from app.models.journal import JournalAction
from app.plateforme import plateforme_bp
from app.services.images_ecole import lire_image_televersee

CHAMPS_TEXTE = ["nom", "sigle", "ville", "pays", "slogan", "prefixe_matricule"]


def super_admin_requis(f):
    @wraps(f)
    def enveloppe(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "developpeur":
            abort(403)
        return f(*args, **kwargs)
    return enveloppe


def _compter(modele, ecole_id):
    requete = select(func.count()).select_from(modele).where(modele.ecole_id == ecole_id)
    return db.session.execute(requete.execution_options(tous_etablissements=True)).scalar()


def _journaliser(ecole_id, action, details):
    db.session.add(JournalAction(
        ecole_id=ecole_id, utilisateur_id=current_user.id, action=action, details=details,
        cible_type="Ecole", cible_id=ecole_id,
    ))


def _appliquer_formulaire(ecole):
    """Recopie le formulaire dans l'école ; renvoie la liste des erreurs."""
    erreurs = []
    valeurs = {c: request.form.get(c, "").strip() for c in CHAMPS_TEXTE}
    if not valeurs["nom"]:
        erreurs.append("Le nom de l'établissement est obligatoire.")
    if not valeurs["sigle"]:
        erreurs.append("Le sigle est obligatoire (il apparaît dans la numérotation des documents).")
    prefixe = valeurs["prefixe_matricule"].upper()
    if not prefixe:
        erreurs.append("Le préfixe des matricules est obligatoire.")
    else:
        doublon = db.session.query(Ecole).filter(Ecole.prefixe_matricule == prefixe, Ecole.id != (ecole.id or 0)).first()
        if doublon:
            erreurs.append(f"Le préfixe {prefixe} est déjà utilisé par {doublon.nom}.")
    for champ in ("logo", "filigrane"):
        contenu, info = lire_image_televersee(request.files.get(champ))
        if contenu:
            setattr(ecole, champ, contenu)
            setattr(ecole, f"{champ}_mime", info)
        elif info:
            erreurs.append(f"{champ.capitalize()} : {info}")
    if not erreurs:
        for champ, valeur in valeurs.items():
            setattr(ecole, champ, prefixe if champ == "prefixe_matricule" else (valeur or None))
    return erreurs


@plateforme_bp.route("/")
@login_required
@super_admin_requis
def index():
    ecoles = db.session.query(Ecole).order_by(Ecole.nom).all()
    stats = {e.id: {"comptes": _compter(User, e.id), "eleves": _compter(Eleve, e.id)} for e in ecoles}
    return render_template("plateforme/index.html", ecoles=ecoles, stats=stats,
                           ecole_active_id=session.get("ecole_active"))


@plateforme_bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
@super_admin_requis
def nouvelle():
    if request.method == "POST":
        ecole = Ecole(actif=True)
        erreurs = _appliquer_formulaire(ecole)

        nom_fondateur = request.form.get("fondateur_nom", "").strip()
        email_fondateur = request.form.get("fondateur_email", "").strip().lower()
        genre_fondateur = request.form.get("fondateur_genre")
        mdp_fondateur = request.form.get("fondateur_mot_de_passe", "")
        if not nom_fondateur or not email_fondateur:
            erreurs.append("Nom et email du fondateur obligatoires.")
        if genre_fondateur not in ("M", "F"):
            erreurs.append("Genre du fondateur obligatoire.")
        if len(mdp_fondateur) < 8:
            erreurs.append("Le mot de passe provisoire du fondateur doit faire au moins 8 caractères.")
        existe = db.session.execute(
            select(User).where(User.email == email_fondateur).execution_options(tous_etablissements=True)
        ).first()
        if existe:
            erreurs.append("Un compte existe déjà avec cet email.")

        if erreurs:
            for e in erreurs:
                flash(e, "error")
            return render_template("plateforme/formulaire.html", etab=None, form=request.form)

        db.session.add(ecole)
        db.session.flush()
        fondateur = User(nom_complet=nom_fondateur, email=email_fondateur, genre=genre_fondateur,
                         role="fondateur", statut="actif", email_verifie=True, ecole_id=ecole.id)
        fondateur.set_mot_de_passe(mdp_fondateur)
        db.session.add(fondateur)
        _journaliser(ecole.id, "creation_etablissement", f"{ecole.nom} — fondateur {email_fondateur}")
        db.session.commit()
        flash(f"Établissement « {ecole.nom} » créé. Le fondateur peut se connecter avec {email_fondateur}.", "info")
        return redirect(url_for("plateforme.index"))

    return render_template("plateforme/formulaire.html", etab=None, form={})


@plateforme_bp.route("/<int:ecole_id>/modifier", methods=["GET", "POST"])
@login_required
@super_admin_requis
def modifier(ecole_id):
    ecole = db.session.get(Ecole, ecole_id) or abort(404)
    if request.method == "POST":
        erreurs = _appliquer_formulaire(ecole)
        if erreurs:
            db.session.rollback()
            for e in erreurs:
                flash(e, "error")
            return render_template("plateforme/formulaire.html", etab=ecole, form=request.form)
        _journaliser(ecole.id, "modification_etablissement", ecole.nom)
        db.session.commit()
        flash("Établissement mis à jour.", "info")
        return redirect(url_for("plateforme.index"))
    return render_template("plateforme/formulaire.html", etab=ecole, form={})


@plateforme_bp.route("/<int:ecole_id>/basculer", methods=["POST"])
@login_required
@super_admin_requis
def basculer(ecole_id):
    ecole = db.session.get(Ecole, ecole_id) or abort(404)
    ecole.actif = not ecole.actif
    _journaliser(ecole.id, "activation_etablissement" if ecole.actif else "suspension_etablissement", ecole.nom)
    db.session.commit()
    flash(f"« {ecole.nom} » {'réactivé' if ecole.actif else 'suspendu : ses utilisateurs ne peuvent plus se connecter'}.", "info")
    return redirect(url_for("plateforme.index"))


@plateforme_bp.route("/<int:ecole_id>/entrer", methods=["POST"])
@login_required
@super_admin_requis
def entrer(ecole_id):
    ecole = db.session.get(Ecole, ecole_id) or abort(404)
    session["ecole_active"] = ecole.id
    flash(f"Tu travailles maintenant dans « {ecole.nom} ».", "info")
    return redirect(url_for("main.index"))


@plateforme_bp.route("/<int:ecole_id>/<any(logo, filigrane):image>")
@login_required
@super_admin_requis
def image(ecole_id, image):
    ecole = db.session.get(Ecole, ecole_id) or abort(404)
    contenu = getattr(ecole, image)
    if not contenu:
        abort(404)
    return Response(contenu, mimetype=getattr(ecole, f"{image}_mime") or "image/png")

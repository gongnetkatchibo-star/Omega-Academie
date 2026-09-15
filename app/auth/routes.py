from flask import render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_mail import Message

from app.extensions import db, mail
from app.models.user import User
from app.auth import auth_bp

# Profils autorisés à s'inscrire eux-mêmes (en attente de validation).
# Les rôles à responsabilité (secrétaire, directeur, comptable,
# administrateur général...) ne sont JAMAIS choisis par la personne
# elle-même : elle s'inscrit en "personnel" générique, en attente, et
# seul l'espace développeur peut ensuite lui attribuer le rôle précis.
ROLES_INSCRIPTION = ["parent", "enseignant", "personnel"]

DUREE_VALIDITE_TOKEN = 1800  # 30 minutes


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generer_token_reset(user):
    return _serializer().dumps(user.email, salt="reset-mot-de-passe")


def email_depuis_token(token, max_age=DUREE_VALIDITE_TOKEN):
    try:
        return _serializer().loads(token, salt="reset-mot-de-passe", max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def _envoyer_email_reset(user, lien_reset):
    """Envoie l'email si un serveur SMTP est configuré (MAIL_SERVER dans
    .env). Retourne True si l'envoi a réussi, False sinon (pas configuré,
    ou erreur réseau/identifiants)."""
    if not current_app.config.get("MAIL_SERVER"):
        return False
    try:
        msg = Message(
            subject="Réinitialisation de votre mot de passe — Omega Académie",
            recipients=[user.email],
            body=(
                f"Bonjour {user.nom_complet},\n\n"
                f"Voici le lien pour choisir un nouveau mot de passe "
                f"(valable 30 minutes) :\n{lien_reset}\n\n"
                f"Si tu n'es pas à l'origine de cette demande, ignore ce message."
            ),
        )
        mail.send(msg)
        return True
    except Exception:
        current_app.logger.exception("Échec de l'envoi de l'email de réinitialisation.")
        return False


def _envoyer_email_reset_multi(destinataires, user, lien_reset):
    """Comme _envoyer_email_reset, mais pour un ou plusieurs destinataires
    (cas du compte élève : le lien part chez le ou les parents liés, pas
    sur l'email généré automatiquement à l'inscription)."""
    if not current_app.config.get("MAIL_SERVER"):
        return False
    try:
        msg = Message(
            subject="Réinitialisation de mot de passe — Omega Académie",
            recipients=destinataires,
            body=(
                f"Bonjour,\n\n"
                f"Une demande de réinitialisation de mot de passe a été faite pour "
                f"le compte de {user.nom_complet}.\n\n"
                f"Voici le lien pour choisir un nouveau mot de passe "
                f"(valable 30 minutes) :\n{lien_reset}\n\n"
                f"Si tu n'es pas à l'origine de cette demande, ignore ce message."
            ),
        )
        mail.send(msg)
        return True
    except Exception:
        current_app.logger.exception("Échec de l'envoi de l'email de réinitialisation.")
        return False


def _envoyer_code_verification(user, code):
    """Code envoyé une seule fois, à l'inscription, pour vérifier que
    l'email fourni est valide et accessible — plus de code demandé
    ensuite à chaque connexion (décision de la direction, sept. 2026)."""
    if not current_app.config.get("MAIL_SERVER"):
        return False
    try:
        msg = Message(
            subject="Vérifie ton email — Omega Académie",
            recipients=[user.email],
            body=(
                f"Bonjour {user.nom_complet},\n\n"
                f"Voici ton code de vérification d'inscription "
                f"(valable 10 minutes) : {code}\n\n"
                f"Une fois vérifié, ta demande de compte sera transmise "
                f"au secrétariat pour validation."
            ),
        )
        mail.send(msg)
        return True
    except Exception:
        current_app.logger.exception("Échec de l'envoi du code de vérification d'inscription.")
        return False


@auth_bp.route("/inscription", methods=["GET", "POST"])
def inscription():
    if request.method == "POST":
        role = request.form.get("role")
        email = request.form.get("email", "").strip().lower()
        telephone = request.form.get("telephone", "").strip()
        mot_de_passe = request.form.get("mot_de_passe", "")
        confirmation = request.form.get("confirmation", "")

        erreurs = []

        if role == "parent":
            # Champs obligatoires spécifiques aux comptes parents (exigence
            # de la direction, sept. 2026) : prénom/nom séparés, téléphone,
            # profession — en plus de l'email et du mot de passe.
            prenom = request.form.get("prenom", "").strip()
            nom = request.form.get("nom", "").strip()
            profession = request.form.get("profession", "").strip()
            nom_complet = f"{prenom} {nom}".strip()

            if not all([prenom, nom, telephone, profession]):
                erreurs.append("Pour un compte parent, le prénom, le nom, le téléphone et la profession sont obligatoires.")
        else:
            prenom = nom = profession = None
            nom_complet = request.form.get("nom_complet", "").strip()

        if not all([nom_complet, email, role, mot_de_passe]):
            erreurs.append("Merci de remplir tous les champs obligatoires.")
        if mot_de_passe and mot_de_passe != confirmation:
            erreurs.append("Les mots de passe ne correspondent pas.")
        if role not in ROLES_INSCRIPTION:
            erreurs.append("Profil invalide.")
        if email and User.query.filter_by(email=email).first():
            erreurs.append("Un compte existe déjà avec cet email.")
        if telephone and User.query.filter_by(telephone=telephone).first():
            erreurs.append("Un compte existe déjà avec ce numéro de téléphone.")

        if erreurs:
            for e in erreurs:
                flash(e, "error")
            return render_template("auth/inscription.html", roles=ROLES_INSCRIPTION)

        user = User(
            nom_complet=nom_complet,
            prenom=prenom,
            nom=nom,
            profession=profession,
            email=email,
            telephone=telephone or None,
            role=role,
            statut="en_attente",
        )
        user.set_mot_de_passe(mot_de_passe)
        db.session.add(user)
        db.session.commit()

        # Vérification de l'email une seule fois, ici, à l'inscription —
        # plus jamais redemandée ensuite à la connexion.
        code = user.generer_code_2fa()
        db.session.commit()
        envoye = _envoyer_code_verification(user, code)
        session["id_en_attente_verification"] = user.id
        if not envoye:
            flash(f"Aucun service d'email configuré — code de vérification : {code}", "info")
        return redirect(url_for("auth.verification_email"))

    return render_template("auth/inscription.html", roles=ROLES_INSCRIPTION)


@auth_bp.route("/connexion", methods=["GET", "POST"])
def connexion():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        mot_de_passe = request.form.get("mot_de_passe", "")
        user = User.query.filter_by(email=email).first()

        if user is None or not user.verifier_mot_de_passe(mot_de_passe):
            flash("Email ou mot de passe incorrect.", "error")
            return render_template("auth/connexion.html")

        if user.statut == "en_attente":
            flash("Votre compte est en attente de validation par le secrétariat.", "warning")
            return render_template("auth/connexion.html")

        if user.statut == "refuse":
            flash("Votre demande de compte a été refusée. Contactez l'école.", "error")
            return render_template("auth/connexion.html")

        login_user(user)
        flash(f"Bienvenue, {user.nom_complet}.", "info")
        return redirect(url_for("main.index"))

    return render_template("auth/connexion.html")


@auth_bp.route("/verification-inscription", methods=["GET", "POST"])
def verification_email(): 
    user_id = session.get("id_en_attente_verification")
    if not user_id:
        return redirect(url_for("auth.inscription"))

    user = User.query.get(user_id)
    if not user:
        session.pop("id_en_attente_verification", None)
        return redirect(url_for("auth.inscription"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()

        if not user.verifier_code_2fa(code):
            flash("Code invalide ou expiré. Demande-en un nouveau si besoin.", "error")
            return render_template("auth/verification_email.html", email=user.email)

        user.invalider_code_2fa()
        user.email_verifie = True
        db.session.commit()
        session.pop("id_en_attente_verification", None)
        flash("Email vérifié. Ta demande de compte est transmise au secrétariat pour validation.", "info")
        return redirect(url_for("auth.connexion"))

    return render_template("auth/verification_email.html", email=user.email)


@auth_bp.route("/verification-inscription/renvoyer", methods=["POST"])
def renvoyer_code_verification():
    user_id = session.get("id_en_attente_verification")
    user = User.query.get(user_id) if user_id else None
    if not user:
        return redirect(url_for("auth.inscription"))

    code = user.generer_code_2fa()
    db.session.commit()
    envoye = _envoyer_code_verification(user, code)
    if envoye:
        flash(f"Nouveau code envoyé à {user.email}.", "info")
    else:
        flash(f"Aucun service d'email configuré — code de vérification : {code}", "info")
    return redirect(url_for("auth.verification_email"))


@auth_bp.route("/deconnexion")
@login_required
def deconnexion():
    logout_user()
    return redirect(url_for("auth.connexion"))


def _destinataires_reset(user):
    """Pour un compte élève, l'email est généré automatiquement à
    l'inscription et n'est jamais consulté par personne — le lien de
    réinitialisation doit donc partir chez le(s) parent(s) lié(s), pas
    sur cette adresse injoignable."""
    if user.role == "eleve":
        from app.models.eleve import Eleve
        eleve = Eleve.query.filter_by(user_id=user.id).first()
        if eleve and eleve.parents:
            return [p.email for p in eleve.parents]
        return []
    return [user.email]


@auth_bp.route("/mot-de-passe-oublie", methods=["GET", "POST"])
def mot_de_passe_oublie():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    lien_reset = None
    email_envoye = False

    if request.method == "POST":
        identifiant = request.form.get("email", "").strip()
        user = User.query.filter_by(email=identifiant.lower()).first()
        if not user:
            # Un élève ne connaît généralement pas son email généré
            # automatiquement — il peut saisir son matricule à la place.
            from app.models.eleve import Eleve
            eleve = Eleve.query.filter_by(matricule=identifiant.upper()).first()
            if eleve and eleve.compte:
                user = eleve.compte

        if user is not None:
            destinataires = _destinataires_reset(user)
            token = generer_token_reset(user)
            lien = url_for("auth.reinitialiser", token=token, _external=True)

            if not destinataires:
                # Compte élève sans parent lié : personne à qui l'envoyer.
                # On affiche quand même le lien (utile si c'est le
                # secrétariat qui agit pour l'élève), sans jamais révéler
                # que c'est ce cas précis qui s'est produit (voir message
                # neutre plus bas).
                lien_reset = lien
                current_app.logger.info("Lien de réinitialisation (aucun parent lié) pour %s : %s", user.email, lien)
            else:
                email_envoye = _envoyer_email_reset_multi(destinataires, user, lien)
                if not email_envoye:
                    lien_reset = lien
                    current_app.logger.info("Lien de réinitialisation pour %s : %s", user.email, lien)

        # Message volontairement identique que le compte existe ou non,
        # et quelle qu'en soit la raison — ne jamais laisser deviner si un
        # email/matricule est enregistré dans la base.
        if email_envoye:
            flash("Un email de réinitialisation vient de t'être envoyé.", "info")
        elif not lien_reset:
            flash(
                "Si un compte existe, un lien de réinitialisation vient d'être généré.", "info",
            )

    return render_template("auth/mot_de_passe_oublie.html", lien_reset=lien_reset)


@auth_bp.route("/reinitialiser/<token>", methods=["GET", "POST"])
def reinitialiser(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    email = email_depuis_token(token)
    if email is None:
        flash("Ce lien de réinitialisation est invalide ou a expiré.", "error")
        return redirect(url_for("auth.mot_de_passe_oublie"))

    user = User.query.filter_by(email=email).first()
    if user is None:
        flash("Ce lien de réinitialisation est invalide ou a expiré.", "error")
        return redirect(url_for("auth.mot_de_passe_oublie"))

    if request.method == "POST":
        mot_de_passe = request.form.get("mot_de_passe", "")
        confirmation = request.form.get("confirmation", "")

        if not mot_de_passe or mot_de_passe != confirmation:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template("auth/reinitialiser.html", token=token)

        user.set_mot_de_passe(mot_de_passe)
        db.session.commit()
        flash("Mot de passe réinitialisé. Tu peux te connecter.", "info")
        return redirect(url_for("auth.connexion"))

    return render_template("auth/reinitialiser.html", token=token)

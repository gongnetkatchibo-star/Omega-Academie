from flask import render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.extensions import db, envoyer_email
from app import limiter
from app.models.user import User
from app.auth import auth_bp
from app.services.temps import maintenant

# Profils autorisés à s'inscrire eux-mêmes (en attente de validation).
# Les rôles à responsabilité (secrétaire, directeur, comptable,
# administrateur général...) ne sont JAMAIS choisis par la personne
# elle-même : elle s'inscrit en "personnel" générique, en attente, et
# seul l'espace développeur peut ensuite lui attribuer le rôle précis.
def _comptes():
    """Recherche de comptes sur toute la plateforme : l'email est unique
    tous établissements confondus, et l'école n'est connue qu'après
    identification."""
    return User.query.execution_options(tous_etablissements=True)


def _ecoles_ouvertes():
    from app.models.ecole import Ecole
    return Ecole.query.filter_by(actif=True).order_by(Ecole.nom).all()


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


def _nom_ecole(user):
    from flask import current_app
    return user.ecole.nom if user.ecole else current_app.config.get("PLATEFORME_NOM")


def _envoyer_email_reset(user, lien_reset):
    """Envoie l'email via Brevo si une clé API est configurée. Retourne
    True si l'envoi a réussi, False sinon (pas configuré, ou erreur)."""
    corps = (
        f"Bonjour {user.nom_complet},\n\n"
        f"Voici le lien pour choisir un nouveau mot de passe "
        f"(valable 30 minutes) :\n{lien_reset}\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez simplement ce message."
    )
    return envoyer_email([user.email], f"Réinitialisation de votre mot de passe — {_nom_ecole(user)}", corps, nom_expediteur=_nom_ecole(user))


def _envoyer_email_reset_multi(destinataires, user, lien_reset):
    """Comme _envoyer_email_reset, mais pour un ou plusieurs destinataires
    (cas du compte élève : le lien part chez le ou les parents liés, pas
    sur l'email généré automatiquement à l'inscription)."""
    corps = (
        f"Bonjour,\n\n"
        f"Une demande de réinitialisation de mot de passe a été faite pour "
        f"le compte de {user.nom_complet}.\n\n"
        f"Voici le lien pour choisir un nouveau mot de passe "
        f"(valable 30 minutes) :\n{lien_reset}\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez simplement ce message."
    )
    return envoyer_email(destinataires, f"Réinitialisation de mot de passe — {_nom_ecole(user)}", corps, nom_expediteur=_nom_ecole(user))


def _envoyer_code_verification(user, code):
    """Code envoyé une seule fois, à l'inscription, pour vérifier que
    l'email fourni est valide et accessible — plus de code demandé
    ensuite à chaque connexion (décision de la direction, sept. 2026)."""
    corps = (
        f"Bonjour {user.nom_complet},\n\n"
        f"Voici votre code de vérification d'inscription "
        f"(valable 10 minutes) : {code}\n\n"
        f"Une fois votre email vérifié, votre demande de compte sera transmise "
        f"au secrétariat pour validation."
    )
    return envoyer_email([user.email], f"Vérifiez votre email — {_nom_ecole(user)}", corps, nom_expediteur=_nom_ecole(user))


DOMAINE_EMAIL_TECHNIQUE_ELEVE = ("@eleves.local", "@eleves.omega-academie.local")


def _email_technique(email):
    return email.endswith(DOMAINE_EMAIL_TECHNIQUE_ELEVE)


def _eleve_par_matricule(matricule, ecole_id=None):
    from sqlalchemy import select
    from app.models.eleve import Eleve

    requete = select(Eleve).where(Eleve.matricule == matricule.strip().upper())
    if ecole_id is not None:
        requete = requete.where(Eleve.ecole_id == ecole_id)
    return db.session.execute(requete.execution_options(tous_etablissements=True)).scalar_one_or_none()


def _inscription_eleve():
    """L'élève crée lui-même son compte : son matricule et sa date de
    naissance doivent correspondre à son dossier. Si le dossier n'a pas
    de date de naissance, le compte attend la validation du secrétariat."""
    from datetime import datetime

    ecoles = _ecoles_ouvertes()
    ecole_id = request.form.get("ecole_id", type=int)
    matricule = request.form.get("matricule", "").strip().upper()
    date_saisie = request.form.get("date_naissance_eleve", "")
    email = request.form.get("email", "").strip().lower()
    telephone = request.form.get("telephone", "").strip()
    mot_de_passe = request.form.get("mot_de_passe", "")
    confirmation = request.form.get("confirmation", "")

    def refuser(message):
        flash(message, "error")
        return render_template("auth/inscription.html", roles=ROLES_INSCRIPTION, ecoles=ecoles)

    if ecole_id not in {e.id for e in ecoles}:
        return refuser("Merci de choisir ton établissement.")
    if not matricule or not date_saisie or not mot_de_passe:
        return refuser("Le matricule, la date de naissance et le mot de passe sont obligatoires.")
    if len(mot_de_passe) < 8:
        return refuser("Le mot de passe doit faire au moins 8 caractères.")
    if mot_de_passe != confirmation:
        return refuser("Les mots de passe ne correspondent pas.")
    try:
        date_naissance = datetime.strptime(date_saisie, "%Y-%m-%d").date()
    except ValueError:
        return refuser("Date de naissance invalide.")

    eleve = _eleve_par_matricule(matricule, ecole_id)
    if eleve is None or not eleve.actif or (eleve.date_naissance and eleve.date_naissance != date_naissance):
        return refuser("Matricule ou date de naissance incorrect.")
    if eleve.user_id:
        return refuser("Un compte existe déjà pour ce matricule. Utilise « Mot de passe oublié » si besoin.")
    if email and _comptes().filter_by(email=email).first():
        return refuser("Un compte existe déjà avec cet email.")
    if telephone and _comptes().filter_by(telephone=telephone).first():
        return refuser("Un compte existe déjà avec ce numéro de téléphone.")

    statut = "actif" if eleve.date_naissance else "en_attente"
    compte = User(
        ecole_id=eleve.ecole_id, nom_complet=eleve.nom_complet, genre=eleve.sexe,
        email=email or f"{matricule.lower()}@eleves.local", telephone=telephone or None,
        role="eleve", statut=statut, email_verifie=not email,
    )
    compte.set_mot_de_passe(mot_de_passe)
    db.session.add(compte)
    db.session.flush()
    eleve.user_id = compte.id
    db.session.commit()

    if statut == "actif":
        flash(f"Compte créé. Connecte-toi avec ton matricule {matricule}.", "info")
    else:
        flash("Compte créé. Il sera activé après vérification de ton dossier par le secrétariat.", "info")
    return redirect(url_for("auth.connexion"))


@auth_bp.route("/inscription", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def inscription():
    if request.method == "POST":
        role = request.form.get("role")
        if role == "eleve":
            return _inscription_eleve()
        email = request.form.get("email", "").strip().lower()
        telephone = request.form.get("telephone", "").strip()
        genre = request.form.get("genre")
        ecole_id = request.form.get("ecole_id", type=int)
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
        if email and _comptes().filter_by(email=email).first():
            erreurs.append("Un compte existe déjà avec cet email.")
        if telephone and _comptes().filter_by(telephone=telephone).first():
            erreurs.append("Un compte existe déjà avec ce numéro de téléphone.")

        if genre not in ("M", "F"):
            erreurs.append("Merci d'indiquer le genre.")
        if ecole_id not in {e.id for e in _ecoles_ouvertes()}:
            erreurs.append("Merci de choisir ton établissement.")

        if erreurs:
            for e in erreurs:
                flash(e, "error")
            return render_template("auth/inscription.html", roles=ROLES_INSCRIPTION, ecoles=_ecoles_ouvertes())

        user = User(
            ecole_id=ecole_id,
            genre=genre,
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

    return render_template("auth/inscription.html", roles=ROLES_INSCRIPTION, ecoles=_ecoles_ouvertes())


@auth_bp.route("/connexion", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def connexion():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        identifiant = request.form.get("email", "").strip()
        mot_de_passe = request.form.get("mot_de_passe", "")
        if "@" in identifiant:
            user = _comptes().filter_by(email=identifiant.lower()).first()
        else:
            eleve = _eleve_par_matricule(identifiant) if identifiant else None
            user = eleve.compte if eleve else None

        from datetime import timedelta
        instant = maintenant()
        if user is not None and user.bloque_jusqua and user.bloque_jusqua > instant:
            minutes = int((user.bloque_jusqua - instant).total_seconds() // 60) + 1
            flash(f"Trop de tentatives : ce compte est bloqué encore {minutes} minute(s).", "error")
            return render_template("auth/connexion.html")

        if user is None or not user.verifier_mot_de_passe(mot_de_passe):
            if user is not None:
                user.echecs_connexion = (user.echecs_connexion or 0) + 1
                if user.echecs_connexion >= current_app.config["ECHECS_CONNEXION_MAX"]:
                    user.bloque_jusqua = instant + timedelta(minutes=current_app.config["BLOCAGE_MINUTES"])
                    user.echecs_connexion = 0
                    from app.models.journal import JournalAction
                    db.session.add(JournalAction(
                        ecole_id=user.ecole_id, action="compte_bloque", cible_type="User", cible_id=user.id,
                        details=f"{user.email} — mots de passe faux répétés",
                    ))
                db.session.commit()
            flash("Identifiant ou mot de passe incorrect.", "error")
            return render_template("auth/connexion.html")

        if user.echecs_connexion or user.bloque_jusqua:
            user.echecs_connexion, user.bloque_jusqua = 0, None
            db.session.commit()

        if user.statut == "en_attente":
            flash("Votre compte est en attente de validation par le secrétariat.", "warning")
            return render_template("auth/connexion.html")

        if user.statut == "refuse":
            flash("Votre demande de compte a été refusée. Contactez l'école.", "error")
            return render_template("auth/connexion.html")

        if user.statut == "verrouille":
            flash("Ce compte a été verrouillé. Contacte le développeur ou la direction pour le débloquer.", "error")
            return render_template("auth/connexion.html")

        login_user(user)
        session.permanent = True  # déconnexion automatique après inactivité
        flash(f"Bienvenue, {user.nom_complet}.", "info")

        # Retour direct à la page demandée avant la connexion (ex. le
        # lien « Voir plus » d'un email d'annonce). On n'accepte qu'un
        # chemin interne, jamais une adresse externe, pour ne pas servir
        # de rebond vers un autre site (sept. 2026).
        destination = request.args.get("next") or request.form.get("next")
        if destination and destination.startswith("/") and not destination.startswith("//"):
            return redirect(destination)
        return redirect(url_for("main.index"))

    return render_template("auth/connexion.html")


@auth_bp.route("/verification-inscription", methods=["GET", "POST"])
def verification_email(): 
    user_id = session.get("id_en_attente_verification")
    if not user_id:
        return redirect(url_for("auth.inscription"))

    user = _comptes().get(user_id)
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
    user = _comptes().get(user_id) if user_id else None
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
        destinataires = [p.email for p in eleve.parents] if eleve else []
        if not _email_technique(user.email):
            destinataires.append(user.email)
        return destinataires
    return [user.email]


@auth_bp.route("/mot-de-passe-oublie", methods=["GET", "POST"])
def mot_de_passe_oublie():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    lien_reset = None
    email_envoye = False

    if request.method == "POST":
        identifiant = request.form.get("email", "").strip()
        user = _comptes().filter_by(email=identifiant.lower()).first()
        if not user:
            # Un élève ne connaît généralement pas son email généré
            # automatiquement — il peut saisir son matricule à la place.
            eleve = _eleve_par_matricule(identifiant) if identifiant else None
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

    user = _comptes().filter_by(email=email).first()
    if user is None:
        flash("Ce lien de réinitialisation est invalide ou a expiré.", "error")
        return redirect(url_for("auth.mot_de_passe_oublie"))

    if request.method == "POST":
        mot_de_passe = request.form.get("mot_de_passe", "")
        confirmation = request.form.get("confirmation", "")

        if not mot_de_passe or mot_de_passe != confirmation:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template("auth/reinitialiser.html", token=token)
        if len(mot_de_passe) < 8:
            flash("Le mot de passe doit faire au moins 8 caractères.", "error")
            return render_template("auth/reinitialiser.html", token=token)

        user.set_mot_de_passe(mot_de_passe)
        user.echecs_connexion, user.bloque_jusqua = 0, None
        db.session.commit()
        flash("Mot de passe réinitialisé. Tu peux te connecter.", "info")
        return redirect(url_for("auth.connexion"))

    return render_template("auth/reinitialiser.html", token=token)


@auth_bp.route("/premiere-configuration", methods=["GET", "POST"])
def premiere_configuration():
    """Créer le tout premier compte (développeur) directement depuis le
    web — sans terminal ni Shell, indisponible sur le plan gratuit Render
    (sept. 2026). Se désactive automatiquement dès qu'un compte existe
    déjà dans la base, pour ne jamais pouvoir être réutilisée après coup."""
    if _comptes().count() > 0:
        flash("La configuration initiale a déjà été faite — connecte-toi normalement.", "error")
        return redirect(url_for("auth.connexion"))

    if request.method == "POST":
        nom_complet = request.form.get("nom_complet", "").strip()
        email = request.form.get("email", "").strip().lower()
        mot_de_passe = request.form.get("mot_de_passe", "")
        confirmation = request.form.get("confirmation", "")

        if not all([nom_complet, email, mot_de_passe]):
            flash("Merci de remplir tous les champs.", "error")
            return render_template("auth/premiere_configuration.html")
        if mot_de_passe != confirmation:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template("auth/premiere_configuration.html")

        # Re-vérifié juste avant l'écriture, au cas où deux personnes
        # tenteraient la configuration en même temps.
        if _comptes().count() > 0:
            flash("La configuration initiale a déjà été faite — connecte-toi normalement.", "error")
            return redirect(url_for("auth.connexion"))

        user = User(nom_complet=nom_complet, email=email, role="developpeur", statut="actif", email_verifie=True)
        user.set_mot_de_passe(mot_de_passe)
        db.session.add(user)
        db.session.commit()

        flash("Compte développeur créé. Tu peux te connecter.", "info")
        return redirect(url_for("auth.connexion"))

    return render_template("auth/premiere_configuration.html")

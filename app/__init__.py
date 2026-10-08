import os
import click
from flask import Flask, render_template, redirect, url_for, flash, request
from markupsafe import Markup, escape
from flask_login import current_user
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import config
from app.extensions import db, migrate, login_manager, mail

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "default")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config[config_name])

    os.makedirs(app.instance_path, exist_ok=True)

    # Suivi d'erreurs Sentry — actif uniquement si un DSN est configuré
    # (variable d'environnement SENTRY_DSN). Sans lui, l'application
    # fonctionne exactement comme avant, silencieusement (sept. 2026).
    if app.config.get("SENTRY_DSN"):
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=app.config["SENTRY_DSN"],
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.2,
            environment=config_name,
            send_default_pii=False,  # jamais de données personnelles des utilisateurs envoyées à Sentry
        )

    if config_name == "production" and not os.environ.get("SECRET_KEY"):
        # Sans clé secrète, n'importe qui pourrait fabriquer une session.
        # On en tire une au hasard plutôt que de démarrer avec une valeur
        # connue : les sessions sont simplement perdues à chaque redémarrage.
        import secrets
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning("SECRET_KEY absente : clé temporaire générée. Définis SECRET_KEY sur le serveur.")

    if app.config.get("PROXY_COUCHES"):
        # Derrière nginx : retrouver la vraie adresse du visiteur et le
        # fait que la connexion est en https (limite de tentatives par
        # personne, liens https dans les emails, cookie sécurisé).
        from werkzeug.middleware.proxy_fix import ProxyFix
        couches = app.config["PROXY_COUCHES"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=couches, x_proto=couches, x_host=couches)

    db.init_app(app)
    from app.services.tenant import installer_isolement
    installer_isolement(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    @app.errorhandler(403)
    def erreur_403(e):
        db.session.rollback()
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def erreur_404(e):
        db.session.rollback()
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def erreur_413(e):
        db.session.rollback()
        return render_template("errors/413.html"), 413

    @app.errorhandler(429)
    def erreur_429(e):
        db.session.rollback()
        return render_template("errors/429.html"), 429

    @app.after_request
    def ajouter_en_tetes_securite(reponse):
        """En-têtes de sécurité HTTP de base (sept. 2026). Le CSP autorise
        le JS/CSS en ligne ('unsafe-inline') car l'application en utilise
        largement (boutons afficher/masquer, calculs de billets...) —
        un CSP strict casserait ces fonctionnalités. Il bloque quand même
        l'exécution de scripts venant d'ailleurs que le site lui-même,
        et interdit tout affichage du site dans une frame externe
        (protection anti-clickjacking, plus stricte qu'un simple
        en-tête X-Frame-Options)."""
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["X-Frame-Options"] = "DENY"
        reponse.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        reponse.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none';"
        )
        if request.is_secure:
            reponse.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return reponse

    @app.errorhandler(500)
    def erreur_500(e):
        # Sans ce rollback, si l'erreur d'origine vient d'une requête SQL
        # ratée, la session reste "sale" — rendre errors/500.html
        # (qui interroge la base via base.html) échoue à son tour, et
        # Flask abandonne en affichant son message générique brut au lieu
        # de notre page (constaté sept. 2026).
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.template_global()
    def version_fichier_statique(chemin_relatif):
        """Ajoute un paramètre basé sur la date de modification du
        fichier (ex. ?v=1758...) pour forcer le navigateur à retélécharger
        le CSS/JS après un déploiement, au lieu de garder une version en
        cache qui ne change jamais visuellement (constaté sept. 2026)."""
        import os
        chemin_complet = os.path.join(app.static_folder, chemin_relatif)
        try:
            return int(os.path.getmtime(chemin_complet))
        except OSError:
            return 0

    # Clé de module → dessin du fichier templates/_icones.html. Des icônes
    # dessinées plutôt que des emojis, qui changeaient d'aspect d'un
    # téléphone à l'autre (oct. 2026).
    ICONES_MODULES = {
        "classes": "ecole", "eleves": "eleves", "tests_niveau": "crayon", "enseignants": "personne",
        "suivi_cours": "livre", "finances": "portefeuille", "caisse": "recu", "salaires": "billets",
        "statistiques": "graphique", "alertes": "alerte", "messagerie": "message", "bibliotheque": "bibliotheque",
        "annonces": "annonce", "communication": "annonce", "assistant": "etincelle", "demandes": "boite",
        "secretariat": "boite", "tableau_de_bord": "accueil", "profil": "personne", "deconnexion": "sortie",
        "dev": "outil", "emploi_du_temps": "calendrier", "notes": "liste", "etablissement": "ecole",
        "documents": "document", "sauvegarde": "disque", "scolarite": "chapeau", "pedagogie": "livre",
        "administration": "reglages", "plateforme": "globe", "mes_enfants": "eleves", "mon_espace": "chapeau",
        "mon_edt": "calendrier", "roles": "outil", "absences": "calendrier",
    }

    @app.template_global()
    def icone(cle):
        """Icône d'un module, dessinée en SVG (fichier _icones.html inclus
        une fois par base.html). `cle` peut aussi être directement le nom
        d'un dessin (ex. "plus", "chevron")."""
        dessin = ICONES_MODULES.get(cle, cle)
        if not dessin:
            return ""
        return Markup(f'<svg class="icone" aria-hidden="true"><use href="#i-{escape(dessin)}"/></svg>')

    @app.template_filter("fcfa")
    def fcfa(montant, unite=True):
        """145000 → « 145 000 FCFA ». Espaces insécables : le montant ne
        se coupe jamais en fin de ligne."""
        try:
            entier = int(round(float(montant or 0)))
        except (TypeError, ValueError):
            return montant
        texte = f"{entier:,}".replace(",", "\u00a0")
        return f"{texte}\u00a0FCFA" if unite else texte

    JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
            "septembre", "octobre", "novembre", "décembre"]

    @app.template_filter("date_longue")
    def date_longue(jour, avec_jour=True):
        """date(2026, 10, 8) → « jeudi 8 octobre 2026 »."""
        if not jour:
            return ""
        texte = f"{'1er' if jour.day == 1 else jour.day} {MOIS[jour.month - 1]} {jour.year}"
        return f"{JOURS[jour.weekday()]} {texte}" if avec_jour else texte

    from app.services.pagination import liens_pagination
    app.add_template_global(liens_pagination, "pagination")

    @app.template_global()
    def mon_dossier_eleve():
        from app.models.eleve import Eleve
        if not current_user.is_authenticated or current_user.role != "eleve":
            return None
        return Eleve.query.filter_by(user_id=current_user.id, actif=True).first()

    @app.template_filter("genre_libelle")
    def genre_libelle(valeur):
        return {"M": "Masculin", "F": "Féminin"}.get(valeur, "—")

    @app.template_global()
    def etat_vide(texte, cle_icone="dossier"):
        """Écran vide (liste sans résultat) — un composant cohérent
        partout, plutôt qu'un simple texte gris différent d'une page à
        l'autre (sept. 2026). `texte` est échappé (pas de HTML actif) :
        pour un texte contenant un lien, garder le <p> manuel dans le
        template plutôt que ce raccourci."""
        return Markup(
            f'<div class="etat-vide"><span class="etat-vide-icone">{icone(cle_icone)}</span>'
            f'<p>{escape(texte)}</p></div>'
        )

    @app.template_global()
    def fil_ariane(*items):
        """Fil de navigation ("Accueil › Élèves › Fatima Abakar").
        Usage : {{ fil_ariane(("Élèves", url_for('eleves.liste')), (eleve.nom_complet, None)) }}
        Le dernier élément (page actuelle) n'a généralement pas de lien
        (sept. 2026)."""
        morceaux = [f'<a href="{escape(url_for("main.index"))}">Accueil</a>']
        for label, url in items:
            morceaux.append('<span class="fil-ariane-sep">›</span>')
            if url:
                morceaux.append(f'<a href="{escape(url)}">{escape(label)}</a>')
            else:
                morceaux.append(f'<span class="fil-ariane-actuel">{escape(label)}</span>')
        return Markup(f'<nav class="fil-ariane" aria-label="Fil d\'Ariane">{"".join(morceaux)}</nav>')

    @app.template_global()
    def banniere(cle_icone, titre, description=None):
        """Bandeau dégradé en haut d'une page de module — remplace un
        simple <h1> par quelque chose de plus soigné, sur le modèle des
        tableaux de bord de référence montrés par l'utilisateur
        (sept. 2026)."""
        bloc_description = f'<p>{escape(description)}</p>' if description else ""
        return Markup(
            f'<div class="banniere-page">'
            f'<span class="banniere-page-icone">{icone(cle_icone)}</span>'
            f'<div><h1>{escape(titre)}</h1>{bloc_description}</div>'
            f'</div>'
        )

    @app.template_global()
    def acces(*roles, module=None):
        """À utiliser dans les templates à la place de
        `current_user.role in [...]`. Inclut toujours le rôle
        développeur (accès complet, décision du fondateur — sept. 2026),
        pour que les templates ne se désynchronisent plus des permissions
        réelles définies côté serveur (roles_required).

        Avec `module=...` : respecte aussi une permission explicite de la
        matrice de l'espace développeur, comme roles_required."""
        if not current_user.is_authenticated:
            return False
        if module:
            from app.services.permissions import role_a_acces
            return role_a_acces(current_user.role, module, roles)
        return current_user.role == "developpeur" or current_user.role in roles

    @app.template_filter("initiales")
    def initiales(nom_complet):
        """Deux lettres pour l'avatar rond du menu (comme Moodle) —
        premières lettres du premier et du dernier mot du nom."""
        if not nom_complet:
            return "?"
        mots = nom_complet.split()
        if len(mots) == 1:
            return mots[0][0].upper()
        return (mots[0][0] + mots[-1][0]).upper()

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        # Chargé sans filtre d'école : c'est justement ce compte qui
        # détermine l'école de la requête.
        from sqlalchemy import select
        return db.session.execute(
            select(User).where(User.id == int(user_id)).execution_options(tous_etablissements=True)
        ).scalar_one_or_none()

    @app.before_request
    def fixer_ecole_courante():
        """Fixe l'école de la requête avant toute autre lecture en base.
        Un compte sans école (hors super-administrateur) ou rattaché à
        une école suspendue est déconnecté."""
        from flask import g, request as req
        from flask_login import logout_user
        from app.services.tenant import determiner_ecole, est_super_admin
        from app.models.ecole import Ecole

        g.ecole_id = None
        g.ecole_obj = None
        if req.endpoint == "static" or not current_user.is_authenticated:
            return
        ecole_id = determiner_ecole(current_user)
        if not est_super_admin(current_user):
            ecole = db.session.get(Ecole, ecole_id) if ecole_id else None
            if ecole is None or not ecole.actif:
                if req.endpoint not in ("auth.connexion", "auth.deconnexion"):
                    logout_user()
                    flash("L'accès de cet établissement est suspendu. Contacte l'administrateur de la plateforme.", "error")
                    return redirect(url_for("auth.connexion"))
                return
        g.ecole_id = ecole_id

    @app.template_global()
    def ecole():
        from app.services.tenant import ecole_courante
        return ecole_courante()

    @app.template_global()
    def nom_plateforme():
        return app.config.get("PLATEFORME_NOM", "Toumaï Edu School")

    @app.before_request
    def verifier_compte_toujours_actif():
        """Un compte verrouillé (ou refusé après coup) perd l'accès
        immédiatement, même en pleine session déjà ouverte — pas
        seulement à la prochaine connexion (sept. 2026)."""
        from flask import request as req
        if current_user.is_authenticated and current_user.statut not in ("actif",):
            if req.endpoint not in ("auth.connexion", "auth.deconnexion", "static"):
                from flask_login import logout_user
                logout_user()
                flash("Ce compte n'est plus actif. Contacte l'école si besoin.", "error")
                return redirect(url_for("auth.connexion"))

    from app.main import main_bp
    app.register_blueprint(main_bp)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.secretariat import secretariat_bp
    app.register_blueprint(secretariat_bp)

    from app.classes import classes_bp
    app.register_blueprint(classes_bp)

    from app.eleves import eleves_bp
    app.register_blueprint(eleves_bp)

    from app.tests_niveau import tests_niveau_bp
    app.register_blueprint(tests_niveau_bp)

    from app.enseignants import enseignants_bp
    app.register_blueprint(enseignants_bp)

    from app.emploi_du_temps import emploi_du_temps_bp
    app.register_blueprint(emploi_du_temps_bp)

    from app.suivi_cours import suivi_cours_bp
    app.register_blueprint(suivi_cours_bp)

    from app.absences import absences_bp
    app.register_blueprint(absences_bp)

    from app.sauvegarde import sauvegarde_bp
    app.register_blueprint(sauvegarde_bp)

    from app.alertes import alertes_bp
    app.register_blueprint(alertes_bp)

    from app.documents_officiels import documents_officiels_bp
    app.register_blueprint(documents_officiels_bp)

    from app.messagerie import messagerie_bp
    app.register_blueprint(messagerie_bp)

    from app.plateforme import plateforme_bp
    app.register_blueprint(plateforme_bp)

    from app.notes import notes_bp
    app.register_blueprint(notes_bp)

    from app.finances import finances_bp
    app.register_blueprint(finances_bp)

    from app.caisse import caisse_bp
    app.register_blueprint(caisse_bp)

    from app.salaires import salaires_bp
    app.register_blueprint(salaires_bp)

    from app.statistiques import statistiques_bp
    app.register_blueprint(statistiques_bp)

    from app.bibliotheque import bibliotheque_bp
    app.register_blueprint(bibliotheque_bp)

    from app.communication import communication_bp
    app.register_blueprint(communication_bp)

    from app.assistant import assistant_bp
    app.register_blueprint(assistant_bp)

    from app.dev import dev_bp
    app.register_blueprint(dev_bp)

    @app.cli.command("creer-compte-initial")
    @click.option("--nom", prompt="Nom complet")
    @click.option("--email", prompt="Email")
    @click.option("--mot-de-passe", prompt="Mot de passe", hide_input=True, confirmation_prompt=True)
    @click.option("--role", default="fondateur", help="Rôle du premier compte (fondateur, secretaire, ...).")
    def creer_compte_initial(nom, email, mot_de_passe, role):
        """Crée un premier compte déjà actif — nécessaire car aucun secrétaire
        n'existe encore pour approuver quiconque au tout premier lancement."""
        if User.query.filter_by(email=email).first():
            click.echo("Un compte existe déjà avec cet email.")
            return
        user = User(nom_complet=nom, email=email, role=role, statut="actif")
        user.set_mot_de_passe(mot_de_passe)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Compte {role} créé et actif : {email}")

    from app.sauvegarde.commandes import enregistrer_commandes
    enregistrer_commandes(app)

    # Création automatique des tables manquantes à chaque démarrage —
    # ne touche jamais aux tables/données déjà existantes. Nécessaire sur
    # le plan gratuit Render, qui n'a pas de Shell pour lancer la
    # commande manuellement (sept. 2026).
    with app.app_context():
        # Import explicite de tout modèle qui ne serait autrement chargé
        # qu'à l'intérieur d'une fonction (import paresseux) — sans ça,
        # SQLAlchemy ne connaît pas encore sa table au moment de
        # db.create_all() et ne la crée jamais (constaté sept. 2026 avec
        # JournalEmail, jamais importé au niveau module).
        from app.models.journal_email import JournalEmail  # noqa: F401
        from app.models.parametre import ParametreEtablissement  # noqa: F401
        from app.models.bulletin import CoefficientMatiere, AppreciationBulletin  # noqa: F401
        from app.models.evaluation import Evaluation  # noqa: F401
        from app.models.frais_annexe import FraisAnnexe  # noqa: F401

        db.create_all()
        from app.services.auto_migration import ajouter_colonnes_manquantes
        ajouter_colonnes_manquantes(app, db)
        from app.services.auto_migration import creer_index_manquants
        creer_index_manquants(app, db)
        from app.services.migration_saas import migrer_vers_multi_etablissements
        migrer_vers_multi_etablissements(app, db)
        from app.services.evaluations import rattacher_notes_sans_evaluation
        rattacher_notes_sans_evaluation(app)

    return app

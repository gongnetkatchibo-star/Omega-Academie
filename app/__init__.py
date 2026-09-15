import os
import click
from flask import Flask
from flask_login import current_user

from config import config
from app.extensions import db, migrate, login_manager, mail


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "default")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config[config_name])

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

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

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

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

    # Création automatique des tables manquantes à chaque démarrage —
    # ne touche jamais aux tables/données déjà existantes. Nécessaire sur
    # le plan gratuit Render, qui n'a pas de Shell pour lancer la
    # commande manuellement (sept. 2026).
    with app.app_context():
        db.create_all()

    return app

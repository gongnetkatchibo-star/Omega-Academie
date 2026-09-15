from flask import render_template
from flask_login import login_required, current_user

from app.main import main_bp
from app.models.user import ROLES_DIRECTION, ROLES_PERSONNEL
from app.models.eleve import Eleve


def _modules_pour(role):
    """Construit la liste des cartes du tableau de bord selon le rôle."""
    modules = []

    if role in ROLES_DIRECTION or role in ["secretaire"]:
        modules.append({"label": "Classes", "endpoint": "classes.liste",
                         "description": "Créer et consulter les classes."})
        modules.append({"label": "Élèves", "endpoint": "eleves.liste",
                         "description": "Inscriptions, dossiers, passages de classe."})
        modules.append({"label": "Tests de niveau", "endpoint": "tests_niveau.liste",
                         "description": "Admissions à évaluer."})

    if role in ROLES_DIRECTION or role in ["responsable_pedagogique"]:
        modules.append({"label": "Enseignants", "endpoint": "enseignants.liste",
                         "description": "Profils et affectations."})
        modules.append({"label": "Suivi des cours", "endpoint": "suivi_cours.tableau",
                         "description": "Avancement des programmes par classe."})

    if role == "enseignant":
        modules.append({"label": "Mon emploi du temps", "endpoint": "emploi_du_temps.moi",
                         "description": "Mes créneaux de cours."})
        modules.append({"label": "Classes", "endpoint": "classes.liste",
                         "description": "Voir les classes et accéder à la saisie de notes."})

    if role in ROLES_DIRECTION or role in ["comptable"]:
        modules.append({"label": "Finances", "endpoint": "finances.liste",
                         "description": "Frais dus, paiements, soldes par élève."})
        modules.append({"label": "Caisse", "endpoint": "caisse.liste",
                         "description": "Recettes et dépenses générales de l'école."})

    if role in ["fondateur", "administrateur_general", "directeur_primaire", "directeur_college", "comptable"]:
        modules.append({"label": "Statistiques", "endpoint": "statistiques.tableau",
                         "description": "Effectifs, recouvrement, indicateurs de l'école."})

    if role in ROLES_DIRECTION or role in ["secretaire"]:
        modules.append({"label": "Demandes de comptes", "endpoint": "secretariat.demandes",
                         "description": "Approuver ou refuser les inscriptions en attente."})

    modules.append({"label": "Bibliothèque", "endpoint": "bibliotheque.liste",
                     "description": "Livres, cours et exercices numériques."})
    modules.append({"label": "Annonces", "endpoint": "communication.liste",
                     "description": "Communications internes."})
    modules.append({"label": "Assistant", "endpoint": "assistant.index",
                     "description": "Aperçu de l'assistant (aucune IA connectée)."})

    if role == "developpeur":
        # Accès complet : toutes les cartes, direction comme personnel.
        modules.append({"label": "Classes", "endpoint": "classes.liste", "description": "Créer et consulter les classes."})
        modules.append({"label": "Élèves", "endpoint": "eleves.liste", "description": "Inscriptions, dossiers, passages de classe."})
        modules.append({"label": "Tests de niveau", "endpoint": "tests_niveau.liste", "description": "Admissions à évaluer."})
        modules.append({"label": "Enseignants", "endpoint": "enseignants.liste", "description": "Profils et affectations."})
        modules.append({"label": "Suivi des cours", "endpoint": "suivi_cours.tableau", "description": "Avancement des programmes par classe."})
        modules.append({"label": "Finances", "endpoint": "finances.liste", "description": "Frais dus, paiements, soldes par élève."})
        modules.append({"label": "Caisse", "endpoint": "caisse.liste", "description": "Recettes et dépenses générales de l'école."})
        modules.append({"label": "Statistiques", "endpoint": "statistiques.tableau", "description": "Effectifs, recouvrement, indicateurs de l'école."})
        modules.append({"label": "Demandes de comptes", "endpoint": "secretariat.demandes", "description": "Approuver ou refuser les inscriptions en attente."})
        modules.insert(0, {"label": "Espace développeur", "endpoint": "dev.utilisateurs",
                            "description": "Attribuer les rôles et gérer les comptes."})

    return modules


@main_bp.route("/")
def index():
    if not current_user.is_authenticated:
        return render_template("main/accueil_public.html")

    user = current_user
    modules = _modules_pour(user.role)

    mon_dossier_eleve = None
    if user.role == "eleve":
        mon_dossier_eleve = Eleve.query.filter_by(user_id=user.id, actif=True).first()

    # Tout compte peut avoir des enfants liés (tout le personnel peut
    # être parent, décision de la direction, sept. 2026) — pas seulement
    # le rôle "parent". On affiche la section "Mes enfants" dès qu'il y
    # en a, en plus de l'espace propre au rôle.
    enfants = sorted((e for e in user.enfants if e.actif), key=lambda e: e.nom_complet)

    return render_template(
        "main/index.html",
        user=user,
        modules=modules,
        enfants=enfants,
        mon_dossier_eleve=mon_dossier_eleve,
        est_personnel=user.role in ROLES_PERSONNEL,
        est_direction=user.role in ROLES_DIRECTION,
    )

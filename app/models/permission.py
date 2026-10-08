from app.extensions import db

# Modules gérables depuis la matrice de permissions (espace développeur).
# La saisie des notes n'y figure pas volontairement : "seul l'enseignant
# saisit les notes" est une règle métier tranchée avec la direction
# (Option A, sept. 2026), pas une permission à activer/désactiver.
MODULES = [
    ("classes", "Classes"),
    ("eleves", "Élèves"),
    ("enseignants", "Enseignants"),
    ("emploi_du_temps", "Emploi du temps"),
    ("suivi_cours", "Suivi des cours"),
    ("notes_supervision", "Bulletins (consultation)"),
    ("finances", "Finances"),
    ("caisse", "Caisse"),
    ("salaires", "Salaires"),
    ("tests_niveau", "Tests de niveau"),
    ("bibliotheque", "Bibliothèque"),
    ("communication", "Annonces (publication)"),
    ("statistiques", "Statistiques"),
    ("secretariat", "Validation des comptes"),
    ("absences", "Absences"),
    ("alertes", "Alertes (absences/moyennes)"),
    ("messagerie", "Messagerie parent-école"),
    ("cahier_textes", "Cahier de textes (consultation)"),
    ("discipline", "Retards et discipline"),
    ("calendrier", "Calendrier scolaire (modification)"),
    # Zones d'administration technique — réservées au développeur par
    # défaut, à accorder explicitement s'il le décide (sept. 2026).
    ("gestion_roles", "Attribution des rôles"),
    ("journal_actions", "Journal d'actions"),
    ("journal_emails", "Journal des emails envoyés"),
    ("sauvegarde", "Sauvegarde des données"),
]
MODULES_CLES = [cle for cle, _ in MODULES]


# Modules d'administration technique : seul le développeur les accorde,
# jamais le fondateur depuis la matrice de son école.
MODULES_TECHNIQUES = ["gestion_roles", "journal_actions", "journal_emails", "sauvegarde"]


class Permission(db.Model):
    """Accès d'un rôle à un module. Une ligne sans école (ecole_id vide)
    est le réglage commun à toutes les écoles ; une ligne d'une école le
    remplace pour cette école seulement (oct. 2026).

    Volontairement hors du filtre automatique par école : la recherche
    doit voir à la fois la ligne de l'école et la ligne commune."""

    __tablename__ = "permissions"
    __table_args__ = (
        db.UniqueConstraint("ecole_id", "role", "module", name="uq_permission_ecole_role_module"),
    )

    id = db.Column(db.Integer, primary_key=True)
    ecole_id = db.Column(db.Integer, db.ForeignKey("ecoles.id"), index=True)
    role = db.Column(db.String(40), nullable=False)
    module = db.Column(db.String(40), nullable=False)
    autorise = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<Permission {self.role}:{self.module}={self.autorise}>"

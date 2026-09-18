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
    # Zones d'administration technique — réservées au développeur par
    # défaut, à accorder explicitement s'il le décide (sept. 2026).
    ("gestion_roles", "Attribution des rôles"),
    ("journal_actions", "Journal d'actions"),
    ("journal_emails", "Journal des emails envoyés"),
    ("sauvegarde", "Sauvegarde des données"),
]
MODULES_CLES = [cle for cle, _ in MODULES]


class Permission(db.Model):
    __tablename__ = "permissions"
    __table_args__ = (
        db.UniqueConstraint("role", "module", name="uq_permission_role_module"),
    )

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(40), nullable=False)
    module = db.Column(db.String(40), nullable=False)
    autorise = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<Permission {self.role}:{self.module}={self.autorise}>"

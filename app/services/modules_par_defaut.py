"""Rôles par défaut de chaque module — copie fidèle de ce qui était codé
en dur dans chaque fichier de routes avant la matrice de permissions
(sept. 2026). Sert de référence à l'écran de permissions pour savoir ce
qui s'applique tant que le développeur n'a rien modifié explicitement.

Ne pas modifier cette liste pour changer un accès — ça se fait depuis
l'espace développeur (table Permission), pas dans le code. Ce fichier ne
change que si un tout nouveau module apparaît."""

ROLES_PAR_DEFAUT = {
    "classes": ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"],
    "eleves": ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"],
    "enseignants": ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"],
    "emploi_du_temps": ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"],
    "suivi_cours": ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"],
    "notes_supervision": ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"],
    "finances": ["comptable", "fondateur", "administrateur_general"],
    "caisse": ["comptable", "fondateur", "administrateur_general"],
    "salaires": ["comptable", "fondateur", "administrateur_general"],
    "tests_niveau": ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"],
    "bibliotheque": ["bibliothecaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "enseignant"],
    "communication": ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "secretaire", "enseignant"],
    "statistiques": ["comptable", "fondateur", "administrateur_general", "directeur_primaire", "directeur_college"],
    "secretariat": ["secretaire", "fondateur", "administrateur_general"],
    "absences": ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique", "secretaire"],
    "alertes": ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique", "secretaire"],
    # Aucun rôle par défaut : seul le développeur y accède (il est
    # toujours autorisé, quelle que soit la matrice). Le fondateur ou un
    # autre rôle doit se voir accorder l'accès explicitement.
    "gestion_roles": [],
    "journal_actions": [],
    "sauvegarde": [],
}

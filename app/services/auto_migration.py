"""Ajoute automatiquement, au démarrage, les colonnes qui existent dans
les modèles mais pas encore dans la base de données réelle.

Nécessaire car le plan gratuit Render n'offre pas de Shell pour lancer
`flask db migrate` manuellement (sept. 2026) : `db.create_all()` seul ne
crée que les tables manquantes, il ne modifie jamais une table qui
existe déjà — donc une nouvelle colonne ajoutée à un modèle existant
n'apparaîtrait jamais en production sans ce mécanisme.

Ne remplace pas un vrai système de migrations (Alembic) pour des
changements complexes (renommage, changement de type...) — mais couvre
le cas le plus fréquent ici : ajouter une colonne simple avec une valeur
par défaut."""

from sqlalchemy import inspect, text


def _valeur_sql_par_defaut(colonne):
    """Convertit colonne.default (valeur Python) en fragment SQL DEFAULT,
    ou None si on ne sait pas la représenter simplement."""
    if colonne.default is None or not hasattr(colonne.default, "arg"):
        return None
    valeur = colonne.default.arg
    if callable(valeur):
        return None  # ex. datetime.utcnow — pas de DEFAULT SQL simple et portable
    if isinstance(valeur, bool):
        return "TRUE" if valeur else "FALSE"
    if isinstance(valeur, (int, float)):
        return str(valeur)
    if isinstance(valeur, str):
        return "'" + valeur.replace("'", "''") + "'"
    return None


def ajouter_colonnes_manquantes(app, db):
    """À appeler une fois, juste après db.create_all(), dans le contexte
    de l'application."""
    inspecteur = inspect(db.engine)
    tables_existantes = set(inspecteur.get_table_names())

    for table in db.metadata.sorted_tables:
        if table.name not in tables_existantes:
            continue  # vient d'être créée par create_all(), rien à ajouter

        colonnes_existantes = {c["name"] for c in inspecteur.get_columns(table.name)}

        for colonne in table.columns:
            if colonne.name in colonnes_existantes:
                continue

            try:
                type_sql = colonne.type.compile(dialect=db.engine.dialect)
            except Exception:
                app.logger.warning(
                    "Type SQL non déterminable pour %s.%s — colonne ignorée, à ajouter manuellement.",
                    table.name, colonne.name,
                )
                continue

            defaut_sql = _valeur_sql_par_defaut(colonne)
            requete = f'ALTER TABLE "{table.name}" ADD COLUMN "{colonne.name}" {type_sql}'
            if defaut_sql is not None:
                requete += f" DEFAULT {defaut_sql}"
            # NOT NULL seulement si on a un DEFAULT pour satisfaire les
            # lignes déjà existantes — sinon on laisse la colonne
            # nullable plutôt que de faire échouer toute l'opération.
            if not colonne.nullable and defaut_sql is not None:
                requete += " NOT NULL"

            try:
                with db.engine.begin() as connexion:
                    connexion.execute(text(requete))
                app.logger.info("Colonne ajoutée automatiquement : %s.%s", table.name, colonne.name)
            except Exception:
                app.logger.exception(
                    "Échec de l'ajout automatique de %s.%s — à faire manuellement si besoin.",
                    table.name, colonne.name,
                )


# Index ajoutés après coup sur les colonnes les plus interrogées (listes,
# recherches, bulletins). `IF NOT EXISTS` : sans effet s'ils existent déjà.
INDEX_A_CREER = [
    ("ix_eleves_classe", "eleves", "classe_id"),
    ("ix_eleves_nom", "eleves", "nom_complet"),
    ("ix_notes_classe", "notes", "classe_id"),
    ("ix_notes_eleve", "notes", "eleve_id"),
    ("ix_absences_classe", "absences", "classe_id"),
    ("ix_absences_eleve", "absences", "eleve_id"),
    ("ix_paiements_eleve", "paiements", "eleve_id"),
    ("ix_mouvements_caisse_date", "mouvements_caisse", "date"),
    ("ix_mouvements_caisse_origine", "mouvements_caisse", "origine_id"),
    ("ix_journal_actions_date", "journal_actions", "date_action"),
    ("ix_journal_emails_date", "journal_emails", "date_envoi"),
    ("ix_messages_parent", "messages", "parent_id"),
    ("ix_historique_eleve", "historique_scolaire", "eleve_id"),
    ("ix_affectations_classe", "affectations", "classe_id"),
    ("ix_creneaux_classe", "creneaux", "classe_id"),
]


def creer_index_manquants(app, db):
    tables = set(inspect(db.engine).get_table_names())
    # Chaque requête filtre sur l'école : toutes les tables rattachées
    # à une école ont un index sur cette colonne.
    par_ecole = [
        (f"ix_{t.name}_ecole_id", t.name, "ecole_id") for t in db.metadata.sorted_tables if "ecole_id" in t.c
    ]
    with db.engine.begin() as connexion:
        for nom, table, colonne in INDEX_A_CREER + par_ecole:
            if table not in tables:
                continue
            try:
                connexion.execute(text(f'CREATE INDEX IF NOT EXISTS {nom} ON {table} ("{colonne}")'))
            except Exception as erreur:  # ne doit jamais empêcher le démarrage
                app.logger.warning("Index %s non créé : %s", nom, erreur)

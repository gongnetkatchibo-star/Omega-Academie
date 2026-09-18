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

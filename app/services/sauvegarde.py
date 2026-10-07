"""Sauvegarde complète d'un établissement et restauration.

Le fichier `donnees.json` de l'archive contient TOUTES les tables de
l'école, dans un format fidèle (dates, montants, fichiers binaires,
mots de passe hachés), pour pouvoir tout remettre en place à
l'identique. La restauration remplace les données de l'école par celles
de l'archive, dans une seule transaction : en cas d'erreur, rien ne
change."""

import base64
import datetime as dt
import json
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, LargeBinary, Numeric, Time, select

from app.extensions import db
from app.services.temps import maintenant

VERSION_FORMAT = 2
NOM_FICHIER_DONNEES = "donnees.json"

# Références « souples » (pas de clé étrangère en base) à recalculer
# après restauration : colonne -> {valeur du module: table visée}.
REFERENCES_SOUPLES = {
    "mouvements_caisse": ("origine_module", "origine_id", {"finances": "paiements", "salaires": "salaires"}),
}

TOUS = {"tous_etablissements": True}


class ErreurRestauration(Exception):
    pass


def tables_de_l_ecole():
    """Tables rattachées à une école, dans l'ordre où on peut les
    remplir (une table vient toujours après celles qu'elle référence)."""
    from app.services.tenant import modeles_rattaches

    rattachees = {m.__table__.name for m in modeles_rattaches()}
    return [t for t in db.metadata.sorted_tables if t.name in rattachees]


def _table_parents():
    return db.metadata.tables["eleve_parents"]


def _vers_json(valeur):
    if valeur is None or isinstance(valeur, (bool, int, float, str)):
        return valeur
    if isinstance(valeur, (dt.datetime, dt.date, dt.time)):
        return valeur.isoformat()
    if isinstance(valeur, Decimal):
        return str(valeur)
    if isinstance(valeur, (bytes, memoryview)):
        return base64.b64encode(bytes(valeur)).decode("ascii")
    return str(valeur)


def _depuis_json(valeur, colonne):
    if valeur is None:
        return None
    type_colonne = colonne.type
    if isinstance(type_colonne, LargeBinary):
        return base64.b64decode(valeur)
    if isinstance(type_colonne, DateTime):
        return dt.datetime.fromisoformat(valeur)
    if isinstance(type_colonne, Date):
        return dt.date.fromisoformat(valeur[:10])
    if isinstance(type_colonne, Time):
        return dt.time.fromisoformat(valeur)
    if isinstance(type_colonne, Numeric):
        return Decimal(str(valeur))
    if isinstance(type_colonne, Boolean):
        return bool(valeur)
    return valeur


def exporter_ecole(ecole):
    """Dictionnaire complet des données de l'école, prêt pour json.dumps."""
    tables = {}
    for table in tables_de_l_ecole():
        lignes = db.session.execute(
            select(table).where(table.c.ecole_id == ecole.id).order_by(table.c.id), execution_options=TOUS
        ).mappings().all()
        tables[table.name] = [{c: _vers_json(v) for c, v in ligne.items()} for ligne in lignes]

    eleves = db.metadata.tables["eleves"]
    parents = _table_parents()
    liens = db.session.execute(
        select(parents).where(parents.c.eleve_id.in_(select(eleves.c.id).where(eleves.c.ecole_id == ecole.id))),
        execution_options=TOUS,
    ).mappings().all()
    tables[parents.name] = [dict(lien) for lien in liens]

    return {
        "version": VERSION_FORMAT,
        "date": maintenant().isoformat(timespec="seconds"),
        "ecole": {"nom": ecole.nom, "sigle": ecole.sigle, "prefixe_matricule": ecole.prefixe_matricule},
        "tables": tables,
    }


def lire_archive(archive):
    """Extrait et contrôle le contenu d'une archive de sauvegarde."""
    if NOM_FICHIER_DONNEES not in archive.namelist():
        raise ErreurRestauration(
            "Cette archive ne contient pas de fichier de restauration (sauvegarde d'une ancienne version)."
        )
    try:
        donnees = json.loads(archive.read(NOM_FICHIER_DONNEES).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ErreurRestauration("Le fichier de sauvegarde est illisible.")
    if donnees.get("version") != VERSION_FORMAT or not isinstance(donnees.get("tables"), dict):
        raise ErreurRestauration("Format de sauvegarde non reconnu.")
    return donnees


def _vider_ecole(ecole_id):
    eleves = db.metadata.tables["eleves"]
    parents = _table_parents()
    db.session.execute(
        parents.delete().where(parents.c.eleve_id.in_(select(eleves.c.id).where(eleves.c.ecole_id == ecole_id))),
        execution_options=TOUS,
    )
    for table in reversed(tables_de_l_ecole()):
        db.session.execute(table.delete().where(table.c.ecole_id == ecole_id), execution_options=TOUS)


def _cible(colonne):
    """Table visée par une clé étrangère, ou None."""
    for cle in colonne.foreign_keys:
        return cle.column.table.name
    return None


def restaurer_ecole(ecole, donnees):
    """Remplace les données de l'école par celles de la sauvegarde.
    Retourne {table: nombre de lignes restaurées}. Lève ErreurRestauration
    (après annulation complète) si quoi que ce soit échoue."""
    from sqlalchemy.exc import IntegrityError

    tables_sauvegardees = donnees["tables"]
    correspondances = {}  # {table: {ancien id: nouvel id}}
    bilan = {}

    try:
        _vider_ecole(ecole.id)
        db.session.flush()

        for table in tables_de_l_ecole():
            nouvelles = correspondances.setdefault(table.name, {})
            restaurees = 0
            for ligne in tables_sauvegardees.get(table.name, []):
                valeurs, ignorer = {}, False
                for colonne in table.columns:
                    if colonne.name == "id" or colonne.name not in ligne:
                        continue
                    valeur = ligne[colonne.name]
                    cible = _cible(colonne)
                    if colonne.name == "ecole_id":
                        valeur = ecole.id
                    elif cible and valeur is not None:
                        valeur = correspondances.get(cible, {}).get(valeur)
                        if valeur is None and not colonne.nullable:
                            ignorer = True  # référence à une donnée absente de la sauvegarde
                            break
                    else:
                        valeur = _depuis_json(valeur, colonne)
                    valeurs[colonne.name] = valeur
                if ignorer:
                    continue
                resultat = db.session.execute(table.insert().values(**valeurs), execution_options=TOUS)
                nouvelles[ligne["id"]] = resultat.inserted_primary_key[0]
                restaurees += 1
            bilan[table.name] = restaurees

        parents = _table_parents()
        liens = 0
        for lien in tables_sauvegardees.get(parents.name, []):
            eleve_id = correspondances.get("eleves", {}).get(lien.get("eleve_id"))
            parent_id = correspondances.get("users", {}).get(lien.get("parent_id"))
            if eleve_id and parent_id:
                db.session.execute(parents.insert().values(eleve_id=eleve_id, parent_id=parent_id), execution_options=TOUS)
                liens += 1
        bilan[parents.name] = liens

        for nom_table, (col_module, col_id, cibles) in REFERENCES_SOUPLES.items():
            table = db.metadata.tables[nom_table]
            for origine in tables_sauvegardees.get(nom_table, []):
                nouveau = correspondances.get(nom_table, {}).get(origine["id"])
                table_cible = cibles.get(origine.get(col_module))
                if nouveau is None or table_cible is None or origine.get(col_id) is None:
                    continue
                db.session.execute(
                    table.update().where(table.c.id == nouveau).values(
                        **{col_id: correspondances.get(table_cible, {}).get(origine[col_id])}
                    ),
                    execution_options=TOUS,
                )

        db.session.flush()
    except IntegrityError as erreur:
        db.session.rollback()
        detail = str(getattr(erreur, "orig", erreur)).splitlines()[0][:200]
        raise ErreurRestauration(
            "Restauration annulée, rien n'a été modifié : une donnée de la sauvegarde existe déjà "
            f"dans un autre établissement (email ou matricule). Détail : {detail}"
        )
    except ErreurRestauration:
        db.session.rollback()
        raise
    except Exception as erreur:  # archive abîmée, colonne inattendue…
        db.session.rollback()
        raise ErreurRestauration(f"Restauration annulée, rien n'a été modifié : sauvegarde invalide ({erreur}).")

    return bilan

"""Supprimer une ligne sans casser la base.

Avant de supprimer un compte (ou un profil enseignant), on regarde tout
ce qui pointe vers lui, d'après la structure réelle de la base : une
nouvelle table est donc prise en compte sans rien ajouter ici.
- lien facultatif : on le vide (l'historique reste, sans auteur) ;
- lien obligatoire : la suppression est refusée, avec la raison."""

from sqlalchemy import func, select

from app.extensions import db

TOUS = {"tous_etablissements": True}

# Nom lisible des tables qui peuvent bloquer une suppression.
LIBELLES_TABLES = {
    "suivis_cours": "des suivis de cours",
    "salaires": "des salaires",
    "prets": "des prêts de livres",
    "messages": "des messages",
    "numeros_telephone": "des numéros de téléphone",
    "affectations": "des affectations",
    "enseignants": "un profil enseignant",
}


def references_vers(nom_table, identifiant):
    """[(table, colonne, facultative, nombre de lignes)] pointant vers
    cette ligne, pour les seuls liens réellement utilisés."""
    trouvees = []
    for table in db.metadata.sorted_tables:
        for colonne in table.columns:
            if not any(cle.column.table.name == nom_table for cle in colonne.foreign_keys):
                continue
            nombre = db.session.execute(
                select(func.count()).select_from(table).where(colonne == identifiant), execution_options=TOUS,
            ).scalar()
            if nombre:
                trouvees.append((table, colonne, colonne.nullable, nombre))
    return trouvees


def detacher(nom_table, identifiant, deja_traitees=()):
    """Vide tous les liens facultatifs vers cette ligne. Retourne les
    noms des tables qui la référencent encore par un lien obligatoire
    (hors `deja_traitees`, que l'appelant gère lui-même)."""
    bloquantes = []
    for table, colonne, facultative, _ in references_vers(nom_table, identifiant):
        if (table.name, colonne.name) in deja_traitees or table.name in deja_traitees:
            continue
        if facultative:
            db.session.execute(
                table.update().where(colonne == identifiant).values({colonne.name: None}), execution_options=TOUS,
            )
        else:
            bloquantes.append(table.name)
    return sorted(set(bloquantes))


def libelle_tables(noms):
    return ", ".join(LIBELLES_TABLES.get(nom, nom) for nom in noms)

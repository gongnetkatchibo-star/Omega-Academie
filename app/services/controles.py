"""Contrôles appliqués à toute écriture en base.

Longueur des textes : PostgreSQL refuse un texte plus long que la
colonne (SQLite, en développement, l'accepte sans rien dire). On le
vérifie donc nous-mêmes avant l'écriture, pour afficher un message qui
nomme le champ au lieu d'une erreur générique."""

from sqlalchemy import String, event, inspect
from sqlalchemy.orm import Session


class TexteTropLong(ValueError):
    def __init__(self, champ, maximum, longueur):
        super().__init__(f"{champ} : {longueur} caractères pour {maximum} au maximum")
        self.champ, self.maximum, self.longueur = champ, maximum, longueur


_installe = False


def installer_controle_longueurs():
    global _installe
    if _installe:  # une seule fois, même si plusieurs applications sont créées (tests)
        return
    _installe = True

    @event.listens_for(Session, "before_flush")
    def _verifier_longueurs(session_db, flush_context, instances):
        for objet in list(session_db.new) + list(session_db.dirty):
            etat = inspect(objet)
            for attribut in etat.mapper.column_attrs:
                colonne = attribut.columns[0]
                maximum = getattr(colonne.type, "length", None)
                if not maximum or not isinstance(colonne.type, String):
                    continue
                ajoutees = etat.attrs[attribut.key].history.added
                if ajoutees and isinstance(ajoutees[0], str) and len(ajoutees[0]) > maximum:
                    raise TexteTropLong(attribut.key.replace("_", " "), maximum, len(ajoutees[0]))

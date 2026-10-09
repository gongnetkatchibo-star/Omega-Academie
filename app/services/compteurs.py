"""Compteurs de numéros (reçus, documents officiels).

Un compteur par école, par type et par année. La ligne du compteur est
verrouillée le temps d'attribuer le numéro : deux personnes qui valident
au même instant obtiennent deux numéros qui se suivent, jamais le même.
La toute première attribution de l'année crée le compteur ; si deux
personnes la font en même temps, la seconde attend puis reprend la ligne
créée par la première (au lieu d'échouer sur un doublon)."""

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.numero_document import NumeroDocument


def prochain_numero(type_document, annee, depart=0):
    """Numéro suivant pour l'école courante. `depart` : dernier numéro
    déjà utilisé avant l'existence du compteur (valeur, ou fonction
    appelée seulement à la création)."""
    from app.services.tenant import ecole_courante_id

    for _ in range(5):
        compteur = (
            NumeroDocument.query.filter_by(type_document=type_document, annee=annee)
            .with_for_update().first()
        )
        if compteur is not None:
            compteur.dernier_numero += 1
            return compteur.dernier_numero
        dernier = depart() if callable(depart) else depart
        try:
            with db.session.begin_nested():
                db.session.add(NumeroDocument(
                    type_document=type_document, annee=annee, dernier_numero=dernier or 0,
                    ecole_id=ecole_courante_id(),
                ))
        except IntegrityError:
            pass  # créé au même instant par quelqu'un d'autre : on le relit
    raise RuntimeError("Compteur de numéros indisponible.")

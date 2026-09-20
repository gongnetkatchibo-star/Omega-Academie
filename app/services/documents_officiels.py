"""Documents officiels du Complexe Scolaire Oméga Académie (CSOA) — un
seul endroit pour la date, la numérotation et l'en-tête, repris à
l'identique sur chaque document (certificat, attestation, décision...),
sur le modèle exact du document officiel fourni par l'école
(Décision N°001/CSOA/PCA/2026), sept. 2026."""

from datetime import date as date_cls

from app.extensions import db
from app.models.numero_document import NumeroDocument

NOM_ETABLISSEMENT = "COMPLEXE SCOLAIRE OMEGA ACADÉMIE"
VILLE_ETABLISSEMENT = "Pala"
PAYS_ETABLISSEMENT = "Tchad"
SIGLE_ETABLISSEMENT = "CSOA"

MOIS_LETTRES = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def date_officielle(une_date=None):
    """Formate une date comme sur le document original : "1er juin 2026",
    "5 septembre 2026" — jamais saisie à la main, toujours calculée."""
    une_date = une_date or date_cls.today()
    jour = une_date.day
    jour_texte = "1er" if jour == 1 else str(jour)
    return f"{jour_texte} {MOIS_LETTRES[une_date.month - 1]} {une_date.year}"


def lieu_et_date_officiels(une_date=None):
    """Ex. "Pala, le 1er juin 2026" — exactement le format du document
    original."""
    return f"{VILLE_ETABLISSEMENT}, le {date_officielle(une_date)}"


def numero_reference(type_document, annee=None):
    """Génère le prochain numéro pour ce type de document, sur cette
    année — ex. "003/CSOA/CERT/2026". S'incrémente tout seul, jamais
    saisi à la main, jamais de doublon possible même si deux personnes
    génèrent un document au même moment (verrouillage de ligne)."""
    annee = annee or date_cls.today().year

    compteur = (
        NumeroDocument.query
        .filter_by(type_document=type_document, annee=annee)
        .with_for_update()
        .first()
    )
    if compteur is None:
        compteur = NumeroDocument(type_document=type_document, annee=annee, dernier_numero=0)
        db.session.add(compteur)
        db.session.flush()

    compteur.dernier_numero += 1
    numero = compteur.dernier_numero
    db.session.commit()

    return f"{numero:03d}/{SIGLE_ETABLISSEMENT}/{type_document}/{annee}"


def contexte_entete_officiel():
    """Variables communes à injecter dans le rendu de tout document PDF
    portant l'en-tête officiel — évite de les répéter dans chaque route
    (sept. 2026)."""
    from app.utils import logo_officiel_data_uri

    return {
        "logo_officiel_uri": logo_officiel_data_uri(),
        "nom_etablissement": NOM_ETABLISSEMENT,
        "ville_etablissement": VILLE_ETABLISSEMENT,
        "pays_etablissement": PAYS_ETABLISSEMENT,
    }

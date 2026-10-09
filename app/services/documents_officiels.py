"""Documents officiels de l'établissement courant — un seul endroit pour
la date, la numérotation et l'en-tête, repris à l'identique sur chaque
document. Nom, sigle, ville et logo viennent de l'école de la requête
(mode multi-établissements)."""

from datetime import date as date_cls

from app.extensions import db
from app.models.numero_document import NumeroDocument
from app.services.temps import aujourd_hui  # date de l'école, pas celle du serveur



def identite_ecole():
    """Nom officiel (majuscules), sigle, ville et pays de l'école courante."""
    from app.services.tenant import ecole_courante

    ecole = ecole_courante()
    if ecole is None:
        return {"nom": "", "sigle": "", "ville": "", "pays": ""}
    return {
        "nom": ecole.nom_officiel,
        "sigle": ecole.sigle or "",
        "ville": ecole.ville or "",
        "pays": ecole.pays or "",
    }

MOIS_LETTRES = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def date_officielle(une_date=None):
    """Formate une date comme sur le document original : "1er juin 2026",
    "5 septembre 2026" — jamais saisie à la main, toujours calculée."""
    une_date = une_date or aujourd_hui()
    jour = une_date.day
    jour_texte = "1er" if jour == 1 else str(jour)
    return f"{jour_texte} {MOIS_LETTRES[une_date.month - 1]} {une_date.year}"


def lieu_et_date_officiels(une_date=None):
    """Ex. "Pala, le 1er juin 2026" — exactement le format du document
    original."""
    ville = identite_ecole()["ville"]
    date_texte = date_officielle(une_date)
    return f"{ville}, le {date_texte}" if ville else f"Le {date_texte}"


def numero_reference(type_document, annee=None):
    """Génère le prochain numéro pour ce type de document, sur cette
    année — ex. "003/CSOA/CERT/2026". S'incrémente tout seul, jamais
    saisi à la main, jamais de doublon possible même si deux personnes
    génèrent un document au même moment (verrouillage de ligne)."""
    from app.services.compteurs import prochain_numero

    annee = annee or aujourd_hui().year
    numero = prochain_numero(type_document, annee)
    db.session.commit()

    sigle = identite_ecole()["sigle"] or "DOC"
    return f"{numero:03d}/{sigle}/{type_document}/{annee}"


def signataire_par_defaut():
    from app.models.parametre import ParametreEtablissement

    parametre = ParametreEtablissement.get()
    return {
        "nom": parametre.nom_directeur or "",
        "qualite": parametre.titre_directeur or "Directeur",
        "genre": parametre.genre_directeur or "M",
    }


def contexte_entete_officiel():
    """Variables communes à tout PDF portant l'en-tête officiel : logo,
    nom de l'établissement, lieu et date, signataire par défaut."""
    from app.utils import logo_officiel_data_uri

    from app.models.parametre import ParametreEtablissement

    identite = identite_ecole()
    contexte = {
        "logo_officiel_uri": logo_officiel_data_uri(),
        "nom_etablissement": identite["nom"],
        "ville_etablissement": identite["ville"],
        "pays_etablissement": identite["pays"],
        "lieu_et_date": lieu_et_date_officiels(),
        "signataire": signataire_par_defaut(),
        "bilingue": bool(ParametreEtablissement.get().documents_bilingues),
    }
    contexte.update(identite_arabe())
    return contexte


def identite_arabe():
    """Nom, ville, pays et « lieu et date » en arabe, pour l'en-tête des
    documents bilingues. Les nombres sont marqués ⟦ ⟧ (voir langues.py)."""
    from app.services.langues import traduction_document, ltr
    from app.services.tenant import ecole_courante
    from app.services.traductions_ar import MOIS

    ecole = ecole_courante()
    jour = aujourd_hui()
    ville = (ecole.ville_arabe if ecole else None) or ""
    date_arabe = f"{ltr(jour.day)} {MOIS[jour.month - 1]} {ltr(jour.year)}"
    return {
        "nom_arabe": (ecole.nom_arabe if ecole else None) or "",
        "ville_arabe": ville,
        "pays_arabe": traduction_document(ecole.pays if ecole else "") or "",
        "lieu_et_date_arabe": f"{ville} في {date_arabe}" if ville else f"بتاريخ {date_arabe}",
    }

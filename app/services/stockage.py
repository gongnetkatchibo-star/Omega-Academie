"""Espace de stockage de chaque école (oct. 2026).

Tout ce qu'une école téléverse est rangé en base : photos d'élèves,
documents de la bibliothèque, pièces jointes des annonces, logo,
filigrane, signature, cachet. L'espace utilisé est la somme de ces
fichiers ; chaque école a un quota (5 Go par défaut, réglable par
l'administrateur de la plateforme). Un téléversement qui ferait dépasser
le quota est refusé avec un message clair."""

from sqlalchemy import LargeBinary, func, select

from app.extensions import db

QUOTA_PAR_DEFAUT = 5 * 1024 ** 3
TOUS = {"tous_etablissements": True}


def _colonnes_fichiers():
    """[(table, colonne)] des colonnes binaires des tables d'une école."""
    from app.services.sauvegarde import tables_de_l_ecole

    return [(t, c) for t in tables_de_l_ecole() for c in t.columns if isinstance(c.type, LargeBinary)]


def espace_utilise(ecole_id, detail=False):
    """Octets occupés par les fichiers de l'école (et, si `detail`, la
    répartition par catégorie)."""
    from app.models.ecole import Ecole

    parts = {}
    for table, colonne in _colonnes_fichiers():
        taille = db.session.execute(
            select(func.coalesce(func.sum(func.length(colonne)), 0)).where(table.c.ecole_id == ecole_id),
            execution_options=TOUS,
        ).scalar() or 0
        if taille:
            parts[CATEGORIES.get(table.name, "Autres fichiers")] = parts.get(CATEGORIES.get(table.name, "Autres fichiers"), 0) + int(taille)
    images = 0
    for nom in ("logo", "filigrane", "signature", "cachet"):
        colonne = Ecole.__table__.c[nom]
        images += int(db.session.execute(
            select(func.coalesce(func.length(colonne), 0)).where(Ecole.__table__.c.id == ecole_id)
        ).scalar() or 0)
    if images:
        parts["Images de l'école"] = images
    total = sum(parts.values())
    return (total, parts) if detail else total


CATEGORIES = {
    "eleves": "Photos des élèves",
    "ressources": "Bibliothèque numérique",
    "annonces": "Pièces jointes des annonces",
}


def quota(ecole):
    return int(ecole.quota_stockage or QUOTA_PAR_DEFAUT) if ecole else QUOTA_PAR_DEFAUT


def place_disponible(taille_ajoutee, ecole=None):
    """None si le fichier tient dans le quota de l'école, sinon le
    message d'erreur à afficher."""
    from app.services.tenant import ecole_courante

    ecole = ecole or ecole_courante()
    if ecole is None:
        return None
    limite = quota(ecole)
    utilise = espace_utilise(ecole.id)
    if utilise + taille_ajoutee > limite:
        return (
            f"Espace de stockage plein : {taille_lisible(utilise)} utilisés sur {taille_lisible(limite)}. "
            "Supprime des fichiers inutiles ou demande plus d'espace à l'administrateur de la plateforme."
        )
    return None


def taille_lisible(octets):
    octets = float(octets or 0)
    for unite in ("octets", "Ko", "Mo", "Go"):
        if octets < 1024 or unite == "Go":
            return f"{octets:.0f} {unite}" if unite == "octets" else f"{octets:.1f} {unite}".replace(".", ",")
        octets /= 1024


def etat(ecole):
    """Ce qu'affichent les jauges : utilisé, quota, pourcentage, détail."""
    utilise, parts = espace_utilise(ecole.id, detail=True)
    limite = quota(ecole)
    return {
        "utilise": utilise, "quota": limite, "pourcent": min(100, round(utilise * 100 / limite)) if limite else 0,
        "utilise_lisible": taille_lisible(utilise), "quota_lisible": taille_lisible(limite),
        "parts": sorted(((nom, taille_lisible(t)) for nom, t in parts.items()), key=lambda x: x[0]),
    }

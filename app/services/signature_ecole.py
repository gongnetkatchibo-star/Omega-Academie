"""Signature et cachet de l'école, imprimés sur les documents quand
l'école le choisit (oct. 2026).

Par défaut rien n'est imprimé : le signataire signe et tamponne le
papier à la main. Si l'école a téléversé sa signature et son cachet
(réglages de l'établissement, direction seulement), elle peut choisir
de les faire imprimer — par défaut pour tous ses documents, ou document
par document au moment de la génération.

Les images sont nettoyées à l'enregistrement : le fond blanc d'une
photo ou d'un scan devient transparent, pour que la signature et le
cachet se posent sur le document sans rectangle blanc autour."""

import io

from app.services.images_ecole import FORMATS_IMAGE, data_uri

TAILLE_MAX = 4 * 1024 * 1024
COTE_MAX = 700
# Taille de l'image composée (cachet à gauche, signature par-dessus à droite).
LARGEUR_BLOC, HAUTEUR_BLOC = 640, 300


def nettoyer_image(fichier):
    """(PNG transparent, None), (None, erreur) ou (None, None) sans fichier."""
    if not fichier or not fichier.filename:
        return None, None
    if fichier.mimetype not in FORMATS_IMAGE:
        return None, "Image refusée : formats acceptés PNG, JPEG ou WEBP."
    contenu = fichier.read()
    if len(contenu) > TAILLE_MAX:
        return None, "Image refusée : 4 Mo maximum."
    try:
        return fond_transparent(contenu), None
    except Exception:
        return None, "Image refusée : le fichier n'est pas une image valide."


def fond_transparent(contenu):
    """Rend transparent le papier blanc autour de l'encre, recadre sur
    l'encre et réduit l'image."""
    from PIL import Image, ImageChops, ImageOps

    image = ImageOps.exif_transpose(Image.open(io.BytesIO(contenu))).convert("RGBA")
    image.thumbnail((COTE_MAX, COTE_MAX))
    # Plus un point est clair, plus il est transparent (dégradé entre 170 et 235).
    clarte = image.convert("L")
    opacite = clarte.point(lambda v: 0 if v >= 235 else (255 if v <= 170 else int((235 - v) * 255 / 65)))
    image.putalpha(ImageChops.darker(image.getchannel("A"), opacite))
    cadre = image.getchannel("A").getbbox()
    if cadre:
        image = image.crop(cadre)
    sortie = io.BytesIO()
    image.save(sortie, "PNG", optimize=True)
    return sortie.getvalue()


def disponible(ecole):
    return bool(ecole and (ecole.signature or ecole.cachet))


def bloc_png(ecole):
    """Cachet et signature réunis en une seule image transparente, comme
    sur un document signé puis tamponné. None si l'école n'a ni l'un ni
    l'autre."""
    from PIL import Image

    if not disponible(ecole):
        return None
    bloc = Image.new("RGBA", (LARGEUR_BLOC, HAUTEUR_BLOC), (0, 0, 0, 0))

    def poser(contenu, largeur, hauteur, x_centre):
        image = Image.open(io.BytesIO(contenu)).convert("RGBA")
        image.thumbnail((largeur, hauteur))
        bloc.alpha_composite(image, (int(x_centre - image.width / 2), int((HAUTEUR_BLOC - image.height) / 2)))

    try:
        if ecole.cachet and ecole.signature:
            poser(ecole.cachet, 290, 290, 170)
            poser(ecole.signature, 400, 220, 420)
        elif ecole.cachet:
            poser(ecole.cachet, 290, 290, LARGEUR_BLOC / 2)
        else:
            poser(ecole.signature, 480, 240, LARGEUR_BLOC / 2)
    except Exception:
        return None
    sortie = io.BytesIO()
    bloc.save(sortie, "PNG", optimize=True)
    return sortie.getvalue()


def bloc_data_uri(ecole):
    contenu = bloc_png(ecole)
    return data_uri(contenu, "image/png") if contenu else None


def imprimee_par_defaut():
    """L'école a-t-elle choisi d'imprimer signature et cachet sur ses documents ?"""
    from app.models.parametre import ParametreEtablissement
    from app.services.tenant import ecole_courante

    return bool(ParametreEtablissement.get().signature_imprimee) and disponible(ecole_courante())

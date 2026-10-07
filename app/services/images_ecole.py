"""Logo et filigrane propres à chaque école, stockés en base (le disque
du serveur s'efface à chaque redéploiement sur Render)."""

import base64

FORMATS_IMAGE = {"image/png", "image/jpeg", "image/webp"}
TAILLE_MAX = 2 * 1024 * 1024


def lire_image_televersee(fichier):
    """Renvoie (contenu, type) si le fichier est une image acceptable,
    (None, message d'erreur) sinon, ou (None, None) si aucun fichier."""
    if not fichier or not fichier.filename:
        return None, None
    if fichier.mimetype not in FORMATS_IMAGE:
        return None, "Image refusée : formats acceptés PNG, JPEG ou WEBP."
    contenu = fichier.read()
    if len(contenu) > TAILLE_MAX:
        return None, "Image refusée : 2 Mo maximum."
    try:
        from PIL import Image
        import io
        Image.open(io.BytesIO(contenu)).verify()
    except Exception:
        return None, "Image refusée : le fichier n'est pas une image valide."
    return contenu, fichier.mimetype


def data_uri(contenu, mime):
    if not contenu:
        return None
    return f"data:{mime or 'image/png'};base64,{base64.b64encode(contenu).decode('ascii')}"


TAILLE_MAX_PHOTO = 8 * 1024 * 1024
COTE_MAX_PHOTO = 400


def photo_identite(fichier):
    """Photo d'élève : acceptée jusqu'à 8 Mo (photo de téléphone), puis
    réduite à 400 px de côté et enregistrée en JPEG, pour ne pas alourdir
    la base. Renvoie (contenu, type), (None, erreur) ou (None, None)."""
    import io

    if not fichier or not fichier.filename:
        return None, None
    if fichier.mimetype not in FORMATS_IMAGE:
        return None, "Photo refusée : formats acceptés PNG, JPEG ou WEBP."
    contenu = fichier.read()
    if len(contenu) > TAILLE_MAX_PHOTO:
        return None, "Photo refusée : 8 Mo maximum."
    try:
        from PIL import Image, ImageOps
        image = Image.open(io.BytesIO(contenu))
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((COTE_MAX_PHOTO, COTE_MAX_PHOTO))
        sortie = io.BytesIO()
        image.save(sortie, "JPEG", quality=85)
    except Exception:
        return None, "Photo refusée : le fichier n'est pas une image valide."
    return sortie.getvalue(), "image/jpeg"

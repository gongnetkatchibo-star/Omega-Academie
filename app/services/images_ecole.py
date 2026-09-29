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

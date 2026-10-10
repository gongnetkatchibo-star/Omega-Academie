"""Icône de l'application installée sur le téléphone, tirée du logo de
chaque école (au lieu de l'icône de la plateforme).

Le logo est posé au centre d'un carré blanc : il n'est ni déformé ni
rogné, quelle que soit sa forme. La version « masquable » laisse plus de
marge, car Android découpe l'icône en rond ou en carré arrondi."""

import hashlib
import io
from functools import lru_cache

TAILLES = (64, 180, 192, 512)
PART_NORMALE = 0.86     # place prise par le logo dans le carré
PART_MASQUABLE = 0.62   # dans la zone toujours visible après découpe


@lru_cache(maxsize=64)
def _dessiner(empreinte, logo, taille, masquable):
    from PIL import Image, ImageOps

    image = Image.open(io.BytesIO(logo)).convert("RGBA")
    cote = int(taille * (PART_MASQUABLE if masquable else PART_NORMALE))
    # Ajusté à la place disponible : réduit s'il est grand, agrandi s'il
    # est petit, toujours dans ses proportions.
    image = ImageOps.contain(image, (cote, cote), Image.LANCZOS)
    fond = Image.new("RGBA", (taille, taille), "#FFFFFF")
    fond.alpha_composite(image, ((taille - image.width) // 2, (taille - image.height) // 2))
    sortie = io.BytesIO()
    fond.convert("RGB").save(sortie, "PNG", optimize=True)
    return sortie.getvalue()


def empreinte_logo(ecole):
    """Change quand le logo change : sert à renouveler l'icône en cache."""
    return hashlib.sha1(ecole.logo).hexdigest()[:12] if ecole is not None and ecole.logo else ""


def icone_ecole(ecole, taille, masquable=False):
    """PNG carré de `taille` pixels, ou None si l'école n'a pas de logo
    (ou un logo illisible)."""
    if ecole is None or not ecole.logo or taille not in TAILLES:
        return None
    try:
        return _dessiner(empreinte_logo(ecole), bytes(ecole.logo), taille, bool(masquable))
    except Exception:
        return None


def nom_court(ecole):
    """Nom sous l'icône, sur l'écran du téléphone : une douzaine de lettres."""
    if ecole.sigle and len(ecole.sigle) <= 12:
        return ecole.sigle
    return ecole.nom if len(ecole.nom) <= 12 else ecole.nom[:11].rstrip() + "…"

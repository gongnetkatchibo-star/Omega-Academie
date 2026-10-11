"""Cartes d'élève (oct. 2026) : planche A4 à découper, dix cartes par
feuille au format d'une carte bancaire (85,6 × 54 mm).

Tout est repris du dossier de l'élève et des réglages de l'école : rien
n'est saisi au moment de l'impression. Le verso porte la personne à
prévenir et le QR code de vérification ; il est imprimé sur la feuille
suivante, colonnes inversées, pour tomber dos à dos avec le recto quand
on imprime en recto verso (retournement sur le bord long)."""

import io

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

LARGEUR, HAUTEUR = 85.6 * mm, 54 * mm
COLONNES, LIGNES = 2, 5
CARTES_PAR_PAGE = COLONNES * LIGNES
ECART_X, ECART_Y = 6 * mm, 3 * mm
MARGE_X = (A4[0] - COLONNES * LARGEUR - (COLONNES - 1) * ECART_X) / 2
MARGE_Y = (A4[1] - LIGNES * HAUTEUR - (LIGNES - 1) * ECART_Y) / 2

NORMAL, GRAS, ITALIQUE = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
ENCRE, GRIS, TRAIT = HexColor("#16202B"), HexColor("#5B6775"), HexColor("#B8C4CF")


def _texte(valeur):
    """Les polices intégrées au PDF couvrent le français ; tout autre
    caractère est remplacé plutôt que de faire échouer l'impression."""
    return str(valeur or "").encode("cp1252", "replace").decode("cp1252")


def _ajuster(texte, police, taille, largeur, taille_min=None):
    """(texte, taille) : réduit le corps puis, s'il le faut, coupe le texte."""
    texte = _texte(texte)
    taille_min = taille_min or taille
    while taille > taille_min and stringWidth(texte, police, taille) > largeur:
        taille -= 0.25
    if stringWidth(texte, police, taille) > largeur:
        while len(texte) > 1 and stringWidth(texte + "…", police, taille) > largeur:
            texte = texte[:-1]
        texte = texte.rstrip() + "…"
    return texte, taille


def _lignes(texte, police, taille, largeur, maximum):
    """Coupe un texte en lignes qui tiennent dans la largeur."""
    lignes, courante = [], ""
    for mot in _texte(texte).split():
        essai = f"{courante} {mot}".strip()
        if courante and stringWidth(essai, police, taille) > largeur:
            lignes.append(courante)
            courante = mot
        else:
            courante = essai
    if courante:
        lignes.append(courante)
    if len(lignes) > maximum:
        lignes = lignes[:maximum]
        lignes[-1] = _ajuster(lignes[-1] + " …", police, taille, largeur)[0]
    return lignes


def _image(contenu):
    try:
        return ImageReader(io.BytesIO(contenu)) if contenu else None
    except Exception:
        return None


def _photo(contenu):
    """Photo recadrée au format 4 × 5 de la carte."""
    from PIL import Image, ImageOps

    if not contenu:
        return None
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(contenu))).convert("RGB")
        return ImageReader(ImageOps.fit(image, (320, 400), centering=(0.5, 0.35)))
    except Exception:
        return None


def position(indice, verso=False):
    """Coin bas-gauche de la carte n° `indice` (0 à 9) sur la feuille."""
    ligne, colonne = divmod(indice, COLONNES)
    if verso:
        colonne = COLONNES - 1 - colonne
    x = MARGE_X + colonne * (LARGEUR + ECART_X)
    y = A4[1] - MARGE_Y - (ligne + 1) * HAUTEUR - ligne * ECART_Y
    return x, y


def _traits_de_coupe(c, x, y):
    """Petits repères aux quatre coins, à l'extérieur de la carte."""
    c.saveState()
    c.setStrokeColor(GRIS)
    c.setLineWidth(0.3)
    for cx, sx in ((x, -1), (x + LARGEUR, 1)):
        for cy, sy in ((y, -1), (y + HAUTEUR, 1)):
            c.line(cx + sx * 0.8 * mm, cy, cx + sx * 2.8 * mm, cy)
            c.line(cx, cy + sy * 0.3 * mm, cx, cy + sy * 1.4 * mm)
    c.restoreState()


def _recto(c, x, y, eleve, ctx):
    c.saveState()
    c.translate(x, y)
    theme, accent = ctx["theme"], ctx["accent"]
    c.setStrokeColor(TRAIT)
    c.setLineWidth(0.4)
    c.setFillColor(white)
    c.roundRect(0, 0, LARGEUR, HAUTEUR, 2.5 * mm, stroke=1, fill=1)

    # --- En-tête : logo, nom de l'école, ville et pays
    gauche = 3.5 * mm
    if ctx["logo"]:
        c.drawImage(ctx["logo"], 3 * mm, HAUTEUR - 13.2 * mm, 10.5 * mm, 10.5 * mm, preserveAspectRatio=True, mask="auto")
        gauche = 15 * mm
    largeur = LARGEUR - gauche - 3 * mm
    nom, taille = _ajuster(ctx["nom_ecole"], GRAS, 8.2, largeur, 5.6)
    c.setFillColor(theme)
    c.setFont(GRAS, taille)
    c.drawString(gauche, HAUTEUR - 7 * mm, nom)
    if ctx["sous_titre"]:
        sous, taille = _ajuster(ctx["sous_titre"], NORMAL, 5.8, largeur, 4.6)
        c.setFillColor(GRIS)
        c.setFont(NORMAL, taille)
        c.drawString(gauche, HAUTEUR - 10.6 * mm, sous)
    c.setStrokeColor(theme)
    c.setLineWidth(1)
    c.line(3 * mm, HAUTEUR - 14.6 * mm, LARGEUR - 3 * mm, HAUTEUR - 14.6 * mm)

    # --- Photo et matricule
    px, py, pl, ph = 3.5 * mm, 9.6 * mm, 20.4 * mm, 25.5 * mm
    if ctx["photos"].get(eleve.id):
        c.drawImage(ctx["photos"][eleve.id], px, py, pl, ph)
    else:
        c.setFillColor(HexColor("#F1F5F8"))
        c.rect(px, py, pl, ph, stroke=0, fill=1)
        c.setFillColor(GRIS)
        c.setFont(NORMAL, 5.5)
        c.drawCentredString(px + pl / 2, py + ph / 2 + 1, "Coller")
        c.drawCentredString(px + pl / 2, py + ph / 2 - 6, "la photo ici")
    c.setStrokeColor(TRAIT)
    c.setLineWidth(0.5)
    c.rect(px, py, pl, ph, stroke=1, fill=0)
    matricule, taille = _ajuster(f"Mat : {eleve.matricule}", GRAS, 6, pl + 2 * mm, 4.6)
    c.setFillColor(ENCRE)
    c.setFont(GRAS, taille)
    c.drawString(px, 6.3 * mm, matricule)

    # --- Titre et année scolaire
    droite = 26.5 * mm
    c.setFillColor(ENCRE)
    c.setFont(GRAS, 8.6)
    c.drawString(droite, HAUTEUR - 20.4 * mm, "CARTE D'ÉLÈVE")
    annee = _texte(ctx["annee"])
    largeur_annee = stringWidth(annee, GRAS, 7.6) + 4 * mm
    c.setFillColor(accent)
    c.roundRect(LARGEUR - 3 * mm - largeur_annee, HAUTEUR - 21.6 * mm, largeur_annee, 4.8 * mm, 1 * mm, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont(GRAS, 7.6)
    c.drawCentredString(LARGEUR - 3 * mm - largeur_annee / 2, HAUTEUR - 20.3 * mm, annee)

    # --- Identité
    largeur = LARGEUR - droite - 3 * mm
    nom, taille = _ajuster(eleve.nom_complet, GRAS, 9, largeur, 6)
    c.setFillColor(ENCRE)
    c.setFont(GRAS, taille)
    c.drawString(droite, HAUTEUR - 26.6 * mm, nom)
    feminin = eleve.sexe == "F"
    naissance = eleve.date_naissance.strftime("%d/%m/%Y") if eleve.date_naissance else "—"
    ne = f"{'Née' if feminin else 'Né'} le {naissance}" + (f" à {eleve.lieu_naissance}" if eleve.lieu_naissance else "")
    lignes = [(ne, largeur), (f"Nationalité : {eleve.nationalite or '—'}", largeur), (f"Classe : {eleve.classe.nom}", 26 * mm)]
    hauteur = HAUTEUR - 30.8 * mm
    for texte, place in lignes:
        texte, taille = _ajuster(texte, NORMAL, 6.6, place, 5)
        c.setFont(NORMAL, taille)
        c.drawString(droite, hauteur, texte)
        hauteur -= 3.6 * mm

    # --- Signature : imprimée (cachet + signature) ou laissée à la main
    signataire = ctx["signataire"]
    centre = LARGEUR - 17.5 * mm
    article = "La" if signataire.get("genre") == "F" else "Le"
    qualite, taille = _ajuster(f"{article} {signataire.get('qualite') or 'Directeur'}", GRAS, 5.6, 31 * mm, 4.4)
    c.setFont(GRAS, taille)
    c.drawCentredString(centre, 16.4 * mm, qualite)
    if ctx["signature"]:
        c.drawImage(ctx["signature"], centre - 13.5 * mm, 4.9 * mm, 27 * mm, 12.7 * mm, mask="auto")
    if signataire.get("nom"):
        nom, taille = _ajuster(signataire["nom"], NORMAL, 5, 31 * mm, 4)
        c.setFont(NORMAL, taille)
        c.drawCentredString(centre, 5.9 * mm, nom)

    # --- Bandeau du bas : devise de l'école
    c.setFillColor(theme)
    chemin = c.beginPath()
    chemin.roundRect(0, 0, LARGEUR, 9 * mm, 2.5 * mm)
    c.clipPath(chemin, stroke=0, fill=0)
    c.rect(0, 0, LARGEUR, 4.6 * mm, stroke=0, fill=1)
    devise, taille = _ajuster(ctx["devise"], ITALIQUE, 5.6, LARGEUR - 8 * mm, 4.4)
    c.setFillColor(white)
    c.setFont(ITALIQUE, taille)
    c.drawCentredString(LARGEUR / 2, 1.6 * mm, devise)
    c.restoreState()


def _verso(c, x, y, eleve, ctx):
    c.saveState()
    c.translate(x, y)
    theme = ctx["theme"]
    c.setStrokeColor(TRAIT)
    c.setLineWidth(0.4)
    c.setFillColor(white)
    c.roundRect(0, 0, LARGEUR, HAUTEUR, 2.5 * mm, stroke=1, fill=1)

    # --- Vérification
    verification = ctx["verifications"].get(eleve.id)
    if verification:
        c.drawImage(verification["image"], 4 * mm, 18.5 * mm, 22 * mm, 22 * mm)
        c.setFillColor(ENCRE)
        c.setFont(GRAS, 5.4)
        c.drawCentredString(15 * mm, 15.6 * mm, verification["code"])
        adresse, taille = _ajuster(verification["adresse"], NORMAL, 4.4, 25 * mm, 3.2)
        c.setFillColor(GRIS)
        c.setFont(NORMAL, 4.4)
        c.drawCentredString(15 * mm, 13.2 * mm, "Vérifier cette carte sur")
        c.setFont(NORMAL, taille)
        c.drawCentredString(15 * mm, 11.2 * mm, adresse)

    # --- Personne à prévenir
    droite, largeur = 30 * mm, LARGEUR - 33 * mm
    hauteur = HAUTEUR - 14 * mm
    c.setFillColor(theme)
    c.setFont(GRAS, 6.2)
    c.drawString(droite, hauteur, "En cas d'urgence, prévenir :")
    personne = eleve.personne_urgence or eleve.nom_pere or eleve.nom_mere or ""
    telephone = eleve.telephone_urgence or eleve.telephone_parent or ""
    c.setFillColor(ENCRE)
    if personne:
        hauteur -= 3.8 * mm
        texte, taille = _ajuster(personne, NORMAL, 6.6, largeur, 5)
        c.setFont(NORMAL, taille)
        c.drawString(droite, hauteur, texte)
    hauteur -= 4.2 * mm
    c.setFont(GRAS, 8)
    c.drawString(droite, hauteur, _texte(telephone) if telephone else "Tél. : ..............................")

    hauteur -= 5.4 * mm
    c.setFillColor(GRIS)
    c.setFont(NORMAL, 5)
    avis = ("Cette carte est strictement personnelle. Elle doit être présentée à toute demande. "
            f"En cas de perte, merci de la rapporter à l'école{' (' + ctx['ville'] + ')' if ctx['ville'] else ''}.")
    for ligne in _lignes(avis, NORMAL, 5, largeur, 5):
        c.drawString(droite, hauteur, ligne)
        hauteur -= 2.3 * mm

    # --- Rappel du titulaire : pour ne pas mélanger les cartes à la découpe
    titulaire, taille = _ajuster(f"{eleve.nom_complet} · {eleve.matricule}", GRAS, 5.6, LARGEUR - 8 * mm, 4.2)
    c.setFillColor(ENCRE)
    c.setFont(GRAS, taille)
    c.drawCentredString(LARGEUR / 2, 6.4 * mm, titulaire)

    # --- Bandeaux
    c.setFillColor(theme)
    chemin = c.beginPath()
    chemin.roundRect(0, 0, LARGEUR, HAUTEUR, 2.5 * mm)
    c.clipPath(chemin, stroke=0, fill=0)
    c.rect(0, HAUTEUR - 8 * mm, LARGEUR, 8 * mm, stroke=0, fill=1)
    c.rect(0, 0, LARGEUR, 4.6 * mm, stroke=0, fill=1)
    c.setFillColor(white)
    nom, taille = _ajuster(ctx["nom_ecole"], GRAS, 7.4, LARGEUR - 8 * mm, 5)
    c.setFont(GRAS, taille)
    c.drawCentredString(LARGEUR / 2, HAUTEUR - 5.4 * mm, nom)
    c.setFont(NORMAL, 5.4)
    c.drawCentredString(LARGEUR / 2, 1.6 * mm, _texte(f"Valable pour l'année scolaire {ctx['annee']}"))
    c.restoreState()


def planche_cartes(eleves, ecole, signataire, annee, verifications=None, signature_png=None, avec_verso=True):
    """PDF des cartes des élèves donnés (dans l'ordre reçu).

    `verifications` : {id de l'élève: {"code", "adresse", "qr" (PNG)}} ;
    `signature_png` : image « cachet + signature » à imprimer, ou None
    pour laisser la place à la signature manuscrite."""
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=A4)
    c.setTitle(_texte(f"Cartes d'élève — {ecole.nom}"))
    c.setAuthor(_texte(ecole.nom))

    verifs = {}
    for eleve_id, bloc in (verifications or {}).items():
        image = _image(bloc.get("qr"))
        if image:
            verifs[eleve_id] = {"image": image, "code": bloc["code"], "adresse": bloc["adresse"]}
    ctx = {
        "theme": HexColor(ecole.couleur_theme or "#0F5FA6"),
        "accent": HexColor(ecole.couleur_accent or "#00A99D"),
        "logo": _image(ecole.logo),
        "nom_ecole": ecole.nom_officiel,
        "sous_titre": " – ".join(v for v in (ecole.ville, ecole.pays) if v),
        "ville": ecole.ville or "",
        "devise": ecole.slogan or ecole.sigle or "",
        "annee": annee,
        "signataire": signataire or {},
        "signature": _image(signature_png),
        "photos": {e.id: _photo(e.photo) for e in eleves if e.photo_mime},
        "verifications": verifs,
    }

    for debut in range(0, len(eleves), CARTES_PAR_PAGE):
        page = eleves[debut:debut + CARTES_PAR_PAGE]
        for verso in ((False, True) if avec_verso else (False,)):
            for indice, eleve in enumerate(page):
                x, y = position(indice, verso)
                _traits_de_coupe(c, x, y)
                (_verso if verso else _recto)(c, x, y, eleve, ctx)
            c.setFillColor(GRIS)
            c.setFont(NORMAL, 6)
            c.drawCentredString(A4[0] / 2, 3.2 * mm, _texte(
                ("Verso" if verso else "Recto") + " — imprimer à 100 % (sans « ajuster à la page »)"
                + (", en recto verso, retournement sur le bord long" if avec_verso else "") + "."
            ))
            c.showPage()
    c.save()
    return tampon.getvalue()

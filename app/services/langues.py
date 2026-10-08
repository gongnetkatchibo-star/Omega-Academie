"""Bilingue français / arabe (oct. 2026).

Deux usages distincts :

1. L'interface. Chaque compte choisit sa langue (bouton FR / ع du haut de
   page). `traduire()` renvoie la traduction arabe d'un texte français
   s'il y en a une, sinon le texte français : on peut donc traduire
   l'application écran par écran, sans rien casser entre-temps. Le
   navigateur gère seul l'écriture de droite à gauche.

2. Les documents PDF (bulletin, certificat, attestation, reçu). Le moteur
   PDF ne sait ni lier les lettres arabes ni les ordonner de droite à
   gauche : `arabe_pdf()` prépare le texte (lettres liées, ordre
   d'affichage) avant de le lui passer. Contrainte : une ligne arabe d'un
   PDF ne doit pas passer à la ligne, sinon les lignes s'inversent. Les
   textes arabes des documents sont donc écrits en lignes courtes.

Les traductions sont à faire relire par un arabophone de l'école :
elles suivent l'arabe standard des documents scolaires, sans tenir compte
d'éventuels usages propres à un établissement."""

import re

from flask import has_request_context, request, session

LANGUES = {"fr": "Français", "ar": "العربية"}
LANGUE_PAR_DEFAUT = "fr"
CLE_REQUETE = "toumai.langue"


def langue_courante():
    if not has_request_context():
        return LANGUE_PAR_DEFAUT
    # Retenue pour la durée de la requête (sur la requête elle-même).
    if CLE_REQUETE in request.environ:
        return request.environ[CLE_REQUETE]
    from flask_login import current_user

    langue = None
    if current_user and current_user.is_authenticated:
        langue = getattr(current_user, "langue", None)
    langue = langue or session.get("langue") or LANGUE_PAR_DEFAUT
    langue = langue if langue in LANGUES else LANGUE_PAR_DEFAUT
    request.environ[CLE_REQUETE] = langue
    return langue


def traduire(texte, **valeurs):
    """Texte dans la langue de la personne connectée. Les {valeurs} sont
    remplacées après traduction : _("Bonjour, {prenom}", prenom="Amina")."""
    from markupsafe import Markup, escape

    texte = str(texte)
    if langue_courante() == "ar":
        from app.services.traductions_ar import INTERFACE
        texte = INTERFACE.get(texte, texte)
    if valeurs:
        texte = texte.format(**{cle: str(valeur) for cle, valeur in valeurs.items()})
    # Échappé (le texte peut contenir un nom saisi par un utilisateur), mais
    # l'apostrophe reste telle quelle : elle ne présente aucun risque entre
    # balises ni dans un attribut entre guillemets doubles.
    return Markup(str(escape(texte)).replace("&#39;", "'"))


# --- Documents PDF ------------------------------------------------------------

# ⟦…⟧ entoure ce qui doit rester de gauche à droite dans une phrase arabe :
# un nom en lettres latines, une date, un numéro.
MOTIF_LTR = re.compile(r"⟦(.*?)⟧")


def _afficher_arabe(morceau):
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(morceau))


def arabe_pdf(texte):
    """Prépare une ligne arabe pour le moteur PDF : lettres liées et
    morceaux dans l'ordre d'affichage de droite à gauche. Les passages
    entre ⟦ ⟧ gardent leur ordre de lecture (gauche à droite)."""
    if not texte:
        return ""
    morceaux = []
    position = 0
    for trouve in MOTIF_LTR.finditer(texte):
        if trouve.start() > position:
            morceaux.append(_afficher_arabe(texte[position:trouve.start()]))
        morceaux.append(trouve.group(1))
        position = trouve.end()
    if position < len(texte):
        morceaux.append(_afficher_arabe(texte[position:]))
    return "".join(reversed(morceaux))


def ltr(valeur):
    """Marque une valeur (nom, date, numéro) à garder de gauche à droite
    dans une phrase arabe passée à arabe_pdf()."""
    return f"⟦{valeur}⟧"


def traduction_document(texte):
    """Équivalent arabe d'un libellé de document (matière, mention,
    période, décision, titre du signataire…), ou None s'il n'y en a pas."""
    from app.services.traductions_ar import DOCUMENTS
    return DOCUMENTS.get((texte or "").strip())


def css_polices_arabes():
    """@font-face des polices arabes pour le moteur PDF (fichiers TTF
    livrés avec l'application)."""
    import os
    from flask import current_app

    dossier = os.path.join(current_app.static_folder, "fonts")
    normale = os.path.join(dossier, "noto-naskh-arabic-400.ttf")
    grasse = os.path.join(dossier, "noto-naskh-arabic-700.ttf")
    return (
        f'@font-face {{ font-family: "NaskhArabe"; src: url("{normale}"); }}'
        f'@font-face {{ font-family: "NaskhArabeGras"; src: url("{grasse}"); }}'
        '.ar { font-family: "NaskhArabe"; }'
        '.ar-gras, .ar b, .ar strong { font-family: "NaskhArabeGras"; }'
    )

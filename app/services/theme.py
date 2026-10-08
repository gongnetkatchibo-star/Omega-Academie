"""Couleurs de l'interface propres à chaque école (oct. 2026).

L'école choisit une couleur principale (menu, en-têtes, boutons) et une
couleur d'accent ; les nuances (foncée, pâle) en sont tirées. Sans choix,
l'interface garde les couleurs de la plateforme."""

import re

FORMAT = re.compile(r"^#[0-9a-fA-F]{6}$")
# Texte blanc posé sur la couleur : contraste minimal exigé (WCAG).
CONTRASTE_MIN_PRINCIPALE = 4.5
CONTRASTE_MIN_ACCENT = 3.0


def _rgb(couleur):
    return tuple(int(couleur[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def _luminance(couleur):
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in _rgb(couleur))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste_avec_blanc(couleur):
    return 1.05 / (_luminance(couleur) + 0.05)


def melanger(couleur, autre, part):
    """`part` de `autre` dans `couleur` (0 à 1)."""
    a, b = _rgb(couleur), _rgb(autre)
    return _hex(x + (y - x) * part for x, y in zip(a, b))


def verifier_couleur(saisie, nom, contraste_min):
    """(couleur normalisée ou None, message d'erreur ou None)."""
    saisie = (saisie or "").strip()
    if not saisie:
        return None, None
    if not FORMAT.match(saisie):
        return None, f"{nom} : format attendu #RRVVBB."
    if contraste_avec_blanc(saisie) < contraste_min:
        return None, f"{nom} trop claire : le texte blanc serait illisible. Choisis une teinte plus foncée."
    return saisie.upper(), None


def variables_css(ecole):
    """Variables CSS à redéfinir pour cette école, ou {} sans choix."""
    if ecole is None:
        return {}
    variables = {}
    if ecole.couleur_theme:
        principale = ecole.couleur_theme
        variables.update({
            "--navy": principale,
            "--navy-fonce": melanger(principale, "#000000", 0.18),
            "--carte": melanger(principale, "#FFFFFF", 0.92),
        })
    if ecole.couleur_accent:
        accent = ecole.couleur_accent
        variables.update({
            "--gold": accent,
            "--accent-vif": accent,
            "--accent-pale": melanger(accent, "#FFFFFF", 0.89),
            "--alerte-fond": melanger(accent, "#FFFFFF", 0.89),
        })
    return variables


def lire_couleurs_formulaire(formulaire):
    """Couleurs choisies dans un formulaire (paramètres de l'école ou
    console de la plateforme) : ({champ: couleur ou None}, erreurs)."""
    if formulaire.get("couleurs_plateforme") == "on":
        return {"couleur_theme": None, "couleur_accent": None}, []
    couleurs, erreurs = {}, []
    for champ, nom, minimum in (("couleur_theme", "Couleur principale", CONTRASTE_MIN_PRINCIPALE),
                                ("couleur_accent", "Couleur d'accent", CONTRASTE_MIN_ACCENT)):
        couleurs[champ], erreur = verifier_couleur(formulaire.get(champ), nom, minimum)
        if erreur:
            erreurs.append(erreur)
    return couleurs, erreurs

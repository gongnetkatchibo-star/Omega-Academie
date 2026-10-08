"""Numéros de téléphone mobiles, quel que soit le pays de l'école.

Un numéro saisi sans indicatif est lu comme un numéro du pays de l'école
(champ « Pays » de l'établissement). Un numéro saisi avec « + » ou « 00 »
est accepté tel quel, d'où qu'il soit : un parent installé à l'étranger
reste joignable.

Le Tchad garde exactement la règle d'origine (8 chiffres commençant par
6 ou 9, voir utils.normaliser_numero_tchad). Pour les autres pays, on
vérifie la longueur du numéro national quand elle est fixe."""

import re
import unicodedata

# Pays (minuscules, sans accents) → (indicatif, chiffres du numéro
# national ou None si variable, préfixe national à retirer devant).
PAYS = {
    "tchad": ("235", 8, ""),
    "cameroun": ("237", 9, ""),
    "centrafrique": ("236", 8, ""),
    "republique centrafricaine": ("236", 8, ""),
    "niger": ("227", 8, ""),
    "nigeria": ("234", 10, "0"),
    "soudan": ("249", 9, "0"),
    "congo": ("242", 9, ""),
    "republique du congo": ("242", 9, ""),
    "rdc": ("243", 9, "0"),
    "republique democratique du congo": ("243", 9, "0"),
    "gabon": ("241", None, ""),
    "guinee equatoriale": ("240", 9, ""),
    "senegal": ("221", 9, ""),
    "mali": ("223", 8, ""),
    "burkina faso": ("226", 8, ""),
    "cote d'ivoire": ("225", 10, ""),
    "benin": ("229", 10, ""),
    "togo": ("228", 8, ""),
    "guinee": ("224", 9, ""),
    "mauritanie": ("222", 8, ""),
    "france": ("33", 9, "0"),
}
PAYS_PAR_DEFAUT = "tchad"


def _cle_pays(pays):
    texte = unicodedata.normalize("NFKD", (pays or "").strip().lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c)).replace("’", "'")
    return texte if texte in PAYS else PAYS_PAR_DEFAUT


def indicatif(pays):
    return PAYS[_cle_pays(pays)][0]


def normaliser_numero(saisie, pays=None):
    """Numéro saisi → « +<indicatif><numéro> », ou None s'il n'est pas
    valable. `pays` : celui de l'école (Tchad si vide ou inconnu)."""
    from app.utils import normaliser_numero_tchad

    saisie = (saisie or "").strip()
    chiffres = re.sub(r"[^0-9]", "", saisie)
    if not chiffres:
        return None
    international = saisie.startswith("+") or chiffres.startswith("00")
    if chiffres.startswith("00"):
        chiffres = chiffres[2:]

    cle = _cle_pays(pays)
    code, longueur, prefixe = PAYS[cle]

    if international:
        if chiffres.startswith("235"):  # numéro tchadien : la règle d'origine
            return normaliser_numero_tchad(chiffres)
        return f"+{chiffres}" if 8 <= len(chiffres) <= 15 else None

    if cle == "tchad":
        return normaliser_numero_tchad(chiffres)

    national = chiffres
    if longueur and len(national) == len(code) + longueur and national.startswith(code):
        national = national[len(code):]  # indicatif tapé sans « + »
    if prefixe and national.startswith(prefixe) and (longueur is None or len(national) == longueur + len(prefixe)):
        national = national[len(prefixe):]
    if longueur is not None and len(national) != longueur:
        return None
    if longueur is None and not 6 <= len(national) <= 12:
        return None
    return f"+{code}{national}"


def numero_lisible(numero):
    """« +23566123456 » → « +235 66 12 34 56 » ; « +237690112233 » →
    « +237 690 11 22 33 ». Les chiffres sont groupés par deux, avec un
    groupe de trois en tête quand leur nombre est impair."""
    if not numero or not numero.startswith("+"):
        return numero or ""
    chiffres = numero[1:]
    code = next(
        (c for c in sorted({v[0] for v in PAYS.values()}, key=len, reverse=True) if chiffres.startswith(c)),
        None,
    )
    if code is None:
        return numero
    national = chiffres[len(code):]
    groupes = []
    if len(national) % 2:
        groupes.append(national[:3])
        national = national[3:]
    groupes += [national[i:i + 2] for i in range(0, len(national), 2)]
    return f"+{code} " + " ".join(groupes)

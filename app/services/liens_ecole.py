"""Lien propre à chaque école : https://…/e/<identifiant>.

L'identifiant est un mot court tiré du nom de l'école (« lycee-toumai »).
Arriver par ce lien montre le nom, le logo et les couleurs de l'école sur
les pages publiques (accueil, connexion, création de compte) : c'est
« l'école d'accueil » du visiteur, gardée dans sa session. Elle ne sert
qu'à l'affichage — les données restent cloisonnées par le compte
connecté, jamais par le lien."""

import re
import unicodedata

from flask import session, url_for
from flask_login import current_user

from app.extensions import db
from app.models.ecole import Ecole

LONGUEUR_MAX = 50
FORME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CLE_SESSION = "ecole_accueil"


def identifiant_depuis(texte):
    """« Lycée Toumaï de Pala » → « lycee-toumai-de-pala »."""
    sans_accents = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    mot = re.sub(r"[^a-z0-9]+", "-", sans_accents.lower()).strip("-")
    return mot[:LONGUEUR_MAX].strip("-")


def identifiant_valide(identifiant):
    return bool(identifiant) and 3 <= len(identifiant) <= LONGUEUR_MAX and bool(FORME.match(identifiant))


def _pris(identifiant, sauf_id=None):
    requete = db.session.query(Ecole.id).filter(Ecole.identifiant == identifiant)
    if sauf_id:
        requete = requete.filter(Ecole.id != sauf_id)
    return db.session.query(requete.exists()).scalar()


def identifiant_libre(souhaite, sauf_id=None):
    """L'identifiant souhaité, suivi de -2, -3… s'il est déjà pris."""
    base = identifiant_depuis(souhaite) or "ecole"
    if len(base) < 3:
        base = f"ecole-{base}"
    candidat, n = base, 1
    while _pris(candidat, sauf_id):
        n += 1
        suffixe = f"-{n}"
        candidat = base[:LONGUEUR_MAX - len(suffixe)].strip("-") + suffixe
    return candidat


def attribuer_identifiant(ecole):
    """Donne un identifiant à une école qui n'en a pas (sans enregistrer)."""
    if not ecole.identifiant:
        ecole.identifiant = identifiant_libre(ecole.nom, sauf_id=ecole.id)
    return ecole.identifiant


def attribuer_identifiants_manquants(app):
    """Au démarrage : les écoles créées avant les liens en reçoivent un."""
    try:
        ecoles = db.session.query(Ecole).filter(db.or_(Ecole.identifiant.is_(None), Ecole.identifiant == "")).all()
        for ecole in ecoles:
            ecole.identifiant = None
            attribuer_identifiant(ecole)
            db.session.flush()
        if ecoles:
            db.session.commit()
            app.logger.info("Lien attribué à %s école(s).", len(ecoles))
    except Exception:
        db.session.rollback()
        app.logger.exception("Attribution des liens d'école impossible.")


def ecole_par_identifiant(identifiant):
    """L'école active qui porte cet identifiant, ou None."""
    if not identifiant_valide(identifiant):
        return None
    return db.session.query(Ecole).filter(Ecole.identifiant == identifiant, Ecole.actif.is_(True)).first()


def retenir_ecole_d_accueil(ecole):
    if ecole is not None and ecole.actif and ecole.identifiant:
        session[CLE_SESSION] = ecole.id
    else:
        session.pop(CLE_SESSION, None)


def ecole_d_accueil():
    """L'école dont le visiteur (non connecté) a suivi le lien, ou None."""
    if current_user.is_authenticated:
        return None
    ecole_id = session.get(CLE_SESSION)
    if not ecole_id:
        return None
    ecole = db.session.get(Ecole, ecole_id)
    if ecole is None or not ecole.actif or not ecole.identifiant:
        session.pop(CLE_SESSION, None)
        return None
    return ecole


def lien_ecole(ecole, externe=True):
    """Adresse de la page de l'école, à donner aux familles et au personnel."""
    if ecole is None or not ecole.identifiant:
        return None
    return url_for("main.page_ecole", identifiant=ecole.identifiant, _external=externe)

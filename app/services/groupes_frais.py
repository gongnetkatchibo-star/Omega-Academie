"""Regroupement des classes qui partagent le même échéancier de frais.
Modifier les frais d'une classe du groupe met à jour automatiquement
toutes les autres classes du même groupe (même année scolaire) — pas de
ressaisie (demande de la direction, sept. 2026).

Niveaux (voir app/classes/routes.py NIVEAUX) :
1=CP1 2=CP2 3=CE1 4=CE2 5=CM1 6=CM2 7=6ème 8=5ème 9=4ème 10=3ème
"""

GROUPES_NIVEAUX = [
    set(range(1, 5)),   # CP1 à CE2
    set(range(5, 7)),   # CM1 à CM2
    set(range(7, 10)),  # 6ème à 4ème
    # 3ème (10) : pas de groupe, échéancier propre.
]


def groupe_du_niveau(niveau):
    for groupe in GROUPES_NIVEAUX:
        if niveau in groupe:
            return groupe
    return {niveau}  # seule dans son propre "groupe" (ex. 3ème)


def classes_du_meme_groupe(classe):
    """Toutes les classes (même année scolaire) qui doivent partager le
    même échéancier que `classe`, elle incluse."""
    from app.models.classe import Classe

    niveaux = groupe_du_niveau(classe.niveau)
    return Classe.query.filter(
        Classe.annee_scolaire == classe.annee_scolaire,
        Classe.niveau.in_(niveaux),
    ).all()


def appliquer_frais_au_groupe(classe, inscription, tranche1, tranche2):
    """Applique le même échéancier à `classe` et à toutes les classes de
    son groupe. Retourne la liste des classes mises à jour."""
    from app.extensions import db

    maj = []
    for c in classes_du_meme_groupe(classe):
        c.frais_inscription = inscription
        c.frais_tranche1 = tranche1
        c.frais_tranche2 = tranche2
        maj.append(c)
    db.session.commit()
    return maj

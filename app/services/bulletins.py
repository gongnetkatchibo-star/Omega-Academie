"""Calcul des bulletins d'une classe.

Tout est calculé en une passe pour la classe entière (notes,
coefficients, absences), puis chaque bulletin est lu dans ce résultat :
moyennes par matière, moyenne générale pondérée, rang, moyenne de
classe, mentions. Les moyennes restent sur le barème de la classe
(/10 au primaire, /20 au collège), celui que les familles connaissent."""

from collections import defaultdict

from app.models.absence import Absence
from app.models.bulletin import AppreciationBulletin, CoefficientMatiere
from app.models.eleve import Eleve
from app.models.note import Note
from app.services.moyennes import bareme_pour_classe, seuil_reussite_pour_classe

TRIMESTRES = ["T1", "T2", "T3"]
ANNUEL = "AN"
LIBELLES_PERIODE = {"T1": "1er trimestre", "T2": "2e trimestre", "T3": "3e trimestre", ANNUEL: "Année"}

# (part minimale du barème, mention)
MENTIONS = [(0.9, "Excellent"), (0.8, "Très bien"), (0.7, "Bien"), (0.6, "Assez bien"), (0.5, "Passable")]


def mention(moyenne, bareme):
    if moyenne is None:
        return ""
    part = moyenne / bareme
    return next((libelle for seuil, libelle in MENTIONS if part >= seuil), "Insuffisant")


def coefficients_de_la_classe(classe_id):
    return {c.matiere: c.coefficient for c in CoefficientMatiere.query.filter_by(classe_id=classe_id).all()}


def matieres_de_la_classe(classe):
    """Matières enseignées ou déjà notées dans la classe."""
    from app.models.enseignant import Affectation

    matieres = {a.matiere for a in Affectation.query.filter_by(classe_id=classe.id).all()}
    matieres |= {m for (m,) in Note.query.filter_by(classe_id=classe.id).with_entities(Note.matiere).distinct()}
    return sorted(matieres)


def _rangs(moyennes):
    """{id: rang}, ex æquo au même rang (15, 15, 12 -> 1, 1, 3)."""
    ordonnes = sorted(moyennes.items(), key=lambda paire: paire[1], reverse=True)
    rangs, precedent, rang = {}, None, 0
    for position, (cle, valeur) in enumerate(ordonnes, start=1):
        if valeur != precedent:
            rang, precedent = position, valeur
        rangs[cle] = rang
    return rangs


def _moyenne(valeurs):
    return round(sum(valeurs) / len(valeurs), 2) if valeurs else None


def _moyenne_ponderee(notes):
    """Moyenne de [(valeur, coefficient de l'évaluation), …]."""
    poids = sum(c for _, c in notes)
    return round(sum(v * c for v, c in notes) / poids, 2) if poids else None


def _periode(notes_par_eleve, coefficients, bareme):
    """Bulletins d'une période à partir de
    {eleve_id: {matiere: [(valeur, coefficient de l'évaluation), …]}}."""
    par_eleve, generales = {}, {}
    par_matiere = defaultdict(dict)  # {matiere: {eleve_id: moyenne}}

    for eleve_id, matieres in notes_par_eleve.items():
        lignes, total, poids = {}, 0.0, 0.0
        for matiere, valeurs in matieres.items():
            moyenne = _moyenne_ponderee(valeurs)
            if moyenne is None:
                continue
            coefficient = coefficients.get(matiere, 1)
            lignes[matiere] = {"moyenne": moyenne, "coefficient": coefficient}
            par_matiere[matiere][eleve_id] = moyenne
            total += moyenne * coefficient
            poids += coefficient
        par_eleve[eleve_id] = lignes
        if poids:
            generales[eleve_id] = round(total / poids, 2)

    rangs = _rangs(generales)
    stats_matiere = {
        matiere: {
            "classe": _moyenne(list(moyennes.values())),
            "min": min(moyennes.values()), "max": max(moyennes.values()),
            "rangs": _rangs(moyennes),
        }
        for matiere, moyennes in par_matiere.items()
    }

    bulletins = {}
    for eleve_id, lignes in par_eleve.items():
        detail = []
        for matiere in sorted(lignes):
            ligne, stats = lignes[matiere], stats_matiere[matiere]
            detail.append({
                "matiere": matiere, "moyenne": ligne["moyenne"], "coefficient": ligne["coefficient"],
                "points": round(ligne["moyenne"] * ligne["coefficient"], 2),
                "classe": stats["classe"], "min": stats["min"], "max": stats["max"],
                "rang": stats["rangs"][eleve_id], "mention": mention(ligne["moyenne"], bareme),
            })
        generale = generales.get(eleve_id)
        bulletins[eleve_id] = {
            "lignes": detail, "moyenne": generale, "rang": rangs.get(eleve_id),
            "mention": mention(generale, bareme),
            "total_coefficients": sum(l["coefficient"] for l in detail),
            "total_points": round(sum(l["points"] for l in detail), 2),
        }

    return {
        "bulletins": bulletins, "effectif_classe": len(generales),
        "moyenne_classe": _moyenne(list(generales.values())),
        "plus_forte": max(generales.values()) if generales else None,
        "plus_faible": min(generales.values()) if generales else None,
    }


def bulletins_de_la_classe(classe, periode, annee):
    """Tous les bulletins de la classe pour une période ("T1".."T3" ou "AN").
    Retourne {"bareme", "seuil", "periode", "eleves": {eleve_id: bulletin}, …}."""
    bareme = bareme_pour_classe(classe)
    seuil = seuil_reussite_pour_classe(classe)
    coefficients = coefficients_de_la_classe(classe.id)
    eleves_actifs = {e.id for e in Eleve.query.filter_by(classe_id=classe.id, actif=True).all()}

    par_trimestre = {t: defaultdict(lambda: defaultdict(list)) for t in TRIMESTRES}
    from app.models.evaluation import Evaluation
    poids_evaluation = {
        e.id: e.coefficient for e in Evaluation.query.filter_by(classe_id=classe.id, annee_scolaire=annee).all()
    }
    for n in Note.query.filter_by(classe_id=classe.id, annee_scolaire=annee).all():
        if n.eleve_id in eleves_actifs and n.trimestre in par_trimestre and n.bareme:
            par_trimestre[n.trimestre][n.eleve_id][n.matiere].append(
                (n.valeur * bareme / n.bareme, poids_evaluation.get(n.evaluation_id, 1) or 1)
            )

    absences = defaultdict(lambda: {"justifiees": 0, "non_justifiees": 0})
    for a in Absence.query.filter_by(classe_id=classe.id).all():
        absences[a.eleve_id]["justifiees" if a.justifiee else "non_justifiees"] += 1

    appreciations = {
        a.eleve_id: a.texte
        for a in AppreciationBulletin.query.filter_by(periode=periode, annee_scolaire=annee).all()
        if a.eleve_id in eleves_actifs
    }

    if periode in TRIMESTRES:
        resultat = _periode(par_trimestre[periode], coefficients, bareme)
    else:
        trimestres = {t: _periode(par_trimestre[t], coefficients, bareme) for t in TRIMESTRES}
        annuelles, bulletins = {}, {}
        for eleve_id in eleves_actifs:
            moyennes = {t: trimestres[t]["bulletins"].get(eleve_id, {}).get("moyenne") for t in TRIMESTRES}
            connues = [m for m in moyennes.values() if m is not None]
            if connues:
                annuelles[eleve_id] = _moyenne(connues)
                bulletins[eleve_id] = {"trimestres": moyennes}
        rangs = _rangs(annuelles)
        for eleve_id, bulletin in bulletins.items():
            moyenne = annuelles[eleve_id]
            bulletin.update({
                "lignes": [], "moyenne": moyenne, "rang": rangs[eleve_id], "mention": mention(moyenne, bareme),
                "decision": "Admis en classe supérieure" if moyenne >= seuil else "Redouble",
            })
        resultat = {
            "bulletins": bulletins, "effectif_classe": len(annuelles),
            "moyenne_classe": _moyenne(list(annuelles.values())),
            "plus_forte": max(annuelles.values()) if annuelles else None,
            "plus_faible": min(annuelles.values()) if annuelles else None,
        }

    for eleve_id, bulletin in resultat["bulletins"].items():
        bulletin["absences"] = dict(absences[eleve_id])
        bulletin["appreciation"] = appreciations.get(eleve_id, "")

    resultat.update({
        "bareme": bareme, "seuil": seuil, "periode": periode, "libelle_periode": LIBELLES_PERIODE[periode],
        "annee": annee,
    })
    return resultat

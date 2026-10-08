from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.eleve import Eleve
from app.models.note import Note
from app.notes import notes_bp
from app.utils import roles_required
from app.services.moyennes import bareme_pour_classe
from app.models.bulletin import AppreciationBulletin, CoefficientMatiere
from app.models.evaluation import Evaluation, TYPES_EVALUATION, LIBELLES_TYPE
from app.services.bulletins import bulletins_de_la_classe, matieres_de_la_classe, ANNUEL, LIBELLES_PERIODE
from app.services.periodes import periodes as periodes_de_l_ecole, periodes_et_annee

from app.services.cycles import cycle_du_role, classe_dans_le_cycle
from app.services.temps import maintenant

ROLES_SUPERVISION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"]


@notes_bp.route("/")
@login_required
def index():
    """Entrée du menu « Notes » : les classes de l'année, avec la saisie
    pour l'enseignant et les bulletins pour la supervision."""
    from app.services.permissions import role_a_acces
    from app.services.cycles import filtrer_par_cycle

    supervision = current_user.role == "developpeur" or role_a_acces(current_user.role, "notes_supervision", ROLES_SUPERVISION)
    if current_user.role == "enseignant":
        profil = current_user.profil_enseignant
        ids = {a.classe_id for a in profil.affectations} if profil else set()
        classes = [c for c in Classe.query.order_by(Classe.niveau, Classe.nom).all() if c.id in ids]
    elif supervision:
        classes = filtrer_par_cycle(
            Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau, Classe.nom).all(),
            cycle_du_role(current_user.role),
        )
    else:
        abort(403)
    return render_template("notes/index.html", classes=classes, supervision=supervision)


def _matieres_enseignees(classe_id):
    """Matières que le compte enseigne dans la classe (liste vide sinon)."""
    profil = current_user.profil_enseignant if current_user.role == "enseignant" else None
    if profil is None:
        return None, []
    return profil, sorted({a.matiere for a in profil.affectations if a.classe_id == classe_id})


@notes_bp.route("/classe/<int:classe_id>", methods=["GET", "POST"])
@login_required
@roles_required("enseignant")
def saisie(classe_id):
    """Évaluations de la classe dans les matières de l'enseignant, et
    création d'une nouvelle évaluation."""
    from datetime import datetime

    classe_obj = db.get_or_404(Classe, classe_id)
    profil, matieres = _matieres_enseignees(classe_id)
    if current_user.role == "enseignant" and not matieres:
        flash("Vous n'enseignez pas dans cette classe.", "error")
        return redirect(url_for("classes.liste"))

    annee = classe_obj.annee_scolaire
    if request.method == "POST" and profil is not None:
        matiere = request.form.get("matiere")
        trimestre = request.form.get("trimestre")
        titre = request.form.get("titre", "").strip()[:120]
        type_evaluation = request.form.get("type")
        coefficient = request.form.get("coefficient", type=float)
        try:
            date_evaluation = datetime.strptime(request.form.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            date_evaluation = None

        if matiere not in matieres or trimestre not in periodes_de_l_ecole():
            flash("Merci de choisir une matière que vous enseignez et une période valide.", "error")
        elif not titre or type_evaluation not in TYPES_EVALUATION or date_evaluation is None:
            flash("Le titre, le type et la date de l'évaluation sont obligatoires.", "error")
        elif coefficient is None or not 0 < coefficient <= 10:
            flash("Le coefficient doit être compris entre 0,5 et 10.", "error")
        else:
            evaluation = Evaluation(
                classe_id=classe_id, matiere=matiere, trimestre=trimestre, annee_scolaire=annee, titre=titre,
                type=type_evaluation, date=date_evaluation, coefficient=coefficient, enseignant_id=profil.id,
            )
            db.session.add(evaluation)
            db.session.commit()
            return redirect(url_for("notes.evaluation", evaluation_id=evaluation.id))

    evaluations = []
    if matieres:
        evaluations = (
            Evaluation.query.filter(Evaluation.classe_id == classe_id, Evaluation.annee_scolaire == annee,
                                    Evaluation.matiere.in_(matieres))
            .order_by(Evaluation.trimestre, Evaluation.matiere, Evaluation.date).all()
        )
    effectif = Eleve.query.filter_by(classe_id=classe_id, actif=True).count()
    return render_template(
        "notes/saisie.html", classe=classe_obj, matieres=matieres, trimestres=periodes_de_l_ecole(), libelles=LIBELLES_PERIODE, evaluations=evaluations,
        types=TYPES_EVALUATION, libelles_type=LIBELLES_TYPE, effectif=effectif, bareme=bareme_pour_classe(classe_obj),
        aujourd_hui=maintenant().date().isoformat(),
    )


def _evaluation_de_l_enseignant(evaluation_id):
    evaluation = db.get_or_404(Evaluation, evaluation_id)
    profil, matieres = _matieres_enseignees(evaluation.classe_id)
    if profil is None or evaluation.matiere not in matieres:
        abort(403)
    return evaluation, profil


@notes_bp.route("/evaluation/<int:evaluation_id>", methods=["GET", "POST"])
@login_required
@roles_required("enseignant")
def evaluation(evaluation_id):
    """Saisie des notes d'une évaluation. Ressaisir corrige la note de
    cette évaluation, sans jamais en créer une deuxième."""
    evaluation, profil = _evaluation_de_l_enseignant(evaluation_id)
    classe_obj = evaluation.classe
    bareme = bareme_pour_classe(classe_obj)
    eleves = Eleve.query.filter_by(classe_id=classe_obj.id, actif=True).order_by(Eleve.nom_complet).all()
    existantes = {n.eleve_id: n for n in Note.query.filter_by(evaluation_id=evaluation.id).all()}

    if request.method == "POST":
        nb_saisies, hors_bareme = 0, 0
        for eleve in eleves:
            valeur_str = request.form.get(f"note_{eleve.id}", "").strip().replace(",", ".")
            note = existantes.get(eleve.id)
            if valeur_str == "":
                if note:  # case vidée : la note est retirée (élève absent à l'évaluation)
                    db.session.delete(note)
                continue
            try:
                valeur = float(valeur_str)
            except ValueError:
                continue
            if not 0 <= valeur <= bareme:
                hors_bareme += 1
                continue
            if note:
                note.valeur = valeur
                note.bareme = bareme
            else:
                db.session.add(Note(
                    eleve_id=eleve.id, classe_id=classe_obj.id, matiere=evaluation.matiere, valeur=valeur,
                    bareme=bareme, trimestre=evaluation.trimestre, annee_scolaire=evaluation.annee_scolaire,
                    enseignant_id=profil.id, evaluation_id=evaluation.id,
                ))
            nb_saisies += 1
        db.session.commit()
        flash(f"{nb_saisies} note(s) enregistrée(s).", "info")
        if hors_bareme:
            flash(f"{hors_bareme} note(s) ignorée(s) : elles doivent être comprises entre 0 et {bareme}.", "error")
        return redirect(url_for("notes.evaluation", evaluation_id=evaluation.id))

    return render_template(
        "notes/evaluation.html", evaluation=evaluation, classe=classe_obj, eleves=eleves, bareme=bareme,
        notes={eleve_id: n.valeur for eleve_id, n in existantes.items()},
    )


@notes_bp.route("/evaluation/<int:evaluation_id>/supprimer", methods=["POST"])
@login_required
@roles_required("enseignant")
def supprimer_evaluation(evaluation_id):
    evaluation, _ = _evaluation_de_l_enseignant(evaluation_id)
    classe_id = evaluation.classe_id
    db.session.delete(evaluation)  # ses notes partent avec elle
    db.session.commit()
    flash("Évaluation supprimée, avec ses notes.", "info")
    return redirect(url_for("notes.saisie", classe_id=classe_id))


def _acces_bulletin(eleve):
    """Accès basé sur la relation, pas seulement sur le rôle : un parent
    lié à l'élève et l'élève lui-même voient le bulletin, en plus des
    enseignants et de la supervision. Retourne True si le compte peut
    aussi rédiger l'appréciation du conseil."""
    from app.services.permissions import role_a_acces

    est_lie_comme_parent = current_user in eleve.parents
    est_soi_meme = current_user.role == "eleve" and eleve.user_id == current_user.id
    supervision = current_user.role == "developpeur" or role_a_acces(current_user.role, "notes_supervision", ROLES_SUPERVISION)
    # Un enseignant voit les bulletins des classes où il enseigne, pas ceux de toute l'école.
    profil = current_user.profil_enseignant if current_user.role == "enseignant" else None
    enseigne_dans_la_classe = bool(profil and any(a.classe_id == eleve.classe_id for a in profil.affectations))
    if not (supervision or enseigne_dans_la_classe or est_lie_comme_parent or est_soi_meme):
        abort(403)
    cycle = cycle_du_role(current_user.role)
    if cycle and not classe_dans_le_cycle(eleve.classe, cycle):
        abort(403)
    return supervision


def _periode_demandee():
    valables = periodes_et_annee()
    periode = request.values.get("trimestre", valables[0])
    return periode if periode in valables else valables[0]


def _supervision_de_la_classe(classe_id):
    from app.services.permissions import role_a_acces

    classe = db.get_or_404(Classe, classe_id)
    if current_user.role != "developpeur" and not role_a_acces(current_user.role, "notes_supervision", ROLES_SUPERVISION):
        abort(403)
    if not classe_dans_le_cycle(classe, cycle_du_role(current_user.role)):
        abort(403)
    return classe


def _pdf_bulletins(classe, periode, eleves, nom_fichier):
    from flask import make_response
    from app.utils import html_vers_pdf
    from app.services.documents_officiels import contexte_entete_officiel

    calcul = bulletins_de_la_classe(classe, periode, classe.annee_scolaire)
    pages = [(e, calcul["bulletins"][e.id]) for e in eleves if e.id in calcul["bulletins"]]
    if not pages:
        return None
    from app.services.verification import emettre_bulletin, bloc_verification
    verifs = {e.id: bloc_verification(emettre_bulletin(e, classe, calcul, b)) for e, b in pages}
    db.session.commit()
    html = render_template(
        "notes/bulletin_pdf.html", classe=classe, calcul=calcul, pages=pages, verifs=verifs, **contexte_entete_officiel(),
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename={nom_fichier}.pdf"
    return reponse


@notes_bp.route("/bulletin/<int:eleve_id>")
@login_required
def bulletin(eleve_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    peut_apprecier = _acces_bulletin(eleve)
    periode = _periode_demandee()
    calcul = bulletins_de_la_classe(eleve.classe, periode, eleve.classe.annee_scolaire)
    return render_template(
        "notes/bulletin.html", eleve=eleve, periode=periode, periodes=periodes_et_annee(), libelles=LIBELLES_PERIODE,
        calcul=calcul, bulletin=calcul["bulletins"].get(eleve.id), peut_apprecier=peut_apprecier,
    )


@notes_bp.route("/bulletin/<int:eleve_id>/pdf")
@login_required
def bulletin_pdf(eleve_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    _acces_bulletin(eleve)
    periode = _periode_demandee()
    reponse = _pdf_bulletins(eleve.classe, periode, [eleve], f"bulletin_{eleve.matricule}_{periode}")
    if reponse is None:
        flash("Aucune note enregistrée pour cette période.", "error")
        return redirect(url_for("notes.bulletin", eleve_id=eleve.id, trimestre=periode))
    return reponse


@notes_bp.route("/bulletin/<int:eleve_id>/appreciation", methods=["POST"])
@login_required
def appreciation(eleve_id):
    eleve = db.get_or_404(Eleve, eleve_id)
    if not _acces_bulletin(eleve):
        abort(403)
    periode = _periode_demandee()
    annee = eleve.classe.annee_scolaire
    texte = request.form.get("appreciation", "").strip()[:400]
    existante = AppreciationBulletin.query.filter_by(eleve_id=eleve.id, periode=periode, annee_scolaire=annee).first()
    if not texte:
        if existante:
            db.session.delete(existante)
    elif existante:
        existante.texte = texte
    else:
        db.session.add(AppreciationBulletin(eleve_id=eleve.id, periode=periode, annee_scolaire=annee, texte=texte))
    db.session.commit()
    flash("Appréciation enregistrée.", "info")
    return redirect(url_for("notes.bulletin", eleve_id=eleve.id, trimestre=periode))


@notes_bp.route("/classe/<int:classe_id>/coefficients", methods=["GET", "POST"])
@login_required
def coefficients(classe_id):
    classe = _supervision_de_la_classe(classe_id)
    matieres = matieres_de_la_classe(classe)
    actuels = {c.matiere: c for c in CoefficientMatiere.query.filter_by(classe_id=classe.id).all()}

    if request.method == "POST":
        for position, matiere in enumerate(matieres):
            valeur = request.form.get(f"coefficient_{position}", type=float)
            if valeur is None or not 0 < valeur <= 20:
                continue
            if matiere in actuels:
                actuels[matiere].coefficient = valeur
            else:
                db.session.add(CoefficientMatiere(classe_id=classe.id, matiere=matiere, coefficient=valeur))
        db.session.commit()
        flash("Coefficients enregistrés.", "info")
        return redirect(url_for("notes.coefficients", classe_id=classe.id))

    return render_template(
        "notes/coefficients.html", classe=classe, matieres=matieres,
        coefficients={m: (actuels[m].coefficient if m in actuels else 1) for m in matieres},
    )


@notes_bp.route("/classe/<int:classe_id>/bulletins")
@login_required
def bulletins_classe(classe_id):
    """Tableau de la classe pour une période : moyenne, rang et mention
    de chaque élève, avec le lien vers son bulletin."""
    classe = _supervision_de_la_classe(classe_id)
    periode = _periode_demandee()
    calcul = bulletins_de_la_classe(classe, periode, classe.annee_scolaire)
    eleves = Eleve.query.filter_by(classe_id=classe.id, actif=True).order_by(Eleve.nom_complet).all()
    lignes = sorted(
        ((e, calcul["bulletins"].get(e.id)) for e in eleves),
        key=lambda paire: (paire[1] is None, paire[1]["rang"] if paire[1] else 0, paire[0].nom_complet),
    )
    return render_template(
        "notes/bulletins_classe.html", classe=classe, periode=periode, periodes=periodes_et_annee(),
        libelles=LIBELLES_PERIODE, calcul=calcul, lignes=lignes,
    )


@notes_bp.route("/classe/<int:classe_id>/bulletins/pdf")
@login_required
def bulletins_classe_pdf(classe_id):
    classe = _supervision_de_la_classe(classe_id)
    periode = _periode_demandee()
    eleves = Eleve.query.filter_by(classe_id=classe.id, actif=True).order_by(Eleve.nom_complet).all()
    reponse = _pdf_bulletins(classe, periode, eleves, f"bulletins_{classe.nom}_{periode}")
    if reponse is None:
        flash("Aucune note enregistrée pour cette période.", "error")
        return redirect(url_for("notes.bulletins_classe", classe_id=classe.id, trimestre=periode))
    return reponse

from datetime import datetime

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.eleve import Eleve
from app.models.test_niveau import TestNiveau, DECISIONS, LIBELLES_DECISION
from app.tests_niveau import tests_niveau_bp
from app.utils import roles_required
from app.services.cycles import cycle_du_role, classe_dans_le_cycle, filtrer_par_cycle

# Même périmètre que la gestion des élèves — le module remplace le suivi
# papier/Excel des tests d'admission (document complémentaire, sept. 2026).
ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]


@tests_niveau_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module="tests_niveau")
def liste():
    tests = TestNiveau.query.order_by(TestNiveau.date_test.desc()).all()
    cycle = cycle_du_role(current_user.role)
    if cycle:
        tests = [t for t in tests if classe_dans_le_cycle(t.classe_demandee, cycle)]
    return render_template("tests_niveau/liste.html", tests=tests)


@tests_niveau_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="tests_niveau")
def nouveau():
    cycle = cycle_du_role(current_user.role)
    classes = filtrer_par_cycle(Classe.query.order_by(Classe.niveau).all(), cycle)

    if request.method == "POST":
        nom_candidat = request.form.get("nom_candidat", "").strip()
        date_naissance_str = request.form.get("date_naissance_candidat", "")
        classe_demandee_id = request.form.get("classe_demandee_id", type=int)
        date_test_str = request.form.get("date_test", "")

        classe_demandee = Classe.query.get(classe_demandee_id) if classe_demandee_id else None

        if not nom_candidat or not classe_demandee:
            flash("Merci de renseigner au moins le nom du candidat et la classe demandée.", "error")
            return render_template("tests_niveau/nouveau.html", classes=classes)

        if cycle and not classe_dans_le_cycle(classe_demandee, cycle):
            flash("Cette classe ne fait pas partie de ton cycle de supervision.", "error")
            return render_template("tests_niveau/nouveau.html", classes=classes)

        try:
            date_naissance = datetime.strptime(date_naissance_str, "%Y-%m-%d").date() if date_naissance_str else None
        except ValueError:
            date_naissance = None
        try:
            date_test = datetime.strptime(date_test_str, "%Y-%m-%d").date() if date_test_str else datetime.utcnow().date()
        except ValueError:
            date_test = datetime.utcnow().date()

        test = TestNiveau(
            nom_candidat=nom_candidat, date_naissance_candidat=date_naissance,
            sexe_candidat=request.form.get("sexe_candidat") if request.form.get("sexe_candidat") in ("M", "F") else None,
            classe_demandee_id=classe_demandee.id, date_test=date_test,
            evaluateur_id=current_user.id,
        )
        db.session.add(test)
        db.session.commit()
        flash(f"Test de niveau créé pour {nom_candidat}.", "info")
        return redirect(url_for("tests_niveau.liste"))

    return render_template("tests_niveau/nouveau.html", classes=classes)


@tests_niveau_bp.route("/<int:test_id>/decision", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="tests_niveau")
def decision(test_id):
    test = TestNiveau.query.get_or_404(test_id)
    note = request.form.get("note_obtenue", type=float)
    decision_val = request.form.get("decision")
    observation = request.form.get("observation", "").strip()

    if decision_val not in DECISIONS:
        flash("Décision invalide.", "error")
    else:
        test.note_obtenue = note
        test.decision = decision_val
        test.observation = observation
        db.session.commit()
        flash(f"Décision enregistrée : {LIBELLES_DECISION[decision_val]}.", "info")
    return redirect(url_for("tests_niveau.liste"))

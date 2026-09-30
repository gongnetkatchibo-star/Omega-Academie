from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.eleve import Eleve
from app.models.test_niveau import TestNiveau, DECISIONS, LIBELLES_DECISION
from app.tests_niveau import tests_niveau_bp
from app.utils import roles_required
from app.services.cycles import cycle_du_role, classe_dans_le_cycle, filtrer_par_cycle
from app.services.admission import bareme, decision_pour_note, inscrire_candidat_admis

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
    return render_template("tests_niveau/liste.html", tests=tests, bareme=bareme, libelles=LIBELLES_DECISION)


@tests_niveau_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="tests_niveau")
def nouveau():
    cycle = cycle_du_role(current_user.role)
    classes = filtrer_par_cycle(
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau).all(), cycle
    )

    if request.method == "POST":
        nom_candidat = request.form.get("nom_candidat", "").strip()
        date_naissance_str = request.form.get("date_naissance_candidat", "")
        classe_demandee_id = request.form.get("classe_demandee_id", type=int)
        date_test_str = request.form.get("date_test", "")

        classe_demandee = next((c for c in classes if c.id == classe_demandee_id), None)

        if not nom_candidat or not classe_demandee:
            flash("Merci de renseigner au moins le nom du candidat et la classe demandée.", "error")
            return render_template("tests_niveau/nouveau.html", classes=classes, bareme=bareme)

        if cycle and not classe_dans_le_cycle(classe_demandee, cycle):
            flash("Cette classe ne fait pas partie de ton cycle de supervision.", "error")
            return render_template("tests_niveau/nouveau.html", classes=classes, bareme=bareme)

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
            telephone_parent=request.form.get("telephone_parent", "").strip() or None,
            classe_demandee_id=classe_demandee.id, date_test=date_test,
            evaluateur_id=current_user.id,
        )
        db.session.add(test)
        db.session.commit()
        flash(f"Test de niveau créé pour {nom_candidat}.", "info")
        return redirect(url_for("tests_niveau.liste"))

    return render_template("tests_niveau/nouveau.html", classes=classes, bareme=bareme)


@tests_niveau_bp.route("/<int:test_id>/decision", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="tests_niveau")
def decision(test_id):
    """La note seule décide : admis au-dessus du seuil du cycle, refusé
    en dessous. Un candidat admis est inscrit tout de suite dans la
    classe demandée."""
    test = TestNiveau.query.get_or_404(test_id)
    if not classe_dans_le_cycle(test.classe_demandee, cycle_du_role(current_user.role)):
        abort(403)

    if test.eleve_id:
        flash(f"{test.nom_candidat} est déjà inscrit (matricule {test.eleve.matricule}) : la note ne peut plus être modifiée.", "error")
        return redirect(url_for("tests_niveau.liste"))

    note_max, seuil = bareme(test.classe_demandee)
    note = request.form.get("note_obtenue", type=float)
    if note is None or not 0 <= note <= note_max:
        flash(f"Note invalide : elle doit être comprise entre 0 et {note_max:g}.", "error")
        return redirect(url_for("tests_niveau.liste"))

    test.note_obtenue = note
    test.decision = decision_pour_note(note, test.classe_demandee)
    test.observation = request.form.get("observation", "").strip() or test.observation

    if test.decision == "refuse":
        db.session.commit()
        flash(f"{test.nom_candidat} : {note:g}/{note_max:g} — non admis (seuil {seuil:g}).", "info")
        return redirect(url_for("tests_niveau.liste"))

    eleve = inscrire_candidat_admis(test)
    db.session.commit()
    if eleve:
        flash(
            f"{test.nom_candidat} : {note:g}/{note_max:g} — admis et inscrit en {test.classe_demandee.nom}. "
            f"Matricule : {eleve.matricule}.",
            "info",
        )
    else:
        flash(
            f"{test.nom_candidat} : {note:g}/{note_max:g} — admis. La classe demandée n'est pas de l'année "
            f"en cours : inscription à faire dans le module Élèves.",
            "warning",
        )
    return redirect(url_for("tests_niveau.liste"))

"""Calendrier scolaire : rentrée, vacances, jours fériés, compositions,
réunions. Tout le monde le consulte ; le secrétariat et la direction le
tiennent à jour."""

from itertools import groupby

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.calendrier import calendrier_bp
from app.models.calendrier import EvenementCalendrier, TYPES_EVENEMENT, LIBELLES_EVENEMENT
from app.services.permissions import role_a_acces
from app.services.suivi_eleve import DIRECTION, date_du_formulaire
from app.services.temps import aujourd_hui

ROLES_GESTION = ["secretaire"] + DIRECTION
MODULE = "calendrier"


def peut_modifier():
    return role_a_acces(current_user.role, MODULE, ROLES_GESTION)


def voit_tout():
    """Le personnel voit aussi les dates internes (conseils de classe…)."""
    return current_user.role not in ("parent", "eleve")


def evenements_visibles():
    requete = EvenementCalendrier.query
    if not voit_tout():
        requete = requete.filter_by(visible_familles=True)
    return requete


def prochains_evenements(nombre=4):
    """Pour le tableau de bord : les prochaines dates (en cours comprises)."""
    return (
        evenements_visibles().filter(EvenementCalendrier.date_fin >= aujourd_hui())
        .order_by(EvenementCalendrier.date_debut).limit(nombre).all()
    )


def _debut_annee_scolaire(jour):
    from datetime import date
    return date(jour.year if jour.month >= 9 else jour.year - 1, 8, 1)


@calendrier_bp.route("/")
@login_required
def index():
    jour = aujourd_hui()
    evenements = (
        evenements_visibles().filter(EvenementCalendrier.date_fin >= _debut_annee_scolaire(jour))
        .order_by(EvenementCalendrier.date_debut).all()
    )
    a_venir = [e for e in evenements if e.date_fin >= jour]
    passes = [e for e in evenements if e.date_fin < jour]
    par_mois = [
        (groupe_liste[0].date_debut.replace(day=1), groupe_liste)
        for groupe_liste in (
            list(g) for _, g in groupby(a_venir, key=lambda e: (e.date_debut.year, e.date_debut.month))
        )
    ]
    return render_template(
        "calendrier/index.html", par_mois=par_mois, passes=list(reversed(passes)), types=TYPES_EVENEMENT,
        peut_modifier=peut_modifier(), aujourd_hui=jour, evenement=None,
    )


def _lire_formulaire(evenement):
    titre = request.form.get("titre", "").strip()
    type_evenement = request.form.get("type", "")
    debut = date_du_formulaire("date_debut", facultative=True)
    fin = date_du_formulaire("date_fin", facultative=True) or debut
    if not titre or type_evenement not in LIBELLES_EVENEMENT or not debut:
        return "Indique le titre, le type et la date de début."
    if fin < debut:
        return "La date de fin ne peut pas précéder la date de début."
    evenement.titre = titre[:150]
    evenement.type = type_evenement
    evenement.date_debut, evenement.date_fin = debut, fin
    evenement.description = request.form.get("description", "").strip()[:500] or None
    evenement.visible_familles = request.form.get("interne") != "on"
    return None


@calendrier_bp.route("/nouveau", methods=["POST"])
@login_required
def nouveau():
    if not peut_modifier():
        abort(403)
    evenement = EvenementCalendrier()
    erreur = _lire_formulaire(evenement)
    if erreur:
        flash(erreur, "error")
    else:
        db.session.add(evenement)
        db.session.commit()
        flash("Date ajoutée au calendrier.", "info")
    return redirect(url_for("calendrier.index"))


@calendrier_bp.route("/<int:evenement_id>/modifier", methods=["GET", "POST"])
@login_required
def modifier(evenement_id):
    if not peut_modifier():
        abort(403)
    evenement = db.get_or_404(EvenementCalendrier, evenement_id)
    if request.method == "POST":
        erreur = _lire_formulaire(evenement)
        if erreur:
            db.session.rollback()
            flash(erreur, "error")
        else:
            db.session.commit()
            flash("Calendrier mis à jour.", "info")
            return redirect(url_for("calendrier.index"))
    return render_template("calendrier/modifier.html", evenement=evenement, types=TYPES_EVENEMENT)


@calendrier_bp.route("/<int:evenement_id>/supprimer", methods=["POST"])
@login_required
def supprimer(evenement_id):
    if not peut_modifier():
        abort(403)
    evenement = db.get_or_404(EvenementCalendrier, evenement_id)
    db.session.delete(evenement)
    db.session.commit()
    flash("Date retirée du calendrier.", "info")
    return redirect(url_for("calendrier.index"))

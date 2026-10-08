"""Retards et discipline : registre des retards, avertissements, blâmes,
convocations et exclusions, avec information des parents."""

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.discipline import discipline_bp
from app.models.classe import Classe
from app.models.discipline import Incident, TYPES_INCIDENT, LIBELLES_INCIDENT
from app.models.eleve import Eleve
from app.services.cycles import cycle_du_role, filtrer_par_cycle
from app.services.pagination import paginer
from app.services.permissions import role_a_acces
from app.services.suivi_eleve import DIRECTION, classes_de_l_enseignant, supervise, date_du_formulaire

ROLES_SUPERVISION = DIRECTION + ["responsable_pedagogique", "secretaire"]
MODULE = "discipline"


def _classes_visibles():
    """Classes de l'année dont le compte peut tenir le registre."""
    classes = (
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante())
        .order_by(Classe.niveau, Classe.nom).all()
    )
    if current_user.role == "developpeur" or role_a_acces(current_user.role, MODULE, ROLES_SUPERVISION):
        return filtrer_par_cycle(classes, cycle_du_role(current_user.role))
    mes_classes = classes_de_l_enseignant()
    return [c for c in classes if c.id in mes_classes]


def _peut_gerer(incident):
    return incident.auteur_id == current_user.id or supervise(incident.classe, MODULE, ROLES_SUPERVISION)


@discipline_bp.route("/")
@login_required
def registre():
    classes = _classes_visibles()
    if not classes and current_user.role not in ("enseignant", "developpeur") \
            and not role_a_acces(current_user.role, MODULE, ROLES_SUPERVISION):
        abort(403)
    ids = [c.id for c in classes]
    classe_id = request.args.get("classe_id", type=int)
    type_incident = request.args.get("type", "")
    requete = Incident.query.options(
        db.joinedload(Incident.eleve), db.joinedload(Incident.classe),
    ).filter(Incident.classe_id.in_(ids))
    if classe_id in ids:
        requete = requete.filter_by(classe_id=classe_id)
    if type_incident in LIBELLES_INCIDENT:
        requete = requete.filter_by(type=type_incident)
    page = paginer(requete.order_by(Incident.date.desc(), Incident.id.desc()))
    return render_template(
        "discipline/registre.html", page=page, classes=classes, classe_id=classe_id,
        type_incident=type_incident, types=TYPES_INCIDENT,
    )


@discipline_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
def nouveau():
    classes = _classes_visibles()
    if not classes:
        abort(403)
    ids = [c.id for c in classes]
    eleves = (
        Eleve.query.options(db.joinedload(Eleve.classe)).filter(Eleve.actif.is_(True), Eleve.classe_id.in_(ids))
        .order_by(Eleve.nom_complet).all()
    )

    if request.method == "POST":
        eleve = next((e for e in eleves if e.id == request.form.get("eleve_id", type=int)), None)
        type_incident = request.form.get("type", "")
        motif = request.form.get("motif", "").strip()[:250]
        minutes = request.form.get("minutes", type=int)
        duree = request.form.get("duree_jours", type=int)
        if eleve is None or type_incident not in LIBELLES_INCIDENT:
            flash("Choisis l'élève et le type.", "error")
        elif type_incident != "retard" and not motif:
            flash("Précise le motif.", "error")
        else:
            incident = Incident(
                eleve_id=eleve.id, classe_id=eleve.classe_id, date=date_du_formulaire("date"),
                type=type_incident, motif=motif or None, auteur_id=current_user.id,
                minutes=max(1, min(minutes, 600)) if type_incident == "retard" and minutes else None,
                duree_jours=max(1, min(duree, 60)) if type_incident == "exclusion" and duree else None,
            )
            db.session.add(incident)
            db.session.commit()
            _prevenir_les_parents(incident)
            flash("Enregistré dans le registre de discipline.", "info")
            return redirect(url_for("discipline.registre"))

    return render_template(
        "discipline/nouveau.html", eleves=eleves, types=TYPES_INCIDENT,
        eleve_id=request.args.get("eleve_id", type=int),
    )


def _prevenir_les_parents(incident):
    """Les parents reçoivent un email pour toute mesure de discipline ;
    les retards, eux, sont signalés au troisième du mois."""
    from app.services.notifications import notifier, signature

    eleve = incident.eleve
    destinataires = [p.email for p in eleve.parents]
    if not destinataires:
        return
    date_txt = incident.date.strftime("%d/%m/%Y")
    if incident.type == "retard":
        debut_mois = incident.date.replace(day=1)
        nb = Incident.query.filter(
            Incident.eleve_id == eleve.id, Incident.type == "retard", Incident.date >= debut_mois,
        ).count()
        if nb != 3:
            return
        sujet = f"Retards répétés — {eleve.nom_complet}"
        texte = f"{eleve.nom_complet} est arrivé(e) en retard {nb} fois ce mois-ci (dernier retard le {date_txt})."
    else:
        sujet = f"{incident.libelle} — {eleve.nom_complet}"
        texte = f"{incident.libelle} pour {eleve.nom_complet} le {date_txt}"
        if incident.duree_jours:
            texte += f", pour {incident.duree_jours} jour(s)"
        texte += f".\nMotif : {incident.motif}"
    notifier(destinataires, sujet, f"Bonjour,\n\n{texte}\nMerci de prendre contact avec l'école.\n\n{signature()}")


@discipline_bp.route("/<int:incident_id>/supprimer", methods=["POST"])
@login_required
def supprimer(incident_id):
    incident = db.get_or_404(Incident, incident_id)
    if not _peut_gerer(incident):
        abort(403)
    from app.services.journal import journaliser
    journaliser("suppression_incident", details=f"{incident.libelle} — {incident.eleve.nom_complet} ({incident.date})",
                cible_type="Eleve", cible_id=incident.eleve_id)
    eleve_id = incident.eleve_id
    db.session.delete(incident)
    db.session.commit()
    flash("Ligne retirée du registre.", "info")
    if request.form.get("retour") == "eleve":
        return redirect(url_for("absences.historique", eleve_id=eleve_id))
    return redirect(url_for("discipline.registre"))

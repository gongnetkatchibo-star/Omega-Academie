from flask import render_template, redirect, url_for, flash, request, make_response, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.enseignant import Enseignant
from app.models.emploi_du_temps import Creneau, JOURS
from app.emploi_du_temps import emploi_du_temps_bp
from app.utils import roles_required, html_vers_pdf
from app.services.cycles import cycle_du_role, classe_dans_le_cycle

ROLES_GESTION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"]
ROLES_LECTURE = ROLES_GESTION + ["enseignant", "eleve"]

NOM_ETABLISSEMENT = "Omega Académie"


def _verifier_cycle(classe_obj):
    cycle = cycle_du_role(current_user.role)
    if cycle and not classe_dans_le_cycle(classe_obj, cycle):
        abort(403)


def _construire_grille(creneaux):
    """Construit une grille jours (colonnes) x heures (lignes) à partir
    d'une liste de créneaux. Les lignes sont les plages horaires
    distinctes réellement utilisées, triées par heure de début."""
    plages = sorted({(c.heure_debut, c.heure_fin) for c in creneaux})
    grille = []
    for debut, fin in plages:
        ligne = {"heure_debut": debut, "heure_fin": fin, "jours": {}}
        for jour in JOURS:
            ligne["jours"][jour] = next(
                (c for c in creneaux if c.jour == jour and c.heure_debut == debut and c.heure_fin == fin),
                None,
            )
        grille.append(ligne)
    return grille


def _se_chevauchent(debut1, fin1, debut2, fin2):
    return debut1 < fin2 and debut2 < fin1


def _conflit_creneau(classe_id, enseignant_id, jour, heure_debut, heure_fin, exclure_id=None):
    """Détecte un conflit avant de créer un créneau : la même classe ne
    peut pas avoir deux matières en même temps, et un enseignant ne peut
    pas être dans deux classes à la fois (sept. 2026)."""
    requete = Creneau.query.filter_by(jour=jour)
    if exclure_id:
        requete = requete.filter(Creneau.id != exclure_id)

    for c in requete.all():
        if not _se_chevauchent(heure_debut, heure_fin, c.heure_debut, c.heure_fin):
            continue
        if c.classe_id == classe_id:
            return f"Conflit : {c.classe.nom} a déjà {c.matiere} de {c.heure_debut} à {c.heure_fin} le {jour}."
        if enseignant_id and c.enseignant_id == enseignant_id:
            return f"Conflit : {c.enseignant.nom_complet} enseigne déjà {c.classe.nom} de {c.heure_debut} à {c.heure_fin} le {jour}."
    return None


@emploi_du_temps_bp.route("/classe/<int:classe_id>", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_LECTURE)
def classe(classe_id):
    classe_obj = Classe.query.get_or_404(classe_id)
    _verifier_cycle(classe_obj)
    enseignants = sorted(Enseignant.query.all(), key=lambda e: e.nom_complet)

    if request.method == "POST":
        from app.services.permissions import role_a_acces
        if not role_a_acces(current_user.role, "emploi_du_temps", ROLES_GESTION):
            flash("Vous n'avez pas le droit de modifier l'emploi du temps.", "error")
            return redirect(url_for("emploi_du_temps.classe", classe_id=classe_id))

        matiere = request.form.get("matiere", "").strip()
        enseignant_id = request.form.get("enseignant_id", type=int) or None
        jour = request.form.get("jour")
        heure_debut = request.form.get("heure_debut", "").strip()
        heure_fin = request.form.get("heure_fin", "").strip()

        if not all([matiere, jour, heure_debut, heure_fin]):
            flash("Merci de remplir tous les champs.", "error")
        elif heure_fin <= heure_debut:
            flash("L'heure de fin doit être après l'heure de début.", "error")
        else:
            conflit = _conflit_creneau(classe_id, enseignant_id, jour, heure_debut, heure_fin)
            if conflit:
                flash(conflit, "error")
            else:
                db.session.add(Creneau(
                    classe_id=classe_id, enseignant_id=enseignant_id, matiere=matiere,
                    jour=jour, heure_debut=heure_debut, heure_fin=heure_fin,
                ))
                db.session.commit()
                flash("Créneau ajouté.", "info")
        return redirect(url_for("emploi_du_temps.classe", classe_id=classe_id))

    creneaux = Creneau.query.filter_by(classe_id=classe_id).order_by(Creneau.heure_debut).all()
    return render_template(
        "emploi_du_temps/classe.html",
        classe=classe_obj, jours=JOURS, grille=_construire_grille(creneaux), enseignants=enseignants,
    )


@emploi_du_temps_bp.route("/classe/<int:classe_id>/pdf")
@login_required
@roles_required(*ROLES_LECTURE)
def classe_pdf(classe_id):
    classe_obj = Classe.query.get_or_404(classe_id)
    _verifier_cycle(classe_obj)
    creneaux = Creneau.query.filter_by(classe_id=classe_id).order_by(Creneau.heure_debut).all()
    from app.services.documents_officiels import contexte_entete_officiel
    html = render_template(
        "emploi_du_temps/pdf.html",
        etablissement=NOM_ETABLISSEMENT, annee_scolaire=classe_obj.annee_scolaire,
        classe=classe_obj, jours=JOURS, grille=_construire_grille(creneaux), enseignant=None,
        **contexte_entete_officiel(),
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename=emploi_du_temps_{classe_obj.nom}.pdf"
    return reponse


@emploi_du_temps_bp.route("/moi")
@login_required
@roles_required("enseignant")
def moi():
    profil = current_user.profil_enseignant
    creneaux = Creneau.query.filter_by(enseignant_id=profil.id).order_by(Creneau.heure_debut).all() if profil else []
    classes = sorted({c.classe for c in creneaux}, key=lambda cl: cl.nom)
    return render_template("emploi_du_temps/moi.html", profil=profil, classes=classes)


@emploi_du_temps_bp.route("/moi/classe/<int:classe_id>")
@login_required
@roles_required("enseignant")
def moi_classe(classe_id):
    profil = current_user.profil_enseignant
    if not profil:
        abort(403)
    classe_obj = Classe.query.get_or_404(classe_id)
    # L'enseignant ne peut consulter que les classes où il intervient.
    if not Creneau.query.filter_by(classe_id=classe_id, enseignant_id=profil.id).first():
        abort(403)
    creneaux = Creneau.query.filter_by(classe_id=classe_id).order_by(Creneau.heure_debut).all()
    return render_template(
        "emploi_du_temps/classe.html",
        classe=classe_obj, jours=JOURS, grille=_construire_grille(creneaux), enseignants=[],
        vue_enseignant=profil,
    )


@emploi_du_temps_bp.route("/moi/classe/<int:classe_id>/pdf")
@login_required
@roles_required("enseignant")
def moi_classe_pdf(classe_id):
    profil = current_user.profil_enseignant
    if not profil:
        abort(403)
    classe_obj = Classe.query.get_or_404(classe_id)
    if not Creneau.query.filter_by(classe_id=classe_id, enseignant_id=profil.id).first():
        abort(403)
    creneaux = Creneau.query.filter_by(classe_id=classe_id).order_by(Creneau.heure_debut).all()
    from app.services.documents_officiels import contexte_entete_officiel
    html = render_template(
        "emploi_du_temps/pdf.html",
        etablissement=NOM_ETABLISSEMENT, annee_scolaire=classe_obj.annee_scolaire,
        classe=classe_obj, jours=JOURS, grille=_construire_grille(creneaux), enseignant=profil,
        **contexte_entete_officiel(),
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename=emploi_du_temps_{classe_obj.nom}_{profil.nom_complet}.pdf"
    return reponse

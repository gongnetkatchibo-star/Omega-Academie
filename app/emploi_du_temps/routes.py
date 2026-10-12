from flask import render_template, redirect, url_for, flash, request, make_response, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.services.tenant import nom_ecole_courante
from app.models.classe import Classe
from app.models.enseignant import Enseignant
from app.models.emploi_du_temps import Creneau, JOURS
from app.emploi_du_temps import emploi_du_temps_bp
from app.utils import roles_required, html_vers_pdf
from app.services.cycles import cycle_du_role, classe_dans_le_cycle

ROLES_GESTION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"]
ROLES_LECTURE = ROLES_GESTION + ["enseignant", "eleve"]



def _verifier_cycle(classe_obj):
    cycle = cycle_du_role(current_user.role)
    if cycle and not classe_dans_le_cycle(classe_obj, cycle):
        abort(403)
    if current_user.role == "enseignant":
        # Un enseignant consulte l'emploi du temps des classes où il enseigne.
        from app.services.suivi_eleve import classes_de_l_enseignant
        if classe_obj.id not in classes_de_l_enseignant():
            abort(403)
    if current_user.role == "eleve":
        # Un élève ne voit que l'emploi du temps de sa propre classe.
        from app.models.eleve import Eleve
        if not Eleve.query.filter_by(user_id=current_user.id, classe_id=classe_obj.id, actif=True).first():
            abort(403)


def _matiere_acceptee(matiere):
    from app.models.matiere import matiere_acceptee
    return matiere_acceptee(matiere)


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


def _lire_creneau(classe_id, exclure_id=None):
    """(valeurs, erreur) depuis le formulaire d'un créneau."""
    import re

    matiere = request.form.get("matiere", "").strip()
    enseignant_id = request.form.get("enseignant_id", type=int) or None
    jour = request.form.get("jour")
    heure_debut = request.form.get("heure_debut", "").strip()[:5]
    heure_fin = request.form.get("heure_fin", "").strip()[:5]
    format_heure = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
    valeurs = {"matiere": matiere[:80], "enseignant_id": enseignant_id, "jour": jour,
               "heure_debut": heure_debut, "heure_fin": heure_fin}
    if enseignant_id and db.session.get(Enseignant, enseignant_id) is None:
        return valeurs, "Enseignant introuvable."
    if not all([matiere, jour, heure_debut, heure_fin]):
        return valeurs, "Merci de remplir tous les champs."
    if jour not in JOURS:
        return valeurs, "Jour invalide."
    if not format_heure.match(heure_debut) or not format_heure.match(heure_fin):
        return valeurs, "Heures invalides (format HH:MM)."
    if not _matiere_acceptee(matiere):
        return valeurs, "Cette matière ne fait pas partie de la liste de l'école."
    if heure_fin <= heure_debut:
        return valeurs, "L'heure de fin doit être après l'heure de début."
    return valeurs, _conflit_creneau(classe_id, enseignant_id, jour, heure_debut, heure_fin, exclure_id)


def _conflit_creneau(classe_id, enseignant_id, jour, heure_debut, heure_fin, exclure_id=None):
    """Détecte un conflit avant de créer un créneau : la même classe ne
    peut pas avoir deux matières en même temps, et un enseignant ne peut
    pas être dans deux classes à la fois (sept. 2026)."""
    # Seulement les créneaux de la même année scolaire : ceux de l'an
    # dernier ne bloquent pas la nouvelle année.
    classe_obj = db.session.get(Classe, classe_id)
    requete = Creneau.query.join(Classe, Creneau.classe_id == Classe.id).filter(
        Creneau.jour == jour, Classe.annee_scolaire == classe_obj.annee_scolaire,
    )
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


@emploi_du_temps_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module="emploi_du_temps")
def index():
    """Entrée du menu : les classes de l'année, chacune avec son emploi du temps."""
    from app.models.eleve import Eleve
    from app.services.cycles import cycle_du_role, filtrer_par_cycle

    classes = filtrer_par_cycle(
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau, Classe.nom).all(),
        cycle_du_role(current_user.role),
    )
    return render_template(
        "classes/choisir.html", classes=classes, titre="Emplois du temps", icone_cle="emploi_du_temps",
        endpoint="emploi_du_temps.classe", libelle="Emploi du temps",
    )


@emploi_du_temps_bp.route("/classe/<int:classe_id>", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_LECTURE)
def classe(classe_id):
    classe_obj = db.get_or_404(Classe, classe_id)
    _verifier_cycle(classe_obj)
    enseignants = sorted(Enseignant.query.all(), key=lambda e: e.nom_complet)

    if request.method == "POST":
        from app.services.permissions import role_a_acces
        if not role_a_acces(current_user.role, "emploi_du_temps", ROLES_GESTION):
            flash("Vous n'avez pas le droit de modifier l'emploi du temps.", "error")
            return redirect(url_for("emploi_du_temps.classe", classe_id=classe_id))

        valeurs, erreur = _lire_creneau(classe_id)
        if erreur:
            flash(erreur, "error")
        else:
            db.session.add(Creneau(classe_id=classe_id, **valeurs))
            db.session.commit()
            flash("Créneau ajouté.", "info")
        return redirect(url_for("emploi_du_temps.classe", classe_id=classe_id))

    creneaux = Creneau.query.filter_by(classe_id=classe_id).order_by(Creneau.heure_debut).all()
    return render_template(
        "emploi_du_temps/classe.html",
        classe=classe_obj, jours=JOURS, grille=_construire_grille(creneaux), enseignants=enseignants,
    )


@emploi_du_temps_bp.route("/creneau/<int:creneau_id>/modifier", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="emploi_du_temps")
def modifier_creneau(creneau_id):
    creneau = db.get_or_404(Creneau, creneau_id)
    _verifier_cycle(creneau.classe)
    if request.method == "POST":
        valeurs, erreur = _lire_creneau(creneau.classe_id, exclure_id=creneau.id)
        if erreur:
            flash(erreur, "error")
        else:
            for champ, valeur in valeurs.items():
                setattr(creneau, champ, valeur)
            db.session.commit()
            flash("Créneau modifié.", "info")
            return redirect(url_for("emploi_du_temps.classe", classe_id=creneau.classe_id))
    enseignants = sorted(Enseignant.query.all(), key=lambda e: e.nom_complet)
    return render_template("emploi_du_temps/modifier.html", creneau=creneau, jours=JOURS, enseignants=enseignants)


@emploi_du_temps_bp.route("/creneau/<int:creneau_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="emploi_du_temps")
def supprimer_creneau(creneau_id):
    creneau = db.get_or_404(Creneau, creneau_id)
    _verifier_cycle(creneau.classe)
    classe_id = creneau.classe_id
    db.session.delete(creneau)
    db.session.commit()
    flash("Créneau retiré.", "info")
    return redirect(url_for("emploi_du_temps.classe", classe_id=classe_id))


@emploi_du_temps_bp.route("/classe/<int:classe_id>/pdf")
@login_required
@roles_required(*ROLES_LECTURE)
def classe_pdf(classe_id):
    classe_obj = db.get_or_404(Classe, classe_id)
    _verifier_cycle(classe_obj)
    return _pdf_de_la_classe(classe_obj)


def _pdf_de_la_classe(classe_obj):
    classe_id = classe_obj.id
    creneaux = Creneau.query.filter_by(classe_id=classe_id).order_by(Creneau.heure_debut).all()
    from app.services.documents_officiels import contexte_entete_officiel
    html = render_template(
        "emploi_du_temps/pdf.html",
        etablissement=nom_ecole_courante(), annee_scolaire=classe_obj.annee_scolaire,
        classe=classe_obj, jours=JOURS, grille=_construire_grille(creneaux), enseignant=None,
        **contexte_entete_officiel(),
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename=emploi_du_temps_{classe_obj.nom}.pdf"
    return reponse


def _eleve_suivi(eleve_id):
    from app.models.eleve import Eleve
    from app.services.suivi_eleve import peut_suivre

    eleve = db.get_or_404(Eleve, eleve_id)
    if not peut_suivre(eleve, "emploi_du_temps", ROLES_GESTION):
        abort(403)
    return eleve


@emploi_du_temps_bp.route("/eleve/<int:eleve_id>")
@login_required
def eleve(eleve_id):
    """L'emploi du temps de la classe d'un enfant, pour ses parents."""
    eleve_obj = _eleve_suivi(eleve_id)
    creneaux = Creneau.query.filter_by(classe_id=eleve_obj.classe_id).order_by(Creneau.heure_debut).all()
    return render_template(
        "emploi_du_temps/classe.html", classe=eleve_obj.classe, jours=JOURS, grille=_construire_grille(creneaux),
        enseignants=[], lien_pdf=url_for("emploi_du_temps.eleve_pdf", eleve_id=eleve_obj.id), lecture_seule=True,
    )


@emploi_du_temps_bp.route("/eleve/<int:eleve_id>/pdf")
@login_required
def eleve_pdf(eleve_id):
    return _pdf_de_la_classe(_eleve_suivi(eleve_id).classe)


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
    classe_obj = db.get_or_404(Classe, classe_id)
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
    classe_obj = db.get_or_404(Classe, classe_id)
    if not Creneau.query.filter_by(classe_id=classe_id, enseignant_id=profil.id).first():
        abort(403)
    creneaux = Creneau.query.filter_by(classe_id=classe_id).order_by(Creneau.heure_debut).all()
    from app.services.documents_officiels import contexte_entete_officiel
    html = render_template(
        "emploi_du_temps/pdf.html",
        etablissement=nom_ecole_courante(), annee_scolaire=classe_obj.annee_scolaire,
        classe=classe_obj, jours=JOURS, grille=_construire_grille(creneaux), enseignant=profil,
        **contexte_entete_officiel(),
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename=emploi_du_temps_{classe_obj.nom}_{profil.nom_complet}.pdf"
    return reponse

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.classes import classes_bp
from app.utils import roles_required
from app.services.cycles import cycle_du_role, filtrer_par_cycle, classe_dans_le_cycle
from app.services.groupes_frais import appliquer_frais_au_groupe, groupe_du_niveau

ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]
ROLES_LECTURE = ROLES_GESTION + ["enseignant"]
ROLES_FRAIS = ROLES_GESTION + ["comptable"]


def _montant_formulaire(nom_champ):
    """Lit un montant saisi via le champ liste déroulante + "Autre"
    (voir macro champ_montant) : priorité au menu, sinon la saisie libre."""
    valeur = request.form.get(nom_champ, type=float)
    if valeur is None:
        valeur = request.form.get(f"{nom_champ}_autre", type=float)
    return valeur

# Niveaux du Module 1 du cahier des charges, dans l'ordre. Le champ
# Classe.niveau stocke la position dans cette liste (1 = CP1, etc.) —
# c'est ce qui permet de calculer la classe supérieure pour le passage.
NIVEAUX = ["CP1", "CP2", "CE1", "CE2", "CM1", "CM2", "6ème", "5ème", "4ème", "3ème"]


@classes_bp.route("/")
@login_required
@roles_required(*ROLES_LECTURE)
def liste():
    from app.models.eleve import Eleve

    annees_disponibles = sorted({c.annee_scolaire for c in Classe.query.all()}, reverse=True)
    annee_courante = Eleve.annee_scolaire_courante()
    annee_selectionnee = request.args.get("annee") or (annee_courante if annee_courante in annees_disponibles else (annees_disponibles[0] if annees_disponibles else annee_courante))

    toutes = Classe.query.filter_by(annee_scolaire=annee_selectionnee).order_by(Classe.niveau).all()
    # Un directeur de cycle ne voit que les classes de son cycle
    # (document complémentaire, §5) — fondateur/administrateur général
    # voient tout.
    toutes = filtrer_par_cycle(toutes, cycle_du_role(current_user.role))
    return render_template(
        "classes/liste.html", classes=toutes, annees_disponibles=annees_disponibles,
        annee_selectionnee=annee_selectionnee, annee_courante=annee_courante,
    )


@classes_bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="classes")
def nouvelle():
    niveaux_numerotes = list(enumerate(NIVEAUX, start=1))
    cycle = cycle_du_role(current_user.role)

    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        niveau = request.form.get("niveau", type=int)
        annee_scolaire = request.form.get("annee_scolaire", "").strip()
        frais_inscription = _montant_formulaire("frais_inscription") or 0
        frais_tranche1 = _montant_formulaire("frais_tranche1") or 0
        frais_tranche2 = _montant_formulaire("frais_tranche2") or 0

        if not nom or not niveau or not annee_scolaire:
            flash("Merci de remplir tous les champs.", "error")
            return render_template("classes/nouvelle.html", niveaux=niveaux_numerotes)

        classe_candidate = Classe(niveau=niveau, nom=nom)
        if not classe_dans_le_cycle(classe_candidate, cycle):
            flash("Ce niveau ne fait pas partie de ton cycle de supervision.", "error")
            return render_template("classes/nouvelle.html", niveaux=niveaux_numerotes)

        if Classe.query.filter_by(nom=nom, annee_scolaire=annee_scolaire).first():
            flash(f"La classe {nom} existe déjà pour l'année {annee_scolaire}.", "error")
            return render_template("classes/nouvelle.html", niveaux=niveaux_numerotes)

        # Si d'autres classes du même groupe (même échéancier, même année)
        # existent déjà et qu'aucun montant n'a été saisi ici, on hérite
        # directement de leur échéancier plutôt que de repartir à 0.
        niveaux_groupe = groupe_du_niveau(niveau)
        membres_existants = Classe.query.filter(
            Classe.annee_scolaire == annee_scolaire, Classe.niveau.in_(niveaux_groupe)
        ).all()
        if membres_existants and frais_inscription == 0 and frais_tranche1 == 0 and frais_tranche2 == 0:
            ref = membres_existants[0]
            frais_inscription, frais_tranche1, frais_tranche2 = ref.frais_inscription, ref.frais_tranche1, ref.frais_tranche2

        nouvelle_classe = Classe(
            nom=nom, niveau=niveau, annee_scolaire=annee_scolaire,
            frais_inscription=frais_inscription, frais_tranche1=frais_tranche1,
            frais_tranche2=frais_tranche2,
        )
        db.session.add(nouvelle_classe)
        db.session.commit()
        # Propage au reste du groupe (utile si des montants ont été saisis
        # ici alors que les classes sœurs existaient déjà sans échéancier).
        appliquer_frais_au_groupe(nouvelle_classe, frais_inscription, frais_tranche1, frais_tranche2)
        flash(f"Classe {nom} créée.", "info")
        return redirect(url_for("classes.liste"))

    return render_template("classes/nouvelle.html", niveaux=niveaux_numerotes)


@classes_bp.route("/<int:classe_id>/frais", methods=["POST"])
@login_required
@roles_required(*ROLES_FRAIS)
def modifier_frais(classe_id):
    classe_obj = Classe.query.get_or_404(classe_id)
    if not classe_dans_le_cycle(classe_obj, cycle_du_role(current_user.role)):
        abort(403)
    inscription = _montant_formulaire("frais_inscription")
    tranche1 = _montant_formulaire("frais_tranche1")
    tranche2 = _montant_formulaire("frais_tranche2")

    if None in (inscription, tranche1, tranche2) or min(inscription, tranche1, tranche2) < 0:
        flash("Montants invalides.", "error")
    else:
        classes_maj = appliquer_frais_au_groupe(classe_obj, inscription, tranche1, tranche2)
        noms = ", ".join(c.nom for c in classes_maj)
        flash(f"Échéancier mis à jour pour {noms} (total {classe_obj.frais_annuel:.0f}).", "info")

    return redirect(url_for("classes.liste"))


@classes_bp.route("/demarrer-annee", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="classes")
def demarrer_annee():
    """Crée les classes CP1 à 3ème pour une année scolaire donnée. Si des
    classes existent déjà pour l'année précédente, leur échéancier de
    frais est repris automatiquement (à ajuster ensuite si besoin) —
    l'ancienne année reste intacte et consultable (document
    complémentaire, sept. 2026)."""
    from app.models.eleve import Eleve

    annees_existantes = sorted({c.annee_scolaire for c in Classe.query.all()}, reverse=True)
    annee_suggeree = Eleve.annee_scolaire_courante()

    if request.method == "POST":
        annee = request.form.get("annee_scolaire", "").strip()
        annee_source = request.form.get("annee_source", "").strip()

        if not annee:
            flash("Merci d'indiquer l'année scolaire à créer (ex : 2027-2028).", "error")
            return render_template("classes/demarrer_annee.html", annees=annees_existantes, annee_suggeree=annee_suggeree)

        classes_source = {c.nom: c for c in Classe.query.filter_by(annee_scolaire=annee_source).all()} if annee_source else {}

        creees = 0
        for position, nom in enumerate(NIVEAUX, start=1):
            if Classe.query.filter_by(nom=nom, annee_scolaire=annee).first():
                continue
            reference = classes_source.get(nom)
            db.session.add(Classe(
                nom=nom, niveau=position, annee_scolaire=annee,
                frais_inscription=reference.frais_inscription if reference else 0,
                frais_tranche1=reference.frais_tranche1 if reference else 0,
                frais_tranche2=reference.frais_tranche2 if reference else 0,
            ))
            creees += 1
        db.session.commit()
        flash(f"{creees} classe(s) créée(s) pour l'année {annee}." if creees else "Toutes les classes existent déjà pour cette année.", "info")
        return redirect(url_for("classes.liste", annee=annee))

    return render_template("classes/demarrer_annee.html", annees=annees_existantes, annee_suggeree=annee_suggeree)

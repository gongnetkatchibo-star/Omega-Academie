from datetime import datetime
from decimal import Decimal

from flask import render_template, redirect, url_for, flash, request, make_response, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.mouvement_caisse import MouvementCaisse, TYPES_CAISSE
from app.models.eleve import Eleve
from app.models.paiement import MODES_PAIEMENT, ECHEANCES, LIBELLES_ECHEANCE
from app.caisse import caisse_bp
from app.utils import roles_required, html_vers_pdf
from app.services.paiements import enregistrer_paiement

# Même périmètre que le module Finances (le secrétariat n'y a plus accès,
# décision de la direction — sept. 2026). Le comptable et la direction
# gèrent la caisse générale (recettes/dépenses hors scolarité).
ROLES_GESTION = ["comptable", "fondateur", "administrateur_general"]
ROLES_SUPPRESSION = ["fondateur", "administrateur_general"]

NOM_ETABLISSEMENT = "Omega Académie"


@caisse_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module="caisse")
def liste():
    """Registre unique de toute la trésorerie de l'école (Option A validée
    avec la direction, sept. 2026) : les paiements de scolarité y entrent
    automatiquement (lignes marquées "automatique"), les autres recettes
    et dépenses sont saisies ici directement. Une seule table, une seule
    source de vérité, aucune ressaisie."""
    mouvements = MouvementCaisse.query.order_by(
        MouvementCaisse.date.asc(), MouvementCaisse.id.asc()
    ).all()

    lignes = []
    solde = Decimal("0")
    total_recettes = Decimal("0")
    total_depenses = Decimal("0")
    for m in mouvements:
        solde += Decimal(str(m.recette or 0)) - Decimal(str(m.depense or 0))
        total_recettes += Decimal(str(m.recette or 0))
        total_depenses += Decimal(str(m.depense or 0))
        lignes.append({"mouvement": m, "solde": solde})

    lignes.reverse()

    return render_template(
        "caisse/liste.html",
        lignes=lignes,
        solde_actuel=solde,
        total_recettes=total_recettes,
        total_depenses=total_depenses,
    )


@caisse_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="caisse")
def nouveau():
    """Saisie manuelle — pour tout ce qui n'est PAS un paiement de
    scolarité (celui-ci passe par /caisse/nouveau-paiement ou par
    Finances, qui alimentent automatiquement ce registre)."""
    if request.method == "POST":
        date_str = request.form.get("date", "")
        type_ = request.form.get("type", "")
        reference = request.form.get("reference", "").strip()
        libelle = request.form.get("libelle", "").strip()
        recette = request.form.get("recette", type=float) or 0
        depense = request.form.get("depense", type=float) or 0
        observation = request.form.get("observation", "").strip()

        erreur = None
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            erreur = "Date invalide."

        if not libelle:
            erreur = "Le libellé est obligatoire."
        elif not type_ or type_ not in TYPES_CAISSE:
            erreur = "Le type de mouvement est obligatoire."
        elif recette == 0 and depense == 0:
            erreur = "Indique un montant en recette ou en dépense."
        elif recette > 0 and depense > 0:
            erreur = "Une ligne ne peut être à la fois une recette et une dépense — sépare-les en deux lignes."

        if erreur:
            flash(erreur, "error")
            return render_template("caisse/nouveau.html", types=TYPES_CAISSE, form=request.form)

        db.session.add(MouvementCaisse(
            date=date, type=type_, reference=reference, libelle=libelle,
            recette=recette, depense=depense, observation=observation,
            responsable_id=current_user.id,
        ))
        db.session.commit()
        flash("Mouvement de caisse enregistré.", "info")
        return redirect(url_for("caisse.liste"))

    return render_template("caisse/nouveau.html", types=TYPES_CAISSE, form={})


@caisse_bp.route("/mouvement/<int:mouvement_id>/modifier", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="caisse")
def modifier(mouvement_id):
    """Correction d'un mouvement saisi manuellement uniquement — une ligne
    automatique (paiement de scolarité) se corrige depuis Finances, pour
    ne jamais avoir deux écrans qui modifient la même donnée."""
    mouvement = MouvementCaisse.query.get_or_404(mouvement_id)
    if mouvement.automatique:
        flash("Cette ligne vient d'un paiement de scolarité : corrige-la depuis la fiche Finances de l'élève.", "error")
        return redirect(url_for("caisse.liste"))

    if request.method == "POST":
        date_str = request.form.get("date", "")
        type_ = request.form.get("type", "")
        reference = request.form.get("reference", "").strip()
        libelle = request.form.get("libelle", "").strip()
        recette = request.form.get("recette", type=float) or 0
        depense = request.form.get("depense", type=float) or 0
        observation = request.form.get("observation", "").strip()

        erreur = None
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            erreur = "Date invalide."
        if not libelle:
            erreur = "Le libellé est obligatoire."
        elif not type_ or type_ not in TYPES_CAISSE:
            erreur = "Le type de mouvement est obligatoire."
        elif recette == 0 and depense == 0:
            erreur = "Indique un montant en recette ou en dépense."
        elif recette > 0 and depense > 0:
            erreur = "Une ligne ne peut être à la fois une recette et une dépense — sépare-les en deux lignes."

        if erreur:
            flash(erreur, "error")
            return render_template("caisse/modifier.html", types=TYPES_CAISSE, mouvement=mouvement)

        mouvement.date = date
        mouvement.type = type_
        mouvement.reference = reference
        mouvement.libelle = libelle
        mouvement.recette = recette
        mouvement.depense = depense
        mouvement.observation = observation
        db.session.commit()
        flash("Mouvement de caisse corrigé.", "info")
        return redirect(url_for("caisse.liste"))

    return render_template("caisse/modifier.html", types=TYPES_CAISSE, mouvement=mouvement)


@caisse_bp.route("/mouvement/<int:mouvement_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION)
def supprimer(mouvement_id):
    mouvement = MouvementCaisse.query.get_or_404(mouvement_id)
    if mouvement.automatique:
        flash("Cette ligne vient d'un paiement de scolarité : supprime le paiement depuis Finances plutôt que la ligne de Caisse.", "error")
        return redirect(url_for("caisse.liste"))
    db.session.delete(mouvement)
    db.session.commit()
    flash("Mouvement de caisse supprimé.", "info")
    return redirect(url_for("caisse.liste"))


@caisse_bp.route("/nouveau-paiement", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="caisse")
def nouveau_paiement():
    """Formulaire de paiement officiel directement depuis la Caisse — même
    mécanisme que Finances (référence auto-générée, historique commun),
    pour un comptable qui travaille depuis cet écran plutôt que la fiche
    de l'élève."""
    eleves = Eleve.query.filter_by(actif=True).order_by(Eleve.nom_complet).all()

    if request.method == "POST":
        eleve_id = request.form.get("eleve_id", type=int)
        montant = request.form.get("montant", type=float)
        mode = request.form.get("mode")
        echeance = request.form.get("echeance")
        reference = request.form.get("reference", "").strip()

        eleve = Eleve.query.get(eleve_id) if eleve_id else None

        if not eleve or not montant or montant <= 0 or mode not in MODES_PAIEMENT or echeance not in ECHEANCES:
            flash("Merci de choisir un élève, un montant valide, un mode et une échéance.", "error")
            return render_template("caisse/nouveau_paiement.html", eleves=eleves, modes=MODES_PAIEMENT, echeances=ECHEANCES, libelles_echeance=LIBELLES_ECHEANCE)

        paiement = enregistrer_paiement(eleve, montant, mode, echeance, current_user, reference=reference or None)
        flash(f"Paiement enregistré — reçu {paiement.numero_recu}.", "info")
        return redirect(url_for("caisse.liste"))

    return render_template("caisse/nouveau_paiement.html", eleves=eleves, modes=MODES_PAIEMENT, echeances=ECHEANCES, libelles_echeance=LIBELLES_ECHEANCE)


@caisse_bp.route("/recu/<int:mouvement_id>/pdf")
@login_required
@roles_required(*ROLES_GESTION, module="caisse")
def recu_pdf(mouvement_id):
    """Reçu téléchargeable pour une ligne de caisse — exigé par la
    direction pour les paiements de scolarité, utile aussi pour toute
    autre ligne officielle."""
    m = MouvementCaisse.query.get_or_404(mouvement_id)
    html = render_template("caisse/recu_pdf.html", etablissement=NOM_ETABLISSEMENT, m=m)
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename=recu_{m.reference or m.id}.pdf"
    return reponse

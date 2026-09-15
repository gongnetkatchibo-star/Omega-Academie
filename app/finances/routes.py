from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.eleve import Eleve
from app.models.paiement import Paiement, MODES_PAIEMENT, ECHEANCES, LIBELLES_ECHEANCE
from app.finances import finances_bp
from app.utils import roles_required
from app.services.paiements import enregistrer_paiement, resume_paiements
from app.models.mouvement_caisse import MouvementCaisse

ROLES_GESTION = ["comptable", "fondateur", "administrateur_general"]
# Suppression réservée à la direction — le comptable peut corriger un
# paiement, mais pas l'effacer (séparation des responsabilités, une
# pratique comptable courante).
ROLES_SUPPRESSION = ["fondateur", "administrateur_general"]


@finances_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module="finances")
def liste():
    eleves = Eleve.query.filter_by(actif=True).order_by(Eleve.nom_complet).all()
    lignes = []
    for e in eleves:
        r = resume_paiements(e)
        lignes.append({"eleve": e, "du": r["du"], "paye": r["paye"], "solde": r["solde"], "statut": r["statut"]})
    return render_template("finances/liste.html", lignes=lignes)


@finances_bp.route("/<int:eleve_id>", methods=["GET", "POST"])
@login_required
def detail(eleve_id):
    eleve = Eleve.query.get_or_404(eleve_id)

    est_lie_comme_parent = current_user in eleve.parents
    est_gestionnaire = current_user.role in ROLES_GESTION or current_user.role == "developpeur"

    if not est_gestionnaire and not est_lie_comme_parent:
        abort(403)

    if not est_gestionnaire and est_lie_comme_parent:
        # Un parent (personnel compris) consulte le solde, il n'enregistre
        # pas de paiement lui-même (ça reste une saisie manuelle du
        # comptable/secrétariat).
        if request.method == "POST":
            abort(403)

    if request.method == "POST":
        montant = request.form.get("montant", type=float)
        mode = request.form.get("mode")
        echeance = request.form.get("echeance")
        reference = request.form.get("reference", "").strip()

        if not montant or montant <= 0 or mode not in MODES_PAIEMENT or echeance not in ECHEANCES:
            flash("Merci de saisir un montant valide, un mode de paiement et une échéance.", "error")
        else:
            paiement = enregistrer_paiement(
                eleve, montant, mode, echeance, current_user, reference=reference or None,
            )
            flash(f"Paiement enregistré — reçu {paiement.numero_recu}. Visible immédiatement dans la Caisse.", "info")
        return redirect(url_for("finances.detail", eleve_id=eleve.id))

    resume = resume_paiements(eleve)
    paiements = sorted(eleve.paiements, key=lambda p: p.date_paiement, reverse=True)
    return render_template(
        "finances/detail.html", eleve=eleve, resume=resume,
        paiements=paiements, modes=MODES_PAIEMENT, echeances=ECHEANCES,
        libelles_echeance=LIBELLES_ECHEANCE,
    )


@finances_bp.route("/paiement/<int:paiement_id>/modifier", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="finances")
def modifier_paiement(paiement_id):
    paiement = Paiement.query.get_or_404(paiement_id)
    eleve = paiement.eleve

    if request.method == "POST":
        montant = request.form.get("montant", type=float)
        mode = request.form.get("mode")
        echeance = request.form.get("echeance")
        reference = request.form.get("reference", "").strip()

        if not montant or montant <= 0 or mode not in MODES_PAIEMENT or echeance not in ECHEANCES:
            flash("Merci de saisir un montant valide, un mode de paiement et une échéance.", "error")
            return redirect(url_for("finances.modifier_paiement", paiement_id=paiement.id))

        paiement.montant = montant
        paiement.mode = mode
        paiement.echeance = echeance
        paiement.reference = reference or None

        # La ligne de Caisse liée doit rester synchronisée — on ne
        # ressaisit jamais la même correction à deux endroits.
        mouvement = MouvementCaisse.query.filter_by(origine_module="finances", origine_id=paiement.id).first()
        if mouvement:
            mouvement.recette = montant
            mouvement.reference = paiement.numero_recu
            mouvement.libelle = (
                f"Scolarité — {eleve.nom_complet} ({LIBELLES_ECHEANCE[echeance]}) [corrigé]"
            )

        db.session.commit()
        flash(f"Paiement {paiement.numero_recu} corrigé — la Caisse a été mise à jour.", "info")
        return redirect(url_for("finances.detail", eleve_id=eleve.id))

    return render_template(
        "finances/modifier_paiement.html", paiement=paiement, eleve=eleve,
        modes=MODES_PAIEMENT, echeances=ECHEANCES, libelles_echeance=LIBELLES_ECHEANCE,
    )


@finances_bp.route("/paiement/<int:paiement_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION)
def supprimer_paiement(paiement_id):
    paiement = Paiement.query.get_or_404(paiement_id)
    eleve_id = paiement.eleve_id
    numero = paiement.numero_recu

    MouvementCaisse.query.filter_by(origine_module="finances", origine_id=paiement.id).delete()
    db.session.delete(paiement)
    db.session.commit()

    flash(f"Paiement {numero} supprimé (et sa ligne de Caisse associée).", "info")
    return redirect(url_for("finances.detail", eleve_id=eleve_id))

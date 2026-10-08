from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.eleve import Eleve
from app.models.paiement import Paiement, MODES_PAIEMENT, ECHEANCES, LIBELLES_ECHEANCE
from app.finances import finances_bp
from app.utils import roles_required
from app.services.paiements import enregistrer_paiement, resume_paiements, resumes_paiements, analyser_echeance
from app.utils import montant_entier
from app.services.journal import journaliser
from app.models.mouvement_caisse import MouvementCaisse
from app.services.whatsapp import contacts as contacts_whatsapp

ROLES_GESTION = ["comptable", "fondateur", "administrateur_general"]
# Suppression réservée à la direction — le comptable peut corriger un
# paiement, mais pas l'effacer (séparation des responsabilités, une
# pratique comptable courante).
ROLES_SUPPRESSION = ["fondateur", "administrateur_general"]


@finances_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module="finances")
def liste():
    from app.services.pagination import paginer

    terme = request.args.get("q", "").strip()
    requete = Eleve.query.filter_by(actif=True)
    if terme:
        motif = f"%{terme}%"
        requete = requete.filter(db.or_(Eleve.nom_complet.ilike(motif), Eleve.matricule.ilike(motif)))
    en_retard = request.args.get("retard") == "1"
    if en_retard:
        # Le retard dépend des paiements et des dates limites : il se
        # calcule élève par élève, puis on pagine le résultat.
        from app.services.pagination import paginer_liste
        eleves = requete.order_by(Eleve.nom_complet).all()
        resumes = resumes_paiements(eleves)
        tous = [(e, resumes[e.id]) for e in eleves]
        page = paginer_liste([(e, r) for e, r in tous if r["retard"] > 0])
        couples = list(page)
    else:
        page = paginer(requete.order_by(Eleve.nom_complet))
        resumes = resumes_paiements(page.elements)
        couples = [(e, resumes[e.id]) for e in page]
    lignes = [
        {"eleve": e, "du": r["du"], "paye": r["paye"], "solde": r["solde"], "statut": r["statut"], "retard": r["retard"]}
        for e, r in couples
    ]
    return render_template("finances/liste.html", lignes=lignes, page=page, terme=terme, en_retard=en_retard)


@finances_bp.route("/<int:eleve_id>/remise", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION)
def remise(eleve_id):
    """Remise sur la scolarité : réservée à la direction, comme la
    suppression d'un paiement."""
    eleve = db.get_or_404(Eleve, eleve_id)
    pourcent = request.form.get("remise_pourcent", type=float)
    if pourcent is None or not 0 <= pourcent <= 100:
        flash("La remise doit être comprise entre 0 et 100 %.", "error")
    else:
        eleve.remise_pourcent = pourcent
        eleve.remise_motif = request.form.get("remise_motif", "").strip()[:120] or None
        journaliser("remise_scolarite", details=f"{eleve.nom_complet} — {pourcent:g} % ({eleve.remise_motif or 'sans motif'})",
                    cible_type="Eleve", cible_id=eleve.id)
        db.session.commit()
        flash(f"Remise de {pourcent:g} % enregistrée." if pourcent else "Remise retirée.", "info")
    return redirect(url_for("finances.detail", eleve_id=eleve.id))


@finances_bp.route("/frais-annexes", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="finances")
def frais_annexes():
    from datetime import datetime
    from app.models.classe import Classe
    from app.models.frais_annexe import FraisAnnexe

    annee = Eleve.annee_scolaire_courante()
    classes = Classe.query.filter_by(annee_scolaire=annee).order_by(Classe.niveau, Classe.nom).all()
    if request.method == "POST":
        libelle = request.form.get("libelle", "").strip()[:80]
        montant = montant_entier(request.form.get("montant"))
        classe_id = request.form.get("classe_id", type=int)
        date_str = request.form.get("date_limite", "")
        try:
            date_limite = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
        except ValueError:
            date_limite = None
        if not libelle or not montant or (classe_id and classe_id not in {c.id for c in classes}):
            flash("Le libellé et un montant valide sont obligatoires.", "error")
        else:
            db.session.add(FraisAnnexe(libelle=libelle, montant=montant, annee_scolaire=annee,
                                       classe_id=classe_id or None, date_limite=date_limite))
            journaliser("creation_frais_annexe", details=f"{libelle} — {montant}")
            db.session.commit()
            flash(f"Frais « {libelle} » ajouté.", "info")
        return redirect(url_for("finances.frais_annexes"))

    frais = FraisAnnexe.query.filter_by(annee_scolaire=annee).order_by(FraisAnnexe.id).all()
    encaisse = {
        f.id: sum(p.montant for p in Paiement.query.filter_by(frais_annexe_id=f.id).all()) for f in frais
    }
    return render_template("finances/frais_annexes.html", frais=frais, classes=classes, annee=annee, encaisse=encaisse)


@finances_bp.route("/frais-annexes/<int:frais_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION)
def supprimer_frais_annexe(frais_id):
    from app.models.frais_annexe import FraisAnnexe

    frais = db.get_or_404(FraisAnnexe, frais_id)
    if Paiement.query.filter_by(frais_annexe_id=frais.id).count():
        flash("Impossible de supprimer ce frais : des paiements y sont déjà rattachés.", "error")
    else:
        journaliser("suppression_frais_annexe", details=frais.libelle)
        db.session.delete(frais)
        db.session.commit()
        flash("Frais supprimé.", "info")
    return redirect(url_for("finances.frais_annexes"))


@finances_bp.route("/<int:eleve_id>/relancer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="finances")
def relancer(eleve_id):
    """Relance manuelle — le comptable déclenche l'email quand il le
    juge utile, plutôt qu'un envoi automatique qui pourrait harceler une
    famille en cours d'arrangement avec l'école (sept. 2026)."""
    from app.services.notifications import notifier, montant_fcfa, signature

    eleve = db.get_or_404(Eleve, eleve_id)
    resume = resume_paiements(eleve)

    if resume["solde"] <= 0:
        flash("Rien à relancer, le solde est déjà à jour.", "error")
        return redirect(url_for("finances.detail", eleve_id=eleve_id))

    if not eleve.parents:
        flash("Aucun parent lié à ce dossier pour recevoir la relance.", "error")
        return redirect(url_for("finances.detail", eleve_id=eleve_id))

    envoye = notifier(
        [p.email for p in eleve.parents],
        f"Rappel de paiement — {eleve.nom_complet}",
        (
            f"Bonjour,\n\n"
            f"Nous vous rappelons qu'un solde de {montant_fcfa(resume['solde'])} reste à régler "
            f"pour la scolarité de {eleve.nom_complet}.\n\n"
            f"Merci de régulariser dès que possible, ou de contacter le secrétariat "
            f"si vous souhaitez un arrangement.\n\n"
            f"{signature()}"
        ),
    )
    flash("Relance envoyée." if envoye else "Échec de l'envoi — vérifie la configuration email.", "info" if envoye else "error")
    return redirect(url_for("finances.detail", eleve_id=eleve_id))


@finances_bp.route("/<int:eleve_id>", methods=["GET", "POST"])
@login_required
def detail(eleve_id):
    eleve = db.get_or_404(Eleve, eleve_id)

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
        montant = montant_entier(request.form.get("montant"))
        mode = request.form.get("mode")
        choix = analyser_echeance(request.form.get("echeance"), eleve)
        reference = request.form.get("reference", "").strip()

        if not montant or mode not in MODES_PAIEMENT or choix is None:
            flash("Merci de saisir un montant valide (sans centimes), un mode de paiement et une échéance.", "error")
        else:
            echeance, frais_annexe = choix
            paiement = enregistrer_paiement(
                eleve, montant, mode, echeance, current_user, reference=reference or None, frais_annexe=frais_annexe,
            )
            flash(f"Paiement enregistré — reçu {paiement.numero_recu}. Visible immédiatement dans la Caisse.", "info")
        return redirect(url_for("finances.detail", eleve_id=eleve.id))

    resume = resume_paiements(eleve)
    paiements = sorted(eleve.paiements, key=lambda p: p.date_paiement, reverse=True)
    return render_template(
        "finances/detail.html", eleve=eleve, resume=resume,
        paiements=paiements, modes=MODES_PAIEMENT, echeances=ECHEANCES,
        libelles_echeance=LIBELLES_ECHEANCE, peut_remise=current_user.role in ROLES_SUPPRESSION + ["developpeur"],
        contacts_whatsapp=contacts_whatsapp(eleve),
    )


@finances_bp.route("/paiement/<int:paiement_id>/modifier", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="finances")
def modifier_paiement(paiement_id):
    paiement = db.get_or_404(Paiement, paiement_id)
    eleve = paiement.eleve

    if request.method == "POST":
        montant = montant_entier(request.form.get("montant"))
        mode = request.form.get("mode")
        choix = analyser_echeance(request.form.get("echeance"), eleve)
        reference = request.form.get("reference", "").strip()

        if not montant or mode not in MODES_PAIEMENT or choix is None:
            flash("Merci de saisir un montant valide (sans centimes), un mode de paiement et une échéance.", "error")
            return redirect(url_for("finances.modifier_paiement", paiement_id=paiement.id))

        echeance, frais_annexe = choix
        paiement.montant = montant
        paiement.mode = mode
        paiement.echeance = echeance
        paiement.frais_annexe_id = frais_annexe.id if frais_annexe else None
        paiement.reference = reference or None

        journaliser(
            "correction_paiement",
            details=f"{eleve.nom_complet} — reçu {paiement.numero_recu} → {montant:.0f} ({mode})",
            cible_type="Paiement", cible_id=paiement.id,
        )

        # La ligne de Caisse liée doit rester synchronisée — on ne
        # ressaisit jamais la même correction à deux endroits.
        mouvement = MouvementCaisse.query.filter_by(origine_module="finances", origine_id=paiement.id).first()
        if mouvement:
            mouvement.recette = montant
            mouvement.reference = paiement.numero_recu
            mouvement.libelle = (
                f"{frais_annexe.libelle} — {eleve.nom_complet} [corrigé]" if frais_annexe
                else f"Scolarité — {eleve.nom_complet} ({LIBELLES_ECHEANCE[echeance]}) [corrigé]"
            )

        db.session.commit()
        flash(f"Paiement {paiement.numero_recu} corrigé — la Caisse a été mise à jour.", "info")
        return redirect(url_for("finances.detail", eleve_id=eleve.id))

    return render_template(
        "finances/modifier_paiement.html", paiement=paiement, eleve=eleve, modes=MODES_PAIEMENT,
        resume=resume_paiements(eleve, paiement.annee_scolaire),
        choisie=f"annexe_{paiement.frais_annexe_id}" if paiement.frais_annexe_id else paiement.echeance,
    )


@finances_bp.route("/paiement/<int:paiement_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION)
def supprimer_paiement(paiement_id):
    paiement = db.get_or_404(Paiement, paiement_id)
    eleve_id = paiement.eleve_id
    numero = paiement.numero_recu

    journaliser(
        "suppression_paiement",
        details=f"{paiement.eleve.nom_complet} — reçu {numero} ({paiement.montant:.0f})",
        cible_type="Paiement", cible_id=paiement.id,
    )
    MouvementCaisse.query.filter_by(origine_module="finances", origine_id=paiement.id).delete()
    db.session.delete(paiement)
    db.session.commit()

    flash(f"Paiement {numero} supprimé (et sa ligne de Caisse associée).", "info")
    return redirect(url_for("finances.detail", eleve_id=eleve_id))

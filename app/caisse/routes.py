from datetime import datetime
from decimal import Decimal

from flask import render_template, redirect, url_for, flash, request, make_response, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.services.tenant import nom_ecole_courante
from app.models.mouvement_caisse import MouvementCaisse, TYPES_CAISSE
from app.models.eleve import Eleve
from app.models.paiement import MODES_PAIEMENT, ECHEANCES, LIBELLES_ECHEANCE
from app.caisse import caisse_bp
from app.utils import roles_required, html_vers_pdf, piece_jointe
from app.services.paiements import enregistrer_paiement
from app.services.journal import journaliser

# Même périmètre que le module Finances (le secrétariat n'y a plus accès,
# décision de la direction — sept. 2026). Le comptable et la direction
# gèrent la caisse générale (recettes/dépenses hors scolarité).
ROLES_GESTION = ["comptable", "fondateur", "administrateur_general"]
ROLES_SUPPRESSION = ["fondateur", "administrateur_general"]



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
    from app.services.pagination import paginer_liste
    page = paginer_liste(lignes)

    return render_template(
        "caisse/liste.html",
        lignes=page, page=page,
        solde_actuel=solde,
        total_recettes=total_recettes,
        total_depenses=total_depenses,
        date_cloture=__import__("app.services.paiements", fromlist=["date_cloture"]).date_cloture(),
        peut_cloturer=current_user.role in ROLES_SUPPRESSION + ["developpeur"],
    )


def _lire_mouvement(types_permis):
    """(valeurs, erreur) depuis le formulaire de saisie manuelle."""
    from app.services.paiements import periode_close
    from app.services.temps import aujourd_hui
    from app.utils import montant_positif_ou_nul

    valeurs = {
        "type": request.form.get("type", ""),
        # Pas de troncature ici : un texte trop long est refusé avec le nom
        # du champ (services/controles.py), plutôt que coupé en silence.
        "reference": request.form.get("reference", "").strip(),
        "libelle": request.form.get("libelle", "").strip(),
        "observation": request.form.get("observation", "").strip(),
        "recette": montant_positif_ou_nul(request.form.get("recette", "").strip()),
        "depense": montant_positif_ou_nul(request.form.get("depense", "").strip()),
    }
    try:
        valeurs["date"] = datetime.strptime(request.form.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        return valeurs, "Date invalide."
    if valeurs["recette"] is None or valeurs["depense"] is None:
        return valeurs, "Les montants doivent être des nombres entiers positifs (le franc CFA n'a pas de centimes)."
    if not valeurs["libelle"]:
        return valeurs, "Le libellé est obligatoire."
    if valeurs["type"] not in types_permis:
        return valeurs, "Le type de mouvement est obligatoire."
    if not valeurs["recette"] and not valeurs["depense"]:
        return valeurs, "Indique un montant en recette ou en dépense."
    if valeurs["recette"] and valeurs["depense"]:
        return valeurs, "Une ligne ne peut être à la fois une recette et une dépense — sépare-les en deux lignes."
    if valeurs["date"] > aujourd_hui():
        return valeurs, "La date ne peut pas être dans le futur."
    return valeurs, periode_close(valeurs["date"])


@caisse_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="caisse")
def nouveau():
    """Saisie manuelle — pour tout ce qui n'est PAS un paiement de
    scolarité (celui-ci passe par /caisse/nouveau-paiement ou par
    Finances, qui alimentent automatiquement ce registre)."""
    if request.method == "POST":
        valeurs, erreur = _lire_mouvement(TYPES_CAISSE)
        if erreur:
            flash(erreur, "error")
            return render_template("caisse/nouveau.html", types=TYPES_CAISSE, form=request.form)

        db.session.add(MouvementCaisse(responsable_id=current_user.id, **valeurs))
        journaliser("mouvement_caisse", details=f"{valeurs['libelle']} — {valeurs['recette'] or -valeurs['depense']}")
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
    mouvement = db.get_or_404(MouvementCaisse, mouvement_id)
    if mouvement.automatique:
        flash("Cette ligne vient d'un paiement de scolarité : corrige-la depuis la fiche Finances de l'élève.", "error")
        return redirect(url_for("caisse.liste"))

    from app.services.paiements import periode_close
    types_permis = TYPES_CAISSE + ([mouvement.type] if mouvement.type not in TYPES_CAISSE else [])
    erreur_periode = periode_close(mouvement.date)
    if erreur_periode:
        flash(erreur_periode, "error")
        return redirect(url_for("caisse.liste"))

    if request.method == "POST":
        valeurs, erreur = _lire_mouvement(types_permis)
        if erreur:
            flash(erreur, "error")
            return render_template("caisse/modifier.html", types=types_permis, mouvement=mouvement)

        ancien = f"{mouvement.date:%d/%m/%Y} {mouvement.libelle} ({mouvement.recette or 0:.0f}/{mouvement.depense or 0:.0f})"
        for champ, valeur in valeurs.items():
            setattr(mouvement, champ, valeur)
        from app.services.paiements import annuler_recus
        annuler_recus(mouvement.id)
        journaliser("correction_mouvement_caisse", details=f"{ancien} → {mouvement.libelle} ({mouvement.recette or 0:.0f}/{mouvement.depense or 0:.0f})",
                    cible_type="MouvementCaisse", cible_id=mouvement.id)
        db.session.commit()
        flash("Mouvement de caisse corrigé.", "info")
        return redirect(url_for("caisse.liste"))

    return render_template("caisse/modifier.html", types=types_permis, mouvement=mouvement)


@caisse_bp.route("/mouvement/<int:mouvement_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION)
def supprimer(mouvement_id):
    """Annule une ligne saisie à la main : elle reste dans le registre,
    marquée « annulée », compensée par une écriture inverse."""
    from app.services.paiements import contrepasser, periode_close
    from app.services.temps import aujourd_hui

    mouvement = db.get_or_404(MouvementCaisse, mouvement_id)
    if mouvement.automatique:
        flash("Cette ligne vient d'un autre module (scolarité, salaire, annulation) : annule-la à sa source.", "error")
        return redirect(url_for("caisse.liste"))
    erreur = periode_close(aujourd_hui())
    if erreur:
        flash(erreur, "error")
        return redirect(url_for("caisse.liste"))
    motif = request.form.get("motif", "").strip()[:200]
    journaliser("annulation_mouvement_caisse", details=f"{mouvement.libelle}{' — ' + motif if motif else ''}",
                cible_type="MouvementCaisse", cible_id=mouvement.id)
    contrepasser(mouvement, motif or "Annulation d'une saisie manuelle", current_user)
    mouvement.automatique = True  # ne se modifie plus
    db.session.commit()
    flash("Mouvement annulé : il reste visible, compensé par une écriture inverse.", "info")
    return redirect(url_for("caisse.liste"))


@caisse_bp.route("/cloture", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION, module="caisse")
def cloturer():
    """La direction arrête la caisse à une date : plus rien ne peut être
    ajouté, corrigé ou annulé jusqu'à cette date incluse."""
    from app.models.parametre import ParametreEtablissement
    from app.services.temps import aujourd_hui

    parametre = ParametreEtablissement.get()
    saisie = request.form.get("date_cloture", "")
    try:
        nouvelle = datetime.strptime(saisie, "%Y-%m-%d").date() if saisie else None
    except ValueError:
        nouvelle = False
    if nouvelle is False or (nouvelle and nouvelle > aujourd_hui()):
        flash("Date de clôture invalide (elle ne peut pas être dans le futur).", "error")
    elif parametre.date_cloture_caisse and (nouvelle is None or nouvelle < parametre.date_cloture_caisse) and current_user.role != "fondateur" and current_user.role != "developpeur":
        flash("Seul le fondateur peut rouvrir une période déjà clôturée.", "error")
    else:
        parametre.date_cloture_caisse = nouvelle
        journaliser("cloture_caisse", details=f"Caisse clôturée jusqu'au {nouvelle:%d/%m/%Y}" if nouvelle else "Clôture de la caisse retirée")
        db.session.commit()
        flash(f"Caisse clôturée jusqu'au {nouvelle:%d/%m/%Y}." if nouvelle else "Clôture retirée.", "info")
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
        from app.utils import montant_entier
        from app.services.paiements import analyser_echeance, controler_montant, periode_close
        from app.services.temps import aujourd_hui

        eleve_id = request.form.get("eleve_id", type=int)
        montant = montant_entier(request.form.get("montant"))
        mode = request.form.get("mode")
        reference = request.form.get("reference", "").strip()[:80]

        eleve = db.session.get(Eleve, eleve_id) if eleve_id else None
        choix = analyser_echeance(request.form.get("echeance"), eleve) if eleve else None

        erreur = None
        if not eleve or not eleve.actif or not montant or mode not in MODES_PAIEMENT or choix is None:
            erreur = "Merci de choisir un élève, un montant valide (sans centimes), un mode et une échéance."
        else:
            erreur = periode_close(aujourd_hui()) or controler_montant(eleve, choix[0], choix[1], montant)
        if erreur:
            flash(erreur, "error")
            return render_template("caisse/nouveau_paiement.html", eleves=eleves, modes=MODES_PAIEMENT, echeances=ECHEANCES, libelles_echeance=LIBELLES_ECHEANCE)

        paiement = enregistrer_paiement(eleve, montant, mode, choix[0], current_user, reference=reference or None, frais_annexe=choix[1])
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
    m = db.get_or_404(MouvementCaisse, mouvement_id)
    if (m.origine_module or "").endswith("_annule"):
        flash("Ce mouvement a été annulé : aucun reçu ne peut plus être édité.", "error")
        return redirect(url_for("caisse.liste"))
    from app.services.documents_officiels import contexte_entete_officiel
    from app.services.verification import emettre_recu, bloc_verification
    verification = bloc_verification(emettre_recu(m))
    db.session.commit()
    html = render_template(
        "caisse/recu_pdf.html", etablissement=nom_ecole_courante(), m=m, verification=verification,
        **contexte_entete_officiel(),
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = piece_jointe(f"recu_{m.reference or m.id}.pdf")
    return reponse

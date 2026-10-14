from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.services.tenant import nom_ecole_courante
from app.models.user import User
from app.models.salaire import Salaire, STATUTS_SALAIRE, LIBELLES_STATUT_SALAIRE, MOIS_LIBELLES
from app.models.mouvement_caisse import MouvementCaisse, TYPE_SALAIRE_AUTO
from app.salaires import salaires_bp
from app.utils import roles_required, export_csv, export_xlsx, export_pdf_liste, piece_jointe
from app.services.journal import journaliser
from app.services.temps import maintenant

ROLES_GESTION = ["comptable", "fondateur", "administrateur_general"]
ROLES_SUPPRESSION = ["fondateur", "administrateur_general"]


def _salaires_filtres():
    """Filtres communs à l'affichage et à chacun des exports — pour que
    ce qu'on voit à l'écran soit toujours exactement ce qu'on télécharge."""
    nom = request.args.get("nom", "").strip()
    date_debut = request.args.get("date_debut", "").strip()
    date_fin = request.args.get("date_fin", "").strip()

    requete = Salaire.query.join(User, Salaire.personnel_id == User.id)
    if nom:
        requete = requete.filter(User.nom_complet.ilike(f"%{nom}%"))
    if date_debut:
        try:
            requete = requete.filter(Salaire.date_paiement >= datetime.strptime(date_debut, "%Y-%m-%d").date())
        except ValueError:
            pass
    if date_fin:
        try:
            requete = requete.filter(Salaire.date_paiement <= datetime.strptime(date_fin, "%Y-%m-%d").date())
        except ValueError:
            pass

    salaires = requete.order_by(Salaire.annee.desc(), Salaire.mois.desc()).all()
    return salaires, nom, date_debut, date_fin


@salaires_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module="salaires")
def liste():
    salaires, nom, date_debut, date_fin = _salaires_filtres()
    total_paye = sum(s.montant for s in salaires if s.statut == "paye")
    total_impaye = sum(s.montant for s in salaires if s.statut == "impaye")
    return render_template(
        "salaires/liste.html", salaires=salaires, total_paye=total_paye,
        total_impaye=total_impaye, mois_libelles=MOIS_LIBELLES,
        filtre_nom=nom, filtre_date_debut=date_debut, filtre_date_fin=date_fin,
    )


def _lignes_export(salaires):
    entetes = ["Bénéficiaire", "Genre", "Fonction", "Email", "Téléphone", "Période", "Montant", "Statut", "Date de paiement"]
    lignes = [
        (
            s.personnel.nom_complet, {"M": "M", "F": "F"}.get(s.personnel.genre, "—"), s.fonction or "—", s.email_contact or "—", s.telephone_contact or "—",
            s.libelle_periode, s.montant, LIBELLES_STATUT_SALAIRE.get(s.statut, s.statut),
            s.date_paiement.strftime("%d/%m/%Y") if s.date_paiement else "—",
        )
        for s in salaires
    ]
    return entetes, lignes


@salaires_bp.route("/export/<format_fichier>")
@login_required
@roles_required(*ROLES_GESTION, module="salaires")
def exporter(format_fichier):
    salaires, nom, date_debut, date_fin = _salaires_filtres()
    entetes, lignes = _lignes_export(salaires)

    if format_fichier == "csv":
        return export_csv(entetes, lignes, "journal_salaires")
    if format_fichier == "xlsx":
        return export_xlsx(entetes, lignes, "journal_salaires", titre_feuille="Salaires")
    if format_fichier == "pdf":
        sous_titre = "Journal de paie"
        if nom:
            sous_titre += f" — {nom}"
        if date_debut or date_fin:
            sous_titre += f" — du {date_debut or '…'} au {date_fin or '…'}"
        return export_pdf_liste("Salaires du personnel", sous_titre, entetes, lignes, "journal_salaires")

    flash("Format d'export inconnu.", "error")
    return redirect(url_for("salaires.liste"))


@salaires_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="salaires")
def nouveau():
    # Tout compte actif peut être payé ici — pas seulement les enseignants,
    # la direction et le personnel administratif ont aussi un salaire.
    personnel = User.query.filter_by(statut="actif").filter(User.role != "eleve").order_by(User.nom_complet).all()

    # Dernière fonction utilisée pour chaque personne, pour pré-remplir
    # le champ automatiquement (évite de la retaper à chaque salaire).
    dernieres_fonctions = {}
    for s in Salaire.query.filter(Salaire.fonction.isnot(None)).order_by(Salaire.date_creation.desc()).all():
        dernieres_fonctions.setdefault(s.personnel_id, s.fonction)
    for p in personnel:
        p.derniere_fonction_salaire = dernieres_fonctions.get(p.id, "")

    if request.method == "POST":
        personnel_id = request.form.get("personnel_id", type=int)
        mois = request.form.get("mois", type=int)
        annee = request.form.get("annee", type=int)
        from app.utils import montant_entier, montant_positif_ou_nul
        base = montant_entier(request.form.get("montant"))
        primes = montant_positif_ou_nul(request.form.get("primes", "").strip())
        retenues = montant_positif_ou_nul(request.form.get("retenues", "").strip())
        montant = (base or 0) + (primes or 0) - (retenues or 0)
        fonction = request.form.get("fonction", "").strip()
        email_contact = request.form.get("email_contact", "").strip()
        telephone_contact = request.form.get("telephone_contact", "").strip()

        employe = db.session.get(User, personnel_id) if personnel_id else None
        erreur = None
        annee_actuelle = maintenant().year
        if not employe or not mois or not 1 <= mois <= 12 or not annee or not base or primes is None or retenues is None:
            erreur = "Merci de remplir tous les champs avec des montants entiers valides (sans centimes)."
        elif not annee_actuelle - 1 <= annee <= annee_actuelle + 1:
            erreur = "L'année du salaire doit être l'année en cours, la précédente ou la suivante."
        elif montant <= 0:
            erreur = "Les retenues dépassent le salaire : le net à payer doit rester positif."
        elif employe.id == current_user.id and current_user.role not in ("fondateur", "developpeur"):
            # Séparation des tâches : personne n'enregistre son propre salaire.
            erreur = "Ton propre salaire est enregistré par la direction, pas par toi-même."
        elif Salaire.query.filter_by(personnel_id=personnel_id, mois=mois, annee=annee).first():
            erreur = f"Un salaire existe déjà pour {employe.nom_complet} sur cette période."

        if erreur:
            flash(erreur, "error")
            return render_template("salaires/nouveau.html", personnel=personnel, mois_libelles=MOIS_LIBELLES,
                                   annee_courante=maintenant().year)

        db.session.add(Salaire(
            personnel_id=personnel_id, mois=mois, annee=annee, montant=montant, salaire_base=base,
            primes=primes or None, retenues=retenues or None,
            motif_primes=request.form.get("motif_primes", "").strip()[:150] or None if primes else None,
            motif_retenues=request.form.get("motif_retenues", "").strip()[:150] or None if retenues else None,
            responsable_id=current_user.id, fonction=fonction or None,
            email_contact=(email_contact or employe.email)[:120], telephone_contact=(telephone_contact or employe.telephone or "")[:30] or None,
        ))
        journaliser("nouveau_salaire", details=f"{employe.nom_complet} — {MOIS_LIBELLES[mois-1]} {annee} ({montant:.0f})")
        db.session.commit()
        flash(f"Salaire de {employe.nom_complet} enregistré pour {MOIS_LIBELLES[mois-1]} {annee} — statut impayé.", "info")
        return redirect(url_for("salaires.liste"))

    return render_template("salaires/nouveau.html", personnel=personnel, mois_libelles=MOIS_LIBELLES,
                           annee_courante=maintenant().year)


@salaires_bp.route("/<int:salaire_id>/payer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="salaires")
def marquer_paye(salaire_id):
    """Enregistre le versement — crée automatiquement la dépense
    correspondante dans la Caisse, même principe que les paiements de
    scolarité (Option A, sept. 2026) : jamais de ressaisie."""
    from app.services.paiements import periode_close

    # Verrou sur la ligne : un double clic ne crée jamais deux dépenses.
    salaire = db.session.execute(
        db.select(Salaire).where(Salaire.id == salaire_id).with_for_update()
    ).scalar_one_or_none() or abort(404)
    if salaire.personnel_id == current_user.id and current_user.role not in ("fondateur", "developpeur"):
        flash("Ton propre salaire est marqué payé par la direction, pas par toi-même.", "error")
        return redirect(url_for("salaires.liste"))
    deja = MouvementCaisse.query.filter_by(origine_module="salaires", origine_id=salaire.id).first()
    if salaire.statut == "paye" or deja:
        flash("Ce salaire est déjà marqué comme payé.", "error")
        return redirect(url_for("salaires.liste"))
    erreur = periode_close(maintenant().date())
    if erreur:
        flash(erreur, "error")
        return redirect(url_for("salaires.liste"))

    salaire.statut = "paye"
    salaire.date_paiement = maintenant().date()
    journaliser("salaire_marque_paye", details=f"{salaire.personnel.nom_complet} — {salaire.libelle_periode} ({salaire.montant:.0f})", cible_type="Salaire", cible_id=salaire.id)
    db.session.flush()

    db.session.add(MouvementCaisse(
        date=salaire.date_paiement,
        type=TYPE_SALAIRE_AUTO,
        reference=f"SAL-{salaire.id}",
        libelle=f"Salaire — {salaire.personnel.nom_complet} ({salaire.libelle_periode})",
        recette=0,
        depense=salaire.montant,
        responsable_id=current_user.id,
        origine_module="salaires",
        origine_id=salaire.id,
        automatique=True,
    ))
    db.session.commit()

    if salaire.email_contact:
        from app.services.notifications import notifier, montant_fcfa
        notifier(
            [salaire.email_contact],
            f"Salaire versé — {salaire.libelle_periode}",
            (
                f"Bonjour {salaire.personnel.nom_complet},\n\n"
                f"Votre salaire de {salaire.libelle_periode}, d'un montant de {montant_fcfa(salaire.montant)}, "
                f"vient d'être enregistré comme versé.\n\n"
                f"Ceci est une notification automatique de {nom_ecole_courante()}."
            ),
        )

    flash(f"Salaire de {salaire.personnel.nom_complet} marqué payé — dépense enregistrée en Caisse.", "info")
    return redirect(url_for("salaires.liste"))


@salaires_bp.route("/<int:salaire_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION)
def supprimer(salaire_id):
    """Un salaire pas encore payé se supprime ; un salaire payé s'annule :
    la dépense reste dans la caisse, compensée par une écriture inverse."""
    from app.services.paiements import contrepasser, periode_close

    salaire = db.get_or_404(Salaire, salaire_id)
    mouvements = MouvementCaisse.query.filter_by(origine_module="salaires", origine_id=salaire.id).all()
    if mouvements:
        erreur = periode_close(maintenant().date())
        if erreur:
            flash(erreur, "error")
            return redirect(url_for("salaires.liste"))
    journaliser("suppression_salaire", details=f"{salaire.personnel.nom_complet} — {salaire.libelle_periode} ({salaire.montant:.0f}, {salaire.statut})",
                cible_type="Salaire", cible_id=salaire.id)
    for mouvement in mouvements:
        contrepasser(mouvement, f"Annulation du salaire {salaire.libelle_periode}", current_user)
    from app.models.document_verifiable import DocumentVerifiable
    DocumentVerifiable.query.filter_by(cle_objet=f"fiche_paie:{salaire.id}", annule=False).update({"annule": True})
    db.session.delete(salaire)
    db.session.commit()
    flash("Salaire supprimé." if not mouvements else "Salaire annulé : la dépense reste visible en caisse, compensée par une écriture inverse.", "info")
    return redirect(url_for("salaires.liste"))

def _fiche_pdf(salaire):
    from flask import make_response
    from app.services.documents_officiels import contexte_entete_officiel
    from app.services.verification import emettre, bloc_verification
    from app.utils import html_vers_pdf
    from app.services.notifications import montant_fcfa

    reference = f"PAIE-{salaire.annee}{salaire.mois:02d}-{salaire.id}"
    document = emettre(
        "fiche_paie", f"fiche_paie:{salaire.id}", "Fiche de paie", reference=reference,
        details=[
            ("Bénéficiaire", salaire.personnel.nom_complet),
            ("Période", salaire.libelle_periode),
            ("Net à payer", montant_fcfa(salaire.montant)),
            ("Statut", LIBELLES_STATUT_SALAIRE.get(salaire.statut, salaire.statut)),
        ],
    )
    db.session.commit()
    html = render_template(
        "salaires/fiche_pdf.html", s=salaire, reference=reference, verification=bloc_verification(document),
        **contexte_entete_officiel(),
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = piece_jointe(f"fiche_paie_{reference}.pdf")
    return reponse


@salaires_bp.route("/<int:salaire_id>/fiche")
@login_required
def fiche(salaire_id):
    """Fiche de paie : pour la comptabilité, et pour la personne payée."""
    from flask import abort
    from app.services.permissions import role_a_acces

    salaire = db.get_or_404(Salaire, salaire_id)
    if salaire.personnel_id != current_user.id and not role_a_acces(current_user.role, "salaires", ROLES_GESTION):
        abort(403)
    return _fiche_pdf(salaire)


@salaires_bp.route("/mes-fiches")
@login_required
def mes_fiches():
    """Les fiches de paie de la personne connectée."""
    salaires = (
        Salaire.query.filter_by(personnel_id=current_user.id)
        .order_by(Salaire.annee.desc(), Salaire.mois.desc()).all()
    )
    return render_template("salaires/mes_fiches.html", salaires=salaires)

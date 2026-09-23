from datetime import datetime

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User
from app.models.salaire import Salaire, STATUTS_SALAIRE, LIBELLES_STATUT_SALAIRE, MOIS_LIBELLES
from app.models.mouvement_caisse import MouvementCaisse
from app.salaires import salaires_bp
from app.utils import roles_required, export_csv, export_xlsx, export_pdf_liste
from app.services.journal import journaliser

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
        montant = request.form.get("montant", type=float)
        fonction = request.form.get("fonction", "").strip()
        email_contact = request.form.get("email_contact", "").strip()
        telephone_contact = request.form.get("telephone_contact", "").strip()

        employe = User.query.get(personnel_id) if personnel_id else None
        erreur = None
        if not employe or not mois or not annee or not montant or montant <= 0:
            erreur = "Merci de remplir tous les champs avec des valeurs valides."
        elif Salaire.query.filter_by(personnel_id=personnel_id, mois=mois, annee=annee).first():
            erreur = f"Un salaire existe déjà pour {employe.nom_complet} sur cette période."

        if erreur:
            flash(erreur, "error")
            return render_template("salaires/nouveau.html", personnel=personnel, mois_libelles=MOIS_LIBELLES)

        db.session.add(Salaire(
            personnel_id=personnel_id, mois=mois, annee=annee, montant=montant,
            responsable_id=current_user.id, fonction=fonction or None,
            email_contact=email_contact or employe.email, telephone_contact=telephone_contact or employe.telephone,
        ))
        db.session.commit()
        flash(f"Salaire de {employe.nom_complet} enregistré pour {MOIS_LIBELLES[mois-1]} {annee} — statut impayé.", "info")
        return redirect(url_for("salaires.liste"))

    return render_template("salaires/nouveau.html", personnel=personnel, mois_libelles=MOIS_LIBELLES)


@salaires_bp.route("/<int:salaire_id>/payer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="salaires")
def marquer_paye(salaire_id):
    """Enregistre le versement — crée automatiquement la dépense
    correspondante dans la Caisse, même principe que les paiements de
    scolarité (Option A, sept. 2026) : jamais de ressaisie."""
    salaire = Salaire.query.get_or_404(salaire_id)
    if salaire.statut == "paye":
        flash("Ce salaire est déjà marqué comme payé.", "error")
        return redirect(url_for("salaires.liste"))

    salaire.statut = "paye"
    salaire.date_paiement = datetime.utcnow().date()
    journaliser("salaire_marque_paye", details=f"{salaire.personnel.nom_complet} — {salaire.libelle_periode} ({salaire.montant:.0f})", cible_type="Salaire", cible_id=salaire.id)
    db.session.flush()

    db.session.add(MouvementCaisse(
        date=salaire.date_paiement,
        type="Salaire",
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
        from app.services.notifications import notifier
        notifier(
            [salaire.email_contact],
            f"Salaire versé — {salaire.libelle_periode}",
            (
                f"Bonjour {salaire.personnel.nom_complet},\n\n"
                f"Ton salaire de {salaire.libelle_periode} d'un montant de {salaire.montant:.0f} "
                f"vient d'être enregistré comme versé.\n\n"
                f"Ceci est une notification automatique d'Omega Académie."
            ),
        )

    flash(f"Salaire de {salaire.personnel.nom_complet} marqué payé — dépense enregistrée en Caisse.", "info")
    return redirect(url_for("salaires.liste"))


@salaires_bp.route("/<int:salaire_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION)
def supprimer(salaire_id):
    salaire = Salaire.query.get_or_404(salaire_id)
    journaliser("suppression_salaire", details=f"{salaire.personnel.nom_complet} — {salaire.libelle_periode}", cible_type="Salaire", cible_id=salaire.id)
    MouvementCaisse.query.filter_by(origine_module="salaires", origine_id=salaire.id).delete()
    db.session.delete(salaire)
    db.session.commit()
    flash("Ligne de salaire supprimée (et sa dépense de Caisse associée si elle existait).", "info")
    return redirect(url_for("salaires.liste"))

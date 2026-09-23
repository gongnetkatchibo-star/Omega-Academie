from datetime import datetime
import secrets

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.eleve import Eleve, STATUTS_DOSSIER, MAX_PARENTS_PAR_ELEVE
from app.services.moyennes import moyenne_eleve, a_reussi, seuil_reussite_pour_classe
from app.models.historique import HistoriqueScolaire
from app.models.user import User
from app.eleves import eleves_bp
from app.utils import roles_required, export_csv, export_xlsx, export_pdf_liste
from app.services.cycles import cycle_du_role, filtrer_par_cycle, classe_dans_le_cycle

ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]
ROLES_LECTURE = ROLES_GESTION + ["enseignant"]


@eleves_bp.route("/")
@login_required
@roles_required(*ROLES_LECTURE)
def liste():
    classe_id = request.args.get("classe_id", type=int)
    requete = Eleve.query.filter_by(actif=True)
    if classe_id:
        requete = requete.filter_by(classe_id=classe_id)
    eleves = requete.order_by(Eleve.nom_complet).all()
    classes = Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau).all()

    cycle = cycle_du_role(current_user.role)
    if cycle:
        eleves = [e for e in eleves if classe_dans_le_cycle(e.classe, cycle)]
        classes = filtrer_par_cycle(classes, cycle)

    return render_template("eleves/liste.html", eleves=eleves, classes=classes, classe_id=classe_id)


def _lignes_export_eleves(classe_id=None, cycle=None):
    requete = Eleve.query.filter_by(actif=True)
    if classe_id:
        requete = requete.filter_by(classe_id=classe_id)
    eleves = requete.order_by(Eleve.nom_complet).all()
    if cycle:
        eleves = [e for e in eleves if classe_dans_le_cycle(e.classe, cycle)]
    entetes = ["Matricule", "Nom complet", "Genre", "Classe", "Téléphone parent", "Statut dossier", "Parent(s) lié(s)"]
    lignes = [
        (
            e.matricule, e.nom_complet, e.sexe or "—", e.classe.nom,
            e.telephone_parent or "—", e.statut_dossier,
            ", ".join(p.nom_complet for p in e.parents) if e.parents else "—",
        )
        for e in eleves
    ]
    return entetes, lignes


@eleves_bp.route("/export/<fmt>")
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def export(fmt):
    classe_id = request.args.get("classe_id", type=int)
    classe_obj = Classe.query.get(classe_id) if classe_id else None
    sous_titre = f"Classe : {classe_obj.nom}" if classe_obj else "Toutes classes"
    nom_fichier = f"eleves_{classe_obj.nom}" if classe_obj else "eleves_toutes_classes"
    entetes, lignes = _lignes_export_eleves(classe_id, cycle=cycle_du_role(current_user.role))

    if fmt == "csv":
        return export_csv(entetes, lignes, nom_fichier)
    if fmt == "xlsx":
        return export_xlsx(entetes, lignes, nom_fichier, "Élèves")
    if fmt == "pdf":
        return export_pdf_liste("Liste des élèves", sous_titre, entetes, lignes, nom_fichier)
    flash("Format d'export inconnu.", "error")
    return redirect(url_for("eleves.liste"))


@eleves_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def nouveau():
    # On n'inscrit un nouvel élève que dans une classe de l'année en
    # cours — les classes des années passées restent consultables mais
    # ne doivent jamais recevoir de nouvelle inscription.
    classes = Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau).all()

    if request.method == "POST":
        nom_complet = request.form.get("nom_complet", "").strip()
        classe_id = request.form.get("classe_id", type=int)
        date_naissance_str = request.form.get("date_naissance", "")
        sexe = request.form.get("sexe")
        telephone_parent = request.form.get("telephone_parent", "").strip()

        if not nom_complet or not classe_id:
            flash("Le nom et la classe sont obligatoires.", "error")
            return render_template("eleves/nouveau.html", classes=classes)

        date_naissance = None
        if date_naissance_str:
            try:
                date_naissance = datetime.strptime(date_naissance_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        classe = Classe.query.get(classe_id)
        eleve = Eleve(
            matricule=Eleve.generer_matricule(classe),
            nom_complet=nom_complet,
            classe_id=classe_id,
            date_naissance=date_naissance,
            sexe=sexe,
            telephone_parent=telephone_parent or None,
        )
        db.session.add(eleve)
        db.session.flush()

        # Création automatique du compte utilisateur de l'élève (document
        # complémentaire, §4, sept. 2026) : identifiant technique basé sur
        # le matricule (unique), mot de passe généré une seule fois — à
        # communiquer à la famille, il ne sera plus jamais réaffiché.
        email_auto = f"{eleve.matricule.lower()}@eleves.omega-academie.local"
        mot_de_passe_auto = secrets.token_urlsafe(6)
        compte_eleve = User(
            nom_complet=nom_complet, email=email_auto, role="eleve", statut="actif",
        )
        compte_eleve.set_mot_de_passe(mot_de_passe_auto)
        db.session.add(compte_eleve)
        db.session.flush()
        eleve.user_id = compte_eleve.id

        eleve.actualiser_statut_dossier()
        db.session.add(HistoriqueScolaire(
            eleve_id=eleve.id,
            classe_id=classe_id,
            annee_scolaire=Eleve.annee_scolaire_courante(),
            resultat="en_cours",
        ))
        db.session.commit()

        flash(
            f"Élève inscrit avec le matricule {eleve.matricule}. "
            f"Compte élève créé — identifiant : {email_auto} / mot de passe : {mot_de_passe_auto} "
            f"(à noter et communiquer à la famille, il ne sera plus affiché).",
            "info",
        )
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    return render_template("eleves/nouveau.html", classes=classes)


@eleves_bp.route("/<int:eleve_id>")
@login_required
def detail(eleve_id):
    eleve = Eleve.query.get_or_404(eleve_id)
    # Accès basé sur la relation, pas sur le rôle : n'importe quel compte
    # (personnel compris) peut être parent d'un élève. Le personnel de
    # gestion voit toujours tout ; les autres doivent être un parent lié.
    est_lie_comme_parent = current_user in eleve.parents
    est_soi_meme = current_user.role == "eleve" and eleve.user_id == current_user.id
    if current_user.role not in ROLES_LECTURE and current_user.role != "developpeur" and not est_lie_comme_parent and not est_soi_meme:
        abort(403)
    classe_superieure = Classe.query.filter_by(niveau=eleve.classe.niveau + 1, annee_scolaire=eleve.classe.annee_scolaire).first()
    parents_disponibles = (
        # Tout le personnel peut être parent (décision de la direction,
        # sept. 2026) — on ne filtre plus sur role="parent". Seul un
        # compte élève ne peut pas être le parent de lui-même.
        User.query.filter(User.statut == "actif", User.role != "eleve").order_by(User.nom_complet).all()
        if (current_user.role in ROLES_GESTION or current_user.role == "developpeur") else []
    )
    annee = Eleve.annee_scolaire_courante()
    moyenne = moyenne_eleve(eleve, annee)
    return render_template(
        "eleves/detail.html", eleve=eleve, classe_superieure=classe_superieure,
        parents_disponibles=parents_disponibles, statuts_dossier=STATUTS_DOSSIER,
        max_parents=MAX_PARENTS_PAR_ELEVE, moyenne=moyenne,
        reussite=a_reussi(eleve, annee), seuil=seuil_reussite_pour_classe(eleve.classe),
    )


@eleves_bp.route("/<int:eleve_id>/parent/ajouter", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def ajouter_parent(eleve_id):
    eleve = Eleve.query.get_or_404(eleve_id)
    parent_id = request.form.get("parent_id", type=int)

    # Tout compte actif peut être lié comme parent (personnel compris),
    # sauf un compte élève (ne peut pas être son propre parent).
    parent = User.query.filter(User.id == parent_id, User.statut == "actif", User.role != "eleve").first()
    if not parent:
        flash("Compte introuvable ou pas encore actif.", "error")
    elif parent in eleve.parents:
        flash(f"{parent.nom_complet} est déjà lié à {eleve.nom_complet}.", "error")
    elif len(eleve.parents) >= MAX_PARENTS_PAR_ELEVE:
        flash(f"Un élève ne peut avoir plus de {MAX_PARENTS_PAR_ELEVE} parents liés. Retire d'abord un parent existant.", "error")
    else:
        eleve.parents.append(parent)
        # Le dossier se complète automatiquement avec les informations du
        # parent (téléphone) — pas de ressaisie (décision de la
        # direction, sept. 2026).
        if not eleve.telephone_parent and parent.telephone:
            eleve.telephone_parent = parent.telephone
        eleve.actualiser_statut_dossier()
        db.session.commit()
        flash(f"{parent.nom_complet} est maintenant lié à {eleve.nom_complet}.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))


@eleves_bp.route("/<int:eleve_id>/parent/<int:parent_id>/retirer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def retirer_parent(eleve_id, parent_id):
    eleve = Eleve.query.get_or_404(eleve_id)
    parent = User.query.get_or_404(parent_id)
    if parent in eleve.parents:
        eleve.parents.remove(parent)
        eleve.actualiser_statut_dossier()
        db.session.commit()
        flash(f"{parent.nom_complet} délié de {eleve.nom_complet}.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))


@eleves_bp.route("/<int:eleve_id>/passage", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def passage(eleve_id):
    eleve = Eleve.query.get_or_404(eleve_id)
    classe_actuelle = eleve.classe
    annee = Eleve.annee_scolaire_courante()

    classe_suivante = Classe.query.filter_by(niveau=classe_actuelle.niveau + 1, annee_scolaire=classe_actuelle.annee_scolaire).first()
    if not classe_suivante:
        flash("Aucune classe supérieure n'est encore définie après cette classe.", "error")
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    # Admission automatique selon la moyenne (document complémentaire,
    # sept. 2026) : Primaire >= 5/10, Collège >= 10/20. Le secrétariat ne
    # décide plus lui-même — le système calcule et applique le critère.
    moyenne = moyenne_eleve(eleve, annee)
    reussite = a_reussi(eleve, annee)

    dernier_historique = (
        HistoriqueScolaire.query.filter_by(eleve_id=eleve.id, classe_id=classe_actuelle.id)
        .order_by(HistoriqueScolaire.id.desc())
        .first()
    )

    if reussite is None:
        flash(
            f"Impossible de déterminer l'admission automatiquement : aucune note "
            f"enregistrée pour {eleve.nom_complet} cette année. Saisis d'abord ses notes.",
            "error",
        )
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    if not reussite:
        if dernier_historique:
            dernier_historique.resultat = "echec"
        db.session.commit()
        flash(
            f"{eleve.nom_complet} n'atteint pas la moyenne requise ({moyenne} — "
            f"seuil {seuil_reussite_pour_classe(classe_actuelle)}) : il/elle redouble "
            f"{classe_actuelle.nom}, pas de passage en classe supérieure.",
            "error",
        )
        return redirect(url_for("eleves.detail", eleve_id=eleve.id))

    if dernier_historique:
        dernier_historique.resultat = "admis"

    eleve.classe_id = classe_suivante.id
    db.session.add(HistoriqueScolaire(
        eleve_id=eleve.id,
        classe_id=classe_suivante.id,
        annee_scolaire=annee,
        resultat="en_cours",
    ))
    db.session.commit()
    flash(f"Admission automatique validée (moyenne {moyenne}) — {eleve.nom_complet} passe en {classe_suivante.nom}.", "info")
    return redirect(url_for("eleves.detail", eleve_id=eleve.id))

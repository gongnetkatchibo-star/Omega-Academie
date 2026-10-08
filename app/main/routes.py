from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from datetime import datetime

from app import limiter
from app.extensions import db
from app.main import main_bp
from app.models.user import ROLES_DIRECTION, ROLES_PERSONNEL
from app.models.eleve import Eleve
from app.models.telephone import NumeroTelephone, OPERATEURS_TCHAD
from app.utils import normaliser_numero_tchad
from app.services.guides import guides_pour, guide_pour, DESCRIPTION_PLATEFORME
from app.services.temps import maintenant
from app.services.tableau_de_bord import donnees_tableau_de_bord


def _modules_pour(role):
    """Construit la liste des cartes du tableau de bord selon le rôle."""
    modules = []

    if role in ROLES_DIRECTION or role in ["secretaire"]:
        modules.append({"label": "Classes", "endpoint": "classes.liste",
                         "description": "Créer et consulter les classes."})
        modules.append({"label": "Élèves", "endpoint": "eleves.liste",
                         "description": "Inscriptions, dossiers, passages de classe."})
        modules.append({"label": "Tests de niveau", "endpoint": "tests_niveau.liste",
                         "description": "Admissions à évaluer."})

    if role in ROLES_DIRECTION or role in ["responsable_pedagogique"]:
        modules.append({"label": "Enseignants", "endpoint": "enseignants.liste",
                         "description": "Profils et affectations."})
        modules.append({"label": "Suivi des cours", "endpoint": "suivi_cours.tableau",
                         "description": "Avancement des programmes par classe."})
        modules.append({"label": "Alertes", "endpoint": "alertes.tableau",
                         "description": "Absences répétées et moyennes faibles."})

    if role == "enseignant":
        modules.append({"label": "Mon emploi du temps", "endpoint": "emploi_du_temps.moi",
                         "description": "Mes créneaux de cours."})
        modules.append({"label": "Classes", "endpoint": "classes.liste",
                         "description": "Voir les classes et accéder à la saisie de notes."})

    if role in ROLES_DIRECTION or role in ["comptable"]:
        modules.append({"label": "Scolarité", "endpoint": "finances.liste", "groupe": "Finances",
                         "description": "Frais dus, paiements, soldes par élève."})
        modules.append({"label": "Caisse", "endpoint": "caisse.liste", "groupe": "Finances",
                         "description": "Recettes et dépenses générales de l'école."})
        modules.append({"label": "Salaires", "endpoint": "salaires.liste", "groupe": "Finances",
                         "description": "Journal de paie du personnel."})

    if role in ["fondateur", "administrateur_general", "directeur_primaire", "directeur_college", "comptable"]:
        modules.append({"label": "Statistiques", "endpoint": "statistiques.tableau",
                         "description": "Effectifs, recouvrement, indicateurs de l'école."})

    if role in ROLES_DIRECTION or role in ["secretaire"]:
        modules.append({"label": "Demandes de comptes", "endpoint": "secretariat.demandes",
                         "description": "Approuver ou refuser les inscriptions en attente."})

    from app.services.permissions import role_a_acces
    if role != "developpeur" and role_a_acces(role, "gestion_roles", []):
        modules.append({"label": "Rôles des comptes", "endpoint": "dev.utilisateurs",
                         "description": "Attribuer un rôle à un compte."})

    modules.append({"label": "Bibliothèque", "endpoint": "bibliotheque.liste",
                     "description": "Livres, cours et exercices numériques."})
    modules.append({"label": "Annonces", "endpoint": "communication.liste",
                     "description": "Communications internes."})
    modules.append({"label": "Assistant", "endpoint": "assistant.index",
                     "description": "Aperçu de l'assistant (aucune IA connectée)."})

    if role == "developpeur":
        # Accès complet : toutes les cartes, direction comme personnel.
        modules.append({"label": "Classes", "endpoint": "classes.liste", "description": "Créer et consulter les classes."})
        modules.append({"label": "Élèves", "endpoint": "eleves.liste", "description": "Inscriptions, dossiers, passages de classe."})
        modules.append({"label": "Tests de niveau", "endpoint": "tests_niveau.liste", "description": "Admissions à évaluer."})
        modules.append({"label": "Enseignants", "endpoint": "enseignants.liste", "description": "Profils et affectations."})
        modules.append({"label": "Suivi des cours", "endpoint": "suivi_cours.tableau", "description": "Avancement des programmes par classe."})
        modules.append({"label": "Alertes", "endpoint": "alertes.tableau", "description": "Absences répétées et moyennes faibles."})
        modules.append({"label": "Scolarité", "endpoint": "finances.liste", "groupe": "Finances", "description": "Frais dus, paiements, soldes par élève."})
        modules.append({"label": "Caisse", "endpoint": "caisse.liste", "groupe": "Finances", "description": "Recettes et dépenses générales de l'école."})
        modules.append({"label": "Salaires", "endpoint": "salaires.liste", "groupe": "Finances", "description": "Journal de paie du personnel."})
        modules.append({"label": "Statistiques", "endpoint": "statistiques.tableau", "description": "Effectifs, recouvrement, indicateurs de l'école."})
        modules.append({"label": "Demandes de comptes", "endpoint": "secretariat.demandes", "description": "Approuver ou refuser les inscriptions en attente."})
        modules.insert(0, {"label": "Espace développeur", "endpoint": "dev.utilisateurs",
                            "description": "Attribuer les rôles et gérer les comptes."})

    return modules


@main_bp.route("/")
def index():
    if not current_user.is_authenticated:
        return render_template("main/accueil_public.html")

    user = current_user
    modules = _modules_pour(user.role)

    mon_dossier_eleve = None
    if user.role == "eleve":
        mon_dossier_eleve = Eleve.query.filter_by(user_id=user.id, actif=True).first()

    # Tout compte peut avoir des enfants liés (tout le personnel peut
    # être parent, décision de la direction, sept. 2026) — pas seulement
    # le rôle "parent". On affiche la section "Mes enfants" dès qu'il y
    # en a, en plus de l'espace propre au rôle.
    enfants = sorted((e for e in user.enfants if e.actif), key=lambda e: e.nom_complet)

    # Rappel de sauvegarde — seulement visible pour ceux qui ont
    # réellement le droit d'en déclencher une (respecte la matrice de
    # permissions, pas une liste de rôles fixe — sept. 2026).
    alerte_sauvegarde = None
    from app.services.permissions import role_a_acces
    if role_a_acces(user.role, "sauvegarde", []):
        from app.models.journal import JournalAction
        derniere = (
            JournalAction.query.filter_by(action="sauvegarde_exportee")
            .order_by(JournalAction.date_action.desc()).first()
        )
        jours_limite = 14
        if derniere is None:
            alerte_sauvegarde = "Aucune sauvegarde n'a encore été téléchargée."
        else:
            jours_ecoules = (maintenant() - derniere.date_action).days
            if jours_ecoules >= jours_limite:
                alerte_sauvegarde = f"Dernière sauvegarde téléchargée il y a {jours_ecoules} jours."

    return render_template(
        "main/index.html",
        user=user,
        modules=modules,
        enfants=enfants,
        dossier_eleve=mon_dossier_eleve,
        est_personnel=user.role in ROLES_PERSONNEL,
        est_direction=user.role in ROLES_DIRECTION,
        alerte_sauvegarde=alerte_sauvegarde,
        guides=guides_pour(user),
        description_plateforme=DESCRIPTION_PLATEFORME,
        tableau=donnees_tableau_de_bord(user),
        aujourd_hui=maintenant().date(),
    )


@main_bp.route("/recherche")
@login_required
def recherche():
    """Recherche par nom dans tout ce que le compte a le droit de voir :
    élèves, enseignants, comptes."""
    from app.models.classe import Classe
    from app.models.enseignant import Enseignant
    from app.models.user import User
    from app.services.cycles import cycle_du_role, filtrer_par_cycle
    from app.services.permissions import role_a_acces

    role = current_user.role
    direction = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]
    voit_eleves = role == "enseignant" or role_a_acces(role, "classes", ["secretaire"] + direction)
    voit_enseignants = role_a_acces(role, "enseignants", direction + ["responsable_pedagogique"])
    voit_comptes = role_a_acces(role, "gestion_roles", ["developpeur"])
    if not (voit_eleves or voit_enseignants or voit_comptes):
        abort(403)

    terme = request.args.get("q", "").strip()
    eleves = enseignants = comptes = []
    if len(terme) >= 2:
        motif = f"%{terme}%"
        if voit_eleves:
            du_cycle = [c.id for c in filtrer_par_cycle(Classe.query.all(), cycle_du_role(role))]
            eleves = (
                Eleve.query.filter(Eleve.actif.is_(True), Eleve.classe_id.in_(du_cycle))
                .filter(db.or_(Eleve.nom_complet.ilike(motif), Eleve.matricule.ilike(motif)))
                .order_by(Eleve.nom_complet).limit(30).all()
            )
        if voit_enseignants:
            enseignants = (
                Enseignant.query.join(User, Enseignant.user_id == User.id)
                .filter(User.nom_complet.ilike(motif)).order_by(User.nom_complet).limit(15).all()
            )
        if voit_comptes:
            comptes = (
                User.query.filter(db.or_(User.nom_complet.ilike(motif), User.email.ilike(motif)))
                .order_by(User.nom_complet).limit(15).all()
            )
    return render_template(
        "main/recherche.html", terme=terme, eleves=eleves, enseignants=enseignants, comptes=comptes,
        voit_finances=role_a_acces(role, "finances", ["comptable", "fondateur", "administrateur_general"]),
    )


@main_bp.route("/guide/<cle>")
@login_required
def guide(cle):
    """Guide d'utilisation d'un module — seulement ceux des modules
    auxquels le compte a accès."""
    fiche = guide_pour(current_user, cle)
    if fiche is None:
        abort(404)
    return render_template("main/guide.html", guide=fiche)


@main_bp.route("/profil")
@login_required
def profil():
    numeros = NumeroTelephone.query.filter_by(user_id=current_user.id).all()
    return render_template("main/profil.html", numeros=numeros, operateurs=OPERATEURS_TCHAD)


@main_bp.route("/profil/mot-de-passe", methods=["POST"])
@login_required
def changer_mot_de_passe():
    actuel = request.form.get("mot_de_passe_actuel", "")
    nouveau = request.form.get("nouveau_mot_de_passe", "")
    confirmation = request.form.get("confirmation", "")
    if not current_user.verifier_mot_de_passe(actuel):
        flash("Le mot de passe actuel est incorrect.", "error")
    elif len(nouveau) < 8:
        flash("Le nouveau mot de passe doit faire au moins 8 caractères.", "error")
    elif nouveau != confirmation:
        flash("Les deux saisies du nouveau mot de passe ne correspondent pas.", "error")
    elif nouveau == actuel:
        flash("Le nouveau mot de passe doit être différent de l'actuel.", "error")
    else:
        from app.services.journal import journaliser
        current_user.set_mot_de_passe(nouveau)
        journaliser("changement_mot_de_passe", cible_type="User", cible_id=current_user.id)
        db.session.commit()
        flash("Mot de passe modifié.", "info")
    return redirect(url_for("main.profil"))


@main_bp.route("/profil/genre", methods=["POST"])
@login_required
def modifier_genre():
    genre = request.form.get("genre")
    if genre in ("M", "F"):
        current_user.genre = genre
        db.session.commit()
        flash("Genre enregistré.", "info")
    return redirect(url_for("main.profil"))


@main_bp.route("/profil/numero/ajouter", methods=["POST"])
@login_required
def ajouter_numero():
    saisie = request.form.get("numero", "")
    operateur = request.form.get("operateur")
    libelle = request.form.get("libelle", "").strip()

    numero_normalise = normaliser_numero_tchad(saisie)
    if not numero_normalise:
        flash("Numéro invalide — un mobile tchadien a 8 chiffres et commence par 6 ou 9 (ex. 66 12 34 56).", "error")
        return redirect(url_for("main.profil"))

    if operateur not in dict(OPERATEURS_TCHAD):
        flash("Merci de choisir l'opérateur.", "error")
        return redirect(url_for("main.profil"))

    db.session.add(NumeroTelephone(
        user_id=current_user.id, numero=numero_normalise, operateur=operateur, libelle=libelle or None,
    ))
    db.session.commit()
    flash("Numéro ajouté.", "info")
    return redirect(url_for("main.profil"))


@main_bp.route("/profil/numero/<int:numero_id>/supprimer", methods=["POST"])
@login_required
def supprimer_numero(numero_id):
    numero = db.get_or_404(NumeroTelephone, numero_id)
    if numero.user_id != current_user.id:
        from flask import abort
        abort(403)
    db.session.delete(numero)
    db.session.commit()
    flash("Numéro supprimé.", "info")
    return redirect(url_for("main.profil"))


@main_bp.route("/etablissement/<any(logo, filigrane):image>")
@login_required
def image_ecole(image):
    """Logo ou filigrane de l'école courante (stockés en base)."""
    from flask import Response, abort
    from app.services.tenant import ecole_courante

    ecole = ecole_courante()
    contenu = getattr(ecole, image, None) if ecole else None
    if not contenu:
        abort(404)
    reponse = Response(contenu, mimetype=getattr(ecole, f"{image}_mime") or "image/png")
    reponse.headers["Cache-Control"] = "private, max-age=3600"
    return reponse


@main_bp.route("/verifier", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def verifier_formulaire():
    """Page publique : saisir à la main le code imprimé sous le QR code."""
    from app.services.verification import normaliser_code

    if request.method == "POST":
        code = normaliser_code(request.form.get("code"))
        if code:
            return redirect(url_for("main.verifier", code=code))
        flash("Ce code n'a pas le bon format. Il compte 12 caractères, par exemple K7QF-3M9X-PA2D.", "error")
    return render_template("main/verifier.html", document=None, recherche=False)


@main_bp.route("/verifier/<code>")
@limiter.limit("30 per minute")
def verifier(code):
    """Page publique ouverte par le QR code d'un document officiel. Elle
    n'affiche que ce qui figure déjà sur le papier."""
    from sqlalchemy import select
    from app.models.ecole import Ecole
    from app.services.verification import trouver

    document = trouver(code)
    ecole = None
    if document:
        ecole = db.session.execute(
            select(Ecole).where(Ecole.id == document.ecole_id).execution_options(tous_etablissements=True)
        ).scalar_one_or_none()
    reponse = render_template("main/verifier.html", document=document, ecole_emettrice=ecole, recherche=True, code=code)
    # Jamais indexée par les moteurs de recherche : elle contient des noms d'élèves.
    return reponse, (200 if document else 404), {"X-Robots-Tag": "noindex, nofollow"}


@main_bp.route("/langue/<code>")
def changer_langue(code):
    """Bouton FR / ع : retenu sur le compte (et dans la session pour une
    personne non connectée), puis retour à la page d'où l'on vient."""
    from urllib.parse import urlparse
    from flask import session
    from app.services.langues import LANGUES

    if code not in LANGUES:
        abort(404)
    session["langue"] = code
    request.environ.pop("toumai.langue", None)
    if current_user.is_authenticated and current_user.langue != code:
        current_user.langue = code
        db.session.commit()
    retour = request.referrer or ""
    cible = urlparse(retour)
    if not retour or (cible.netloc and cible.netloc != request.host):
        return redirect(url_for("main.index"))
    return redirect(cible.path + (f"?{cible.query}" if cible.query else ""))

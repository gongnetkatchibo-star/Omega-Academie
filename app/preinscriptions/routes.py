"""Pré-inscription en ligne : une famille dépose une demande depuis la
page publique ; le secrétariat la convoque au test de niveau ou la refuse."""

import secrets
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort, g, current_app
from flask_login import login_required, current_user

from app import limiter
from app.extensions import db
from app.preinscriptions import preinscriptions_bp
from app.models.classe import Classe
from app.models.ecole import Ecole
from app.models.eleve import Eleve
from app.models.preinscription import PreInscription, STATUTS_PREINSCRIPTION, LIBELLES_STATUT_PREINSCRIPTION
from app.services.cycles import cycle_du_role, filtrer_par_cycle, classe_dans_le_cycle
from app.services.pagination import paginer
from app.services.suivi_eleve import date_du_formulaire
from app.utils import roles_required

ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]
MODULE = "tests_niveau"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _ecoles_ouvertes():
    return Ecole.query.filter_by(actif=True).order_by(Ecole.nom).all()


def _nouvelle_reference():
    while True:
        reference = "PI-" + "".join(secrets.choice(ALPHABET) for _ in range(6))
        existe = PreInscription.query.execution_options(tous_etablissements=True).filter_by(reference=reference).first()
        if not existe:
            return reference


# ------------------------------------------------------------ page publique
@preinscriptions_bp.route("/demande")
def choisir_ecole():
    ecoles = _ecoles_ouvertes()
    if len(ecoles) == 1:
        return redirect(url_for("preinscriptions.demande", ecole_id=ecoles[0].id))
    return render_template("preinscriptions/choisir_ecole.html", ecoles=ecoles)


@preinscriptions_bp.route("/demande/<int:ecole_id>", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def demande(ecole_id):
    ecole = db.session.get(Ecole, ecole_id)
    if ecole is None or not ecole.actif:
        abort(404)
    # Toute la suite de la requête se passe dans cette école : lectures
    # filtrées et nouvelle demande rattachée à elle.
    g.ecole_id = ecole.id
    classes = (
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante())
        .order_by(Classe.niveau, Classe.nom).all()
    )

    if request.method == "POST":
        if request.form.get("site_web"):  # champ invisible : rempli seulement par les robots
            return redirect(url_for("preinscriptions.merci", reference="-"))
        from app.services.numeros import normaliser_numero

        nom = request.form.get("nom_candidat", "").strip()
        nom_parent = request.form.get("nom_parent", "").strip()
        telephone = normaliser_numero(request.form.get("telephone_parent"), ecole.pays)
        email = request.form.get("email_parent", "").strip().lower()
        classe = next((c for c in classes if c.id == request.form.get("classe_demandee_id", type=int)), None)
        erreur = None
        if not nom or not nom_parent:
            erreur = "Indique le nom de l'enfant et celui du parent."
        elif not telephone:
            erreur = "Numéro de téléphone invalide."
        elif email and ("@" not in email or len(email) > 150):
            erreur = "Adresse email invalide."
        if erreur:
            flash(erreur, "error")
            return render_template("preinscriptions/demande.html", etab=ecole, classes=classes, form=request.form)

        sexe = request.form.get("sexe")
        demande_obj = PreInscription(
            ecole_id=ecole.id, reference=_nouvelle_reference(), nom_candidat=nom[:120],
            sexe=sexe if sexe in ("M", "F") else None,
            date_naissance=date_du_formulaire("date_naissance", facultative=True),
            lieu_naissance=request.form.get("lieu_naissance", "").strip()[:120] or None,
            classe_demandee_id=classe.id if classe else None,
            ecole_origine=request.form.get("ecole_origine", "").strip()[:150] or None,
            nom_parent=nom_parent[:120], telephone_parent=telephone, email_parent=email or None,
            message=request.form.get("message", "").strip()[:1000] or None,
        )
        db.session.add(demande_obj)
        db.session.commit()
        _prevenir_le_secretariat(demande_obj, ecole)
        return redirect(url_for("preinscriptions.merci", reference=demande_obj.reference))

    return render_template("preinscriptions/demande.html", etab=ecole, classes=classes, form={})


@preinscriptions_bp.route("/merci/<reference>")
def merci(reference):
    return render_template("preinscriptions/merci.html", reference=reference)


def _prevenir_le_secretariat(demande_obj, ecole):
    from app.models.user import User
    from app.extensions import envoyer_email

    destinataires = [
        u.email for u in User.query.filter(User.statut == "actif", User.role.in_(["secretaire", "fondateur"])).all()
        if u.email and not u.email.endswith(".local")
    ]
    if not destinataires:
        return
    classe = demande_obj.classe_demandee.nom if demande_obj.classe_demandee else "non précisée"
    try:
        envoyer_email(
            destinataires, f"Nouvelle pré-inscription — {demande_obj.nom_candidat}",
            (f"Bonjour,\n\nUne famille vient de pré-inscrire {demande_obj.nom_candidat} (classe demandée : {classe}).\n"
             f"Parent : {demande_obj.nom_parent} — {demande_obj.telephone_parent}\n"
             f"Référence : {demande_obj.reference}\n\nLa demande attend dans « Pré-inscriptions ».\n\n{ecole.nom}"),
            nom_expediteur=ecole.nom,
        )
    except Exception:  # un email en panne ne doit pas faire échouer la demande
        current_app.logger.exception("Email de pré-inscription non envoyé")


# ------------------------------------------------------------ secrétariat
def _visible(demande_obj):
    cycle = cycle_du_role(current_user.role)
    return not cycle or demande_obj.classe_demandee is None or classe_dans_le_cycle(demande_obj.classe_demandee, cycle)


@preinscriptions_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def liste():
    statut = request.args.get("statut", "nouvelle")
    requete = PreInscription.query
    if statut in LIBELLES_STATUT_PREINSCRIPTION:
        requete = requete.filter_by(statut=statut)
    cycle = cycle_du_role(current_user.role)
    if cycle:
        ids = [c.id for c in filtrer_par_cycle(Classe.query.all(), cycle)]
        requete = requete.filter(db.or_(PreInscription.classe_demandee_id.is_(None),
                                        PreInscription.classe_demandee_id.in_(ids)))
    page = paginer(requete.order_by(PreInscription.date_creation.desc()))
    return render_template("preinscriptions/liste.html", page=page, statut=statut, statuts=STATUTS_PREINSCRIPTION)


@preinscriptions_bp.route("/<int:demande_id>", methods=["GET"])
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def detail(demande_id):
    demande_obj = db.get_or_404(PreInscription, demande_id)
    if not _visible(demande_obj):
        abort(403)
    classes = filtrer_par_cycle(
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau, Classe.nom).all(),
        cycle_du_role(current_user.role),
    )
    from app.services.temps import aujourd_hui
    return render_template("preinscriptions/detail.html", d=demande_obj, classes=classes, aujourd_hui=aujourd_hui())


@preinscriptions_bp.route("/<int:demande_id>/convoquer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def convoquer(demande_id):
    """Crée le test de niveau du candidat et prévient la famille."""
    from app.models.test_niveau import TestNiveau

    demande_obj = db.get_or_404(PreInscription, demande_id)
    if not _visible(demande_obj):
        abort(403)
    classes = filtrer_par_cycle(
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).all(), cycle_du_role(current_user.role),
    )
    classe = next((c for c in classes if c.id == request.form.get("classe_id", type=int)), None)
    if demande_obj.statut != "nouvelle" or classe is None:
        flash("Choisis la classe du test.", "error")
        return redirect(url_for("preinscriptions.detail", demande_id=demande_obj.id))
    date_test = date_du_formulaire("date_test")
    test = TestNiveau(
        nom_candidat=demande_obj.nom_candidat, date_naissance_candidat=demande_obj.date_naissance,
        sexe_candidat=demande_obj.sexe, telephone_parent=demande_obj.telephone_parent,
        classe_demandee_id=classe.id, date_test=date_test, evaluateur_id=current_user.id,
        observation=f"Pré-inscription {demande_obj.reference}",
    )
    db.session.add(test)
    db.session.flush()
    demande_obj.test_niveau_id, demande_obj.statut, demande_obj.traite_par_id = test.id, "convoquee", current_user.id
    db.session.commit()
    heure = request.form.get("heure", "").strip()[:10]
    _ecrire_a_la_famille(
        demande_obj, f"Pré-inscription {demande_obj.reference} — convocation au test",
        (f"{demande_obj.nom_candidat} est convoqué(e) au test de niveau (classe {classe.nom}) "
         f"le {date_test.strftime('%d/%m/%Y')}{(' à ' + heure) if heure else ''}."),
    )
    flash("Candidat convoqué : le test de niveau est créé.", "info")
    return redirect(url_for("tests_niveau.liste"))


@preinscriptions_bp.route("/<int:demande_id>/refuser", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def refuser(demande_id):
    demande_obj = db.get_or_404(PreInscription, demande_id)
    if not _visible(demande_obj):
        abort(403)
    if demande_obj.statut != "nouvelle":
        return redirect(url_for("preinscriptions.detail", demande_id=demande_obj.id))
    demande_obj.statut, demande_obj.traite_par_id = "refusee", current_user.id
    demande_obj.motif_refus = request.form.get("motif_refus", "").strip()[:250] or None
    db.session.commit()
    texte = f"Nous ne pouvons pas donner suite à la pré-inscription de {demande_obj.nom_candidat}."
    if demande_obj.motif_refus:
        texte += f"\nMotif : {demande_obj.motif_refus}"
    _ecrire_a_la_famille(demande_obj, f"Pré-inscription {demande_obj.reference}", texte)
    flash("Demande refusée.", "info")
    return redirect(url_for("preinscriptions.liste"))


def _ecrire_a_la_famille(demande_obj, sujet, texte):
    if not demande_obj.email_parent:
        return
    from app.services.notifications import notifier, signature
    notifier([demande_obj.email_parent], sujet, f"Bonjour {demande_obj.nom_parent},\n\n{texte}\n\n{signature()}")

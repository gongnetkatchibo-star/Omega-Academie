from flask import render_template, make_response, request
from flask_login import login_required

from app.models.eleve import Eleve
from app.models.parametre import ParametreEtablissement
from app.documents_officiels import documents_officiels_bp
from app.utils import roles_required, html_vers_pdf, piece_jointe
from app.services.documents_officiels import (
    numero_reference, contexte_entete_officiel, signature_du_document,
)
from app.services.journal import journaliser
from app.extensions import db
from app.services import signature_ecole
from app.services.tenant import ecole_courante

ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]

DOCUMENTS = {
    "certificat": ("CERT", "Certificat de scolarité", "documents_officiels/certificat_scolarite.html", "certificat_scolarite"),
    "attestation": ("ATTEST", "Attestation de fréquentation", "documents_officiels/attestation_frequentation.html", "attestation_frequentation"),
    "radiation": ("RAD", "Certificat de radiation", "documents_officiels/certificat_radiation.html", "certificat_radiation"),
}


def signataire_depuis_formulaire():
    """Signataire saisi juste avant la génération (pré-rempli avec les
    paramètres de l'établissement)."""
    parametre = ParametreEtablissement.get()
    genre = request.form.get("signataire_genre") or parametre.genre_directeur or "M"
    return {
        "nom": request.form.get("signataire_nom", "").strip() or (parametre.nom_directeur or ""),
        "qualite": request.form.get("signataire_qualite", "").strip() or (parametre.titre_directeur or "Directeur"),
        "genre": genre if genre in ("M", "F") else "M",
    }


def signature_demandee(signataire=None):
    """La case « Imprimer la signature et le cachet » du formulaire. La
    signature enregistrée est celle du signataire de l'école : elle ne
    s'imprime jamais sous le nom de quelqu'un d'autre."""
    if request.form.get("signature_imprimee") != "on":
        return False
    if signataire is None:
        return True
    return signataire["nom"] == (ParametreEtablissement.get().nom_directeur or "")


def _generer(eleve_id, type_doc):
    code, libelle, modele, prefixe_fichier = DOCUMENTS[type_doc]
    eleve = db.get_or_404(Eleve, eleve_id)
    from flask import abort
    from flask_login import current_user
    from app.services.cycles import cycle_du_role, classe_dans_le_cycle
    if not classe_dans_le_cycle(eleve.classe, cycle_du_role(current_user.role)):
        abort(403)
    # Le certificat de radiation ne concerne qu'un élève parti, le
    # certificat de scolarité qu'un élève inscrit.
    if (type_doc == "radiation" and eleve.actif) or (type_doc == "certificat" and not eleve.actif):
        abort(404)

    if request.method == "GET":
        return render_template(
            "documents_officiels/preparer.html",
            eleve=eleve, libelle=libelle, parametre=ParametreEtablissement.get(),
            signature_disponible=signature_ecole.disponible(ecole_courante()),
        )

    from app.services.verification import emettre_document_eleve, bloc_verification

    signataire = signataire_depuis_formulaire()
    numero = numero_reference(code)
    journaliser(f"generation_{prefixe_fichier}", details=f"{eleve.nom_complet} — {numero}", cible_type="Eleve", cible_id=eleve.id)
    document = emettre_document_eleve(type_doc, eleve, numero, signataire)
    db.session.commit()

    contexte = contexte_entete_officiel()
    contexte["signataire"] = signataire
    contexte["signature_uri"] = signature_du_document(signature_demandee(signataire))
    contexte["verification"] = bloc_verification(document)
    html = render_template(modele, eleve=eleve, numero=numero, **contexte)
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = piece_jointe(f"{prefixe_fichier}_{eleve.matricule}.pdf")
    return reponse


@documents_officiels_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def index():
    """Entrée du menu : retrouver un élève et éditer ses documents."""
    from flask_login import current_user
    from app.models.classe import Classe
    from app.services.cycles import cycle_du_role, filtrer_par_cycle
    from app.services.pagination import paginer

    terme = request.args.get("q", "").strip()
    classes = filtrer_par_cycle(Classe.query.all(), cycle_du_role(current_user.role))
    requete = Eleve.query.filter(Eleve.actif.is_(True), Eleve.classe_id.in_([c.id for c in classes]))
    if terme:
        motif = f"%{terme}%"
        requete = requete.filter(db.or_(Eleve.nom_complet.ilike(motif), Eleve.matricule.ilike(motif)))
    page = paginer(requete.order_by(Eleve.nom_complet))
    return render_template("documents_officiels/index.html", page=page, terme=terme)


@documents_officiels_bp.route("/eleve/<int:eleve_id>/certificat", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def certificat_scolarite(eleve_id):
    return _generer(eleve_id, "certificat")


@documents_officiels_bp.route("/eleve/<int:eleve_id>/attestation", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def attestation_frequentation(eleve_id):
    return _generer(eleve_id, "attestation")


@documents_officiels_bp.route("/eleve/<int:eleve_id>/radiation", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def certificat_radiation(eleve_id):
    return _generer(eleve_id, "radiation")


def _classes_accessibles():
    from flask_login import current_user
    from app.models.classe import Classe
    from app.services.cycles import cycle_du_role, filtrer_par_cycle

    classes = Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau, Classe.nom).all()
    return filtrer_par_cycle(classes, cycle_du_role(current_user.role))


@documents_officiels_bp.route("/cartes", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="eleves")
def cartes():
    """Cartes d'élève en planche A4 : toute une classe, ou un seul élève."""
    from flask import flash, redirect, url_for
    from sqlalchemy import func
    from sqlalchemy.orm import undefer

    classes = _classes_accessibles()
    ids_classes = [c.id for c in classes]
    eleve_id = request.values.get("eleve_id", type=int)
    eleve = None
    if eleve_id:
        eleve = db.get_or_404(Eleve, eleve_id)
        if not eleve.actif or eleve.classe_id not in ids_classes:
            from flask import abort
            abort(404)

    if request.method == "POST":
        classe_id = request.form.get("classe_id", type=int)
        requete = Eleve.query.options(undefer(Eleve.photo)).filter(Eleve.actif.is_(True))
        if eleve:
            eleves = requete.filter(Eleve.id == eleve.id).all()
            nom_fichier = f"carte_{eleve.matricule}"
        elif classe_id in ids_classes:
            eleves = requete.filter(Eleve.classe_id == classe_id).order_by(func.lower(Eleve.nom_complet)).all()
            nom_fichier = "cartes_" + next(c.nom for c in classes if c.id == classe_id)
        else:
            eleves = []
        if not eleves:
            flash("Choisis une classe qui a des élèves.", "error")
            return redirect(url_for("documents_officiels.cartes"))

        from app.services.cartes_eleves import planche_cartes
        from app.services.documents_officiels import signataire_par_defaut
        from app.services.verification import emettre_carte, qr_code_png

        ecole = ecole_courante()
        db.session.refresh(ecole, ["logo", "signature", "cachet"])
        adresse = url_for("main.verifier_formulaire", _external=True).split("://", 1)[-1]
        verifications = {}
        for e in eleves:
            document = emettre_carte(e, e.classe.annee_scolaire)
            verifications[e.id] = {
                "code": document.code, "adresse": adresse,
                "qr": qr_code_png(url_for("main.verifier", code=document.code, _external=True)),
            }
        journaliser("generation_cartes_eleves", details=f"{len(eleves)} carte(s) — {nom_fichier}")
        db.session.commit()

        pdf = planche_cartes(
            eleves, ecole, signataire_par_defaut(), eleves[0].classe.annee_scolaire, verifications=verifications,
            signature_png=signature_ecole.bloc_png(ecole) if signature_demandee() else None,
            avec_verso=request.form.get("verso") == "on",
        )
        reponse = make_response(pdf)
        reponse.headers["Content-Type"] = "application/pdf"
        reponse.headers["Content-Disposition"] = piece_jointe(f"{nom_fichier}.pdf")
        return reponse

    effectifs = dict(
        db.session.query(Eleve.classe_id, func.count(Eleve.id))
        .filter(Eleve.actif.is_(True), Eleve.classe_id.in_(ids_classes)).group_by(Eleve.classe_id).all()
    ) if ids_classes else {}
    avec_photo = dict(
        db.session.query(Eleve.classe_id, func.count(Eleve.id))
        .filter(Eleve.actif.is_(True), Eleve.classe_id.in_(ids_classes), Eleve.photo_mime.isnot(None))
        .group_by(Eleve.classe_id).all()
    ) if ids_classes else {}
    ecole = ecole_courante()
    return render_template(
        "documents_officiels/cartes.html", classes=classes, effectifs=effectifs, avec_photo=avec_photo, eleve=eleve,
        parametre=ParametreEtablissement.get(), signature_disponible=signature_ecole.disponible(ecole),
        classe_choisie=request.args.get("classe_id", type=int),
    )

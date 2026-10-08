from datetime import datetime

from flask import render_template, request, redirect, url_for, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.eleve import Eleve
from app.relances import relances_bp
from app.services import whatsapp
from app.services.cycles import cycle_du_role, classe_dans_le_cycle
from app.services.journal import journaliser
from app.services.modules_par_defaut import ROLES_PAR_DEFAUT
from app.services.permissions import role_a_acces
from app.services.temps import aujourd_hui

PAR_PAGE = 30

# Type d'envoi → (module dont il faut l'accès, action du journal).
TYPES_ENVOI = {
    "absence": ("absences", whatsapp.ACTION_ABSENCE),
    "relance": ("finances", whatsapp.ACTION_RELANCE),
    "contact": ("eleves", whatsapp.ACTION_CONTACT),
}


def _a_acces(module):
    return current_user.is_authenticated and role_a_acces(current_user.role, module, ROLES_PAR_DEFAUT.get(module, []))


def _eleves_visibles():
    """Élèves actifs de l'année que ce compte peut voir (un directeur de
    cycle ne voit que son cycle)."""
    annee = Eleve.annee_scolaire_courante()
    eleves = [e for e in Eleve.query.filter_by(actif=True).all() if e.classe and e.classe.annee_scolaire == annee]
    cycle = cycle_du_role(current_user.role)
    if cycle:
        eleves = [e for e in eleves if classe_dans_le_cycle(e.classe, cycle)]
    return eleves


@relances_bp.route("/")
@login_required
def index():
    voit_absences, voit_paiements = _a_acces("absences"), _a_acces("finances")
    if not (voit_absences or voit_paiements):
        abort(403)

    eleves = _eleves_visibles()
    jour = aujourd_hui()
    try:
        jour = datetime.strptime(request.args.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        pass

    absences = whatsapp.absences_a_prevenir(jour, {e.id for e in eleves}) if voit_absences else None

    paiements = None
    if voit_paiements:
        from app.services.paiements import resumes_paiements

        tous = request.args.get("tous") == "1"
        resumes = resumes_paiements(eleves)
        lignes = [
            {"eleve": e, "resume": resumes[e.id]} for e in eleves
            if (resumes[e.id]["solde"] > 0 if tous else resumes[e.id]["retard"] > 0)
        ]
        lignes.sort(key=lambda l: (-l["resume"]["retard"], -l["resume"]["solde"], l["eleve"].nom_complet))
        nb_total = len(lignes)
        nb_pages = max(1, -(-nb_total // PAR_PAGE))
        page = min(max(request.args.get("page", 1, type=int), 1), nb_pages)
        lignes = lignes[(page - 1) * PAR_PAGE: page * PAR_PAGE]
        envois = whatsapp.derniers_envois(whatsapp.ACTION_RELANCE, [l["eleve"].id for l in lignes])
        for l in lignes:
            l["contacts"] = whatsapp.contacts(l["eleve"])
            l["envoi"] = envois.get(l["eleve"].id)
        paiements = {"lignes": lignes, "tous": tous, "page": page, "nb_pages": nb_pages, "total": nb_total}

    return render_template(
        "relances/index.html", jour=jour, absences=absences, paiements=paiements,
    )


@relances_bp.route("/envoyer", methods=["POST"])
@login_required
def envoyer():
    """Note l'envoi dans le journal, puis ouvre WhatsApp avec le message
    déjà rédigé. Le numéro doit être l'un de ceux du dossier de l'élève."""
    type_envoi = request.form.get("type")
    if type_envoi not in TYPES_ENVOI:
        abort(400)
    module, action = TYPES_ENVOI[type_envoi]
    if not _a_acces(module):
        abort(403)

    eleve = db.get_or_404(Eleve, request.form.get("eleve_id", type=int))
    cycle = cycle_du_role(current_user.role)
    if cycle and not classe_dans_le_cycle(eleve.classe, cycle):
        abort(403)
    numero = request.form.get("numero", "")
    if numero not in {c["numero"] for c in whatsapp.contacts(eleve)}:
        abort(400)

    if type_envoi == "absence":
        try:
            jour = datetime.strptime(request.form.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            abort(400)
        texte = whatsapp.message_absence(eleve, jour)
        details = f"Absence du {jour.isoformat()} → {numero}"
    elif type_envoi == "relance":
        from app.services.paiements import resume_paiements
        texte = whatsapp.message_relance(eleve, resume_paiements(eleve))
        details = f"Relance de paiement → {numero}"
    else:
        texte = whatsapp.message_contact(eleve)
        details = f"Message → {numero}"

    journaliser(action, details=details, cible_type="Eleve", cible_id=eleve.id)
    db.session.commit()
    return redirect(whatsapp.lien(numero, texte))

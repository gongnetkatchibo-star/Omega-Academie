"""Prévenir les parents sur WhatsApp, sans frais (oct. 2026).

Aucun message ne part tout seul : l'application prépare le texte et le
numéro, puis ouvre WhatsApp (lien wa.me) sur le téléphone ou l'ordinateur
de la personne qui clique. Elle n'a plus qu'à appuyer sur « Envoyer ».
Pas d'abonnement, pas de prestataire, pas de coût par message : l'envoi
part du WhatsApp de l'école.

Chaque clic est noté dans le journal des actions, pour savoir quelle
famille a déjà été prévenue et par qui."""

from urllib.parse import quote

from flask import current_app

from app.models.journal import JournalAction
from app.services.numeros import normaliser_numero, numero_lisible as _numero_lisible

ACTION_ABSENCE = "whatsapp_absence"
ACTION_RELANCE = "whatsapp_relance"
ACTION_CONTACT = "whatsapp_contact"


def contacts(eleve):
    """Numéros mobiles joignables pour cet élève, sans doublon, dans
    l'ordre : parents liés (leurs numéros de profil), puis le téléphone
    parent et le contact d'urgence saisis dans le dossier."""
    from app.services.tenant import ecole_courante

    ecole = ecole_courante()
    pays = ecole.pays if ecole else None  # numéros sans indicatif : ceux du pays de l'école
    resultat, vus = [], set()

    def ajouter(nom, saisie, libelle=None):
        numero = normaliser_numero(saisie, pays)
        if numero and numero not in vus:
            vus.add(numero)
            resultat.append({"nom": nom, "numero": numero, "libelle": libelle})

    for parent in sorted(eleve.parents, key=lambda p: p.nom_complet):
        ajouter(parent.nom_complet, parent.telephone)
        for n in getattr(parent, "numeros_telephone", []):
            ajouter(parent.nom_complet, n.numero, n.libelle)
    ajouter("Téléphone du dossier", eleve.telephone_parent)
    ajouter(eleve.personne_urgence or "Contact d'urgence", eleve.telephone_urgence, "urgence")
    return resultat


def numero_lisible(numero):
    """+23566123456 → +235 66 12 34 56 (tout pays, voir services/numeros.py)."""
    return _numero_lisible(numero)


def lien(numero, texte):
    return f"https://wa.me/{numero.lstrip('+')}?text={quote(texte)}"


def _nom_ecole():
    from app.services.tenant import ecole_courante
    ecole = ecole_courante()
    return ecole.nom if ecole else "L'école"


def _date(jour):
    return current_app.jinja_env.filters["date_longue"](jour, langue="fr")


def message_absence(eleve, jour):
    absent = "absente" if eleve.sexe == "F" else "absent"
    return (
        f"Bonjour, ici {_nom_ecole()}.\n"
        f"{eleve.nom_complet} ({eleve.classe.nom}) a été {absent} le {_date(jour)}, sans justification.\n"
        f"Merci de nous contacter pour justifier cette absence."
    )


def message_relance(eleve, resume):
    fcfa = current_app.jinja_env.filters["fcfa"]
    lignes = [
        f"Bonjour, ici {_nom_ecole()}.",
        f"Il reste {fcfa(resume['solde'])} à régler pour la scolarité de {eleve.nom_complet} ({eleve.classe.nom}).",
    ]
    if resume.get("retard"):
        lignes.append(f"Dont {fcfa(resume['retard'])} dont la date limite est dépassée.")
    lignes.append("Merci de régulariser, ou de passer au secrétariat si vous souhaitez un arrangement.")
    return "\n".join(lignes)


def message_contact(eleve):
    return f"Bonjour, ici {_nom_ecole()}, au sujet de {eleve.nom_complet} ({eleve.classe.nom}).\n"


def derniers_envois(action, eleve_ids, contient=None):
    """{eleve_id: dernière JournalAction} pour ce type d'envoi. `contient` :
    texte que doit contenir le détail (ex. la date de l'absence)."""
    if not eleve_ids:
        return {}
    requete = JournalAction.query.filter(
        JournalAction.action == action, JournalAction.cible_type == "Eleve",
        JournalAction.cible_id.in_(list(eleve_ids)),
    )
    if contient:
        requete = requete.filter(JournalAction.details.contains(contient))
    resultat = {}
    for ligne in requete.order_by(JournalAction.date_action, JournalAction.id).all():
        resultat[ligne.cible_id] = ligne
    return resultat


def absences_a_prevenir(jour, eleves_visibles=None):
    """Absences non justifiées du jour, avec pour chacune les numéros des
    parents et l'envoi WhatsApp déjà fait pour cette absence (ou None)."""
    from app.models.absence import Absence
    from app.models.eleve import Eleve

    ids = {a.eleve_id for a in Absence.query.filter_by(date=jour, justifiee=False).all()}
    if eleves_visibles is not None:
        ids &= eleves_visibles
    eleves = (
        Eleve.query.filter(Eleve.id.in_(ids), Eleve.actif.is_(True)).order_by(Eleve.nom_complet).all()
        if ids else []
    )
    envois = derniers_envois(ACTION_ABSENCE, ids, contient=jour.isoformat())
    return [{"eleve": e, "contacts": contacts(e), "envoi": envois.get(e.id)} for e in eleves]

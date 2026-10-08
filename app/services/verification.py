"""QR code de vérification des documents officiels (oct. 2026).

Chaque bulletin, certificat, attestation ou reçu porte un QR code et un
code lisible (ex. K7QF-3M9X-PA2D). Scanner le QR code ou saisir le code
sur /verifier ouvre une page publique qui affiche les informations
enregistrées au moment de l'émission : de quoi démasquer un faux ou un
document retouché, sans avoir à appeler l'école."""

import base64
import secrets
from io import BytesIO

from flask import url_for
from flask_login import current_user

from app.extensions import db
from app.models.document_verifiable import DocumentVerifiable

# Sans 0/O, 1/I/L : le code se recopie à la main sans confusion.
ALPHABET_CODE = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generer_code():
    while True:
        brut = "".join(secrets.choice(ALPHABET_CODE) for _ in range(12))
        code = f"{brut[:4]}-{brut[4:8]}-{brut[8:]}"
        existe = (
            db.session.query(DocumentVerifiable.id).filter_by(code=code)
            .execution_options(tous_etablissements=True).first()
        )
        if not existe:
            return code


def normaliser_code(saisie):
    """« k7qf 3m9x-pa2d » → « K7QF-3M9X-PA2D » (ou None si ce n'est pas un code)."""
    brut = "".join(c for c in (saisie or "").upper() if c.isalnum())
    if len(brut) != 12 or any(c not in ALPHABET_CODE for c in brut):
        return None
    return f"{brut[:4]}-{brut[4:8]}-{brut[8:]}"


def emettre(type_document, cle_objet, titre, nom_eleve=None, classe=None, reference=None, details=()):
    """Enregistre l'émission d'un document et renvoie sa trace.

    Un document réimprimé à l'identique garde son code : on ne crée une
    nouvelle trace que si une information a changé (une note corrigée
    entre deux impressions, par exemple). L'ancienne trace reste valable
    pour le papier déjà remis."""
    nouveau = DocumentVerifiable(
        type_document=type_document, cle_objet=cle_objet, titre=titre,
        nom_eleve=nom_eleve, classe=classe, reference=reference,
    )
    nouveau.details = [
        tuple(str(v).replace("\u2066", "").replace("\u2069", "") for v in ligne) for ligne in details
    ]
    existant = (
        DocumentVerifiable.query
        .filter_by(cle_objet=cle_objet, titre=titre, nom_eleve=nom_eleve, classe=classe,
                   reference=reference, details_json=nouveau.details_json, annule=False)
        .order_by(DocumentVerifiable.id.desc()).first()
    )
    if existant:
        return existant
    nouveau.code = generer_code()
    if current_user and current_user.is_authenticated:
        nouveau.emis_par_id = current_user.id
    db.session.add(nouveau)
    db.session.flush()
    return nouveau


def qr_code_data_uri(texte):
    """Image PNG du QR code, prête pour un <img src=…> (PDF compris)."""
    import qrcode

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=1)
    qr.add_data(texte)
    qr.make(fit=True)
    tampon = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(tampon, format="PNG")
    return "data:image/png;base64," + base64.b64encode(tampon.getvalue()).decode("ascii")


def bloc_verification(document):
    """Ce dont le modèle PDF a besoin pour imprimer le bloc de vérification."""
    url = url_for("main.verifier", code=document.code, _external=True)
    return {
        "code": document.code,
        "url": url,
        "adresse": url_for("main.verifier_formulaire", _external=True).split("://", 1)[-1],
        "qr": qr_code_data_uri(url),
    }


def trouver(code):
    """Trace correspondant au code, toutes écoles confondues (la page de
    vérification est publique, sans école courante)."""
    code = normaliser_code(code)
    if not code:
        return None
    return (
        db.session.query(DocumentVerifiable).filter_by(code=code)
        .execution_options(tous_etablissements=True).first()
    )


# --- Contenu figé de chaque type de document --------------------------------

def _nombre(valeur, decimales=2):
    return f"{valeur:.{decimales}f}".replace(".", ",") if valeur is not None else "—"


def emettre_bulletin(eleve, classe, calcul, bulletin):
    details = [
        ("Moyenne générale", f"{_nombre(bulletin['moyenne'])} / {calcul['bareme']}"),
        ("Rang", f"{bulletin['rang']} sur {calcul['effectif_classe']}" if bulletin.get("rang") else "—"),
        ("Mention", bulletin.get("mention") or "—"),
    ]
    if bulletin.get("decision"):
        details.append(("Décision", bulletin["decision"]))
    for ligne in bulletin.get("lignes", []):
        details.append((ligne["matiere"], f"{_nombre(ligne['moyenne'])} / {calcul['bareme']}"))
    return emettre(
        "bulletin", f"bulletin:{eleve.id}:{calcul['periode']}:{calcul['annee']}",
        f"Bulletin de notes · {calcul['libelle_periode']} {calcul['annee']}",
        nom_eleve=eleve.nom_complet, classe=classe.nom, reference=eleve.matricule, details=details,
    )


def emettre_document_eleve(type_document, eleve, numero, signataire):
    from app.models.document_verifiable import TYPES_DOCUMENT

    details = [
        ("Matricule", eleve.matricule),
        ("Année scolaire", eleve.classe.annee_scolaire),
        ("Signataire", " ".join(x for x in (signataire.get("qualite"), signataire.get("nom")) if x)),
    ]
    return emettre(
        type_document, f"{type_document}:{numero}", TYPES_DOCUMENT[type_document],
        nom_eleve=eleve.nom_complet, classe=eleve.classe.nom, reference=numero, details=details,
    )


def emettre_recu(mouvement):
    from flask import current_app

    montant = mouvement.recette if mouvement.recette else mouvement.depense
    fcfa = current_app.jinja_env.filters["fcfa"]
    details = [
        ("Montant", fcfa(montant)),
        ("Date", mouvement.date.strftime("%d/%m/%Y")),
        ("Libellé", mouvement.libelle),
    ]
    eleve = mouvement.eleve
    return emettre(
        "recu", f"recu:{mouvement.id}", "Reçu de paiement",
        nom_eleve=eleve.nom_complet if eleve else None,
        classe=eleve.classe.nom if eleve and eleve.classe else None,
        reference=mouvement.reference, details=details,
    )

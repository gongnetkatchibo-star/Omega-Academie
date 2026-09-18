from functools import wraps

from flask import abort
from flask_login import current_user


def roles_required(*roles, module=None):
    """Restreint une vue aux utilisateurs dont le rôle figure dans
    `roles` — sauf si `module` est précisé et qu'une permission
    explicite existe pour ce couple (rôle, module) depuis la matrice de
    permissions de l'espace développeur ; dans ce cas, elle prend le
    dessus sur `roles` (sept. 2026).

    Le rôle « developpeur » a toujours accès complet à toute vue protégée
    par ce décorateur, quels que soient les rôles listés — c'est la seule
    exception volontaire (décision du fondateur)."""

    def decorateur(f):
        @wraps(f)
        def enveloppe(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(403)
            if module:
                from app.services.permissions import role_a_acces
                autorise = role_a_acces(current_user.role, module, roles)
            else:
                autorise = current_user.role == "developpeur" or current_user.role in roles
            if not autorise:
                abort(403)
            return f(*args, **kwargs)

        return enveloppe

    return decorateur


def html_vers_pdf(html):
    """Convertit un fragment HTML (déjà rendu par un template) en PDF.
    Utilisé pour tous les exports imprimables (emplois du temps, listes
    enseignants/élèves…), afin d'avoir un seul point de maintenance pour
    la génération de PDF dans l'application."""
    from io import BytesIO
    from xhtml2pdf import pisa

    tampon = BytesIO()
    pisa.CreatePDF(src=html, dest=tampon, encoding="utf-8")
    tampon.seek(0)
    return tampon.read()


def export_csv(entetes, lignes, nom_fichier):
    """Génère une réponse Flask téléchargeable au format CSV.
    `lignes` est une liste de tuples/listes, dans le même ordre que
    `entetes`."""
    import csv
    from io import StringIO
    from flask import Response

    tampon = StringIO()
    writer = csv.writer(tampon, delimiter=";")
    writer.writerow(entetes)
    writer.writerows(lignes)
    return Response(
        tampon.getvalue().encode("utf-8-sig"),  # BOM pour un bon affichage des accents dans Excel
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nom_fichier}.csv"},
    )


def export_xlsx(entetes, lignes, nom_fichier, titre_feuille="Export"):
    """Génère une réponse Flask téléchargeable au format Excel (.xlsx)."""
    from io import BytesIO
    from flask import Response
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = titre_feuille[:31]  # limite Excel pour le nom d'un onglet

    ws.append(list(entetes))
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="00387B", end_color="00387B", fill_type="solid")
    for ligne in lignes:
        ws.append(list(ligne))
    for col in ws.columns:
        longueur = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(longueur + 2, 45)

    tampon = BytesIO()
    wb.save(tampon)
    tampon.seek(0)
    return Response(
        tampon.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nom_fichier}.xlsx"},
    )


def export_pdf_liste(titre, sous_titre, entetes, lignes, nom_fichier):
    """Génère un PDF imprimable listant des lignes sous forme de tableau
    simple — utilisé pour les exports de listes (enseignants, élèves…)."""
    from flask import make_response, render_template

    html = render_template(
        "exports/liste_pdf.html", titre=titre, sous_titre=sous_titre,
        entetes=entetes, lignes=lignes, etablissement="Omega Académie",
    )
    reponse = make_response(html_vers_pdf(html))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename={nom_fichier}.pdf"
    return reponse


# Extensions autorisées pour les fichiers envoyés par les utilisateurs —
# jamais d'exécutable ni de script, quel que soit le module (sept. 2026).
EXTENSIONS_DOCUMENTS = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "csv"}
EXTENSIONS_IMAGES = {"jpg", "jpeg", "png", "gif", "webp"}
EXTENSIONS_VIDEOS = {"mp4", "webm", "mov"}
EXTENSIONS_BIBLIOTHEQUE = EXTENSIONS_DOCUMENTS | EXTENSIONS_IMAGES | EXTENSIONS_VIDEOS
EXTENSIONS_PIECE_JOINTE = EXTENSIONS_DOCUMENTS | EXTENSIONS_IMAGES


def extension_autorisee(nom_fichier, extensions_autorisees):
    if "." not in nom_fichier:
        return False
    extension = nom_fichier.rsplit(".", 1)[1].lower()
    return extension in extensions_autorisees

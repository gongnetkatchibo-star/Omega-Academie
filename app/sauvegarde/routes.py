import csv
import io
import zipfile
from datetime import datetime

from flask import send_file
from sqlalchemy import LargeBinary
from flask_login import login_required

from app.extensions import db
from app.sauvegarde import sauvegarde_bp
from app.utils import roles_required
from app.services.temps import maintenant

# Jamais dans les fichiers lisibles au tableur (le fichier de
# restauration, lui, garde tout).
COLONNES_SECRETES = {"mot_de_passe_hash", "code_2fa", "code_2fa_expiration"}


def _modeles_a_exporter():
    """Toutes les tables de l'école, lues dans la structure de la base :
    un module ajouté plus tard est exporté sans rien changer ici."""
    from app.services.tenant import modeles_rattaches

    return sorted(modeles_rattaches(), key=lambda modele: modele.__tablename__)


@sauvegarde_bp.route("/exporter")
@login_required
@roles_required("developpeur", module="sauvegarde")
def exporter():
    """Sauvegarde manuelle, indépendante de l'hébergeur. L'archive
    contient un fichier complet pour la restauration (donnees.json) et
    un CSV par table, lisible dans un tableur. Les CSV excluent le mot
    de passe (haché) des comptes ; le fichier de restauration le garde,
    sinon personne ne pourrait se reconnecter après restauration."""
    tampon, nom_fichier = construire_archive()

    from app.services.journal import journaliser
    journaliser("sauvegarde_exportee", details=nom_fichier)
    db.session.commit()

    return send_file(tampon, as_attachment=True, download_name=nom_fichier, mimetype="application/zip")


def construire_archive():
    """Archive de sauvegarde de l'école courante : (contenu, nom de
    fichier). Utilisée par le téléchargement manuel et par la sauvegarde
    planifiée (flask sauvegarder-ecoles)."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for modele in _modeles_a_exporter():
            colonnes = [
                c.name for c in modele.__table__.columns
                if c.name not in COLONNES_SECRETES and not isinstance(c.type, LargeBinary)
            ]
            lignes = modele.query.all()

            sortie = io.StringIO()
            ecrivain = csv.writer(sortie)
            ecrivain.writerow(colonnes)
            for ligne in lignes:
                ecrivain.writerow([getattr(ligne, col) for col in colonnes])

            archive.writestr(f"{modele.__tablename__}.csv", sortie.getvalue())

        from app.services.tenant import ecole_courante
        from app.services.sauvegarde import exporter_ecole, NOM_FICHIER_DONNEES
        import json
        ecole = ecole_courante()
        if ecole is not None:
            # Fichier complet, celui que la restauration relit.
            archive.writestr(NOM_FICHIER_DONNEES, json.dumps(exporter_ecole(ecole), ensure_ascii=False))

    tampon.seek(0)
    sigle = (ecole.sigle if ecole and ecole.sigle else "ecole").lower()
    nom_fichier = f"sauvegarde_{sigle}_{maintenant().strftime('%Y%m%d_%H%M')}.zip"
    return tampon, nom_fichier

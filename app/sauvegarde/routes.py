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

# Toutes les tables exportées — si un nouveau module ajoute un modèle,
# il suffit de l'ajouter ici pour qu'il soit couvert par la sauvegarde.
def _modeles_a_exporter():
    from app.models.user import User
    from app.models.classe import Classe
    from app.models.eleve import Eleve
    from app.models.enseignant import Enseignant, Affectation
    from app.models.note import Note
    from app.models.absence import Absence
    from app.models.paiement import Paiement
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.salaire import Salaire
    from app.models.test_niveau import TestNiveau
    from app.models.annonce import Annonce
    from app.models.ressource import Ressource
    from app.models.historique import HistoriqueScolaire
    from app.models.emploi_du_temps import Creneau
    from app.models.journal import JournalAction
    from app.models.journal_email import JournalEmail
    from app.models.parametre import ParametreEtablissement

    return [
        User, Classe, Eleve, Enseignant, Affectation, Note, Absence,
        Paiement, MouvementCaisse, Salaire, TestNiveau, Annonce, Ressource,
        HistoriqueScolaire, Creneau, JournalAction, JournalEmail, ParametreEtablissement,
    ]


@sauvegarde_bp.route("/exporter")
@login_required
@roles_required("developpeur", module="sauvegarde")
def exporter():
    """Sauvegarde manuelle, indépendante de l'hébergeur. L'archive
    contient un fichier complet pour la restauration (donnees.json) et
    un CSV par table, lisible dans un tableur. Les CSV excluent le mot
    de passe (haché) des comptes ; le fichier de restauration le garde,
    sinon personne ne pourrait se reconnecter après restauration."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for modele in _modeles_a_exporter():
            colonnes = [
                c.name for c in modele.__table__.columns
                if c.name != "mot_de_passe_hash" and not isinstance(c.type, LargeBinary)
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
    nom_fichier = f"sauvegarde_{sigle}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.zip"

    from app.services.journal import journaliser
    journaliser("sauvegarde_exportee", details=nom_fichier)
    db.session.commit()

    return send_file(tampon, as_attachment=True, download_name=nom_fichier, mimetype="application/zip")

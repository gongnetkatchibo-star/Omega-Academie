import csv
import io
import zipfile
from datetime import datetime

from flask import send_file
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
    """Sauvegarde manuelle, indépendante de l'hébergeur — un filet de
    sécurité que la direction peut déclencher à tout moment, en plus des
    sauvegardes automatiques éventuelles de la base gérée (sept. 2026).
    Exclut volontairement le mot de passe (haché) des comptes."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for modele in _modeles_a_exporter():
            colonnes = [c.name for c in modele.__table__.columns if c.name != "mot_de_passe_hash"]
            lignes = modele.query.all()

            sortie = io.StringIO()
            ecrivain = csv.writer(sortie)
            ecrivain.writerow(colonnes)
            for ligne in lignes:
                ecrivain.writerow([getattr(ligne, col) for col in colonnes])

            archive.writestr(f"{modele.__tablename__}.csv", sortie.getvalue())

    tampon.seek(0)
    nom_fichier = f"sauvegarde_omega_academie_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.zip"

    from app.services.journal import journaliser
    journaliser("sauvegarde_exportee", details=nom_fichier)
    db.session.commit()

    return send_file(tampon, as_attachment=True, download_name=nom_fichier, mimetype="application/zip")

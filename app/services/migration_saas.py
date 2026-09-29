"""Passage d'une base « une seule école » à une base multi-établissements.

Exécuté à chaque démarrage, mais sans effet une fois la migration faite :
- si des données existent sans école (base d'Omega Académie d'avant le
  mode SaaS), l'établissement n°1 est créé (ou complété) avec l'identité
  d'Omega, et toutes ces données lui sont rattachées ;
- les comptes « developpeur » restent sans école : ce sont les
  super-administrateurs de la plateforme ;
- sur PostgreSQL, les anciennes contraintes d'unicité globales sont
  remplacées par des contraintes « par école »."""

import os

from sqlalchemy import inspect, text

OMEGA = {
    "nom": "Complexe Scolaire Omega Académie",
    "sigle": "CSOA",
    "ville": "Pala",
    "pays": "Tchad",
    "slogan": "Vers l'excellence et la sagesse",
}


def _lire_image(app, nom_fichier):
    chemin = os.path.join(app.static_folder, "images", nom_fichier)
    if not os.path.exists(chemin):
        return None
    with open(chemin, "rb") as f:
        return f.read()


def _tables_rattachees(db):
    from app.services.tenant import modeles_rattaches

    return [m.__table__.name for m in modeles_rattaches()]


def _remplacer_contraintes(app, db):
    if db.engine.dialect.name != "postgresql":
        return
    inspecteur = inspect(db.engine)
    remplacements = [
        ("classes", "uq_classe_nom_annee", "uq_classe_ecole_nom_annee", "ecole_id, nom, annee_scolaire"),
        ("numeros_documents", "uq_numero_document_type_annee", "uq_numero_document_ecole_type_annee",
         "ecole_id, type_document, annee"),
    ]
    for table, ancienne, nouvelle, colonnes in remplacements:
        existantes = {c["name"] for c in inspecteur.get_unique_constraints(table)}
        with db.engine.begin() as cx:
            if ancienne in existantes:
                cx.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{ancienne}"'))
                app.logger.info("Contrainte %s supprimée", ancienne)
            if nouvelle not in existantes:
                cx.execute(text(f'ALTER TABLE "{table}" ADD CONSTRAINT "{nouvelle}" UNIQUE ({colonnes})'))
                app.logger.info("Contrainte %s créée", nouvelle)


def migrer_vers_multi_etablissements(app, db):
    from app.models.ecole import Ecole

    tables = _tables_rattachees(db)
    orphelins = 0
    with db.engine.connect() as cx:
        for table in tables:
            condition = "ecole_id IS NULL"
            if table == "users":
                condition += " AND role <> 'developpeur'"
            orphelins += cx.execute(text(f'SELECT COUNT(*) FROM "{table}" WHERE {condition}')).scalar()

    if orphelins:
        requete = db.session.query(Ecole).order_by(Ecole.id).execution_options(tous_etablissements=True)
        ecoles = requete.all()
        if len(ecoles) > 1:
            app.logger.error("Données sans école alors que plusieurs écoles existent : rattachement manuel requis.")
        else:
            ecole = ecoles[0] if ecoles else Ecole()
            for champ, valeur in OMEGA.items():
                if not getattr(ecole, champ, None):
                    setattr(ecole, champ, valeur)
            if not ecole.prefixe_matricule:
                ecole.prefixe_matricule = app.config.get("MATRICULE_PREFIXE", "OA26")
            if not ecole.logo:
                ecole.logo, ecole.logo_mime = _lire_image(app, "logo-omega-academie.png"), "image/png"
            if not ecole.filigrane:
                ecole.filigrane, ecole.filigrane_mime = _lire_image(app, "filigrane-csoa.png"), "image/png"
            ecole.actif = True
            db.session.add(ecole)
            db.session.commit()

            with db.engine.begin() as cx:
                for table in tables:
                    condition = "ecole_id IS NULL"
                    if table == "users":
                        condition += " AND role <> 'developpeur'"
                    cx.execute(text(f'UPDATE "{table}" SET ecole_id = :e WHERE {condition}'), {"e": ecole.id})
            app.logger.info("Données existantes rattachées à l'établissement %s (%s)", ecole.id, ecole.nom)

    _remplacer_contraintes(app, db)

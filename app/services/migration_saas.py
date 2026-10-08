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


def migrer_permissions_par_ecole(app, db):
    """Les permissions deviennent réglables école par école (oct. 2026) :
    l'ancienne règle « un seul réglage par (rôle, module) » est remplacée
    par « un seul réglage par (école, rôle, module) ». Les lignes déjà
    enregistrées restent le réglage commun à toutes les écoles."""
    inspecteur = inspect(db.engine)
    if "permissions" not in inspecteur.get_table_names():
        return
    existantes = {c["name"] for c in inspecteur.get_unique_constraints("permissions")}
    if "uq_permission_role_module" not in existantes:
        return
    if db.engine.dialect.name == "postgresql":
        with db.engine.begin() as cx:
            cx.execute(text('ALTER TABLE "permissions" DROP CONSTRAINT "uq_permission_role_module"'))
            if "uq_permission_ecole_role_module" not in existantes:
                cx.execute(text('ALTER TABLE "permissions" ADD CONSTRAINT "uq_permission_ecole_role_module" '
                                "UNIQUE (ecole_id, role, module)"))
    else:
        # SQLite ne sait pas retirer une contrainte : on reconstruit la
        # petite table des permissions à l'identique, sans l'ancienne règle.
        table = db.metadata.tables["permissions"]
        index_existants = [i["name"] for i in inspecteur.get_indexes("permissions") if i.get("name")]
        with db.engine.begin() as cx:
            for nom in index_existants:
                cx.execute(text(f'DROP INDEX IF EXISTS "{nom}"'))
            cx.execute(text('ALTER TABLE "permissions" RENAME TO "permissions_avant_ecoles"'))
            table.create(cx)
            cx.execute(text(
                'INSERT INTO "permissions" (id, ecole_id, role, module, autorise) '
                'SELECT id, NULL, role, module, autorise FROM "permissions_avant_ecoles"'
            ))
            cx.execute(text('DROP TABLE "permissions_avant_ecoles"'))
    app.logger.info("Permissions : réglage par école activé")

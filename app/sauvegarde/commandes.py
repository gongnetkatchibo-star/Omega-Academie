"""Sauvegarde planifiée de tous les établissements.

    flask sauvegarder-ecoles
    flask sauvegarder-ecoles --dossier /var/sauvegardes/toumai --garder 30

Écrit une archive par école (le même fichier que « Télécharger une
sauvegarde », donc restaurable depuis la console Plateforme) et ne garde
que les plus récentes. À lancer chaque nuit par le serveur : voir
deploiement/LISEZMOI.md.

    flask sauvegarder-base --dossier /var/sauvegardes/toumai --garder 14

Copie complète de la base (toutes les écoles, tous les comptes), faite
par l'outil de PostgreSQL : c'est elle qui sert à tout remettre en place
après une panne du serveur."""

import os
import re

import click


def _garder_les_plus_recentes(dossier, motif, garder):
    if garder <= 0:
        return
    fichiers = sorted(
        (f for f in os.listdir(dossier) if motif.match(f)),
        key=lambda f: os.path.getmtime(os.path.join(dossier, f)),
    )
    for nom in fichiers[:-garder]:
        os.remove(os.path.join(dossier, nom))


def enregistrer_commandes(app):
    @app.cli.command("sauvegarder-base")
    @click.option("--dossier", default=None, help="Dossier où écrire la copie (défaut : instance/sauvegardes).")
    @click.option("--garder", default=14, show_default=True, help="Nombre de copies conservées.")
    def sauvegarder_base(dossier, garder):
        """Copie complète de la base de données (toutes les écoles)."""
        import shutil
        import subprocess

        from sqlalchemy.engine import make_url

        from app.services.temps import maintenant

        dossier = dossier or os.path.join(app.instance_path, "sauvegardes")
        os.makedirs(dossier, exist_ok=True)
        url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
        horodatage = maintenant().strftime("%Y%m%d_%H%M%S")

        if url.get_backend_name() == "sqlite":
            import sqlite3

            if not url.database or url.database == ":memory:":
                raise click.ClickException("Base en mémoire : rien à copier.")
            chemin = os.path.join(dossier, f"base_{horodatage}.sqlite")
            source = sqlite3.connect(url.database)
            cible = sqlite3.connect(chemin + ".partiel")
            with cible:
                source.backup(cible)  # copie cohérente, même si l'application écrit en même temps
            cible.close()
            source.close()
        elif url.get_backend_name() == "postgresql":
            if shutil.which("pg_dump") is None:
                raise click.ClickException("pg_dump introuvable : installer le paquet postgresql-client.")
            chemin = os.path.join(dossier, f"base_{horodatage}.dump")
            # Les identifiants passent par l'environnement, pas par la
            # ligne de commande (visible des autres comptes du serveur).
            environnement = dict(os.environ, PGDATABASE=url.database or "")
            for cle, valeur in (("PGHOST", url.host), ("PGPORT", url.port), ("PGUSER", url.username), ("PGPASSWORD", url.password)):
                if valeur:
                    environnement[cle] = str(valeur)
            resultat = subprocess.run(
                ["pg_dump", "--format=custom", "--no-owner", "--file", chemin + ".partiel"],
                env=environnement, capture_output=True, text=True,
            )
            if resultat.returncode != 0:
                if os.path.exists(chemin + ".partiel"):
                    os.remove(chemin + ".partiel")
                raise click.ClickException(f"pg_dump a échoué : {resultat.stderr.strip()[:300]}")
        else:
            raise click.ClickException(f"Base {url.get_backend_name()} : copie non prise en charge.")

        os.chmod(chemin + ".partiel", 0o600)
        os.replace(chemin + ".partiel", chemin)  # jamais de copie à moitié écrite
        _garder_les_plus_recentes(dossier, re.compile(r"^base_\d{8}_\d{6}\.(dump|sqlite)$"), garder)
        click.echo(f"✓ Base copiée : {chemin} ({os.path.getsize(chemin) // 1024} Ko)")

    @app.cli.command("sauvegarder-ecoles")
    @click.option("--dossier", default=None, help="Dossier où écrire les archives (défaut : instance/sauvegardes).")
    @click.option("--garder", default=14, show_default=True, help="Nombre d'archives conservées par école.")
    def sauvegarder_ecoles(dossier, garder):
        """Écrit une archive de sauvegarde par établissement."""
        from flask import g
        from sqlalchemy import select

        from app.extensions import db
        from app.models.ecole import Ecole
        from app.sauvegarde.routes import construire_archive

        dossier = dossier or os.path.join(app.instance_path, "sauvegardes")
        os.makedirs(dossier, exist_ok=True)

        ecoles = db.session.execute(
            select(Ecole).order_by(Ecole.id).execution_options(tous_etablissements=True)
        ).scalars().all()
        echecs = 0
        for ecole in ecoles:
            # Comme dans une requête : tout ce qui est lu ensuite est
            # limité à cette école.
            g.ecole_id, g.ecole_obj = ecole.id, ecole
            prefixe = f"ecole{ecole.id}_"
            try:
                tampon, nom_fichier = construire_archive()
                chemin = os.path.join(dossier, prefixe + nom_fichier)
                # Écriture en deux temps : jamais d'archive à moitié écrite.
                with open(chemin + ".partiel", "wb") as fichier:
                    fichier.write(tampon.getvalue())
                os.replace(chemin + ".partiel", chemin)
                click.echo(f"✓ {ecole.nom} : {chemin}")
            except Exception as erreur:  # une école en échec n'empêche pas les autres
                echecs += 1
                db.session.rollback()
                click.echo(f"✗ {ecole.nom} : {erreur}", err=True)
                continue

            motif = re.compile(rf"^{re.escape(prefixe)}sauvegarde_.*\.zip$")
            _garder_les_plus_recentes(dossier, motif, garder)
        g.ecole_id, g.ecole_obj = None, None

        if echecs:
            raise SystemExit(1)

"""Sauvegarde planifiée de tous les établissements.

    flask sauvegarder-ecoles
    flask sauvegarder-ecoles --dossier /var/sauvegardes/toumai --garder 30

Écrit une archive par école (le même fichier que « Télécharger une
sauvegarde », donc restaurable depuis la console Plateforme) et ne garde
que les plus récentes. À lancer chaque nuit par le serveur : voir
deploiement/LISEZMOI.md."""

import os
import re

import click


def enregistrer_commandes(app):
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
            if garder > 0:
                archives = sorted(
                    (f for f in os.listdir(dossier) if motif.match(f)),
                    key=lambda f: os.path.getmtime(os.path.join(dossier, f)),
                )
                for nom in archives[:-garder]:
                    os.remove(os.path.join(dossier, nom))
        g.ecole_id, g.ecole_obj = None, None

        if echecs:
            raise SystemExit(1)

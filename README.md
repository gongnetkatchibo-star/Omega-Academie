# Toumaï Edu School

Plateforme de gestion scolaire multi-établissements (Flask). Une seule
adresse pour toutes les écoles : chaque école ne voit que ses propres
données, et le super-administrateur (rôle `developpeur`) crée et
administre les écoles depuis la console Plateforme.

## Modules

| Domaine | Modules |
|---|---|
| Scolarité | Classes, élèves (dossier, photo, import Excel, passage de classe), tests de niveau, documents officiels (certificat, attestation) |
| Pédagogie | Notes par évaluation, coefficients, bulletins PDF, absences, emplois du temps, enseignants, suivi des cours, alertes |
| Finances | Scolarité par échéances, remises, frais annexes, reçus, caisse, salaires, statistiques |
| Communication | Annonces, messagerie parent-école, notifications par email (Brevo), bibliothèque numérique, assistant |
| Administration | Validation des comptes, rôles et permissions, paramètres de l'école, journal d'actions, sauvegarde et restauration |

## Installation (poste de développement)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python3 run.py
```

Ouvrir http://127.0.0.1:5000. Sans `DATABASE_URL`, la base est un
fichier SQLite dans `instance/`. Les tables, et les colonnes ajoutées
par une mise à jour, sont créées automatiquement au démarrage.

Au tout premier lancement, la page `/auth/premiere-configuration` crée
le compte super-administrateur ; c'est lui qui crée ensuite les écoles.

## Tests

```bash
pytest
```

La suite utilise une base en mémoire et ne touche jamais la vraie base.
Pour la rejouer sur PostgreSQL, comme en production (base **vide et
réservée aux tests** : elle est effacée à chaque test) :

```bash
TEST_DATABASE_URL=postgresql://utilisateur:motdepasse@127.0.0.1/toumai_test pytest
```

## Mise en production

Sur le serveur, un seul script installe tout (PostgreSQL, gunicorn,
nginx, https, sauvegarde nocturne) :

```bash
sudo bash deploiement/installer.sh                       # essai par l'adresse IP
sudo bash deploiement/installer.sh ecole.example toi@exemple.com   # avec nom de domaine
```

Détails, mises à jour et restauration : [`deploiement/LISEZMOI.md`](deploiement/LISEZMOI.md).

Commandes utiles :

```bash
flask creer-compte-initial      # créer un compte super-administrateur
flask sauvegarder-base          # copie complète de la base
flask sauvegarder-ecoles        # une archive de sauvegarde par école
```

## Envoi automatique vers GitHub

`outils/installer_envoi_auto.sh` installe sur le poste de développement
un service qui crée un commit et le pousse dès que le dossier change.

```bash
bash outils/installer_envoi_auto.sh            # installer
bash outils/installer_envoi_auto.sh --etat     # état et derniers envois
bash outils/installer_envoi_auto.sh --retirer  # désinstaller
```

## Organisation du code

```
app/
├── __init__.py      création de l'application, sécurité, modules
├── models/          tables de la base (une école = un ecole_id partout)
├── services/        calculs partagés : moyennes, bulletins, paiements,
│                    statistiques, sauvegarde, isolement entre écoles
├── <module>/        routes de chaque module
├── templates/       pages
└── static/          styles, images
tests/               tests automatiques
deploiement/         installation sur le serveur (installer.sh)
outils/              envoi automatique vers GitHub
```

## Ce qui n'est pas encore branché

- SMS et WhatsApp : les notifications partent par email uniquement.
- Paiement Mobile Money en ligne : les paiements sont saisis par le comptable.
- Assistant : répond à quelques questions par mots-clés, sans modèle d'IA.

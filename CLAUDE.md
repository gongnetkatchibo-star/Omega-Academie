# Consignes pour les assistants de code (Claude et autres)

Toumaï Edu School : application Flask de gestion scolaire, multi-établissements.
Langue du projet : français (code, commentaires, messages, interface).

## Avant de rendre la main

1. Lancer `pytest` : toute la suite doit passer. Ajouter des tests pour ce qui change.
2. Écrire en une ligne ce qui a changé dans le fichier `.message_envoi`, à la racine
   (exemple : `relances WhatsApp : numéros hors Tchad acceptés`). Le service d'envoi
   automatique s'en sert comme message du prochain commit (« v123 : … ») puis
   l'efface. Sans ce fichier, le message est un simple résumé des fichiers touchés.

Ce dossier est envoyé tout seul sur GitHub (`main`) environ 30 secondes après la
dernière modification (`outils/envoi_auto_github.sh`, journal dans
`.git/envoi_auto.log`). Ne pas faire de commit ni de push à la main ; éviter de
laisser un fichier à moitié modifié pendant une longue pause.

## Règles du code

- Isolement entre écoles : tout modèle de données d'une école hérite de
  `AppartientEcole` (`app/models/tenant.py`) ; le filtre par école est automatique
  (`app/services/tenant.py`). Ne le contourner (`tous_etablissements=True`) que
  pour la console Plateforme ou une page publique.
- Un seul calcul par chiffre : moyennes (`services/moyennes.py`, identiques au
  bulletin), paiements (`services/paiements.py`), statistiques
  (`services/statistiques.py`). Pour une liste d'élèves, utiliser les versions
  groupées (`moyennes_et_reussites`, `resumes_paiements`), pas une boucle élève
  par élève.
- Montants en francs CFA entiers (`utils.montant_entier`). Dates de l'école :
  `services/temps.py` (heure du Tchad), jamais `date.today()`.
- Numéros de téléphone : `services/numeros.py` (pays de l'école).
- Textes affichés : passer par la traduction (`services/langues.py`), l'interface
  existe aussi en arabe.
- Jamais de secret dans le dépôt : `.env` et `instance/` restent hors de Git.
- Nouvelles colonnes : ajoutées automatiquement au démarrage
  (`services/auto_migration.py`) ; un renommage ou un changement de type demande
  une migration écrite à la main.

## Commandes

```bash
pytest                       # tests (base en mémoire)
python3 run.py               # serveur de développement
flask sauvegarder-ecoles     # une archive de sauvegarde par école
```

Mise en production : `deploiement/LISEZMOI.md`.

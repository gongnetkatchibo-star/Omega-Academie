# Toumaï Edu School — squelette Flask

Squelette de départ pour la plateforme Omega Académie / Toumaï Edu School :
structure de dossiers, configuration, et base de données SQLite prêtes à l'emploi.

## Structure

```
toumai_edu_school/
├── app/
│   ├── __init__.py        # application factory
│   ├── extensions.py      # instances db, migrate, login_manager
│   ├── models/
│   │   ├── ecole.py        # table ecoles (prépare le multi-écoles, Phase 4)
│   │   └── user.py         # table users (rôles + statut de validation)
│   ├── main/                # page d'accueil de vérification
│   ├── templates/
│   └── static/css/style.css # couleurs Omega Académie (#00387B / #DEA230)
├── instance/                 # contient toumai.db (généré, non versionné)
├── config.py
├── run.py
├── requirements.txt
└── .env.example
```

## Installation

```bash
python3 -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## Créer la base de données SQLite

```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

(ou plus simple pour démarrer vite : `flask shell` puis `db.create_all()`)

## Créer le tout premier compte (bootstrap)

Personne ne peut approuver le premier secrétaire — il faut donc créer un
premier compte déjà actif directement en ligne de commande :

```bash
flask creer-compte-initial
```

Renseigner un nom, un email, un mot de passe, et le rôle (`fondateur` par
défaut). Ce compte peut ensuite se connecter et approuver tous les autres.

## Lancer le serveur

```bash
python3 run.py
```

Puis ouvrir http://127.0.0.1:5000 — redirige vers la connexion si aucun
compte actif n'est connecté.

## Déjà en place

- Modèle `User` avec les 11 rôles du cahier des charges et un champ
  `statut` (`en_attente` / `actif` / `refuse`) qui bloque la connexion
  tant que le secrétaire n'a pas approuvé le compte (§3 du cahier des
  charges).
- Modèle `Ecole` avec logo et couleurs, pour préparer le mode marque
  blanche multi-écoles (§9).
- **Authentification complète** : inscription (parent, enseignant,
  personnel administratif) avec statut `en_attente`, connexion qui
  bloque les comptes non validés, déconnexion.
- **Validation des comptes** : page `/secretariat/demandes` réservée aux
  rôles secrétaire/fondateur/administrateur général, avec approbation
  ou refus (testé avec un contrôle d'accès 403 pour les autres rôles).
- Commande `flask creer-compte-initial` pour le bootstrap.

## Déjà en place — les 10 modules du cahier des charges

- **Module 1 — Classes** (`/classes/`) : création manuelle ou en un clic (CP1 à 4ème), frais annuel par classe.
- **Module 2 — Élèves** (`/eleves/`) : inscription avec matricule automatique, dossier numérique, historique, passage en classe supérieure.
- **Module 3 — Enseignants** (`/enseignants/`) : profil enseignant (spécialité), affectation à une classe + matière.
- **Module 4 — Emploi du temps** (`/emploi-du-temps/`) : créneaux par classe, vue « Mon EDT » pour l'enseignant.
- **Module 5 — Suivi des cours** (`/suivi-cours/`) : chapitres, % de progression, signalement de retard, tableau de bord direction.
- **Module 6 — Notes et bulletins** (`/notes/`) : saisie par classe/matière/trimestre (barème /10 pour CP1-CM2, /20 au-delà — §6), bulletin avec moyenne générale et classement.
- **Module 7 — Finances** (`/finances/`) : frais dû/payé/solde par élève, enregistrement manuel des paiements (espèces, Mobile Money, virement).
- **Module 8 — Bibliothèque numérique** (`/bibliotheque/`) : dépôt de fichiers (livres, cours, exercices, vidéos), téléchargement.
- **Module 9 — Communication** (`/communication/`) : annonces internes ciblées par rôle (tous, parents, enseignants, élèves).
- **Module 10 — Assistant IA** (`/assistant/`) : aperçu d'interface uniquement — pas de modèle d'IA connecté.

## Limites connues et prochaines étapes réelles

Ces points nécessitent des services externes (identifiants, comptes marchands) que je ne peux pas configurer ici :

- **Mobile Money** (§9) : le module Finances enregistre les paiements manuellement ; l'intégration réelle Orange Money/MTN nécessite leurs API et des identifiants marchands.
- **SMS/email** (§9) : les annonces restent internes à l'application ; l'envoi réel demande un service comme Twilio ou une passerelle SMS locale.
- **IA** (Module 10) : l'écran existe mais ne fait aucun appel à un modèle réel — c'est le point d'intégration prévu pour une API d'IA.
- **PDF des bulletins** (§6) : le bulletin est une page HTML imprimable, pas encore un vrai fichier PDF généré.
- **Multi-écoles / marque blanche** (§9, Phase 4) : l'architecture reste mono-école pour l'instant ; passer en SaaS demandera de relier Classe/Eleve à `Ecole` partout et un panneau super-administrateur.

## Prochaine étape suggérée

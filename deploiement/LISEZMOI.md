# Mise en ligne sur un serveur Linux (Oracle Cloud ou autre)

Serveur visé : Ubuntu 22.04 ou 24.04, par exemple une machine Oracle
« Ampere A1 » gratuite. Un seul script installe tout : PostgreSQL,
l'application (gunicorn), nginx, la sauvegarde de chaque nuit, et le
certificat https si un nom de domaine est fourni.

## 1. Avant : chez l'hébergeur

Ouvrir les ports **80** et **443** en entrée. Chez Oracle : Networking >
Virtual Cloud Networks > le réseau > Security Lists > Add Ingress Rules
(source `0.0.0.0/0`, TCP, ports 80 puis 443).

## 2. Installer

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/gongnetkatchibo-star/Omega-Academie.git
cd Omega-Academie
sudo bash deploiement/installer.sh
```

Le script affiche à la fin l'adresse du site et la **clé d'installation**
à saisir sur `/auth/premiere-configuration` pour créer le compte
super-administrateur. Sans nom de domaine, le site répond en http sur
l'adresse IP : pour essayer seulement.

Dès que le nom de domaine pointe vers l'adresse IP du serveur :

```bash
sudo bash deploiement/installer.sh ecole.example toi@exemple.com
```

Le certificat https est alors installé et renouvelé tout seul, et le
site n'accepte plus que ce nom de domaine.

Le script peut être relancé sans risque : le fichier de réglages
`/opt/toumai_edu_school/.env` (mots de passe, clés) n'est jamais écrasé.

## 3. Réglages (`/opt/toumai_edu_school/.env`)

| Réglage | Rôle |
|---|---|
| `SECRET_KEY`, `DATABASE_URL`, `CLE_INSTALLATION` | Remplis par le script. Ne pas changer `SECRET_KEY` : toutes les sessions seraient fermées. |
| `HTTPS_ACTIF` | `1` dès que le site est en https (mis par le script). |
| `HOTES_AUTORISES` | Nom(s) de domaine acceptés, séparés par des virgules. |
| `BREVO_API_KEY`, `MAIL_DEFAULT_SENDER` | Envoi des emails. **À remplir à la main** (compte brevo.com). |
| `DOUBLE_AUTH_DEVELOPPEUR` | `1` pour un code par email à chaque connexion du super-administrateur, une fois les emails vérifiés. |
| `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT` | Facultatif : puissance allouée (voir `gunicorn.conf.py`). |

Après une modification : `sudo systemctl restart toumai-edu-school`.

## 4. Mettre à jour

```bash
cd ~/Omega-Academie && git pull && sudo bash deploiement/installer.sh
```

(avec le nom de domaine et l'email si le site en a un). Les nouvelles
tables et colonnes sont créées au démarrage.

## 5. Sauvegardes

Chaque nuit à 1 h, dans `/var/sauvegardes/toumai` :

- `base_AAAAMMJJ_HHMMSS.dump` — copie complète de la base (14 gardées) ;
- une archive `.zip` par école (7 gardées), restaurable depuis la console
  Plateforme.

```bash
sudo systemctl start toumai-sauvegarde      # en faire une tout de suite
sudo ls -lh /var/sauvegardes/toumai
```

Ces copies sont sur le même serveur que la base : **en recopier
régulièrement ailleurs** (autre machine, stockage en ligne).

Remettre toute la base après une panne (le site est arrêté le temps de
l'opération) :

```bash
sudo systemctl stop toumai-edu-school
sudo -u postgres dropdb toumai && sudo -u postgres createdb --owner toumai toumai
sudo -u postgres pg_restore --no-owner --role toumai -d toumai /var/sauvegardes/toumai/base_….dump
sudo systemctl start toumai-edu-school
```

## 6. Au quotidien

```bash
sudo journalctl -u toumai-edu-school -f        # journal en direct
sudo systemctl status toumai-edu-school        # état du service
curl http://127.0.0.1:8000/sante               # doit répondre « ok »
```

Créer un compte super-administrateur depuis le serveur (mot de passe
perdu, par exemple) :

```bash
cd /opt/toumai_edu_school
sudo -u toumai bash -c 'set -a; . ./.env; set +a; venv/bin/flask creer-compte-initial'
```

## Limite connue

Le compteur de tentatives de connexion est tenu par processus : la
limite réelle est multipliée par le nombre de processus. Pour un
compteur commun, installer Redis et définir
`RATELIMIT_STORAGE_URI=redis://localhost:6379` (et `pip install redis`).

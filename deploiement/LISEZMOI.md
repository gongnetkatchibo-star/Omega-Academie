# Mise en production (serveur Linux, par exemple Oracle Cloud)

Les fichiers de ce dossier sont des modèles : ils supposent l'application
dans `/opt/toumai_edu_school`, un utilisateur système `toumai` et un
environnement Python dans `venv/`. Adapter les chemins si besoin.

## 1. Application

```bash
cd /opt/toumai_edu_school
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env        # puis renseigner SECRET_KEY, DATABASE_URL, BREVO_API_KEY…
```

`gunicorn.conf.py` (à la racine) règle le nombre de processus, les fils
et les délais. Pour les changer sans modifier le fichier, ajouter dans
`.env` : `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`,
`GUNICORN_BIND`.

```bash
sudo cp deploiement/toumai-edu-school.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now toumai-edu-school
journalctl -u toumai-edu-school -f      # journaux en direct
```

## 2. Serveur web (nginx)

```bash
sudo cp deploiement/nginx.conf /etc/nginx/sites-available/toumai
sudo ln -s /etc/nginx/sites-available/toumai /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Le service définit `PROXY_COUCHES=1` : l'application sait alors qu'elle
est derrière nginx et retrouve la vraie adresse de chaque visiteur et le
https. Ne pas mettre cette valeur si l'application est jointe en direct.

## 3. Sauvegarde nocturne

```bash
sudo mkdir -p /var/sauvegardes/toumai && sudo chown toumai: /var/sauvegardes/toumai
sudo cp deploiement/toumai-sauvegarde.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now toumai-sauvegarde.timer
sudo systemctl start toumai-sauvegarde     # premier essai tout de suite
```

Une archive par école et par nuit, les 30 dernières sont gardées. Chaque
archive se restaure depuis la console Plateforme. Ces archives sont sur
le même serveur que la base : en copier régulièrement ailleurs.

## 4. Mettre à jour l'application

```bash
cd /opt/toumai_edu_school && git pull
venv/bin/pip install -r requirements.txt
sudo systemctl restart toumai-edu-school
```

Les nouvelles tables et colonnes sont créées au démarrage.

## Limite connue

Le compteur de tentatives de connexion est tenu par processus : la
limite réelle est multipliée par le nombre de processus. Pour un
compteur commun, installer Redis et définir
`RATELIMIT_STORAGE_URI=redis://localhost:6379` (et `pip install redis`).

#!/usr/bin/env bash
# Installe — ou met à jour — Toumaï Edu School sur un serveur Ubuntu
# (22.04 ou 24.04), par exemple une machine Oracle Cloud.
#
#   sudo bash deploiement/installer.sh
#       sans nom de domaine : le site répond sur http://ADRESSE-IP
#   sudo bash deploiement/installer.sh ecole.example moi@exemple.com
#       avec nom de domaine : https et certificat (le domaine doit déjà
#       pointer vers l'adresse IP du serveur)
#
# À lancer depuis le dossier récupéré avec git. Peut être relancé autant
# de fois que nécessaire : chaque étape regarde ce qui existe déjà, et le
# fichier .env (mots de passe, clés) n'est jamais écrasé. Pour une mise à
# jour :  git pull && sudo bash deploiement/installer.sh
set -euo pipefail

DOMAINE="${1:-}"
EMAIL="${2:-}"

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CIBLE="${CIBLE:-/opt/toumai_edu_school}"
COMPTE="${COMPTE:-toumai}"
BASE="${BASE:-toumai}"
SAUVEGARDES="${SAUVEGARDES:-/var/sauvegardes/toumai}"
DOSSIER_SYSTEMD="${DOSSIER_SYSTEMD:-/etc/systemd/system}"
DOSSIER_NGINX="${DOSSIER_NGINX:-/etc/nginx}"
ENV="$CIBLE/.env"

etape() { echo; echo "== $* =="; }
arret() { echo "✗ $*" >&2; exit 1; }
# Depuis « / » : le dossier courant (souvent celui d'un autre compte)
# n'est pas toujours lisible par le compte visé.
en_tant_que() { local compte="$1"; shift; (cd / && runuser -u "$compte" -- "$@"); }

# Remplace (ou ajoute) une ligne CLE=valeur du fichier .env.
regler() {
    local cle="$1" valeur="$2"
    if grep -q "^${cle}=" "$ENV"; then
        sed -i "s|^${cle}=.*|${cle}=${valeur}|" "$ENV"
    else
        echo "${cle}=${valeur}" >> "$ENV"
    fi
}

[ "$(id -u)" = "0" ] || arret "À lancer avec sudo."
[ -f "$SOURCE/requirements.txt" ] || arret "Lance ce script depuis le dossier de l'application."
if [ -n "$DOMAINE" ] && [ -z "$EMAIL" ]; then
    arret "Avec un nom de domaine, indique aussi ton email (pour le certificat) : installer.sh $DOMAINE toi@exemple.com"
fi

etape "1/8 Paquets du système"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip python3-dev build-essential libpq-dev \
    postgresql postgresql-client nginx rsync curl > /dev/null
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
    || arret "Python 3.10 ou plus récent est nécessaire (trouvé : $(python3 --version))."
echo "✓ $(python3 --version), PostgreSQL et nginx installés"

etape "2/8 Compte du service et fichiers"
id -u "$COMPTE" > /dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$COMPTE"
mkdir -p "$CIBLE" "$SAUVEGARDES"
if [ "$SOURCE" != "$CIBLE" ]; then
    # Le code est copié ; ce qui appartient au serveur (réglages, données
    # locales, environnement Python) n'est ni copié ni effacé.
    rsync -a --delete \
        --exclude ".git" --exclude ".env" --exclude "venv" --exclude "instance" \
        --exclude "__pycache__" --exclude ".pytest_cache" --exclude ".message_envoi" \
        "$SOURCE/" "$CIBLE/"
fi
mkdir -p "$CIBLE/instance"
chown -R "$COMPTE:" "$CIBLE" "$SAUVEGARDES"
chmod 750 "$SAUVEGARDES"
echo "✓ Application dans $CIBLE"

etape "3/8 Base de données et réglages"
systemctl enable --now postgresql > /dev/null 2>&1 || true
if [ ! -f "$ENV" ]; then
    MOT_DE_PASSE="$(python3 -c 'import secrets; print(secrets.token_hex(20))')"
    en_tant_que postgres psql -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$BASE') THEN
        CREATE ROLE "$BASE" LOGIN PASSWORD '$MOT_DE_PASSE';
    ELSE
        ALTER ROLE "$BASE" LOGIN PASSWORD '$MOT_DE_PASSE';
    END IF;
END
\$\$;
SQL
    if ! en_tant_que postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$BASE'" | grep -q 1; then
        en_tant_que postgres createdb --owner "$BASE" --encoding UTF8 "$BASE"
    fi
    cp "$CIBLE/deploiement/env.production.exemple" "$ENV"
    regler SECRET_KEY "$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    regler DATABASE_URL "postgresql://$BASE:$MOT_DE_PASSE@127.0.0.1:${PGPORT:-5432}/$BASE"
    regler CLE_INSTALLATION "$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
    regler HTTPS_ACTIF 0
    echo "✓ Base « $BASE » et fichier .env créés"
else
    echo "✓ Fichier .env déjà en place : réglages conservés"
fi
chown "$COMPTE:" "$ENV"
chmod 600 "$ENV"

etape "4/8 Environnement Python"
[ -x "$CIBLE/venv/bin/python" ] || en_tant_que "$COMPTE" python3 -m venv "$CIBLE/venv"
en_tant_que "$COMPTE" "$CIBLE/venv/bin/pip" install -q --upgrade pip
# D'abord les versions exactes validées par les tests ; si l'une d'elles
# n'existe pas pour ce serveur, les versions courantes compatibles.
if ! en_tant_que "$COMPTE" "$CIBLE/venv/bin/pip" install -q -r "$CIBLE/requirements.txt" \
        -c "$CIBLE/deploiement/contraintes.txt" 2> /dev/null; then
    echo "  (versions validées indisponibles pour ce serveur : installation des versions courantes)"
    en_tant_que "$COMPTE" "$CIBLE/venv/bin/pip" install -q -r "$CIBLE/requirements.txt"
fi
echo "✓ Dépendances installées"

etape "5/8 Service de l'application"
for fichier in toumai-edu-school.service toumai-sauvegarde.service toumai-sauvegarde.timer; do
    sed -e "s|/opt/toumai_edu_school|$CIBLE|g" -e "s|/var/sauvegardes/toumai|$SAUVEGARDES|g" \
        -e "s|^User=.*|User=$COMPTE|" -e "s|^Group=.*|Group=$COMPTE|" \
        "$CIBLE/deploiement/$fichier" > "$DOSSIER_SYSTEMD/$fichier"
done
systemctl daemon-reload
systemctl enable toumai-edu-school toumai-sauvegarde.timer > /dev/null 2>&1
systemctl restart toumai-edu-school
systemctl start toumai-sauvegarde.timer
pret=""
for _ in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:8000/sante > /dev/null 2>&1; then pret=1; break; fi
    sleep 1
done
if [ -z "$pret" ]; then
    journalctl -u toumai-edu-school -n 40 --no-pager || true
    arret "L'application ne répond pas. Les dernières lignes de son journal sont ci-dessus."
fi
echo "✓ Application démarrée (sauvegarde chaque nuit à 1 h dans $SAUVEGARDES)"

etape "6/8 Serveur web nginx"
SITE="$DOSSIER_NGINX/sites-available/toumai"
if [ -f "$SITE" ] && grep -q "managed by Certbot" "$SITE"; then
    echo "✓ Site déjà configuré avec son certificat : laissé tel quel"
else
    sed -e "s|server_name _;|server_name ${DOMAINE:-_};|" -e "s|/opt/toumai_edu_school|$CIBLE|g" \
        "$CIBLE/deploiement/nginx.conf" > "$SITE"
    ln -sf "$SITE" "$DOSSIER_NGINX/sites-enabled/toumai"
    rm -f "$DOSSIER_NGINX/sites-enabled/default"
fi
nginx -t > /dev/null 2>&1 || { nginx -t; arret "Configuration nginx invalide."; }
systemctl enable nginx > /dev/null 2>&1
systemctl reload nginx 2> /dev/null || systemctl restart nginx
echo "✓ nginx sert le site"

etape "7/8 Pare-feu du serveur"
# Les images Ubuntu d'Oracle bloquent tout sauf SSH : on ouvre le web.
if command -v ufw > /dev/null 2>&1 && ufw status 2> /dev/null | grep -q "Status: active"; then
    ufw allow 80/tcp > /dev/null
    ufw allow 443/tcp > /dev/null
    echo "✓ Ports 80 et 443 ouverts (ufw)"
elif command -v iptables > /dev/null 2>&1 && iptables -S INPUT 2> /dev/null | grep -q -- "-j REJECT"; then
    for port in 80 443; do
        if ! iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2> /dev/null; then
            # Juste avant la règle qui refuse tout le reste.
            rang="$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }')"
            iptables -I INPUT "${rang:-1}" -p tcp --dport "$port" -j ACCEPT
        fi
    done
    if command -v netfilter-persistent > /dev/null 2>&1; then
        netfilter-persistent save > /dev/null 2>&1 || true
    fi
    echo "✓ Ports 80 et 443 ouverts (iptables)"
else
    echo "✓ Aucun pare-feu local à régler"
fi

etape "8/8 Adresse du site"
if [ -n "$DOMAINE" ]; then
    apt-get install -y -qq certbot python3-certbot-nginx > /dev/null
    if certbot --nginx -d "$DOMAINE" --non-interactive --agree-tos -m "$EMAIL" --redirect; then
        regler HTTPS_ACTIF 1
        regler HOTES_AUTORISES "$DOMAINE"
        systemctl restart toumai-edu-school
        ADRESSE="https://$DOMAINE"
        echo "✓ Certificat https installé (renouvelé automatiquement)"
    else
        ADRESSE="http://$DOMAINE"
        echo "✗ Certificat non obtenu. Vérifie que $DOMAINE pointe bien vers ce serveur et que"
        echo "  les ports 80 et 443 sont ouverts chez l'hébergeur, puis relance ce script."
    fi
else
    ADRESSE="http://$(curl -fsS --max-time 5 https://api.ipify.org 2> /dev/null || hostname -I | awk '{ print $1 }')"
fi

echo
echo "================================================================"
echo " Site : $ADRESSE"
echo
echo " Premier compte (super-administrateur) :"
echo "   $ADRESSE/auth/premiere-configuration"
echo "   clé d'installation : $(grep '^CLE_INSTALLATION=' "$ENV" | cut -d= -f2-)"
echo
echo " Chez l'hébergeur (Oracle : Networking > Security Lists), les"
echo " ports 80 et 443 doivent être ouverts en entrée (Ingress)."
if [ -z "$DOMAINE" ]; then
    echo
    echo " Sans nom de domaine, le site est en http : à utiliser seulement"
    echo " pour essayer. Dès que le domaine pointe vers ce serveur :"
    echo "   sudo bash deploiement/installer.sh ton-domaine toi@exemple.com"
fi
echo
echo " Emails : renseigner BREVO_API_KEY et MAIL_DEFAULT_SENDER dans"
echo "   $ENV   puis   sudo systemctl restart toumai-edu-school"
echo " Journal : sudo journalctl -u toumai-edu-school -f"
echo "================================================================"

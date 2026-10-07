#!/usr/bin/env bash
# Installe (ou retire) l'envoi automatique vers GitHub.
#
#   bash outils/installer_envoi_auto.sh              installer et démarrer
#   bash outils/installer_envoi_auto.sh --etat       voir si ça tourne + derniers envois
#   bash outils/installer_envoi_auto.sh --retirer    arrêter et désinstaller
#
# L'installation crée un service utilisateur (systemd) qui démarre à
# chaque ouverture de session et lance outils/envoi_auto_github.sh.

set -e

DEPOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$DEPOT/outils/envoi_auto_github.sh"
NOM="toumai-envoi-github"
DOSSIER_SERVICES="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE="$DOSSIER_SERVICES/$NOM.service"
JOURNAL="$DEPOT/.git/envoi_auto.log"

cd "$DEPOT"

if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user show-environment >/dev/null 2>&1; then
    echo "✗ Les services utilisateur (systemd) ne sont pas disponibles sur cette session."
    echo "  Tu peux quand même lancer la surveillance à la main, tant que le terminal reste ouvert :"
    echo "      bash \"$SCRIPT\""
    exit 1
fi

case "${1:-}" in
    --retirer)
        systemctl --user disable --now "$NOM" >/dev/null 2>&1 || true
        rm -f "$SERVICE"
        systemctl --user daemon-reload
        echo "✓ Envoi automatique arrêté et désinstallé."
        exit 0
        ;;
    --etat)
        if systemctl --user is-active --quiet "$NOM"; then
            echo "✓ L'envoi automatique tourne."
        else
            echo "✗ L'envoi automatique ne tourne pas."
        fi
        [ -f "$JOURNAL" ] && { echo "Dernières lignes du journal :"; tail -n 10 "$JOURNAL"; }
        exit 0
        ;;
esac

# --- Vérifications avant d'installer -------------------------------------

if [ -z "$(git config user.name)" ] || [ -z "$(git config user.email)" ]; then
    echo "✗ Git ne connaît pas ton nom ou ton email (nécessaires pour créer un commit)."
    exit 1
fi

if ! git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
    echo "✗ La branche actuelle n'est reliée à aucune branche GitHub."
    echo "  Fais une fois :  git push -u origin $(git rev-parse --abbrev-ref HEAD)"
    exit 1
fi

echo "Vérification de l'accès à GitHub sans saisie de mot de passe…"
if ! GIT_TERMINAL_PROMPT=0 GIT_ASKPASS= SSH_ASKPASS= git -c core.askPass= push --dry-run >/dev/null 2>&1; then
    cat <<'AIDE'
✗ Git ne peut pas envoyer vers GitHub sans te demander tes identifiants.
  Un service en arrière-plan ne peut pas te poser la question : il faut
  enregistrer l'accès une fois. Dans ce terminal :

      git config --global credential.helper store
      git push

  Saisis ton nom d'utilisateur GitHub et ton jeton d'accès personnel
  (pas ton mot de passe). Git les mémorise dans ~/.git-credentials, en
  clair, lisible seulement par ton compte. Relance ensuite cette
  installation.
AIDE
    exit 1
fi
echo "✓ Accès à GitHub enregistré."

case "$(git config --get credential.helper || true)" in
    cache*) echo "⚠ Ton accès GitHub est mémorisé temporairement (credential.helper=cache) :"
            echo "  l'envoi s'arrêtera quand il expirera. Pour le rendre permanent :"
            echo "      git config --global credential.helper store   puis un  git push" ;;
esac

# --- Installation ---------------------------------------------------------

mkdir -p "$DOSSIER_SERVICES"
# Dans un fichier de service, % est un caractère spécial : on le double.
SCRIPT_ECHAPPE="${SCRIPT//%/%%}"
cat > "$SERVICE" <<UNITE
[Unit]
Description=Envoi automatique de Toumaï Edu School vers GitHub

[Service]
ExecStart=/bin/bash "$SCRIPT_ECHAPPE"
Restart=always
RestartSec=15

[Install]
WantedBy=default.target
UNITE

systemctl --user daemon-reload
systemctl --user enable "$NOM" >/dev/null 2>&1
systemctl --user restart "$NOM"
sleep 2

if systemctl --user is-active --quiet "$NOM"; then
    echo "✓ Envoi automatique installé et démarré."
    echo "  Chaque modification du dossier part sur GitHub environ une minute après."
    echo "  Journal des envois : $JOURNAL"
    echo "  État :    bash outils/installer_envoi_auto.sh --etat"
    echo "  Arrêter : bash outils/installer_envoi_auto.sh --retirer"
else
    echo "✗ Le service n'a pas démarré. Détails :  systemctl --user status $NOM"
    exit 1
fi

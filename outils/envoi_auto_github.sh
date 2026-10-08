#!/usr/bin/env bash
# Envoi automatique vers GitHub.
#
# Surveille le dossier de l'application. Dès que des fichiers ont changé
# et ne bougent plus depuis quelques secondes, crée un commit et le
# pousse vers GitHub. Lancé en arrière-plan par le service installé avec
# outils/installer_envoi_auto.sh — il n'y a rien à lancer à la main.
#
# Message du commit : « vN : description », N suivant le dernier commit.
# La description vient du fichier .message_envoi (première ligne) s'il
# existe à la racine du dossier ; sinon elle résume les parties de
# l'application touchées (ex. « relances, whatsapp, style, tests »).
#
# Le script se relance tout seul quand il est mis à jour.
#
# Journal : .git/envoi_auto.log

set -u

DEPOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DEPOT" || exit 1

INTERVALLE="${ENVOI_AUTO_INTERVALLE:-20}"   # secondes entre deux vérifications
CALME="${ENVOI_AUTO_CALME:-30}"             # secondes sans modification avant d'envoyer
MESSAGE="$DEPOT/.message_envoi"
JOURNAL="$DEPOT/.git/envoi_auto.log"

# Jamais de question posée en arrière-plan (mot de passe, etc.) : si
# l'accès à GitHub n'est pas enregistré, l'envoi échoue tout de suite et
# l'erreur est signalée.
export GIT_TERMINAL_PROMPT=0
unset GIT_ASKPASS SSH_ASKPASS

# Une seule surveillance à la fois.
exec 9>"$DEPOT/.git/envoi_auto.verrou"
flock -n 9 || exit 0

journal() { echo "$(date '+%F %T') $*" >> "$JOURNAL"; }

notifier() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "Envoi GitHub — Toumaï Edu School" "$1" >/dev/null 2>&1 || true
    fi
}

operation_git_en_cours() {
    [ -e .git/index.lock ] || [ -e .git/MERGE_HEAD ] || [ -e .git/CHERRY_PICK_HEAD ] \
        || [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]
}

# Âge (en secondes) de la modification la plus récente parmi les fichiers
# changés ou nouveaux ; 999999 s'il n'y a que des suppressions.
age_derniere_modification() {
    local recent
    recent="$(git ls-files -z --modified --others --exclude-standard 2>/dev/null \
        | xargs -0 -r stat -c %Y 2>/dev/null | sort -n | tail -1)"
    if [ -z "$recent" ]; then echo 999999; else echo $(( $(date +%s) - recent )); fi
}

# Parties de l'application touchées par le commit en préparation, sans
# doublon : nom du module, du service ou du modèle plutôt que « routes.py ».
parties_touchees() {
    git diff --cached --name-only | awk -F/ '
        $1 == "app" && ($2 == "services" || $2 == "models") { sub(/\.py$/, "", $3); print $3; next }
        $1 == "app" && $2 == "templates" && NF > 3 { print $3; next }
        $1 == "app" && $2 == "templates" { sub(/\.html$/, "", $3); sub(/^_/, "", $3); print $3; next }
        $1 == "app" && $2 == "static" { print "style"; next }
        $1 == "app" && NF > 2 { print $2; next }
        $1 == "app" { sub(/\.py$/, "", $2); print ($2 == "__init__" ? "application" : $2); next }
        $1 == "tests" { print "tests"; next }
        $1 == "outils" || $1 == "deploiement" { print $1; next }
        { sub(/^\./, "", $NF); sub(/\.[^.]*$/, "", $NF); print $NF }
    ' | awk '!vu[$0]++' | tr '_' ' '
}

SECRET_SIGNALE=0
creer_commit() {
    git add -A || return 1

    # Garde-fou : les secrets ne partent jamais sur GitHub.
    local secrets
    secrets="$(git diff --cached --name-only | grep -E '(^|/)\.env$|(^|/)instance/' || true)"
    if [ -n "$secrets" ]; then
        git reset -q -- $secrets 2>/dev/null || true
        if [ "$SECRET_SIGNALE" -eq 0 ]; then
            SECRET_SIGNALE=1
            journal "ignoré (fichier sensible, à remettre dans .gitignore) : $(echo "$secrets" | tr '\n' ' ')"
        fi
    fi
    git diff --cached --quiet && return 0

    local prefixe="" dernier description nombre apercu
    dernier="$(git log -1 --pretty=%s 2>/dev/null || true)"
    if [[ "$dernier" =~ ^v([0-9]+) ]]; then
        prefixe="v$(( 10#${BASH_REMATCH[1]} + 1 )) : "
    fi

    description=""
    if [ -s "$MESSAGE" ]; then
        description="$(head -n 1 "$MESSAGE" | tr -d '\r')"
    fi
    if [ -z "$description" ]; then
        local parties total
        nombre="$(git diff --cached --name-only | wc -l)"
        parties="$(parties_touchees)"
        total="$(printf '%s\n' "$parties" | grep -c .)"
        apercu="$(printf '%s\n' "$parties" | head -6 | paste -sd, - | sed 's/,/, /g')"
        [ "$total" -gt 6 ] && apercu="$apercu et $((total - 6)) autre(s)"
        description="$apercu ($nombre fichier(s))"
    fi

    if git commit -q -m "${prefixe}${description}" >> "$JOURNAL" 2>&1; then
        rm -f "$MESSAGE"
        journal "commit : ${prefixe}${description}"
    else
        journal "ERREUR : commit refusé"
        notifier "Le commit automatique a échoué. Voir .git/envoi_auto.log"
        return 1
    fi
}

ECHEC_SIGNALE=0
pousser() {
    # Rien à envoyer si GitHub a déjà tout (compte aussi les commits faits à la main).
    [ -z "$(git rev-list '@{u}..HEAD' 2>/dev/null | head -1)" ] && return 0

    local sortie
    if sortie="$(git -c core.askPass= push 2>&1)"; then
        journal "envoyé sur GitHub : $(git log -1 --pretty=%s)"
        ECHEC_SIGNALE=0
    elif [ "$ECHEC_SIGNALE" -eq 0 ]; then
        ECHEC_SIGNALE=1
        journal "ERREUR : envoi impossible, nouvel essai automatique — $(echo "$sortie" | tail -2 | tr '\n' ' ')"
        notifier "Envoi impossible pour l'instant (connexion ou accès GitHub). Nouvel essai automatique."
    fi
}

journal "surveillance démarrée (vérification toutes les ${INTERVALLE}s, envoi après ${CALME}s de calme)"

SCRIPT="${BASH_SOURCE[0]}"
VERSION_SCRIPT="$(stat -c %Y "$SCRIPT" 2>/dev/null)"

while true; do
    # Script mis à jour (par exemple par un envoi GitHub) : on repart sur
    # la nouvelle version, sans redémarrer le service à la main.
    if [ "$(stat -c %Y "$SCRIPT" 2>/dev/null)" != "$VERSION_SCRIPT" ]; then
        sleep 2
        journal "nouvelle version du script : redémarrage"
        exec 9>&-
        exec /bin/bash "$SCRIPT"
    fi
    if ! operation_git_en_cours; then
        if [ -n "$(git status --porcelain 2>/dev/null)" ] && [ "$(age_derniere_modification)" -ge "$CALME" ]; then
            creer_commit
        fi
        pousser
    fi
    sleep "$INTERVALLE"
done

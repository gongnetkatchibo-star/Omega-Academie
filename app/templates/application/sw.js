/* Service worker de Toumaï Edu School (oct. 2026).

   Rôle : garder une copie des pages déjà consultées pour les relire sans
   connexion. Le réseau passe toujours en premier : la copie ne sert que
   si le réseau ne répond pas. Rien n'est enregistré ni modifié hors
   ligne (les formulaires sont bloqués côté page, voir application.js).

   Confidentialité : les copies sont effacées à la déconnexion et dès
   qu'une page publique (connexion) s'affiche, pour qu'un téléphone
   partagé ne montre pas les pages d'un autre compte. */

const VERSION = "{{ version }}";
const CACHE_PAGES = "toumai-pages";
const CACHE_STATIQUE = "toumai-statique";
const PAGE_HORS_LIGNE = "{{ url_for('main.hors_ligne') }}";
const A_PRECHARGER = {{ a_precharger|tojson }};
const MAX_PAGES = 60;
const MAX_STATIQUE = 80;

// Jamais en copie : connexion, changement de langue, vérification publique.
const EXCLUS = [/^\/auth\//, /^\/langue\//, /^\/verifier/, /^\/sw\.js$/];

self.addEventListener("install", (evenement) => {
  evenement.waitUntil(
    caches.open(CACHE_STATIQUE)
      .then((cache) => cache.addAll([PAGE_HORS_LIGNE, ...A_PRECHARGER]))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evenement) => {
  evenement.waitUntil(
    caches.keys()
      .then((noms) => Promise.all(
        noms.filter((nom) => nom !== CACHE_PAGES && nom !== CACHE_STATIQUE).map((nom) => caches.delete(nom))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (evenement) => {
  if (evenement.data === "vider-pages") {
    evenement.waitUntil(caches.delete(CACHE_PAGES));
  }
});

async function limiter(nomCache, maximum) {
  const cache = await caches.open(nomCache);
  const cles = await cache.keys();
  for (let i = 0; i < cles.length - maximum; i++) {
    await cache.delete(cles[i]);
  }
}

function aGarder(reponse) {
  if (!reponse || !reponse.ok || reponse.redirected || reponse.type !== "basic") return false;
  if ((reponse.headers.get("Cache-Control") || "").includes("no-store")) return false;
  const type = reponse.headers.get("Content-Type") || "";
  return type.startsWith("text/html") || type.startsWith("application/pdf");
}

// Réseau d'abord ; la copie enregistrée ne sert que sans connexion.
async function reseauDabord(requete, nomCache, maximum, garder, secours) {
  try {
    const reponse = await fetch(requete);
    if (garder(reponse)) {
      const copie = reponse.clone();
      caches.open(nomCache)
        .then((cache) => cache.put(requete, copie))
        .then(() => limiter(nomCache, maximum));
    }
    return reponse;
  } catch (erreur) {
    const enregistree = await caches.match(requete, { cacheName: nomCache });
    return enregistree || (secours && (await caches.match(secours))) || Response.error();
  }
}

async function statique(requete) {
  const enregistree = await caches.match(requete, { cacheName: CACHE_STATIQUE });
  if (enregistree) return enregistree;
  const reponse = await fetch(requete);
  if (reponse.ok) {
    const copie = reponse.clone();
    caches.open(CACHE_STATIQUE)
      .then((cache) => cache.put(requete, copie))
      .then(() => limiter(CACHE_STATIQUE, MAX_STATIQUE));
  }
  return reponse;
}

self.addEventListener("fetch", (evenement) => {
  const requete = evenement.request;
  const adresse = new URL(requete.url);
  if (requete.method !== "GET" || adresse.origin !== self.location.origin) return;
  if (EXCLUS.some((motif) => motif.test(adresse.pathname))) return;

  if (adresse.pathname.startsWith("/static/")) {
    evenement.respondWith(statique(requete));
  } else if (requete.mode === "navigate") {
    evenement.respondWith(reseauDabord(requete, CACHE_PAGES, MAX_PAGES, aGarder, PAGE_HORS_LIGNE));
  } else if (adresse.pathname.startsWith("/etablissement/")) {
    // Logo de l'école : propre au compte connecté, effacé avec les pages.
    evenement.respondWith(reseauDabord(requete, CACHE_PAGES, MAX_PAGES,
      (reponse) => reponse.ok && reponse.type === "basic", null));
  }
});

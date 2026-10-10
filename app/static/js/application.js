/* Application installable et lecture hors ligne (oct. 2026).
   Voir app/templates/application/sw.js pour ce qui est gardé en copie. */
(function () {
  "use strict";

  var connecte = document.body.getAttribute("data-connecte") === "oui";

  // 1. Service worker : copies des pages consultées.
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(function (inscription) {
      // Page publique (connexion, déconnexion) : on efface les copies du
      // compte précédent, utile sur un téléphone partagé.
      if (!connecte) {
        var actif = navigator.serviceWorker.controller || inscription.active;
        if (actif) actif.postMessage("vider-pages");
      }
    }).catch(function () { /* navigateur sans prise en charge : le site marche normalement */ });
  }

  // 2. Bandeau « hors ligne » et formulaires bloqués sans connexion.
  var bandeau = document.getElementById("bandeau-hors-ligne");

  function mettreAJour() {
    if (bandeau) bandeau.hidden = navigator.onLine;
    document.documentElement.classList.toggle("hors-ligne-actif", !navigator.onLine);
  }

  window.addEventListener("online", mettreAJour);
  window.addEventListener("offline", mettreAJour);
  mettreAJour();

  // Une copie enregistrée garde les messages du moment où elle a été
  // prise (« Paiement enregistré »…) : sans connexion, ils sont périmés.
  if (!navigator.onLine) {
    document.querySelectorAll(".flashes").forEach(function (liste) { liste.hidden = true; });
  }

  document.addEventListener("submit", function (evenement) {
    if (navigator.onLine) return;
    evenement.preventDefault();
    if (bandeau) {
      bandeau.hidden = false;
      bandeau.classList.remove("bandeau-insiste");
      void bandeau.offsetWidth; // relance l'animation
      bandeau.classList.add("bandeau-insiste");
    }
  }, true);

  // 3. Bouton « Installer l'application » (Android, ordinateur). Sur
  // iPhone, l'installation passe par Partager › Sur l'écran d'accueil.
  var bouton = document.getElementById("bouton-installer");
  var proposition = null;

  window.addEventListener("beforeinstallprompt", function (evenement) {
    evenement.preventDefault();
    proposition = evenement;
    if (bouton) bouton.hidden = false;
  });

  if (bouton) {
    bouton.addEventListener("click", function () {
      if (!proposition) return;
      proposition.prompt();
      proposition.userChoice.then(function () {
        proposition = null;
        bouton.hidden = true;
      });
    });
  }

  window.addEventListener("appinstalled", function () {
    if (bouton) bouton.hidden = true;
  });
})();

/* Tableaux sur téléphone (oct. 2026) : chaque cellule reçoit le titre de
   sa colonne (data-label). La feuille de style s'en sert, en dessous de
   700 px de large, pour présenter chaque ligne comme une fiche. Les
   grilles (emploi du temps, bulletin) gardent leur forme et défilent. */
(function () {
  "use strict";

  var GRILLES = ["table-edt", "table-bulletin"];

  document.querySelectorAll("table.table").forEach(function (tableau) {
    var grille = GRILLES.some(function (classe) { return tableau.classList.contains(classe); });
    var titres = tableau.querySelectorAll("thead tr:first-child th");
    var fusion = tableau.querySelector("tbody [colspan], tbody [rowspan], thead [colspan], thead [rowspan]");
    if (grille || !titres.length || fusion) {
      tableau.classList.add("table-defile");
      return;
    }
    var libelles = Array.prototype.map.call(titres, function (th) { return th.textContent.replace(/\s+/g, " ").trim(); });
    tableau.querySelectorAll("tbody tr").forEach(function (ligne) {
      Array.prototype.forEach.call(ligne.children, function (cellule, rang) {
        if (libelles[rang]) cellule.setAttribute("data-label", libelles[rang]);
      });
    });
    tableau.classList.add("table-fiches");
  });
})();

/* Photos des élèves : chaque image est réduite dans le navigateur avant
   l'envoi (une photo de téléphone pèse plusieurs Mo, il en reste quelques
   dizaines de Ko), puis envoyée sans recharger la page. */
(function () {
  "use strict";
  var zone = document.getElementById("photos");
  if (!zone || !window.fetch || !window.FormData) { return; }
  var jeton = zone.getAttribute("data-jeton");
  var COTE = 600;

  function reduire(fichier) {
    return new Promise(function (resoudre) {
      if (!window.URL || !document.createElement("canvas").toBlob) { resoudre(fichier); return; }
      var image = new Image();
      var adresse = URL.createObjectURL(fichier);
      image.onload = function () {
        URL.revokeObjectURL(adresse);
        var echelle = Math.min(1, COTE / Math.max(image.width, image.height));
        var toile = document.createElement("canvas");
        toile.width = Math.round(image.width * echelle);
        toile.height = Math.round(image.height * echelle);
        var dessin = toile.getContext("2d");
        dessin.fillStyle = "#fff";
        dessin.fillRect(0, 0, toile.width, toile.height);
        dessin.drawImage(image, 0, 0, toile.width, toile.height);
        toile.toBlob(function (reduite) { resoudre(reduite || fichier); }, "image/jpeg", 0.85);
      };
      image.onerror = function () { URL.revokeObjectURL(adresse); resoudre(fichier); };
      image.src = adresse;
    });
  }

  function envoyer(adresse, donnees) {
    return fetch(adresse, {
      method: "POST", body: donnees, credentials: "same-origin",
      headers: { "X-CSRFToken": jeton, "X-Requested-With": "fetch" }
    }).then(function (reponse) {
      return reponse.json().catch(function () { return { ok: false, message: "Envoi refusé (" + reponse.status + ")." }; });
    });
  }

  function nomJpeg(nom) { return nom.replace(/\.[^.]+$/, "") + ".jpg"; }

  function afficher(caseEleve) {
    var cadre = caseEleve.querySelector(".case-photo-image");
    var avait = !!cadre.querySelector("img");
    cadre.innerHTML = "";
    var image = document.createElement("img");
    image.alt = "";
    image.src = caseEleve.getAttribute("data-photo") + "?v=" + Date.now();
    cadre.appendChild(image);
    var compteur = document.getElementById("photos-manquantes");
    if (!avait && compteur) { compteur.textContent = Math.max(0, parseInt(compteur.textContent, 10) - 1); }
  }

  /* Une case par élève. */
  Array.prototype.forEach.call(zone.querySelectorAll(".case-photo"), function (caseEleve) {
    var champ = caseEleve.querySelector("input[type=file]");
    var etat = caseEleve.querySelector(".case-photo-etat");
    champ.addEventListener("change", function () {
      var fichier = champ.files && champ.files[0];
      if (!fichier) { return; }
      etat.textContent = "Envoi…";
      reduire(fichier).then(function (reduite) {
        var donnees = new FormData();
        donnees.append("photo", reduite, nomJpeg(fichier.name || "photo"));
        return envoyer(caseEleve.action, donnees);
      }).then(function (resultat) {
        if (resultat.ok) { afficher(caseEleve); etat.textContent = "Enregistrée"; }
        else { etat.textContent = resultat.message || "Échec de l'envoi."; }
      }).catch(function () { etat.textContent = "Pas de connexion : réessaie."; });
      champ.value = "";
    });
  });

  /* Plusieurs fichiers d'un coup, envoyés un par un. */
  var formulaire = document.getElementById("import-photos");
  if (!formulaire) { return; }
  formulaire.addEventListener("submit", function (evenement) {
    var champ = formulaire.querySelector("input[type=file]");
    var fichiers = Array.prototype.slice.call(champ.files || []);
    if (!fichiers.length) { return; }
    evenement.preventDefault();
    var etat = document.getElementById("import-photos-etat");
    var refus = document.getElementById("import-photos-refus");
    var bouton = formulaire.querySelector("button");
    var rangees = 0, faites = 0;
    refus.innerHTML = "";
    bouton.disabled = true;

    function noter(nom, raison) {
      var ligne = document.createElement("li");
      ligne.textContent = nom + " : " + raison + ".";
      refus.appendChild(ligne);
    }
    function suivant() {
      if (!fichiers.length) {
        etat.textContent = rangees + " photo(s) rangée(s) sur " + faites + ".";
        bouton.disabled = false;
        champ.value = "";
        return;
      }
      var fichier = fichiers.shift();
      faites += 1;
      etat.textContent = "Envoi " + faites + " / " + (faites + fichiers.length) + "…";
      reduire(fichier).then(function (reduite) {
        var donnees = new FormData();
        donnees.append("photos", reduite, nomJpeg(fichier.name));
        return envoyer(zone.getAttribute("data-importer"), donnees);
      }).then(function (resultat) {
        (resultat.rangees || []).forEach(function (r) {
          rangees += 1;
          var caseEleve = zone.querySelector('.case-photo[data-eleve="' + r.eleve_id + '"]');
          if (caseEleve) { afficher(caseEleve); }
        });
        (resultat.refusees || []).forEach(function (r) { noter(fichier.name, r.raison); });
        if (!resultat.rangees && !resultat.refusees) { noter(fichier.name, resultat.message || "envoi refusé"); }
      }).catch(function () { noter(fichier.name, "pas de connexion"); }).then(suivant);
    }
    suivant();
  });
})();

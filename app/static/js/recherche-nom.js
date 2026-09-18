// Transforme tout <select class="recherche-nom"> en champ de recherche
// par début de nom — tape "aw" pour ne voir que "Awa Mbaye", "Awad...".
// Le <select> d'origine reste dans la page (juste caché) : c'est
// toujours lui qui est envoyé au formulaire, aucune route à changer.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("select.recherche-nom").forEach(function (select) {
    const options = Array.from(select.options).filter(o => o.value !== "");
    const optionVide = Array.from(select.options).find(o => o.value === "");

    const conteneur = document.createElement("div");
    conteneur.className = "recherche-nom-conteneur";

    const champ = document.createElement("input");
    champ.type = "text";
    champ.placeholder = optionVide ? optionVide.textContent : "Rechercher un nom…";
    champ.autocomplete = "off";
    champ.value = select.value && select.selectedIndex >= 0 ? select.options[select.selectedIndex].textContent : "";

    const resultats = document.createElement("div");
    resultats.className = "recherche-nom-resultats";

    select.style.display = "none";
    select.parentNode.insertBefore(conteneur, select);
    conteneur.appendChild(champ);
    conteneur.appendChild(resultats);
    conteneur.appendChild(select);

    function afficherResultats(texte) {
      const debut = texte.trim().toLowerCase();
      const correspondances = options.filter(o => o.textContent.trim().toLowerCase().startsWith(debut));
      resultats.innerHTML = "";
      if (!correspondances.length || !debut) {
        resultats.style.display = "none";
        return;
      }
      correspondances.forEach(function (option) {
        const ligne = document.createElement("div");
        ligne.textContent = option.textContent;
        ligne.addEventListener("mousedown", function (e) {
          e.preventDefault();
          select.value = option.value;
          champ.value = option.textContent;
          resultats.style.display = "none";
          select.dispatchEvent(new Event("change"));
        });
        resultats.appendChild(ligne);
      });
      resultats.style.display = "block";
    }

    champ.addEventListener("input", function () {
      if (!champ.value) select.value = "";
      afficherResultats(champ.value);
    });
    champ.addEventListener("focus", function () {
      if (champ.value) afficherResultats(champ.value);
    });
    document.addEventListener("click", function (e) {
      if (!conteneur.contains(e.target)) resultats.style.display = "none";
    });
  });
});

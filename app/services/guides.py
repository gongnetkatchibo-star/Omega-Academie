"""Guides d'utilisation des modules.

Le tableau de bord en montre un aperçu (une carte par module accessible) ;
le guide complet s'ouvre au clic. Chaque guide suit la même trame :
à quoi sert le module, puis les gestes à faire, dans l'ordre."""

from app.services.permissions import role_a_acces

DIRECTION = ("directeur_primaire", "directeur_college", "fondateur", "administrateur_general")

DESCRIPTION_PLATEFORME = (
    "Toute la gestion de l'école au même endroit : inscriptions, notes et bulletins, "
    "scolarité et caisse, emplois du temps, documents officiels et échanges avec les familles."
)


def _guide(cle, titre, icone, apercu, role, etapes, a_savoir=None, endpoint=None,
           roles=(), module=None, pour=None):
    return {
        "cle": cle, "titre": titre, "icone": icone, "apercu": apercu, "role": role,
        "etapes": etapes, "a_savoir": a_savoir or [], "endpoint": endpoint,
        "roles": roles, "module": module, "pour": pour,
    }


GUIDES = [
    _guide(
        "mes_enfants", "Mes enfants", "eleves",
        "Suivre la fiche, la scolarité et le bulletin de chaque enfant.",
        "Chaque enfant rattaché à ton compte apparaît dans le menu, avec trois rubriques.",
        [
            ("Ouvrir le nom de l'enfant", "Dans le menu de gauche, clique sur son nom pour dérouler ses rubriques."),
            ("Fiche", "Sa classe, son matricule et l'état de son dossier."),
            ("Scolarité", "Les frais dus, les paiements enregistrés et le solde restant."),
            ("Bulletin", "Ses notes et sa moyenne, matière par matière."),
        ],
        ["Si un enfant manque, contacte le secrétariat : c'est lui qui rattache les enfants aux comptes."],
        pour="parent",
    ),
    _guide(
        "mon_espace", "Mon espace élève", "eleves",
        "Consulter ta fiche, ton bulletin et ton emploi du temps.",
        "Ton espace regroupe ce qui te concerne, en lecture seule.",
        [
            ("Ma fiche", "Ta classe, ton matricule et l'état de ton dossier."),
            ("Mon bulletin", "Tes notes et ta moyenne, matière par matière."),
            ("Mon emploi du temps", "Les cours de ta classe, jour par jour."),
        ],
        ["Tu te connectes avec ton matricule et ton mot de passe."],
        pour="eleve",
    ),
    _guide(
        "classes", "Classes", "classes",
        "Créer les classes, fixer leurs frais et ouvrir une nouvelle année.",
        "Les classes sont la base de tout : les élèves, les notes, les frais et les emplois du temps s'y rattachent.",
        [
            ("Créer une classe", "« Nouvelle classe » : nom, niveau, année scolaire et frais (inscription, tranches)."),
            ("Ouvrir une classe", "Depuis la liste, on accède à ses élèves et à son emploi du temps."),
            ("Modifier les frais", "Les frais d'une classe se corrigent à tout moment depuis sa ligne."),
            ("Démarrer une nouvelle année", "Recopie les classes de l'année précédente, prêtes à recevoir les élèves."),
        ],
        ["Le même nom de classe ne peut exister qu'une fois par année scolaire."],
        endpoint="classes.liste", roles=("secretaire",) + DIRECTION, module="classes", pour="enseignant",
    ),
    _guide(
        "eleves", "Élèves", "eleves",
        "Inscrire un élève, tenir son dossier et éditer ses documents officiels.",
        "Chaque élève a une fiche : identité, classe, parents, dossier, documents.",
        [
            ("Inscrire", "« Nouvel élève » : nom, classe, date de naissance, genre. Le matricule est créé tout seul."),
            ("Importer depuis Excel", "Télécharge le modèle, remplis-le, renvoie-le : tous les élèves sont créés d'un coup."),
            ("Rattacher les parents", "Sur la fiche, ajoute un ou deux comptes parents : ils verront l'enfant dans leur espace."),
            ("Documents officiels", "Certificat de scolarité et attestation de fréquentation en PDF, depuis la fiche."),
            ("Modifier le dossier", "État civil, famille, personne à prévenir, école d'origine et photo."),
            ("Passage de classe", "En fin d'année, toute une classe passe d'un coup : la décision de chaque élève est proposée d'après sa moyenne."),
            ("Chercher et exporter", "Recherche par nom ou matricule ; la liste se télécharge en PDF, Excel ou CSV."),
        ],
        ["L'élève crée lui-même son compte avec son matricule et sa date de naissance."],
        endpoint="eleves.liste", roles=("secretaire",) + DIRECTION, module="classes", pour="enseignant",
    ),
    _guide(
        "tests_niveau", "Tests de niveau", "tests_niveau",
        "Enregistrer un candidat, saisir sa note : l'admission se décide seule.",
        "Le test d'entrée d'un candidat, de l'enregistrement à l'inscription.",
        [
            ("Enregistrer le candidat", "« Nouveau test » : nom, genre, date de naissance, téléphone du parent, classe demandée."),
            ("Saisir la note", "Dans la liste, tape la note puis « Valider »."),
            ("Décision automatique", "Primaire : sur 10, admis à partir de 5. Collège et autres : sur 20, admis à partir de 10."),
            ("Inscription", "Un candidat admis est inscrit aussitôt dans la classe demandée ; son matricule s'affiche."),
        ],
        ["Une fois l'élève inscrit, la note ne peut plus être modifiée."],
        endpoint="tests_niveau.liste", roles=("secretaire",) + DIRECTION, module="tests_niveau",
    ),
    _guide(
        "notes", "Notes et bulletins", "notes",
        "Saisir les notes, régler les coefficients, éditer les bulletins en PDF.",
        "Les notes se saisissent par classe ; moyennes, rangs et bulletins se calculent tout seuls.",
        [
            ("Créer une évaluation", "Menu « Pédagogie », « Notes et bulletins » : interrogation, devoir ou composition, avec sa date et son coefficient."),
            ("Saisir les notes", "Une note par élève ; ressaisir corrige, vider la case retire la note."),
            ("Coefficients", "Pour chaque classe, le poids de chaque matière dans la moyenne générale."),
            ("Bulletins de la classe", "Le classement de la classe par trimestre ou pour l'année, et tous les bulletins en un seul PDF."),
            ("Bulletin d'un élève", "Moyenne, rang et moyenne de classe par matière ; l'appréciation du conseil se rédige sur la page."),
        ],
        ["La moyenne d'une matière tient compte du coefficient de chaque évaluation.",
         "Sans coefficient réglé, chaque matière compte pour 1."],
        endpoint="notes.index", roles=DIRECTION + ("responsable_pedagogique",), module="notes_supervision", pour="enseignant",
    ),
    _guide(
        "mon_edt", "Mon emploi du temps", "emploi_du_temps",
        "Voir mes créneaux de cours et les classes qui me sont confiées.",
        "Ton planning personnel, tiré des emplois du temps des classes.",
        [
            ("Mon EDT", "Tous tes créneaux de la semaine, classe par classe."),
            ("Mes classes", "Les classes et matières qui te sont affectées."),
            ("Imprimer", "L'emploi du temps d'une classe se télécharge en PDF."),
        ],
        endpoint="emploi_du_temps.moi", pour="enseignant_seul",
    ),
    _guide(
        "enseignants", "Enseignants", "enseignants",
        "Créer les profils des enseignants et leur affecter classes et matières.",
        "Un compte « enseignant » devient un enseignant de l'école une fois son profil créé et ses classes affectées.",
        [
            ("Créer le profil", "« Nouvel enseignant » : choisis le compte déjà validé par le secrétariat."),
            ("Affecter", "Sur sa fiche, ajoute chaque classe et la matière qu'il y enseigne."),
            ("Emploi du temps", "Les créneaux se placent depuis l'emploi du temps de chaque classe."),
            ("Exporter", "La liste des enseignants se télécharge en PDF, Excel ou CSV."),
        ],
        endpoint="enseignants.liste", roles=DIRECTION + ("responsable_pedagogique",), module="enseignants",
    ),
    _guide(
        "suivi_cours", "Suivi des cours", "suivi_cours",
        "Voir où en est le programme dans chaque classe.",
        "L'avancement des programmes, classe par classe et matière par matière.",
        [
            ("Tableau", "Une ligne par classe, avec l'état d'avancement."),
            ("Détail d'une classe", "Par matière : le chapitre en cours, la progression en pourcentage et les difficultés rencontrées."),
        ],
        endpoint="suivi_cours.tableau", roles=DIRECTION + ("responsable_pedagogique",), module="suivi_cours",
    ),
    _guide(
        "scolarite", "Scolarité", "finances",
        "Voir ce que chaque élève doit, ce qu'il a payé et ce qu'il reste.",
        "Le suivi des frais de scolarité, élève par élève.",
        [
            ("Liste", "Chaque élève avec le montant dû, le total payé et le solde."),
            ("Détail d'un élève", "L'échéancier (inscription, tranches) et tous ses paiements."),
            ("Enregistrer un paiement", "Depuis le détail : montant, mode, échéance. Un reçu numéroté est créé et la caisse est mise à jour."),
            ("Retards", "Passé la date limite, ce qui reste dû est compté en retard ; un filtre montre les élèves concernés."),
            ("Remise", "La direction accorde une remise en pourcentage sur la scolarité d'un élève."),
            ("Frais annexes", "Tenue, examen, transport… : pour une classe ou pour toute l'école, payables comme une échéance."),
            ("Relancer", "Un bouton envoie un rappel aux parents d'un élève en retard."),
        ],
        ["Les frais viennent de la classe : on les règle dans « Classes ».",
         "Les dates limites se règlent dans « Établissement ». Les montants sont en francs entiers."],
        endpoint="finances.liste", roles=("comptable", "fondateur", "administrateur_general"), module="finances",
    ),
    _guide(
        "caisse", "Caisse", "caisse",
        "Tenir le journal des recettes et des dépenses de l'école.",
        "Tout ce qui entre et sort de la caisse, avec le solde à jour.",
        [
            ("Nouveau mouvement", "Une recette ou une dépense : date, type, libellé, montant."),
            ("Paiements de scolarité", "Ils arrivent tout seuls dans la caisse, il n'y a rien à ressaisir."),
            ("Reçu", "Chaque encaissement a son reçu en PDF."),
            ("Corriger", "Un mouvement saisi à la main se modifie ou se supprime depuis sa ligne."),
        ],
        endpoint="caisse.liste", roles=("comptable", "fondateur", "administrateur_general"), module="caisse",
    ),
    _guide(
        "salaires", "Salaires", "salaires",
        "Préparer la paie du personnel et garder la trace de chaque paiement.",
        "Le journal de paie : qui a été payé, combien, quand.",
        [
            ("Nouvelle ligne", "Choisis la personne : sa fonction, son email et son téléphone se remplissent seuls."),
            ("Montant", "Additionne les billets ou saisis un autre montant."),
            ("Payer", "Le paiement est enregistré et un email part au bénéficiaire."),
            ("Filtrer et exporter", "Par nom, par date ou par période, en PDF, Excel ou CSV."),
        ],
        endpoint="salaires.liste", roles=("comptable", "fondateur", "administrateur_general"), module="salaires",
    ),
    _guide(
        "statistiques", "Statistiques", "statistiques",
        "Lire en un coup d'œil les effectifs et le recouvrement.",
        "Les indicateurs de l'école, calculés à partir des données saisies.",
        [
            ("Effectifs", "Nombre d'élèves par classe et par genre."),
            ("Recouvrement", "Ce qui est dû, ce qui est encaissé, ce qui reste."),
            ("Exporter", "Les tableaux financiers se téléchargent en PDF, Excel ou CSV."),
        ],
        endpoint="statistiques.tableau",
        roles=("comptable",) + DIRECTION, module="statistiques",
    ),
    _guide(
        "alertes", "Alertes", "alertes",
        "Repérer les élèves aux absences répétées ou aux moyennes faibles.",
        "La liste des situations à surveiller, mise à jour toute seule.",
        [
            ("Absences répétées", "Les élèves qui dépassent le nombre d'absences toléré."),
            ("Moyennes faibles", "Les élèves sous le seuil de réussite de leur classe."),
            ("Agir", "Ouvre la fiche de l'élève pour contacter ses parents."),
        ],
        endpoint="alertes.tableau",
        roles=DIRECTION + ("responsable_pedagogique", "secretaire"), module="alertes",
    ),
    _guide(
        "messagerie", "Messages", "messagerie",
        "Échanger par écrit entre les parents et l'école.",
        "Une conversation par parent, visible par l'école et par lui seul.",
        [
            ("Parent", "Écris ton message : l'école le reçoit et te répond au même endroit."),
            ("École", "La liste montre les conversations, les non lues en premier ; ouvre-en une pour répondre."),
        ],
        endpoint="messagerie.index",
        roles=("secretaire",) + DIRECTION, module="messagerie", pour="parent",
    ),
    _guide(
        "bibliotheque", "Bibliothèque", "bibliotheque",
        "Trouver les livres, cours et exercices mis à disposition.",
        "Les documents numériques de l'école : livres, cours, exercices.",
        [
            ("Chercher", "Parcours la liste ou filtre par type de document."),
            ("Lire ou télécharger", "Selon le document : lecture sur place uniquement, ou téléchargement."),
            ("Ajouter", "Les personnes autorisées déposent un fichier avec son titre et sa matière."),
        ],
        endpoint="bibliotheque.liste", pour="tous",
    ),
    _guide(
        "annonces", "Annonces", "annonces",
        "Lire les communications de l'école et en publier.",
        "Les informations officielles de l'école, adressées à tous ou à un public précis.",
        [
            ("Lire", "Les annonces qui te concernent, de la plus récente à la plus ancienne."),
            ("Publier", "Titre, texte, destinataires et pièce jointe éventuelle (personnes autorisées)."),
            ("Email", "Les destinataires sont aussi prévenus par email."),
        ],
        endpoint="communication.liste", pour="tous",
    ),
    _guide(
        "assistant", "Assistant", "assistant",
        "Poser une question et obtenir une réponse selon tes droits.",
        "L'assistant répond à partir des données auxquelles ton rôle donne accès, jamais au-delà.",
        [
            ("Poser une question", "Écris-la, ou choisis l'une des questions proposées."),
            ("Réponse", "Elle ne contient que ce que ton rôle a le droit de voir."),
        ],
        endpoint="assistant.index", pour="tous",
    ),
    _guide(
        "demandes", "Demandes de comptes", "demandes",
        "Approuver ou refuser les comptes en attente.",
        "Toute personne qui crée un compte attend ici la validation de l'école.",
        [
            ("Vérifier", "Nom, profil demandé, contact."),
            ("Approuver", "Le compte devient actif et la personne peut se connecter."),
            ("Refuser", "La personne est informée à sa prochaine tentative de connexion."),
        ],
        ["Un élève dont le dossier n'a pas de date de naissance passe aussi par ici."],
        endpoint="secretariat.demandes",
        roles=("secretaire", "fondateur", "administrateur_general"), module="secretariat",
    ),
    _guide(
        "roles", "Rôles des comptes", "dev",
        "Attribuer un rôle à chaque compte, verrouiller ou supprimer un compte.",
        "Le rôle d'un compte décide de ce qu'il voit et de ce qu'il peut faire.",
        [
            ("Changer un rôle", "Choisis le rôle et le statut sur la ligne du compte, puis enregistre."),
            ("Verrouiller", "Le compte ne peut plus se connecter, sans rien effacer."),
            ("Supprimer", "Définitif ; refusé si la personne a des salaires dans l'historique."),
        ],
        endpoint="dev.utilisateurs", roles=("developpeur",), module="gestion_roles",
    ),
    _guide(
        "etablissement", "Établissement", "etablissement",
        "Régler l'identité de l'école : nom, logo, filigrane, devise, signataire.",
        "Ces réglages s'appliquent partout : menu, documents PDF, matricules, emails.",
        [
            ("Identité", "Nom officiel, sigle, ville, pays et devise."),
            ("Logo et filigrane", "Le logo du menu et l'image en fond des documents officiels."),
            ("Matricules", "Le préfixe utilisé pour les nouveaux matricules."),
            ("Signataire", "Nom, titre et genre de la personne qui signe les documents."),
            ("Dates limites", "Les dates limites de paiement de l'inscription et des deux tranches."),
        ],
        endpoint="dev.parametres", roles=("developpeur", "fondateur"), module="gestion_roles",
    ),
    _guide(
        "plateforme", "Plateforme", "plateforme",
        "Créer les établissements, y entrer, les suspendre.",
        "La console réservée au super-administrateur : une ligne par école.",
        [
            ("Nouvel établissement", "Son identité et son premier compte fondateur."),
            ("Entrer", "Travailler dans une école comme si on en faisait partie."),
            ("Suspendre", "Les utilisateurs de l'école sont déconnectés jusqu'à la réactivation."),
            ("Restaurer", "Remet en place une sauvegarde (.zip) : les données actuelles de l'école sont remplacées."),
        ],
        endpoint="plateforme.index", pour="developpeur",
    ),
    _guide(
        "profil", "Mon profil", "profil",
        "Changer mon mot de passe et tenir mes numéros à jour.",
        "Tes coordonnées, utilisées par l'école pour te joindre hors de l'application.",
        [
            ("Mot de passe", "Saisis l'actuel puis le nouveau (8 caractères au moins)."),
            ("Ajouter un numéro", "Numéro Airtel ou Moov, avec un libellé (principal, bureau…)."),
            ("Retirer un numéro", "Depuis sa ligne, à tout moment."),
        ],
        endpoint="main.profil", pour="tous",
    ),
]


def _visible(guide, user):
    role = user.role
    pour = guide["pour"]
    if pour == "tous":
        return True
    if pour == "developpeur":
        return role == "developpeur"
    if pour == "eleve":
        return role == "eleve"
    if pour == "enseignant_seul":
        return role == "enseignant"
    if pour == "parent" and (role == "parent" or (guide["cle"] == "mes_enfants" and any(e.actif for e in user.enfants))):
        return True
    if pour == "enseignant" and role == "enseignant":
        return True
    if not guide["roles"]:
        return False
    if role == "developpeur":
        return True
    return role_a_acces(role, guide["module"], list(guide["roles"])) if guide["module"] else role in guide["roles"]


def guides_pour(user):
    return [g for g in GUIDES if _visible(g, user)]


def guide_pour(user, cle):
    return next((g for g in guides_pour(user) if g["cle"] == cle), None)

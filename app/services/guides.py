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
        "Suivre la scolarité, le bulletin, les devoirs et les absences de chaque enfant.",
        "Chaque enfant rattaché à ton compte apparaît dans le menu, avec ses rubriques.",
        [
            ("Ouvrir le nom de l'enfant", "Dans le menu de gauche, clique sur son nom pour dérouler ses rubriques."),
            ("Fiche", "Sa classe, son matricule et l'état de son dossier."),
            ("Scolarité", "Les frais dus, les paiements enregistrés et le solde restant."),
            ("Bulletin", "Ses notes et sa moyenne, matière par matière."),
            ("Devoirs", "Le travail à faire, avec la date de remise, et ce qui a été vu en classe."),
            ("Emploi du temps", "Les cours de sa classe, jour par jour."),
            ("Absences et discipline", "Ses absences, ses retards et les mesures de discipline."),
        ],
        ["Si un enfant manque, contacte le secrétariat : c'est lui qui rattache les enfants aux comptes."],
        pour="parent",
    ),
    _guide(
        "mon_espace", "Mon espace élève", "eleves",
        "Consulter ta fiche, ton bulletin, tes devoirs et ton emploi du temps.",
        "Ton espace regroupe ce qui te concerne, en lecture seule.",
        [
            ("Ma fiche", "Ta classe, ton matricule et l'état de ton dossier."),
            ("Mon bulletin", "Tes notes et ta moyenne, matière par matière."),
            ("Mes devoirs", "Le travail à faire et ce qui a été vu en classe."),
            ("Mon emploi du temps", "Les cours de ta classe, jour par jour."),
            ("Mes absences", "Tes absences et tes retards."),
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
            ("Structure de l'école", "Direction : trimestres, semestres ou séquences ; maternelle et lycée (avec séries) ; liste officielle des matières."),
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
            ("Départ d'un élève", "Sur la fiche, « Départ de l'élève » : motif, date, école d'accueil. Le certificat de radiation s'édite ensuite en PDF."),
            ("Anciens élèves", "Les élèves partis restent consultables et peuvent être réintégrés dans une classe de l'année."),
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
        "preinscriptions", "Pré-inscriptions", "preinscriptions",
        "Les demandes déposées en ligne par les familles, à convoquer au test.",
        "Les familles pré-inscrivent leur enfant depuis la page d'accueil, sans compte.",
        [
            ("Partager l'adresse", "L'adresse de la page de pré-inscription s'affiche en haut de la liste : à envoyer aux familles."),
            ("Traiter une demande", "Ouvre-la : coordonnées, classe souhaitée, message de la famille."),
            ("Convoquer", "Choisis la classe et la date : le test de niveau est créé, la famille reçoit l'email s'il y en a un."),
            ("Refuser", "Avec un motif, envoyé à la famille par email."),
        ],
        ["Le tableau de bord signale les nouvelles demandes.",
         "Sans email, préviens la famille avec le bouton WhatsApp de la demande."],
        endpoint="preinscriptions.liste", roles=("secretaire",) + DIRECTION, module="tests_niveau",
    ),
    _guide(
        "notes", "Notes et bulletins", "notes",
        "Saisir les notes, régler les coefficients, éditer les bulletins en PDF.",
        "Les notes se saisissent par classe ; moyennes, rangs et bulletins se calculent tout seuls.",
        [
            ("Créer une évaluation", "Menu « Pédagogie », « Notes et bulletins » : interrogation, devoir ou composition, avec sa date et son coefficient."),
            ("Saisir les notes", "Une note par élève ; ressaisir corrige, vider la case retire la note."),
            ("Coefficients", "Pour chaque classe, le poids de chaque matière dans la moyenne générale."),
            ("Bulletins de la classe", "Le classement de la classe par période (trimestre, semestre ou séquence) ou pour l'année, et tous les bulletins en un seul PDF."),
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
        "cahier_textes", "Cahier de textes", "cahier_textes",
        "Noter chaque séance et le travail à faire ; les familles voient les devoirs.",
        "Le cahier de textes de chaque classe, tenu par ses enseignants.",
        [
            ("Ouvrir le cahier", "Menu « Pédagogie », « Cahier de textes », puis la classe."),
            ("Nouvelle séance", "La matière, la date, ce qui a été fait et, s'il y en a, le travail à faire et pour quand."),
            ("Côté familles", "Les parents et l'élève voient le travail à faire dans la rubrique « Devoirs »."),
            ("Supervision", "La direction et le responsable pédagogique consultent le cahier de chaque classe."),
        ],
        ["Chaque enseignant n'écrit que pour ses propres matières."],
        endpoint="cahier_textes.index", roles=DIRECTION + ("responsable_pedagogique",), module="cahier_textes",
        pour="enseignant",
    ),
    _guide(
        "discipline", "Retards et discipline", "discipline",
        "Noter retards, avertissements, blâmes et exclusions ; prévenir les parents.",
        "Le registre de discipline de l'école, classe par classe.",
        [
            ("Signaler", "« Signaler un retard ou un incident » : l'élève, le type, la date et le motif."),
            ("Prévenir les parents", "Un email part pour toute mesure de discipline, et au troisième retard du mois."),
            ("Consulter", "Le registre se filtre par classe et par type ; la page d'un élève regroupe ses absences et ses retards."),
        ],
        ["Un enseignant signale pour les élèves de ses classes."],
        endpoint="discipline.registre", roles=DIRECTION + ("responsable_pedagogique", "secretaire"), module="discipline",
        pour="enseignant",
    ),
    _guide(
        "calendrier", "Calendrier scolaire", "calendrier",
        "Rentrée, vacances, jours fériés, compositions et réunions.",
        "Les dates de l'année, visibles par tous ; les prochaines s'affichent sur le tableau de bord.",
        [
            ("Consulter", "Menu « Calendrier scolaire » : les dates à venir, mois par mois."),
            ("Ajouter une date", "Secrétariat et direction : titre, type, début et fin."),
            ("Date interne", "Cocher « Réservé au personnel » la cache aux familles (conseil de classe, réunion pédagogique)."),
        ],
        endpoint="calendrier.index", pour="tous",
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
        "prets", "Livres et prêts", "prets",
        "Tenir le catalogue des livres papier et suivre les prêts.",
        "Chaque livre de la bibliothèque, ses exemplaires et qui les a empruntés.",
        [
            ("Ajouter un livre", "Titre, auteur, cote (le numéro collé sur le livre) et nombre d'exemplaires."),
            ("Prêter", "Sur la page du livre : l'élève ou le membre du personnel, et la date de retour (deux semaines par défaut)."),
            ("Retour", "Un clic quand le livre revient."),
            ("Retards", "La liste des livres non rendus à temps ; « Relancer » envoie un email aux parents."),
        ],
        ["Les livres empruntés par un élève apparaissent aussi sur sa fiche."],
        endpoint="prets.catalogue", roles=("bibliothecaire",) + DIRECTION, module="prets",
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
            ("Primes et retenues", "Facultatives : le net à payer en tient compte, avec leur motif."),
            ("Payer", "Le paiement est enregistré et un email part au bénéficiaire."),
            ("Fiche de paie", "Le PDF de chaque ligne, avec le détail et un QR code ; chacun retrouve les siennes dans « Mon profil »."),
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
            ("Couleurs", "La couleur principale et la couleur d'accent de l'interface de l'école."),
            ("Sécurité", "Option : un code par email à chaque connexion de la direction et de la comptabilité."),
        ],
        endpoint="dev.parametres", roles=("developpeur", "fondateur"), module="gestion_roles",
    ),
    _guide(
        "permissions", "Permissions", "roles",
        "Choisir, rôle par rôle, les modules ouverts dans l'école.",
        "Chaque case ouvre ou ferme un module pour un rôle, dans cette école seulement.",
        [
            ("Cocher ou décocher", "Une ligne par rôle, une colonne par module ; puis « Enregistrer les permissions »."),
            ("Réglage commun", "Ce que l'école ne change pas suit le réglage commun à toutes les écoles."),
            ("Revenir en arrière", "« Revenir au réglage commun » efface les choix propres à l'école."),
        ],
        ["Les zones techniques (rôles, journaux, sauvegarde) restent réglées par le développeur."],
        endpoint="dev.permissions", roles=("fondateur",),
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
            ("Mes fiches de paie", "Pour le personnel : chaque salaire enregistré à ton nom, en PDF."),
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

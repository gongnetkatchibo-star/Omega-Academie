from flask import render_template, request
from flask_login import login_required, current_user

from app.models.classe import Classe
from app.models.eleve import Eleve
from app.models.historique import HistoriqueScolaire
from app.statistiques import statistiques_bp
from app.utils import roles_required, export_csv, export_xlsx, export_pdf_liste
from app.services.cycles import cycle_du_role, filtrer_par_cycle, classe_dans_le_cycle
from app.services.statistiques import (
    stats_reussite, tableau_par_sexe, stats_financieres,
    stats_finance_par_tranche, filtrer_eleves_par_situation, LIBELLES_FILTRE_FINANCE,
)

ROLES_ACCES = ["comptable", "fondateur", "administrateur_general", "directeur_primaire", "directeur_college"]


def annees_disponibles():
    """Toutes les années scolaires connues (classes ou historique),
    la plus récente en premier — pour peupler le sélecteur d'année."""
    depuis_classes = {c.annee_scolaire for c in Classe.query.all()}
    depuis_historique = {h.annee_scolaire for h in HistoriqueScolaire.query.all()}
    return sorted(depuis_classes | depuis_historique, reverse=True)


def _eleves_et_classes_visibles(annee=None):
    """Toutes les classes/élèves visibles pour l'utilisateur connecté,
    en respectant le cloisonnement par cycle (directeur primaire/collège).

    Pour l'année en cours : lecture directe (Eleve.classe_id), la plus
    simple et toujours à jour. Pour une année passée : lecture via
    HistoriqueScolaire — un élève qui a depuis changé de classe ou quitté
    l'école doit quand même apparaître dans les statistiques de l'année
    où il était réellement inscrit (document complémentaire, sept. 2026).

    Retourne aussi `classe_de`, un dict {eleve_id: Classe} qui donne LA
    CLASSE DE L'ÉLÈVE POUR CETTE ANNÉE PRÉCISE — jamais sa classe
    actuelle si on consulte une année passée (sinon les frais et le
    regroupement par classe seraient faux)."""
    annee_courante = Eleve.annee_scolaire_courante()
    annee = annee or annee_courante

    if annee == annee_courante:
        eleves = Eleve.query.filter_by(actif=True).all()
        classe_de = {e.id: e.classe for e in eleves}
    else:
        lignes = HistoriqueScolaire.query.filter_by(annee_scolaire=annee).all()
        eleves = list({l.eleve_id: l.eleve for l in lignes}.values())
        classe_de = {l.eleve_id: l.classe for l in lignes}

    cycle = cycle_du_role(current_user.role)
    if cycle:
        eleves = [e for e in eleves if classe_de.get(e.id) and classe_dans_le_cycle(classe_de[e.id], cycle)]
    classes = filtrer_par_cycle(
        Classe.query.filter_by(annee_scolaire=annee).order_by(Classe.niveau).all(), cycle
    )
    return annee, eleves, classes, classe_de


@statistiques_bp.route("/")
@login_required
@roles_required(*ROLES_ACCES, module="statistiques")
def tableau():
    annee_choisie = request.args.get("annee")
    annee, eleves, classes, classe_de = _eleves_et_classes_visibles(annee_choisie)
    vue = request.args.get("vue", "global")

    if vue.startswith("classe_"):
        classe_id = int(vue.split("_", 1)[1])
        classe_selectionnee = next((c for c in classes if c.id == classe_id), None)
        eleves_vue = [e for e in eleves if classe_selectionnee and classe_de.get(e.id) and classe_de[e.id].id == classe_selectionnee.id]
        titre_vue = classe_selectionnee.nom if classe_selectionnee else "Classe inconnue"
    elif vue == "finances":
        classe_selectionnee = None
        eleves_vue = eleves
        titre_vue = "Finances"
    else:
        vue = "global"
        classe_selectionnee = None
        eleves_vue = eleves
        titre_vue = "Statistique globale"

    contexte = dict(
        annee=annee, annees_disponibles=annees_disponibles(), classes=classes, vue=vue, titre_vue=titre_vue,
        effectif_total=len(eleves_vue),
        garcons=sum(1 for e in eleves_vue if e.sexe == "M"),
        filles=sum(1 for e in eleves_vue if e.sexe == "F"),
    )

    if vue == "finances":
        par_tranche, _ = stats_finance_par_tranche(eleves_vue, annee, classe_de)
        nb_par_filtre = {
            cle: len(filtrer_eleves_par_situation(eleves_vue, annee, cle, classe_de))
            for cle in LIBELLES_FILTRE_FINANCE
        }
        contexte.update(
            par_tranche=par_tranche,
            libelles_filtre=LIBELLES_FILTRE_FINANCE,
            nb_par_filtre=nb_par_filtre,
            **stats_financieres(eleves_vue, annee, classe_de),
        )
    else:
        contexte["tableau_sexe"] = tableau_par_sexe(eleves_vue, annee)
        contexte["stats_globales"] = stats_reussite(eleves_vue, annee)

    return render_template("statistiques/tableau.html", **contexte)


def _lignes_export_finance(eleves, annee, filtre, classe_de=None):
    resultats = filtrer_eleves_par_situation(eleves, annee, filtre, classe_de)
    entetes = ["Matricule", "Nom complet", "Classe", "Parent(s)", "Téléphone"]
    lignes = [
        (e.matricule, e.nom_complet, (classe_de[e.id].nom if classe_de else e.classe.nom),
         ", ".join(p.nom_complet for p in e.parents) or "—",
         e.telephone_parent or "—")
        for e in resultats
    ]
    return entetes, lignes


@statistiques_bp.route("/finances/export/<filtre>/<fmt>")
@login_required
@roles_required(*ROLES_ACCES, module="statistiques")
def export_finance(filtre, fmt):
    if filtre not in LIBELLES_FILTRE_FINANCE:
        return "Filtre inconnu", 404
    annee_choisie = request.args.get("annee")
    annee, eleves, _, classe_de = _eleves_et_classes_visibles(annee_choisie)
    entetes, lignes = _lignes_export_finance(eleves, annee, filtre, classe_de)
    nom_fichier = f"finances_{filtre}"
    sous_titre = LIBELLES_FILTRE_FINANCE[filtre]

    if fmt == "csv":
        return export_csv(entetes, lignes, nom_fichier)
    if fmt == "xlsx":
        return export_xlsx(entetes, lignes, nom_fichier, titre_feuille="Finances")
    if fmt == "pdf":
        return export_pdf_liste(sous_titre, f"Année {annee}", entetes, lignes, nom_fichier)
    return "Format inconnu", 404

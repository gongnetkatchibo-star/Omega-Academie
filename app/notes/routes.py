from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.eleve import Eleve
from app.models.note import Note
from app.notes import notes_bp
from app.utils import roles_required
from app.services.moyennes import bareme_pour_classe

from app.services.cycles import cycle_du_role, classe_dans_le_cycle

ROLES_SUPERVISION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"]
TRIMESTRES = ["T1", "T2", "T3"]


@notes_bp.route("/classe/<int:classe_id>", methods=["GET", "POST"])
@login_required
@roles_required("enseignant")
def saisie(classe_id):
    classe_obj = Classe.query.get_or_404(classe_id)
    profil = current_user.profil_enseignant if current_user.role == "enseignant" else None
    matieres = None

    if current_user.role == "enseignant":
        matieres = [a.matiere for a in profil.affectations if a.classe_id == classe_id] if profil else []
        if not matieres:
            flash("Vous n'enseignez pas dans cette classe.", "error")
            return redirect(url_for("classes.liste"))

    eleves = Eleve.query.filter_by(classe_id=classe_id, actif=True).order_by(Eleve.nom_complet).all()
    bareme = bareme_pour_classe(classe_obj)

    # Matière/trimestre déjà choisis (rechargement en GET) : on prépare les
    # notes existantes pour que l'enseignant les voie et puisse les
    # corriger, plutôt que de ressaisir à l'aveugle.
    matiere_choisie = request.args.get("matiere", "")
    trimestre_choisi = request.args.get("trimestre", "")
    notes_existantes = {}
    if matiere_choisie in (matieres or []) and trimestre_choisi in TRIMESTRES:
        annee = Eleve.annee_scolaire_courante()
        for n in Note.query.filter_by(
            classe_id=classe_id, matiere=matiere_choisie, trimestre=trimestre_choisi, annee_scolaire=annee,
        ).all():
            notes_existantes[n.eleve_id] = n.valeur

    if request.method == "POST" and current_user.role == "enseignant":
        matiere = request.form.get("matiere")
        trimestre = request.form.get("trimestre")

        if matiere not in matieres or trimestre not in TRIMESTRES:
            flash("Merci de choisir une matière que vous enseignez et un trimestre valide.", "error")
        else:
            annee = Eleve.annee_scolaire_courante()
            nb_saisies = 0
            for eleve in eleves:
                valeur_str = request.form.get(f"note_{eleve.id}", "").strip()
                if valeur_str == "":
                    continue
                try:
                    valeur = float(valeur_str)
                except ValueError:
                    continue
                # Corrige la note existante au lieu d'en créer une deuxième
                # (une resaisie pour le même élève/matière/trimestre est
                # une correction, pas un doublon — sinon la moyenne
                # compterait la note deux fois).
                note_existante = Note.query.filter_by(
                    eleve_id=eleve.id, classe_id=classe_id, matiere=matiere,
                    trimestre=trimestre, annee_scolaire=annee,
                ).first()
                if note_existante:
                    note_existante.valeur = valeur
                    note_existante.bareme = bareme
                else:
                    db.session.add(Note(
                        eleve_id=eleve.id, classe_id=classe_id, matiere=matiere,
                        valeur=valeur, bareme=bareme, trimestre=trimestre,
                        annee_scolaire=annee, enseignant_id=profil.id,
                    ))
                nb_saisies += 1
            db.session.commit()
            flash(f"{nb_saisies} note(s) enregistrée(s) (les valeurs déjà saisies ont été corrigées, pas dupliquées).", "info")
            return redirect(url_for("notes.saisie", classe_id=classe_id, matiere=matiere, trimestre=trimestre))

    return render_template(
        "notes/saisie.html", classe=classe_obj, eleves=eleves, matieres=matieres,
        trimestres=TRIMESTRES, bareme=bareme, matiere_choisie=matiere_choisie,
        trimestre_choisi=trimestre_choisi, notes_existantes=notes_existantes,
    )


@notes_bp.route("/bulletin/<int:eleve_id>")
@login_required
def bulletin(eleve_id):
    eleve = Eleve.query.get_or_404(eleve_id)
    # Accès basé sur la relation, pas sur le rôle : n'importe quel compte
    # lié comme parent peut voir le bulletin, en plus de l'enseignant et
    # de la supervision.
    est_lie_comme_parent = current_user in eleve.parents
    est_soi_meme = current_user.role == "eleve" and eleve.user_id == current_user.id
    from app.services.permissions import role_a_acces
    a_droit_supervision = role_a_acces(current_user.role, "notes_supervision", ROLES_SUPERVISION)
    if current_user.role not in ["enseignant", "developpeur"] and not a_droit_supervision and not est_lie_comme_parent and not est_soi_meme:
        abort(403)
    cycle = cycle_du_role(current_user.role)
    if cycle and not classe_dans_le_cycle(eleve.classe, cycle):
        abort(403)
    trimestre = request.args.get("trimestre", "T1")
    annee = Eleve.annee_scolaire_courante()

    notes = Note.query.filter_by(eleve_id=eleve_id, trimestre=trimestre, annee_scolaire=annee).all()

    par_matiere = {}
    for n in notes:
        par_matiere.setdefault(n.matiere, []).append(n)

    lignes = []
    for matiere, notes_matiere in par_matiere.items():
        moyenne = sum(n.valeur_sur_20 for n in notes_matiere) / len(notes_matiere)
        lignes.append({"matiere": matiere, "moyenne": round(moyenne, 2)})

    moyenne_generale = round(sum(l["moyenne"] for l in lignes) / len(lignes), 2) if lignes else None

    classement = None
    if moyenne_generale is not None:
        camarades = Eleve.query.filter_by(classe_id=eleve.classe_id, actif=True).all()
        moyennes_classe = []
        for camarade in camarades:
            notes_c = Note.query.filter_by(eleve_id=camarade.id, trimestre=trimestre, annee_scolaire=annee).all()
            if not notes_c:
                continue
            par_matiere_c = {}
            for n in notes_c:
                par_matiere_c.setdefault(n.matiere, []).append(n)
            moy_c = sum(
                sum(nm.valeur_sur_20 for nm in notes_m) / len(notes_m)
                for notes_m in par_matiere_c.values()
            ) / len(par_matiere_c)
            moyennes_classe.append((camarade.id, round(moy_c, 2)))
        moyennes_classe.sort(key=lambda x: x[1], reverse=True)
        rang = next((i + 1 for i, (eid, _) in enumerate(moyennes_classe) if eid == eleve.id), None)
        classement = f"{rang} / {len(moyennes_classe)}" if rang else None

    return render_template(
        "notes/bulletin.html", eleve=eleve, trimestre=trimestre, trimestres=TRIMESTRES,
        lignes=lignes, moyenne_generale=moyenne_generale, classement=classement,
    )

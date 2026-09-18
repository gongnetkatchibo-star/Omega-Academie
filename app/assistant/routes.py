from flask import render_template, request, current_app
from flask_login import login_required, current_user

from app.assistant import assistant_bp
from app.services.assistant import repondre, questions_suggerees


@assistant_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Assistant (document complémentaire, §6) : applique le principe
    Utilisateur -> Rôle -> Permissions -> Module -> Données avant de
    répondre quoi que ce soit. Fonctionne dès maintenant sans IA
    générative (aucun coût) ; si ANTHROPIC_API_KEY est configurée dans
    .env, c'est ici que le vrai modèle viendrait se brancher — le
    contrôle de permissions resterait strictement le même, appliqué
    avant tout appel au modèle."""
    reponse = None
    question = None

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            reponse = repondre(current_user, question)

    return render_template(
        "assistant/index.html", question=question, reponse=reponse,
        suggestions=questions_suggerees(current_user.role),
        ia_configuree=bool(current_app.config.get("ANTHROPIC_API_KEY")),
    )

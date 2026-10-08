from flask import Blueprint

prets_bp = Blueprint("prets", __name__, url_prefix="/bibliotheque/livres")

from app.prets import routes  # noqa: E402,F401

from flask import Blueprint

preinscriptions_bp = Blueprint("preinscriptions", __name__, url_prefix="/pre-inscriptions")

from app.preinscriptions import routes  # noqa: E402,F401

from flask import Blueprint

gouvernance_bp = Blueprint("gouvernance", __name__, url_prefix="/etablissement")

from app.gouvernance import routes  # noqa: E402,F401

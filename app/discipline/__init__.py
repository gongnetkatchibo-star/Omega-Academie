from flask import Blueprint

discipline_bp = Blueprint("discipline", __name__, url_prefix="/discipline")

from app.discipline import routes  # noqa: E402,F401

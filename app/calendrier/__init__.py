from flask import Blueprint

calendrier_bp = Blueprint("calendrier", __name__, url_prefix="/calendrier")

from app.calendrier import routes  # noqa: E402,F401

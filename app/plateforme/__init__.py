from flask import Blueprint

plateforme_bp = Blueprint("plateforme", __name__, url_prefix="/plateforme")

from app.plateforme import routes  # noqa: E402,F401

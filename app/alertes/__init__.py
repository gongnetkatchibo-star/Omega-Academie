from flask import Blueprint

alertes_bp = Blueprint("alertes", __name__, url_prefix="/alertes")

from app.alertes import routes

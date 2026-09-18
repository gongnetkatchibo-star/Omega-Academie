from flask import Blueprint

suivi_cours_bp = Blueprint("suivi_cours", __name__, url_prefix="/suivi-cours")

from app.suivi_cours import routes

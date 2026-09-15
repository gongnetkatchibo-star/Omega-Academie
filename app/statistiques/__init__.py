from flask import Blueprint

statistiques_bp = Blueprint("statistiques", __name__, url_prefix="/statistiques")

from app.statistiques import routes

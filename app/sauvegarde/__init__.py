from flask import Blueprint

sauvegarde_bp = Blueprint("sauvegarde", __name__, url_prefix="/sauvegarde")

from app.sauvegarde import routes

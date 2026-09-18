from flask import Blueprint

bibliotheque_bp = Blueprint("bibliotheque", __name__, url_prefix="/bibliotheque")

from app.bibliotheque import routes

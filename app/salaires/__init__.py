from flask import Blueprint

salaires_bp = Blueprint("salaires", __name__, url_prefix="/salaires")

from app.salaires import routes

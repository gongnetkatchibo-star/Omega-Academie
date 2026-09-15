from flask import Blueprint

caisse_bp = Blueprint("caisse", __name__, url_prefix="/caisse")

from app.caisse import routes

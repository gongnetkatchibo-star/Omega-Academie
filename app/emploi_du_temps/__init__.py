from flask import Blueprint

emploi_du_temps_bp = Blueprint("emploi_du_temps", __name__, url_prefix="/emploi-du-temps")

from app.emploi_du_temps import routes

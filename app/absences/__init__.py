from flask import Blueprint

absences_bp = Blueprint("absences", __name__, url_prefix="/absences")

from app.absences import routes

from flask import Blueprint

enseignants_bp = Blueprint("enseignants", __name__, url_prefix="/enseignants")

from app.enseignants import routes

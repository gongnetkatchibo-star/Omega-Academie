from flask import Blueprint

eleves_bp = Blueprint("eleves", __name__, url_prefix="/eleves")

from app.eleves import routes

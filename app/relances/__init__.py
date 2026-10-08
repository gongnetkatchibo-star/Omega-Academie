from flask import Blueprint

relances_bp = Blueprint("relances", __name__, url_prefix="/relances")

from app.relances import routes

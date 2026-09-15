from flask import Blueprint

secretariat_bp = Blueprint("secretariat", __name__, url_prefix="/secretariat")

from app.secretariat import routes

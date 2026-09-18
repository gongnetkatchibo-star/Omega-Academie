from flask import Blueprint

dev_bp = Blueprint("dev", __name__, url_prefix="/developpeur")

from app.dev import routes

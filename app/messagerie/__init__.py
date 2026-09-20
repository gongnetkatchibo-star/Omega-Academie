from flask import Blueprint

messagerie_bp = Blueprint("messagerie", __name__, url_prefix="/messagerie")

from app.messagerie import routes

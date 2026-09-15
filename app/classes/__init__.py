from flask import Blueprint

classes_bp = Blueprint("classes", __name__, url_prefix="/classes")

from app.classes import routes

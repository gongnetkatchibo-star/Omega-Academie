from flask import Blueprint

notes_bp = Blueprint("notes", __name__, url_prefix="/notes")

from app.notes import routes

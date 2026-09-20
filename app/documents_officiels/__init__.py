from flask import Blueprint

documents_officiels_bp = Blueprint("documents_officiels", __name__, url_prefix="/documents")

from app.documents_officiels import routes

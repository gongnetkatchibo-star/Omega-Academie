from flask import Blueprint

cahier_textes_bp = Blueprint("cahier_textes", __name__, url_prefix="/cahier-de-textes")

from app.cahier_textes import routes  # noqa: E402,F401

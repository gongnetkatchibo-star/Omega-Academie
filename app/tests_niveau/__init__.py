from flask import Blueprint

tests_niveau_bp = Blueprint("tests_niveau", __name__, url_prefix="/tests-niveau")

from app.tests_niveau import routes

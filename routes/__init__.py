from flask import Blueprint

api = Blueprint('api', __name__)

from . import health, download_index, analyze


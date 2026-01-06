from flask import Blueprint

api = Blueprint('api', __name__)

from . import health, download_index, analyze, find_videos, index_videos, agentic_chat, list_videos


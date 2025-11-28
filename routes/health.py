from flask import jsonify
from . import api


@api.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200



from flask import jsonify
import os
from . import api


@api.route('/health', methods=['GET'])
def health():
    proxy_url = os.environ.get('PROXY_URL', '')
    proxy_configured = bool(proxy_url)
    proxy_preview = f"{proxy_url[:30]}..." if proxy_url and len(proxy_url) > 30 else proxy_url
    
    return jsonify({
        "status": "healthy",
        "proxy_configured": proxy_configured,
        "proxy_preview": proxy_preview if proxy_configured else "not set"
    }), 200



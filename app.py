from flask import Flask, request
from flask_cors import CORS
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import os
import requests
import atexit
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
CORS(app)

@app.before_request
def log_request():
    logger.info(f"Request: {request.method} {request.path}")

@app.after_request
def log_response(response):
    logger.info(f"Response: {response.status_code}")
    return response

TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp_videos')
os.makedirs(TEMP_DIR, exist_ok=True)

from routes import api
app.register_blueprint(api)

@app.route('/')
def home():
    logger.info("Root endpoint accessed")
    return {
        "message": "YouTube Video Analysis API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "download_and_index": "/download-and-index (POST)",
            "analyze": "/analyze (POST)"
        },
        "documentation": "See README.md for full API documentation"
    }, 200

def wake_up_app():
    try:
        app_url = os.getenv('APP_URL', 'http://localhost:5000')
        health_url = f"{app_url}/health"
        response = requests.get(health_url, timeout=9)
        if response.status_code == 200:
            print(f"Successfully pinged {health_url} at {datetime.now()}")
        else:
            print(f"Failed to ping {health_url} (status code: {response.status_code}) at {datetime.now()}")
    except Exception as e:
        print(f"Error occurred while pinging app: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(wake_up_app, 'interval', minutes=9)
scheduler.start()

atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

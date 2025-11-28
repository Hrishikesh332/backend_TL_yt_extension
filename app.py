from flask import Flask
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import os
import requests
import atexit

load_dotenv()

app = Flask(__name__)

TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp_videos')
os.makedirs(TEMP_DIR, exist_ok=True)

from routes import api
app.register_blueprint(api)

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

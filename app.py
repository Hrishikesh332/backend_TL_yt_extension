from flask import Flask
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp_videos')
os.makedirs(TEMP_DIR, exist_ok=True)

from routes import api
app.register_blueprint(api)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

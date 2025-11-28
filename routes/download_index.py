from flask import request, jsonify
import os
import uuid
from . import api
from utils.video_downloader import download_youtube_video
from service.twelvelabs_service import TwelveLabsService

twelvelabs_service = None


def get_twelvelabs_service():
    global twelvelabs_service
    if twelvelabs_service is None:
        twelvelabs_service = TwelveLabsService()
    return twelvelabs_service


@api.route('/download-and-index', methods=['POST'])
def download_and_index():
    try:
        data = request.get_json()
        
        if not data or 'youtube_url' not in data:
            return jsonify({"error": "Missing 'youtube_url' in request body"}), 400
        
        youtube_url = data['youtube_url']
        index_id = os.environ.get('TWELVELABS_INDEX_ID')
        
        if not index_id or index_id == 'your_index_id_here':
            return jsonify({"error": "TWELVELABS_INDEX_ID not configured in .env file"}), 500
        
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp_videos')
        os.makedirs(temp_dir, exist_ok=True)
        
        video_id = str(uuid.uuid4())
        video_path = os.path.join(temp_dir, f"{video_id}.mp4")
        
        print(f"Downloading video from: {youtube_url}")
        downloaded_path = download_youtube_video(youtube_url, video_path)
        
        if not os.path.exists(downloaded_path):
            return jsonify({"error": "Video download failed"}), 500
        
        print(f"Video downloaded to: {downloaded_path}")
        
        service = get_twelvelabs_service()
        
        print(f"Indexing video in TwelveLabs with index_id: {index_id}")
        result = service.upload_video_file(
            index_id=index_id,
            file_path=downloaded_path
        )
        
        if 'error' in result:
            try:
                if os.path.exists(downloaded_path):
                    os.remove(downloaded_path)
            except Exception as e:
                print(f"Warning: Could not delete temp file after error: {e}")
            return jsonify(result), 500
        
        video_id_from_indexing = result.get("video_id")
        if not video_id_from_indexing:
            try:
                if os.path.exists(downloaded_path):
                    os.remove(downloaded_path)
            except Exception as e:
                print(f"Warning: Could not delete temp file after error: {e}")
            return jsonify({"error": "Indexing completed but no video_id returned"}), 500
        
        try:
            if os.path.exists(downloaded_path):
                os.remove(downloaded_path)
                print(f"Temp video file deleted: {downloaded_path}")
        except Exception as e:
            print(f"Warning: Could not delete temp file: {e}")
        
        return jsonify({
            "status": "success",
            "video_id": video_id_from_indexing,
            "message": "Video downloaded and indexed successfully. Ready for analysis."
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


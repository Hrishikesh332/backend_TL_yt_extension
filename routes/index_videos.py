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


@api.route('/index-videos', methods=['POST'])
def index_videos():
    """
    Index one or more YouTube videos using TwelveLabs.
    
    Request Body:
        {
            "video_urls": [
                "https://www.youtube.com/watch?v=...",
                "https://www.youtube.com/watch?v=..."
            ],
            "index_id": "optional_index_id"  // Uses env var if not provided
        }
    
    OR for single video:
        {
            "video_url": "https://www.youtube.com/watch?v=...",
            "index_id": "optional_index_id"
        }
    
    Response:
        {
            "status": "success",
            "indexed_videos": [
                {
                    "video_url": "https://www.youtube.com/watch?v=...",
                    "video_id": "twelvelabs_video_id",
                    "status": "indexed"
                }
            ],
            "failed_videos": []
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Missing request body"}), 400
        
        video_urls = []
        if 'video_urls' in data and isinstance(data['video_urls'], list):
            video_urls = data['video_urls']
        elif 'video_url' in data:
            video_urls = [data['video_url']]
        else:
            return jsonify({"error": "Missing 'video_url' or 'video_urls' in request body"}), 400
        
        if not video_urls:
            return jsonify({"error": "No video URLs provided"}), 400
        
        index_id = data.get('index_id') or os.environ.get('TWELVELABS_INDEX_ID')
        if not index_id or index_id == 'your_index_id_here':
            return jsonify({"error": "TWELVELABS_INDEX_ID not configured. Provide 'index_id' in request or set TWELVELABS_INDEX_ID in environment"}), 400
        
        service = get_twelvelabs_service()
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp_videos')
        os.makedirs(temp_dir, exist_ok=True)
        
        indexed_videos = []
        failed_videos = []
        
        for video_url in video_urls:
            try:
                # Check if video already indexed
                existing_video_id = service.find_video_by_url(index_id, video_url)
                if existing_video_id:
                    print(f"Video already indexed: {video_url} -> {existing_video_id}")
                    indexed_videos.append({
                        "video_url": video_url,
                        "video_id": existing_video_id,
                        "status": "already_indexed"
                    })
                    continue
                
                # Download video
                import re
                video_id_match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11}).*', video_url)
                yt_video_id = video_id_match.group(1) if video_id_match else str(uuid.uuid4())
                
                unique_id = uuid.uuid4().hex[:8]
                video_path = os.path.join(temp_dir, f"yt_{yt_video_id}_{unique_id}.mp4")
                
                print(f"Downloading video: {video_url}")
                downloaded_path = download_youtube_video(video_url, video_path)
                
                if not os.path.exists(downloaded_path):
                    failed_videos.append({
                        "video_url": video_url,
                        "error": "Video download failed"
                    })
                    continue
                
                print(f"Video downloaded: {downloaded_path}")
                
                # Index video
                print(f"Indexing video in TwelveLabs...")
                result = service.upload_video_file(
                    index_id=index_id,
                    file_path=downloaded_path
                )
                
                try:
                    if os.path.exists(downloaded_path):
                        os.remove(downloaded_path)
                        print(f"Temp file deleted: {downloaded_path}")
                except Exception as e:
                    print(f"Warning: Could not delete temp file: {e}")
                
                if 'error' in result:
                    failed_videos.append({
                        "video_url": video_url,
                        "error": result.get('error')
                    })
                    continue
                
                video_id_from_indexing = result.get("video_id")
                if not video_id_from_indexing:
                    failed_videos.append({
                        "video_url": video_url,
                        "error": "Indexing completed but no video_id returned"
                    })
                    continue
                
                indexed_videos.append({
                    "video_url": video_url,
                    "video_id": video_id_from_indexing,
                    "status": "indexed"
                })
                
            except Exception as e:
                print(f"Error processing video {video_url}: {str(e)}")
                failed_videos.append({
                    "video_url": video_url,
                    "error": str(e)
                })
        
        return jsonify({
            "status": "success",
            "indexed_videos": indexed_videos,
            "failed_videos": failed_videos,
            "summary": {
                "total": len(video_urls),
                "indexed": len(indexed_videos),
                "failed": len(failed_videos)
            }
        }), 200
        
    except Exception as e:
        print(f"Error indexing videos: {str(e)}")
        return jsonify({"error": str(e)}), 500



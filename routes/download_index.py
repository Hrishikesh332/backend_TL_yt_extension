from flask import request, jsonify
import os
import uuid
from . import api
from utils.video_downloader import download_youtube_video
from utils.video_processor import clip_video
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
        
        service = get_twelvelabs_service()
        
        existing_video_id = service.find_video_by_url(index_id, youtube_url)
        if existing_video_id:
            print(f"Video already indexed with ID: {existing_video_id}")
            return jsonify({
                "status": "success",
                "video_id": existing_video_id,
                "message": "Video already indexed. Using existing video_id.",
                "already_indexed": True
            }), 200
        
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp_videos')
        os.makedirs(temp_dir, exist_ok=True)
        
        import re
        video_id_match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11}).*', youtube_url)
        yt_video_id = video_id_match.group(1) if video_id_match else str(uuid.uuid4())
        
        unique_id = uuid.uuid4().hex[:8]
        video_path = os.path.join(temp_dir, f"yt_{yt_video_id}_{unique_id}.mp4")
        
        print(f"Downloading video from: {youtube_url}")
        downloaded_path = download_youtube_video(youtube_url, video_path)
        
        if not os.path.exists(downloaded_path):
            return jsonify({"error": "Video download failed"}), 500
        
        print(f"Video downloaded to: {downloaded_path}")
        
        # Check video duration and clip if longer than 1 hour
        video_segments = clip_video(downloaded_path, temp_dir, segment_duration=3600)
        print(f"Video segments to index: {len(video_segments)}")
        
        service = get_twelvelabs_service()
        
        # Index each segment
        segment_video_ids = []
        for segment_idx, segment_path in enumerate(video_segments):
            try:
                print(f"Indexing segment {segment_idx + 1}/{len(video_segments)} in TwelveLabs with index_id: {index_id}")
                result = service.upload_video_file(
                    index_id=index_id,
                    file_path=segment_path
                )
                
                if 'error' in result:
                    print(f"ERROR: TwelveLabs upload failed for segment {segment_idx + 1}: {result.get('error')}")
                    print(f"Full result: {result}")
                    continue
                
                video_id_from_indexing = result.get("video_id")
                if video_id_from_indexing:
                    segment_video_ids.append(video_id_from_indexing)
                    print(f"Segment {segment_idx + 1} indexed successfully: {video_id_from_indexing}")
            except Exception as e:
                print(f"Error indexing segment {segment_idx + 1}: {str(e)}")
            finally:
                # Clean up segment file (keep original if it's the only segment)
                if segment_path != downloaded_path and os.path.exists(segment_path):
                    try:
                        os.remove(segment_path)
                        print(f"Segment file deleted: {segment_path}")
                    except Exception as e:
                        print(f"Warning: Could not delete segment file: {e}")
        
        # Clean up original downloaded file
        try:
            if os.path.exists(downloaded_path):
                os.remove(downloaded_path)
                print(f"Temp video file deleted: {downloaded_path}")
        except Exception as e:
            print(f"Warning: Could not delete temp file: {e}")
        
        if not segment_video_ids:
            return jsonify({"error": "Failed to index any video segments"}), 500
        
        # If multiple segments, return all video IDs
        if len(segment_video_ids) > 1:
            return jsonify({
                "status": "success",
                "video_id": segment_video_ids,  # List of video IDs
                "video_ids": segment_video_ids,  # Alternative key for clarity
                "segments": len(segment_video_ids),
                "message": f"Video downloaded and indexed successfully as {len(segment_video_ids)} segment(s). Ready for analysis."
            }), 200
        else:
            return jsonify({
                "status": "success",
                "video_id": segment_video_ids[0],
                "message": "Video downloaded and indexed successfully. Ready for analysis."
            }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


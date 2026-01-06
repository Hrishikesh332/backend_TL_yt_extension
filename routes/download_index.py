from flask import request, jsonify
import os
import uuid
import threading
import traceback
from collections import defaultdict
from . import api
from utils.video_downloader import download_youtube_video
from utils.video_processor import get_video_duration_from_file, clip_video
from service.twelvelabs_service import TwelveLabsService

# Store chunk video IDs for videos being processed
chunk_video_ids = defaultdict(list)
chunk_lock = threading.Lock()

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
        
        # Check video duration first
        duration = get_video_duration_from_file(downloaded_path)
        is_long_video = duration is not None and duration > 3600
        
        service = get_twelvelabs_service()
        
        if is_long_video:
            print(f"Video is longer than 1 hour ({duration/60:.2f} minutes), will clip and index first chunk immediately")
            video_segments = clip_video(downloaded_path, temp_dir, segment_duration=3600)
            print(f"Video segments created: {len(video_segments)}")
            
            if len(video_segments) > 1:
                # Index first segment immediately
                first_segment = video_segments[0]
                print(f"Indexing first segment immediately: {first_segment}")
                result = service.upload_video_file(
                    index_id=index_id,
                    file_path=first_segment
                )
                
                if 'error' in result:
                    print(f"ERROR: TwelveLabs upload failed for first segment: {result.get('error')}")
                    print(f"Full result: {result}")
                    try:
                        if os.path.exists(downloaded_path):
                            os.remove(downloaded_path)
                    except:
                        pass
                    return jsonify(result), 500
                
                first_video_id = result.get("video_id")
                if not first_video_id:
                    try:
                        if os.path.exists(downloaded_path):
                            os.remove(downloaded_path)
                    except:
                        pass
                    return jsonify({"error": "Indexing completed but no video_id returned for first segment"}), 500
                
                print(f"First segment indexed successfully: {first_video_id}")
                
                # Store first chunk ID
                with chunk_lock:
                    chunk_video_ids[youtube_url] = [first_video_id]
                
                # Clean up first segment file
                if first_segment != downloaded_path and os.path.exists(first_segment):
                    try:
                        os.remove(first_segment)
                    except Exception as e:
                        print(f"Warning: Could not delete first segment file: {e}")
                
                # Process remaining segments in background
                def index_remaining_segments(segments, original_path, vid_url):
                    remaining_segments = segments[1:]
                    
                    for segment_idx, segment_path in enumerate(remaining_segments, start=2):
                        try:
                            print(f"[BACKGROUND] Indexing segment {segment_idx}/{len(segments)}: {segment_path}")
                            result = service.upload_video_file(
                                index_id=index_id,
                                file_path=segment_path
                            )
                            if 'error' not in result and result.get("video_id"):
                                segment_id = result.get("video_id")
                                print(f"[BACKGROUND] Segment {segment_idx} indexed: {segment_id}")
                                
                                # Update stored chunk IDs
                                with chunk_lock:
                                    if vid_url in chunk_video_ids:
                                        chunk_video_ids[vid_url].append(segment_id)
                        except Exception as e:
                            print(f"[BACKGROUND] Error indexing segment {segment_idx}: {str(e)}")
                        finally:
                            if segment_path != original_path and os.path.exists(segment_path):
                                try:
                                    os.remove(segment_path)
                                except:
                                    pass
                    
                    # Clean up original file after all segments processed
                    if os.path.exists(original_path):
                        try:
                            os.remove(original_path)
                            print(f"[BACKGROUND] Original file deleted: {original_path}")
                        except:
                            pass
                    
                    print(f"[BACKGROUND] All segments indexed for {vid_url}. Total chunks: {len(chunk_video_ids.get(vid_url, []))}")
                
                thread = threading.Thread(
                    target=index_remaining_segments,
                    args=(video_segments, downloaded_path, youtube_url),
                    daemon=True
                )
                thread.start()
                
                return jsonify({
                    "status": "success",
                    "video_id": first_video_id,
                    "video_ids": [first_video_id],
                    "chunks": [
                        {
                            "chunk_number": 1,
                            "video_id": first_video_id,
                            "status": "indexed",
                            "time_range": "0:00:00-1:00:00"
                        }
                    ],
                    "segments": len(video_segments),
                    "total_segments": len(video_segments),
                    "indexed_segments": 1,
                    "remaining_segments_processing": True,
                    "message": f"First chunk (1/{len(video_segments)}) indexed and ready for analysis. {len(video_segments)-1} remaining chunk(s) processing in background. Use /api/get-video-chunks?video_url={youtube_url} to get all chunk IDs."
                }), 200
            else:
                # Only one segment (shouldn't happen if duration > 3600, but handle it)
                result = service.upload_video_file(
                    index_id=index_id,
                    file_path=video_segments[0]
                )
                
                if 'error' in result:
                    try:
                        if os.path.exists(downloaded_path):
                            os.remove(downloaded_path)
                    except:
                        pass
                    return jsonify(result), 500
                
                video_id_from_indexing = result.get("video_id")
                if not video_id_from_indexing:
                    try:
                        if os.path.exists(downloaded_path):
                            os.remove(downloaded_path)
                    except:
                        pass
                    return jsonify({"error": "Indexing completed but no video_id returned"}), 500
                
                if video_segments[0] != downloaded_path and os.path.exists(video_segments[0]):
                    try:
                        os.remove(video_segments[0])
                    except:
                        pass
                
                if os.path.exists(downloaded_path):
                    try:
                        os.remove(downloaded_path)
                    except:
                        pass
                
                return jsonify({
                    "status": "success",
                    "video_id": video_id_from_indexing,
                    "message": "Video downloaded and indexed successfully. Ready for analysis."
                }), 200
        else:
            # Video is 1 hour or less - process normally (no changes)
            duration_minutes = f"{duration/60:.2f}" if duration else "unknown"
            print(f"Video is {duration_minutes} minutes, processing normally")
            print(f"Indexing video in TwelveLabs with index_id: {index_id}")
            result = service.upload_video_file(
                index_id=index_id,
                file_path=downloaded_path
            )
            
            print(f"[DEBUG] Upload result type: {type(result)}")
            print(f"[DEBUG] Upload result: {result}")
            print(f"[DEBUG] Result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")
            
            if 'error' in result:
                print(f"ERROR: TwelveLabs upload failed: {result.get('error')}")
                print(f"Full result: {result}")
                try:
                    if os.path.exists(downloaded_path):
                        os.remove(downloaded_path)
                except Exception as e:
                    print(f"Warning: Could not delete temp file after error: {e}")
                return jsonify(result), 500
            
            video_id_from_indexing = result.get("video_id")
            print(f"[DEBUG] Extracted video_id: {video_id_from_indexing}")
            if not video_id_from_indexing:
                print(f"[DEBUG] No video_id in result. Full result: {result}")
                try:
                    if os.path.exists(downloaded_path):
                        os.remove(downloaded_path)
                except Exception as e:
                    print(f"Warning: Could not delete temp file after error: {e}")
                return jsonify({
                    "error": "Indexing completed but no video_id returned",
                    "result": result
                }), 500
            
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
        error_traceback = traceback.format_exc()
        print(f"[ERROR] Exception in download_and_index: {str(e)}")
        print(f"[ERROR] Traceback:\n{error_traceback}")
        return jsonify({
            "error": str(e),
            "traceback": error_traceback
        }), 500


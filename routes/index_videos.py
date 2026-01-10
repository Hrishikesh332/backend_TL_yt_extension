from flask import request, jsonify, Response, stream_with_context
import os
import uuid
import threading
import queue
import json
from datetime import datetime
from collections import defaultdict
from . import api
from utils.video_downloader import download_youtube_video
from utils.video_processor import get_video_duration_from_file, clip_video
from service.twelvelabs_service import TwelveLabsService

# Store chunk video IDs for videos being processed
chunk_video_ids = defaultdict(list)
chunk_lock = threading.Lock()

# Store chunk update queues for streaming
chunk_update_queues = defaultdict(lambda: queue.Queue())
chunk_queue_lock = threading.Lock()

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
                
                # Check video duration first
                duration = get_video_duration_from_file(downloaded_path)
                is_long_video = duration is not None and duration > 3600
                
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
                        
                        if 'error' in result or not result.get("video_id"):
                            failed_videos.append({
                                "video_url": video_url,
                                "error": f"Failed to index first segment: {result.get('error', 'Unknown error')}"
                            })
                            continue
                        
                        first_video_id = result.get("video_id")
                        print(f"First segment indexed successfully: {first_video_id}")
                        
                        # Clean up first segment file
                        if first_segment != downloaded_path and os.path.exists(first_segment):
                            try:
                                os.remove(first_segment)
                            except Exception as e:
                                print(f"Warning: Could not delete first segment file: {e}")
                        
                        # Store first chunk ID
                        with chunk_lock:
                            chunk_video_ids[video_url] = [first_video_id]
                        
                        # Process remaining segments in background
                        def index_remaining_segments(segments, original_path, vid_url):
                            remaining_segments = segments[1:]
                            segment_ids = []
                            
                            for segment_idx, segment_path in enumerate(remaining_segments, start=2):
                                try:
                                    print(f"[BACKGROUND] Indexing segment {segment_idx}/{len(segments)}: {segment_path}")
                                    result = service.upload_video_file(
                                        index_id=index_id,
                                        file_path=segment_path
                                    )
                                    if 'error' not in result and result.get("video_id"):
                                        segment_id = result.get("video_id")
                                        segment_ids.append(segment_id)
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
                        
                        # Get or create update queue for this video
                        with chunk_queue_lock:
                            update_queue = chunk_update_queues.get(video_url)
                        
                        thread = threading.Thread(
                            target=index_remaining_segments,
                            args=(video_segments, downloaded_path, video_url, update_queue),
                            daemon=True
                        )
                        thread.start()
                        
                        indexed_videos.append({
                            "video_url": video_url,
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
                            "status": "indexed",
                            "segments": len(video_segments),
                            "total_segments": len(video_segments),
                            "indexed_segments": 1,
                            "remaining_segments_processing": True,
                            "message": f"First chunk (1/{len(video_segments)}) indexed. {len(video_segments)-1} remaining chunk(s) processing in background."
                        })
                    else:
                        # Only one segment (shouldn't happen if duration > 3600, but handle it)
                        result = service.upload_video_file(
                            index_id=index_id,
                            file_path=video_segments[0]
                        )
                        if 'error' in result or not result.get("video_id"):
                            failed_videos.append({
                                "video_url": video_url,
                                "error": f"Failed to index video: {result.get('error', 'Unknown error')}"
                            })
                            continue
                        
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
                        
                        indexed_videos.append({
                            "video_url": video_url,
                            "video_id": result.get("video_id"),
                            "status": "indexed"
                        })
                else:
                    # Video is 1 hour or less - process normally (no changes)
                    duration_minutes = f"{duration/60:.2f}" if duration else "unknown"
                    print(f"Video is {duration_minutes} minutes, processing normally")
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


@api.route('/index-videos/stream', methods=['POST'])
def index_videos_stream():
    """
    Stream video indexing progress with Server-Sent Events.
    Provides real-time updates as chunks are indexed.
    
    Request Body:
        {
            "video_url": "https://www.youtube.com/watch?v=...",
            "index_id": "optional_index_id"
        }
    
    Response: Server-Sent Events stream with chunk updates
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Missing request body"}), 400
        
        video_url = data.get('video_url')
        if not video_url:
            return jsonify({"error": "Missing 'video_url' in request body"}), 400
        
        index_id = data.get('index_id') or os.environ.get('TWELVELABS_INDEX_ID')
        if not index_id or index_id == 'your_index_id_here':
            return jsonify({"error": "TWELVELABS_INDEX_ID not configured"}), 400
        
        # Create update queue for this video
        update_queue = queue.Queue()
        with chunk_queue_lock:
            chunk_update_queues[video_url] = update_queue
        
        service = get_twelvelabs_service()
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp_videos')
        os.makedirs(temp_dir, exist_ok=True)
        
        def process_video():
            try:
                # Check if already indexed
                existing_video_id = service.find_video_by_url(index_id, video_url)
                if existing_video_id:
                    update_queue.put({
                        "type": "already_indexed",
                        "video_id": existing_video_id,
                        "message": "Video already indexed"
                    })
                    return
                
                # Download video
                import re
                video_id_match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11}).*', video_url)
                yt_video_id = video_id_match.group(1) if video_id_match else str(uuid.uuid4())
                
                unique_id = uuid.uuid4().hex[:8]
                video_path = os.path.join(temp_dir, f"yt_{yt_video_id}_{unique_id}.mp4")
                
                update_queue.put({
                    "type": "status",
                    "status": "downloading",
                    "message": f"Downloading video..."
                })
                
                downloaded_path = download_youtube_video(video_url, video_path)
                
                if not os.path.exists(downloaded_path):
                    update_queue.put({
                        "type": "error",
                        "message": "Video download failed"
                    })
                    return
                
                update_queue.put({
                    "type": "status",
                    "status": "downloaded",
                    "message": "Video downloaded successfully"
                })
                
                # Check video duration
                duration = get_video_duration_from_file(downloaded_path)
                is_long_video = duration is not None and duration > 3600
                
                if is_long_video:
                    update_queue.put({
                        "type": "status",
                        "status": "clipping",
                        "message": f"Video is {duration/60:.2f} minutes, clipping into 1-hour segments"
                    })
                    
                    video_segments = clip_video(downloaded_path, temp_dir, segment_duration=3600)
                    
                    update_queue.put({
                        "type": "clipping_complete",
                        "total_chunks": len(video_segments),
                        "message": f"Video clipped into {len(video_segments)} segment(s)"
                    })
                    
                    if len(video_segments) > 1:
                        # Index first segment
                        first_segment = video_segments[0]
                        update_queue.put({
                            "type": "chunk_started",
                            "chunk_number": 1,
                            "total_chunks": len(video_segments),
                            "message": "Indexing first chunk..."
                        })
                        
                        result = service.upload_video_file(
                            index_id=index_id,
                            file_path=first_segment
                        )
                        
                        if 'error' in result or not result.get("video_id"):
                            update_queue.put({
                                "type": "error",
                                "message": f"Failed to index first chunk: {result.get('error', 'Unknown error')}"
                            })
                            return
                        
                        first_video_id = result.get("video_id")
                        
                        # Store first chunk ID
                        with chunk_lock:
                            chunk_video_ids[video_url] = [first_video_id]
                        
                        update_queue.put({
                            "type": "chunk_completed",
                            "chunk_number": 1,
                            "total_chunks": len(video_segments),
                            "video_id": first_video_id,
                            "time_range": "0:00:00-1:00:00",
                            "message": "First chunk indexed successfully"
                        })
                        
                        # Clean up first segment
                        if first_segment != downloaded_path and os.path.exists(first_segment):
                            try:
                                os.remove(first_segment)
                            except:
                                pass
                        
                        # Process remaining segments in background
                        def index_remaining_segments(segments, original_path, vid_url):
                            remaining_segments = segments[1:]
                            
                            for segment_idx, segment_path in enumerate(remaining_segments, start=2):
                                try:
                                    update_queue.put({
                                        "type": "chunk_started",
                                        "chunk_number": segment_idx,
                                        "total_chunks": len(segments),
                                        "message": f"Indexing chunk {segment_idx}/{len(segments)}..."
                                    })
                                    
                                    result = service.upload_video_file(
                                        index_id=index_id,
                                        file_path=segment_path
                                    )
                                    
                                    if 'error' not in result and result.get("video_id"):
                                        segment_id = result.get("video_id")
                                        
                                        with chunk_lock:
                                            if vid_url in chunk_video_ids:
                                                chunk_video_ids[vid_url].append(segment_id)
                                        
                                        start_hour = segment_idx - 1
                                        end_hour = segment_idx
                                        update_queue.put({
                                            "type": "chunk_completed",
                                            "chunk_number": segment_idx,
                                            "total_chunks": len(segments),
                                            "video_id": segment_id,
                                            "time_range": f"{start_hour}:00:00-{end_hour}:00:00",
                                            "message": f"Chunk {segment_idx}/{len(segments)} indexed successfully"
                                        })
                                    else:
                                        update_queue.put({
                                            "type": "chunk_error",
                                            "chunk_number": segment_idx,
                                            "total_chunks": len(segments),
                                            "error": result.get('error', 'Unknown error'),
                                            "message": f"Failed to index chunk {segment_idx}/{len(segments)}"
                                        })
                                except Exception as e:
                                    update_queue.put({
                                        "type": "chunk_error",
                                        "chunk_number": segment_idx,
                                        "total_chunks": len(segments),
                                        "error": str(e),
                                        "message": f"Error indexing chunk {segment_idx}/{len(segments)}"
                                    })
                                finally:
                                    if segment_path != original_path and os.path.exists(segment_path):
                                        try:
                                            os.remove(segment_path)
                                        except:
                                            pass
                            
                            if os.path.exists(original_path):
                                try:
                                    os.remove(original_path)
                                except:
                                    pass
                            
                            update_queue.put({
                                "type": "all_chunks_completed",
                                "total_chunks": len(segments),
                                "video_url": vid_url,
                                "all_video_ids": chunk_video_ids.get(vid_url, []),
                                "message": f"All {len(segments)} chunk(s) indexed successfully"
                            })
                        
                        thread = threading.Thread(
                            target=index_remaining_segments,
                            args=(video_segments, downloaded_path, video_url),
                            daemon=True
                        )
                        thread.start()
                    else:
                        # Single segment
                        result = service.upload_video_file(
                            index_id=index_id,
                            file_path=video_segments[0]
                        )
                        if 'error' not in result and result.get("video_id"):
                            update_queue.put({
                                "type": "completed",
                                "video_id": result.get("video_id"),
                                "message": "Video indexed successfully"
                            })
                else:
                    # Video <= 1 hour
                    update_queue.put({
                        "type": "status",
                        "status": "indexing",
                        "message": f"Video is {f'{duration/60:.2f}' if duration else 'unknown'} minutes, indexing normally"
                    })
                    
                    result = service.upload_video_file(
                        index_id=index_id,
                        file_path=downloaded_path
                    )
                    
                    if 'error' not in result and result.get("video_id"):
                        update_queue.put({
                            "type": "completed",
                            "video_id": result.get("video_id"),
                            "message": "Video indexed successfully"
                        })
                    else:
                        update_queue.put({
                            "type": "error",
                            "message": result.get('error', 'Unknown error')
                        })
                    
                    if os.path.exists(downloaded_path):
                        try:
                            os.remove(downloaded_path)
                        except:
                            pass
            except Exception as e:
                update_queue.put({
                    "type": "error",
                    "message": str(e)
                })
        
        # Start processing in background
        process_thread = threading.Thread(target=process_video, daemon=True)
        process_thread.start()
        
        def generate():
            """Generate SSE events from update queue"""
            while True:
                try:
                    # Check if thread is still alive or queue has items
                    if not process_thread.is_alive() and update_queue.empty():
                        # Wait a bit for final updates
                        import time
                        time.sleep(0.5)
                        if update_queue.empty():
                            break
                    
                    try:
                        update = update_queue.get(timeout=1)
                        event_data = {
                            **update,
                            "timestamp": datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                        
                        # If it's a completion or error, we're done
                        if update.get("type") in ["completed", "all_chunks_completed", "error", "already_indexed"]:
                            break
                    except queue.Empty:
                        continue
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'timestamp': datetime.now().isoformat()})}\n\n"
                    break
        
        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route('/get-video-chunks', methods=['GET'])
def get_video_chunks():
    """
    Get all chunk video IDs for a video that was chunked.
    
    Query Parameters:
        video_url: YouTube video URL
        
    Response:
        {
            "status": "success",
            "video_url": "https://www.youtube.com/watch?v=...",
            "chunks": [
                {
                    "chunk_number": 1,
                    "video_id": "twelvelabs_video_id",
                    "time_range": "0:00-1:00:00"
                },
                ...
            ],
            "total_chunks": 3
        }
    """
    try:
        video_url = request.args.get('video_url')
        if not video_url:
            return jsonify({"error": "Missing 'video_url' query parameter"}), 400
        
        with chunk_lock:
            chunk_ids = chunk_video_ids.get(video_url, [])
        
        if not chunk_ids:
            return jsonify({
                "status": "not_found",
                "message": "No chunks found for this video. It may not be chunked or processing may not have started."
            }), 404
        
        chunks = []
        for idx, video_id in enumerate(chunk_ids, start=1):
            start_hour = idx - 1
            end_hour = idx
            
            start_time = f"{start_hour}:00:00"
            end_time = f"{end_hour}:00:00"
            
            chunks.append({
                "chunk_number": idx,
                "video_id": video_id,
                "time_range": f"{start_time}-{end_time}",
                "status": "indexed"
            })
        
        return jsonify({
            "status": "success",
            "video_url": video_url,
            "chunks": chunks,
            "total_chunks": len(chunks),
            "all_video_ids": chunk_ids
        }), 200
        
    except Exception as e:
        print(f"Error getting video chunks: {str(e)}")
        return jsonify({"error": str(e)}), 500
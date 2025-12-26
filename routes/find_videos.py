from flask import request, jsonify, Response, stream_with_context
import json
import os
from . import api
from service.browserbase_service import BrowserbaseService

browserbase_service = None


def get_browserbase_service():
    global browserbase_service
    if browserbase_service is None:
        browserbase_service = BrowserbaseService()
    return browserbase_service


@api.route('/find-videos', methods=['POST'])
def find_videos():

    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Missing request body"}), 400
        
        search_query = data.get('search_query')
        if not search_query:
            return jsonify({"error": "Missing 'search_query' in request body"}), 400
        
        max_videos = data.get('max_videos', 3)
        if not isinstance(max_videos, int) or max_videos < 1:
            max_videos = 3
        
        # Limit max_videos to prevent abuse
        if max_videos > 5:
            max_videos = 5
        
        stream = request.args.get('stream', 'false').lower() == 'true'
        
        if stream:
            return _find_videos_stream(search_query, max_videos)
        else:
            service = get_browserbase_service()
            
            print(f"Finding videos for query: '{search_query}' (max: {max_videos})")
            videos = service.discover_youtube_videos(search_query, max_videos)
            
            return jsonify({
                "status": "success",
                "videos": videos,
                "count": len(videos)
            }), 200
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Error finding videos: {str(e)}")
        return jsonify({"error": str(e)}), 500


def _find_videos_stream(search_query: str, max_videos: int):
    import threading
    import queue
    from datetime import datetime
    
    status_queue = queue.Queue()
    result_queue = queue.Queue()
    
    def status_callback(status, message):
        status_queue.put({"status": status, "message": message})
    
    def run_discovery():
        try:
            service = get_browserbase_service()
            videos = service.discover_youtube_videos(
                search_query, 
                max_videos, 
                status_callback=status_callback
            )
            result_queue.put(("success", videos))
        except Exception as e:
            result_queue.put(("error", str(e)))
    
    discovery_thread = threading.Thread(target=run_discovery, daemon=True)
    discovery_thread.start()
    
    def generate():
        videos = None
        error_message = None
        discovery_complete = False
        
        while not discovery_complete:
            while not status_queue.empty():
                try:
                    status_update = status_queue.get_nowait()
                    event_data = {
                        "status": status_update["status"],
                        "message": status_update["message"],
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                except queue.Empty:
                    break
            
            if not result_queue.empty():
                try:
                    result_type, result_value = result_queue.get_nowait()
                    if result_type == "success":
                        videos = result_value
                    else:
                        error_message = result_value
                    discovery_complete = True
                except queue.Empty:
                    pass
            
            if not discovery_thread.is_alive() and not discovery_complete:
                try:
                    result_type, result_value = result_queue.get_nowait()
                    if result_type == "success":
                        videos = result_value
                    else:
                        error_message = result_value
                    discovery_complete = True
                except queue.Empty:
                    error_message = "Discovery completed without result"
                    discovery_complete = True
            
            if not discovery_complete:
                import time
                time.sleep(0.1)  
        
        while not status_queue.empty():
            try:
                status_update = status_queue.get_nowait()
                event_data = {
                    "status": status_update["status"],
                    "message": status_update["message"],
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(event_data)}\n\n"
            except queue.Empty:
                break
        
        if videos is not None:
            event_data = {
                "status": "completed",
                "message": f"Found {len(videos)} videos",
                "videos": videos,
                "count": len(videos),
                "timestamp": datetime.now().isoformat()
            }
        else:
            event_data = {
                "status": "error",
                "message": error_message or "Unknown error occurred",
                "timestamp": datetime.now().isoformat()
            }
        
        yield f"data: {json.dumps(event_data)}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


from flask import request, jsonify, Response, stream_with_context
import json
from . import api
from service.agentic_service import AgenticService

agentic_service = None


def get_agentic_service():
    global agentic_service
    if agentic_service is None:
        agentic_service = AgenticService()
    return agentic_service

# Agentic chat API that understands user intent and routes to appropriate actions.
@api.route('/agentic-chat', methods=['POST'])
def agentic_chat():

    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Missing request body"}), 400
        
        user_query = data.get('query') or data.get('message') or data.get('text')
        if not user_query:
            return jsonify({"error": "Missing 'query', 'message', or 'text' in request body"}), 400
        
        conversation_context = data.get('conversation_context', {})
        
        service = get_agentic_service()
        
        print(f"Processing agentic query: '{user_query}'")
        result = service.process_query(user_query, conversation_context)
        
        response_data = {
            "status": "success",
            "response": result.get("response", "")
        }
        
        if "intent" in result and result.get("intent"):
            response_data["intent"] = result["intent"]
        if "found_videos" in result and result.get("found_videos"):
            response_data["found_videos"] = result["found_videos"]
        if "video_id" in result and result.get("video_id"):
            response_data["video_id"] = result["video_id"]
        if "analysis_result" in result and result.get("analysis_result"):
            response_data["analysis_result"] = result["analysis_result"]
        if "indexed_videos" in result and result.get("indexed_videos"):
            response_data["indexed_videos"] = result["indexed_videos"]
        
        return jsonify(response_data), 200
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Error in agentic chat: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api.route('/agentic-chat/stream', methods=['POST'])
def agentic_chat_stream():

    from datetime import datetime
    import queue
    import threading
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Missing request body"}), 400
        
        user_query = data.get('query') or data.get('message') or data.get('text')
        if not user_query:
            return jsonify({"error": "Missing 'query', 'message', or 'text' in request body"}), 400
        
        conversation_context = data.get('conversation_context', {})
        service = get_agentic_service()
        
        status_queue = queue.Queue()
        result_queue = queue.Queue()
        
        def status_callback(status, message):
            """Collect status updates from video discovery."""
            status_queue.put({"status": status, "message": message})
        
        def process_query():
            """Process query in background thread."""
            try:
                result = service.process_query(user_query, conversation_context, status_callback=status_callback)
                result_queue.put(("success", result))
            except Exception as e:
                result_queue.put(("error", str(e)))
        
        # Start processing in background
        process_thread = threading.Thread(target=process_query, daemon=True)
        process_thread.start()
        
        def generate():
            """Generate SSE events."""
            result = None
            error_msg = None
            complete = False
            
            # Send initial status
            yield f"data: {json.dumps({'status': 'starting', 'message': 'Processing your request...', 'timestamp': datetime.now().isoformat()})}\n\n"
            
            while not complete:
                status_updates_yielded = False
                while not status_queue.empty():
                    try:
                        status_update = status_queue.get_nowait()
                        event_data = {
                            "status": status_update["status"],
                            "message": status_update["message"],
                            "timestamp": datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                        status_updates_yielded = True
                    except queue.Empty:
                        break
                
                if not status_updates_yielded:

                    if not result_queue.empty():
                        try:
                            result_type, result_value = result_queue.get_nowait()
                            if result_type == "success":
                                result = result_value
                            else:
                                error_msg = result_value
                            complete = True
                        except queue.Empty:
                            pass
                    
                    if not process_thread.is_alive() and not complete:
                        import time
                        time.sleep(0.2) 
                        
                        if not result_queue.empty():
                            try:
                                result_type, result_value = result_queue.get_nowait()
                                if result_type == "success":
                                    result = result_value
                                else:
                                    error_msg = result_value
                                complete = True
                            except queue.Empty:
                                pass
                        
                        if not complete:
                            try:
                                result_type, result_value = result_queue.get(timeout=0.1)
                                if result_type == "success":
                                    result = result_value
                                else:
                                    error_msg = result_value
                            except queue.Empty:
                                error_msg = "Processing completed without result"
                            complete = True
                    
                    if not complete:
                        import time
                        time.sleep(0.05) 
            
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
            
            if result:
                event_data = {
                    "status": "completed",
                    "response": result.get("response", ""),
                    "timestamp": datetime.now().isoformat()
                }
                
                if "intent" in result and result.get("intent"):
                    event_data["intent"] = result["intent"]
                if "found_videos" in result and result.get("found_videos"):
                    event_data["found_videos"] = result["found_videos"]
                if "video_id" in result and result.get("video_id"):
                    event_data["video_id"] = result["video_id"]
                if "analysis_result" in result and result.get("analysis_result"):
                    event_data["analysis_result"] = result["analysis_result"]
                if "indexed_videos" in result and result.get("indexed_videos"):
                    event_data["indexed_videos"] = result["indexed_videos"]
            else:
                event_data = {
                    "status": "error",
                    "message": error_msg or "Unknown error",
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
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


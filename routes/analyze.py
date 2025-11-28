from flask import request, jsonify, Response, stream_with_context
import json
from . import api
from service.twelvelabs_service import TwelveLabsService


twelvelabs_service = None


def get_twelvelabs_service():
    global twelvelabs_service
    if twelvelabs_service is None:
        twelvelabs_service = TwelveLabsService()
    return twelvelabs_service


@api.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Missing request body"}), 400
        
        video_id = data.get('video_id')
        prompt = data.get('prompt', '')
        analysis_type = data.get('analysis_type', 'open-ended')
        
        if not video_id:
            return jsonify({"error": "Missing 'video_id' in request body"}), 400
        
        if analysis_type == 'open-ended' and not prompt:
            return jsonify({"error": "Missing 'prompt' for open-ended analysis"}), 400
        
        service = get_twelvelabs_service()
        
        if not prompt and analysis_type != 'open-ended':
            prompt_map = {
                'title': 'Generate a title for this video',
                'topic': 'What are the main topics in this video?',
                'hashtag': 'Generate relevant hashtags for this video',
                'summary': 'Provide a summary of this video',
                'chapter': 'Break down this video into chapters',
                'highlight': 'What are the highlights of this video?'
            }
            prompt = prompt_map.get(analysis_type, 'Analyze this video')
        
        def generate():
            try:
                yield json.dumps({
                    "status": "success",
                    "video_id": video_id,
                    "analysis_type": analysis_type,
                    "streaming": True
                }) + "\n"
                
                for chunk in service.analyze_video_stream(video_id, prompt):
                    yield json.dumps({"chunk": chunk}) + "\n"
                
                yield json.dumps({"done": True}) + "\n"
            except Exception as e:
                yield json.dumps({"error": str(e)}) + "\n"
        
        return Response(stream_with_context(generate()), mimetype='application/x-ndjson')
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500



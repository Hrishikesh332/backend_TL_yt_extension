from flask import request, jsonify
import os
from . import api
from service.twelvelabs_service import TwelveLabsService

twelvelabs_service = None


def get_twelvelabs_service():
    global twelvelabs_service
    if twelvelabs_service is None:
        twelvelabs_service = TwelveLabsService()
    return twelvelabs_service


@api.route('/list-videos', methods=['GET'])
def list_videos():

    try:
        # Get index_id from query param or environment
        index_id = request.args.get('index_id') or os.environ.get('TWELVELABS_INDEX_ID')
        
        if not index_id or index_id == 'your_index_id_here':
            return jsonify({"error": "TWELVELABS_INDEX_ID not configured. Provide 'index_id' query parameter or set TWELVELABS_INDEX_ID in environment."}), 400
        
        # Get pagination parameters
        fetch_all = request.args.get('all', 'false').lower() == 'true'
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 5)), 1000)  # Default 5 per page, max 1000
        
        service = get_twelvelabs_service()
        
        all_videos = []
        current_page = page
        
        if fetch_all:
            # Fetch all pages (but still respect limit per page)
            print(f"[LIST-VIDEOS] Fetching all videos from index: {index_id} (limit: {limit} per page)")
            while True:
                videos = service.get_videos(index_id, page=current_page)
                if not videos:
                    break
                
                # Apply limit per page
                if len(videos) > limit:
                    videos = videos[:limit]
                
                all_videos.extend(videos)
                print(f"[LIST-VIDEOS] Fetched page {current_page}: {len(videos)} videos (total so far: {len(all_videos)})")
                
                # Check if there are more pages (if we got fewer than limit, we're probably on last page)
                # Note: TwelveLabs API doesn't always provide total count, so we check by trying next page
                if len(videos) < limit:
                    break
                current_page += 1
                
                # Safety limit to prevent infinite loops
                if current_page > 1000:
                    print(f"[LIST-VIDEOS] Reached safety limit of 1000 pages")
                    break
            
            total_videos = len(all_videos)
            total_pages = current_page if len(all_videos) > 0 else 0
            
        else:
            # Fetch single page with limit
            print(f"[LIST-VIDEOS] Fetching page {page} from index: {index_id} (limit: {limit})")
            all_videos = service.get_videos(index_id, page=page)
            
            # Apply limit
            if len(all_videos) > limit:
                all_videos = all_videos[:limit]
            
            total_videos = len(all_videos)
            total_pages = 1  # We don't know total pages without fetching all
        
        # Format response with pagination info
        has_more = False
        if not fetch_all:
            # Check if there might be more pages by fetching next page
            next_page_videos = service.get_videos(index_id, page=page + 1)
            has_more = len(next_page_videos) > 0
        
        return jsonify({
            "status": "success",
            "videos": all_videos,
            "total": total_videos,
            "page": page if not fetch_all else 1,
            "limit": limit,
            "has_more": has_more if not fetch_all else False,
            "pages": total_pages if fetch_all else ("unknown" if not has_more else page + 1),
            "index_id": index_id,
            "fetched_all": fetch_all
        }), 200
        
    except ValueError as e:
        return jsonify({"error": f"Invalid parameter: {str(e)}"}), 400
    except Exception as e:
        print(f"[ERROR] Error listing videos: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


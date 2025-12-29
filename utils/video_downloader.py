import yt_dlp
import os
import time


def download_youtube_video(url, output_path):
    proxy_url = os.environ.get('PROXY_URL')
    
    if proxy_url:
        print(f"[PROXY] Using proxy: {proxy_url[:50]}...")
    else:
        print("[PROXY] No proxy configured. Downloading directly.")
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            ydl_opts = {
                'format': '18/22/best[ext=mp4]/best',
                'outtmpl': output_path,
                'quiet': False,
                'no_warnings': True,
                'ignoreerrors': False,
                'noplaylist': True,
                'merge_output_format': 'mp4',
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['ios', 'android'],
                        'player_skip': ['webpage', 'configs'],
                    }
                },
                'geo_bypass': True,
                'geo_bypass_country': 'US',
                'nocheckcertificate': True,
                'socket_timeout': 60,
                'retries': 5,
                'fragment_retries': 5,
                'skip_unavailable_fragments': True,
                'source_address': '0.0.0.0',
            }
            
            if proxy_url:
                ydl_opts['proxy'] = proxy_url
                os.environ['HTTP_PROXY'] = proxy_url
                os.environ['HTTPS_PROXY'] = proxy_url
                os.environ['http_proxy'] = proxy_url
                os.environ['https_proxy'] = proxy_url
            
            print(f"[DOWNLOAD] Attempt {attempt + 1}/{max_retries}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"[DOWNLOAD] Extracting video info from: {url}")
                info = ydl.extract_info(url, download=False)
                
                if info is None:
                    raise Exception("Failed to extract video info")
                
                video_title = info.get('title', 'video')
                print(f"[DOWNLOAD] Found video: {video_title}")
                print(f"[DOWNLOAD] Starting download...")
                
                ydl.download([url])
                
                if os.path.exists(output_path):
                    print(f"[DOWNLOAD] Success! File saved to: {output_path}")
                    return output_path
                
                output_dir = os.path.dirname(output_path)
                base_name_without_ext = os.path.splitext(os.path.basename(output_path))[0]
                
                if os.path.exists(output_dir):
                    for filename in os.listdir(output_dir):
                        if filename.startswith(base_name_without_ext):
                            full_path = os.path.join(output_dir, filename)
                            if os.path.isfile(full_path) and not filename.endswith('.part'):
                                print(f"[DOWNLOAD] Success! File saved to: {full_path}")
                                return full_path
                
                base_name = os.path.splitext(output_path)[0]
                for ext in ['.mkv', '.mp4', '.webm', '.m4a']:
                    if os.path.exists(base_name + ext):
                        print(f"[DOWNLOAD] Success! File saved to: {base_name + ext}")
                        return base_name + ext
                
                raise Exception(f"Downloaded file not found. Expected: {output_path}")
                
        except Exception as e:
            last_error = str(e)
            print(f"[ERROR] Attempt {attempt + 1}: {last_error}")
            
            if attempt < max_retries - 1:
                wait_time = 3 * (attempt + 1)
                print(f"[RETRY] Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
    
    raise Exception(f"Error downloading video after {max_retries} attempts: {last_error}")

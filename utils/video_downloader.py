import yt_dlp
import os
import time


def download_youtube_video(url, output_path):
    # Get proxy URL from environment variable
    proxy_url = os.environ.get('PROXY_URL')
    
    if proxy_url:
        print(f"Using proxy for YouTube download: {proxy_url[:30]}...")
    else:
        print("No proxy configured. Downloading directly.")
    
    # Try different client strategies for bot detection bypass
    client_strategies = [
        ['mweb', 'ios'],  # Mobile web + iOS (most reliable)
        ['ios', 'android'],
        ['android', 'web'],
        ['web'],
    ]
    
    max_retries = 3
    last_error = None
    
    for strategy_idx, client_list in enumerate(client_strategies):
        for attempt in range(max_retries):
            try:
                ydl_opts = {
                    # Use formats that don't require PO tokens (18=360p, 22=720p, 135+140=480p)
                    'format': '18/22/135+140/134+140/best[ext=mp4]/best',
                    'outtmpl': output_path,
                    'quiet': False,
                    'no_warnings': True,  # Suppress PO token warnings
                    'ignoreerrors': False,  # Still show actual errors
                    'noplaylist': True,
                    'merge_output_format': 'mp4',
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Upgrade-Insecure-Requests': '1',
                    },
                    'extractor_args': {
                        'youtube': {
                            'player_client': client_list,
                            'player_skip': ['webpage'],
                        }
                    },
                    'age_limit': None,
                    'geo_bypass': True,
                    'nocheckcertificate': True,
                    'socket_timeout': 30,
                }
                
                # Add proxy if configured
                if proxy_url:
                    ydl_opts['proxy'] = proxy_url
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    video_title = info.get('title', 'video')
                    print(f"Downloading: {video_title} (Strategy {strategy_idx + 1}/{len(client_strategies)}, Attempt {attempt + 1}/{max_retries})")
                    
                    ydl.download([url])
                    
                    if os.path.exists(output_path):
                        return output_path
                    
                    output_dir = os.path.dirname(output_path)
                    base_name_without_ext = os.path.splitext(os.path.basename(output_path))[0]
                    
                    if os.path.exists(output_dir):
                        for filename in os.listdir(output_dir):
                            if filename.startswith(base_name_without_ext):
                                full_path = os.path.join(output_dir, filename)
                                if os.path.isfile(full_path):
                                    return full_path
                    
                    base_name = os.path.splitext(output_path)[0]
                    for ext in ['.mkv', '.mp4', '.webm', '.m4a']:
                        if os.path.exists(base_name + ext):
                            return base_name + ext
                    
                    raise Exception(f"Downloaded file not found. Expected: {output_path}")
            except Exception as e:
                last_error = str(e)
                error_str = str(e).lower()
                
                # If it's a bot detection error, try next strategy
                if 'bot' in error_str or 'sign in' in error_str or '403' in error_str:
                    if strategy_idx < len(client_strategies) - 1:
                        print(f"Bot detection triggered. Trying next strategy...")
                        break  # Break to next strategy
                    elif attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"Download attempt {attempt + 1} failed: {last_error}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        continue  # Try next strategy
                else:
                    # Other errors, retry with same strategy
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"Download attempt {attempt + 1} failed: {last_error}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        continue  # Try next strategy
    
    # If all strategies failed
    raise Exception(f"Error downloading video after trying {len(client_strategies)} strategies: {last_error}")



import yt_dlp
import os
import time


def download_youtube_video(url, output_path):
    # Get proxy URL from environment variable
    proxy_url = os.environ.get('PROXY_URL')
    
    if proxy_url:
        print(f"[PROXY] Using proxy: {proxy_url[:50]}...")
    else:
        print("[PROXY] No proxy configured. Downloading directly.")
    
    # Strategies optimized for proxy usage
    # When using proxy, simpler clients work better
    if proxy_url:
        client_strategies = [
            ['web'],  # Web client works best with proxies
            ['mweb'],  # Mobile web as fallback
            ['android'],
            ['ios'],
        ]
    else:
        client_strategies = [
            ['mweb', 'ios'],
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
                    'format': '18/22/135+140/134+140/best[ext=mp4]/best',
                    'outtmpl': output_path,
                    'quiet': False,
                    'verbose': True,  # Enable verbose logging for debugging
                    'no_warnings': False,  # Show warnings to debug proxy issues
                    'ignoreerrors': False,
                    'noplaylist': True,
                    'merge_output_format': 'mp4',
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    },
                    'extractor_args': {
                        'youtube': {
                            'player_client': client_list,
                            'player_skip': ['webpage', 'configs'],
                        }
                    },
                    'age_limit': None,
                    'geo_bypass': True,
                    'geo_bypass_country': 'US',
                    'nocheckcertificate': True,
                    'socket_timeout': 60,
                    'retries': 5,
                    'fragment_retries': 5,
                    'skip_unavailable_fragments': True,
                    'source_address': '0.0.0.0',  # Force IPv4
                }
                
                # Add proxy configuration if available
                if proxy_url:
                    ydl_opts['proxy'] = proxy_url
                    # Also set environment variables for subprocess calls
                    os.environ['HTTP_PROXY'] = proxy_url
                    os.environ['HTTPS_PROXY'] = proxy_url
                    os.environ['http_proxy'] = proxy_url
                    os.environ['https_proxy'] = proxy_url
                    print(f"[PROXY] Configured proxy in yt-dlp and environment variables")
                
                print(f"[DOWNLOAD] Strategy {strategy_idx + 1}/{len(client_strategies)}: {client_list}, Attempt {attempt + 1}/{max_retries}")
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # First extract info to verify connection works
                    print(f"[DOWNLOAD] Extracting video info from: {url}")
                    info = ydl.extract_info(url, download=False)
                    
                    if info is None:
                        raise Exception("Failed to extract video info - info is None")
                    
                    video_title = info.get('title', 'video')
                    print(f"[DOWNLOAD] Found video: {video_title}")
                    print(f"[DOWNLOAD] Starting download...")
                    
                    ydl.download([url])
                    
                    # Check for downloaded file
                    if os.path.exists(output_path):
                        print(f"[DOWNLOAD] Success! File saved to: {output_path}")
                        return output_path
                    
                    # Search for file with different extensions
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
                error_str = str(e).lower()
                print(f"[ERROR] Strategy {strategy_idx + 1}, Attempt {attempt + 1}: {last_error}")
                
                # Check for various error types
                is_blocking_error = any(x in error_str for x in [
                    'bot', 'sign in', '403', 'forbidden', 
                    'player response', 'unavailable', 'private',
                    'connection', 'timeout', 'proxy'
                ])
                
                if is_blocking_error:
                    if strategy_idx < len(client_strategies) - 1:
                        print(f"[RETRY] Switching to next strategy...")
                        break  # Break to next strategy
                    elif attempt < max_retries - 1:
                        wait_time = 3 * (attempt + 1)
                        print(f"[RETRY] Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                else:
                    if attempt < max_retries - 1:
                        wait_time = 2 * (attempt + 1)
                        print(f"[RETRY] Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
    
    # If all strategies failed
    raise Exception(f"Error downloading video after trying {len(client_strategies)} strategies: {last_error}")

import yt_dlp
import os
import time
import shutil
import tempfile


def download_youtube_video(url, output_path):
    proxy_url = os.environ.get('PROXY_URL')
    
    # Get cookies file path - check multiple locations
    cookies_source = None
    cookies_paths = [
        '/etc/secrets/cookies.txt',  # Render deployment (check first)
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cookies.txt'),  # Local: project root
        os.path.join(os.getcwd(), 'cookies.txt'),  # Current working directory
    ]
    
    print(f"[DEBUG] Checking cookies paths...")
    for path in cookies_paths:
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        readable = False
        first_line = ""
        if exists:
            try:
                with open(path, 'r') as f:
                    first_line = f.readline().strip()
                    readable = True
            except Exception as e:
                print(f"[DEBUG]   {path}: exists but cannot read: {e}")
        print(f"[DEBUG]   {path}: exists={exists}, size={size}, readable={readable}")
        if exists and size > 0 and readable:
            cookies_source = path
            print(f"[DEBUG] ✅ Found cookies at: {cookies_source}")
            print(f"[DEBUG]   First line: {first_line[:50]}...")
            break
    
    cookies_available = cookies_source is not None
    cookies_file = None
    
    if cookies_available:
        # If source is read-only (like /etc/secrets/), copy to writable location
        if cookies_source.startswith('/etc/secrets/'):
            try:
                temp_dir = tempfile.gettempdir()
                cookies_file = os.path.join(temp_dir, 'cookies_ytdlp.txt')
                shutil.copy2(cookies_source, cookies_file)
                # Make sure it's writable
                os.chmod(cookies_file, 0o644)
                print(f"[DEBUG] ✅ Copied cookies to writable location: {cookies_file}")
            except Exception as e:
                print(f"[DEBUG] ⚠️  Failed to copy cookies: {e}")
                cookies_file = cookies_source  # Fallback to original (may fail if yt-dlp writes)
        else:
            # Check if original location is writable
            if os.access(cookies_source, os.W_OK):
                cookies_file = cookies_source
            else:
                # Copy to temp if not writable
                try:
                    temp_dir = tempfile.gettempdir()
                    cookies_file = os.path.join(temp_dir, 'cookies_ytdlp.txt')
                    shutil.copy2(cookies_source, cookies_file)
                    os.chmod(cookies_file, 0o644)
                    print(f"[DEBUG] ✅ Copied cookies to writable location: {cookies_file}")
                except Exception as e:
                    print(f"[DEBUG] ⚠️  Failed to copy cookies: {e}")
                    cookies_file = cookies_source  # Fallback
    
    if not cookies_available:
        print(f"[DEBUG] ❌ No cookies file found in any location")
    
    if cookies_available and cookies_file:
        print(f"[COOKIES] Using cookies file: {cookies_file}")
    else:
        print("[COOKIES] No cookies file found")
    
    if proxy_url:
        print(f"[PROXY] Proxy available: {proxy_url[:50]}...")
    else:
        print("[PROXY] No proxy configured.")
    
    # Strategy: Use proxy-first approach (as it was working before)
    # When proxy is available, use it with web/mweb clients (as previous working version)
    strategies = []
    
    # Proxy was working before - use it first with the client strategies that worked
    if proxy_url:
        # Use the exact client order that worked before: ['web'], ['mweb'], ['android'], ['ios']
        strategies.append({'use_cookies': False, 'use_proxy': True, 'fake_ip': False, 'name': 'Proxy only (web client)', 'client_order': ['web']})
        strategies.append({'use_cookies': False, 'use_proxy': True, 'fake_ip': False, 'name': 'Proxy only (mweb client)', 'client_order': ['mweb']})
        strategies.append({'use_cookies': False, 'use_proxy': True, 'fake_ip': False, 'name': 'Proxy only (android client)', 'client_order': ['android']})
        strategies.append({'use_cookies': False, 'use_proxy': True, 'fake_ip': False, 'name': 'Proxy only (ios client)', 'client_order': ['ios']})
    
    # Then try cookies combinations
    if cookies_available:
        if proxy_url:
            strategies.append({'use_cookies': True, 'use_proxy': True, 'fake_ip': False, 'name': 'Cookies + Proxy'})
        strategies.append({'use_cookies': True, 'use_proxy': False, 'fake_ip': False, 'name': 'Cookies only'})
    
    # Fallback: no cookies, no proxy
    strategies.append({'use_cookies': False, 'use_proxy': False, 'fake_ip': False, 'name': 'Direct'})
    
    last_error = None
    
    for strategy_idx, strategy in enumerate(strategies):
        # Wait 6 seconds between strategies (except for the first one)
        if strategy_idx > 0:
            print(f"\n[WAIT] Waiting 6 seconds before next strategy...")
            time.sleep(6)
        
        print(f"\n[STRATEGY {strategy_idx + 1}/{len(strategies)}] {strategy['name']}")
        
        for attempt in range(3):
            try:
                # Fake IP configurations - different countries and IPs
                fake_ip_configs = [
                    {'country': 'US', 'ip': '104.28.45.67', 'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
                    {'country': 'GB', 'ip': '185.199.108.153', 'ua': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'},
                    {'country': 'DE', 'ip': '138.201.81.199', 'ua': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'},
                    {'country': 'CA', 'ip': '99.79.189.123', 'ua': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'},
                ]
                
                # Select fake IP config based on attempt
                fake_config = fake_ip_configs[attempt % len(fake_ip_configs)]
                
                # Base headers
                http_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                }
                
                geo_country = 'US'
                
                # Apply fake IP settings
                if strategy.get('fake_ip'):
                    http_headers = {
                        'User-Agent': fake_config['ua'],
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'X-Forwarded-For': fake_config['ip'],
                        'X-Real-IP': fake_config['ip'],
                        'CF-Connecting-IP': fake_config['ip'],
                    }
                    geo_country = fake_config['country']
                    print(f"[FAKE-IP] Using IP: {fake_config['ip']} Country: {geo_country}")
                
                # Choose player client - use specific client from strategy if specified
                # Otherwise use default based on proxy usage
                if 'client_order' in strategy:
                    player_clients = strategy['client_order']
                elif strategy['use_proxy'] and proxy_url:
                    player_clients = ['web', 'mweb', 'ios', 'android']  # Fallback
                else:
                    player_clients = ['ios', 'android']
                
                ydl_opts = {
                    'format': '18/22/135+140/134+140/best[ext=mp4]/best',  # Use formats that worked before
                    'outtmpl': output_path,
                    'quiet': False,
                    'no_warnings': True,
                    'ignoreerrors': False,
                    'noplaylist': True,
                    'merge_output_format': 'mp4',
                    'http_headers': http_headers,
                    'extractor_args': {
                        'youtube': {
                            'player_client': player_clients,
                            'player_skip': ['webpage', 'configs'],
                        }
                    },
                    'geo_bypass': True,
                    'geo_bypass_country': geo_country,
                    'nocheckcertificate': True,
                    'socket_timeout': 60,
                    'retries': 5,
                    'fragment_retries': 5,
                    'skip_unavailable_fragments': True,
                    'source_address': '0.0.0.0',
                }
                
                # Apply strategy - set proxy first and ensure it's used
                if strategy['use_proxy'] and proxy_url:
                    ydl_opts['proxy'] = proxy_url
                    # Set proxy env vars for all subprocess calls
                    os.environ['HTTP_PROXY'] = proxy_url
                    os.environ['HTTPS_PROXY'] = proxy_url
                    os.environ['http_proxy'] = proxy_url
                    os.environ['https_proxy'] = proxy_url
                    # Also set for requests library
                    ydl_opts['http_chunk_size'] = 10485760  # 10MB chunks
                    print(f"[PROXY] Using proxy: {proxy_url[:50]}...")
                    print(f"[PROXY] Player clients: {player_clients}")
                else:
                    # Clear proxy env vars to ensure no proxy is used
                    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
                        if key in os.environ:
                            del os.environ[key]
                    print(f"[PROXY] Proxy disabled for this strategy")
                
                if strategy['use_cookies'] and cookies_available:
                    ydl_opts['cookiefile'] = cookies_file
                
                print(f"[DOWNLOAD] Attempt {attempt + 1}/3")
                
                # Verify proxy is set correctly
                if strategy['use_proxy'] and proxy_url:
                    print(f"[DEBUG] Proxy in ydl_opts: {ydl_opts.get('proxy', 'NOT SET')}")
                    print(f"[DEBUG] HTTP_PROXY env: {os.environ.get('HTTP_PROXY', 'NOT SET')[:50] if os.environ.get('HTTP_PROXY') else 'NOT SET'}")
                
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
                
                # If bot detection, try next strategy immediately
                if 'bot' in str(e).lower() or 'sign in' in str(e).lower():
                    print(f"[INFO] Bot detection, trying next strategy...")
                    break
                
                if attempt < 2:
                    wait_time = 2 * (attempt + 1)
                    print(f"[RETRY] Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
    
    raise Exception(f"Error downloading video after trying all strategies: {last_error}")

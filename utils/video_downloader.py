import yt_dlp
import os
import time


def download_youtube_video(url, output_path):
    ydl_opts = {
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]/bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best',
        'outtmpl': output_path,
        'quiet': False,
        'no_warnings': False,
        'noplaylist': True,
        'merge_output_format': 'mp4',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'player_skip': ['webpage', 'configs'],
            }
        },
        'geo_bypass': True,
        'nocheckcertificate': True,
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                video_title = info.get('title', 'video')
                print(f"Downloading: {video_title} (Attempt {attempt + 1}/{max_retries})")
                
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
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Download attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise Exception(f"Error downloading video after {max_retries} attempts: {str(e)}")



import yt_dlp
import os


def download_youtube_video(url, output_path):
    ydl_opts = {
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]/bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best',
        'outtmpl': output_path,
        'quiet': False,
        'no_warnings': False,
        'noplaylist': True,
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'video')
            print(f"Downloading: {video_title}")
            
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
        raise Exception(f"Error downloading video: {str(e)}")



import yt_dlp
import subprocess
import os
import math
from typing import List, Optional


def get_video_duration(url: str) -> Optional[float]:
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and 'duration' in info:
                duration = info.get('duration', 0)
                print(f"[DURATION] Video duration: {duration} seconds ({duration/60:.2f} minutes)")
                return float(duration)
        
        return None
    except Exception as e:
        print(f"[DURATION] Error getting video duration: {e}")
        return None


def get_video_duration_from_file(file_path: str) -> Optional[float]:
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        duration = float(result.stdout.strip())
        print(f"[DURATION] File duration: {duration} seconds ({duration/60:.2f} minutes)")
        return duration
    except subprocess.CalledProcessError as e:
        print(f"[DURATION] Error getting file duration: {e}")
        return None
    except Exception as e:
        print(f"[DURATION] Unexpected error: {e}")
        return None


def clip_video(input_path: str, output_dir: str, segment_duration: int = 3600) -> List[str]:
    try:
        duration = get_video_duration_from_file(input_path)
        if duration is None:
            print(f"[CLIP] Could not determine video duration, skipping clipping")
            return [input_path]
        
        if duration <= segment_duration:
            print(f"[CLIP] Video is {duration/60:.2f} minutes, no clipping needed")
            return [input_path]
        
        print(f"[CLIP] Video is {duration/60:.2f} minutes, clipping into {segment_duration/60:.0f}-minute segments")
        
        num_segments = math.ceil(duration / segment_duration)
        print(f"[CLIP] Creating {num_segments} segment(s)")
        
        os.makedirs(output_dir, exist_ok=True)
        
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_paths = []
        
        for i in range(num_segments):
            start_time = i * segment_duration
            output_path = os.path.join(output_dir, f"{base_name}_segment_{i+1:03d}.mp4")
            
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-ss', str(start_time),
                '-t', str(segment_duration),
                '-c', 'copy',
                '-avoid_negative_ts', 'make_zero',
                '-y',
                output_path
            ]
            
            print(f"[CLIP] Creating segment {i+1}/{num_segments}: {output_path}")
            print(f"[CLIP] Command: {' '.join(cmd)}")
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=600  # 10 minute timeout per segment
                )
                
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    output_paths.append(output_path)
                    print(f"[CLIP] Segment {i+1} created successfully: {output_path}")
                else:
                    print(f"[CLIP] Warning: Segment {i+1} file not found or empty")
                    
            except subprocess.TimeoutExpired:
                print(f"[CLIP] Error: Segment {i+1} creation timed out")
            except subprocess.CalledProcessError as e:
                print(f"[CLIP] Error creating segment {i+1}: {e.stderr}")
                print(f"[CLIP] Retrying segment {i+1} with re-encoding...")
                cmd_reencode = [
                    'ffmpeg',
                    '-i', input_path,
                    '-ss', str(start_time),
                    '-t', str(segment_duration),
                    '-c:v', 'libx264',
                    '-c:a', 'aac',
                    '-avoid_negative_ts', 'make_zero',
                    '-y',
                    output_path
                ]
                try:
                    subprocess.run(cmd_reencode, capture_output=True, text=True, check=True, timeout=600)
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        output_paths.append(output_path)
                        print(f"[CLIP] Segment {i+1} created with re-encoding: {output_path}")
                except Exception as e2:
                    print(f"[CLIP] Failed to create segment {i+1} even with re-encoding: {e2}")
        
        if not output_paths:
            print(f"[CLIP] Warning: No segments created, returning original file")
            return [input_path]
        
        print(f"[CLIP] Successfully created {len(output_paths)} segment(s)")
        return output_paths
        
    except Exception as e:
        print(f"[CLIP] Error during clipping: {e}")
        return [input_path]


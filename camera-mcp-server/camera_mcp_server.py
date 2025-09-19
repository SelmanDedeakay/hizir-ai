from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
import os
import threading
import time
import subprocess
from datetime import datetime, timedelta
import re
import glob
from pathlib import Path

mcp = FastMCP("camera_server")

cameras = {
            #"ANADOLU HİSARI": "https://livestream.ibb.gov.tr/cam_turistik/b_anadoluhisari.stream/playlist.m3u8",
            #"BEYAZIT KULESİ 1": "https://livestream.ibb.gov.tr/cam_turistik/b_beyazitkule.stream/playlist.m3u8",
            #"BEYAZIT KULESİ 2": "https://livestream.ibb.gov.tr/cam_turistik/b_beyazitkule2new.stream/playlist.m3u8",
            #"BEYAZIT MEYDANI": "https://livestream.ibb.gov.tr/cam_turistik/b_beyazitmeydani.stream/playlist.m3u8",
            #"BÜYÜK ÇAMLICA": "https://livestream.ibb.gov.tr/cam_turistik/b_buyukcamlıca.stream/playlist.m3u8",  # Fixed encoding
            #"DRAGOS": "https://livestream.ibb.gov.tr/cam_turistik/b_dragos.stream/playlist.m3u8",
            #"EMİNÖNÜ": "https://livestream.ibb.gov.tr/cam_turistik/b_eminonu.stream/playlist.m3u8",
            #"EMİRGAN": "https://livestream.ibb.gov.tr/cam_turistik/b_emirgan.stream/playlist.m3u8",
            #"EYÜP SULTAN": "https://livestream.ibb.gov.tr/cam_turistik/b_eyupsultan.stream/playlist.m3u8",
            #"HİDİV KASRI": "https://livestream.ibb.gov.tr/cam_turistik/b_hidivkasri.stream/playlist.m3u8",
            #"KADIKÖY": "https://livestream.ibb.gov.tr/cam_turistik/b_kadikoy2.stream/playlist.m3u8",
            "KAPALI ÇARŞI": "https://livestream.ibb.gov.tr/cam_turistik/b_kapalicarsi.stream/playlist.m3u8",
            #"KIZ KULESİ": "https://livestream.ibb.gov.tr/cam_turistik/new_Kızkulesi.stream/playlist.m3u8",
            "METROHAN": "https://livestream.ibb.gov.tr/cam_turistik/b_metrohan.stream/playlist.m3u8",
            "ORTAKÖY": "https://livestream.ibb.gov.tr/cam_turistik/b_ortakoy.stream/playlist.m3u8",
            #"PİERRE LOTTİ": "https://livestream.ibb.gov.tr/cam_turistik/b_pierreloti.stream/playlist.m3u8",
            #"SALACAK": "https://livestream.ibb.gov.tr/cam_turistik/b_salacak.stream/playlist.m3u8",
            "SARAÇHANE": "https://livestream.ibb.gov.tr/cam_turistik/b_sarachane.stream/playlist.m3u8",
            #"SEPETÇİLER KASRI": "https://livestream.ibb.gov.tr/cam_turistik/b_sepetcilerkasri.stream/playlist.m3u8",
            "SULTANAHMET 1": "https://livestream.ibb.gov.tr/cam_turistik/b_sultanahmet.stream/playlist.m3u8",
            #"SULTANAHMET 2": "https://livestream.ibb.gov.tr/cam_turistik/b_sultanahmet2.stream/playlist.m3u8",
            "TAKSİM MEYDANI": "https://livestream.ibb.gov.tr/cam_turistik/b_taksim_meydan.stream/playlist.m3u8",
            #"ULUS PARKI": "https://livestream.ibb.gov.tr/cam_turistik/b_ulus_parki.stream/playlist.m3u8",
            #"ÜSKÜDAR": "https://livestream.ibb.gov.tr/cam_turistik/b_uskudar.stream/playlist.m3u8"
        }

# Create recordings directory
os.makedirs("recordings", exist_ok=True)

def sanitize_filename(name):
    """Convert camera name to a safe filename"""
    # Replace special characters with underscores
    safe_name = re.sub(r'[^\w\s-]', '_', name)
    # Replace spaces and multiple underscores with single underscore
    safe_name = re.sub(r'[\s_]+', '_', safe_name)
    # Remove leading/trailing underscores
    return safe_name.strip('_')

def check_ffmpeg():
    """Check if ffmpeg is available"""
    # Try different possible ffmpeg locations
    ffmpeg_paths = [
        'ffmpeg',  # System PATH
        'ffmpeg.exe',  # Windows executable
        r'C:\ffmpeg\bin\ffmpeg.exe',  # Common manual installation location
        os.path.join(os.getcwd(), 'ffmpeg.exe'),  # Local directory
    ]
    
    for ffmpeg_path in ffmpeg_paths:
        try:
            result = subprocess.run([ffmpeg_path, '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"Found FFmpeg at: {ffmpeg_path}")
                return ffmpeg_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    return None

def record_camera(camera_name, m3u8_url):
    """Record 1-minute MP4 files continuously for a camera"""
    safe_name = sanitize_filename(camera_name)
    
    # Check if ffmpeg is available
    ffmpeg_path = check_ffmpeg()
    if not ffmpeg_path:
        print(f"FFmpeg not found for {camera_name}! Please install FFmpeg.")
        print("See INSTALL_FFMPEG.md for installation instructions.")
        return
    
    while True:
        try:
            start_time = datetime.now()
            # Create timestamp for filename
            timestamp = start_time.strftime('%Y%m%d_%H%M%S')
            filename = f"recordings/{safe_name}_{timestamp}.mp4"
            
            print(f"Starting recording: {filename}")
            
            # Use ffmpeg to record 1 minute of video as MP4 with lower quality settings
            cmd = [
                ffmpeg_path, '-y',  # Use found ffmpeg path, -y flag overwrites existing files
                '-i', m3u8_url,
                '-t', '60',  # Record for 60 seconds
                '-c:v', 'libx264',  # Video codec
                '-preset', 'ultrafast',  # Fastest encoding preset
                '-crf', '28',  # Lower quality (higher CRF = lower quality, saves resources)
                '-vf', 'scale=640:360',  # Downscale to 360p to save space and processing
                '-r', '15',  # Reduce frame rate to 15fps
                '-c:a', 'aac',  # Audio codec
                '-b:a', '64k',  # Lower audio bitrate
                '-f', 'mp4',  # Output format
                '-loglevel', 'error',  # Only show errors to reduce output
                filename
            ]
            
            # Run ffmpeg
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                print(f"Successfully recorded: {filename}")
                
                # Clean up old recordings for this camera (keep only the latest)
                cleanup_old_recordings(safe_name)
            else:
                print(f"Error recording {camera_name}: {result.stderr}")
            
            # Wait a bit before starting next recording
            time.sleep(2)
            
        except subprocess.TimeoutExpired:
            print(f"Timeout recording {camera_name}, retrying...")
            time.sleep(5)
        except Exception as e:
            print(f"Exception in recording {camera_name}: {str(e)}")
            time.sleep(5)  # Wait 5 seconds before retrying

def cleanup_old_recordings(safe_camera_name):
    """Remove old recordings for a camera, keeping only the latest one"""
    try:
        recordings_dir = "recordings"
        # Find all files for this camera
        camera_files = []
        
        for filename in os.listdir(recordings_dir):
            if filename.startswith(safe_camera_name + "_") and filename.endswith(".mp4"):
                filepath = os.path.join(recordings_dir, filename)
                # Get file creation time
                creation_time = os.path.getctime(filepath)
                camera_files.append((filepath, creation_time))
        
        # Sort by creation time (newest first)
        camera_files.sort(key=lambda x: x[1], reverse=True)
        
        # Remove all but the newest file
        for filepath, _ in camera_files[1:]:
            try:
                os.remove(filepath)
                print(f"Removed old recording: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"Error removing file {filepath}: {str(e)}")
                
    except Exception as e:
        print(f"Error in cleanup for {safe_camera_name}: {str(e)}")

def get_latest_recording(camera_name):
    """Get the latest MP4 recording for a specific camera"""
    safe_name = sanitize_filename(camera_name)
    recordings_dir = "recordings"
    
    try:
        # Find all files for this camera
        pattern = os.path.join(recordings_dir, f"{safe_name}_*.mp4")
        camera_files = glob.glob(pattern)
        
        if not camera_files:
            return None
        
        # Get the latest file by modification time
        latest_file = max(camera_files, key=os.path.getmtime)
        
        # Check if file exists and is not empty
        if os.path.exists(latest_file) and os.path.getsize(latest_file) > 0:
            return latest_file
        
        return None
        
    except Exception as e:
        print(f"Error getting latest recording for {camera_name}: {str(e)}")
        return None

def get_available_cameras():
    """Get list of available cameras"""
    return list(cameras.keys())

def find_camera_by_location(camera_loc):
    """Find camera name by location (case-insensitive partial match)"""
    camera_loc_lower = camera_loc.lower()
    
    # First try exact match
    for camera_name in cameras.keys():
        if camera_name.lower() == camera_loc_lower:
            return camera_name
    
    # Then try partial match
    for camera_name in cameras.keys():
        if camera_loc_lower in camera_name.lower():
            return camera_name
    
    # Try to match without special characters
    safe_search = re.sub(r'[^\w\s]', '', camera_loc_lower)
    for camera_name in cameras.keys():
        safe_camera = re.sub(r'[^\w\s]', '', camera_name.lower())
        if safe_search in safe_camera:
            return camera_name
    
    return None

# MCP API endpoints
@mcp.tool()
def get_camera_recording(camera_loc: str) -> dict:
    """
    Get the latest MP4 recording for a camera by location name.
    
    Args:
        camera_loc: Camera location name (can be partial match, case-insensitive)
    
    Returns:
        Dictionary with camera info and file path, or error message
    """
    try:
        # Find the camera by location
        camera_name = find_camera_by_location(camera_loc)
        
        if not camera_name:
            available_cameras = get_available_cameras()
            return {
                "success": False,
                "error": f"Camera location '{camera_loc}' not found",
                "available_cameras": available_cameras
            }
        
        # Get the latest recording
        latest_file = get_latest_recording(camera_name)
        
        if not latest_file:
            return {
                "success": False,
                "error": f"No recording found for camera '{camera_name}'",
                "camera_name": camera_name
            }
        
        # Get file info
        file_size = os.path.getsize(latest_file)
        file_modified = datetime.fromtimestamp(os.path.getmtime(latest_file))
        
        return {
            "success": True,
            "camera_name": camera_name,
            "camera_location": camera_loc,
            "file_path": latest_file,
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "last_updated": file_modified.strftime('%Y-%m-%d %H:%M:%S'),
            "absolute_path": os.path.abspath(latest_file)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"An error occurred: {str(e)}"
        }

@mcp.tool()
def list_available_cameras() -> dict:
    """
    Get a list of all available camera locations.
    
    Returns:
        Dictionary with list of available cameras and their recording status
    """
    try:
        camera_status = {}
        
        for camera_name in cameras.keys():
            latest_file = get_latest_recording(camera_name)
            if latest_file:
                file_size = os.path.getsize(latest_file)
                file_modified = datetime.fromtimestamp(os.path.getmtime(latest_file))
                camera_status[camera_name] = {
                    "has_recording": True,
                    "file_path": latest_file,
                    "file_size_mb": round(file_size / (1024 * 1024), 2),
                    "last_updated": file_modified.strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                camera_status[camera_name] = {
                    "has_recording": False,
                    "file_path": None,
                    "file_size_mb": 0,
                    "last_updated": None
                }
        
        return {
            "success": True,
            "total_cameras": len(cameras),
            "cameras": camera_status
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"An error occurred: {str(e)}"
        }

@mcp.tool()
def get_recording_stats() -> dict:
    """
    Get overall statistics about the recording system.
    
    Returns:
        Dictionary with system statistics
    """
    try:
        recordings_dir = "recordings"
        total_files = 0
        total_size = 0
        active_cameras = 0
        
        if os.path.exists(recordings_dir):
            for camera_name in cameras.keys():
                latest_file = get_latest_recording(camera_name)
                if latest_file and os.path.exists(latest_file):
                    total_files += 1
                    total_size += os.path.getsize(latest_file)
                    active_cameras += 1
        
        return {
            "success": True,
            "total_cameras_configured": len(cameras),
            "active_cameras_with_recordings": active_cameras,
            "total_recording_files": total_files,
            "total_storage_used_mb": round(total_size / (1024 * 1024), 2),
            "recordings_directory": os.path.abspath(recordings_dir),
            "system_status": "Running" if recording_threads else "Stopped"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"An error occurred: {str(e)}"
        }

def start_all_recordings():
    """Start recording threads for all cameras"""
    threads = []
    print(f"Starting recordings for {len(cameras)} cameras...")
    
    for camera_name, m3u8_url in cameras.items():
        print(f"Starting recording thread for: {camera_name}")
        thread = threading.Thread(
            target=record_camera, 
            args=(camera_name, m3u8_url),
            daemon=False  # Changed to False so threads don't exit when main program ends
        )
        thread.start()
        threads.append(thread)
        time.sleep(1)  # Small delay between starting threads
    
    print(f"All {len(threads)} recording threads started!")
    return threads

def keep_alive():
    """Keep the main program running"""
    try:
        while True:
            time.sleep(60)  # Check every minute
            print(f"System running... Active recordings: {len(cameras)} cameras")
    except KeyboardInterrupt:
        print("\nShutting down recording system...")
        return

# Start recordings when the module is imported
recording_threads = start_all_recordings()

# If this script is run directly, keep it alive
if __name__ == "__main__":
    print("Camera recording system started. Press Ctrl+C to stop.")
    keep_alive()



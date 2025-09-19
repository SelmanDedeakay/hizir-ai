from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
import os
import threading
import time
import subprocess
from datetime import datetime
import re
import glob
from pathlib import Path
import uvicorn

# Create FastAPI app
app = FastAPI(
    title="Camera Recording Server",
    description="API for recording and accessing Istanbul camera feeds",
    version="1.0.0"
)

# Camera configurations
cameras = {
    "KAPALI ÇARŞI": "https://livestream.ibb.gov.tr/cam_turistik/b_kapalicarsi.stream/playlist.m3u8",
    "METROHAN": "https://livestream.ibb.gov.tr/cam_turistik/b_metrohan.stream/playlist.m3u8",
    "SARAÇHANE": "https://livestream.ibb.gov.tr/cam_turistik/b_sarachane.stream/playlist.m3u8",
    "SULTANAHMET 1": "https://livestream.ibb.gov.tr/cam_turistik/b_sultanahmet.stream/playlist.m3u8",
    "TAKSİM MEYDANI": "https://livestream.ibb.gov.tr/cam_turistik/b_taksim_meydan.stream/playlist.m3u8",
}

# Configuration constants
SEGMENT_DURATION = 10  # seconds per segment
MAX_SEGMENTS = 18  # 3 minutes worth of segments
MIN_VIDEO_SIZE = 500 * 1024  # 500KB minimum for valid video
DEFAULT_RECORDING_DURATION = 1  # minute

# Create directories
os.makedirs("recordings", exist_ok=True)
os.makedirs("ts_segments", exist_ok=True)

# Global variable to track recording threads
recording_threads = []

# Pydantic models
class CameraRecordingResponse(BaseModel):
    success: bool
    camera_name: Optional[str] = None
    camera_location: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_size_mb: Optional[float] = None
    last_updated: Optional[str] = None
    absolute_path: Optional[str] = None
    error: Optional[str] = None
    available_cameras: Optional[list] = None

class CameraStatus(BaseModel):
    has_recording: bool
    file_path: Optional[str]
    file_size_mb: float
    last_updated: Optional[str]

class CamerasListResponse(BaseModel):
    success: bool
    total_cameras: Optional[int] = None
    cameras: Optional[Dict[str, CameraStatus]] = None
    error: Optional[str] = None

class RecordingStatsResponse(BaseModel):
    success: bool
    total_cameras_configured: Optional[int] = None
    active_cameras_with_recordings: Optional[int] = None
    total_recording_files: Optional[int] = None
    total_storage_used_mb: Optional[float] = None
    recordings_directory: Optional[str] = None
    system_status: Optional[str] = None
    error: Optional[str] = None

# Utility functions
def sanitize_filename(name):
    """Convert camera name to a safe filename"""
    safe_name = re.sub(r'[^\w\s-]', '_', name)
    safe_name = re.sub(r'[\s_]+', '_', safe_name)
    return safe_name.strip('_')

def check_executable(executable_name):
    """Check if an executable (ffmpeg or ffprobe) is available"""
    paths = [
        executable_name,
        f'{executable_name}.exe',
        f'C:\\ffmpeg\\bin\\{executable_name}.exe',
        os.path.join(os.getcwd(), f'{executable_name}.exe'),
    ]
    
    for path in paths:
        try:
            result = subprocess.run([path, '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"Found {executable_name} at: {path}")
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    return None

def validate_video_file(filepath):
    """Validate that the video file is not corrupted using ffprobe"""
    try:
        ffprobe_path = check_executable('ffprobe')
        if not ffprobe_path:
            return os.path.exists(filepath) and os.path.getsize(filepath) > MIN_VIDEO_SIZE
        
        cmd = [
            ffprobe_path,
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=duration',
            '-of', 'csv=p=0',
            filepath
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                duration = float(result.stdout.strip())
                return duration >= 30.0  # Expect at least 30 seconds
            except ValueError:
                return False
        
        return False
        
    except Exception as e:
        print(f"Error validating video file {filepath}: {str(e)}")
        return False

def find_camera_by_location(camera_loc):
    """Find camera name by location (case-insensitive partial match)"""
    camera_loc_lower = camera_loc.lower()
    
    # Try exact match
    for camera_name in cameras.keys():
        if camera_name.lower() == camera_loc_lower:
            return camera_name
    
    # Try partial match
    for camera_name in cameras.keys():
        if camera_loc_lower in camera_name.lower():
            return camera_name
    
    # Try without special characters
    safe_search = re.sub(r'[^\w\s]', '', camera_loc_lower)
    for camera_name in cameras.keys():
        safe_camera = re.sub(r'[^\w\s]', '', camera_name.lower())
        if safe_search in safe_camera:
            return camera_name
    
    return None

def get_camera_or_404(camera_location: str):
    """Find camera or raise HTTPException"""
    camera_name = find_camera_by_location(camera_location)
    if not camera_name:
        raise HTTPException(
            status_code=404, 
            detail=f"Camera location '{camera_location}' not found. Available: {list(cameras.keys())}"
        )
    return camera_name

# Recording functions
def cleanup_old_segments(camera_ts_dir, max_segments):
    """Clean up old .ts segments, keeping only the most recent ones"""
    try:
        ts_files = []
        for filename in os.listdir(camera_ts_dir):
            if filename.endswith('.ts'):
                filepath = os.path.join(camera_ts_dir, filename)
                mtime = os.path.getmtime(filepath)
                ts_files.append((filepath, mtime))
        
        ts_files.sort(key=lambda x: x[1], reverse=True)
        
        for filepath, _ in ts_files[max_segments:]:
            try:
                os.remove(filepath)
                print(f"Removed old segment: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"Error removing segment {filepath}: {str(e)}")
                
    except Exception as e:
        print(f"Error in segment cleanup: {str(e)}")

def record_camera_segments(camera_name, m3u8_url):
    """Continuously capture .ts segments from the live stream"""
    safe_name = sanitize_filename(camera_name)
    ffmpeg_path = check_executable('ffmpeg')
    
    if not ffmpeg_path:
        print(f"FFmpeg not found for {camera_name}! Please install FFmpeg.")
        return
    
    camera_ts_dir = os.path.join("ts_segments", safe_name)
    os.makedirs(camera_ts_dir, exist_ok=True)
    
    while True:
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            segment_pattern = os.path.join(camera_ts_dir, f"{safe_name}_{timestamp}_%03d.ts")
            playlist_file = os.path.join(camera_ts_dir, f"{safe_name}_playlist.m3u8")
            
            print(f"Starting segment capture for {camera_name}")
            
            cmd = [
                ffmpeg_path, '-y',
                '-i', m3u8_url,
                '-c', 'copy',
                '-f', 'segment',
                '-segment_time', str(SEGMENT_DURATION),
                '-segment_list', playlist_file,
                '-segment_list_flags', 'live',
                '-segment_wrap', str(MAX_SEGMENTS),
                '-reset_timestamps', '1',
                '-loglevel', 'error',
                segment_pattern
            ]
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(180)  # Run for 3 minutes
            process.terminate()
            
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            
            cleanup_old_segments(camera_ts_dir, MAX_SEGMENTS)
            
        except Exception as e:
            print(f"Exception in segment capture for {camera_name}: {str(e)}")
            time.sleep(10)

def get_available_segments(camera_name, duration_minutes=1):
    """Get available .ts segments for a camera within the specified duration"""
    safe_name = sanitize_filename(camera_name)
    camera_ts_dir = os.path.join("ts_segments", safe_name)
    
    if not os.path.exists(camera_ts_dir):
        return []
    
    try:
        ts_files = []
        for filename in os.listdir(camera_ts_dir):
            if filename.endswith('.ts'):
                filepath = os.path.join(camera_ts_dir, filename)
                mtime = os.path.getmtime(filepath)
                ts_files.append((filepath, mtime))
        
        ts_files.sort(key=lambda x: x[1], reverse=True)
        
        required_segments = int((duration_minutes * 60) / SEGMENT_DURATION)
        recent_segments = [filepath for filepath, _ in ts_files[:required_segments]]
        recent_segments.sort()
        
        return recent_segments
        
    except Exception as e:
        print(f"Error getting segments for {camera_name}: {str(e)}")
        return []

def create_mp4_from_segments(camera_name, segments, duration_minutes=1):
    """Create an MP4 file from .ts segments"""
    if not segments:
        return None
    
    safe_name = sanitize_filename(camera_name)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"recordings/{safe_name}_{duration_minutes}min_{timestamp}.mp4"
    
    ffmpeg_path = check_executable('ffmpeg')
    if not ffmpeg_path:
        print(f"FFmpeg not found! Cannot create MP4.")
        return None
    
    try:
        valid_segments = [s for s in segments if os.path.exists(s) and os.path.getsize(s) > 0]
        
        if not valid_segments:
            print(f"No valid segments found for {camera_name}")
            return None
        
        filelist_path = f"recordings/{safe_name}_filelist_{timestamp}.txt"
        
        with open(filelist_path, 'w', encoding='utf-8-sig') as f:
            for segment in valid_segments:
                # Get path relative to the filelist.txt location (recordings/)
                rel_path = os.path.relpath(segment, start="recordings")
                # Normalize to forward slashes (ffmpeg prefers this)
                rel_path = rel_path.replace('\\', '/')
                f.write(f"file '{rel_path}'\n")
        
        print(f"Creating MP4 from {len(valid_segments)} segments for {camera_name}")
        
        cmd = [
            ffmpeg_path, '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', filelist_path,
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts',
            output_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        try:
            os.remove(filelist_path)
        except:
            pass
        
        if result.returncode == 0 and os.path.exists(output_file):
            print(f"Successfully created MP4: {output_file}")
            return output_file
        else:
            print(f"Error creating MP4: {result.stderr}")
            return None
            
    except Exception as e:
        print(f"Exception creating MP4: {str(e)}")
        return None

def cleanup_old_recordings(safe_camera_name, keep_count=3):
    """Remove old recordings for a camera, keeping the latest N files"""
    try:
        camera_files = []
        
        for filename in os.listdir("recordings"):
            if filename.startswith(safe_camera_name + "_") and filename.endswith(".mp4"):
                filepath = os.path.join("recordings", filename)
                creation_time = os.path.getctime(filepath)
                camera_files.append((filepath, creation_time))
        
        camera_files.sort(key=lambda x: x[1], reverse=True)
        
        for filepath, _ in camera_files[keep_count:]:
            try:
                os.remove(filepath)
                print(f"Removed old recording: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"Error removing file: {str(e)}")
                
    except Exception as e:
        print(f"Error in cleanup: {str(e)}")

def get_latest_recording(camera_name, duration_minutes=1):
    """Get or create the latest MP4 recording for a specific camera"""
    try:
        safe_name = sanitize_filename(camera_name)
        segments = get_available_segments(camera_name, duration_minutes)
        
        if not segments:
            print(f"No segments available for {camera_name}")
            return None
        
        mp4_file = create_mp4_from_segments(camera_name, segments, duration_minutes)
        
        if mp4_file:
            cleanup_old_recordings(safe_name, keep_count=2)
            return mp4_file
        
        return None
        
    except Exception as e:
        print(f"Error getting recording: {str(e)}")
        return None

def start_all_recordings():
    """Start recording threads for all cameras"""
    threads = []
    print(f"Starting segment capture for {len(cameras)} cameras...")
    
    for camera_name, m3u8_url in cameras.items():
        print(f"Starting thread for: {camera_name}")
        thread = threading.Thread(
            target=record_camera_segments, 
            args=(camera_name, m3u8_url),
            daemon=False
        )
        thread.start()
        threads.append(thread)
        time.sleep(1)
    
    print(f"All {len(threads)} threads started!")
    return threads

# API Endpoints
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Camera Recording Server",
        "version": "1.0.0",
        "endpoints": {
            "GET /cameras": "List all available cameras",
            "GET /camera/{camera_location}/recording": "Get 1-minute recording",
            "GET /camera/{camera_location}/recording/{duration}": "Get custom duration recording",
            "GET /camera/{camera_location}/download": "Download 1-minute recording",
            "GET /camera/{camera_location}/download/{duration}": "Download custom duration",
            "GET /camera/{camera_location}/status": "Get camera status",
            "GET /camera/{camera_location}/segments": "Get segments info",
            "GET /stats": "System statistics",
            "POST /start-recordings": "Start recording all cameras",
            "GET /health": "Health check"
        }
    }

@app.get("/cameras", response_model=CamerasListResponse)
async def list_cameras():
    """Get list of all cameras and their recording status"""
    try:
        camera_status = {}
        
        for camera_name in cameras.keys():
            latest_file = get_latest_recording(camera_name)
            if latest_file:
                file_size = os.path.getsize(latest_file)
                file_modified = datetime.fromtimestamp(os.path.getmtime(latest_file))
                camera_status[camera_name] = CameraStatus(
                    has_recording=True,
                    file_path=latest_file,
                    file_size_mb=round(file_size / (1024 * 1024), 2),
                    last_updated=file_modified.strftime('%Y-%m-%d %H:%M:%S')
                )
            else:
                camera_status[camera_name] = CameraStatus(
                    has_recording=False,
                    file_path=None,
                    file_size_mb=0,
                    last_updated=None
                )
        
        return CamerasListResponse(
            success=True,
            total_cameras=len(cameras),
            cameras=camera_status
        )
        
    except Exception as e:
        return CamerasListResponse(
            success=False,
            error=f"Error: {str(e)}"
        )

@app.get("/camera/{camera_location}/recording", response_model=CameraRecordingResponse)
async def get_camera_recording(camera_location: str):
    """Get 1-minute recording info for a camera"""
    return await get_camera_recording_with_duration(camera_location, DEFAULT_RECORDING_DURATION)

@app.get("/camera/{camera_location}/recording/{duration_minutes}", response_model=CameraRecordingResponse)
async def get_camera_recording_with_duration(camera_location: str, duration_minutes: int):
    """Get recording info with custom duration (1-10 minutes)"""
    try:
        if duration_minutes < 1 or duration_minutes > 10:
            return CameraRecordingResponse(
                success=False,
                error="Duration must be between 1 and 10 minutes"
            )
        
        camera_name = get_camera_or_404(camera_location)
        latest_file = get_latest_recording(camera_name, duration_minutes)
        
        if not latest_file:
            return CameraRecordingResponse(
                success=False,
                error=f"No recording could be created for {camera_name}",
                camera_name=camera_name
            )
        
        file_size = os.path.getsize(latest_file)
        file_modified = datetime.fromtimestamp(os.path.getmtime(latest_file))
        
        return CameraRecordingResponse(
            success=True,
            camera_name=camera_name,
            camera_location=camera_location,
            file_path=latest_file,
            file_size_bytes=file_size,
            file_size_mb=round(file_size / (1024 * 1024), 2),
            last_updated=file_modified.strftime('%Y-%m-%d %H:%M:%S'),
            absolute_path=os.path.abspath(latest_file)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        return CameraRecordingResponse(
            success=False,
            error=f"Error: {str(e)}"
        )

@app.get("/camera/{camera_location}/download")
async def download_camera_recording(camera_location: str):
    """Download 1-minute recording file"""
    return await download_camera_recording_with_duration(camera_location, DEFAULT_RECORDING_DURATION)

@app.get("/camera/{camera_location}/download/{duration_minutes}")
async def download_camera_recording_with_duration(camera_location: str, duration_minutes: int):
    """Download recording with custom duration"""
    try:
        if duration_minutes < 1 or duration_minutes > 10:
            raise HTTPException(status_code=400, detail="Duration must be between 1 and 10 minutes")
        
        camera_name = get_camera_or_404(camera_location)
        latest_file = get_latest_recording(camera_name, duration_minutes)
        
        if not latest_file or not os.path.exists(latest_file):
            raise HTTPException(status_code=404, detail=f"No recording available for {camera_name}")
        
        return FileResponse(
            latest_file,
            media_type='video/mp4',
            filename=os.path.basename(latest_file)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/camera/{camera_location}/status")
async def get_camera_status(camera_location: str):
    """Get detailed camera status including segments and processing state"""
    try:
        camera_name = get_camera_or_404(camera_location)
        safe_name = sanitize_filename(camera_name)
        camera_ts_dir = os.path.join("ts_segments", safe_name)
        
        # Get latest MP4 info
        latest_mp4_info = None
        pattern = os.path.join("recordings", f"{safe_name}_*.mp4")
        camera_files = glob.glob(pattern)
        
        if camera_files:
            camera_files.sort(key=os.path.getmtime, reverse=True)
            latest_file = camera_files[0]
            latest_mp4_info = {
                "path": latest_file,
                "size_mb": round(os.path.getsize(latest_file) / (1024 * 1024), 2),
                "age_seconds": time.time() - os.path.getmtime(latest_file)
            }
        
        # Get segments info
        segments_info = {
            "available": 0,
            "total_duration_seconds": 0,
            "newest_segment_age_seconds": None
        }
        
        if os.path.exists(camera_ts_dir):
            ts_files = []
            for filename in os.listdir(camera_ts_dir):
                if filename.endswith('.ts'):
                    filepath = os.path.join(camera_ts_dir, filename)
                    mtime = os.path.getmtime(filepath)
                    ts_files.append((filepath, mtime))
            
            segments_info["available"] = len(ts_files)
            segments_info["total_duration_seconds"] = len(ts_files) * SEGMENT_DURATION
            
            if ts_files:
                newest_segment_time = max(ts_files, key=lambda x: x[1])[1]
                segments_info["newest_segment_age_seconds"] = time.time() - newest_segment_time
        
        status = "No data available"
        if segments_info["available"] > 0:
            if segments_info["newest_segment_age_seconds"] < 60:
                status = "Active - receiving live segments"
            else:
                status = "Segments available but not receiving live data"
        
        return {
            "camera_name": camera_name,
            "camera_location": camera_location,
            "latest_mp4": latest_mp4_info,
            "segments": segments_info,
            "max_recording_duration_minutes": int(segments_info["total_duration_seconds"] / 60),
            "status": status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/camera/{camera_location}/segments")
async def get_camera_segments_info(camera_location: str):
    """Get information about available .ts segments"""
    try:
        camera_name = get_camera_or_404(camera_location)
        safe_name = sanitize_filename(camera_name)
        camera_ts_dir = os.path.join("ts_segments", safe_name)
        
        if not os.path.exists(camera_ts_dir):
            return {
                "camera_name": camera_name,
                "segments_available": 0,
                "total_duration_seconds": 0,
                "segments": []
            }
        
        ts_files = []
        for filename in os.listdir(camera_ts_dir):
            if filename.endswith('.ts'):
                filepath = os.path.join(camera_ts_dir, filename)
                file_size = os.path.getsize(filepath)
                file_mtime = os.path.getmtime(filepath)
                ts_files.append({
                    "filename": filename,
                    "size_mb": round(file_size / (1024 * 1024), 2),
                    "age_seconds": time.time() - file_mtime
                })
        
        ts_files.sort(key=lambda x: x['filename'])
        total_duration = len(ts_files) * SEGMENT_DURATION
        
        return {
            "camera_name": camera_name,
            "segments_available": len(ts_files),
            "total_duration_seconds": total_duration,
            "max_recording_minutes": int(total_duration / 60),
            "segment_duration_seconds": SEGMENT_DURATION,
            "segments": ts_files
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats", response_model=RecordingStatsResponse)
async def get_recording_stats():
    """Get overall system statistics"""
    try:
        total_files = 0
        total_size = 0
        active_cameras = 0
        
        for camera_name in cameras.keys():
            latest_file = get_latest_recording(camera_name)
            if latest_file and os.path.exists(latest_file):
                total_files += 1
                total_size += os.path.getsize(latest_file)
                active_cameras += 1
        
        return RecordingStatsResponse(
            success=True,
            total_cameras_configured=len(cameras),
            active_cameras_with_recordings=active_cameras,
            total_recording_files=total_files,
            total_storage_used_mb=round(total_size / (1024 * 1024), 2),
            recordings_directory=os.path.abspath("recordings"),
            system_status="Running" if recording_threads else "Stopped"
        )
        
    except Exception as e:
        return RecordingStatsResponse(
            success=False,
            error=str(e)
        )

@app.post("/start-recordings")
async def start_recordings():
    """Manually start recording threads"""
    global recording_threads
    
    try:
        if recording_threads:
            return {
                "message": "Recordings already running",
                "active_threads": len(recording_threads)
            }
        
        recording_threads = start_all_recordings()
        
        return {
            "message": f"Started {len(cameras)} recording threads",
            "cameras": list(cameras.keys()),
            "active_threads": len(recording_threads)
        }
        
    except Exception as e:
        return {"error": str(e)}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cameras_configured": len(cameras),
        "recordings_active": len(recording_threads) > 0
    }

@app.on_event("startup")
async def startup_event():
    """Start segment capture on server startup"""
    global recording_threads
    print("Starting Camera Recording Server...")
    recording_threads = start_all_recordings()
    print(f"Server started with {len(recording_threads)} capture threads")

if __name__ == "__main__":
    print("Starting FastAPI Camera Recording Server...")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
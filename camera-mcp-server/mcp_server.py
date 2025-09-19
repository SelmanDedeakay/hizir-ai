import asyncio
import datetime
import os
import subprocess
import sys
import logging
from typing import Literal
from mcp.server.fastmcp import FastMCP
from video_classifier import video_classifier

# -------- Logging Setup --------
logging.basicConfig(
    level=logging.DEBUG,  # Set to INFO in production
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Console output
        logging.FileHandler("earthquake_analyser.log", encoding="utf-8")  # File output
    ]
)
logger = logging.getLogger("earthquake-video-analyser")

# -------- Camera sources --------
CAMERA_STREAMS = {
    "kapali_carsi": "https://livestream.ibb.gov.tr/cam_turistik/b_kapalicarsi.stream/playlist.m3u8",
    "metrohan": "https://livestream.ibb.gov.tr/cam_turistik/b_metrohan.stream/playlist.m3u8",
    "sarachane": "https://livestream.ibb.gov.tr/cam_turistik/b_sarachane.stream/playlist.m3u8",
    "sultanahmet_1": "https://livestream.ibb.gov.tr/cam_turistik/b_sultanahmet.stream/playlist.m3u8",
    "taksim": "https://livestream.ibb.gov.tr/cam_turistik/b_taksim_meydan.stream/playlist.m3u8",
}

logger.info("Camera streams configured: %s", list(CAMERA_STREAMS.keys()))

mcp = FastMCP("earthquake-video-analyser")
logger.info("FastMCP server instance created with name: earthquake-video-analyser")

# Allowed values for the tool parameter (kept explicit so schema is clean)
LocationLiteral = Literal["kapali_carsi", "metrohan", "sarachane", "sultanahmet_1", "taksim"]

# -------- Helpers --------
async def _run_ffmpeg(cmd: list[str], timeout_sec: float) -> tuple[int, str]:
    """Run an ffmpeg command with a hard timeout. Returns (returncode, stderr_text)."""
    logger.info("FFmpeg command: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        logger.error("FFmpeg timed out after %.1fs, killing process.", timeout_sec)
        proc.kill()
        await proc.wait()
        return 124, f"FFmpeg timed out after {timeout_sec}s"
    rc = proc.returncode
    err = stderr.decode(errors="replace") if stderr else ""
    logger.debug("FFmpeg exited rc=%s, stderr(len)=%d", rc, len(err))
    return rc, err

def _check_file_nonempty(path: str) -> None:
    if not os.path.exists(path):
        raise RuntimeError(f"Video file not created: {path}")
    size = os.path.getsize(path)
    if size == 0:
        raise RuntimeError(f"Video file is empty: {path} (0 bytes)")

# -------- Video Capture (Remux-first + Fallbacks + Timeouts) --------
async def capture_video(location_key: str) -> str:
    """Capture ~10s of video from livestream and return saved file path."""
    logger.debug("capture_video called with location_key: %s", location_key)

    if location_key not in CAMERA_STREAMS:
        logger.error("Invalid location requested: %s", location_key)
        raise ValueError(f"Invalid location: {location_key}")

    url = CAMERA_STREAMS[location_key].strip()
    logger.debug("Resolved stream URL: %s", url)

    recordings_dir = "recordings"
    os.makedirs(recordings_dir, exist_ok=True)
    logger.debug("Ensured directory exists: %s", recordings_dir)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{location_key}_{timestamp}.mp4"
    filepath = os.path.join(recordings_dir, filename)
    logger.info("Planned video output path: %s", filepath)

    # Attempt 1: Remux only (fast, near-zero CPU)
    cmd1 = [
        "ffmpeg",
        "-hide_banner", "-nostdin", "-loglevel", "error",
        "-t", "10",              # apply duration to input read
        "-i", url,
        "-map", "0:v:0?",
        "-map", "0:a:0?",
        "-c", "copy",
        "-movflags", "+faststart",
        "-y", filepath,
    ]
    rc, err = await _run_ffmpeg(cmd1, timeout_sec=30)
    if rc == 0:
        _check_file_nonempty(filepath)
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        logger.info("Video captured successfully (remux): %s (%.2f MB)", filepath, size_mb)
        return filepath
    logger.warning("Remux attempt failed (rc=%s). stderr: %s", rc, err.strip()[:500])

    # Attempt 2: Copy video, encode audio only (common fix for ADTS->MP4)
    cmd2 = [
        "ffmpeg",
        "-hide_banner", "-nostdin", "-loglevel", "error",
        "-t", "10",
        "-i", url,
        "-map", "0:v:0?",
        "-map", "0:a:0?",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-y", filepath,
    ]
    rc, err = await _run_ffmpeg(cmd2, timeout_sec=45)
    if rc == 0:
        _check_file_nonempty(filepath)
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        logger.info("Video captured successfully (copy V, encode A): %s (%.2f MB)", filepath, size_mb)
        return filepath
    logger.warning("Copy-video/encode-audio attempt failed (rc=%s). stderr: %s", rc, err.strip()[:500])

    # Attempt 3: Full re-encode (CPU heavy but robust) with ultrafast preset
    cmd3 = [
        "ffmpeg",
        "-hide_banner", "-nostdin", "-loglevel", "error",
        "-t", "10",
        "-i", url,
        "-map", "0:v:0?",
        "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-y", filepath,
    ]
    rc, err = await _run_ffmpeg(cmd3, timeout_sec=120)
    if rc == 0:
        _check_file_nonempty(filepath)
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        logger.info("Video captured successfully (full encode): %s (%.2f MB)", filepath, size_mb)
        return filepath

    # If all attempts fail, raise with best error context
    logger.error("All ffmpeg attempts failed for %s. Last stderr: %s", location_key, err)
    raise RuntimeError(f"FFmpeg failed to capture video for {location_key}: {err}")

# -------- MCP Tool Definition --------
@mcp.tool()
async def analyse_video(location: LocationLiteral) -> str:
    """
    Analyse a ~10s video from a specified Istanbul camera for earthquake signs.
    """
    logger.info("=== TOOL INVOCATION: analyse_video ===")
    logger.info("Requested location: %s", location)

    try:
        logger.info("Starting video capture for location: %s", location)
        video_path = await capture_video(location)
        logger.info("Video capture completed: %s", video_path)

        logger.info("Starting video classification (in thread pool)...")
        result = await asyncio.to_thread(video_classifier.classify_video, video_path)
        logger.info("Classification completed with result: %s", result)

        response = f"Analysis result: {result}\nVideo saved to: {video_path}"
        logger.info("Returning tool response")
        return response

    except Exception as e:
        error_msg = f"Error during analysis: {str(e)}"
        logger.exception("Tool 'analyse_video' failed for location: %s", location)
        return error_msg

# -------- Main Execution --------
def main():
    """Main entry point to configure and run the server."""
    logger.info("=== APPLICATION STARTUP ===")
    print("Loading video classification model...")
    logger.info("Loading video classification model...")

    try:
        video_classifier.load_model()
        logger.info("Model loaded successfully.")
        print("Model loaded.")
    except Exception as e:
        logger.exception("Failed to load model")
        print("ERROR: Failed to load model:", e)
        sys.exit(1)

    print("Starting MCP server... Waiting for requests. Press Ctrl+C to stop.")
    logger.info("Starting FastMCP server...")

    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server interrupted by user (Ctrl+C)")
        print("\nServer stopped by user.")
    except Exception as e:
        logger.exception("Server crashed with unhandled exception")
        print("ERROR: Server crashed:", e)
    finally:
        logger.info("=== APPLICATION SHUTDOWN ===")
        print("Server has been stopped.")

if __name__ == "__main__":
    main()
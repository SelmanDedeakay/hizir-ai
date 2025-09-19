# camera_monitor.py - Optimized FastAPI Client

import os
import subprocess
from datetime import datetime
import logging
from typing import Dict, List, Optional, Tuple
import json
import requests

logger = logging.getLogger(__name__)

class CameraMonitor:
    def __init__(self, fastapi_base_url: str = "http://localhost:8000"):
        self.fastapi_base_url = fastapi_base_url.rstrip('/')
        self.recordings_dir = "recordings"
        os.makedirs(self.recordings_dir, exist_ok=True)
        
        # Cache settings
        self.cameras_cache = {}
        self.cache_timestamp = None
        self.cache_duration = 30  # seconds

    def _api_request(self, endpoint: str, method: str = "GET", timeout: int = 30) -> Optional[Dict]:
        """Generic API request handler"""
        try:
            url = f"{self.fastapi_base_url}/{endpoint}"
            if method == "GET":
                response = requests.get(url, timeout=timeout)
            elif method == "POST":
                response = requests.post(url, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code == 200:
                return response.json()
            
            logger.error(f"API request failed: {endpoint} - HTTP {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"API request error ({endpoint}): {e}")
            return None

    def _get_cameras_from_api(self) -> Dict[str, str]:
        """Fetch camera list from FastAPI server with caching"""
        # Check cache
        current_time = datetime.now().timestamp()
        if (self.cache_timestamp and 
            current_time - self.cache_timestamp < self.cache_duration and 
            self.cameras_cache):
            return self.cameras_cache
        
        # Fetch from API
        data = self._api_request("cameras")
        if data and data.get('success') and data.get('cameras'):
            cameras = {name: f"api://{name}" for name in data['cameras'].keys()}
            self.cameras_cache = cameras
            self.cache_timestamp = current_time
            return cameras
        
        return {}

    @property
    def cameras(self) -> Dict[str, str]:
        """Dynamic property that fetches cameras from API"""
        return self._get_cameras_from_api()

    def get_all_camera_streams(self) -> List[Tuple[str, str]]:
        """Get all camera streams as list of tuples"""
        return list(self.cameras.items())

    def get_camera_url(self, camera_name: str) -> Optional[str]:
        """Get URL for a specific camera"""
        return self.cameras.get(camera_name)

    def record_clip(self, name: str, duration: int = 1) -> Optional[str]:
        """Get recording from FastAPI server with specified duration (in minutes)"""
        try:
            # Validate and normalize duration
            duration_minutes = max(1, min(10, duration if duration <= 10 else duration // 60))
            
            logger.info(f"Requesting {duration_minutes} minute recording for {name}")
            
            # Request recording from API
            data = self._api_request(f"camera/{name}/recording/{duration_minutes}")
            
            if not data or not data.get('success'):
                error_msg = data.get('error', 'Unknown error') if data else 'No response'
                logger.error(f"Failed to get recording for {name}: {error_msg}")
                return None
            
            file_path = data.get('absolute_path') or data.get('file_path')
            if not file_path:
                logger.error(f"No file path in API response for {name}")
                return None
            
            # Try to find the file locally
            if os.path.exists(file_path):
                logger.info(f"Found recording at: {file_path}")
                return file_path
            
            # If not found locally, download it
            logger.info(f"File not found locally, downloading from API")
            return self.download_recording(name, duration_minutes)
            
        except Exception as e:
            logger.error(f"Error getting recording for {name}: {e}")
            return None

    def download_recording(self, name: str, duration_minutes: int = 1, save_path: Optional[str] = None) -> Optional[str]:
        """Download recording from FastAPI server"""
        try:
            duration_minutes = max(1, min(10, duration_minutes))
            
            response = requests.get(
                f"{self.fastapi_base_url}/camera/{name}/download/{duration_minutes}", 
                timeout=60
            )
            
            if response.status_code != 200:
                logger.error(f"Download failed for {name}: HTTP {response.status_code}")
                return None
            
            if save_path is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_name = name.replace(' ', '_').replace('İ', 'I').replace('ı', 'i')
                save_path = os.path.join(
                    self.recordings_dir, 
                    f"{safe_name}_{duration_minutes}min_{timestamp}.mp4"
                )
            
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Downloaded {duration_minutes}min recording to {save_path}")
            return save_path
            
        except Exception as e:
            logger.error(f"Download error for {name}: {e}")
            return None

    def get_camera_segments_info(self, name: str) -> Optional[Dict]:
        """Get segment information for a camera"""
        return self._api_request(f"camera/{name}/segments")

    def get_camera_detailed_status(self, name: str) -> Optional[Dict]:
        """Get detailed status for a camera"""
        return self._api_request(f"camera/{name}/status")

    def get_recording_stats(self) -> Dict:
        """Get recording statistics from API"""
        return self._api_request("stats") or {"success": False, "error": "No response"}

    def get_camera_grid_html(self, max_cameras: int = 6) -> str:
        """Generate HTML grid showing camera status and video previews"""
        cameras = self.cameras
        if not cameras:
            return "<p>Kamera bulunamadı.</p>"

        streams = list(cameras.items())[:max_cameras]
        
        html = f"""
        <style>
            {self._get_grid_css()}
        </style>
        <div class="camera-grid" id="camera-grid">
        """

        for idx, (name, _) in enumerate(streams):
            html += self._generate_camera_card(name, idx)

        html += f"""
        </div>
        <script>
            {self._get_grid_javascript()}
        </script>
        """

        return html

    def _get_grid_css(self) -> str:
        """Get CSS for camera grid"""
        return """
            .camera-grid {
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
                padding: 20px;
            }
            .camera-item {
                width: 300px;
                min-height: 400px;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                padding: 15px;
                background: white;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }
            .camera-item:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            }
            .camera-title {
                margin: 0 0 12px 0;
                color: #1a237e;
                font-size: 16px;
                font-weight: 600;
                text-align: center;
                padding: 8px 0;
                border-bottom: 2px solid #e3f2fd;
            }
            .video-preview {
                width: 100%;
                height: 200px;
                background: #000;
                border-radius: 8px;
                margin: 10px 0;
                position: relative;
                overflow: hidden;
            }
            .video-preview video {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }
            .video-placeholder {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 100%;
                height: 100%;
                background: linear-gradient(45deg, #f0f0f0, #e0e0e0);
                color: #666;
            }
            .camera-status {
                text-align: center;
                padding: 8px;
                font-size: 13px;
                font-weight: 500;
                margin-top: 8px;
                border-radius: 4px;
            }
            .status-available { background: #e8f5e8; color: #2e7d32; }
            .status-unavailable { background: #ffebee; color: #d32f2f; }
            .recording-info {
                background: #f5f5f5;
                padding: 8px;
                border-radius: 4px;
                margin-top: 8px;
                font-size: 12px;
            }
            .action-buttons {
                display: flex;
                gap: 8px;
                margin-top: 10px;
            }
            .btn {
                flex: 1;
                padding: 8px 12px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 500;
                transition: background 0.2s;
            }
            .btn-download {
                background: #2196F3;
                color: white;
            }
            .btn-download:hover {
                background: #1976d2;
            }
            .btn:disabled {
                background: #ccc;
                cursor: not-allowed;
            }
        """

    def _generate_camera_card(self, name: str, idx: int) -> str:
        """Generate HTML for a single camera card"""
        return f"""
        <div class="camera-item" data-camera="{name}">
            <h3 class="camera-title">{name}</h3>
            
            <div class="video-preview" id="video-preview-{idx}">
                <div class="video-placeholder" id="placeholder-{idx}">
                    📹 Video yükleniyor...
                </div>
            </div>
            
            <div id="status-{idx}" class="camera-status">Kontrol ediliyor...</div>
            <div id="info-{idx}" class="recording-info">Bilgi yükleniyor...</div>
            
            <div class="action-buttons">
                <button class="btn btn-download" onclick="downloadRecording('{name}', {idx}, 1)">📥 1dk</button>
                <button class="btn btn-download" onclick="downloadRecording('{name}', {idx}, 2)">📥 2dk</button>
                <button class="btn btn-download" onclick="downloadRecording('{name}', {idx}, 5)">📥 5dk</button>
            </div>
        </div>
        """

    def _get_grid_javascript(self) -> str:
        """Get JavaScript for camera grid functionality"""
        return """
        async function checkCameraStatus() {
            try {
                const response = await fetch('http://localhost:8000/cameras');
                const data = await response.json();
                
                if (data.success && data.cameras) {
                    let idx = 0;
                    for (const [cameraName, status] of Object.entries(data.cameras)) {
                        updateCameraDisplay(cameraName, status, idx);
                        idx++;
                    }
                }
            } catch (error) {
                console.error('Camera status check failed:', error);
            }
        }

        async function updateCameraDisplay(cameraName, status, idx) {
            const statusEl = document.getElementById('status-' + idx);
            const infoEl = document.getElementById('info-' + idx);
            
            // Update status
            if (status.has_recording) {
                statusEl.innerHTML = '🟢 Kayıt Mevcut';
                statusEl.className = 'camera-status status-available';
                infoEl.innerHTML = `Son: ${status.last_updated}<br>Boyut: ${status.file_size_mb} MB`;
            } else {
                statusEl.innerHTML = '🔴 Kayıt Yok';
                statusEl.className = 'camera-status status-unavailable';
                infoEl.innerHTML = 'Kayıt bulunmuyor';
            }
            
            // Load video preview
            const previewEl = document.getElementById('video-preview-' + idx);
            const videoUrl = `http://localhost:8000/camera/${encodeURIComponent(cameraName)}/download/1`;
            previewEl.innerHTML = `
                <video controls muted>
                    <source src="${videoUrl}" type="video/mp4">
                </video>
            `;
        }

        async function downloadRecording(cameraName, idx, duration) {
            const button = event.target;
            button.disabled = true;
            button.innerHTML = '⏳';
            
            try {
                const url = `http://localhost:8000/camera/${encodeURIComponent(cameraName)}/download/${duration}`;
                const response = await fetch(url);
                
                if (response.ok) {
                    const blob = await response.blob();
                    const downloadUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = downloadUrl;
                    a.download = `${cameraName.replace(/\\s+/g, '_')}_${duration}min.mp4`;
                    a.click();
                    window.URL.revokeObjectURL(downloadUrl);
                    button.innerHTML = '✅';
                } else {
                    button.innerHTML = '❌';
                }
            } catch (error) {
                button.innerHTML = '❌';
            }
            
            setTimeout(() => {
                button.innerHTML = `📥 ${duration}dk`;
                button.disabled = false;
            }, 2000);
        }

        checkCameraStatus();
        setInterval(checkCameraStatus, 30000);
        """

    def get_simple_camera_preview(self, camera_name: str) -> str:
        """Generate simple preview HTML for a single camera"""
        status_data = self.get_camera_detailed_status(camera_name)
        
        if not status_data:
            return f"""
            <div style="padding: 20px; border: 1px solid #f8d7da; border-radius: 8px; background: #f8d7da;">
                <h3 style="color: #721c24;">{camera_name} - Bağlantı Hatası</h3>
            </div>
            """
        
        status = status_data.get('status', 'Bilinmiyor')
        segments = status_data.get('segments', {})
        max_duration = status_data.get('max_recording_duration_minutes', 0)
        
        status_icon = "🟢" if "Active" in status else "🟡" if "available" in status else "🔴"
        
        return f"""
        <div style="padding: 20px; border: 1px solid #ddd; border-radius: 8px; background: #f9f9f9;">
            <h3 style="color: #1976d2;">{camera_name}</h3>
            <p><strong>Durum:</strong> {status_icon} {status}</p>
            <p><strong>Max Kayıt:</strong> {max_duration} dakika</p>
            <p><strong>Segmentler:</strong> {segments.get('available', 0)} adet</p>
            
            <div style="margin-top: 15px;">
                <button onclick="downloadVideo('{camera_name}', 1)" 
                        style="padding: 8px 16px; background: #2196F3; color: white; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px;">
                    📥 1 Dakika
                </button>
                <button onclick="downloadVideo('{camera_name}', 5)" 
                        style="padding: 8px 16px; background: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer;">
                    📥 5 Dakika
                </button>
            </div>
            
            <script>
            function downloadVideo(cameraName, duration) {{
                window.open(`http://localhost:8000/camera/${{encodeURIComponent(cameraName)}}/download/${{duration}}`, '_blank');
            }}
            </script>
        </div>
        """

# Global instance
camera_monitor = CameraMonitor()
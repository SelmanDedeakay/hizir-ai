import os
import subprocess
from datetime import datetime
import logging
from typing import Dict, List, Optional, Tuple
import tempfile

logger = logging.getLogger(__name__)

class CameraMonitor:
    def __init__(self):
        self.recordings_dir = "recordings"
        os.makedirs(self.recordings_dir, exist_ok=True)
        
        # Hardcoded camera list for faster access
        self.cameras = {
            "ANADOLU HİSARI": "https://livestream.ibb.gov.tr/cam_turistik/b_anadoluhisari.stream/playlist.m3u8",
            "BEYAZIT KULESİ 1": "https://livestream.ibb.gov.tr/cam_turistik/b_beyazitkule.stream/playlist.m3u8",
            "BEYAZIT KULESİ 2": "https://livestream.ibb.gov.tr/cam_turistik/b_beyazitkule2new.stream/playlist.m3u8",
            "BEYAZIT MEYDANI": "https://livestream.ibb.gov.tr/cam_turistik/b_beyazitmeydani.stream/playlist.m3u8",
            "BÜYÜK ÇAMLICA": "https://livestream.ibb.gov.tr/cam_turistik/b_buyukcamlıca.stream/playlist.m3u8",
            "DRAGOS": "https://livestream.ibb.gov.tr/cam_turistik/b_dragos.stream/playlist.m3u8",
            "EMİNÖNÜ": "https://livestream.ibb.gov.tr/cam_turistik/b_eminonu.stream/playlist.m3u8",
            "EMİRGAN": "https://livestream.ibb.gov.tr/cam_turistik/b_emirgan.stream/playlist.m3u8",
            "EYÜP SULTAN": "https://livestream.ibb.gov.tr/cam_turistik/b_eyupsultan.stream/playlist.m3u8",
            "HİDİV KASRI": "https://livestream.ibb.gov.tr/cam_turistik/b_hidivkasri.stream/playlist.m3u8",
            "KADIKÖY": "https://livestream.ibb.gov.tr/cam_turistik/b_kadikoy2.stream/playlist.m3u8",
            "KAPALI ÇARŞI": "https://livestream.ibb.gov.tr/cam_turistik/b_kapalicarsi.stream/playlist.m3u8",
            "KIZ KULESİ": "https://livestream.ibb.gov.tr/cam_turistik/new_Kızkulesi.stream/playlist.m3u8",
            "KÜÇÜKÇEKMECE": "https://livestream.ibb.gov.tr/cam_turistik/b_kucukcekmece.stream/playlist.m3u8",
            "METROHAN": "https://livestream.ibb.gov.tr/cam_turistik/b_metrohan.stream/playlist.m3u8",
            "ORTAKÖY": "https://livestream.ibb.gov.tr/cam_turistik/b_ortakoy.stream/playlist.m3u8",
            "PİERRE LOTTİ": "https://livestream.ibb.gov.tr/cam_turistik/b_pierreloti.stream/playlist.m3u8",
            "SALACAK": "https://livestream.ibb.gov.tr/cam_turistik/b_salacak.stream/playlist.m3u8",
            "SARAÇHANE": "https://livestream.ibb.gov.tr/cam_turistik/b_sarachane.stream/playlist.m3u8",
            "SEPETÇİLER KASRI": "https://livestream.ibb.gov.tr/cam_turistik/b_sepetcilerkasri.stream/playlist.m3u8",
            "SULTANAHMET 1": "https://livestream.ibb.gov.tr/cam_turistik/b_sultanahmet.stream/playlist.m3u8",
            "SULTANAHMET 2": "https://livestream.ibb.gov.tr/cam_turistik/b_sultanahmet2.stream/playlist.m3u8",
            "TAKSİM MEYDANI": "https://livestream.ibb.gov.tr/cam_turistik/b_taksim_meydan.stream/playlist.m3u8",
            "ULUS PARKI": "https://livestream.ibb.gov.tr/cam_turistik/b_ulus_parki.stream/playlist.m3u8",
            "ÜSKÜDAR": "https://livestream.ibb.gov.tr/cam_turistik/b_uskudar.stream/playlist.m3u8"
        }
    
    def get_all_camera_streams(self) -> List[Tuple[str, str]]:
        """Get all camera names with their m3u8 URLs (instant, no fetching needed)"""
        return list(self.cameras.items())
    
    def get_camera_url(self, camera_name: str) -> Optional[str]:
        """Get URL for a specific camera"""
        return self.cameras.get(camera_name)
    
    def capture_frame(self, m3u8_url: str, output_path: str) -> bool:
        """Capture a single frame from stream"""
        try:
            cmd = [
                'ffmpeg', '-y', '-i', m3u8_url,
                '-frames:v', '1', '-q:v', '2',
                output_path
            ]
            subprocess.run(cmd, capture_output=True, timeout=10, check=True)
            return True
        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            return False
    
    def capture_thumbnail(self, name: str, m3u8_url: str) -> Optional[str]:
        """Capture a thumbnail from the stream"""
        try:
            # Create temp file for thumbnail
            temp_dir = tempfile.gettempdir()
            thumbnail_path = os.path.join(temp_dir, f"thumb_{name.replace(' ', '_')}.jpg")
            
            cmd = [
                'ffmpeg', '-y', '-i', m3u8_url,
                '-frames:v', '1', '-q:v', '2',
                '-vf', 'scale=320:180',  # Smaller thumbnail
                thumbnail_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode == 0 and os.path.exists(thumbnail_path):
                # Read and encode as base64
                import base64
                with open(thumbnail_path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode()
                os.remove(thumbnail_path)  # Clean up
                return f"data:image/jpeg;base64,{img_data}"
            return None
        except Exception as e:
            logger.error(f"Error capturing thumbnail for {name}: {e}")
            return None
    
    def record_clip(self, name: str, m3u8_url: str, duration: int = 30) -> Optional[str]:
        """Record a clip from stream for analysis"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.recordings_dir, f"{name.replace(' ', '_')}_{timestamp}.mp4")
            
            cmd = [
                'ffmpeg', '-y', '-i', m3u8_url,
                '-t', str(duration),
                '-c:v', 'libx264',  # Ensure MP4 compatibility
                '-preset', 'fast',
                '-movflags', '+faststart',
                filename
            ]
            
            logger.info(f"Recording {duration}s clip from {name}")
            subprocess.run(cmd, capture_output=True, timeout=duration+10, check=True)
            return filename
        except Exception as e:
            logger.error(f"Error recording clip from {name}: {e}")
            return None
    
    def get_camera_grid_html(self, max_cameras: int = 6) -> str:
        """Generate HTML grid with camera thumbnails and HLS.js player"""
        streams = list(self.cameras.items())[:max_cameras]
        
        if not streams:
            return "<p>Kamera bulunamadı.</p>"
        
        html = """
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <style>
            .camera-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 15px;
                padding: 10px;
            }
            .camera-item {
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 10px;
                background: #f9f9f9;
                position: relative;
            }
            .camera-title {
                margin: 0 0 10px 0;
                color: #333;
                font-size: 14px;
                font-weight: bold;
                text-align: center;
            }
            .camera-video {
                width: 100%;
                height: 180px;
                background: #000;
                border-radius: 4px;
                cursor: pointer;
            }
            .camera-status {
                text-align: center;
                padding: 5px;
                font-size: 12px;
                color: #666;
            }
            .play-button {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 60px;
                height: 60px;
                background: rgba(255,255,255,0.9);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                transition: all 0.3s;
            }
            .play-button:hover {
                background: rgba(255,255,255,1);
                transform: translate(-50%, -50%) scale(1.1);
            }
            .play-button::after {
                content: '▶';
                font-size: 24px;
                color: #333;
                margin-left: 4px;
            }
            .loading {
                color: #ff9800;
            }
            .error {
                color: #f44336;
            }
            .playing {
                color: #4caf50;
            }
        </style>
        <div class="camera-grid">
        """
        
        for idx, (name, m3u8_url) in enumerate(streams):
            video_id = f"camera-video-{idx}"
            html += f"""
            <div class="camera-item">
                <h4 class="camera-title">{name}</h4>
                <div style="position: relative;">
                    <video id="{video_id}" class="camera-video" muted controls></video>
                    <div id="play-{video_id}" class="play-button" onclick="playCamera('{video_id}', '{m3u8_url}')"></div>
                </div>
                <div id="status-{video_id}" class="camera-status">Oynatmak için tıklayın</div>
            </div>
            """
        
        html += """
        </div>
        <script>
        function playCamera(videoId, url) {
            var video = document.getElementById(videoId);
            var playBtn = document.getElementById('play-' + videoId);
            var status = document.getElementById('status-' + videoId);
            
            if (Hls.isSupported()) {
                status.innerHTML = '<span class="loading">Yükleniyor...</span>';
                playBtn.style.display = 'none';
                
                var hls = new Hls({
                    debug: false,
                    enableWorker: true,
                    lowLatencyMode: true,
                    backBufferLength: 90
                });
                
                hls.loadSource(url);
                hls.attachMedia(video);
                
                hls.on(Hls.Events.MANIFEST_PARSED, function() {
                    video.play().then(function() {
                        status.innerHTML = '<span class="playing">● Canlı Yayın</span>';
                    }).catch(function(error) {
                        console.error('Playback error:', error);
                        status.innerHTML = '<span class="error">Oynatma hatası</span>';
                        playBtn.style.display = 'flex';
                    });
                });
                
                hls.on(Hls.Events.ERROR, function(event, data) {
                    console.error('HLS error:', data);
                    if (data.fatal) {
                        status.innerHTML = '<span class="error">Bağlantı hatası</span>';
                        playBtn.style.display = 'flex';
                        hls.destroy();
                    }
                });
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                // For Safari
                video.src = url;
                playBtn.style.display = 'none';
                video.play().then(function() {
                    status.innerHTML = '<span class="playing">● Canlı Yayın</span>';
                }).catch(function(error) {
                    status.innerHTML = '<span class="error">Oynatma hatası</span>';
                    playBtn.style.display = 'flex';
                });
            } else {
                status.innerHTML = '<span class="error">Tarayıcı desteklenmiyor</span>';
            }
        }
        </script>
        """
        
        return html
    
    def get_simple_camera_preview(self, camera_name: str) -> str:
        """Get a simple preview for a single camera with HLS.js"""
        url = self.cameras.get(camera_name)
        if not url:
            return "<p>Kamera bulunamadı</p>"
        
        return f"""
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <div style="max-width: 640px; margin: 0 auto;">
            <h3 style="text-align: center; margin-bottom: 10px;">{camera_name}</h3>
            <video id="preview-video" controls muted style="width: 100%; height: auto; background: #000;"></video>
            <div id="preview-status" style="text-align: center; padding: 10px; color: #666;">Yükleniyor...</div>
        </div>
        <script>
        (function() {{
            var video = document.getElementById('preview-video');
            var status = document.getElementById('preview-status');
            
            if (Hls.isSupported()) {{
                var hls = new Hls({{
                    debug: false,
                    enableWorker: true,
                    lowLatencyMode: true
                }});
                
                hls.loadSource('{url}');
                hls.attachMedia(video);
                
                hls.on(Hls.Events.MANIFEST_PARSED, function() {{
                    video.play().then(function() {{
                        status.innerHTML = '<span style="color: #4caf50;">● Canlı Yayın</span>';
                    }}).catch(function(error) {{
                        status.innerHTML = '<span style="color: #f44336;">Oynatma hatası - Manuel olarak başlatın</span>';
                    }});
                }});
                
                hls.on(Hls.Events.ERROR, function(event, data) {{
                    if (data.fatal) {{
                        status.innerHTML = '<span style="color: #f44336;">Bağlantı hatası</span>';
                        hls.destroy();
                    }}
                }});
            }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
                video.src = '{url}';
                video.play().then(function() {{
                    status.innerHTML = '<span style="color: #4caf50;">● Canlı Yayın</span>';
                }}).catch(function() {{
                    status.innerHTML = '<span style="color: #ff9800;">Manuel olarak başlatın</span>';
                }});
            }} else {{
                status.innerHTML = '<span style="color: #f44336;">Tarayıcı HLS desteklemiyor</span>';
            }}
        }})();
        </script>
        """

# Global instance
camera_monitor = CameraMonitor()
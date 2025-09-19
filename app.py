import gradio as gr
from earthquake_monitor import earthquake_monitor
from video_classifier import video_classifier
import os
import pandas as pd
import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Load Models at Startup ---
print("Loading AI model...")
try:
    video_classifier.load_model()
    print("AI model loaded.")
except Exception as e:
    print(f"Failed to load AI model: {e}")

# --- Custom CSS for Styling ---
custom_css = """
#refresh-button {
    height: 50px;
    font-size: 16px;
}
#status-text {
    font-size: 18px;
    font-weight: bold;
    color: #2E7D32;
}
#last-update {
    font-style: italic;
    color: #757575;
    text-align: right;
    margin-top: 10px;
}
table.dataframe {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    overflow: hidden;
}
table.dataframe thead {
    background-color: #f5f5f5;
}
.gradio-html div {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    overflow: hidden;
}
iframe {
    width: 100%;
    height: 600px;
}
.gradio-container {
    padding: 20px;
}
.camera-grid {
    margin: 20px 0;
}
"""

# --- Helper Functions for Gradio ---

def refresh_earthquake_data():
    """Fetches new earthquake data and returns DataFrame and Map HTML"""
    try:
        earthquakes = earthquake_monitor.get_recent_earthquakes()
        df = earthquake_monitor.get_earthquake_dataframe()
        map_html = earthquake_monitor.get_folium_map_html()
        status = earthquake_monitor.get_monitoring_status()
        last_update_text = f"Son güncelleme: {status['last_update']}"
        return df, map_html, last_update_text
    except Exception as e:
        import pandas as pd
        error_df = pd.DataFrame({"Hata": ["Veri çekilemedi"]})
        error_map_html = "<div style='padding: 20px; color: red;'><h3>Harita yüklenemedi.</h3><p>{}</p></div>".format(str(e))
        return error_df, error_map_html, f"Hata: {str(e)}"

def classify_video_gradio(video_file_path_or_obj):
    """Handles video classification for Gradio."""
    if video_file_path_or_obj is None:
        return "Lütfen bir video dosyası yükleyin."
    
    try:
        if isinstance(video_file_path_or_obj, str):
            temp_video_path = video_file_path_or_obj
        else:
            temp_video_path = getattr(video_file_path_or_obj, 'name', None)
            if temp_video_path is None:
                 return "Yüklenen video dosyasının yolu alınamadı."

        print(f"Processing video at: {temp_video_path}")
        result = video_classifier.classify_video(temp_video_path)
        return result
    except Exception as e:
        return f"Video işlenirken hata oluştu: {e}"
# --- Gradio Interface Definition ---

with gr.Blocks(
    title="Hizir AI - Canlı Deprem & Video Analizi",
    theme=gr.themes.Soft(primary_hue="blue", secondary_hue="cyan")
) as demo:
    
    # --- Inject Custom CSS ---
    gr.HTML(f"<style>{custom_css}</style>", visible=False)
    
    gr.Markdown("# 🌍 Hizir AI - Canlı Deprem & Video Analizi")
    
    with gr.Tab("Canlı Deprem Takibi"):
        gr.Markdown("## Son Depremler ve Harita")
        
        with gr.Row():
            with gr.Column(scale=1):
                refresh_btn = gr.Button("🔄 Verileri Yenile", elem_id="refresh-button")
            
            with gr.Column(scale=3):
                status_md = gr.Markdown("Veri çekiliyor...", elem_id="status-text")
        
        with gr.Row():
            with gr.Column(scale=1):
                earthquake_df = gr.DataFrame(label="Deprem Verileri")
            
            with gr.Column(scale=2):
                earthquake_map = gr.HTML(label="Deprem Haritası")
        
        last_update_md = gr.Markdown("", elem_id="last-update")
        
        demo.load(refresh_earthquake_data, None, [earthquake_df, earthquake_map, last_update_md])
        
        refresh_btn.click(
            fn=refresh_earthquake_data,
            inputs=None,
            outputs=[earthquake_df, earthquake_map, last_update_md]
        )
        
    with gr.Tab("Video Deprem Analizi"):
        gr.Markdown("## 🎥 Canlı Kamera Kısa Tespiti – SmolVLM-500M")
        gr.Markdown(
            "**Kullanım:** Aşağıdan bir mekan seçin, 10 saniyelik canlı kesit alınıp "
            "deprem belirtisi var mı diye incelenecektir."
        )

        CAMERA_STREAMS = {
            "kapali_carsi": "https://livestream.ibb.gov.tr/cam_turistik/b_kapalicarsi.stream/playlist.m3u8",
            "metrohan": "https://livestream.ibb.gov.tr/cam_turistik/b_metrohan.stream/playlist.m3u8",
            "sarachane": "https://livestream.ibb.gov.tr/cam_turistik/b_sarachane.stream/playlist.m3u8",
            "sultanahmet_1": "https://livestream.ibb.gov.tr/cam_turistik/b_sultanahmet.stream/playlist.m3u8",
            "taksim": "https://livestream.ibb.gov.tr/cam_turistik/b_taksim_meydan.stream/playlist.m3u8",
        }

        with gr.Row():
            with gr.Column():
                location = gr.Dropdown(
                    label="Mekan seçin",
                    choices=list(CAMERA_STREAMS.keys()),
                    value="taksim",
                )
                run_btn = gr.Button("▶️ 10 sn çek ve analiz et", variant="primary")

            with gr.Column():
                result_tb = gr.Textbox(
                    label="🧠 Model cevabı",
                    interactive=False,
                    lines=4,
                )
        
        with gr.Row():
            captured_video = gr.Video(
                label="📹 Yakalanan 10 saniyelik video",
                interactive=False,
                visible=False
            )

        def analyse_live(location_key: str) -> tuple[str, str]:
            """Grab 10-s fragment to tmp file → classify → return result and video path."""
            if not video_classifier.is_loaded:
                return "Model yüklenmemiş, lütfen sunucu yöneticisine başvurun.", None

            m3u8 = CAMERA_STREAMS.get(location_key)
            if not m3u8:
                return "Geçersiz mekan seçildi.", None

            import tempfile, subprocess, os
            import shutil

            # Location display names (using ASCII-safe characters)
            location_names = {
                "kapali_carsi": "KAPALI CARSI",
                "metrohan": "METROHAN", 
                "sarachane": "SARACHANE",
                "sultanahmet_1": "SULTANAHMET",
                "taksim": "TAKSIM MEYDANI"
            }

            tmp_path = None
            permanent_path = None
            try:
                # Create temporary file with .mp4 extension
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                    tmp_path = tmp.name

                # Get current datetime for overlay (using dots instead of colons)
                current_time = datetime.datetime.now().strftime("%d.%m.%Y %H.%M")
                location_display = location_names.get(location_key, location_key.upper())
                
                # Create text overlay with proper escaping - avoid colons in text
                line1 = location_display
                line2 = current_time
                line3 = "HIZIR AI - DEPREM ANALIZI"
                
                # Run FFmpeg with text overlay using multiple drawtext filters
                cmd = [
                    "ffmpeg",
                    "-v", "error",          # only print real errors
                    "-i", m3u8,
                    "-t", "10",             # capture 10 seconds
                    "-vf", f"drawtext=text='{line1}':fontcolor=white:fontsize=24:box=1:boxcolor=black@0.8:boxborderw=5:x=10:y=10,drawtext=text='{line2}':fontcolor=white:fontsize=20:box=1:boxcolor=black@0.8:boxborderw=5:x=10:y=40,drawtext=text='{line3}':fontcolor=white:fontsize=18:box=1:boxcolor=black@0.8:boxborderw=5:x=10:y=70",
                    "-c:a", "copy",         # copy audio without re-encoding
                    "-y",                   # overwrite output file if exists
                    tmp_path
                ]
                
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                if proc.returncode != 0:
                    stderr_text = proc.stderr if proc.stderr else "Unknown FFmpeg error"
                    return f"FFmpeg hatası:\n{stderr_text}", None

                # Verify the file was created and has content
                if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                    return "Video dosyası oluşturulamadı veya boş.", None

                # Copy to recordings directory with timestamp for permanent storage
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                recordings_dir = "recordings"
                os.makedirs(recordings_dir, exist_ok=True)
                permanent_path = os.path.join(recordings_dir, f"{location_key}_analysis_{timestamp}.mp4")
                shutil.copy2(tmp_path, permanent_path)

                # Classify the video
                answer = video_classifier.classify_video(tmp_path)
                return answer, permanent_path

            except Exception as exc:
                return f"Hata oluştu: {exc}", None
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

        def handle_analysis(location_key: str):
            """Handle the analysis and return results for UI update."""
            result, video_path = analyse_live(location_key)
            if video_path:
                return result, gr.Video(value=video_path, visible=True)
            else:
                return result, gr.Video(visible=False)

        run_btn.click(
            fn=handle_analysis, 
            inputs=location, 
            outputs=[result_tb, captured_video]
        )
    
        
       

# --- Launch the App ---
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
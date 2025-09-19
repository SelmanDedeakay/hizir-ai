import gradio as gr
from earthquake_monitor import earthquake_monitor
from video_classifier import video_classifier
from camera_monitor import camera_monitor
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

# --- Camera Monitoring Functions (OPTIMIZED) ---

def get_camera_choices():
    """Get available camera choices from API"""
    try:
        streams = camera_monitor.get_all_camera_streams()
        return [name for name, _ in streams] if streams else []
    except Exception as e:
        logger.error(f"Error getting cameras: {e}")
        return []

def load_camera_streams():
    """Load camera streams and generate display"""
    try:
        stats = camera_monitor.get_recording_stats()
        if not stats.get('success'):
            return pd.DataFrame({"Durum": ["FastAPI sunucusu yanıt vermiyor"]}), "Sunucu bağlantısı yok"
        
        streams = camera_monitor.get_all_camera_streams()
        if not streams:
            return pd.DataFrame({"Durum": ["Kamera bulunamadı"]}), "Kamera yok"
        
        display_df = pd.DataFrame({"Kamera Adı": [name for name, _ in streams]})
        html_grid = camera_monitor.get_camera_grid_html(max_cameras=12)
        
        return display_df, html_grid
    except Exception as e:
        return pd.DataFrame({"Hata": [str(e)]}), f"<p>Hata: {e}</p>"

def analyze_camera_stream(camera_name, duration_minutes):
    """Analyze camera recording - optimized version"""
    if not camera_name:
        return "Lütfen bir kamera seçin.", "", ""
    
    try:
        duration_minutes = max(1, min(10, int(duration_minutes)))
        
        logger.info(f"Requesting {duration_minutes}min recording for {camera_name}")
        video_path = camera_monitor.record_clip(camera_name, duration=duration_minutes)
        
        if not video_path or not os.path.exists(video_path):
            segments_info = camera_monitor.get_camera_segments_info(camera_name)
            if segments_info:
                return f"Kayıt alınamadı. Mevcut: {segments_info.get('segments_available', 0)} segment", "", ""
            return f"Kayıt alınamadı: {camera_name}", "", ""
        
        # Analyze video
        file_size_mb = round(os.path.getsize(video_path) / (1024 * 1024), 2)
        analysis_result = video_classifier.classify_video(video_path)
        
        result_msg = f"""
**✅ Analiz Tamamlandı**
- **Kamera:** {camera_name}
- **Süre:** {duration_minutes} dakika
- **Boyut:** {file_size_mb} MB
- **Sonuç:** {analysis_result}
- **Tarih:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        download_html = f"""
        <div style="margin-top: 15px;">
            <button onclick="window.open('http://localhost:8000/camera/{camera_name}/download/{duration_minutes}', '_blank')" 
                    style="padding: 10px 20px; background: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer;">
                📥 Videoyu İndir ({duration_minutes} dakika)
            </button>
        </div>
        """
        
        return result_msg, video_path, download_html
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return f"Analiz hatası: {e}", "", ""

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
        gr.Markdown("## Video ile Deprem Tespiti")
        gr.Markdown("""
        Bu bölümde, bir video yükleyerek videoda deprem belirtileri olup olmadığını analiz edebilirsiniz.
        AI modeli, videoda sallanan binalar, yıkılmış alanlar gibi belirtiler arayacaktır.
        **En iyi sonuçlar için MP4 formatında, 10-30 saniyelik videolar önerilir.**
        """)
        
        with gr.Row():
            with gr.Column():
                video_input = gr.Video(label="Videoyu Yükleyin")
                classify_btn = gr.Button("Analiz Et", variant="primary")
            
            with gr.Column():
                result_text = gr.Textbox(label="Analiz Sonucu", interactive=False, lines=5)

        classify_btn.click(
            fn=classify_video_gradio,
            inputs=video_input,
            outputs=result_text
        )
    
    with gr.Tab("📹 Canlı Kamera İzleme (FastAPI)"):
        gr.Markdown("## İstanbul Canlı Kamera Kayıtları ve Deprem Analizi")
        gr.Markdown("""
        İstanbul'daki farklı noktalardan FastAPI sunucusu tarafından kaydedilen 
        video dosyalarını analiz edebilirsiniz. **FastAPI sunucusu otomatik olarak başlatılmıştır.**
        """)
        
        # System status section
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### ℹ️ Sunucu Bilgileri")
                gr.HTML("""
                <div style="padding: 15px; background: #e3f2fd; border-radius: 8px; margin: 10px 0;">
                    <p><strong>FastAPI Sunucusu:</strong> localhost:8000</p>
                    <p><strong>Durum:</strong> Otomatik başlatıldı</p>
                    <p><strong>Segment Süresi:</strong> 10 saniye</p>
                    <p><strong>Maksimum Kayıt:</strong> 10 dakika</p>
                </div>
                """)
                
            with gr.Column(scale=1):
                gr.Markdown("### 📊 Sistem Durumu")
                health_btn = gr.Button("🛠️ Sistem Kontrolü")
                health_output = gr.JSON(label="Sistem İstatistikleri")

        health_btn.click(
            fn=camera_monitor.get_recording_stats,
            inputs=None,
            outputs=health_output
        )
        
        # Main camera grid
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📍 Mevcut Kameralar")
                camera_list_df = gr.DataFrame(
                    label="FastAPI Sunucusu Kameraları",
                    interactive=False,
                    wrap=True,
                )
                
            with gr.Column(scale=2):
                gr.Markdown("### 🎥 Kayıt Durumları")
                camera_preview_html = gr.HTML(
                    label="Kamera Kayıt Durumları",
                    elem_classes=["camera-grid"]
                )
        
        gr.Markdown("---")
        gr.Markdown("### 🔍 Deprem Analizi için Kamera Seçin")
        gr.Markdown("**Not:** Analiz, FastAPI sunucusundaki en son kayıttan yapılacaktır.")
        
        with gr.Row():
            with gr.Column():
                refresh_cameras_btn = gr.Button("🔄 Kamera Listesini Yenile", variant="secondary")
                camera_selector = gr.Dropdown(
                    label="Kamera Seçin",
                    choices=get_camera_choices(),
                    value=None,
                    interactive=True
                )
                
                selected_camera_preview = gr.HTML(label="Seçili Kamera Bilgileri")
                
                with gr.Row():
                    duration_selector = gr.Dropdown(
                        label="Kayıt Süresi (dakika)",
                        choices=[1, 2, 5, 10],
                        value=2,
                        interactive=True
                    )
                    analyze_btn = gr.Button("🎯 Seçili Sürede Analiz Et", variant="primary")
                
            with gr.Column():
                analysis_result = gr.Textbox(
                    label="Analiz Sonucu",
                    lines=8,
                    interactive=False
                )
                recorded_video = gr.Video(
                    label="Analiz Edilen Video",
                    interactive=False
                )
                download_options = gr.HTML(
                    label="İndirme Seçenekleri",
                    value=""
                )
        
        # Event handlers
        def load_cameras_on_startup():
            try:
                df, html = load_camera_streams()
                return df, html
            except Exception as e:
                return pd.DataFrame({"Hata": [str(e)]}), f"<p>Hata: {str(e)}</p>"

        demo.load(
            fn=load_cameras_on_startup,
            inputs=None,
            outputs=[camera_list_df, camera_preview_html]
        )
        
        def refresh_camera_choices():
            return gr.Dropdown(choices=get_camera_choices())

        refresh_cameras_btn.click(
            fn=refresh_camera_choices,
            inputs=None,
            outputs=camera_selector
        )
        
        camera_selector.change(
            fn=camera_monitor.get_simple_camera_preview,
            inputs=camera_selector,
            outputs=selected_camera_preview
        )
        
        analyze_btn.click(
            fn=analyze_camera_stream,
            inputs=[camera_selector, duration_selector],
            outputs=[analysis_result, recorded_video, download_options]
        )

# --- Launch the App ---
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
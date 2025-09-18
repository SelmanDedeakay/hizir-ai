import gradio as gr
from earthquake_monitor import earthquake_monitor
from video_classifier import video_classifier
from camera_monitor import camera_monitor  # Add this import
import os
import pandas as pd
import datetime
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

# --- Camera Monitoring Functions ---

def load_camera_streams():
    """Load available camera streams - now instant!"""
    try:
        streams = camera_monitor.get_all_camera_streams()
        if not streams:
            return pd.DataFrame({"Durum": ["Kamera bulunamadı"]}), "Kameralar yüklenemedi."
        
        # Create DataFrame for display
        df = pd.DataFrame(streams, columns=["Kamera Adı", "Stream URL"])
        # Only show camera names in the table for cleaner display
        display_df = pd.DataFrame({"Kamera Adı": [name for name, _ in streams]})
        
        # Generate HTML grid with video players
        html_grid = camera_monitor.get_camera_grid_html(max_cameras=6)
        
        return display_df, html_grid
    except Exception as e:
        return pd.DataFrame({"Hata": [str(e)]}), f"<p>Hata: {str(e)}</p>"

def preview_single_camera(camera_name):
    """Show preview for a single selected camera"""
    if not camera_name:
        return "<p>Lütfen bir kamera seçin</p>"
    
    return camera_monitor.get_simple_camera_preview(camera_name)

def analyze_camera_stream(camera_name, duration):
    """Record and analyze a clip from selected camera"""
    if not camera_name:
        return "Lütfen bir kamera seçin.", ""
    
    try:
        # Get stream URL for selected camera
        m3u8_url = camera_monitor.get_camera_url(camera_name)
        
        if not m3u8_url:
            return f"Kamera bulunamadı: {camera_name}", ""
        
        # Record clip with specified duration
        status_msg = f"{camera_name} kamerasından {duration} saniyelik kayıt alınıyor..."
        print(status_msg)
        
        video_path = camera_monitor.record_clip(camera_name, m3u8_url, duration=duration)
        
        if not video_path:
            return f"Kayıt alınamadı: {camera_name}", ""
        
        # Analyze the recorded clip
        print(f"Analyzing video: {video_path}")
        analysis_result = video_classifier.classify_video(video_path)
        
        # Create result message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_msg = f"""
**Analiz Tamamlandı**
- **Kamera:** {camera_name}
- **Tarih/Saat:** {timestamp}
- **Kayıt Süresi:** {duration} saniye
- **Deprem Belirtisi:** {analysis_result}
- **Dosya:** {os.path.basename(video_path)}
        """
        
        return result_msg, video_path
        
    except Exception as e:
        return f"Analiz hatası: {str(e)}", ""

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
    
    with gr.Tab("📹 Canlı Kamera İzleme"):
        gr.Markdown("## İstanbul Canlı Kamera Yayınları ve Deprem Analizi")
        gr.Markdown("""
        İstanbul'daki 25 farklı noktadan canlı kamera yayınlarını izleyebilir ve 
        seçtiğiniz kameradan kayıt alarak deprem analizi yapabilirsiniz.
        """)
        
        # Main camera grid
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📍 Kamera Listesi")
                camera_list_df = gr.DataFrame(
                    label="Mevcut Kameralar",
                    interactive=False,
                    wrap=True,
                )
                
            with gr.Column(scale=2):
                gr.Markdown("### 🎥 Canlı Yayınlar")
                camera_preview_html = gr.HTML(
                    label="Kamera Önizlemeleri",
                    elem_classes=["camera-grid"]
                )
        
        gr.Markdown("---")
        gr.Markdown("### 🔍 Deprem Analizi için Kamera Seçin")
        
        with gr.Row():
            with gr.Column():
                camera_selector = gr.Dropdown(
                    label="Kamera Seçin",
                    choices=[name for name, _ in camera_monitor.get_all_camera_streams()],
                    value=None,
                    interactive=True
                )
                
                # Preview selected camera
                selected_camera_preview = gr.HTML(
                    label="Seçili Kamera Önizlemesi"
                )
                
                with gr.Row():
                    duration_slider = gr.Slider(
                        minimum=10,
                        maximum=60,
                        value=30,
                        step=5,
                        label="Kayıt Süresi (saniye)",
                        interactive=True
                    )
                    analyze_btn = gr.Button("🎯 Kaydet ve Analiz Et", variant="primary")
                
            with gr.Column():
                analysis_result = gr.Textbox(
                    label="Analiz Sonucu",
                    lines=8,
                    interactive=False
                )
                recorded_video = gr.Video(
                    label="Kaydedilen Video",
                    interactive=False
                )
        
        # Load cameras on page load
        demo.load(
            fn=load_camera_streams,
            inputs=None,
            outputs=[camera_list_df, camera_preview_html]
        )
        
        # Update preview when camera is selected
        camera_selector.change(
            fn=preview_single_camera,
            inputs=camera_selector,
            outputs=selected_camera_preview
        )
        
        # Analyze camera action
        analyze_btn.click(
            fn=analyze_camera_stream,
            inputs=[camera_selector, duration_slider],
            outputs=[analysis_result, recorded_video]
        )

# --- Launch the App ---
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
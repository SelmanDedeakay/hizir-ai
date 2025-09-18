import gradio as gr
import time
from earthquake_monitor import earthquake_monitor
from video_classifier import video_classifier
import os
import tempfile

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
    color: #2E7D32; /* Dark green */
}
#last-update {
    font-style: italic;
    color: #757575; /* Gray */
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
        # Return a simple error message for the map
        error_map_html = "<div style='padding: 20px; color: red;'><h3>Harita yüklenemedi.</h3><p>{}</p></div>".format(str(e))
        return error_df, error_map_html, f"Hata: {str(e)}"

def classify_video_gradio(video_file_path_or_obj):
    """Handles video classification for Gradio.
    Handles both str (file path) and file object cases."""
    if video_file_path_or_obj is None:
        return "Lütfen bir video dosyası yükleyin."
    
    try:
        # Determine the type of input
        if isinstance(video_file_path_or_obj, str):
            # It's already a file path string
            temp_video_path = video_file_path_or_obj
        else:
            # Assume it's a file-like object with a .name attribute
            # This is the common case for Gradio file uploads
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
            inputs=video_input, # Gradio will pass the file path or object
            outputs=result_text
        )

# --- Launch the App ---
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
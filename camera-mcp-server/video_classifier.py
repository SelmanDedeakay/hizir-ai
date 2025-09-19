"""
Video Classification Pipeline using SmolVLM2 with Improved Robustness
(Keeping the standard processor workflow)
"""

import torch
from transformers import AutoProcessor, AutoModelForImageTextToText
import logging
from typing import Optional
import os
# --- Optional: For better video format checking ---
# import mimetypes

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoClassifier:
    """Handles loading and inference for the SmolVLM2 video classification model."""
    
    def __init__(self):
        self.model_path = "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"
        self.processor = None
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.bfloat16 if self.device == "cuda" and torch.cuda.is_available() and torch.bfloat16 is not None else torch.float32
        self.is_loaded = False

    def load_model(self):
        """Load the model and processor. This should be called once at app startup."""
        if self.is_loaded:
            logger.info("Model already loaded.")
            return

        try:
            logger.info("Loading processor...")
            self.processor = AutoProcessor.from_pretrained(self.model_path)
            
            logger.info("Loading model...")
            self.model = AutoModelForImageTextToText.from_pretrained(
                self.model_path,
                dtype=self.dtype,
                # _attn_implementation="flash_attention_2" # Yorumlandi
            ).to(self.device) # Device check is implicit in .to()
            
            self.is_loaded = True
            logger.info("Model and processor loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            self.is_loaded = False
            raise

    def classify_video(self, video_path: str) -> str:
        """
        Classify a video using the loaded model.
        Focuses on robust error handling based on the standard processor workflow.
        
        Args:
            video_path (str): Path to the video file.
            
        Returns:
            str: The model's generated text response or an error message.
        """
        if not self.is_loaded:
            raise RuntimeError("Model is not loaded. Call load_model() first.")
            
        try:
            # --- Enhanced Video File Validation ---
            if not os.path.exists(video_path):
                 logger.error(f"Video file not found: {video_path}")
                 return "Hata: Video dosyası bulunamadı."

            # Basic file size check
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            if file_size_mb < 0.1: # Less than 100KB
                logger.warning(f"Video file is very small ({file_size_mb:.2f} MB). It might be corrupted or empty.")
                # We'll still try to process it, but warn the user

            # --- Optional: Basic format check (can be expanded) ---
            # mime_type, _ = mimetypes.guess_type(video_path)
            # if mime_type and not mime_type.startswith('video'):
            #     logger.warning(f"File might not be a video based on MIME type: {mime_type}")

            # --- End of Validation ---
            
            prompt = """Is there any sign of these examples below?:
            -An earthquake happening.
            -A post-earthquake area
            -Shaking buildings
            -Collapsed or damaged buildings.

            If yes, shortly answer "Yes." else answer "No."""
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "video", "path": video_path}, # Standard way
                        {"type": "text", "text": prompt}
                    ]
                },
            ]

            logger.info(f"Processing video: {video_path}")
            
            # --- Processing using the standard processor workflow ---
            inputs = self.processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self.model.device, dtype=self.dtype)

            logger.info("Generating response...")
            generated_ids = self.model.generate(**inputs, do_sample=False, max_new_tokens=64)
            generated_texts = self.processor.batch_decode(
                generated_ids,
                skip_special_tokens=True,
            )
            
            logger.info("Response generated successfully.")
            
            full_text = generated_texts[0]
            if "Assistant:" in full_text:
                 response = full_text.split("Assistant:")[-1].strip()
            else:
                 response = full_text.strip()
                 
            return response
            
        # --- More Specific Error Handling ---
        except (OSError, IOError) as file_error:
            # Catch file system related errors (e.g., permissions, corrupted file read issues)
            logger.error(f"OS/File error processing video {video_path}: {file_error}", exc_info=True)
            return ("Hata: Video dosyası okunamadı. "
                    "Dosya bozuk, erişilemez veya desteklenmeyen bir formatta olabilir. "
                    "Lütfen geçerli bir MP4 veya MOV dosyası yükleyin.")
        except RuntimeError as re:
             # Catch runtime errors, which might include CUDA OOM or decoding errors from the processor's internal loader
             logger.error(f"Runtime error during video processing: {re}", exc_info=True)
             if "out of memory" in str(re).lower():
                 return "Hata: İşlem için yeterli GPU belleği yok. Daha kısa bir video deneyin."
             else:
                 return ("Hata: Video işlenirken bir çalışma zamanı hatası oluştu. "
                         "Bu, video formatı veya içeriğiyle ilgili olabilir. "
                         "Lütfen 10-30 saniyelik, MP4 formatında bir video yükleyin.")
        except Exception as e:
            # Catch any other unexpected errors
            logger.error(f"Unexpected error during video classification for {video_path}: {e}", exc_info=True)
            return f"Video işlenirken beklenmeyen bir hata oluştu: {str(e)}. Lütfen farklı bir video deneyin."

# Global instance for the app
video_classifier = VideoClassifier()

# --- The rest of app.py remains the same ---
# (classify_video_gradio calls video_classifier.classify_video as before)
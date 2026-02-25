import os
import sys
import json
import logging
import subprocess
import time
import warnings
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

# Suppress noisy warnings that are harmless in our setup
warnings.filterwarnings("ignore", message="torchcodec is not installed correctly")
warnings.filterwarnings("ignore", message="TensorFloat-32 \\(TF32\\) has been disabled")
warnings.filterwarnings("ignore", message="`huggingface_hub` cache-system uses symlinks")
warnings.filterwarnings("ignore", message="Lightning automatically upgraded")
warnings.filterwarnings("ignore", category=UserWarning, module="pyannote")

# Load WhisperX after potential environment setup
try:
    import whisperx
    import torch
except ImportError:
    print("Error: WhisperX or Torch not found. Please ensure you are running in the correct virtual environment.")
    sys.exit(1)

# Configuration and Paths
BASE_DIR = Path(r"C:\Users\x6921\Documents\Audacity")
SOURCE_DIR = BASE_DIR / "sourceAudio"
PROCESSED_BASE = BASE_DIR / "processed"
EXTRACTED_AUDIO_DIR = PROCESSED_BASE / "extractedAudio"
TRANSCRIPTIONS_DIR = PROCESSED_BASE / "transcriptions"
SUMMARIES_DIR = PROCESSED_BASE / "summaries"
LOGS_DIR = PROCESSED_BASE / "logs"
PROCESSED_SOURCE_DIR = PROCESSED_BASE / "sourceAudio"
PROMPT_FILE = BASE_DIR / "meetingSummarizationInstruction.md"

# LM Studio Configuration
LM_STUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"

# Load environment variables (HF_TOKEN)
load_dotenv(BASE_DIR / ".env")
HF_TOKEN = os.getenv("HF_TOKEN")

# VRAM Tuning for 12GB GPU
# large-v3 takes ~8GB, pyannote can take 4-12GB depending on batch sizes
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
BATCH_SIZE = 4 # for diarization

# Compute type: float16 for CUDA (fast + accurate), int8 for CPU fallback
if DEVICE == "cuda":
    COMPUTE_TYPE = "float16"
    print(f"[GPU DETECTED] Using CUDA device: {torch.cuda.get_device_name(0)}")
    print(f"[GPU DETECTED] VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
else:
    COMPUTE_TYPE = "int8"
    print("[WARNING] No CUDA GPU detected! Running on CPU with int8 — this will be VERY slow.")
    print("[WARNING] To fix: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 --force-reinstall")

def setup_logging():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = LOGS_DIR / f"processing_{timestamp}.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return log_file

def format_meeting_title(filename):
    # Example: "2026-02-17_-_Internal_AI_Meeting.wav" -> "2026/02/17 - Internal AI Meeting"
    stem = Path(filename).stem
    parts = stem.split("_-_")
    if len(parts) >= 2:
        date_part = parts[0].replace("-", "/")
        title_part = parts[1].replace("_", " ")
        return f"{date_part} - {title_part}"
    return stem.replace("_", " ")

def extract_audio(input_path, output_path):
    """Extracts or re-encodes audio to 16kHz mono WAV for WhisperX."""
    logging.info(f"Extracting/Converting audio: {input_path.name}")
    EXTRACTED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    
    # FFmpeg command: -i input -ar 16000 -ac 1 -c:a pcm_s16le output
    command = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ar", "16000", "-ac", "1",
        "-c:a", "pcm_s16le", str(output_path)
    ]
    
    try:
        subprocess.run(command, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg error: {e.stderr.decode()}")
        return False

def assign_speakers_to_segments(diarization, segments):
    """
    Match pyannote diarization turns to WhisperX segments by timestamp overlap.
    Each segment gets the speaker label whose turn overlaps the most with it.
    """
    # Build list of (start, end, speaker) from pyannote output
    turns = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append((turn.start, turn.end, speaker))

    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", seg_start + 0.01)
        best_speaker = "Unknown"
        best_overlap = 0.0

        for t_start, t_end, speaker in turns:
            overlap = max(0, min(seg_end, t_end) - max(seg_start, t_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker

        seg["speaker"] = best_speaker

    return segments


def transcribe_and_diarize(audio_path):
    """Runs WhisperX transcription and speaker diarization."""
    logging.info(f"Starting WhisperX transcription (large-v3) for: {audio_path.name}")

    # 1. Transcribe (force English to skip language detection)
    model = whisperx.load_model("large-v3", DEVICE, compute_type=COMPUTE_TYPE, language="en")
    audio = whisperx.load_audio(str(audio_path))
    result = model.transcribe(audio, batch_size=16, language="en")

    # Free GPU memory before alignment
    del model
    torch.cuda.empty_cache()

    # 2. Align timestamps
    model_a, metadata = whisperx.load_align_model(language_code="en", device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)

    # Free GPU memory before diarization
    del model_a
    torch.cuda.empty_cache()

    # 3. Diarize using pyannote.audio directly
    if not HF_TOKEN:
        logging.warning("HF_TOKEN not found in .env. Diarization will be skipped.")
        return result

    logging.info("Starting speaker diarization...")
    from pyannote.audio import Pipeline

    diarize_pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=HF_TOKEN
    )
    diarize_pipeline.to(torch.device(DEVICE))

    # Run diarization — pass waveform dict to avoid AudioDecoder error on Windows
    # (pyannote's own warning recommends this when torchcodec is unavailable)
    waveform_tensor = torch.from_numpy(audio).unsqueeze(0)  # shape: (1, samples)
    audio_input = {"waveform": waveform_tensor, "sample_rate": 16000}
    diarization = diarize_pipeline(audio_input)

    # DiarizeOutput is a dataclass — the actual Annotation is in .speaker_diarization
    annotation = diarization.speaker_diarization

    # Count detected speakers
    speakers = set(speaker for _, _, speaker in annotation.itertracks(yield_label=True))
    logging.info(f"Detected {len(speakers)} speaker(s): {sorted(speakers)}")

    # 4. Assign speaker labels to segments by timestamp overlap
    result["segments"] = assign_speakers_to_segments(annotation, result["segments"])

    return result, len(speakers)


def infer_speaker_names(segments):
    """Attempts to find speaker names if they introduce themselves."""
    # This is a very basic heuristic; a better one would use an LLM
    speaker_map = {}
    for seg in segments:
        speaker = seg.get("speaker")
        if not speaker or speaker in speaker_map:
            continue
            
        text = seg["text"].lower()
        if "i'm " in text or "i am " in text or "name is " in text:
            # Simple check for "Hi I'm John"
            # In a real scenario, this would be more complex
            pass
            
    return speaker_map

def summarize_with_lm_studio(transcript_text, title):
    """Sends transcript to LM Studio for summarization."""
    logging.info("Summarizing with LM Studio...")

    if not PROMPT_FILE.exists():
        system_instructions = "Summarize the following meeting transcript accurately."
    else:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            system_instructions = f.read().strip()

    # Log which model is loaded in LM Studio
    try:
        models_resp = requests.get("http://127.0.0.1:1234/v1/models", timeout=10)
        if models_resp.ok:
            models = models_resp.json().get("data", [])
            if models:
                model_id = models[0].get("id", "unknown")
                logging.info(f"LM Studio model: {model_id}")
    except Exception:
        pass  # Non-critical

    # Truncate transcript if it's very long to avoid context window overflow.
    # ~12,000 chars ≈ 3,000 tokens — leaves plenty of room for system prompt + output.
    MAX_TRANSCRIPT_CHARS = 262_144 # roughly 65536 tokens, which is possible on my hardware with GPT-OSS-20B
    truncated = False
    if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
        transcript_text = transcript_text[:MAX_TRANSCRIPT_CHARS]
        truncated = True
        logging.warning(
            f"Transcript truncated to {MAX_TRANSCRIPT_CHARS} chars to fit model context window. "
            "Consider using a model with a larger context window for full accuracy."
        )

    truncation_note = "\n\n[Note: Transcript was truncated due to length. Summary covers the first portion only.]" if truncated else ""

    prompt = f"""Meeting Title: {title}

Transcript:
{transcript_text}{truncation_note}

Please provide the summary in the requested format."""

    payload = {
        "messages": [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": -1,
        "stream": False
    }

    try:
        response = requests.post(LM_STUDIO_URL, json=payload, timeout=600)
        if not response.ok:
            logging.error(f"LM Studio Error {response.status_code}: {response.text[:500]}")
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logging.error(f"LM Studio Error: {e}")
        return None

def process_file(source_path):
    start_time = time.time()
    basename = source_path.stem
    meeting_title = format_meeting_title(source_path.name)
    
    wav_path = EXTRACTED_AUDIO_DIR / f"{basename}.wav"
    json_path = TRANSCRIPTIONS_DIR / f"{basename}_-_transcription.json"
    md_path = SUMMARIES_DIR / f"{basename}_-_summary.md"
    
    try:
        # 1. Extraction
        if not extract_audio(source_path, wav_path):
            return False
            
        # 2. Transcription + Diarization
        transcription_result = transcribe_and_diarize(wav_path)
        if isinstance(transcription_result, tuple):
            result, speaker_count = transcription_result
        else:
            result, speaker_count = transcription_result, None
        
        # 3. Save Transcription JSON
        TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
        output_data = {
            "meeting_title": meeting_title,
            "source_file": source_path.name,
            "processed_at": datetime.now().isoformat(),
            "speaker_count": speaker_count,
            "segments": result["segments"]
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
            
        # 3.5 Create and save sentence-level JSON (without word arrays)
        sentence_json_path = TRANSCRIPTIONS_DIR / f"{basename}_-_transcription_Sentence.json"
        sentence_segments = []
        for seg in result["segments"]:
            sentence_segments.append({
                "speaker": seg.get("speaker", "Unknown"),
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "").strip()
            })
            
        with open(sentence_json_path, "w", encoding="utf-8") as f:
            # We want each JSON object on its own line like the user requested
            for seg in sentence_segments:
                f.write(json.dumps(seg, ensure_ascii=False) + "\n")
            
        # 4. Build readable transcript with timestamps for LM Studio
        full_transcript = []
        for seg in sentence_segments:
            speaker = seg.get("speaker")
            start_ts = seg.get("start")
            mins = int(start_ts // 60)
            secs = int(start_ts % 60)
            full_transcript.append(f"[{mins:02d}:{secs:02d}] [{speaker}] {seg['text']}")
        
        summary_md = summarize_with_lm_studio("\n".join(full_transcript), meeting_title)
        
        if summary_md:
            SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(summary_md)
        
        # 5. Move Source
        PROCESSED_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        os.rename(source_path, PROCESSED_SOURCE_DIR / source_path.name)
        
        duration = time.time() - start_time
        speaker_info = f", {speaker_count} speaker(s) detected" if speaker_count else ""
        logging.info(f"Successfully processed {source_path.name} in {duration:.1f}s{speaker_info}")
        return True

    except Exception as e:
        import traceback
        logging.error(f"Failed to process {source_path.name}: {str(e)}")
        logging.error(traceback.format_exc())
        return False

def main():
    log_file = setup_logging()
    logging.info("Starting Meeting Transcription Pipeline")
    
    # Discover files
    files = []
    for ext in [".wav", ".mp4", ".m4a"]:
        files.extend(list(SOURCE_DIR.glob(f"*{ext}")))
    
    # Sort by creation date
    files.sort(key=lambda x: os.path.getctime(x))
    
    if not files:
        logging.info("No new files found in sourceAudio.")
        return

    logging.info(f"Found {len(files)} files to process.")
    
    for f in files:
        if not process_file(f):
            logging.error("Stopping pipeline due to error.")
            break

if __name__ == "__main__":
    main()

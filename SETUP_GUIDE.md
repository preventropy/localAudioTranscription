# Meeting Transcription & Summarization Pipeline Setup Guide

This guide describes how to use the `process_meetings.py` script to transcribe and summarize your meetings locally.

## 1. Prerequisites (Complete)
- [x] **Python 3.10.11** (Installed)
- [x] **ffmpeg** (Installed)
- [x] **NVIDIA 4070 Super** (Ready)

## 2. Configuration & Environment

### .env File
The script requires a `.env` file in the `Audacity` folder. 
**Action Required**: Ensure your file is named exactly `.env` (not `New Text Document.env`).
It must contain:
```text
HF_TOKEN=your_huggingface_token_here
```

### Dependencies
Open your terminal, activate your virtual environment, and install the required libraries:
```powershell
cd C:\Users\x6921\Documents\Audacity
.\.venv\Scripts\Activate.ps1

# Install helper for .env files
pip install python-dotenv

# (Already installed)
# pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
# pip install whisperx
# pip install requests
```

## 3. How to Process Meetings

1. **Record your meeting**: Drop the `.wav` or `.mp4` file into `C:\Users\x6921\Documents\Audacity\sourceAudio`.
2. **Start LM Studio**:
    - Load a model (e.g., Ministral 3 14B Reasoning).
    - Start the Local Server (port 1234).
3. **Run the Script**:
    ```powershell
    cd C:\Users\x6921\Documents\Audacity
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    Y
    .\.venv\Scripts\Activate.ps1
    python process_meetings.py
    ```

## 4. Output Locations

- **Transcriptions**: `Audacity\processed\transcriptions\` (JSON format with timestamps).
- **Summaries**: `Audacity\processed\summaries\` (Markdown format).
- **Logs**: `Audacity\processed\logs\` (Tracking process time and errors).
- **Archived Audio**: Your source file will automatically move to `Audacity\processed\sourceAudio\` once processing succeeds.

## 5. Customizing Summaries
You can edit `Audacity\meetingSummarizationInstruction.md` at any time to change the tone or format of the AI's meeting notes. The script reads this file every time it runs.

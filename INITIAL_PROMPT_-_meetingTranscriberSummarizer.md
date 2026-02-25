Can you help me setup an audio transcription solution that also summarizes the transcription; handling everything locally after I populate the meeting recording into a specific folder? I want to be able to record meetings from Teams and Zoom, even when I'm not the host, so they can be transcribed with speakers labeled, and then process the text into a summarized meeting notes version. 

## Existing local tech
- Nvidia 4070 Super (12GB vRAM)
- Windows 11
- LM Studio, to be used after transcription in order to summarize the transcription. (at the default http://127.0.0.1:1234)
- I'm considering the following models, and would like to be able to manually change the model through LM Studio where specifically, I have to start LM Studio:
    - GPT-OSS-20B 
    - Ministral 3 14B Reasoning (start with this as the default)
    - Ministral 3 3B Instruct 2512 (for fastest processing)
- "\Audacity\sourceAudio" folder is where I will put all recordings needing to be transcribed and summarized
- "\Audacity\processed" parent folder where I'd like any processed artifacts such as new audio files 
    - \Audacity\processed\sourceAudio (this is simply where the files go after they've been processed. Meaning they'll start in "\Audacity\sourceAudio" but then move to "\Audacity\processed\sourceAudio" after they've been transcribed)
    - \Audacity\processed\extractedAudio
    - \Audacity\processed\summaries
    - \Audacity\processed\transcriptions
    - \Audacity\processed\logs

## New tech under consideration
- Audacity or OBS for recording the audio. I understand OBS is very extensible such that I can setup recording hotkeys or tie it into the script. Unless a compelling recommendation is made, I just plan to manually use one of the two to record my audio, exporting the files to the "\Audacity\processed" folder. In other words, I'd manually handle recording and moving the audio files to where they need to be. If you think this can some how be automated further for the sake of simplicity, then I'm eager to hear your suggestions. 
- Virtual Cable (might be worth using for audio recording). Similar to the audio recording applications, I understand this application would be helpful for the recording to be cleaner, without systems sounds from notifications etc. Again, if you think this can be automated, for simplicity purposes, then I'm eager to hear your suggestions, but I'm planning to set this up myself just as I'm planning to do the recording myself. 
- ffmpeg to extract the audio track before passing to WhisperX. Where the extracted audio is saved as an intermediate file in \processed\extractedAudio 
- WhisperX; likely the large v3 (for the transcription and diarization). 
    - I'd like your help ensuring I install this and its dependencies correctly. 
    - autodetect the number of speakers


## Ideal Workflow
1. I manually record the audio via OBS or Audacity and export an audio file to \sourceAudio
2. I manually run start LM Studio > load the model of choice > start the server
3. I manually run the script for:
    1. grabbing the audio file from \sourceAudio
    2. ffmpeg extracts the audio track and moves it to \processed\extractedAudio 
    3. WhisperX pulls \extractedAudio and then transcribes and diarizes
    4. Moves the transcription file to \processed\transcriptions
    5. LM Studio summarizes, producing summary md files
    6. Moves the summarized .md file to \processed\summaries

## Requirements
- audio recordings will record both my mic input and audio out 
- support only English language
- support up to 1 hour 30 minute long meetings. 
    - There will likely be 5-7 meetings that are 10-15 minutes per week, but these are a lower priority compared to the longer meetings. 
    - There will likely be 5-10 meetings that are 1 hour long per month. Accuracy is most important for these meetings. Processing time can be many hours long if needed, as accuracy is significantly more important than the turnaround time on delivering meeting notes.
- sourceAudio files will be in .wav or .mp4 formats at a minimum
- after transcribing the \sourceAudio files should be moved to \processed
- save transcription as .json
- .md output format for summarized meeting notes 
- you can use the already existing file names and just add a suffix to them to denote transcription or summary. For example, "2026-02-17_-_Internal_AI_Meeting.wav" would become "2026-02-17_-_Internal_AI_Meeting_-_transcription.json" or "2026-02-17_-_Internal_AI_Meeting_-_summary.md"
- Meeting Title will be derived from the filenames in the "\Audacity\sourceAudio" folder. For example, "2026-02-17_-_Internal_AI_Meeting.wav" could become "2026/02/17 - Internal AI Meeting"
- Audience, Agenda Items, and To-Dos should all be derived intelligently from the transcript. In other words, I do not plan to provide any metadata up front before the transcription or the summarizing, beyond what's available in the filename itself. If there is any information missing in the summary, I'll manually edit the .md file myself to add it.
- The initial transcript and diarization can label speakers with names inferred from the transcript whenever possible, and fall back on generic names like "Speaker 1", "Speaker 2", when inferring names is not possible. The summary will continue with however the names appear, accurate or generic. 
- leverage a script to auto recognize new files in "input" folder
    - runs manually, on demand when needed. 
    - If there are multiple new files, the files should be processed in serial, by file creation date. 
    - create a log file for the script within the "\Audacity\processed\logs" directory
        - started
        - completed
        - failed
        - processing time per file (ideally, not a firm requirement)
        - speaker count detected (ideally, not a firm requirement)
        - summary model used (ideally, not a firm requirement)
    - if the script fails it doesn't attempt to retry, it just adds to the log file and stops after the logging

## Meeting transcription template 1
### Format
  - yyyy/mm/dd - Meeting Title
  - Audience (First Last, Organization; First Last, Organization; ...)
  - Table of Contents (derived from the key topics)
    - Executive Summary
    - Key Topic with summary
    - Key Topic with summary
    - Key Topic with summary
    - To Dos (Action Items):
      - PERSON A: task description; due date (if known); timestamp from transcription for when this was assigned to the person
      - PERSON B: task description; due date (if known); timestamp from transcription for when this was assigned to the person
      - PERSON C: task description; due date (if known); timestamp from transcription for when this was assigned to the person
### Summarization prompt to pass to LM Studio's model when summarizing
This prompt may adjust over time and be improved upon externally. Therefore, the authoritative prompt that will be used repeatedly for every meeting, will live in the /Audacity/ directory, specifically within the file, "meetingSummarizationInstruction.md"
`Make the Summary more conversational in tone than formal. The length of topic summaries should be more succinct than excessively verbose. Both explicitly assigned and inferred tasks should be extracted to the To-Dos section.`
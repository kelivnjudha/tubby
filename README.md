# Tubby

Tubby is a local desktop media toolkit with two modes:

- **Tubby Downloader** downloads video or MP3 audio from URLs supported by `yt-dlp`.
- **Local Transcript Intelligence** reads YouTube captions or transcribes local audio/video,
  extracts evidence with Gemma 4 through Ollama, and creates a publication-style PDF.

The finished PDF can be an e-book, narrative story, concise brief, or fully detailed
reference. Every edition includes source notes and the complete timestamped transcript.
The `tubby` command-line downloader remains available with the same functionality.

Use Tubby only with content you have the right to access and download.

## Desktop Modes

### Tubby Downloader

The left side of the desktop mode switch exposes URL inspection, video or MP3 mode,
quality selection, download progress, and output-folder controls.

### Local Transcript Intelligence

The right side of the desktop mode switch supports:

1. Manual or automatic captions from a YouTube link.
2. Local speech-to-text for common audio and video files with `faster-whisper`.
3. Evidence extraction from long transcripts in manageable chunks.
4. A separate Gemma 4 synthesis pass that builds coherent chapters without inventing facts.
5. A PDF with a cover, contents, executive summary, introduction, chapters, takeaways,
   conclusion, reference notes, and timestamped transcript appendix.

YouTube caption retrieval requires internet access. Local media transcription and Gemma 4
analysis run on your computer after their models have been downloaded.

## Requirements

- Python 3.10 or newer
- A current [Ollama](https://ollama.com/download) release
- [Gemma 4](https://ollama.com/library/gemma4) downloaded in Ollama
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and a local Whisper model
- Internet access for setup, model downloads, and retrieving YouTube captions
- FFmpeg on `PATH` only for MP3 conversion and high-resolution downloader CLI output

macOS users need macOS 14 Sonoma or newer because that is the minimum version supported
by the current Ollama release. Both Apple silicon and Intel Macs are supported; Ollama
uses GPU acceleration on Apple silicon and CPU execution on Intel.

The setup scripts download `gemma4` and the multilingual Whisper `small` model by default.
Performance depends on available RAM, GPU memory, media duration, and transcript length.
Local speech-to-text defaults to CPU `int8` execution for consistent Windows, macOS, and
Linux behavior.

## Automatic Setup

### Windows

Double-click `setup.cmd`, or run it from Command Prompt:

```bat
setup.cmd
```

For setup options, run the PowerShell script directly:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

The script creates `.venv`, installs Tubby and local speech-to-text dependencies, downloads
the `small` speech model, installs Ollama through `winget` when needed, starts Ollama, and
downloads `gemma4`.

To skip an existing model download:

```powershell
.\setup.ps1 -SkipModelPull
```

To skip the speech-model download:

```powershell
.\setup.ps1 -SkipSpeechModelDownload
```

To install FFmpeg for the downloader CLI as part of setup:

```powershell
.\setup.ps1 -InstallFfmpeg
```

To use another Ollama model:

```powershell
.\setup.ps1 -Model gemma4:e2b
```

To use another speech model:

```powershell
.\setup.ps1 -SpeechModel medium
```

### macOS

Double-click `setup-macos.command` in Finder. If macOS asks for confirmation, Control-click
the file, choose `Open`, and confirm once.

You can also run the same setup from Terminal:

```sh
chmod +x setup-macos.command setup.sh
./setup-macos.command
```

The macOS setup checks for macOS 14 or newer, creates `.venv`, installs Python and Tk
support through Homebrew when needed, installs Tubby and Ollama, downloads the local
speech model, starts Ollama, and downloads `gemma4`.

Pass another Ollama model name as the first argument when required:

```sh
./setup-macos.command gemma4:e2b
```

The optional second argument selects the speech model:

```sh
./setup-macos.command gemma4 medium
```

### Linux

```sh
chmod +x setup.sh
./setup.sh
```

Pass another Ollama model name as the first argument when required:

```sh
./setup.sh gemma4:e2b
```

The optional second argument selects the speech model:

```sh
./setup.sh gemma4 medium
```

The Linux setup installs Ollama with its official installer when needed. The same
`setup.sh` remains usable directly from a macOS terminal.

## Run The Desktop App

Windows:

```powershell
.\.venv\Scripts\python -m tubby
```

macOS or Linux:

```sh
./.venv/bin/python -m tubby
```

Use the top mode switch to move between the downloader and transcript intelligence.
Local Transcript Intelligence accepts either a YouTube link or a selected local media file.
Choose the report language, output style, models, and output folder, then select
`Create PDF`.

Reports are saved to `Downloads/Tubby Reports` by default.

## Output Styles

- **E-book** creates a polished nonfiction edition with logical chapters and takeaways.
- **Story** follows the source chronologically as a factual narrative.
- **Short** keeps the result compact while retaining material facts and caveats.
- **Fully detailed** preserves technical explanations, chronology, examples, decisions,
  disagreements, and open questions.

Style changes presentation and depth, not the evidence standard. Gemma is instructed not
to invent dialogue, motives, events, examples, or conclusions.

## Language Support

English is the default report language. The desktop app includes common language presets
supported by both Gemma 4 and Tubby's PDF renderer.

The included PDF renderer supports the listed left-to-right language presets. Right-to-left
PDF layout is not currently included, so languages such as Arabic are not offered as presets.

The selected language controls:

- Which YouTube caption track Tubby prefers
- The language Gemma 4 uses for the generated edition

Local speech language is detected automatically. The transcript appendix remains in the
source language, while the crafted report uses the selected report language.

## Transcription Limitations

For a YouTube link, Tubby still reads an existing caption track. When a video has no
captions, download a copy you have the right to use and select it as a local media file
for speech-to-text. Private, age-restricted, region-restricted, or bot-protected videos
may require authentication that is not currently exposed in the desktop app.

Automatic captions and local speech recognition can contain transcription mistakes.
The PDF includes the source transcript so important claims can be checked.

## Downloader Desktop And CLI

The desktop downloader and command-line interface use the same `yt-dlp` based media
download functionality.

Show video information:

```sh
tubby --info "https://www.youtube.com/watch?v=VIDEO_ID"
```

Download video:

```sh
tubby "https://www.youtube.com/watch?v=VIDEO_ID" --mode video --quality 1080p --output Downloads
```

Download MP3 audio:

```sh
tubby "https://www.youtube.com/watch?v=VIDEO_ID" --mode audio --audio-quality "320 kbps" --output Downloads
```

YouTube commonly serves 1080p, 1440p, and 2160p video separately from audio. FFmpeg is
required to merge those streams and to convert audio to MP3. Without FFmpeg, video mode
is limited to single-file streams and high-resolution selections are rejected.

## Manual Installation

```sh
python -m venv .venv
```

Activate the environment, then install Tubby:

```sh
python -m pip install --upgrade pip
pip install -e .
python -c "from tubby.media_transcript import download_transcription_model; download_transcription_model('small')"
ollama pull gemma4
```

Ollama must be running at `http://127.0.0.1:11434`. Advanced installations can override
the defaults with:

```sh
TUBBY_OLLAMA_URL=http://127.0.0.1:11434
TUBBY_OLLAMA_MODEL=gemma4
TUBBY_WHISPER_MODEL=small
TUBBY_WHISPER_DEVICE=cpu
TUBBY_WHISPER_COMPUTE_TYPE=int8
```

## Validate

Install test dependencies and run:

```sh
pip install -e ".[test]"
python -m unittest discover -s tests
python -m compileall tubby tests
```

## Build A Desktop Executable

```sh
pip install -e ".[build]"
pyinstaller tubby.spec
```

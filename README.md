# Tubby

Tubby is a local desktop media toolkit with two modes:

- **Tubby Downloader** downloads video or MP3 audio from URLs supported by `yt-dlp`.
- **Local Transcript Intelligence** reads YouTube captions or transcribes local audio/video,
  extracts evidence with a selected local Ollama model, and creates a publication-style PDF.

The finished PDF can be an e-book, narrative story, concise brief, or fully detailed
reference. Every chapter includes a source timestamp range; the complete raw transcript is
an optional appendix and is excluded by default.
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
4. A separate local-model synthesis pass that builds coherent chapters without inventing facts.
5. A PDF with a cover, contents, executive summary, introduction, timestamped chapters,
   takeaways, conclusion, reference notes, and an optional raw transcript appendix.
6. An Ollama model selector populated from compatible models installed on the computer.

YouTube caption retrieval requires internet access. Local media transcription and Ollama
analysis run on your computer after their models have been downloaded.

## Requirements

- Python 3.10 or newer
- A current [Ollama](https://ollama.com/download) release
- [Gemma 4](https://ollama.com/library/gemma4), recommended, or another compatible Ollama model
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and a local Whisper model
- Internet access for setup, model downloads, and retrieving YouTube captions
- FFmpeg on `PATH` only for MP3 conversion and high-resolution downloader CLI output

macOS users need macOS 14 Sonoma or newer because that is the minimum version supported
by the current Ollama release. Both Apple silicon and Intel Macs are supported; Ollama
uses GPU acceleration on Apple silicon and CPU execution on Intel.

The setup scripts recommend `gemma4` and download the multilingual Whisper `small` model
by default. If other report-capable Ollama models are already installed, setup offers a
choice between installing Gemma 4 and continuing with one of those models.
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
the `small` speech model, installs Ollama through `winget` when needed, and starts Ollama.
When Gemma 4 is not installed but other models are available, it asks whether to install
Gemma 4 or continue with an installed model.

To prohibit a new Ollama model download and choose only from installed models:

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

To explicitly select another Ollama model and bypass the interactive choice:

```powershell
.\setup.ps1 -Model gemma4:e2b
```

For unattended Windows setup, preselect an installed model with:

```powershell
$env:TUBBY_SETUP_MODEL_CHOICE = "qwen3:4b"
.\setup.ps1
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
speech model, and starts Ollama. If another compatible model is already installed, the
same Gemma 4 or installed-model choice is shown.

Pass another Ollama model name as the first argument to select it directly:

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

For unattended macOS or Linux setup, preselect an installed model with
`TUBBY_SETUP_MODEL_CHOICE`, or set `TUBBY_SKIP_MODEL_PULL=1` to prohibit downloading a
new Ollama model:

```sh
TUBBY_SETUP_MODEL_CHOICE=qwen3:4b ./setup.sh
TUBBY_SKIP_MODEL_PULL=1 ./setup.sh
```

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
The Ollama model selector reads compatible installed models automatically. Choose the
report language, output style, models, and output folder, then select
`Create PDF`.

Reports are saved to `Downloads/Tubby Reports` by default.
Enable `Add Raw Source Transcript` only when the PDF should include the complete caption or
speech-recognition text. Each chapter shows its supporting source range. In YouTube reports,
selecting that range opens the source video at the chapter's start time.

## Ollama Model Selection

Tubby reads installed model metadata from
[Ollama's local model-list API](https://docs.ollama.com/api/tags). The desktop selector
shows text-generation models that can create reports and omits embedding-only models.
Select `Refresh` after installing or removing a model while Tubby is open.
Ollama cloud entries are also omitted because Tubby keeps report generation on the local
Ollama connection and relies on local structured output.

Gemma 4 remains the recommended report model. The selected model is saved in the current
user's Tubby configuration and restored the next time the desktop app starts.

Ollama does not expose language support in its installed-model metadata. Tubby therefore
uses a conservative family classification:

- Confirmed broad multilingual families such as Gemma 3/4, Qwen, and Aya keep every report
  language option enabled and show no warning.
- Known English-focused families restrict the report language to English.
- Unknown model families remain selectable, but Tubby warns that multilingual output has
  not been verified.

The setup chooser uses the same classification and only prints a language warning when
the selected model is English-focused or its multilingual support is unknown.

These checks describe language compatibility, not report quality. Smaller or specialized
models may still produce weaker extraction or invalid structured output.

## Output Styles

- **E-book** creates a polished nonfiction edition with logical chapters and takeaways.
- **Story** follows the source chronologically as a factual narrative.
- **Short** keeps the result compact while retaining material facts and caveats.
- **Fully detailed** preserves technical explanations, chronology, examples, decisions,
  disagreements, and open questions.

Style changes presentation and depth, not the evidence standard. The selected model is
instructed not to invent dialogue, motives, events, examples, or conclusions.

## Language Support

English is the default report language. The desktop app includes common language presets
supported by Gemma 4 and Tubby's PDF renderer. Other model families are checked using the
compatibility rules above.

The included PDF renderer supports the listed left-to-right language presets. Right-to-left
PDF layout is not currently included, so languages such as Arabic are not offered as presets.

The selected language controls:

- Which YouTube caption track Tubby prefers
- The language the selected Ollama model uses for the generated edition

Local speech language is detected automatically. When included, the raw transcript appendix
remains in the source language, while the crafted report uses the selected report language.

## Transcription Limitations

For a YouTube link, Tubby still reads an existing caption track. When a video has no
captions, download a copy you have the right to use and select it as a local media file
for speech-to-text. Private, age-restricted, region-restricted, or bot-protected videos
may require authentication that is not currently exposed in the desktop app.

Automatic captions and local speech recognition can contain transcription mistakes.
Chapter source ranges support verification against the original media. Include the optional
raw transcript appendix when line-by-line caption or speech-recognition text is also needed.

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

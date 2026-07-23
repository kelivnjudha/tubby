# Tubby

Tubby turns a YouTube transcript into a structured PDF report using Gemma 4 through
your local Ollama installation. The desktop app retrieves available captions, extracts
the important information locally, and includes the full timestamped transcript in the
finished PDF.

The existing `tubby` command-line downloader remains available for downloading video
and MP3 audio from URLs supported by `yt-dlp`.

Use Tubby only with content you have the right to access and download.

## Desktop App

The desktop workflow:

1. Reads manual YouTube captions or automatic captions when manual captions are absent.
2. Prefers captions matching the selected report language, then falls back to another
   available caption track.
3. Analyzes long transcripts in manageable chunks with local Gemma 4.
4. Extracts an executive summary, key points, important details, decisions, actions,
   questions, and caveats.
5. Creates a PDF containing the analysis, source details, and complete transcript.

Transcript retrieval requires internet access. The transcript analysis is sent only to
the Ollama API running on your computer by default.

## Requirements

- Python 3.10 or newer
- A current [Ollama](https://ollama.com/download) release
- [Gemma 4](https://ollama.com/library/gemma4) downloaded in Ollama
- Internet access for retrieving YouTube captions
- FFmpeg on `PATH` only for MP3 conversion and high-resolution downloader CLI output

macOS users need macOS 14 Sonoma or newer because that is the minimum version supported
by the current Ollama release. Both Apple silicon and Intel Macs are supported; Ollama
uses GPU acceleration on Apple silicon and CPU execution on Intel.

The default `gemma4` Ollama model is approximately 9.6 GB. It supports multilingual
analysis and a long context window, but performance depends on available RAM, GPU memory,
and transcript length.

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

The script creates `.venv`, installs Tubby, installs Ollama through `winget` when needed,
starts the local Ollama service, and downloads `gemma4`.

To skip an existing model download:

```powershell
.\setup.ps1 -SkipModelPull
```

To install FFmpeg for the downloader CLI as part of setup:

```powershell
.\setup.ps1 -InstallFfmpeg
```

To use another Ollama model:

```powershell
.\setup.ps1 -Model gemma4:e2b
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
support through Homebrew when needed, installs Tubby and Ollama, starts the local Ollama
service, and downloads `gemma4`.

Pass another Ollama model name as the first argument when required:

```sh
./setup-macos.command gemma4:e2b
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

Paste a YouTube URL, choose the report language and output folder, then select
`Create PDF`. The model field defaults to `gemma4` and can be changed to any compatible
model already installed in Ollama.

Reports are saved to `Downloads/Tubby Reports` by default.

## Language Support

English is the default report language. The desktop app includes common language presets
supported by both Gemma 4 and Tubby's PDF renderer.

The included PDF renderer supports the listed left-to-right language presets. Right-to-left
PDF layout is not currently included, so languages such as Arabic are not offered as presets.

The selected language controls:

- Which YouTube caption track Tubby prefers
- The language Gemma 4 uses for the generated analysis

The transcript appendix remains in the language supplied by YouTube. When no matching
captions exist, Tubby analyzes an available fallback transcript and writes the findings
in the selected report language.

## Caption Limitations

Tubby currently reads existing YouTube caption tracks. It does not perform speech-to-text
on videos without captions. Private, age-restricted, region-restricted, or bot-protected
videos may require authentication support that is not currently exposed in the desktop
app.

Automatic captions and automatically translated captions can contain transcription or
translation mistakes. The PDF includes the source transcript so important claims can be
checked.

## Downloader CLI

The command-line interface keeps its existing media download functionality.

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
ollama pull gemma4
```

Ollama must be running at `http://127.0.0.1:11434`. Advanced installations can override
the defaults with:

```sh
TUBBY_OLLAMA_URL=http://127.0.0.1:11434
TUBBY_OLLAMA_MODEL=gemma4
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

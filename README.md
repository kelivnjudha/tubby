<p align="center">
  <img src="public/logo/tubby_logo_for_github_readme.png" alt="Tubby" width="680">
</p>

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
6. An Ollama model selector populated from compatible installed models, with each model's
   recommendation, report strength, and approximate installed size.

YouTube caption retrieval requires internet access. Local media transcription and Ollama
analysis run on your computer after their models have been downloaded.

## Requirements

- Python 3.10 or newer
- A current [Ollama](https://ollama.com/download) release
- One compatible local Ollama text-generation model; setup offers several compact options
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and a local Whisper model
- Internet access for setup, model downloads, and retrieving YouTube captions
- FFmpeg on `PATH` only for MP3 conversion and high-resolution downloader CLI output

macOS users need macOS 14 Sonoma or newer because that is the minimum version supported
by the current Ollama release. Both Apple silicon and Intel Macs are supported; Ollama
uses GPU acceleration on Apple silicon and CPU execution on Intel.

The setup scripts present a model catalog instead of requiring Gemma 4. `qwen3:4b` is the
balanced recommendation, and smaller downloads are available for constrained computers.
Setup also detects compatible models already installed in Ollama. The multilingual Whisper
`small` speech model remains the default transcription download.
Performance depends on available RAM, GPU memory, media duration, and transcript length.
Local speech-to-text defaults to CPU `int8` execution for consistent Windows, macOS, and
Linux behavior.

## Install A Release

GitHub releases provide self-contained desktop installers. They include Tubby, Python, and
its application dependencies; Python does not need to be installed separately.

### Windows Release

Download `Tubby-VERSION-Windows-x64-Setup.exe` from the
[latest release](https://github.com/kelivnjudha/tubby/releases/latest). The per-user installer
adds Tubby to the Start Menu, offers an optional desktop shortcut, and includes an uninstaller.
The x64 build supports x64 Windows 10/11 and Windows 11 on Arm through x64 emulation.

### macOS Release

Download the DMG matching the Mac:

- `Tubby-VERSION-macOS-arm64.dmg` for Apple silicon
- `Tubby-VERSION-macOS-x64.dmg` for Intel

Open the DMG and drag `Tubby` into `Applications`. Tubby requires macOS 14 Sonoma or newer.
When a release is not signed and notarized, macOS may require Control-clicking Tubby,
selecting `Open`, and confirming once. See [Release Signing](#release-signing) for producing
notarized builds.

The installers do not bundle Ollama, multi-gigabyte AI models, or FFmpeg. The downloader
works without Ollama. FFmpeg is still required for MP3 conversion and high-resolution video
with merged audio. Before creating transcript reports, install
[Ollama](https://ollama.com/download), start it, and install a report model:

```sh
ollama pull qwen3:4b
```

The selected local Whisper speech model downloads on the first local audio or video
transcription. Source checkouts can use the automatic setup scripts below to download these
models in advance.

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
It then shows the compact model catalog with approximate download sizes, language coverage,
recommended uses, and tradeoffs. Installed options are labeled and do not download again.

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
.\setup.ps1 -Model granite4.1:3b
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
speech model, and starts Ollama. It shows the same compact model catalog as Windows and
labels compatible models that are already installed.

Pass another Ollama model name as the first argument to select it directly:

```sh
./setup-macos.command granite4.1:3b
```

The optional second argument selects the speech model:

```sh
./setup-macos.command qwen3:4b medium
```

### Linux

```sh
chmod +x setup.sh
./setup.sh
```

Pass another Ollama model name as the first argument when required:

```sh
./setup.sh granite4.1:3b
```

The optional second argument selects the speech model:

```sh
./setup.sh qwen3:4b medium
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

When several Ollama models are installed, each menu option uses the format
`model | recommendation or strength | size`. The selected-model summary explains its best
uses, language coverage, and known tradeoffs. Models outside Tubby's curated catalog remain
available but are clearly marked as unprofiled or unverified.

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

Interactive setup offers these local models. Download sizes are approximate and can change
when Ollama updates a tag:

| Model | Approx. download | Recommended use | Language coverage and tradeoffs |
| --- | ---: | --- | --- |
| **[Qwen 3 4B](https://ollama.com/library/qwen3:4b)** | 2.5 GB | **Best overall:** polished e-books, stories, and detailed reports | 119 languages and dialects |
| [Granite 4.1 3B](https://ollama.com/library/granite4.1:3b) | 2.1 GB | **Best structured reports:** evidence extraction, JSON reliability, technical or business sources | Multilingual |
| [Qwen 3.5 2B](https://ollama.com/library/qwen3.5:2b-q4_K_M) | 1.9 GB | Fast short or medium reports on low-memory computers | Multilingual; less nuance in long, fully detailed reports |
| [Qwen 3 1.7B](https://ollama.com/library/qwen3:1.7b) | 1.4 GB | **Smallest practical option:** briefs and shorter videos | 119 languages and dialects; simpler prose and weaker long synthesis |
| [Llama 3.2 3B](https://ollama.com/library/llama3.2:3b) | 2.0 GB | Fast summaries, rewriting, and story-style reports | Officially supports English, German, French, Italian, Portuguese, Hindi, Spanish, and Thai |
| [Phi-4 Mini 3.8B](https://ollama.com/library/phi4-mini:3.8b) | 2.5 GB | Lectures with math, logic, or dense technical explanations | Multilingual |
| [Gemma 3 4B](https://ollama.com/library/gemma3:4b) | 3.3 GB | Broad multilingual writing coverage | 140+ languages |
| [Ministral 3 3B](https://ollama.com/library/ministral-3:3b) | 3.0 GB | Long-context consolidation and JSON-oriented output | Dozens of languages; requires a current Ollama release |

Every catalog model can run Tubby's transcript extraction and PDF workflow. Smaller models
reduce storage and memory requirements but can lose detail, prose quality, or structured
output reliability on long sources. Available memory also depends on context length and
hardware, not only the download size.

`qwen3:4b` is the default highlighted recommendation, not a forced download. Interactive
setup can choose any catalog entry or a compatible installed model. In unattended use,
Tubby reuses the requested or first compatible installed model before downloading the
default. Passing a model explicitly continues to bypass the chooser. Existing Gemma 4 and
other compatible local models remain supported and appear as installed options.

The selected model is saved in the current user's Tubby configuration and restored the next
time the desktop app starts. The desktop selector lists compatible models that are actually
installed and compares their recommendation, strength, and detected size; run setup or
`ollama pull MODEL_NAME`, then select `Refresh` to add another one.

Ollama does not expose language support in its installed-model metadata. Tubby therefore
uses a conservative family classification:

- Confirmed multilingual catalog models and broad multilingual families such as Gemma,
  Qwen, Granite, Phi, Ministral, and Aya keep report-language options enabled.
- Llama 3.2 keeps language options available but shows its eight-language support limit.
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
supported by the recommended multilingual models and Tubby's PDF renderer. Each selected
model is checked using the compatibility rules above.

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
ollama pull qwen3:4b
```

Ollama must be running at `http://127.0.0.1:11434`. Advanced installations can override
the defaults with:

```sh
TUBBY_OLLAMA_URL=http://127.0.0.1:11434
TUBBY_OLLAMA_MODEL=qwen3:4b
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

On Windows, this creates `dist/Tubby.exe`. On macOS, it creates `dist/Tubby.app`.

## Release Installers

The `Build release installers` GitHub Actions workflow runs the full tests and builds:

- A Windows x64 Inno Setup installer
- A native Apple silicon DMG
- A native Intel Mac DMG
- `SHA256SUMS.txt` for tagged releases

Run the workflow manually to test release artifacts. Pushing a version tag that matches
`pyproject.toml`, such as `v0.9.0`, builds the installers and publishes a GitHub release.
Packaging implementation and local build commands are documented in
[`packaging/README.md`](packaging/README.md).

## Release Signing

Unsigned installers are usable but can trigger Windows SmartScreen or macOS Gatekeeper.
The release workflow signs Windows and macOS artifacts when signing secrets are configured.
Apple notarization uses `notarytool` and staples the resulting ticket to each DMG. Secret
names and certificate preparation are documented in
[`packaging/README.md`](packaging/README.md).

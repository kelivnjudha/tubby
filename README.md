# Tubby

Tubby is a small desktop and command-line downloader for YouTube video and MP3 audio.
The maintained app is now a single Python package backed by `yt-dlp`, with the old
v0.1, v0.2, and Android/Kivy copies preserved under `legacy/`.

Use Tubby only for content you have the right to download.

## Requirements

- Python 3.10 or newer
- FFmpeg on `PATH` for MP3 conversion and high-resolution video downloads with sound

YouTube commonly serves 1080p, 1440p, and 2160p video separately from audio. Tubby can
merge those streams when FFmpeg is installed. Without FFmpeg, video mode is limited to
single-file streams, which may be 720p, 480p, or lower depending on the video.

## Install FFmpeg

Tubby uses FFmpeg to merge high-resolution video with audio and to convert audio
downloads to MP3. After installing it, restart your terminal and verify:

```sh
ffmpeg -version
```

### Windows

Recommended with Windows Package Manager:

```powershell
winget install --id Gyan.FFmpeg --exact
```

Manual install:

1. Open the official FFmpeg download page: <https://ffmpeg.org/download.html>
2. Choose the Windows build from `gyan.dev`: <https://www.gyan.dev/ffmpeg/builds/>
3. Download the `ffmpeg-release-essentials.zip` release build.
4. Extract it somewhere stable, for example `C:\ffmpeg`.
5. Add the extracted `bin` folder to your user `Path`. If you rename the extracted
   folder so `ffmpeg.exe` is at `C:\ffmpeg\bin\ffmpeg.exe`, use:

```powershell
[Environment]::SetEnvironmentVariable(
    "Path",
    [Environment]::GetEnvironmentVariable("Path", "User") + ";C:\ffmpeg\bin",
    "User"
)
```

Open a new terminal and run `ffmpeg -version`.

### macOS

With Homebrew:

```sh
brew install ffmpeg
ffmpeg -version
```

### Linux

Ubuntu/Debian:

```sh
sudo apt update
sudo apt install ffmpeg
ffmpeg -version
```

Fedora:

```sh
sudo dnf install ffmpeg
ffmpeg -version
```

Arch Linux:

```sh
sudo pacman -S ffmpeg
ffmpeg -version
```

## Install

```sh
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run The Desktop App

```sh
python -m tubby
```

or, after installation:

```sh
tubby-gui
```

## Run From The CLI

Show video information:

```sh
tubby --info "https://www.youtube.com/watch?v=VIDEO_ID"
```

Download video:

```sh
tubby "https://www.youtube.com/watch?v=VIDEO_ID" --mode video --quality 1080p --output Downloads
```

For 1080p, 1440p, or 2160p with sound, install FFmpeg first. Without FFmpeg, Tubby
will only use single-file video streams and will reject high-resolution selections
instead of silently downloading a lower-resolution file.

Download MP3 audio:

```sh
tubby "https://www.youtube.com/watch?v=VIDEO_ID" --mode audio --audio-quality "320 kbps" --output Downloads
```

Audio quality settings control MP3 conversion quality. They cannot restore quality that is
not present in the original source stream.

## Validate

```sh
python -m unittest discover -s tests
python -m compileall tubby tests
```

## Build A Desktop Executable

```sh
pip install ".[build]"
pyinstaller tubby.spec
```

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, TypeVar

import customtkinter as ctk

from tubby import __version__
from tubby.downloader import (
    AUDIO_QUALITY_OPTIONS,
    VIDEO_QUALITY_OPTIONS,
    TubbyError,
    VideoInfo,
    download_media,
    fetch_video_info,
    has_ffmpeg,
)
from tubby.utils import format_download_status

T = TypeVar("T")


class TubbyApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title(f"Tubby {__version__}")
        self.geometry("760x540")
        self.minsize(680, 500)

        self.url_var = ctk.StringVar()
        self.output_var = ctk.StringVar(value=str(Path.home() / "Downloads"))
        self.mode_var = ctk.StringVar(value="video")
        self.quality_var = ctk.StringVar(value="Best")
        self.status_var = ctk.StringVar(value="Ready")
        self._worker: threading.Thread | None = None
        self._current_info: VideoInfo | None = None
        self._ffmpeg_available = has_ffmpeg()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        title = ctk.CTkLabel(self, text="Tubby", font=ctk.CTkFont(size=28, weight="bold"))
        title.grid(row=0, column=0, padx=24, pady=(22, 8), sticky="w")

        form = ctk.CTkFrame(self, corner_radius=8)
        form.grid(row=1, column=0, padx=24, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="URL").grid(
            row=0,
            column=0,
            padx=(16, 10),
            pady=(16, 8),
            sticky="w",
        )
        self.url_entry = ctk.CTkEntry(
            form,
            textvariable=self.url_var,
            placeholder_text="https://...",
        )
        self.url_entry.grid(row=0, column=1, columnspan=3, padx=(0, 16), pady=(16, 8), sticky="ew")

        ctk.CTkLabel(form, text="Folder").grid(row=1, column=0, padx=(16, 10), pady=8, sticky="w")
        self.output_entry = ctk.CTkEntry(form, textvariable=self.output_var)
        self.output_entry.grid(row=1, column=1, padx=(0, 8), pady=8, sticky="ew")
        browse_button = ctk.CTkButton(form, text="Browse", width=92, command=self._choose_output)
        browse_button.grid(row=1, column=2, padx=(0, 16), pady=8, sticky="e")

        ctk.CTkLabel(form, text="Mode").grid(
            row=2,
            column=0,
            padx=(16, 10),
            pady=(8, 16),
            sticky="w",
        )
        self.mode_control = ctk.CTkSegmentedButton(
            form,
            values=["video", "audio"],
            variable=self.mode_var,
            command=self._mode_changed,
        )
        self.mode_control.grid(row=2, column=1, padx=(0, 8), pady=(8, 16), sticky="w")

        self.quality_menu = ctk.CTkOptionMenu(
            form,
            values=list(VIDEO_QUALITY_OPTIONS),
            variable=self.quality_var,
            command=lambda _: self._refresh_info_summary(),
            width=120,
        )
        self.quality_menu.grid(row=2, column=2, padx=(0, 16), pady=(8, 16), sticky="e")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, padx=24, pady=(8, 4), sticky="ew")
        actions.grid_columnconfigure(2, weight=1)

        self.info_button = ctk.CTkButton(actions, text="Fetch Info", command=self._fetch_info)
        self.info_button.grid(row=0, column=0, padx=(0, 8), sticky="w")
        self.download_button = ctk.CTkButton(actions, text="Download", command=self._download)
        self.download_button.grid(row=0, column=1, padx=(0, 8), sticky="w")

        self.progress = ctk.CTkProgressBar(actions)
        self.progress.set(0)
        self.progress.grid(row=0, column=2, sticky="ew")

        self.info_box = ctk.CTkTextbox(self, corner_radius=8, wrap="word")
        self.info_box.grid(row=3, column=0, padx=24, pady=8, sticky="nsew")
        intro = "Paste a YouTube URL, fetch details, then download video or MP3 audio."
        if not self._ffmpeg_available:
            intro = (
                f"{intro}\n\nFFmpeg is not on PATH. 1080p, 1440p, 2160p, and MP3 audio "
                "conversion require FFmpeg."
            )
        self.info_box.insert("1.0", intro)
        self.info_box.configure(state="disabled")

        status = ctk.CTkLabel(self, textvariable=self.status_var, anchor="w")
        status.grid(row=4, column=0, padx=24, pady=(4, 18), sticky="ew")

    def _mode_changed(self, value: str) -> None:
        if value == "audio":
            self.quality_menu.configure(values=list(AUDIO_QUALITY_OPTIONS), state="normal")
            if self.quality_var.get() not in AUDIO_QUALITY_OPTIONS:
                self.quality_var.set("Best")
        else:
            self.quality_menu.configure(values=list(VIDEO_QUALITY_OPTIONS), state="normal")
            if self.quality_var.get() not in VIDEO_QUALITY_OPTIONS:
                self.quality_var.set("Best")
        self._refresh_info_summary()

    def _choose_output(self) -> None:
        directory = filedialog.askdirectory(initialdir=self.output_var.get() or str(Path.home()))
        if directory:
            self.output_var.set(directory)

    def _fetch_info(self) -> None:
        url = self._validated_url()
        if url is None:
            return

        self._run_background(lambda: fetch_video_info(url), self._show_info)

    def _download(self) -> None:
        url = self._validated_url()
        if url is None:
            return

        output = self.output_var.get().strip() or str(Path.home() / "Downloads")
        mode = self.mode_var.get()
        quality = self.quality_var.get()
        started = self._run_background(
            lambda: download_media(url, output, mode, quality, self._progress_hook),
            self._download_finished,
        )
        if started:
            self.progress.set(0)
            self._start_loader("Starting download...")

    def _validated_url(self) -> str | None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Tubby", "Enter a YouTube URL first.")
            return None
        return url

    def _run_background(self, work: Callable[[], T], on_success: Callable[[T], None]) -> bool:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Tubby", "A task is already running.")
            return False

        self._set_busy(True)

        def runner() -> None:
            try:
                result = work()
            except TubbyError as exc:
                message = str(exc)
                self.after(0, lambda message=message: self._show_error(message))
            except Exception as exc:
                message = f"Unexpected error: {exc}"
                self.after(0, lambda message=message: self._show_error(message))
            else:
                self.after(0, lambda: on_success(result))
            finally:
                self.after(0, lambda: self._set_busy(False))

        self._worker = threading.Thread(target=runner, daemon=True)
        self._worker.start()
        return True

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.info_button.configure(state=state)
        self.download_button.configure(state=state)
        if busy:
            self.status_var.set("Working...")

    def _show_info(self, info: VideoInfo) -> None:
        self._current_info = info
        self._refresh_info_summary()
        self.status_var.set("Video information loaded.")

    def _download_finished(self, path: Path) -> None:
        self._set_progress(1, f"Saved to {path}")
        self.status_var.set(f"Saved to {path}")
        self._append_info_text(f"\n\nSaved to: {path}")

    def _show_error(self, message: str) -> None:
        self._stop_loader()
        self.status_var.set("Error")
        messagebox.showerror("Tubby", message)

    def _progress_hook(self, event: dict[str, object]) -> None:
        status = event.get("status")
        if status == "downloading":
            downloaded = _number(event.get("downloaded_bytes")) or 0
            total = _number(event.get("total_bytes")) or _number(event.get("total_bytes_estimate"))
            speed = _number(event.get("speed"))
            eta = _number(event.get("eta"))
            ratio, text = format_download_status(downloaded, total, speed, eta)

            if total:
                self.after(0, lambda: self._set_progress(ratio, text))
            else:
                self.after(0, lambda: self._start_loader(text))
        elif status == "finished":
            self.after(0, lambda: self._set_progress(1, "Finalizing download..."))

    def _start_loader(self, text: str) -> None:
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.status_var.set(text)

    def _stop_loader(self) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")

    def _set_progress(self, ratio: float, text: str) -> None:
        self._stop_loader()
        self.progress.set(ratio)
        self.status_var.set(text)

    def _set_info_text(self, text: str) -> None:
        self.info_box.configure(state="normal")
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", text)
        self.info_box.configure(state="disabled")

    def _refresh_info_summary(self) -> None:
        if self._current_info is None:
            return
        self._set_info_text(
            "\n".join(
                self._current_info.summary_lines(
                    mode=self.mode_var.get(),
                    quality=self.quality_var.get(),
                    allow_merge=self._ffmpeg_available,
                )
            )
        )

    def _append_info_text(self, text: str) -> None:
        self.info_box.configure(state="normal")
        self.info_box.insert("end", text)
        self.info_box.configure(state="disabled")


def _number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def main() -> int:
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = TubbyApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

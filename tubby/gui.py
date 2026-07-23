from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import PhotoImage, TclError, filedialog, messagebox
from typing import Callable, TypeVar

import customtkinter as ctk

from tubby import __version__
from tubby.downloader import (
    AUDIO_QUALITY_OPTIONS,
    VIDEO_QUALITY_OPTIONS,
    TubbyError,
    download_media,
    fetch_video_info,
    has_ffmpeg,
)
from tubby.languages import LANGUAGE_OPTIONS
from tubby.local_ai import OllamaError
from tubby.media_transcript import (
    DEFAULT_WHISPER_MODEL,
    SUPPORTED_MEDIA_EXTENSIONS,
    WHISPER_MODEL_OPTIONS,
)
from tubby.ollama_models import (
    DEFAULT_MODEL,
    ModelLanguageSupport,
    OllamaModel,
    OllamaModelError,
    choose_preferred_model,
    list_installed_models,
    model_selector_details,
    model_selector_label,
    ordered_report_models,
    report_language_warning,
    save_preferred_model,
)
from tubby.pdf_report import PdfReportError
from tubby.report_styles import DEFAULT_REPORT_STYLE, REPORT_STYLE_OPTIONS
from tubby.transcript import TranscriptError
from tubby.utils import format_download_status
from tubby.workflow import AnalysisResult, analyze_media_to_pdf, analyze_youtube_to_pdf

T = TypeVar("T")

DOWNLOADER_MODE = "Tubby Downloader"
INTELLIGENCE_MODE = "Local Transcript Intelligence"
YOUTUBE_SOURCE = "YouTube link"
MEDIA_SOURCE = "Media file"
VIDEO_MODE = "Video"
AUDIO_MODE = "MP3 audio"
APP_ICON_NAME = "tubby_logo.png"


def _app_icon_path() -> Path | None:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(Path(bundle_root) / "public" / "logo" / APP_ICON_NAME)
    candidates.extend(
        (
            Path(__file__).resolve().parent.parent / "public" / "logo" / APP_ICON_NAME,
            Path(sys.prefix) / "share" / "tubby" / "logo" / APP_ICON_NAME,
        )
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


class TubbyApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title(f"Tubby {__version__}")
        self.geometry("960x760")
        self.minsize(820, 680)
        self._window_icon: PhotoImage | None = None
        self._apply_window_icon()
        if sys.platform == "win32":
            self.after(250, self._apply_window_icon)

        self.mode_var = ctk.StringVar(value=INTELLIGENCE_MODE)
        self.subtitle_var = ctk.StringVar(value="Local transcript intelligence")
        self.status_var = ctk.StringVar(value="Ready")

        self.download_url_var = ctk.StringVar()
        self.download_mode_var = ctk.StringVar(value=VIDEO_MODE)
        self.download_quality_var = ctk.StringVar(value="Best")
        self.download_output_var = ctk.StringVar(value=str(Path.home() / "Downloads"))

        self.intelligence_source_var = ctk.StringVar(value=YOUTUBE_SOURCE)
        self.youtube_url_var = ctk.StringVar()
        self.media_path_var = ctk.StringVar()
        self.source_label_var = ctk.StringVar(value="YouTube URL")
        self.language_var = ctk.StringVar(value="English")
        self.report_style_var = ctk.StringVar(value=DEFAULT_REPORT_STYLE)
        self.include_source_transcript_var = ctk.BooleanVar(value=False)
        self.model_var = ctk.StringVar(value=DEFAULT_MODEL)
        self.model_choice_var = ctk.StringVar(value=DEFAULT_MODEL)
        self.model_status_var = ctk.StringVar(value="Loading installed Ollama models...")
        self.whisper_model_var = ctk.StringVar(value=DEFAULT_WHISPER_MODEL)
        self.report_output_var = ctk.StringVar(
            value=str(Path.home() / "Downloads" / "Tubby Reports")
        )

        self._busy = False
        self._worker: threading.Thread | None = None
        self._report_path: Path | None = None
        self._download_path: Path | None = None
        self._ollama_models: dict[str, OllamaModel] = {}
        self._model_names_by_label: dict[str, str] = {}
        self._model_labels_by_name: dict[str, str] = {}
        self._model_refreshing = False
        self._selected_model_installed = False
        self._mode_info = {
            DOWNLOADER_MODE: "Ready for a media URL.",
            INTELLIGENCE_MODE: "Ready for a YouTube link or local media file.",
        }

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_content()
        self._build_activity_area()
        self._switch_mode(INTELLIGENCE_MODE)
        self.after(150, self._refresh_ollama_models)

    def _apply_window_icon(self) -> None:
        icon_path = _app_icon_path()
        if icon_path is None:
            return
        try:
            self._window_icon = PhotoImage(master=self, file=str(icon_path))
            self.iconphoto(True, self._window_icon)
        except (OSError, TclError):
            self._window_icon = None

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=28, pady=(22, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Tubby",
            font=ctk.CTkFont(size=30, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            textvariable=self.subtitle_var,
            text_color=("gray40", "gray70"),
            font=ctk.CTkFont(size=13),
        ).grid(row=1, column=0, pady=(2, 0), sticky="w")

        self.mode_switch = ctk.CTkSegmentedButton(
            header,
            values=[DOWNLOADER_MODE, INTELLIGENCE_MODE],
            variable=self.mode_var,
            command=self._switch_mode,
            width=440,
        )
        self.mode_switch.grid(row=0, column=1, rowspan=2, padx=(20, 0), sticky="e")

    def _build_content(self) -> None:
        self.content_host = ctk.CTkFrame(self, fg_color="transparent")
        self.content_host.grid(row=1, column=0, padx=28, pady=6, sticky="ew")
        self.content_host.grid_columnconfigure(0, weight=1)

        self.downloader_frame = self._build_downloader_frame(self.content_host)
        self.intelligence_frame = self._build_intelligence_frame(self.content_host)
        self.downloader_frame.grid(row=0, column=0, sticky="ew")
        self.intelligence_frame.grid(row=0, column=0, sticky="ew")

    def _build_downloader_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, corner_radius=8)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Media URL").grid(
            row=0, column=0, padx=(16, 12), pady=(16, 8), sticky="w"
        )
        self.download_url_entry = ctk.CTkEntry(
            frame,
            textvariable=self.download_url_var,
            placeholder_text="https://example.com/video",
        )
        self.download_url_entry.grid(
            row=0, column=1, columnspan=3, padx=(0, 16), pady=(16, 8), sticky="ew"
        )

        ctk.CTkLabel(frame, text="Download as").grid(
            row=1, column=0, padx=(16, 12), pady=8, sticky="w"
        )
        self.download_format_switch = ctk.CTkSegmentedButton(
            frame,
            values=[VIDEO_MODE, AUDIO_MODE],
            variable=self.download_mode_var,
            command=self._download_mode_changed,
            width=230,
        )
        self.download_format_switch.grid(row=1, column=1, padx=(0, 16), pady=8, sticky="w")

        ctk.CTkLabel(frame, text="Quality").grid(row=1, column=2, padx=(8, 12), pady=8, sticky="e")
        self.download_quality_menu = ctk.CTkOptionMenu(
            frame,
            values=list(VIDEO_QUALITY_OPTIONS),
            variable=self.download_quality_var,
            width=150,
        )
        self.download_quality_menu.grid(row=1, column=3, padx=(0, 16), pady=8, sticky="e")

        ctk.CTkLabel(frame, text="Save folder").grid(
            row=2, column=0, padx=(16, 12), pady=(8, 16), sticky="w"
        )
        self.download_output_entry = ctk.CTkEntry(
            frame,
            textvariable=self.download_output_var,
        )
        self.download_output_entry.grid(
            row=2, column=1, columnspan=2, padx=(0, 8), pady=(8, 16), sticky="ew"
        )
        self.download_browse_button = ctk.CTkButton(
            frame,
            text="Browse",
            width=92,
            command=lambda: self._choose_directory(self.download_output_var),
        )
        self.download_browse_button.grid(row=2, column=3, padx=(0, 16), pady=(8, 16), sticky="e")

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=3, column=0, columnspan=4, padx=16, pady=(0, 16), sticky="ew")
        self.inspect_button = ctk.CTkButton(
            actions,
            text="Inspect",
            width=100,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self._inspect_download,
        )
        self.inspect_button.grid(row=0, column=0, padx=(0, 8))
        self.download_button = ctk.CTkButton(
            actions,
            text="Download",
            width=110,
            command=self._download,
        )
        self.download_button.grid(row=0, column=1, padx=(0, 8))
        self.open_download_button = ctk.CTkButton(
            actions,
            text="Open File",
            width=105,
            state="disabled",
            command=self._open_download,
        )
        self.open_download_button.grid(row=0, column=2)
        return frame

    def _build_intelligence_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, corner_radius=8)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Transcript source").grid(
            row=0, column=0, padx=(16, 12), pady=(16, 8), sticky="w"
        )
        self.source_switch = ctk.CTkSegmentedButton(
            frame,
            values=[YOUTUBE_SOURCE, MEDIA_SOURCE],
            variable=self.intelligence_source_var,
            command=self._source_changed,
            width=290,
        )
        self.source_switch.grid(
            row=0, column=1, columnspan=3, padx=(0, 16), pady=(16, 8), sticky="w"
        )

        ctk.CTkLabel(frame, textvariable=self.source_label_var).grid(
            row=1, column=0, padx=(16, 12), pady=8, sticky="w"
        )
        self.source_entry = ctk.CTkEntry(
            frame,
            textvariable=self.youtube_url_var,
            placeholder_text="https://www.youtube.com/watch?v=...",
        )
        self.source_entry.grid(row=1, column=1, columnspan=2, padx=(0, 8), pady=8, sticky="ew")
        self.select_file_button = ctk.CTkButton(
            frame,
            text="Select File",
            width=100,
            state="disabled",
            command=self._choose_media_file,
        )
        self.select_file_button.grid(row=1, column=3, padx=(0, 16), pady=8, sticky="e")

        ctk.CTkLabel(frame, text="Report language").grid(
            row=2, column=0, padx=(16, 12), pady=8, sticky="w"
        )
        self.language_menu = ctk.CTkOptionMenu(
            frame,
            values=list(LANGUAGE_OPTIONS),
            variable=self.language_var,
            width=190,
        )
        self.language_menu.grid(row=2, column=1, padx=(0, 16), pady=8, sticky="w")

        ctk.CTkLabel(frame, text="Output style").grid(
            row=2, column=2, padx=(8, 12), pady=8, sticky="e"
        )
        self.report_style_menu = ctk.CTkOptionMenu(
            frame,
            values=list(REPORT_STYLE_OPTIONS),
            variable=self.report_style_var,
            width=170,
        )
        self.report_style_menu.grid(row=2, column=3, padx=(0, 16), pady=8, sticky="e")

        ctk.CTkLabel(frame, text="Ollama model").grid(
            row=3, column=0, padx=(16, 12), pady=8, sticky="w"
        )
        model_controls = ctk.CTkFrame(frame, fg_color="transparent")
        model_controls.grid(
            row=3,
            column=1,
            columnspan=3,
            padx=(0, 16),
            pady=8,
            sticky="ew",
        )
        model_controls.grid_columnconfigure(0, weight=1)
        self.model_menu = ctk.CTkOptionMenu(
            model_controls,
            values=[DEFAULT_MODEL],
            variable=self.model_choice_var,
            command=self._model_changed,
            width=500,
            dynamic_resizing=False,
            state="disabled",
        )
        self.model_menu.grid(row=0, column=0, sticky="ew")
        self.refresh_models_button = ctk.CTkButton(
            model_controls,
            text="Refresh",
            width=70,
            command=self._refresh_ollama_models,
        )
        self.refresh_models_button.grid(row=0, column=1, padx=(8, 0))

        ctk.CTkLabel(frame, text="Speech model").grid(
            row=5, column=0, padx=(16, 12), pady=8, sticky="w"
        )
        self.whisper_model_menu = ctk.CTkOptionMenu(
            frame,
            values=list(WHISPER_MODEL_OPTIONS),
            variable=self.whisper_model_var,
            width=170,
            state="disabled",
        )
        self.whisper_model_menu.grid(row=5, column=1, padx=(0, 16), pady=8, sticky="w")

        self.model_status_label = ctk.CTkLabel(
            frame,
            textvariable=self.model_status_var,
            anchor="w",
            justify="left",
            wraplength=720,
            text_color=("gray35", "gray72"),
        )
        self.model_status_label.grid(
            row=4,
            column=0,
            columnspan=4,
            padx=16,
            pady=(0, 4),
            sticky="ew",
        )

        ctk.CTkLabel(frame, text="PDF options").grid(
            row=5, column=2, padx=(8, 12), pady=8, sticky="e"
        )
        self.include_source_transcript_switch = ctk.CTkSwitch(
            frame,
            text="Add Raw Source Transcript",
            variable=self.include_source_transcript_var,
            onvalue=True,
            offvalue=False,
        )
        self.include_source_transcript_switch.grid(
            row=5,
            column=3,
            padx=(0, 16),
            pady=8,
            sticky="w",
        )

        ctk.CTkLabel(frame, text="Save folder").grid(
            row=6, column=0, padx=(16, 12), pady=(8, 16), sticky="w"
        )
        self.report_output_entry = ctk.CTkEntry(frame, textvariable=self.report_output_var)
        self.report_output_entry.grid(
            row=6, column=1, columnspan=2, padx=(0, 8), pady=(8, 16), sticky="ew"
        )
        self.report_browse_button = ctk.CTkButton(
            frame,
            text="Browse",
            width=92,
            command=lambda: self._choose_directory(self.report_output_var),
        )
        self.report_browse_button.grid(row=6, column=3, padx=(0, 16), pady=(8, 16), sticky="e")

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=7, column=0, columnspan=4, padx=16, pady=(0, 16), sticky="ew")
        self.analyze_button = ctk.CTkButton(
            actions,
            text="Create PDF",
            command=self._analyze,
            width=120,
        )
        self.analyze_button.grid(row=0, column=0, padx=(0, 8))
        self.open_report_button = ctk.CTkButton(
            actions,
            text="Open PDF",
            command=self._open_report,
            state="disabled",
            width=110,
        )
        self.open_report_button.grid(row=0, column=1)
        return frame

    def _build_activity_area(self) -> None:
        self.info_box = ctk.CTkTextbox(self, corner_radius=8, wrap="word")
        self.info_box.grid(row=2, column=0, padx=28, pady=8, sticky="nsew")

        activity = ctk.CTkFrame(self, fg_color="transparent")
        activity.grid(row=3, column=0, padx=28, pady=(4, 0), sticky="ew")
        activity.grid_columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(activity)
        self.progress.set(0)
        self.progress.grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            anchor="w",
            text_color=("gray35", "gray72"),
        ).grid(row=4, column=0, padx=28, pady=(6, 18), sticky="ew")

    def _switch_mode(self, selected_mode: str) -> None:
        if self._busy:
            return
        if selected_mode == DOWNLOADER_MODE:
            self.intelligence_frame.grid_remove()
            self.downloader_frame.grid()
            self.subtitle_var.set("Downloader")
            self.download_url_entry.focus_set()
        else:
            self.downloader_frame.grid_remove()
            self.intelligence_frame.grid()
            self.subtitle_var.set("Local transcript intelligence")
            self.source_entry.focus_set()
        self._set_info_text(self._mode_info[selected_mode], remember=False)
        self._set_progress(0, "Ready")

    def _source_changed(self, source: str) -> None:
        local_file = source == MEDIA_SOURCE
        if local_file:
            self.source_label_var.set("Audio / video file")
            self.source_entry.configure(
                textvariable=self.media_path_var,
                placeholder_text="Choose a local audio or video file",
            )
        else:
            self.source_label_var.set("YouTube URL")
            self.source_entry.configure(
                textvariable=self.youtube_url_var,
                placeholder_text="https://www.youtube.com/watch?v=...",
            )
        state = "disabled" if self._busy else "normal"
        self.select_file_button.configure(state=state if local_file else "disabled")
        self.whisper_model_menu.configure(state=state if local_file else "disabled")
        if self.mode_var.get() == INTELLIGENCE_MODE:
            self.source_entry.focus_set()

    def _download_mode_changed(self, selected_mode: str) -> None:
        values = AUDIO_QUALITY_OPTIONS if selected_mode == AUDIO_MODE else VIDEO_QUALITY_OPTIONS
        self.download_quality_menu.configure(values=list(values))
        self.download_quality_var.set("Best")

    def _refresh_ollama_models(self) -> None:
        if self._busy or self._model_refreshing:
            return
        self._model_refreshing = True
        self.model_status_var.set("Loading installed Ollama models...")
        self.model_status_label.configure(text_color=("gray35", "gray72"))
        self.model_status_label.grid()
        self.model_menu.configure(state="disabled")
        self.refresh_models_button.configure(state="disabled")
        self.analyze_button.configure(state="disabled")

        def runner() -> None:
            try:
                models = list_installed_models()
            except OllamaModelError as exc:
                message = str(exc)
                self.after(0, lambda message=message: self._model_refresh_failed(message))
            except Exception as exc:
                message = f"Could not load Ollama models: {exc}"
                self.after(0, lambda message=message: self._model_refresh_failed(message))
            else:
                self.after(0, lambda models=models: self._models_loaded(models))

        threading.Thread(target=runner, daemon=True).start()

    def _models_loaded(self, models: tuple[OllamaModel, ...]) -> None:
        self._model_refreshing = False
        report_models = ordered_report_models(models)
        self._ollama_models = {model.name: model for model in report_models}
        self._model_names_by_label = {}
        self._model_labels_by_name = {}
        self.refresh_models_button.configure(state="normal" if not self._busy else "disabled")

        if not report_models:
            self._selected_model_installed = False
            self.model_menu.configure(values=[DEFAULT_MODEL], state="disabled")
            self.model_var.set(DEFAULT_MODEL)
            self.model_choice_var.set(DEFAULT_MODEL)
            self._set_model_status(
                "No installed Ollama model can generate reports. Run a Tubby setup script "
                "to choose a compact report model, then refresh.",
                error=True,
            )
            self.analyze_button.configure(state="disabled")
            return

        selected = choose_preferred_model(report_models, self.model_var.get())
        if selected is None:
            return
        labels = [model_selector_label(model) for model in report_models]
        self._model_names_by_label = {
            label: model.name for label, model in zip(labels, report_models, strict=True)
        }
        self._model_labels_by_name = {
            model_name: label for label, model_name in self._model_names_by_label.items()
        }
        self.model_menu.configure(
            values=labels,
            state="normal" if not self._busy else "disabled",
        )
        self.model_var.set(selected.name)
        self.model_choice_var.set(self._model_labels_by_name[selected.name])
        self._model_changed(selected.name)

    def _model_refresh_failed(self, message: str) -> None:
        self._model_refreshing = False
        self._ollama_models = {}
        self._model_names_by_label = {}
        self._model_labels_by_name = {}
        self._selected_model_installed = False
        self.model_menu.configure(state="disabled")
        self.refresh_models_button.configure(state="normal" if not self._busy else "disabled")
        self.analyze_button.configure(state="disabled")
        self._set_model_status(message, error=True)

    def _model_changed(self, selected_value: str) -> None:
        selected_model = self._model_names_by_label.get(selected_value, selected_value)
        model = self._ollama_models.get(selected_model)
        self._selected_model_installed = model is not None
        if model is None:
            self.analyze_button.configure(state="disabled")
            return

        self.model_var.set(model.name)
        display_label = self._model_labels_by_name.get(model.name)
        if display_label is not None:
            self.model_choice_var.set(display_label)

        try:
            save_preferred_model(model.name)
        except OSError:
            pass

        support = model.language_support
        if support == ModelLanguageSupport.ENGLISH_ONLY:
            self.language_var.set("English")
            self.language_menu.configure(values=["English"], state="disabled")
        else:
            self.language_menu.configure(
                values=list(LANGUAGE_OPTIONS),
                state="disabled" if self._busy else "normal",
            )

        warning = report_language_warning(model)
        details = model_selector_details(model)
        if warning:
            self._set_model_status(f"{details}\nWarning: {warning}", warning=True)
        else:
            self._set_model_status(details)

        self.analyze_button.configure(
            state="normal" if self._selected_model_installed and not self._busy else "disabled"
        )

    def _set_model_status(
        self,
        message: str,
        *,
        error: bool = False,
        warning: bool = False,
    ) -> None:
        if error:
            color = ("#A02828", "#FF8A80")
        elif warning:
            color = ("#8A5A00", "#E8B44C")
        else:
            color = ("gray35", "gray72")
        self.model_status_var.set(message)
        self.model_status_label.configure(text_color=color)
        self.model_status_label.grid()

    def _choose_directory(self, variable: ctk.StringVar) -> None:
        initial = Path(variable.get()).expanduser()
        directory = filedialog.askdirectory(
            initialdir=str(initial if initial.exists() else Path.home())
        )
        if directory:
            variable.set(directory)

    def _choose_media_file(self) -> None:
        current = Path(self.media_path_var.get()).expanduser()
        initial_dir = current.parent if current.is_file() else Path.home()
        patterns = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_MEDIA_EXTENSIONS))
        selected = filedialog.askopenfilename(
            initialdir=str(initial_dir),
            filetypes=[("Audio and video", patterns), ("All files", "*.*")],
        )
        if selected:
            self.media_path_var.set(selected)

    def _inspect_download(self) -> None:
        url = self._validated_download_url()
        if url is None:
            return
        mode, quality = self._download_selection()
        self._start_loader("Reading media information...")
        self._set_info_text("Inspecting the selected URL...")
        self._run_background(
            lambda: fetch_video_info(url),
            lambda info: self._inspection_finished(info.summary_lines(mode, quality, has_ffmpeg())),
        )

    def _inspection_finished(self, summary_lines: list[str]) -> None:
        self._set_progress(1, "Media information loaded")
        self._set_info_text("\n".join(summary_lines))

    def _download(self) -> None:
        url = self._validated_download_url()
        if url is None:
            return
        output = self.download_output_var.get().strip()
        if not output:
            messagebox.showerror("Tubby", "Choose a download folder.")
            return

        mode, quality = self._download_selection()
        self._download_path = None
        self.open_download_button.configure(state="disabled")
        self.progress.set(0)
        self._set_info_text("Preparing download...")
        self._start_loader("Reading media formats...")
        self._run_background(
            lambda: download_media(
                url=url,
                output_dir=output,
                mode=mode,
                quality=quality,
                progress_hook=self._download_progress,
            ),
            self._download_finished,
        )

    def _download_selection(self) -> tuple[str, str]:
        mode = "audio" if self.download_mode_var.get() == AUDIO_MODE else "video"
        return mode, self.download_quality_var.get()

    def _validated_download_url(self) -> str | None:
        url = self.download_url_var.get().strip()
        if not url:
            messagebox.showerror("Tubby", "Enter a media URL first.")
            return None
        if not url.casefold().startswith(("https://", "http://")):
            messagebox.showerror("Tubby", "Enter a complete URL beginning with https://.")
            return None
        return url

    def _download_progress(self, event: dict[str, object]) -> None:
        status = event.get("status")
        if status == "downloading":
            downloaded = event.get("downloaded_bytes")
            total = event.get("total_bytes") or event.get("total_bytes_estimate")
            ratio, text = format_download_status(
                downloaded,
                total,
                event.get("speed"),
                event.get("eta"),
            )
            self.after(0, lambda ratio=ratio, text=text: self._set_progress(ratio, text))
        elif status == "finished":
            self.after(0, lambda: self._start_loader("Processing downloaded media..."))

    def _download_finished(self, path: Path) -> None:
        self._download_path = path
        self.open_download_button.configure(state="normal")
        self._set_progress(1, f"Saved download to {path}")
        self._set_info_text(f"Download complete.\n\nSaved to:\n{path}")

    def _analyze(self) -> None:
        source_mode = self.intelligence_source_var.get()
        source = (
            self.media_path_var.get().strip()
            if source_mode == MEDIA_SOURCE
            else self.youtube_url_var.get().strip()
        )
        language = self.language_var.get().strip() or "English"
        model = self.model_var.get().strip()
        report_style = self.report_style_var.get().strip() or DEFAULT_REPORT_STYLE
        whisper_model = self.whisper_model_var.get().strip() or DEFAULT_WHISPER_MODEL
        include_source_transcript = bool(self.include_source_transcript_var.get())
        output = self.report_output_var.get().strip()

        if not source:
            message = (
                "Choose an audio or video file first."
                if source_mode == MEDIA_SOURCE
                else "Enter a YouTube URL first."
            )
            messagebox.showerror("Tubby", message)
            return
        if source_mode == YOUTUBE_SOURCE and not source.casefold().startswith(
            ("https://", "http://")
        ):
            messagebox.showerror("Tubby", "Enter a complete YouTube URL beginning with https://.")
            return
        if not model:
            messagebox.showerror("Tubby", "Select an installed Ollama model.")
            return
        if not self._selected_model_installed or model not in self._ollama_models:
            messagebox.showerror(
                "Tubby",
                "The selected Ollama model is not available. Start Ollama and refresh the list.",
            )
            return
        if not output:
            messagebox.showerror("Tubby", "Choose a folder for the PDF report.")
            return

        self._report_path = None
        self.open_report_button.configure(state="disabled")
        self.progress.set(0)
        self._set_info_text("Starting transcript intelligence...")
        self._start_loader(
            "Transcribing the selected media..."
            if source_mode == MEDIA_SOURCE
            else "Reading the YouTube transcript..."
        )

        def work() -> AnalysisResult:
            if source_mode == MEDIA_SOURCE:
                return analyze_media_to_pdf(
                    media_path=source,
                    output_dir=output,
                    output_language=language,
                    model=model,
                    report_style=report_style,
                    whisper_model=whisper_model,
                    progress=self._report_progress,
                    include_source_transcript=include_source_transcript,
                )
            return analyze_youtube_to_pdf(
                url=source,
                output_dir=output,
                output_language=language,
                model=model,
                report_style=report_style,
                progress=self._report_progress,
                include_source_transcript=include_source_transcript,
            )

        self._run_background(work, self._analysis_finished)

    def _run_background(self, work: Callable[[], T], on_success: Callable[[T], None]) -> bool:
        if self._busy:
            messagebox.showinfo("Tubby", "Another task is already running.")
            return False

        self._set_busy(True)

        def runner() -> None:
            try:
                result = work()
            except (TranscriptError, OllamaError, PdfReportError, TubbyError) as exc:
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

    def _report_progress(self, message: str) -> None:
        self.after(0, lambda message=message: self._start_loader(message))

    def _analysis_finished(self, result: AnalysisResult) -> None:
        self._report_path = result.pdf_path
        self.open_report_button.configure(state="normal")
        self._set_progress(1, f"Saved PDF to {result.pdf_path}")

        details = [
            result.analysis.report_title,
            result.analysis.executive_summary,
            "",
            f"Source: {result.transcript.title}",
            f"Transcript: {result.transcript.transcript_source_label}",
            f"Edition: {self.report_style_var.get()}",
            f"Report: {result.pdf_path}",
        ]
        self._set_info_text("\n".join(item for item in details if item is not None))

    def _show_error(self, message: str) -> None:
        self._stop_loader()
        self.status_var.set("Task failed")
        self._set_info_text(message)
        messagebox.showerror("Tubby", message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        widgets = (
            self.mode_switch,
            self.download_url_entry,
            self.download_format_switch,
            self.download_quality_menu,
            self.download_output_entry,
            self.download_browse_button,
            self.inspect_button,
            self.download_button,
            self.source_switch,
            self.source_entry,
            self.language_menu,
            self.report_style_menu,
            self.include_source_transcript_switch,
            self.model_menu,
            self.refresh_models_button,
            self.report_output_entry,
            self.report_browse_button,
            self.analyze_button,
        )
        for widget in widgets:
            widget.configure(state=state)

        if busy:
            self.select_file_button.configure(state="disabled")
            self.whisper_model_menu.configure(state="disabled")
            self.open_download_button.configure(state="disabled")
            self.open_report_button.configure(state="disabled")
        else:
            self._source_changed(self.intelligence_source_var.get())
            if self._ollama_models:
                self._model_changed(self.model_var.get())
            else:
                self.analyze_button.configure(state="disabled")
                self.refresh_models_button.configure(
                    state="disabled" if self._model_refreshing else "normal"
                )
            self.open_download_button.configure(
                state="normal"
                if self._download_path is not None and self._download_path.exists()
                else "disabled"
            )
            self.open_report_button.configure(
                state="normal"
                if self._report_path is not None and self._report_path.exists()
                else "disabled"
            )

    def _start_loader(self, text: str) -> None:
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.status_var.set(text)

    def _stop_loader(self) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")

    def _set_progress(self, ratio: float, text: str) -> None:
        self._stop_loader()
        self.progress.set(max(0.0, min(1.0, ratio)))
        self.status_var.set(text)

    def _set_info_text(self, text: str, remember: bool = True) -> None:
        if remember:
            self._mode_info[self.mode_var.get()] = text
        self.info_box.configure(state="normal")
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", text)
        self.info_box.configure(state="disabled")

    def _open_download(self) -> None:
        if self._download_path is None or not self._download_path.exists():
            messagebox.showerror("Tubby", "The downloaded file could not be found.")
            return
        self._open_path(self._download_path)

    def _open_report(self) -> None:
        if self._report_path is None or not self._report_path.exists():
            messagebox.showerror("Tubby", "The generated PDF could not be found.")
            return
        self._open_path(self._report_path)

    def _open_path(self, path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("Tubby", f"Could not open the file: {exc}")


def main() -> int:
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = TubbyApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

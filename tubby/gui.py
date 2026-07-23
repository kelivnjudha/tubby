from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, TypeVar

import customtkinter as ctk

from tubby import __version__
from tubby.languages import LANGUAGE_OPTIONS
from tubby.local_ai import DEFAULT_MODEL, OllamaError
from tubby.pdf_report import PdfReportError
from tubby.transcript import TranscriptError
from tubby.workflow import AnalysisResult, analyze_youtube_to_pdf

T = TypeVar("T")


class TubbyApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title(f"Tubby {__version__}")
        self.geometry("840x640")
        self.minsize(720, 580)

        self.url_var = ctk.StringVar()
        self.language_var = ctk.StringVar(value="English")
        self.model_var = ctk.StringVar(value=DEFAULT_MODEL)
        self.output_var = ctk.StringVar(value=str(Path.home() / "Downloads" / "Tubby Reports"))
        self.status_var = ctk.StringVar(value="Ready")
        self._worker: threading.Thread | None = None
        self._report_path: Path | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=28, pady=(24, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Tubby",
            font=ctk.CTkFont(size=30, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Local transcript intelligence",
            text_color=("gray40", "gray70"),
            font=ctk.CTkFont(size=13),
        ).grid(row=1, column=0, pady=(2, 0), sticky="w")

        form = ctk.CTkFrame(self, corner_radius=8)
        form.grid(row=1, column=0, padx=28, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="YouTube URL").grid(
            row=0,
            column=0,
            padx=(16, 12),
            pady=(16, 8),
            sticky="w",
        )
        self.url_entry = ctk.CTkEntry(
            form,
            textvariable=self.url_var,
            placeholder_text="https://www.youtube.com/watch?v=...",
        )
        self.url_entry.grid(
            row=0,
            column=1,
            columnspan=3,
            padx=(0, 16),
            pady=(16, 8),
            sticky="ew",
        )

        ctk.CTkLabel(form, text="Report language").grid(
            row=1,
            column=0,
            padx=(16, 12),
            pady=8,
            sticky="w",
        )
        self.language_menu = ctk.CTkOptionMenu(
            form,
            values=list(LANGUAGE_OPTIONS),
            variable=self.language_var,
            width=190,
        )
        self.language_menu.grid(row=1, column=1, padx=(0, 16), pady=8, sticky="w")

        ctk.CTkLabel(form, text="Ollama model").grid(
            row=1,
            column=2,
            padx=(8, 12),
            pady=8,
            sticky="e",
        )
        self.model_entry = ctk.CTkEntry(
            form,
            textvariable=self.model_var,
            width=170,
        )
        self.model_entry.grid(row=1, column=3, padx=(0, 16), pady=8, sticky="e")

        ctk.CTkLabel(form, text="Save folder").grid(
            row=2,
            column=0,
            padx=(16, 12),
            pady=(8, 16),
            sticky="w",
        )
        self.output_entry = ctk.CTkEntry(form, textvariable=self.output_var)
        self.output_entry.grid(
            row=2,
            column=1,
            columnspan=2,
            padx=(0, 8),
            pady=(8, 16),
            sticky="ew",
        )
        self.browse_button = ctk.CTkButton(
            form,
            text="Browse",
            width=92,
            command=self._choose_output,
        )
        self.browse_button.grid(row=2, column=3, padx=(0, 16), pady=(8, 16), sticky="e")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, padx=28, pady=(8, 4), sticky="ew")
        actions.grid_columnconfigure(2, weight=1)

        self.analyze_button = ctk.CTkButton(
            actions,
            text="Create PDF",
            command=self._analyze,
            width=120,
        )
        self.analyze_button.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.open_button = ctk.CTkButton(
            actions,
            text="Open PDF",
            command=self._open_report,
            state="disabled",
            width=110,
        )
        self.open_button.grid(row=0, column=1, padx=(0, 12), sticky="w")

        self.progress = ctk.CTkProgressBar(actions)
        self.progress.set(0)
        self.progress.grid(row=0, column=2, sticky="ew")

        self.info_box = ctk.CTkTextbox(self, corner_radius=8, wrap="word")
        self.info_box.grid(row=3, column=0, padx=28, pady=8, sticky="nsew")
        self._set_info_text("Ready for a YouTube link.")

        status = ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            anchor="w",
            text_color=("gray35", "gray72"),
        )
        status.grid(row=4, column=0, padx=28, pady=(4, 18), sticky="ew")

        self.url_entry.focus_set()

    def _choose_output(self) -> None:
        initial = Path(self.output_var.get()).expanduser()
        directory = filedialog.askdirectory(
            initialdir=str(initial if initial.exists() else Path.home())
        )
        if directory:
            self.output_var.set(directory)

    def _analyze(self) -> None:
        url = self.url_var.get().strip()
        language = self.language_var.get().strip() or "English"
        model = self.model_var.get().strip()
        output = self.output_var.get().strip()

        if not url:
            messagebox.showerror("Tubby", "Enter a YouTube URL first.")
            return
        if not url.casefold().startswith(("https://", "http://")):
            messagebox.showerror("Tubby", "Enter a complete YouTube URL beginning with https://.")
            return
        if not model:
            messagebox.showerror("Tubby", "Enter an Ollama model name.")
            return
        if not output:
            messagebox.showerror("Tubby", "Choose a folder for the PDF report.")
            return

        self._report_path = None
        self.open_button.configure(state="disabled")
        self.progress.set(0)
        self._set_info_text("Starting transcript analysis...")
        self._start_loader("Reading the YouTube transcript...")

        self._run_background(
            lambda: analyze_youtube_to_pdf(
                url=url,
                output_dir=output,
                output_language=language,
                model=model,
                progress=self._report_progress,
            ),
            self._analysis_finished,
        )

    def _run_background(self, work: Callable[[], T], on_success: Callable[[T], None]) -> bool:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Tubby", "An analysis is already running.")
            return False

        self._set_busy(True)

        def runner() -> None:
            try:
                result = work()
            except (TranscriptError, OllamaError, PdfReportError) as exc:
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
        self._set_progress(1, f"Saved PDF to {result.pdf_path}")
        self.open_button.configure(state="normal")

        caption_kind = (
            "automatic captions" if result.transcript.is_auto_generated else "manual captions"
        )
        details = [
            result.analysis.executive_summary,
            "",
            f"Video: {result.transcript.title}",
            f"Transcript: {result.transcript.language_name} ({caption_kind})",
            f"Report: {result.pdf_path}",
        ]
        self._set_info_text("\n".join(details))

    def _show_error(self, message: str) -> None:
        self._stop_loader()
        self.status_var.set("Analysis failed")
        self._set_info_text(message)
        messagebox.showerror("Tubby", message)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.analyze_button.configure(state=state)
        self.browse_button.configure(state=state)
        self.url_entry.configure(state=state)
        self.language_menu.configure(state=state)
        self.model_entry.configure(state=state)
        self.output_entry.configure(state=state)

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

    def _open_report(self) -> None:
        if self._report_path is None or not self._report_path.exists():
            messagebox.showerror("Tubby", "The generated PDF could not be found.")
            return

        try:
            if sys.platform == "win32":
                os.startfile(self._report_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self._report_path)])
            else:
                subprocess.Popen(["xdg-open", str(self._report_path)])
        except OSError as exc:
            messagebox.showerror("Tubby", f"Could not open the PDF: {exc}")


def main() -> int:
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = TubbyApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

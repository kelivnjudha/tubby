from __future__ import annotations

import threading
from collections.abc import Callable

import customtkinter as ctk

from tubby.media_transcript import DEFAULT_WHISPER_MODEL, WHISPER_MODEL_OPTIONS
from tubby.ollama_models import (
    DEFAULT_MODEL,
    MODEL_RECOMMENDATIONS,
    ModelRecommendation,
    OllamaModel,
    find_installed_model,
    model_selector_details,
    models_match,
)
from tubby.runtime_setup import (
    RuntimeStatus,
    SetupError,
    SetupOptions,
    SetupProgress,
    SetupResult,
    inspect_runtime,
    provision_runtime,
)

SPEECH_MODEL_DETAILS = {
    "tiny": "Fastest | about 75 MB | useful for clear, short recordings",
    "base": "Fast | about 145 MB | better accuracy than tiny",
    "small": "Recommended | about 465 MB | balanced speed and accuracy",
    "medium": "High accuracy | about 1.5 GB | slower on CPU",
    "large-v3": "Most accurate | about 3 GB | highest memory use",
    "turbo": "Fast high accuracy | about 1.6 GB | best on capable hardware",
}


class SetupDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master: ctk.CTk,
        on_complete: Callable[[SetupResult], None],
        *,
        preferred_model: str = DEFAULT_MODEL,
        speech_model: str = DEFAULT_WHISPER_MODEL,
    ) -> None:
        super().__init__(master)
        self.title("Prepare Tubby")
        self.geometry("720x650")
        self.minsize(660, 610)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._on_complete = on_complete
        self._busy = False
        self._status: RuntimeStatus | None = None
        self._preferred_model = preferred_model
        self._model_names_by_label: dict[str, str] = {}
        self._recommendations_by_name = {
            recommendation.name: recommendation for recommendation in MODEL_RECOMMENDATIONS
        }

        self.model_choice_var = ctk.StringVar()
        self.speech_model_var = ctk.StringVar(value=speech_model)
        self.model_details_var = ctk.StringVar()
        self.speech_details_var = ctk.StringVar(
            value=SPEECH_MODEL_DETAILS.get(speech_model, "")
        )
        self.ollama_status_var = ctk.StringVar(value="Checking...")
        self.report_status_var = ctk.StringVar(value="Checking...")
        self.speech_status_var = ctk.StringVar(value="Checking...")
        self.ffmpeg_status_var = ctk.StringVar(value="Checking...")
        self.progress_status_var = ctk.StringVar(value="Checking local components...")

        self.grid_columnconfigure(0, weight=1)
        self._build_content()
        self._set_recommendation_choices()
        self.after(50, self._begin_scan)
        self.after(100, self._take_focus)

    def _build_content(self) -> None:
        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.grid(row=0, column=0, padx=24, pady=(22, 12), sticky="ew")
        heading.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            heading,
            text="Prepare Tubby",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            heading,
            text="Install local AI components and download the models you choose.",
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, pady=(3, 0), sticky="w")

        status_frame = ctk.CTkFrame(self, corner_radius=8)
        status_frame.grid(row=1, column=0, padx=24, pady=8, sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)
        status_rows = (
            ("Ollama", self.ollama_status_var),
            ("Report model", self.report_status_var),
            ("Speech model", self.speech_status_var),
            ("FFmpeg", self.ffmpeg_status_var),
        )
        for row, (label, variable) in enumerate(status_rows):
            ctk.CTkLabel(status_frame, text=label, font=ctk.CTkFont(weight="bold")).grid(
                row=row,
                column=0,
                padx=(14, 16),
                pady=(10 if row == 0 else 5, 10 if row == len(status_rows) - 1 else 5),
                sticky="w",
            )
            ctk.CTkLabel(
                status_frame,
                textvariable=variable,
                anchor="w",
                text_color=("gray35", "gray72"),
            ).grid(
                row=row,
                column=1,
                padx=(0, 14),
                pady=(10 if row == 0 else 5, 10 if row == len(status_rows) - 1 else 5),
                sticky="ew",
            )

        choices = ctk.CTkFrame(self, fg_color="transparent")
        choices.grid(row=2, column=0, padx=24, pady=(10, 4), sticky="ew")
        choices.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(choices, text="Report model", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.model_menu = ctk.CTkOptionMenu(
            choices,
            variable=self.model_choice_var,
            values=["Loading..."],
            command=self._model_changed,
            dynamic_resizing=False,
        )
        self.model_menu.grid(row=1, column=0, pady=(5, 4), sticky="ew")
        ctk.CTkLabel(
            choices,
            textvariable=self.model_details_var,
            anchor="w",
            justify="left",
            wraplength=650,
            text_color=("gray35", "gray72"),
        ).grid(row=2, column=0, pady=(0, 12), sticky="ew")

        ctk.CTkLabel(
            choices,
            text="Speech model",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=3, column=0, sticky="w")

        self.speech_menu = ctk.CTkOptionMenu(
            choices,
            variable=self.speech_model_var,
            values=list(WHISPER_MODEL_OPTIONS),
            command=self._speech_model_changed,
            width=180,
        )
        self.speech_menu.grid(row=4, column=0, pady=(5, 4), sticky="w")
        ctk.CTkLabel(
            choices,
            textvariable=self.speech_details_var,
            anchor="w",
            text_color=("gray35", "gray72"),
        ).grid(row=5, column=0, sticky="ew")

        activity = ctk.CTkFrame(self, fg_color="transparent")
        activity.grid(row=3, column=0, padx=24, pady=(12, 8), sticky="ew")
        activity.grid_columnconfigure(0, weight=1)
        self.progress_bar = ctk.CTkProgressBar(activity)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_status_label = ctk.CTkLabel(
            activity,
            textvariable=self.progress_status_var,
            anchor="w",
            justify="left",
            wraplength=650,
            text_color=("gray35", "gray72"),
        )
        self.progress_status_label.grid(row=1, column=0, pady=(6, 0), sticky="ew")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, padx=24, pady=(6, 22), sticky="e")
        self.later_button = ctk.CTkButton(
            actions,
            text="Later",
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self._close,
            width=92,
        )
        self.later_button.grid(row=0, column=0, padx=(0, 8))
        self.install_button = ctk.CTkButton(
            actions,
            text="Install & Prepare",
            command=self._begin_setup,
            width=150,
        )
        self.install_button.grid(row=0, column=1)

    def _take_focus(self) -> None:
        if not self.winfo_exists():
            return
        self.lift()
        self.focus_force()
        self.grab_set()

    def _set_recommendation_choices(self) -> None:
        labels: list[str] = []
        self._model_names_by_label = {}
        for recommendation in MODEL_RECOMMENDATIONS:
            label = self._recommendation_label(recommendation)
            labels.append(label)
            self._model_names_by_label[label] = recommendation.name
        self.model_menu.configure(values=labels)

        preferred_label = next(
            (
                label
                for label, name in self._model_names_by_label.items()
                if models_match(name, self._preferred_model)
            ),
            labels[0],
        )
        self.model_choice_var.set(preferred_label)
        self._model_changed(preferred_label)

    def _begin_scan(self) -> None:
        def runner() -> None:
            status = inspect_runtime(self.speech_model_var.get())
            self.after(0, lambda: self._scan_finished(status))

        threading.Thread(target=runner, daemon=True).start()

    def _scan_finished(self, status: RuntimeStatus) -> None:
        self._status = status
        self._update_status_rows(status)
        self._add_installed_model_choices(status.report_models)
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        if status.needs_setup:
            self.progress_status_var.set("Choose models, then install and prepare Tubby.")
        else:
            self.progress_status_var.set("All required local components are ready.")
            self.install_button.configure(text="Check & Prepare")

    def _add_installed_model_choices(self, models: tuple[OllamaModel, ...]) -> None:
        labels = list(self._model_names_by_label)
        for model in models:
            if any(models_match(model.name, name) for name in self._model_names_by_label.values()):
                continue
            label = f"Installed | {model.name}"
            labels.append(label)
            self._model_names_by_label[label] = model.name
        self.model_menu.configure(values=labels)

        preferred = find_installed_model(models, self._preferred_model)
        if preferred is None and models:
            preferred = models[0]
        if preferred is None:
            return
        selected_label = next(
            label
            for label, name in self._model_names_by_label.items()
            if models_match(name, preferred.name)
        )
        self.model_choice_var.set(selected_label)
        self._model_changed(selected_label)

    def _update_status_rows(self, status: RuntimeStatus) -> None:
        if status.ollama_running:
            ollama_status = "Running"
        elif status.ollama_executable is not None:
            ollama_status = "Installed, not running"
        else:
            ollama_status = "Not installed"
        self.ollama_status_var.set(ollama_status)

        report_count = len(status.report_models)
        self.report_status_var.set(
            f"{report_count} compatible model{'s' if report_count != 1 else ''} installed"
            if report_count
            else "No compatible model installed"
        )
        self.speech_status_var.set(
            f"{status.whisper_model} is ready"
            if status.whisper_ready
            else f"{status.whisper_model} requires download"
        )
        self.ffmpeg_status_var.set(
            "Ready" if status.ffmpeg_executable is not None else "Missing from this build"
        )

    def _model_changed(self, selected_label: str) -> None:
        model_name = self._model_names_by_label.get(selected_label, selected_label)
        recommendation = next(
            (
                value
                for name, value in self._recommendations_by_name.items()
                if models_match(name, model_name)
            ),
            None,
        )
        if recommendation is not None:
            details = (
                f"{recommendation.best_for.capitalize()}. "
                f"Language support: {recommendation.language_note}."
            )
            if recommendation.tradeoff:
                details += f" Tradeoff: {recommendation.tradeoff}."
            self.model_details_var.set(details)
            return

        model = next(
            (
                candidate
                for candidate in (self._status.report_models if self._status else ())
                if models_match(candidate.name, model_name)
            ),
            OllamaModel.inferred(model_name),
        )
        self.model_details_var.set(model_selector_details(model))

    def _speech_model_changed(self, selected_model: str) -> None:
        self.speech_details_var.set(SPEECH_MODEL_DETAILS.get(selected_model, ""))
        if not self._busy:
            self._begin_scan()

    def _begin_setup(self) -> None:
        if self._busy:
            return
        model = self._model_names_by_label.get(
            self.model_choice_var.get(), self.model_choice_var.get()
        )
        options = SetupOptions(
            report_model=model,
            whisper_model=self.speech_model_var.get(),
            prepare_speech_model=True,
        )
        self._set_busy(True)
        self._show_progress(SetupProgress("Starting setup..."))

        def runner() -> None:
            try:
                result = provision_runtime(options, self._thread_progress)
            except SetupError as exc:
                message = str(exc)
                self.after(0, lambda: self._setup_failed(message))
            except Exception as exc:
                message = f"Setup failed unexpectedly: {exc}"
                self.after(0, lambda: self._setup_failed(message))
            else:
                self.after(0, lambda: self._setup_finished(result))

        threading.Thread(target=runner, daemon=True).start()

    def _thread_progress(self, update: SetupProgress) -> None:
        self.after(0, lambda: self._show_progress(update))

    def _show_progress(self, update: SetupProgress) -> None:
        self.progress_status_var.set(update.message)
        self.progress_status_label.configure(text_color=("gray35", "gray72"))
        if update.ratio is None:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(max(0.0, min(1.0, update.ratio)))

    def _setup_finished(self, result: SetupResult) -> None:
        self._status = result.status
        self._update_status_rows(result.status)
        self._show_progress(SetupProgress("Tubby is ready.", 1.0))
        self._set_busy(False)
        self.install_button.configure(text="Done", command=self._close)
        self.later_button.grid_remove()
        self._on_complete(result)

    def _setup_failed(self, message: str) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_status_var.set(message)
        self.progress_status_label.configure(text_color=("#A02828", "#FF8A80"))
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.model_menu.configure(state=state)
        self.speech_menu.configure(state=state)
        self.install_button.configure(state=state)
        self.later_button.configure(state=state)

    def _close(self) -> None:
        if self._busy:
            return
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    @staticmethod
    def _recommendation_label(recommendation: ModelRecommendation) -> str:
        return (
            f"{recommendation.profile} | {recommendation.name} | "
            f"{recommendation.download_size}"
        )

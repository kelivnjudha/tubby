import tkinter as tk
from tkinter import messagebox
from pytube import YouTube
from tkinter.filedialog import askdirectory
import customtkinter
import shutil
import datetime
import os
import sys
from moviepy.editor import AudioFileClip
from pytube.exceptions import AgeRestrictedError

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()

        self.title("Tubby Version 0.2")
        self.minsize(600, 500)
        self.resizable(False, False)

        version = customtkinter.CTkLabel(
            master=self,
            text="Tubby version 0.2",
            fg_color="#575757",
            bg_color="#575757",
            corner_radius=10
        )
        version.place(relx=0.49, rely=0.95, anchor=tk.CENTER)

        self.link = customtkinter.CTkEntry(
            master=self,
            placeholder_text="Enter url",
            width=380,
            height=30,
            border_width=2,
            corner_radius=10,
        )

        self.link.place(relx=0.5, rely=0.1, anchor=tk.CENTER)

        videobutton = customtkinter.CTkButton(
            master=self,
            text="Download Video",
            command=lambda: self.show_video_info(self.link.get(), "video"),
            height=35,
            corner_radius=8,
        )
        videobutton.place(relx=0.07, rely=0.165)

        reloadbutton = customtkinter.CTkButton(
            master=self,
            text="Reload",
            command=self.restart_app,
            height=35,
            corner_radius=8,
        )
        reloadbutton.place(relx=0.5, rely=0.2, anchor=tk.CENTER)

        audiobutton = customtkinter.CTkButton(
            master=self,
            text="Download Audio",
            command=lambda: self.show_video_info(self.link.get(), "audio"),
            height=35,
            corner_radius=8,
        )
        audiobutton.place(relx=0.7, rely=0.165)

    def restart_app(self):
        self.destroy()
        os.execl(sys.executable, sys.executable, *sys.argv)

    def show_message_and_restart(self, title, message):
        messagebox.showinfo(title, message)
        self.restart_app()

    def show_video_info(self, url, download_type):
        try:
            yt = YouTube(url)
        except AgeRestrictedError:
            messagebox.showerror("Error", "This video is age-restricted and can't be accessed without logging in.")
            self.restart_app()
            return
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.restart_app()
            return

        info_frame = tk.Frame(self, height=200, width=500)
        info_frame.place(relx=0.5, rely=0.59, anchor=tk.CENTER)

        title_label = tk.Label(info_frame, text=f"Title: {yt.title}", wraplength=480)
        title_label.pack(pady=2)

        length_label = tk.Label(info_frame, text=f"Length: {str(datetime.timedelta(seconds=yt.length))}")
        length_label.pack(pady=2)

        views_label = tk.Label(info_frame, text=f"Views: {yt.views}")
        views_label.pack(pady=2)

        publish_label = tk.Label(info_frame, text=f"Publish Date: {yt.publish_date}")
        publish_label.pack(pady=2)

        cancel_button = tk.Button(info_frame, text="Cancel", command=info_frame.destroy)
        cancel_button.pack(side=tk.LEFT, padx=10, pady=10)

        if download_type == "video":
            continue_button = tk.Button(info_frame, text="Continue", command=lambda: [self.video_download(url), info_frame.destroy()])
        elif download_type == "audio":
            continue_button = tk.Button(info_frame, text="Continue", command=lambda: [self.audio_download(url), info_frame.destroy()])

        continue_button.pack(side=tk.RIGHT, padx=10, pady=10)

    def video_download(self, url):
        try:
            yt = YouTube(url)
        except AgeRestrictedError:
            messagebox.showerror("Error", "This video is age-restricted and can't be accessed without logging in.")
            self.restart_app()
            return
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.restart_app()
            return

        video_stream = yt.streams.filter(progressive=True, mime_type='video/mp4')

        if not video_stream:
            messagebox.showinfo("Tubby", "No video streams available for this URL")
            self.restart_app()
            return

        stream_frame = tk.Frame(self, height=200, width=500)
        stream_frame.place(relx=0.5, rely=0.59, anchor=tk.CENTER)

        canvas = tk.Canvas(stream_frame, height=300, width=345)
        scrollbar = tk.Scrollbar(stream_frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

        stream_list = tk.Frame(canvas)
        canvas.create_window((0, 0), window=stream_list, anchor=tk.NW)

        for i, stream in enumerate(video_stream):
            button_text = f"{stream.resolution} @ {stream.fps}fps"

            stream_button = customtkinter.CTkButton(
                master=stream_list,
                text=button_text,
                command=lambda stream=stream: self.download_selected_stream(stream),
                height=35,
                corner_radius=8,
                width=320
            )
            stream_button.pack(fill=tk.X, padx=10, pady=5)

        stream_list.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        self.stream_list = stream_list

    def download_selected_stream(self, stream):
        download_path = askdirectory()
        if not download_path:
            return
        try:
            stream.download(output_path=download_path)
            self.show_message_and_restart("Tubby", "Video downloaded successfully")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while downloading: {e}")
            self.restart_app()

    def audio_download(self, url):
        try:
            yt = YouTube(url)
        except AgeRestrictedError:
            messagebox.showerror("Error", "This video is age-restricted and can't be accessed without logging in.")
            self.restart_app()
            return
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.restart_app()
            return

        audio_stream = yt.streams.filter(only_audio=True)

        if not audio_stream:
            messagebox.showinfo("Tubby", "No audio streams available for this URL")
            self.restart_app()
            return

        stream_frame = tk.Frame(self, height=200, width=500)
        stream_frame.place(relx=0.5, rely=0.59, anchor=tk.CENTER)

        canvas = tk.Canvas(stream_frame, height=300, width=348)
        scrollbar = tk.Scrollbar(stream_frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

        stream_list = tk.Frame(canvas)
        canvas.create_window((0, 0), window=stream_list, anchor=tk.NW)

        for i, stream in enumerate(audio_stream):
            button_text = f"Audio - {stream.abr}"

            stream_button = customtkinter.CTkButton(
                master=stream_list,
                text=button_text,
                command=lambda stream=stream: self.download_audio_stream(stream),
                height=35,
                corner_radius=8,
                width=320
            )
            stream_button.pack(fill=tk.X, padx=10, pady=5)

        stream_list.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        self.stream_list = stream_list

    def download_audio_stream(self, stream):
        download_path = askdirectory()
        if not download_path:
            return
        try:
            audio_file = stream.download(output_path=download_path)
            base, ext = os.path.splitext(audio_file)
            new_file = base + '.mp3'
            audio_clip = AudioFileClip(audio_file)
            audio_clip.write_audiofile(new_file)
            audio_clip.close()
            os.remove(audio_file)
            self.show_message_and_restart("Tubby", "Audio downloaded successfully as MP3")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while downloading: {e}")
            self.restart_app()

if __name__ == "__main__":
    app = App()
    app.mainloop()

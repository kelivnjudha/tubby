#import require modules
import tkinter # for gui
import pytube # for yt video/ audio download
import humanize # for display file size with MB/GB etc
import customtkinter #for modern user interface
import shutil #for file moving and copying

from tkinter import * #from tkinter import everything
from tkinter import messagebox # from tkinter import messagebox for display errors
from pytube import YouTube
from tkinter.filedialog import askdirectory
from tkinter import messagebox

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
        version.place(relx=0.49,rely=0.95, anchor= CENTER)

###################### Entry #########################
        link = customtkinter.CTkEntry(
            master=self,
            placeholder_text="Enter url",
            width=380,
            height=30,
            border_width=2,
            corner_radius=10,
        )

        link.place(relx=0.5,rely=0.1, anchor=tkinter.CENTER)
###################### Video Button ##################
        videobutton = customtkinter.CTkButton(
            master=self,
            text="Download Video",
            command=lambda: self.video_download(link.get()),
            height=35,
            corner_radius=8,
            )
        videobutton.place(relx=0.2, rely=0.17)
##################### Audio Button ###################
        audiobutton = customtkinter.CTkButton(
            master=self,
            text="Download Audio",
            command=lambda: self.audio_download(link.get()),
            height=35,
            corner_radius=8,
        )
        audiobutton.place(relx=0.56,rely=0.17)

##################### Video Download ##################

    def video_download(self, url):
        index = -1
        try:
            yt=YouTube(url)
        except Exception as e:
            messagebox.showerror("Error",str(e))
        video_stream = yt.streams.filter(only_video=False, only_audio=False, mime_type='video/mp4')

        if not video_stream:
            messagebox.showinfo("Tubby", "No video streams available for this URL")
            return
        
        # Create a frame to hold the stream options and scrollbar
        stream_frame = Frame(self, height=200, width=500)
        stream_frame.place(relx=0.5, rely=0.59, anchor=CENTER)

        # Create a canvas to hold the frame and attach the scrollbar to the canvas
        canvas = Canvas(stream_frame, height=300, width=345)
        scrollbar = Scrollbar(stream_frame, orient=VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=1)

        # Create another frame to hold the stream buttons
        stream_list = Frame(canvas)
        canvas.create_window((0, 0), window=stream_list, anchor=NW)

        for i, stream in enumerate(video_stream):
            button_text = f"{stream.resolution} @ {stream.fps}fps"

            # Button for stream option
            stream_button = customtkinter.CTkButton(
                master=stream_list,  # <-- Fix: Use stream_list instead of self
                text=button_text,
                command=lambda stream=stream: self.download_selected_stream(stream),
                height=35,
                corner_radius=8,
                width=320
            )
            stream_button.pack(fill=X, padx=10, pady=5)

        # Update the canvas
        stream_list.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        self.stream_list = stream_list
    def download_selected_stream(self, stream):
        download_path = askdirectory()
        if not download_path:
            return
        try:
            stream.download(output_path=download_path)
            messagebox.showinfo("Tubby", "Video downloaded successfully")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while downloading: {e}")



    def audio_download(self, url):
        index = -1
        try:
            yt=YouTube(url)
        except Exception as e:
            messagebox.showerror("Error",str(e))
        video_stream = yt.streams.filter(only_audio=True, mime_type='audio/mp3')

        if not video_stream:
            messagebox.showinfo("Tubby", "No video streams available for this URL")
            return
        
        # Create a frame to hold the stream options and scrollbar
        stream_frame = Frame(self, height=200, width=500)
        stream_frame.place(relx=0.32, rely=0.5, anchor=CENTER)

        # Create a canvas to hold the frame and attach the scrollbar to the canvas
        canvas = Canvas(stream_frame, height=200, width=170)
        scrollbar = Scrollbar(stream_frame, orient=VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=1)

        # Create another frame to hold the stream buttons
        stream_list = Frame(canvas)
        canvas.create_window((0, 0), window=stream_list, anchor=NW)

        for i, stream in enumerate(video_stream):
            button_text = f"{stream.resolution} @ {stream.fps}fps"

            # Button for stream option
            stream_button = customtkinter.CTkButton(
                master=stream_list,  # <-- Fix: Use stream_list instead of self
                text=button_text,
                command=lambda stream=stream: self.download_selected_stream(stream),
                height=35,
                corner_radius=8,
            )
            stream_button.pack(fill=X, padx=10, pady=5)

        # Update the canvas
        stream_list.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        self.stream_list = stream_list


if __name__ == "__main__":
    app = App()
    app.mainloop()
import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from pytube import YouTube
from moviepy.editor import AudioFileClip
import datetime
import os

class TubbyApp(App):
    def build(self):
        self.title = "Tubby Version 0.2"

        self.layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        self.url_input = TextInput(hint_text="Enter YouTube URL", size_hint=(1, 0.1))
        self.layout.add_widget(self.url_input)

        self.button_layout = BoxLayout(size_hint=(1, 0.1), spacing=10)
        self.download_video_button = Button(text="Download Video", on_press=self.download_video)
        self.download_audio_button = Button(text="Download Audio", on_press=self.download_audio)
        self.button_layout.add_widget(self.download_video_button)
        self.button_layout.add_widget(self.download_audio_button)
        self.layout.add_widget(self.button_layout)

        self.reload_button = Button(text="Reload", size_hint=(1, 0.1), on_press=self.reload_app)
        self.layout.add_widget(self.reload_button)

        self.message_label = Label(text="", size_hint=(1, 0.1))
        self.layout.add_widget(self.message_label)

        return self.layout

    def reload_app(self, instance):
        self.url_input.text = ""
        self.message_label.text = ""

    def show_message(self, title, message):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        message_label = Label(text=message, size_hint=(1, 0.8), text_size=(None, None), halign='center')
        message_label.bind(width=lambda s, w: setattr(s, 'text_size', (w, None)))
        content.add_widget(message_label)
        ok_button = Button(text="OK", size_hint=(1, 0.2))
        content.add_widget(ok_button)
        popup = Popup(title=title, content=content, size_hint=(0.8, 0.8))
        ok_button.bind(on_press=popup.dismiss)
        popup.open()

    def download_video(self, instance):
        url = self.url_input.text
        if not url:
            self.show_message("Error", "Please enter a YouTube URL")
            return
        self.fetch_video_info(url, "video")

    def download_audio(self, instance):
        url = self.url_input.text
        if not url:
            self.show_message("Error", "Please enter a YouTube URL")
            return
        self.fetch_video_info(url, "audio")

    def fetch_video_info(self, url, download_type):
        try:
            yt = YouTube(url)
            video_info = {
                "title": yt.title,
                "length": str(datetime.timedelta(seconds=yt.length)),
                "views": yt.views,
                "publish_date": yt.publish_date,
                "streams": yt.streams
            }
            self.show_video_info_popup(video_info, download_type)
        except Exception as e:
            self.show_message("Error", str(e))

    def show_video_info_popup(self, video_info, download_type):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        title_label = Label(text=f"Title: {video_info['title']}", size_hint=(1, 0.2), text_size=(None, None), halign='center')
        title_label.bind(width=lambda s, w: setattr(s, 'text_size', (w, None)))
        length_label = Label(text=f"Length: {video_info['length']}", size_hint=(1, 0.2), text_size=(None, None), halign='center')
        length_label.bind(width=lambda s, w: setattr(s, 'text_size', (w, None)))
        views_label = Label(text=f"Views: {video_info['views']}", size_hint=(1, 0.2), text_size=(None, None), halign='center')
        views_label.bind(width=lambda s, w: setattr(s, 'text_size', (w, None)))
        publish_date_label = Label(text=f"Publish Date: {video_info['publish_date']}", size_hint=(1, 0.2), text_size=(None, None), halign='center')
        publish_date_label.bind(width=lambda s, w: setattr(s, 'text_size', (w, None)))
        
        content.add_widget(title_label)
        content.add_widget(length_label)
        content.add_widget(views_label)
        content.add_widget(publish_date_label)

        button_layout = BoxLayout(size_hint=(1, 0.2), spacing=10)
        continue_button = Button(text="Continue", on_press=lambda x: self.show_resolution_popup(video_info['streams'], download_type))
        cancel_button = Button(text="Cancel", on_press=lambda x: self.video_info_popup.dismiss())
        button_layout.add_widget(continue_button)
        button_layout.add_widget(cancel_button)

        content.add_widget(button_layout)

        self.video_info_popup = Popup(title="Video Information", content=content, size_hint=(0.8, 0.8))
        self.video_info_popup.open()

    def show_resolution_popup(self, streams, download_type):
        self.download_type = download_type
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        scrollview = ScrollView(size_hint=(1, 0.8))
        grid_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)
        grid_layout.bind(minimum_height=grid_layout.setter('height'))

        if download_type == "video":
            video_streams = streams.filter(progressive=True, mime_type='video/mp4')
            for stream in video_streams:
                btn = Button(text=f"{stream.resolution} @ {stream.fps}fps", size_hint_y=None, height=40, on_press=lambda btn, stream=stream: self.on_resolution_selection(stream))
                grid_layout.add_widget(btn)
        elif download_type == "audio":
            audio_streams = streams.filter(only_audio=True)
            for stream in audio_streams:
                btn = Button(text=f"Audio - {stream.abr}", size_hint_y=None, height=40, on_press=lambda btn, stream=stream: self.on_resolution_selection(stream))
                grid_layout.add_widget(btn)

        scrollview.add_widget(grid_layout)
        layout.add_widget(scrollview)

        cancel_button = Button(text="Cancel", size_hint=(1, 0.2), on_press=lambda x: self.resolution_popup.dismiss())
        layout.add_widget(cancel_button)

        self.resolution_popup = Popup(title="Select Resolution", content=layout, size_hint=(0.8, 0.8))
        self.resolution_popup.open()
        self.video_info_popup.dismiss()

    def on_resolution_selection(self, stream):
        self.selected_stream = stream
        self.resolution_popup.dismiss()
        self.show_filechooser()

    def show_filechooser(self):
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        filechooser = FileChooserIconView(filters=['*/'], path='/', dirselect=True)
        select_button = Button(text="Select", size_hint=(1, 0.1), on_press=lambda *args: self.on_filechooser_selection(filechooser.selection))
        layout.add_widget(filechooser)
        layout.add_widget(select_button)

        self.filechooser_popup = Popup(title="Select Download Directory", content=layout, size_hint=(0.9, 0.9))
        self.filechooser_popup.open()

    def on_filechooser_selection(self, selection):
        if selection:
            self.download_path = selection[0]
            self.filechooser_popup.dismiss()
            self.perform_download()

    def perform_download(self):
        if self.download_type == "video":
            self.perform_video_download()
        elif self.download_type == "audio":
            self.perform_audio_download()

    def perform_video_download(self):
        try:
            self.selected_stream.download(output_path=self.download_path)
            self.show_message("Success", "Video downloaded successfully")
        except Exception as e:
            self.show_message("Error", str(e))

    def perform_audio_download(self):
        try:
            audio_file = self.selected_stream.download(output_path=self.download_path)
            base, ext = os.path.splitext(audio_file)
            new_file = base + '.mp3'
            audio_clip = AudioFileClip(audio_file)
            audio_clip.write_audiofile(new_file)
            audio_clip.close()
            os.remove(audio_file)
            self.show_message("Success", "Audio downloaded successfully as MP3")
        except Exception as e:
            self.show_message("Error", str(e))

if __name__ == "__main__":
    TubbyApp().run()

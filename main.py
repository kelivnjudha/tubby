import pytube
import humanize
from pytube import YouTube

flag = False

def menu():
	usr = input("""
		OPTIONS
		---------
		1. Download Video
		2. Download audio only
		---------
		> """)
	if usr == '1':
		video()
	elif usr == '2':
		audio()
	else:
		quit()

def video():
	index = -1
	print("\n__________ Download Video __________")
	url = input("\nEnter video url > ")
	try:
		yt = YouTube(url)
	except Exception as e:
		print("Connection Error!", e)
		return menu()
	video_stream = yt.streams.filter(only_video=True)

	if not video_stream:
		print("No video streams available for this URL")
		return menu()

	print("\n_____available resoluations_____")
	for i, Stream in enumerate (video_stream):
		print(f"\n{i} : {Stream}")
	
	c_res = int(input("Choose a resoluation > "))

	if c_res > i:
		print("Please enter the number of the resolution you want to download!!")
		return menu()
	else:
		stream_D = video_stream[c_res]

		if stream_D is not None:	
			print(f"\nVideo Title\t:\t{yt.title} ")
			print(f"\nVideo Length\t:\t{yt.length} seconds ")
			print(f"\nPublish date\t:\t{yt.publish_date}")
			print(f"\nViews Count\t:\t{yt.views}")
			print(f"\nFile size\t:\t{humanize.naturalsize(stream_D.filesize)}")
			name = stream_D.default_filename

			check = input("\nDo you wnat to Download? (y/n) > ").lower()
			if check.startswith('y'):
				path = input("\nEnter path to save video > ")
				name_check = input("Do you want to rename your video? (y/n) > ").lower()
				if name_check.startswith('y'):
					rename = input("Rename your video > ")
					stream_D.download(output_path = path, filename = rename)
					sec_check = input("Do you want to Download another one? (y/n) > ").lower()
					if sec_check.startswith('y'):
						menu()
					else:
						quit()
				else:	
					stream_D.download(output_path = path, filename = name)
					sec_check = input("Do you want to Download another one? (y/n) > ").lower()
					if sec_check.startswith('y'):
						menu()
					else:
						quit()
			else:
				menu()
		else:
			print("Error: chosen resolution not found in list of available resolutions")
			return menu()
	

def audio():
	print("\n__________ Download Audio __________")
	url = input("\nEnter video url > ")
	try:
		yt = YouTube(url)

	except Exception as e:
		print("Connection Error!", e)
		return menu()

	audio_streams = yt.streams.filter(only_audio = True)

	if not audio_streams:
		print("No video streams available for this URL")
		return menu()

	print("_____available quality_____")
	for i, Stream in enumerate(audio_streams):
		print(f"\n{i} : {Stream}")

	c_res = int(input("Choose any quality > "))

	if c_res > i:
		print("Please enter the number of the resolution you want to download!!")
		return menu()
	else:
		stream_D = audio_streams[c_res]

		if stream_D is not None:
			print(f"\nVideo Title\t:\t{yt.title} ")
			print(f"\nVideo Length\t:\t{yt.length} seconds ")
			print(f"\nPublish date\t:\t{yt.publish_date}")
			print(f"\nViews Count\t:\t{yt.views}")
			print(f"\nFile size\t:\t{humanize.naturalsize(stream_D.filesize)}")
			name = stream_D.default_filename
			check = input("\nDo you want to Download? (y/n) > ").lower()
			if check.startswith('y'):
				path = input("\nEnter path to save audio > ")
				name_check = input("Do you want to rename your audio file? (y/n) > ").lower()
				if name_check.startswith('y'):
					rename = input("Rename your audio > ")
					stream_D.download(output_path = path, filename = rename)

					sec_check = input("Do you want to Download another one? (y/n) > ").lower()
					if sec_check.startswith('y'):
						menu()
					else:
						quit()
				else:
					stream_D.download(output_path = path, filename = name)
					sec_check = input("Do you want to Download another one? (y/n) > ").lower()
					if sec_check.startswith('y'):
						menu()
					else:
						quit()
			else:
				menu()
		else:
			print("Error: chosen quality not found in list of available quality")
			return menu()

menu()

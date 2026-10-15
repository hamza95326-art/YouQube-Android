YouQube Android - Flet

CONTENTS
- main.py: Android-friendly Flet app
- requirements.txt: Python dependencies

RUN ON WINDOWS FOR A QUICK TEST
1. Install Python 3.12 (or a version supported by your installed Flet).
2. Open CMD in this folder.
3. Run:
   python -m venv .venv
   .venv\Scripts\activate
   python -m pip install -r requirements.txt
   python main.py

BUILD AN ANDROID APK
1. Install Flutter and the Android SDK and accept Android SDK licences.
2. Install Flet:
   python -m pip install --upgrade flet
3. Open a terminal in this project folder and run:
   flet build apk
4. Follow any build setup prompts. The APK is generated in the build output
   directory reported by Flet; the exact path can vary by Flet version.

IMPORTANT LIMITATIONS
- This is a rewritten mobile-friendly version, not a line-by-line conversion.
- YouTube search and downloads depend on yt-dlp and may stop working when
  YouTube changes its systems or for videos that require authentication,
  are region-restricted, or otherwise unavailable.
- This sample downloads the best available audio stream; it does not convert
  audio to MP3 because FFmpeg is not bundled.
- Android may restrict access to files outside the app's writable directory.
- The UI and Python syntax were checked, but an Android APK has not been built
  or tested on a physical device in this environment.
- Use downloads only where you have permission and where applicable terms allow it.

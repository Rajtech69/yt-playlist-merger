# YT Playlist Merger & 1080p Render Engine

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Hardware%20Accelerated-green.svg)](https://ffmpeg.org/)
[![yt--dlp](https://img.shields.io/badge/yt--dlp-Latest-red.svg)](https://github.com/yt-dlp/yt-dlp)

A high-performance desktop suite to download complete YouTube playlists, standardize clips into **1080p Full HD** (or 4K/720p), and merge them into a single continuous video with support for **Multi-Hour Rendering** (up to 10–24 hours) and **100% Intact Intros**. Includes both a native Tkinter Desktop GUI and an interactive Visual Timeline Editor Studio.

---

## 🌟 Key Features

1. **1080p Full HD Standardized Rendering**:
   - Scales and pillarboxes/letterboxes clips to true **1920x1080** Full HD with 48kHz Stereo AAC audio.
   - Eliminates black screens, stutter, or video freezes when mixing different source aspect ratios or resolutions.

2. **Full Multi-Hour Render Engine**:
   - **Full Natural Playlist Duration**: Merges all videos in a multi-hour playlist from start to finish (supports 10+ hours).
   - **10-Hour Loop / Extend Mode**: Seamlessly extends / loops any sequence (e.g., 19-minute playlist or 1-hour lofi music) into a full **10:00:00 (10-Hour)** continuous render.
   - **Custom Duration**: Specify any target duration in hours (e.g. 2 hours, 8 hours, 10 hours).

3. **Intact Intros by Default ("No Trimming")**:
   - Video intros are preserved with 100% integrity (Intro Trim is disabled by default).
   - Optional intro skip slider (1-120 seconds) is available if you explicitly want to skip repetitious intros.

4. **Hardware Acceleration Engine**:
   - Auto-detects GPU hardware encoders (`h264_nvenc` for NVIDIA, `h264_qsv` for Intel, `h264_amf` for AMD, `h264_mf` for Windows Media Foundation) with automatic fallback to multi-core CPU `libx264`.
   - 64-bit MP4 muxing with `-movflags +faststart` ensures 20GB+ video files open instantly without player lag.

5. **Visual Timeline Video Editor Studio**:
   - Built-in multi-track timeline web editor (`editor_backend.py` + `editor_ui.html`) for precise trimming, speed control, volume adjustments, and custom sequencing.

6. **Full Playlist Extraction**:
   - Automatically cleans watch URLs containing `&list=...` into playlist URLs so `yt-dlp` downloads all items without stopping early.

---

## 📁 Repository Structure

```
yt-playlist-merger/
├── main.py                   # Desktop Tkinter GUI application
├── video_processor.py        # FFmpeg video normalization & concat engine
├── downloader.py             # yt-dlp playlist extraction & download pipeline
├── editor_backend.py         # Visual Studio local backend server (secure HTTP)
├── editor_ui.html            # Web-based multi-track timeline video editor
├── install_deps.bat          # Automated dependency installation script
├── run.bat                   # Desktop app launcher
├── run_timeline_editor.bat   # Timeline Studio launcher
├── requirements.txt          # Python dependencies
├── .env.example              # Example environment configuration
├── .gitignore                # Production ignore rules (prevents large video commits)
├── .gitattributes           # Cross-platform line ending normalization
├── LICENSE                   # MIT License
├── SECURITY.md               # Responsible security policy
└── README.md                 # Project documentation
```

---

## 📋 Requirements

1. **Python 3.8+** (Installed & accessible via `py` or `python`)
2. **FFmpeg** (Included in `C:\ffmpeg\bin` or configured in system `PATH`)
3. **yt-dlp** (Run `install_deps.bat` or `pip install -r requirements.txt`)

---

## 🚀 Quick Start

### 1. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/Rajtech69/yt-playlist-merger.git
cd yt-playlist-merger
install_deps.bat
# Or manually:
pip install -r requirements.txt
```

### 2. Launching Desktop GUI
Double-click **`run.bat`** (or execute `py main.py`):
1. Paste your YouTube Playlist URL.
2. Choose your Output folder and filename.
3. Select **1080p Full HD** (selected by default).
4. Choose your output duration:
   - **Natural Playlist Duration** to merge all videos as-is.
   - **★ 10 Hours Full Render** to loop/extend the video to 10 hours.
5. Click **▶ Start 1080p Merge & Render**.
6. Once finished, click **📂 Open Output Folder** to access your merged video.

### 3. Launching Visual Timeline Studio
Double-click **`run_timeline_editor.bat`** (or execute `py editor_backend.py`):
- Automatically opens your browser at `http://localhost:7860`.
- Allows multi-track visual editing, clip trimming, and custom rendering.

---

## 🔒 Security & Privacy

- **Zero Secrets / Tokens**: No API keys or credentials required or stored.
- **Local Isolation**: Web services bind strictly to `127.0.0.1` and enforce local-origin CORS checks.
- **Safe Command Execution**: FFmpeg subprocesses run via structured argument lists (no shell injection risk).
- **Git Protection**: All temporary videos, downloads, and output renders (`*.mp4`, `test_output/`, `editor_media/`) are ignored by `.gitignore` to keep git repositories lightweight and under GitHub limits.

---

## 🛠️ Troubleshooting

| Issue | Solution |
|---|---|
| `Only 1 video downloaded` | The app automatically cleans URLs to download the full playlist. |
| `Audio out of sync on long videos` | Built-in 48kHz audio resampling (`aresample=async=1000`) keeps audio synced across 10+ hours. |
| `Out of disk space during render` | Ensure at least 15–25 GB free space on your chosen drive for 10-hour 1080p files. |
| `FFmpeg not found` | Place FFmpeg in `C:\ffmpeg\bin` or add its `bin` folder to your Windows system `PATH`. |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

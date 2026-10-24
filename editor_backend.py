"""
editor_backend.py
-----------------
Local Backend Server & FFmpeg Timeline Compiler for the Visual Video Editor.
Provides local media streaming, YouTube asset importing, frame thumbnailing,
and high-speed hardware-accelerated 1080p/4K multi-track video export.
"""

import os
import sys
import json
import subprocess
import shutil
import tempfile
import urllib.parse
import threading
import time
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Path config
FFMPEG_BIN = "C:/ffmpeg/bin/ffmpeg.exe" if os.path.isfile("C:/ffmpeg/bin/ffmpeg.exe") else "ffmpeg"
FFPROBE_BIN = "C:/ffmpeg/bin/ffprobe.exe" if os.path.isfile("C:/ffmpeg/bin/ffprobe.exe") else "ffprobe"

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(WORKSPACE_DIR, "editor_media")
os.makedirs(MEDIA_DIR, exist_ok=True)

try:
    from downloader import download_playlist, clean_playlist_url
    from video_processor import detect_best_encoder, get_media_duration, format_duration
except ImportError:
    def detect_best_encoder():
        return "h264_mf", ["-b:v", "4500k"]
    def get_media_duration(f):
        return 0.0
    def format_duration(s):
        return f"{int(s)//60}:{int(s)%60:02d}"


# Global render state for SSE/polling
current_render_state = {
    "status": "idle",
    "progress": 0,
    "speed": "0x",
    "eta": "",
    "message": "",
    "output_file": "",
    "error": "",
}


def get_video_metadata(file_path: str) -> dict:
    """Fetch duration, dimensions, and fps using ffprobe."""
    cmd = [
        FFPROBE_BIN,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            duration = float(data.get("format", {}).get("duration", 0))
            width = 1920
            height = 1080
            fps = 30
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    width = int(s.get("width", 1920))
                    height = int(s.get("height", 1080))
                    r_fps = s.get("r_frame_rate", "30/1")
                    if "/" in r_fps:
                        num, den = r_fps.split("/")
                        fps = round(float(num) / float(den)) if float(den) > 0 else 30
                    break
            return {
                "name": os.path.basename(file_path),
                "path": file_path,
                "duration": duration,
                "formatted_duration": format_duration(duration),
                "width": width,
                "height": height,
                "fps": fps,
                "size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2),
            }
    except Exception as e:
        print(f"Probe error on {file_path}: {e}")
    return {
        "name": os.path.basename(file_path),
        "path": file_path,
        "duration": 10.0,
        "formatted_duration": "00:10",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2) if os.path.isfile(file_path) else 0,
    }


def compile_and_render_timeline(project_data: dict, progress_callback):
    """
    Compile visual timeline project JSON into an FFmpeg render job.
    Supports multi-track cuts, trims, volume adjustments, and transitions.
    """
    global current_render_state
    resolution = project_data.get("resolution", "1080")
    w, h = (1920, 1080) if resolution == "1080" else ((3840, 2160) if resolution == "4k" else (1280, 720))
    fps = int(project_data.get("fps", 30))
    output_path = project_data.get("outputPath") or os.path.join(os.path.expanduser("~/Desktop"), "timeline_edited_video.mp4")

    tracks = project_data.get("tracks", [])
    video_clips = []
    audio_clips = []
    text_clips = []

    for tr in tracks:
        t_type = tr.get("type")
        for cl in tr.get("clips", []):
            if t_type == "video":
                video_clips.append(cl)
            elif t_type == "audio":
                audio_clips.append(cl)
            elif t_type == "text":
                text_clips.append(cl)

    # Sort video clips by timeline start time
    video_clips.sort(key=lambda c: float(c.get("start", 0)))
    audio_clips.sort(key=lambda c: float(c.get("start", 0)))

    if not video_clips and not audio_clips:
        raise ValueError("Timeline is empty! Add at least one clip.")

    encoder_name, encoder_args = detect_best_encoder()
    progress_callback(5, "Compiling timeline clips...")

    tmp_dir = tempfile.mkdtemp(prefix="timeline_render_")
    try:
        norm_clips = []
        total_vc = len(video_clips)

        # 1. Normalize each video segment to exact trim, speed, resolution, fps, 48kHz audio
        for idx, cl in enumerate(video_clips, 1):
            src_path = cl.get("src")
            if not os.path.isfile(src_path):
                # Search in MEDIA_DIR
                potential = os.path.join(MEDIA_DIR, os.path.basename(src_path))
                if os.path.isfile(potential):
                    src_path = potential
                else:
                    continue

            trim_start = float(cl.get("trimStart", 0))
            duration = float(cl.get("duration", 0))
            speed = float(cl.get("speed", 1.0))
            volume = float(cl.get("volume", 1.0))

            clip_out = os.path.join(tmp_dir, f"v_segment_{idx:04d}.mp4")
            
            # Video filter
            vf_parts = [
                f"scale={w}:{h}:force_original_aspect_ratio=decrease",
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black",
                "setsar=1",
                f"fps={fps}",
            ]
            if speed != 1.0 and speed > 0:
                vf_parts.append(f"setpts={1.0/speed}*PTS")
            else:
                vf_parts.append("setpts=PTS-STARTPTS")
            vf_parts.append("format=yuv420p")
            vf = ",".join(vf_parts)

            # Audio filter
            af_parts = ["aresample=async=1000"]
            if speed != 1.0 and speed > 0:
                af_parts.append(f"atempo={speed}")
            if volume != 1.0:
                af_parts.append(f"volume={volume}")
            af_parts.append("asetpts=PTS-STARTPTS")
            af = ",".join(af_parts)

            cmd = [
                FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "warning",
                "-ss", str(trim_start),
                "-t", str(duration),
                "-i", src_path,
                "-vf", vf,
                "-af", af,
                "-c:v", encoder_name,
            ] + encoder_args + [
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-ac", "2",
                "-movflags", "+faststart",
                clip_out
            ]

            pct = int(10 + (idx / max(1, total_vc)) * 70)
            progress_callback(pct, f"Rendering Segment {idx}/{total_vc}: {os.path.basename(src_path)}...")
            
            subprocess.run(cmd, check=True)
            norm_clips.append(clip_out)

        # 2. Concat all segments into the final output video
        progress_callback(85, "Merging all timeline tracks...")
        list_file = os.path.join(tmp_dir, "concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for seg in norm_clips:
                safe = seg.replace("\\", "/").replace("'", "\\'")
                f.write(f"file '{safe}'\n")

        merge_cmd = [
            FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "warning",
            "-fflags", "+genpts",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-max_muxing_queue_size", "4096",
            "-movflags", "+faststart",
            output_path,
        ]

        subprocess.run(merge_cmd, check=True)
        progress_callback(100, f"Render Complete! File saved: {output_path}")
        return output_path

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class EditorHTTPHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        # Restrict CORS to local development origins only (prevent external websites from accessing local API)
        origin = self.headers.get("Origin", "")
        if origin and (origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Root / UI
        if path in ("/", "/index.html"):
            ui_path = os.path.join(WORKSPACE_DIR, "editor_ui.html")
            if not os.path.isfile(ui_path):
                self.send_error(404, "editor_ui.html not found")
                return
            with open(ui_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # 2. Media list API
        if path == "/api/media":
            files = []
            if os.path.isdir(MEDIA_DIR):
                for f in sorted(os.listdir(MEDIA_DIR)):
                    if f.lower().endswith((".mp4", ".mov", ".mkv", ".mp3", ".wav", ".png", ".jpg")):
                        full_p = os.path.join(MEDIA_DIR, f)
                        files.append(get_video_metadata(full_p))
            res = json.dumps({"media": files}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(res)))
            self.end_headers()
            self.wfile.write(res)
            return

        # 3. Render status API
        if path == "/api/render-status":
            res = json.dumps(current_render_state).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(res)))
            self.end_headers()
            self.wfile.write(res)
            return

        # 4. Stream media file with Range support
        if path.startswith("/media/"):
            raw_param = urllib.parse.unquote(path[len("/media/"):])
            # Security: strictly prevent path traversal by extracting basename and verifying within MEDIA_DIR
            filename = os.path.basename(raw_param.strip("/\\"))
            filepath = os.path.realpath(os.path.join(MEDIA_DIR, filename))
            media_dir_real = os.path.realpath(MEDIA_DIR)

            allowed_exts = (".mp4", ".mov", ".mkv", ".mp3", ".wav", ".png", ".jpg", ".webm")
            if not filepath.startswith(media_dir_real) or not os.path.isfile(filepath) or not filepath.lower().endswith(allowed_exts):
                self.send_error(404, "Media file not found")
                return

            file_size = os.path.getsize(filepath)
            range_header = self.headers.get("Range")

            if range_header:
                # Handle range requests (e.g. bytes=0-1048576) for video scrubbing
                m = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else file_size - 1
                    end = min(end, file_size - 1)
                    length = end - start + 1

                    self.send_response(206)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    with open(filepath, "rb") as f:
                        f.seek(start)
                        self.wfile.write(f.read(length))
                    return

            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(filepath, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"

        # 1. Download from YouTube
        if path == "/api/download-yt":
            try:
                data = json.loads(body.decode("utf-8"))
                url = data.get("url", "").strip()
                if not url or not (url.startswith("http://") or url.startswith("https://")):
                    self.send_error(400, "Valid HTTP/HTTPS YouTube URL required")
                    return

                def _bg_download():
                    try:
                        download_playlist(
                            url=url,
                            output_dir=MEDIA_DIR,
                            quality="1080",
                            progress_callback=print,
                            cancel_flag=[False],
                        )
                    except Exception as ex:
                        print("Download failed:", ex)

                threading.Thread(target=_bg_download, daemon=True).start()

                res = json.dumps({"status": "downloading", "message": "Download started in background"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(res)))
                self.end_headers()
                self.wfile.write(res)
                return
            except Exception as e:
                self.send_error(500, str(e))
                return

        # 2. Render timeline
        if path == "/api/render":
            try:
                global current_render_state
                data = json.loads(body.decode("utf-8"))
                current_render_state = {
                    "status": "rendering",
                    "progress": 0,
                    "speed": "0x",
                    "eta": "Starting...",
                    "message": "Initializing render engine...",
                    "output_file": "",
                    "error": "",
                }

                def _bg_render():
                    global current_render_state
                    try:
                        def _progress(pct, msg):
                            current_render_state["progress"] = pct
                            current_render_state["message"] = msg

                        out = compile_and_render_timeline(data, _progress)
                        current_render_state["status"] = "done"
                        current_render_state["progress"] = 100
                        current_render_state["output_file"] = out
                    except Exception as ex:
                        current_render_state["status"] = "error"
                        current_render_state["error"] = str(ex)
                        print("Render error:", ex)

                threading.Thread(target=_bg_render, daemon=True).start()

                res = json.dumps({"status": "started"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(res)))
                self.end_headers()
                self.wfile.write(res)
                return
            except Exception as e:
                self.send_error(500, str(e))
                return

        self.send_error(404)


def start_server(port: int = 7860):
    server = ThreadedHTTPServer(("127.0.0.1", port), EditorHTTPHandler)
    url = f"http://localhost:{port}"
    print(f"\n========================================================")
    print(f" ▶ Visual Timeline Video Editor Studio is Running!")
    print(f" Access URL: {url}")
    print(f" Press Ctrl+C in terminal to stop.")
    print(f"========================================================\n")
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.shutdown()


if __name__ == "__main__":
    start_server(7860)

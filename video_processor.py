"""
video_processor.py
------------------
High-Performance 1080p Full HD Video Normalization & Any-Duration Render Engine.

Features:
  1. Universal Duration Support:
     - Merges videos/playlists of ANY duration (30 mins, 2 hours, 10 hours, 24+ hours, or natural playlist length).
     - Target Duration / Loop Mode: Can extend/loop any video sequence to any target duration (1h, 5h, 10h, 24h, etc.)
       via high-speed stream-copy concat.
  2. 1080p Full HD Standardized Rendering:
     - Scales & pads any playlist (1080p, 720p, 4K, 9:16 shorts) to 1080p Full HD (1920x1080) by default.
  3. Hardware Acceleration & Safe Fallback:
     - Auto-detects Windows Media Foundation (h264_mf), NVIDIA (h264_nvenc),
       Intel (h264_qsv), AMD (h264_amf), and falls back to multi-core CPU libx264.
  4. Flawless Timestamp & Audio Sync:
     - 48kHz Stereo AAC with aresample=async=1000 and genpts/make_zero to prevent PTS/DTS drift on multi-hour renders.
  5. 64-bit Large-File MP4 (100GB+ Capable):
     - Uses -movflags +faststart and -max_muxing_queue_size 4096 so multi-gigabyte/multi-hour files play instantly anywhere.
  6. Full Intro Preservation:
     - Video intros are preserved 100% intact by default.
"""

import os
import subprocess
import shutil
import tempfile
import math

FFMPEG_BIN = "C:/ffmpeg/bin/ffmpeg.exe"
FFPROBE_BIN = "C:/ffmpeg/bin/ffprobe.exe"


def _get_ffmpeg():
    if os.path.isfile(FFMPEG_BIN):
        return FFMPEG_BIN
    return "ffmpeg"


def _get_ffprobe():
    if os.path.isfile(FFPROBE_BIN):
        return FFPROBE_BIN
    return "ffprobe"


def detect_best_encoder() -> tuple[str, list]:
    """
    Test available encoders and return (encoder_name, extra_args).
    Prefers hardware acceleration on Windows, falls back to libx264.
    """
    ffmpeg = _get_ffmpeg()
    
    candidates = [
        ("h264_nvenc", ["-preset", "p4", "-cq", "20"]),
        ("h264_mf",    ["-b:v", "4500k"]),
        ("h264_qsv",   ["-preset", "fast", "-global_quality", "20"]),
        ("h264_amf",   ["-quality", "speed", "-rc", "cqp", "-qp_p", "20"]),
        ("libx264",    ["-preset", "fast", "-crf", "19", "-threads", "0"]),
    ]

    for enc, args in candidates:
        try:
            cmd = [
                ffmpeg, "-y", "-f", "lavfi",
                "-i", "nullsrc=s=640x360:d=0.1",
                "-c:v", enc
            ] + args + ["-f", "null", "-"]
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )
            if res.returncode == 0:
                return enc, args
        except Exception:
            continue

    return "libx264", ["-preset", "fast", "-crf", "19", "-threads", "0"]


def get_media_duration(file_path: str) -> float:
    """Return exact duration of a media file in seconds using ffprobe."""
    ffprobe = _get_ffprobe()
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass
    return 0.0


def format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS format."""
    total_sec = int(round(seconds))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def get_resolution_dimensions(quality: str) -> tuple[int, int]:
    """Map quality string to (width, height). Defaults to 1080p (1920x1080)."""
    q = str(quality).lower().strip()
    if q in ("4k", "2160", "2160p"):
        return 3840, 2160
    elif q in ("720", "720p"):
        return 1280, 720
    elif q in ("480", "480p"):
        return 854, 480
    elif q in ("1080", "1080p", "best"):
        return 1920, 1080
    return 1920, 1080


def _run_ffmpeg_streaming(args: list, progress_callback, cancel_flag: list) -> bool:
    """Run ffmpeg command and stream output lines to callback with cancellation check."""
    cmd = [_get_ffmpeg(), "-y", "-hide_banner", "-loglevel", "warning"] + args
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    
    output_lines = []
    try:
        for line in proc.stdout:
            if cancel_flag and cancel_flag[0]:
                proc.terminate()
                progress_callback("  [Cancelled by user]")
                return False
            line = line.rstrip()
            output_lines.append(line)
            if line:
                progress_callback(f"    {line}")
        proc.wait()
    except Exception as e:
        proc.kill()
        raise e

    if proc.returncode != 0 and not (cancel_flag and cancel_flag[0]):
        tail = "\n".join(output_lines[-15:])
        raise RuntimeError(f"FFmpeg error (code {proc.returncode}):\n{tail}")
    return proc.returncode == 0


def encode_single_clip(
    input_path: str,
    output_path: str,
    target_w: int,
    target_h: int,
    skip_seconds: float,
    encoder_name: str,
    encoder_args: list,
    progress_callback,
    cancel_flag: list,
) -> bool:
    """
    Encode a single clip into standardized 1080p/720p/4K H.264 + 48kHz Stereo AAC.
    Preserves exact aspect ratio with high-quality letterboxing/pillarboxing.
    """
    vf_filter = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,"
        f"fps=30,"
        f"setpts=PTS-STARTPTS,"
        f"format=yuv420p"
    )
    
    af_filter = "aresample=async=1000,asetpts=PTS-STARTPTS"

    args = []
    if skip_seconds > 0:
        args += ["-ss", str(skip_seconds)]

    args += [
        "-i", input_path,
        "-vf", vf_filter,
        "-af", af_filter,
        "-c:v", encoder_name,
    ] + encoder_args + [
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-max_muxing_queue_size", "4096",
        "-movflags", "+faststart",
        output_path,
    ]

    return _run_ffmpeg_streaming(args, progress_callback, cancel_flag)


def concatenate_videos(
    video_paths: list,
    output_path: str,
    quality: str = "1080",
    trim_intro_enabled: bool = False,
    skip_seconds: float = 0.0,
    target_duration_seconds: float = None,
    progress_callback = print,
    cancel_flag: list = None,
) -> str:
    """
    Universal Any-Duration 1080p/4K Merging Engine:
      1. Normalizes each clip into target resolution (1080p default) and 48kHz stereo AAC.
      2. Assembles concat playlist:
         - Natural Duration: Merges all videos in the playlist (any duration: 10 mins, 2 hours, 10 hours, 24+ hours).
         - Target Duration / Loop Mode: Loops or trims the sequence to match ANY requested duration (e.g. 1h, 3h, 5h, 10h, 24h).
      3. Stream-copies normalized clips into the final single high-speed MP4 with 64-bit offsets.

    Returns output_path on success, or empty string on cancel/failure.
    """
    if cancel_flag is None:
        cancel_flag = [False]

    target_w, target_h = get_resolution_dimensions(quality)
    encoder_name, encoder_args = detect_best_encoder()

    progress_callback(f"[Pipeline Init] Target Resolution: {target_w}x{target_h} ({quality}p)")
    progress_callback(f"[Pipeline Init] Video Encoder: {encoder_name} ({'Hardware GPU' if 'mf' in encoder_name or 'nvenc' in encoder_name or 'qsv' in encoder_name or 'amf' in encoder_name else 'Multi-Core CPU'})")
    
    if trim_intro_enabled and skip_seconds > 0:
        progress_callback(f"[Pipeline Init] Intro Trim: Skipping first {int(skip_seconds)}s of each clip")
    else:
        progress_callback("[Pipeline Init] Intro Trim: DISABLED — Full video intros preserved 100%")

    tmp_dir = tempfile.mkdtemp(prefix="yt_render_")

    try:
        encoded_clips = []
        clip_durations = []
        total_clips = len(video_paths)

        # ── Step 1: Normalize all clips ─────────────────────────────────────
        progress_callback(f"\n--- Normalizing {total_clips} Clip(s) to Standardized {target_w}x{target_h} 1080p ---")
        
        for idx, vpath in enumerate(video_paths, 1):
            if cancel_flag[0]:
                progress_callback("Render cancelled during clip normalization.")
                return ""

            bname = os.path.basename(vpath)
            progress_callback(f"\n[{idx}/{total_clips}] Normalizing: {bname}")

            actual_skip = skip_seconds if (trim_intro_enabled and skip_seconds > 0) else 0.0
            out_clip = os.path.join(tmp_dir, f"norm_clip_{idx:04d}.mp4")

            try:
                ok = encode_single_clip(
                    input_path=vpath,
                    output_path=out_clip,
                    target_w=target_w,
                    target_h=target_h,
                    skip_seconds=actual_skip,
                    encoder_name=encoder_name,
                    encoder_args=encoder_args,
                    progress_callback=progress_callback,
                    cancel_flag=cancel_flag,
                )
                if ok and os.path.isfile(out_clip):
                    dur = get_media_duration(out_clip)
                    encoded_clips.append(out_clip)
                    clip_durations.append(dur)
                    progress_callback(f"  [OK] Clip {idx}/{total_clips} ready ({format_duration(dur)})")
                else:
                    progress_callback(f"  [SKIP] Could not encode clip {idx}")
            except Exception as e:
                progress_callback(f"  [ERROR] Clip {idx} failed: {e}")

        if not encoded_clips:
            progress_callback("No clips were successfully encoded.")
            return ""

        if cancel_flag[0]:
            progress_callback("Render cancelled before concat assembly.")
            return ""

        # ── Step 2: Calculate Durations and Duration Strategy ──────────────
        unique_total_duration = sum(clip_durations)
        progress_callback(f"\nTotal Unique Content Length: {format_duration(unique_total_duration)} ({unique_total_duration:.1f}s)")

        concat_sequence = []
        apply_time_limit = None

        if target_duration_seconds and target_duration_seconds > 0:
            target_sec = float(target_duration_seconds)
            progress_callback(f"Target Output Duration: {format_duration(target_sec)} ({target_sec/3600:.2f} Hours)")

            if unique_total_duration > 0 and unique_total_duration < target_sec:
                loop_count = math.ceil(target_sec / unique_total_duration)
                progress_callback(
                    f"-> Extending sequence ({len(encoded_clips)} clip(s) x {loop_count} loops) to reach {format_duration(target_sec)}..."
                )
                for _ in range(loop_count):
                    concat_sequence.extend(encoded_clips)
                apply_time_limit = target_sec
            else:
                concat_sequence = list(encoded_clips)
                apply_time_limit = target_sec
        else:
            concat_sequence = list(encoded_clips)
            progress_callback(f"Rendering full natural duration: {format_duration(unique_total_duration)} ({unique_total_duration/3600:.2f} Hours)")

        # ── Step 3: Write Concat List ──────────────────────────────────────
        list_file = os.path.join(tmp_dir, "concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for clip_path in concat_sequence:
                safe_path = clip_path.replace("\\", "/").replace("'", "\\'")
                f.write(f"file '{safe_path}'\n")

        # ── Step 4: Stream-Copy Concat Assembly ────────────────────────────
        progress_callback(f"\n--- Assembling Final Output ({len(concat_sequence)} segments) via High-Speed Stream Concat ---")
        
        merge_args = [
            "-fflags", "+genpts",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
        ]

        if apply_time_limit and apply_time_limit > 0:
            merge_args += ["-t", str(apply_time_limit)]

        merge_args += [
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-max_muxing_queue_size", "4096",
            "-movflags", "+faststart",
            output_path,
        ]

        success = _run_ffmpeg_streaming(merge_args, progress_callback, cancel_flag)

        if success and os.path.isfile(output_path):
            final_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            final_dur = get_media_duration(output_path)
            progress_callback("\n" + "=" * 60)
            progress_callback(f" [SUCCESS] Render Finished Successfully!")
            progress_callback(f" Output Location: {output_path}")
            progress_callback(f" Final Duration:  {format_duration(final_dur)} ({final_dur/3600:.2f} Hours)")
            progress_callback(f" Final File Size: {final_size_mb:.2f} MB ({final_size_mb/1024:.2f} GB)")
            progress_callback("=" * 60 + "\n")
            return output_path
        else:
            progress_callback("Final merge assembly did not complete.")
            return ""

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

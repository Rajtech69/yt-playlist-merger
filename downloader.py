"""
downloader.py
-------------
Handles YouTube playlist downloading via yt-dlp.
Reports progress through a callback function so the GUI stays updated.
"""

import os
import re
import yt_dlp

FFMPEG_DIR = "C:/ffmpeg/bin"


def _get_ffmpeg_location():
    if os.path.exists(FFMPEG_DIR):
        return FFMPEG_DIR
    return "ffmpeg"


def clean_playlist_url(url: str) -> str:
    """
    If the user pastes a watch URL with a playlist parameter
    (e.g., https://www.youtube.com/watch?v=XYZ&list=PL123),
    extract the playlist ID and convert to a clean playlist URL
    so yt-dlp downloads all videos in the playlist rather than just the single video.
    """
    url = url.strip()
    match = re.search(r"[?&]list=([a-zA-Z0-9_-]+)", url)
    if match:
        playlist_id = match.group(1)
        return f"https://www.youtube.com/playlist?list={playlist_id}"
    return url


def get_playlist_info(url: str) -> dict:
    """
    Fetch playlist metadata without downloading.
    Works for pure playlist URLs and video URLs with ?list= param.
    """
    target_url = clean_playlist_url(url)
    ydl_opts = {
        "quiet": True,
        "extract_flat": "in_playlist",
        "no_warnings": True,
        "noplaylist": False,
        "yes_playlist": True,
        "ffmpeg_location": _get_ffmpeg_location(),
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "mweb", "ios", "android"]
            }
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(target_url, download=False)
    return info


def download_playlist(
    url: str,
    output_dir: str,
    quality: str,
    progress_callback,
    cancel_flag: list,
    playlist_items: str = None,
) -> list:
    """
    Download videos in the playlist to output_dir.

    Parameters
    ----------
    url              : YouTube playlist URL
    output_dir       : Folder to save downloaded videos
    quality          : '1080', '720', '480', '4k', or 'best'
    progress_callback: callable(message: str)
    cancel_flag      : single-element list [False]; set [True] to cancel
    playlist_items   : optional range e.g. "1-33" or None for all

    Returns
    -------
    List of absolute mp4 paths sorted by playlist index.
    """
    target_url = clean_playlist_url(url)

    # ── Format selector ────────────────────────────────────────────────────
    if quality == "best":
        fmt = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo+bestaudio"
            "/best"
        )
    elif quality == "4k" or quality == "2160":
        fmt = (
            "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=2160]+bestaudio"
            "/best[height<=2160]"
            "/best"
        )
    elif quality == "1080":
        fmt = (
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=1080]+bestaudio"
            "/best[height<=1080]"
            "/best"
        )
    else:
        h = quality  # e.g. "720", "480"
        fmt = (
            f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={h}]+bestaudio"
            f"/best[height<={h}]"
            f"/best"
        )

    output_template = os.path.join(
        output_dir, "%(playlist_index|0000)04d_%(title).100B.%(ext)s"
    )

    class CancelledError(Exception):
        pass

    final_files_set: set = set()

    def pp_hook(d):
        """Called after every postprocessor step."""
        if d.get("status") == "finished":
            filepath = d.get("info_dict", {}).get("filepath") or d.get("filepath", "")
            if filepath and filepath.lower().endswith(".mp4"):
                final_files_set.add(os.path.abspath(filepath))

    def dl_hook(d):
        if cancel_flag[0]:
            raise CancelledError("Cancelled by user.")
        status = d.get("status", "")
        if status == "downloading":
            title   = d.get("info_dict", {}).get("title", os.path.basename(d.get("filename", "")))
            percent = d.get("_percent_str", "?%").strip()
            speed   = d.get("_speed_str", "?/s").strip()
            eta     = d.get("_eta_str", "?").strip()
            progress_callback(f"  [{percent}] {title[:60]}  @ {speed}  ETA {eta}")
        elif status == "finished":
            title = d.get("info_dict", {}).get("title", "")
            progress_callback(f"  Downloaded: {title[:60]}")

    ydl_opts = {
        "format": fmt,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "progress_hooks": [dl_hook],
        "postprocessor_hooks": [pp_hook],
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,       # skip unavailable videos
        "noplaylist": False,        # always download the full playlist
        "yes_playlist": True,       # even when URL contains a video id
        "ffmpeg_location": _get_ffmpeg_location(),
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "mweb", "ios", "android"]
            }
        },
    }

    if playlist_items and playlist_items.strip() and playlist_items.strip().lower() != "all":
        ydl_opts["playlist_items"] = playlist_items.strip()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([target_url])
    except CancelledError:
        progress_callback("Download cancelled.")
        return []

    # ── Collect and sort by playlist index prefix ──────────────────────────
    dir_mp4s = {
        os.path.abspath(os.path.join(output_dir, f))
        for f in os.listdir(output_dir)
        if f.lower().endswith(".mp4")
    }
    all_files = (final_files_set | dir_mp4s)
    all_files = {f for f in all_files if os.path.dirname(f) == os.path.abspath(output_dir)}

    def sort_key(path):
        name = os.path.basename(path)
        m = re.match(r"^(\d+)", name)
        return int(m.group(1)) if m else 9999

    return sorted(all_files, key=sort_key)

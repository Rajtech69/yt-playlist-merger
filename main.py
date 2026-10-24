"""
main.py
-------
YouTube Playlist Video Merger & Any-Duration 1080p Render Engine
GUI built with tkinter.
Downloads all videos from a playlist, standardizes to 1080p Full HD (or 4K/720p),
merges playlists of ANY duration (1h, 5h, 10h, 24h+, or natural length),
and preserves 100% full video intros by default.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tempfile
import shutil

# Ensure ffmpeg bin is in PATH
if os.path.isdir("C:/ffmpeg/bin") and "C:/ffmpeg/bin" not in os.environ.get("PATH", ""):
    os.environ["PATH"] += ";C:/ffmpeg/bin"

try:
    from downloader import get_playlist_info, download_playlist, clean_playlist_url
    from video_processor import concatenate_videos, format_duration, detect_best_encoder
except ImportError as e:
    import traceback
    traceback.print_exc()
    print(f"Import error: {e}")
    sys.exit(1)


# ── Color Palette & Styles ──────────────────────────────────────────────────
BG        = "#14142b"
CARD      = "#1e1e38"
CARD_HOVER= "#262648"
ACCENT    = "#ff3366"
ACCENT2   = "#2b2b52"
ACCENT_BLUE = "#4361ee"
FG        = "#f8f9fa"
FG2       = "#a0a3bd"
GREEN     = "#06d6a0"
YELLOW    = "#ffd166"
CYAN      = "#4cc9f0"
FONT_MAIN = ("Segoe UI", 10)
FONT_HEAD = ("Segoe UI Semibold", 11)
FONT_BIG  = ("Segoe UI Bold", 13)
FONT_MONO = ("Consolas", 9)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YT Playlist Merger · Any-Duration & 1080p Engine")
        self.geometry("940x840")
        self.minsize(820, 700)
        self.configure(bg=BG)
        self.resizable(True, True)

        # State
        self._cancel_flag = [False]
        self._worker: threading.Thread | None = None
        self._temp_dir: str | None = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header bar ──
        header = tk.Frame(self, bg=ACCENT2, height=64)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title_frame = tk.Frame(header, bg=ACCENT2)
        title_frame.pack(side=tk.LEFT, fill=tk.Y, padx=18)

        tk.Label(
            title_frame,
            text="▶  YT Playlist Merger & Render Engine",
            font=FONT_BIG,
            bg=ACCENT2,
            fg=FG,
        ).pack(anchor=tk.W, pady=(8, 0))

        tk.Label(
            title_frame,
            text="Merge ANY Duration (1hr to 24hr+) · 1080p Full HD · Full Intros Preserved",
            font=("Segoe UI", 9),
            bg=ACCENT2,
            fg=CYAN,
        ).pack(anchor=tk.W)

        # Hardware encoder badge
        enc, _ = detect_best_encoder()
        badge_text = f"⚡ Engine: {enc.upper()}"
        tk.Label(
            header,
            text=badge_text,
            font=("Segoe UI Semibold", 9),
            bg="#111126",
            fg=GREEN,
            padx=10,
            pady=4,
        ).pack(side=tk.RIGHT, padx=18, pady=16)

        # ── Main Container ──
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self._build_input_section(body)
        self._build_settings_section(body)
        self._build_intro_section(body)
        self._build_buttons(body)
        self._build_log(body)

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, font=FONT_HEAD, bg=BG, fg=ACCENT).pack(
            anchor=tk.W, pady=(6, 2)
        )

    def _build_input_section(self, parent):
        self._section_label(parent, "① Playlist URL & Destination")

        card = tk.Frame(parent, bg=CARD, padx=12, pady=8)
        card.pack(fill=tk.X)

        # Row 1: URL input
        row1 = tk.Frame(card, bg=CARD)
        row1.pack(fill=tk.X, pady=(0, 6))

        tk.Label(row1, text="Playlist URL:", font=FONT_MAIN, bg=CARD, fg=FG2, width=12, anchor="w").pack(side=tk.LEFT)
        self._url_var = tk.StringVar()
        url_entry = tk.Entry(
            row1, textvariable=self._url_var, font=FONT_MAIN,
            bg=BG, fg=FG, insertbackground=FG,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=ACCENT2,
        )
        url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 6))
        url_entry.insert(0, "https://www.youtube.com/playlist?list=...")

        def _clear(e):
            if url_entry.get() == "https://www.youtube.com/playlist?list=...":
                url_entry.delete(0, tk.END)
        url_entry.bind("<FocusIn>", _clear)

        self._inspect_btn = tk.Button(
            row1, text="🔍 Inspect Playlist", font=FONT_MAIN, bg=ACCENT_BLUE, fg="white",
            relief=tk.FLAT, padx=12, cursor="hand2",
            command=self._inspect_playlist,
        )
        self._inspect_btn.pack(side=tk.LEFT, ipady=3)

        # Row 2: Destination folder & filename
        row2 = tk.Frame(card, bg=CARD)
        row2.pack(fill=tk.X)

        tk.Label(row2, text="Save to:", font=FONT_MAIN, bg=CARD, fg=FG2, width=12, anchor="w").pack(side=tk.LEFT)
        self._out_dir_var = tk.StringVar(value=os.path.expanduser("~/Desktop"))
        out_entry = tk.Entry(
            row2, textvariable=self._out_dir_var, font=FONT_MAIN,
            bg=BG, fg=FG, insertbackground=FG,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=ACCENT2,
        )
        out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        tk.Button(
            row2, text="Browse", font=FONT_MAIN, bg=ACCENT2, fg=FG,
            relief=tk.FLAT, padx=10, cursor="hand2",
            command=self._browse_folder,
        ).pack(side=tk.LEFT, padx=(6, 12), ipady=2)

        tk.Label(row2, text="Filename:", font=FONT_MAIN, bg=CARD, fg=FG2).pack(side=tk.LEFT, padx=(0, 4))
        self._fname_var = tk.StringVar(value="merged_1080p_video.mp4")
        tk.Entry(
            row2, textvariable=self._fname_var, font=FONT_MAIN,
            bg=BG, fg=FG, insertbackground=FG, width=24,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=ACCENT2,
        ).pack(side=tk.LEFT, ipady=4)

    def _build_settings_section(self, parent):
        self._section_label(parent, "② Resolution & Output Duration (Any Duration Capable)")

        card = tk.Frame(parent, bg=CARD, padx=12, pady=8)
        card.pack(fill=tk.X)

        # Row 1: Resolution options
        r_row = tk.Frame(card, bg=CARD)
        r_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(r_row, text="Resolution:", font=FONT_HEAD, bg=CARD, fg=FG, width=14, anchor="w").pack(side=tk.LEFT)
        self._quality_var = tk.StringVar(value="1080")
        
        resolutions = [
            ("★ 1080p Full HD (1920x1080)", "1080"),
            ("720p HD (1280x720)", "720"),
            ("4K Ultra HD (3840x2160)", "4k"),
            ("480p SD (854x480)", "480"),
        ]
        for label, val in resolutions:
            rb = tk.Radiobutton(
                r_row, text=label, variable=self._quality_var, value=val,
                font=FONT_MAIN, bg=CARD, fg=FG, selectcolor=ACCENT2,
                activebackground=CARD, activeforeground=ACCENT, cursor="hand2",
            )
            rb.pack(side=tk.LEFT, padx=(0, 8))

        # Row 2: Render Duration Mode
        d_row = tk.Frame(card, bg=CARD)
        d_row.pack(fill=tk.X, pady=(4, 6))

        tk.Label(d_row, text="Output Duration:", font=FONT_HEAD, bg=CARD, fg=FG, width=14, anchor="w").pack(side=tk.LEFT)
        self._duration_choice = tk.StringVar(value="natural")

        rb_nat = tk.Radiobutton(
            d_row, text="Natural Playlist Length (Full Merge of all videos — Any Duration)",
            variable=self._duration_choice, value="natural",
            font=FONT_MAIN, bg=CARD, fg=GREEN, selectcolor=ACCENT2,
            activebackground=CARD, activeforeground=ACCENT, cursor="hand2",
            command=self._toggle_duration_mode,
        )
        rb_nat.pack(side=tk.LEFT, padx=(0, 10))

        rb_target = tk.Radiobutton(
            d_row, text="Specific Duration (Loop / Extend to Desired Length):",
            variable=self._duration_choice, value="custom",
            font=FONT_MAIN, bg=CARD, fg=YELLOW, selectcolor=ACCENT2,
            activebackground=CARD, activeforeground=ACCENT, cursor="hand2",
            command=self._toggle_duration_mode,
        )
        rb_target.pack(side=tk.LEFT)

        # Row 3: Preset duration chips & custom hours/minutes
        self._dur_controls_row = tk.Frame(card, bg=CARD)
        self._dur_controls_row.pack(fill=tk.X, padx=(110, 0), pady=(0, 6))

        tk.Label(self._dur_controls_row, text="Presets:", font=("Segoe UI", 9), bg=CARD, fg=FG2).pack(side=tk.LEFT, padx=(0, 4))
        
        self._preset_buttons = []
        for p_label, p_hrs in [("30m", 0.5), ("1h", 1.0), ("2h", 2.0), ("3h", 3.0), ("5h", 5.0), ("8h", 8.0), ("10h ★", 10.0), ("12h", 12.0), ("24h", 24.0)]:
            btn = tk.Button(
                self._dur_controls_row, text=p_label, font=("Segoe UI", 8),
                bg=ACCENT2, fg=FG, relief=tk.FLAT, padx=6, pady=1, cursor="hand2",
                command=lambda h=p_hrs: self._set_preset_duration(h),
            )
            btn.pack(side=tk.LEFT, padx=2)
            self._preset_buttons.append(btn)

        tk.Label(self._dur_controls_row, text="  Or Custom:", font=("Segoe UI", 9), bg=CARD, fg=FG2).pack(side=tk.LEFT, padx=(6, 4))
        
        self._custom_hours_var = tk.StringVar(value="10.0")
        self._custom_hours_entry = tk.Entry(
            self._dur_controls_row, textvariable=self._custom_hours_var, font=FONT_MAIN,
            bg=BG, fg=FG, insertbackground=FG, width=6,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=ACCENT2,
        )
        self._custom_hours_entry.pack(side=tk.LEFT, padx=(0, 4), ipady=1)
        tk.Label(self._dur_controls_row, text="hour(s)", font=("Segoe UI", 9), bg=CARD, fg=FG2).pack(side=tk.LEFT)

        self._toggle_duration_mode()

        # Row 4: Video Selection Range
        v_row = tk.Frame(card, bg=CARD)
        v_row.pack(fill=tk.X, pady=(4, 0))

        tk.Label(v_row, text="Videos to Merge:", font=FONT_HEAD, bg=CARD, fg=FG, width=14, anchor="w").pack(side=tk.LEFT)
        self._range_choice = tk.StringVar(value="all")

        rb_all = tk.Radiobutton(
            v_row, text="All Videos in Playlist", variable=self._range_choice, value="all",
            font=FONT_MAIN, bg=CARD, fg=FG, selectcolor=ACCENT2,
            activebackground=CARD, activeforeground=ACCENT, cursor="hand2",
            command=self._toggle_range,
        )
        rb_all.pack(side=tk.LEFT, padx=(0, 15))

        rb_custom_range = tk.Radiobutton(
            v_row, text="Custom Video Range:", variable=self._range_choice, value="custom",
            font=FONT_MAIN, bg=CARD, fg=FG, selectcolor=ACCENT2,
            activebackground=CARD, activeforeground=ACCENT, cursor="hand2",
            command=self._toggle_range,
        )
        rb_custom_range.pack(side=tk.LEFT)

        self._range_var = tk.StringVar(value="1-50")
        self._range_entry = tk.Entry(
            v_row, textvariable=self._range_var, font=FONT_MAIN,
            bg=BG, fg=FG, insertbackground=FG, width=10,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=ACCENT2,
            state=tk.DISABLED,
        )
        self._range_entry.pack(side=tk.LEFT, padx=(6, 10), ipady=2)
        tk.Label(v_row, text="(e.g. 1-10 or 1,3,5)", font=("Segoe UI", 8), bg=CARD, fg=FG2).pack(side=tk.LEFT)

    def _set_preset_duration(self, hours: float):
        self._duration_choice.set("custom")
        self._custom_hours_var.set(str(hours))
        self._toggle_duration_mode()

    def _toggle_duration_mode(self):
        is_custom = (self._duration_choice.get() == "custom")
        state = tk.NORMAL if is_custom else tk.DISABLED
        self._custom_hours_entry.config(state=state)
        for btn in self._preset_buttons:
            btn.config(state=state)

    def _toggle_range(self):
        state = tk.NORMAL if self._range_choice.get() == "custom" else tk.DISABLED
        self._range_entry.config(state=state)

    def _build_intro_section(self, parent):
        self._section_label(parent, "③ Intro Trimming (Disabled by Default — Keeps Intros Intact)")

        card = tk.Frame(parent, bg=CARD, padx=12, pady=6)
        card.pack(fill=tk.X)

        top_row = tk.Frame(card, bg=CARD)
        top_row.pack(fill=tk.X)

        self._trim_enabled = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(
            top_row,
            text="✂️  Optional: Trim start of every video (Unchecked = Keep 100% Full Video Intros)",
            variable=self._trim_enabled,
            font=FONT_MAIN, bg=CARD, fg=FG,
            selectcolor=ACCENT2, activebackground=CARD, activeforeground=ACCENT,
            relief=tk.FLAT, cursor="hand2",
            command=self._toggle_trim,
        )
        chk.pack(side=tk.LEFT)

        # Slider row
        self._trim_frame = tk.Frame(card, bg=CARD)
        self._trim_frame.pack(fill=tk.X, pady=(2, 2))

        tk.Label(self._trim_frame, text="Skip:", font=FONT_MAIN, bg=CARD, fg=FG2).pack(side=tk.LEFT)
        self._skip_var = tk.DoubleVar(value=5.0)
        self._slider = tk.Scale(
            self._trim_frame,
            from_=1, to=120,
            orient=tk.HORIZONTAL,
            variable=self._skip_var,
            length=260,
            bg=CARD, fg=FG, troughcolor=ACCENT2,
            highlightthickness=0, activebackground=ACCENT,
            font=FONT_MAIN,
            resolution=1,
        )
        self._slider.pack(side=tk.LEFT, padx=8)
        self._skip_label = tk.Label(
            self._trim_frame, text="5 seconds per video",
            font=FONT_MAIN, bg=CARD, fg=YELLOW,
        )
        self._skip_label.pack(side=tk.LEFT)
        self._slider.config(command=self._update_skip_label)
        self._toggle_trim()

    def _toggle_trim(self):
        state = tk.NORMAL if self._trim_enabled.get() else tk.DISABLED
        self._slider.config(state=state)

    def _update_skip_label(self, val):
        secs = int(float(val))
        self._skip_label.config(text=f"{secs} second{'s' if secs != 1 else ''} per video")

    def _build_buttons(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill=tk.X, pady=(8, 4))

        self._start_btn = tk.Button(
            row, text="▶  Start 1080p Merge & Render",
            font=("Segoe UI Bold", 11),
            bg=ACCENT, fg="white",
            relief=tk.FLAT, padx=24, pady=8,
            cursor="hand2",
            command=self._start,
        )
        self._start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self._cancel_btn = tk.Button(
            row, text="⏹  Cancel",
            font=FONT_MAIN,
            bg=ACCENT2, fg=FG,
            relief=tk.FLAT, padx=16, pady=8,
            cursor="hand2", state=tk.DISABLED,
            command=self._cancel,
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=(0, 10))

        self._open_btn = tk.Button(
            row, text="📂  Open Output Folder",
            font=FONT_MAIN,
            bg=ACCENT_BLUE, fg="white",
            relief=tk.FLAT, padx=16, pady=8,
            cursor="hand2", state=tk.DISABLED,
            command=self._open_folder,
        )
        self._open_btn.pack(side=tk.LEFT)

        # Status chip
        self._status_var = tk.StringVar(value="Ready")
        self._status_lbl = tk.Label(
            row, textvariable=self._status_var,
            font=FONT_HEAD, bg=BG, fg=GREEN,
        )
        self._status_lbl.pack(side=tk.RIGHT, padx=6)

    def _build_log(self, parent):
        tk.Label(parent, text="④ Live Progress & Render Log", font=FONT_HEAD, bg=BG, fg=ACCENT).pack(anchor=tk.W, pady=(4, 2))

        log_frame = tk.Frame(parent, bg=CARD)
        log_frame.pack(fill=tk.BOTH, expand=True)

        scroll = tk.Scrollbar(log_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._log = tk.Text(
            log_frame,
            font=FONT_MONO, bg=CARD, fg=FG,
            insertbackground=FG,
            relief=tk.FLAT, bd=0,
            wrap=tk.WORD,
            yscrollcommand=scroll.set,
            state=tk.DISABLED,
        )
        self._log.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        scroll.config(command=self._log.yview)

        # Colour tags
        self._log.tag_config("green",  foreground=GREEN)
        self._log.tag_config("yellow", foreground=YELLOW)
        self._log.tag_config("red",    foreground=ACCENT)
        self._log.tag_config("cyan",   foreground=CYAN)
        self._log.tag_config("dim",    foreground=FG2)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self._out_dir_var.set(folder)

    def _open_folder(self):
        folder = self._out_dir_var.get()
        if os.path.isdir(folder):
            os.startfile(folder)

    def _log_write(self, msg: str, tag: str = ""):
        def _do():
            self._log.config(state=tk.NORMAL)
            if tag:
                self._log.insert(tk.END, msg + "\n", tag)
            else:
                self._log.insert(tk.END, msg + "\n")
            self._log.see(tk.END)
            self._log.config(state=tk.DISABLED)
        self.after(0, _do)

    def _set_status(self, msg: str, color=GREEN):
        def _do():
            self._status_var.set(msg)
            self._status_lbl.config(fg=color)
        self.after(0, _do)

    def _set_running(self, running: bool):
        def _do():
            if running:
                self._start_btn.config(state=tk.DISABLED)
                self._inspect_btn.config(state=tk.DISABLED)
                self._cancel_btn.config(state=tk.NORMAL)
                self._open_btn.config(state=tk.DISABLED)
            else:
                self._start_btn.config(state=tk.NORMAL)
                self._inspect_btn.config(state=tk.NORMAL)
                self._cancel_btn.config(state=tk.DISABLED)
        self.after(0, _do)

    def _inspect_playlist(self):
        url = self._url_var.get().strip()
        if not url or url.startswith("https://www.youtube.com/playlist?list=..."):
            messagebox.showerror("Input Error", "Please enter a valid YouTube playlist URL first.")
            return

        def _worker():
            self._log_write("\n[Inspecting playlist...]", "cyan")
            try:
                info = get_playlist_info(url)
                title = info.get("title", "Unknown Playlist")
                entries = info.get("entries") or []
                self._log_write(f"Playlist Title: {title}", "green")
                self._log_write(f"Total Videos Found: {len(entries)}", "green")
                self._log_write("─" * 55, "dim")
                for i, e in enumerate(entries, 1):
                    t = (e.get("title") or "Unknown Video")
                    self._log_write(f"  {i:02d}. {t}", "dim")
                self._log_write("─" * 55, "dim")
                self._log_write("Ready! Click 'Start 1080p Merge & Render' to begin.", "yellow")
            except Exception as e:
                self._log_write(f"Error inspecting playlist: {e}", "red")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    # ── Core workflow ────────────────────────────────────────────────────────

    def _validate(self):
        url = self._url_var.get().strip()
        if not url or url.startswith("https://www.youtube.com/playlist?list=..."):
            messagebox.showerror("Input Error", "Please enter a valid YouTube playlist URL.")
            return False
        out_dir = self._out_dir_var.get().strip()
        if not out_dir:
            messagebox.showerror("Input Error", "Please choose an output folder.")
            return False
        fname = self._fname_var.get().strip()
        if not fname:
            messagebox.showerror("Input Error", "Please enter an output filename.")
            return False
        if not fname.lower().endswith(".mp4"):
            self._fname_var.set(fname + ".mp4")
        return True

    def _start(self):
        if not self._validate():
            return

        # Clear log
        self._log.config(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.config(state=tk.DISABLED)

        self._cancel_flag = [False]
        self._set_running(True)
        self._set_status("Rendering ...", YELLOW)
        self._open_btn.config(state=tk.DISABLED)

        self._worker = threading.Thread(target=self._run_pipeline, daemon=True)
        self._worker.start()

    def _cancel(self):
        self._cancel_flag[0] = True
        self._set_status("Cancelling ...", YELLOW)
        self._log_write("Cancel requested - stopping gracefully...", "yellow")

    def _run_pipeline(self):
        url         = self._url_var.get().strip()
        out_dir     = self._out_dir_var.get().strip()
        fname       = self._fname_var.get().strip()
        quality     = self._quality_var.get()
        trim_on     = self._trim_enabled.get()
        skip_secs   = self._skip_var.get() if trim_on else 0.0
        range_mode  = self._range_choice.get()
        range_val   = self._range_var.get().strip() if range_mode == "custom" else None
        dur_mode    = self._duration_choice.get()

        target_dur_sec = None
        if dur_mode == "custom":
            try:
                hours = float(self._custom_hours_var.get().strip())
                target_dur_sec = max(10.0, hours * 3600.0)
            except ValueError:
                target_dur_sec = None

        final_output = os.path.join(out_dir, fname)

        try:
            os.makedirs(out_dir, exist_ok=True)

            # ── Step 1: Fetch metadata ──
            self._log_write("Fetching playlist metadata...", "yellow")
            try:
                info = get_playlist_info(url)
                title   = info.get("title", "Unknown Playlist")
                entries = info.get("entries", []) or []
                n       = len(entries)
                self._log_write(f'Playlist: "{title}" | Total: {n} video(s)', "green")
            except Exception as e:
                self._log_write(f"Could not fetch playlist metadata: {e}", "yellow")
                self._log_write("Proceeding directly to download...", "dim")

            if self._cancel_flag[0]:
                self._log_write("Cancelled.", "red")
                self._finish(success=False)
                return

            # ── Step 2: Download ──
            self._temp_dir = tempfile.mkdtemp(prefix="yt_dl_")
            self._log_write(f"\nTarget Resolution: {quality.upper()}p Full HD" if quality.isdigit() else f"Target Resolution: {quality.upper()}", "cyan")
            
            if target_dur_sec:
                self._log_write(f"Target Render Duration: {format_duration(target_dur_sec)} ({target_dur_sec/3600:.2f} Hours)", "yellow")
            else:
                self._log_write("Target Render Duration: Full Natural Playlist (Any length)", "green")

            if range_val:
                self._log_write(f"Download Range: Videos {range_val}", "cyan")
            else:
                self._log_write("Download Range: ALL videos in playlist", "cyan")

            if trim_on and skip_secs > 0:
                self._log_write(f"Intro Trim: Skipping first {int(skip_secs)}s of each video", "yellow")
            else:
                self._log_write("Intro Trim: DISABLED (Full intros kept intact)", "green")

            self._log_write("\n--- Downloading Videos from Playlist ---", "yellow")
            video_files = download_playlist(
                url, self._temp_dir, quality,
                progress_callback=lambda m: self._log_write(m, "dim"),
                cancel_flag=self._cancel_flag,
                playlist_items=range_val,
            )

            if self._cancel_flag[0]:
                self._log_write("Cancelled.", "red")
                self._finish(success=False)
                return

            if not video_files:
                self._log_write("No videos were downloaded. Check the URL and try again.", "red")
                self._finish(success=False)
                return

            self._log_write(f"\n[OK] {len(video_files)} video(s) ready for processing.", "green")

            # ── Step 3: Process + 1080p Normalization + Any-Duration Concat ──
            self._log_write("\nStarting 1080p standardization & any-duration merge engine...", "yellow")
            result = concatenate_videos(
                video_files,
                output_path=final_output,
                quality=quality,
                trim_intro_enabled=trim_on,
                skip_seconds=skip_secs,
                target_duration_seconds=target_dur_sec,
                progress_callback=lambda m: self._log_write(m),
                cancel_flag=self._cancel_flag,
            )

            if result and os.path.isfile(result):
                sz_mb = os.path.getsize(result) / (1024 * 1024)
                self._log_write(f"\n[OK] Output generated successfully:\n   File: {final_output}\n   Size: {sz_mb:.1f} MB ({sz_mb/1024:.2f} GB)", "green")
                self._finish(success=True)
            else:
                self._log_write("Merge and render did not complete.", "red")
                self._finish(success=False)

        except Exception as e:
            import traceback
            self._log_write(f"\nError: {e}", "red")
            self._log_write(traceback.format_exc(), "dim")
            self._finish(success=False)
        finally:
            if self._temp_dir and os.path.isdir(self._temp_dir):
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                self._temp_dir = None

    def _finish(self, success: bool):
        def _do():
            self._set_running(False)
            if success:
                self._set_status("Render Complete!", GREEN)
                self._open_btn.config(state=tk.NORMAL)
            else:
                self._set_status("Stopped" if self._cancel_flag[0] else "Error", ACCENT)
        self.after(0, _do)

    def _on_close(self):
        if self._worker and self._worker.is_alive():
            self._cancel_flag[0] = True
        self.destroy()


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()

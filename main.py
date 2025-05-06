import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))
import threading
import glob
import re
import shutil
import subprocess
import time
import requests

from tkinterdnd2 import DND_FILES, TkinterDnD
import tkinter as tk
import customtkinter as ctk
from customtkinter import CTkFont, CTkImage
from PIL import Image
from mpv_controller import MPVController

# --- Constants ---
LIBRARY_DIR    = "library"
FAVORITES_FILE = "favorites.txt"
PLAYLISTS_DIR  = "playlists"
ICONS_DIR      = os.path.join("assets", "icons")
ART_DIR        = "art"

# --- Theme Setup ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


def extract_metadata(filename):
    """
    Parse 'Artist - Title.ext' into (artist, title),
    or fall back to ('Unknown Artist', basename).
    """
    base  = os.path.splitext(os.path.basename(filename))[0]
    parts = re.split(r" - |_", base)
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return "Unknown Artist", base


def fetch_youtube_thumbnail(url, dest=ART_DIR):
    """
    Download YouTube video thumbnail to ART_DIR and return its path,
    or None on failure.
    """
    if "v=" in url:
        vid = url.split("v=")[1].split("&")[0]
    else:
        vid = url.rstrip("/").split("/")[-1]
    thumb_url = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
    os.makedirs(dest, exist_ok=True)
    out = os.path.join(dest, f"{vid}.jpg")
    try:
        r = requests.get(thumb_url, timeout=5)
        r.raise_for_status()
        with open(out, "wb") as f:
            f.write(r.content)
        return out
    except Exception as e:
        print("❌ Thumbnail fetch failed:", e)
        return None


class FOGRPlayer(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        # --- Graceful shutdown: ensure MPV is killed on window close ---
        self.quit_app = self.destroy
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- Window Setup ---
        self.title("KEEP-IT PLAYR")
        self.geometry("1200x750")
        self.minsize(800, 600)

        # --- Fonts ---
        self.title_font  = CTkFont(family="Akira Jimbo", size=24, weight="bold")
        self.button_font = CTkFont(family="Akira Jimbo", size=14)
        self.option_add("*Font", self.button_font)

        # --- Icons ---
        self.icon_sun    = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, "sun.png")),  size=(20,20))
        self.icon_moon   = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, "moon.png")), size=(20,20))
        self.icon_trash  = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, "trash.png")), size=(16,16))
        self.icon_up     = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, "up.png")),    size=(16,16))
        self.icon_down   = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, "down.png")),  size=(16,16))

        # --- State Variables ---
        self.url_var          = ctk.StringVar()
        self.search_var_lib   = ctk.StringVar()
        self.search_var_fav   = ctk.StringVar()
        self.current_process  = None
        self.mpv              = MPVController()
        self.current_song     = None
        self.is_paused        = False
        self.volume_level     = 50
        self.current_duration = 1
        self.song_list        = []
        self.song_index       = 0
        self.favorites        = set()

        # --- Ensure Directories & Load Favorites ---
        os.makedirs(LIBRARY_DIR,  exist_ok=True)
        os.makedirs(PLAYLISTS_DIR, exist_ok=True)
        os.makedirs(ART_DIR,       exist_ok=True)
        if os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE) as f:
                self.favorites = set(line.strip() for line in f)

        # --- Drag & Drop Setup ---
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self.handle_drop)

        # --- Build UI ---
        self.build_sidebar()
        self.build_main_area()
        self.build_playback_bar()
        self.show_library()

        # --- Keyboard Shortcuts ---
        self.bind("<space>", lambda e: self.toggle_play())
        self.bind("<Left>",  lambda e: self.adjust_position(-10))
        self.bind("<Right>", lambda e: self.adjust_position(10))
        self.bind("<Up>",    lambda e: self.change_volume(self.volume_level+5))
        self.bind("<Down>",  lambda e: self.change_volume(self.volume_level-5))


    # --- Graceful on-close handler ---
    def on_close(self):
        """Terminate MPV process before closing the GUI."""
        if self.current_process and self.current_process.poll() is None:
            self.current_process.terminate()
        self.destroy()


    # --- Drag & Drop Handler ---
    def handle_drop(self, event):
        """Copy dropped mp3/m4a files into the library."""
        for fp in self.tk.splitlist(event.data):
            if fp.lower().endswith((".mp3", ".m4a")):
                try:
                    shutil.copy(fp, os.path.join(LIBRARY_DIR, os.path.basename(fp)))
                except Exception as e:
                    print("❌ Drag-drop error:", e)
        self.show_library()


    # --- YouTube Playback & Download ---
    def play_url(self):
        """Download a YouTube URL then play it."""
        url = self.url_var.get().strip()
        if not url:
            return
        def runner():
            try:
                title = subprocess.check_output(["yt-dlp","--get-title",url]).decode().strip()
                safe  = re.sub(r'[\\/*?:"<>|]',"_", title)
                fn    = f"{safe}.m4a"
                path  = os.path.join(LIBRARY_DIR, fn)
                subprocess.run(
                    ["yt-dlp","-f","bestaudio","--extract-audio",
                     "--audio-format","m4a","-o",path,url],
                    check=True
                )
                thumb = fetch_youtube_thumbnail(url)
                if thumb:
                    self.set_cover_art(thumb)
                self.play_song(fn)
            except Exception as e:
                print("❌ play_url error:", e)
        threading.Thread(target=runner, daemon=True).start()


    def download_audio(self):
        """Download a YouTube URL into your local library (no playback)."""
        url = self.url_var.get().strip()
        if not url:
            return
        def runner():
            try:
                title = subprocess.check_output(["yt-dlp","--get-title",url]).decode().strip()
                safe  = re.sub(r'[\\/*?:"<>|]',"_", title)
                fn    = f"{safe}.m4a"
                path  = os.path.join(LIBRARY_DIR, fn)
                subprocess.run(
                    ["yt-dlp","-f","bestaudio","--extract-audio",
                     "--audio-format","m4a","-o",path,url],
                    check=True
                )
                self.show_library()
            except Exception as e:
                print("❌ download_audio error:", e)
        threading.Thread(target=runner, daemon=True).start()


    # --- Sidebar with Navigation ---
    def build_sidebar(self):
        sb = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color="#111")
        sb.pack(side="left", fill="y")

        items = [
            ("home.png",      "Home",      self.show_home),
            ("library.png",   "Library",   self.show_library),
            ("favorites.png", "Favorites", self.show_favorites),
            ("playlists.png", "Playlists", self.show_playlists),
        ]
        for icon_file, label, cmd in items:
            path = os.path.join(ICONS_DIR, icon_file)
            img  = CTkImage(light_image=Image.open(path), size=(20,20)) if os.path.exists(path) else None
            btn = ctk.CTkButton(
                sb, text=label, image=img, compound="left",
                fg_color="#222", hover_color="#333",
                text_color="#FFD369", font=self.button_font,
                corner_radius=5, height=40, command=cmd
            )
            btn.pack(fill="x", pady=5, padx=10)

        # Theme toggle at bottom
        mode = ctk.get_appearance_mode().lower()
        ico  = self.icon_sun if mode == "dark" else self.icon_moon
        self.theme_btn = ctk.CTkButton(
            sb, image=ico, text="",
            fg_color="#222", hover_color="#333",
            command=self.toggle_theme
        )
        self.theme_btn.pack(fill="x", pady=20, padx=10)


    # --- Main Content Area ---
    def build_main_area(self):
        self.main_frame = ctk.CTkFrame(self, fg_color="#1e1e1e")
        self.main_frame.pack(side="top", fill="both", expand=True)

        self.title_label = ctk.CTkLabel(
            self.main_frame, text="Now Playing",
            font=self.title_font, text_color="#FFD369"
        )
        self.title_label.pack(pady=10)

        self.content_frame = ctk.CTkScrollableFrame(
            self.main_frame, fg_color="#1e1e1e"
        )
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=10)


    # --- Playback Bar at Bottom ---
    def build_playback_bar(self):
        bar = ctk.CTkFrame(self, fg_color="#111")
        bar.pack(side="bottom", fill="x")

        # Track info + favorite
        self.track_label = ctk.CTkLabel(
            bar, text="No track loaded",
            font=self.button_font, text_color="#FFD369"
        )
        self.track_label.pack(side="left", padx=15)

        self.heart_empty = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR,"heart.png")),        size=(20,20))
        self.heart_full  = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR,"heart_filled.png")), size=(20,20))
        self.heart_btn   = ctk.CTkButton(
            bar, image=self.heart_empty, text="", width=40,
            command=self.toggle_favorite
        )
        self.heart_btn.pack(side="left", padx=5)

        # Seek bar
        self.seek_canvas = tk.Canvas(bar, height=8, bg="#333", highlightthickness=0)
        self.seek_canvas.pack(fill="x", expand=True, padx=20, pady=5)
        self.seek_canvas.bind("<Button-1>", self.seek_to_position)

        # Controls + volume + quit
        ctrl = ctk.CTkFrame(bar, fg_color="#111")
        ctrl.pack(side="left", padx=10)
        self.prev_img  = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR,"prev.png")),  size=(20,20))
        self.play_img  = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR,"play.png")),  size=(20,20))
        self.pause_img = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR,"pause.png")), size=(20,20))
        self.next_img  = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR,"next.png")), size=(20,20))

        ctk.CTkButton(ctrl, image=self.prev_img,  text="", width=40, command=self.prev_song).pack(side="left")
        self.pp_btn = ctk.CTkButton(ctrl, image=self.play_img, text="", width=40, command=self.toggle_play)
        self.pp_btn.pack(side="left")
        ctk.CTkButton(ctrl, image=self.next_img,  text="", width=40, command=self.next_song).pack(side="left")

        self.vol_slider = ctk.CTkSlider(bar, from_=0, to=100, command=self.change_volume)
        self.vol_slider.set(self.volume_level)
        self.vol_slider.pack(side="left", padx=10)

        ctk.CTkButton(bar, text="Quit", command=self.quit_app).pack(side="right", padx=10)


    # --- Play a Library Song ---
    def play_song(self, song):
        artist, title = extract_metadata(song)
        self.current_song = song
        self.track_label.configure(text=f"{artist} — {title}")

        thumb = os.path.join(ART_DIR, os.path.splitext(song)[0] + ".jpg")
        if os.path.exists(thumb):
            self.set_cover_art(thumb)

        self.song_list  = sorted(glob.glob(os.path.join(LIBRARY_DIR,"*.m4a")) +
                                 glob.glob(os.path.join(LIBRARY_DIR,"*.mp3")))
        self.song_index = self.song_list.index(os.path.join(LIBRARY_DIR, song))
        self.heart_btn.configure(image=self.heart_full if song in self.favorites else self.heart_empty)
        self.pp_btn.configure(image=self.pause_img)

        def runner():
            if self.current_process and self.current_process.poll() is None:
                self.current_process.terminate()
            sock = "/tmp/mpvsocket"
            if os.path.exists(sock):
                os.remove(sock)
            self.current_process = subprocess.Popen([
                "mpv","--no-video",f"--volume={self.volume_level}",
                f"--input-ipc-server={sock}",
                os.path.join(LIBRARY_DIR, song)
            ])
            self.mpv = MPVController(sock)
            self.update_seek_loop()

        threading.Thread(target=runner).start()


    # --- Update Seek Bar Continuously ---
    def update_seek_loop(self):
        def loop():
            while self.current_process and self.current_process.poll() is None:
                pos = self.mpv.get_property("time-pos")
                dur = self.mpv.get_property("duration")
                if pos and dur:
                    frac = float(pos) / float(dur)
                    self.current_duration = float(dur)
                    self.seek_canvas.delete("prog")
                    w = int(frac * self.seek_canvas.winfo_width())
                    self.seek_canvas.create_rectangle(0, 0, w, 8, fill="#FFD369", tags="prog")
                time.sleep(0.5)
        threading.Thread(target=loop, daemon=True).start()


    # --- Animate New Cover Art ---
    def set_cover_art(self, image_path):
        orig = Image.open(image_path)
        for size in (20, 40, 60, 80):
            img = orig.resize((size, size), Image.LANCZOS)
            ctk_img = CTkImage(light_image=img, size=(size, size))
            self.cover_img_label.configure(image=ctk_img)
            self.cover_img_label.image = ctk_img
            self.update()
            time.sleep(0.05)


    # --- Seek To Click Position ---
    def seek_to_position(self, event):
        if self.current_duration > 0:
            frac = event.x / self.seek_canvas.winfo_width()
            self.mpv.set_property("time-pos", frac * self.current_duration)


    # --- Play/Pause Toggle ---
    def toggle_play(self):
        self.is_paused = not self.is_paused
        self.mpv.set_property("pause", self.is_paused)
        self.pp_btn.configure(image=self.play_img if self.is_paused else self.pause_img)


    # --- Skip Forward/Back ---
    def adjust_position(self, seconds):
        if self.current_process and self.current_process.poll() is None:
            pos = self.mpv.get_property("time-pos")
            if pos is not None:
                self.mpv.set_property("time-pos", max(0, float(pos) + seconds))


    # --- Volume Control ---
    def change_volume(self, val):
        self.volume_level = max(0, min(100, int(val)))
        self.vol_slider.set(self.volume_level)
        self.mpv.set_property("volume", self.volume_level)


    # --- Previous / Next Song ---
    def prev_song(self):
        if self.song_list:
            self.song_index = (self.song_index - 1) % len(self.song_list)
            self.play_song(os.path.basename(self.song_list[self.song_index]))


    def next_song(self):
        if self.song_list:
            self.song_index = (self.song_index + 1) % len(self.song_list)
            self.play_song(os.path.basename(self.song_list[self.song_index]))


    # --- Theme Toggle ---
    def toggle_theme(self):
        mode = ctk.get_appearance_mode().lower()
        new  = "light" if mode == "dark" else "dark"
        ctk.set_appearance_mode(new)
        ico = self.icon_sun if new=="light" else self.icon_moon
        self.theme_btn.configure(image=ico)


    # --- Home Tab UI ---
    def show_home(self):
        self.title_label.configure(text="Home")
        for w in self.content_frame.winfo_children():
            w.destroy()

        logo = os.path.join(ART_DIR, "officiallogo.png")
        if os.path.exists(logo):
            img = CTkImage(light_image=Image.open(logo), size=(300, 300))
            lbl = ctk.CTkLabel(self.content_frame, image=img, text="")
            lbl.image = img
            lbl.pack(pady=20)

        entry = ctk.CTkEntry(
            self.content_frame,
            placeholder_text="Paste YouTube URL…",
            textvariable=self.url_var,
            width=500,
            font=self.button_font
        )
        entry.pack(pady=(10,5))
        entry.bind("<Button-3>", lambda ev: entry.insert(tk.INSERT, self.clipboard_get()))

        btn_frame = ctk.CTkFrame(self.content_frame, fg_color="#1e1e1e")
        btn_frame.pack(pady=(0,20))
        ctk.CTkButton(
            btn_frame, text="▶ Play URL", font=self.button_font,
            command=self.play_url, width=120
        ).pack(side="left", padx=10)
        ctk.CTkButton(
            btn_frame, text="💾 Download", font=self.button_font,
            command=self.download_audio, width=120
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            self.content_frame,
            text="Enter a YouTube URL to play or save to your library.",
            text_color="#aaa",
            font=self.button_font
        ).pack(pady=10)


    # --- Library Tab UI ---
    def show_library(self):
        self.title_label.configure(text="Library")
        for w in self.content_frame.winfo_children():
            w.destroy()

        entry = ctk.CTkEntry(
            self.content_frame,
            placeholder_text="Paste URL…",
            textvariable=self.url_var,
            width=500,
            font=self.button_font
        )
        entry.pack(pady=(10,5))
        entry.bind("<Button-3>", lambda ev: entry.insert(tk.INSERT, self.clipboard_get()))

        btn_frame = ctk.CTkFrame(self.content_frame, fg_color="#1e1e1e")
        btn_frame.pack(pady=(0,5))
        ctk.CTkButton(
            btn_frame, text="▶ Play URL", font=self.button_font,
            command=self.play_url, width=120
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="💾 Download", font=self.button_font,
            command=self.download_audio, width=120
        ).pack(side="left", padx=5)

        search = ctk.CTkEntry(
            self.content_frame,
            placeholder_text="Search library…",
            textvariable=self.search_var_lib,
            width=300,
            font=self.button_font
        )
        search.pack(pady=(5,10))
        search.bind("<KeyRelease>", lambda e: self.filter_library())

        self.lib_buttons = []
        for fp in sorted(
            glob.glob(os.path.join(LIBRARY_DIR,"*.m4a")) +
            glob.glob(os.path.join(LIBRARY_DIR,"*.mp3"))
        ):
            a, t = extract_metadata(os.path.basename(fp))
            btn = ctk.CTkButton(
                self.content_frame,
                text=f"{a} — {t}",
                font=self.button_font,
                command=lambda x=os.path.basename(fp): self.play_song(x),
                fg_color="#333",
                hover_color="#444",
                text_color="#fff",
                width=600,
                anchor="w"
            )
            btn.pack(pady=2)
            self.lib_buttons.append((btn, (a+" "+t).lower()))


    def filter_library(self):
        term = self.search_var_lib.get().lower()
        for btn, txt in self.lib_buttons:
            btn.pack(pady=2) if term in txt else btn.pack_forget()


    # --- Favorites Tab UI ---
    def show_favorites(self):
        self.title_label.configure(text="Favorites")
        for w in self.content_frame.winfo_children():
            w.destroy()

        search = ctk.CTkEntry(
            self.content_frame,
            placeholder_text="Search favorites…",
            textvariable=self.search_var_fav,
            width=300,
            font=self.button_font
        )
        search.pack(pady=(10,10))
        search.bind("<KeyRelease>", lambda e: self.filter_favorites())

        self.fav_buttons = []
        for f in sorted(self.favorites):
            row = ctk.CTkFrame(self.content_frame, fg_color="#1e1e1e")
            row.pack(fill="x", pady=2, padx=5)
            a, t = extract_metadata(f)
            ctk.CTkButton(
                row, text=f"{a} — {t}", font=self.button_font,
                command=lambda x=f: self.play_song(x),
                fg_color="#222", hover_color="#333",
                text_color="#FFD369", anchor="w"
            ).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(
                row, image=self.icon_trash, text="", width=32,
                fg_color="#550000", hover_color="#770000",
                command=lambda x=f: self.remove_favorite(x)
            ).pack(side="right", padx=5)
            self.fav_buttons.append((row, (a+" "+t).lower()))


    def filter_favorites(self):
        term = self.search_var_fav.get().lower()
        for row, txt in self.fav_buttons:
            row.pack(fill="x", pady=2, padx=5) if term in txt else row.pack_forget()


    def remove_favorite(self, song):
        if song in self.favorites:
            self.favorites.remove(song)
            self.save_favorites()
            self.show_favorites()


    # --- Playlists Tab UI ---
    def show_playlists(self):
        self.title_label.configure(text="Playlists")
        for w in self.content_frame.winfo_children():
            w.destroy()

        for pf in sorted(f for f in os.listdir(PLAYLISTS_DIR) if f.endswith(".playlist")):
            name = pf[:-9]
            row = ctk.CTkFrame(self.content_frame, fg_color="#1e1e1e")
            row.pack(fill="x", pady=2, padx=5)
            ctk.CTkButton(
                row, text=name, font=self.button_font,
                command=lambda n=name: self.load_playlist(n),
                fg_color="#333", hover_color="#444",
                text_color="#fff", anchor="w"
            ).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(
                row, image=self.icon_trash, text="", width=32,
                fg_color="#550000", hover_color="#770000",
                command=lambda n=name: self.delete_playlist(n)
            ).pack(side="right", padx=5)

        entry = ctk.CTkEntry(
            self.content_frame, placeholder_text="New Playlist Name",
            width=400, font=self.button_font
        )
        entry.pack(pady=10)
        def save_new():
            n = entry.get().strip()
            if n:
                with open(os.path.join(PLAYLISTS_DIR, f"{n}.playlist"), "w") as f:
                    for full in self.song_list:
                        f.write(os.path.basename(full) + "\n")
                self.show_playlists()
        ctk.CTkButton(
            self.content_frame, text="💾 Save Playlist",
            font=self.button_font, command=save_new, width=200
        ).pack(pady=5)


    def delete_playlist(self, name):
        try:
            os.remove(os.path.join(PLAYLISTS_DIR, f"{name}.playlist"))
        except:
            pass
        self.show_playlists()


    def load_playlist(self, name):
        path = os.path.join(PLAYLISTS_DIR, f"{name}.playlist")
        if not os.path.exists(path):
            return
        basenames = [l.strip() for l in open(path) if l.strip()]
        fulls     = [os.path.join(LIBRARY_DIR, b) for b in basenames
                     if os.path.exists(os.path.join(LIBRARY_DIR, b))]
        if not fulls:
            return
        self.song_list  = fulls
        self.song_index = 0
        self.display_playlist([os.path.basename(p) for p in fulls])


    def display_playlist(self, names):
        # remove all except the Save-entry/Button
        for w in self.content_frame.winfo_children():
            if isinstance(w, ctk.CTkEntry): continue
            if isinstance(w, ctk.CTkButton) and w.cget("text") == "💾 Save Playlist":
                continue
            w.destroy()

        for i, b in enumerate(names):
            row = ctk.CTkFrame(self.content_frame, fg_color="#1e1e1e")
            row.pack(fill="x", pady=2, padx=5)
            ctk.CTkButton(
                row, image=self.icon_up, text="", width=24,
                command=lambda i=i: self.swap_playlist(i, i-1)
            ).pack(side="left")
            ctk.CTkButton(
                row, image=self.icon_down, text="", width=24,
                command=lambda i=i: self.swap_playlist(i, i+1)
            ).pack(side="left")
            a, t = extract_metadata(b)
            ctk.CTkButton(
                row, text=f"{a} — {t}", font=self.button_font,
                command=lambda x=b: self.play_song(x),
                fg_color="#222", hover_color="#333",
                text_color="#00F0FF", anchor="w"
            ).pack(side="left", fill="x", expand=True)


    def swap_playlist(self, i, j):
        if 0 <= i < len(self.song_list) and 0 <= j < len(self.song_list):
            self.song_list[i], self.song_list[j] = self.song_list[j], self.song_list[i]
            self.display_playlist([os.path.basename(p) for p in self.song_list])


    def save_favorites(self):
        with open(FAVORITES_FILE, "w") as f:
            for s in self.favorites:
                f.write(s + "\n")


    def toggle_favorite(self):
        if not self.current_song:
            return
        if self.current_song in self.favorites:
            self.favorites.remove(self.current_song)
            self.heart_btn.configure(image=self.heart_empty)
        else:
            self.favorites.add(self.current_song)
            self.heart_btn.configure(image=self.heart_full)
        self.save_favorites()


if __name__ == "__main__":
    try:
        app = FOGRPlayer()
        app.mainloop()
    except Exception as e:
        print("❌ Startup error:", e)

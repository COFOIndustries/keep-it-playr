import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))

# Drag-and-Drop support via tkinterdnd2
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    print("❌ Missing tkinterdnd2. Run: pip3 install tkinterdnd2")
    sys.exit(1)

import threading, glob, re, shutil, subprocess, requests

from tkinter import simpledialog, messagebox, Menu
import tkinter as tk
import customtkinter as ctk
from customtkinter import CTkFont, CTkImage, CTkOptionMenu
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
    base = os.path.splitext(os.path.basename(filename))[0]
    parts = re.split(r" - |_", base)
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return "Unknown Artist", base


def fetch_youtube_thumbnail(url, dest=ART_DIR):
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
    except Exception:
        return None


class FOGRPlayer(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.title("KEEP-IT PLAYR")
        self.geometry("1200x750")
        self.minsize(800, 600)

        # Fonts & Icons
        self.title_font  = CTkFont(family="Akira Jimbo", size=24, weight="bold")
        self.button_font = CTkFont(family="Akira Jimbo", size=14)
        self.option_font = CTkFont(family="Akira Jimbo", size=12)
        self.option_add("*Font", self.button_font)
        self.icon_sun    = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, "sun.png")),  size=(20,20))
        self.icon_moon   = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, "moon.png")), size=(20,20))
        self.icon_up     = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, "up.png")),    size=(16,16))
        self.icon_down   = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, "down.png")),  size=(16,16))

        # State & Controller
        self.url_var        = ctk.StringVar()
        self.search_var_lib = ctk.StringVar()
        self.playlist_var   = ctk.StringVar()
        self.mpv            = MPVController()
        self.favorites      = set()

        # Ensure data dirs
        os.makedirs(LIBRARY_DIR,  exist_ok=True)
        os.makedirs(PLAYLISTS_DIR, exist_ok=True)
        os.makedirs(ART_DIR,       exist_ok=True)
        if os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE) as f:
                self.favorites = set(line.strip() for line in f)

        # Drag & Drop
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self.handle_drop)

        # Build UI
        self.build_sidebar()
        self.build_main_area()
        self.build_playback_bar()
        self.show_library()

        # Shortcuts
        self.bind("<space>", lambda e: self.toggle_play())
        self.bind("<Left>",  lambda e: self.adjust_position(-10))
        self.bind("<Right>", lambda e: self.adjust_position(10))
        self.bind("<Up>",    lambda e: self.change_volume(self.mpv.get_volume()+5))
        self.bind("<Down>",  lambda e: self.change_volume(self.mpv.get_volume()-5))

    def on_close(self):
        self.mpv.stop()
        self.destroy()

    def handle_drop(self, event):
        for fp in self.tk.splitlist(event.data):
            if fp.lower().endswith((".mp3", ".m4a")):
                shutil.copy(fp, os.path.join(LIBRARY_DIR, os.path.basename(fp)))
        self.show_library()

    def play_url(self):
        url = self.url_var.get().strip()
        if not url: return
        def runner():
            try:
                title = subprocess.check_output(["yt-dlp","--get-title",url]).decode().strip()
                safe  = re.sub(r'[\\/*?:"<>|]',"_", title)
                fn    = f"{safe}.m4a"
                path  = os.path.join(LIBRARY_DIR, fn)
                subprocess.run([
                    "yt-dlp","-f","bestaudio","--extract-audio",
                    "--audio-format","m4a","-o",path,url
                ], check=True)
                thumb = fetch_youtube_thumbnail(url)
                if thumb: self.set_cover_art(thumb)
                self.play_song(fn)
            except Exception as e:
                print("❌", e)
        threading.Thread(target=runner, daemon=True).start()

    def download_audio(self):
        self.play_url()  # same logic minus auto-play

    def get_playlists(self):
        return sorted(f[:-9] for f in os.listdir(PLAYLISTS_DIR) if f.endswith(".playlist"))

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
            img = CTkImage(light_image=Image.open(os.path.join(ICONS_DIR, icon_file)), size=(20,20))
            btn = ctk.CTkButton(sb, text=label, image=img, compound="left",
                                fg_color="#222", hover_color="#333",
                                text_color="#FFD369", font=self.button_font,
                                corner_radius=5, height=40, command=cmd)
            btn.pack(fill="x", pady=5, padx=10)
        self.theme_btn = ctk.CTkButton(sb, image=self.icon_sun, text="",
                                        fg_color="#222", hover_color="#333",
                                        command=self.toggle_theme)
        self.theme_btn.pack(fill="x", pady=20, padx=10)

    def build_main_area(self):
        self.main_frame = ctk.CTkFrame(self, fg_color="#1e1e1e")
        self.main_frame.pack(side="top", fill="both", expand=True)
        self.title_label = ctk.CTkLabel(self.main_frame, text="Now Playing",
                                        font=self.title_font, text_color="#FFD369")
        self.title_label.pack(pady=10)
        self.content_frame = ctk.CTkScrollableFrame(self.main_frame, fg_color="#1e1e1e")
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=10)

    def build_playback_bar(self):
        # Placeholder for playback controls
        pass

    def show_library(self):
        self.title_label.configure(text="Library")
        for w in self.content_frame.winfo_children(): w.destroy()
        search = ctk.CTkEntry(self.content_frame, placeholder_text="Search…",
                                textvariable=self.search_var_lib,
                                width=300, font=self.button_font)
        search.pack(pady=(5,10)); search.bind("<KeyRelease>", lambda e: self.filter_library())
        self.lib_buttons = []
        for fp in sorted(glob.glob(os.path.join(LIBRARY_DIR,"*.m4a"))+glob.glob(os.path.join(LIBRARY_DIR,"*.mp3"))):
            fn = os.path.basename(fp); a,t = extract_metadata(fn)
            btn = ctk.CTkButton(self.content_frame, text=f"{a} — {t}",
                                font=self.button_font, fg_color="#333",
                                hover_color="#444", text_color="#fff",
                                width=600, anchor="w",
                                command=lambda x=fn: self.play_song(x))
            btn.pack(pady=2); btn.bind("<Button-3>", lambda e,x=fn: self.show_song_context_menu(e,x))
            self.lib_buttons.append((btn,(a+" "+t).lower()))

    def filter_library(self):
        term = self.search_var_lib.get().lower()
        for btn, txt in self.lib_buttons:
            btn.pack() if term in txt else btn.pack_forget()

    def show_playlists(self):
        self.title_label.configure(text="Playlists")
        for w in self.content_frame.winfo_children(): w.destroy()
        pls = self.get_playlists(); self.playlist_var.set("Select playlist")
        dropdown = CTkOptionMenu(self.content_frame, values=pls,
                                 variable=self.playlist_var,
                                 font=self.option_font,
                                 command=self.load_playlist)
        dropdown.pack(pady=(10,5))
        entry = ctk.CTkEntry(self.content_frame, placeholder_text="New Playlist Name",
                             width=400, font=self.button_font); entry.pack(pady=(10,5))
        def save_new():
            n=entry.get().strip();
            if not n: return
            path=os.path.join(PLAYLISTS_DIR, f"{n}.playlist");
            with open(path,"w"): pass
            entry.delete(0,"end"); dropdown.configure(values=self.get_playlists())
        ctk.CTkButton(self.content_frame, text="💾 Save Playlist",
                      font=self.button_font, command=save_new, width=200).pack(pady=(0,10))

    def delete_playlist(self, name):
        path=os.path.join(PLAYLISTS_DIR, f"{name}.playlist");
        try: os.remove(path)
        except OSError: pass
        self.show_playlists()

    def load_playlist(self, name):
        path=os.path.join(PLAYLISTS_DIR, f"{name}.playlist")
        if not os.path.exists(path): return
        bas=[l.strip() for l in open(path) if l.strip()]
        fulls=[os.path.join(LIBRARY_DIR,b) for b in bas if os.path.exists(os.path.join(LIBRARY_DIR,b))]
        if not fulls: return
        self.song_list, self.song_index = fulls, 0
        self.title_label.configure(text=name)
        self.display_playlist([os.path.basename(p) for p in fulls])

    def display_playlist(self, names):
        for w in self.content_frame.winfo_children():
            if isinstance(w, CTkOptionMenu): continue
            if isinstance(w, ctk.CTkEntry) and w.cget("placeholder_text").startswith("New"): continue
            if isinstance(w, ctk.CTkButton) and w.cget("text")=="💾 Save Playlist": continue
            w.destroy()
        for i,b in enumerate(names):
            row=ctk.CTkFrame(self.content_frame, fg_color="#1e1e1e"); row.pack(fill="x",pady=2,padx=5)
            ctk.CTkButton(row,image=self.icon_up,text="",width=24,
                          command=lambda i=i:self.swap_playlist(i,i-1)).pack(side="left")
            ctk.CTkButton(row,image=self.icon_down,text="",width=24,
                          command=lambda i=i:self.swap_playlist(i,i+1)).pack(side="left")
            a,t=extract_metadata(b)
            ctk.CTkButton(row,text=f"{a} — {t}",font=self.button_font,
                          fg_color="#222",hover_color="#333",
                          text_color="#00F0FF",anchor="w",
                          command=lambda x=b:self.play_song(x)
            ).pack(side="left",fill="x",expand=True)

    def swap_playlist(self, i, j):
        if 0<=i<len(self.song_list) and 0<=j<len(self.song_list):
            self.song_list[i],self.song_list[j]=self.song_list[j],self.song_list[i]
            self.display_playlist([os.path.basename(p) for p in self.song_list])

    # --- New stubs to satisfy sidebar callbacks ---
    def show_home(self):
        self.title_label.configure(text="Home")
        for w in self.content_frame.winfo_children(): w.destroy()
        frame=ctk.CTkFrame(self.content_frame, fg_color="#1e1e1e"); frame.pack(pady=20)
        ctk.CTkEntry(frame, width=600, placeholder_text="YouTube URL...", textvariable=self.url_var).pack(side="left",padx=5)
        ctk.CTkButton(frame, text="▶️ Play URL", command=self.play_url).pack(side="left",padx=5)
        ctk.CTkButton(frame, text="⬇️ Download Audio", command=self.download_audio).pack(side="left",padx=5)

    def show_favorites(self):
        self.title_label.configure(text="Favorites")
        for w in self.content_frame.winfo_children(): w.destroy()
        if not self.favorites:
            ctk.CTkLabel(self.content_frame, text="No favorites yet.", font=self.button_font).pack(pady=20)
            return
        for song in sorted(self.favorites):
            ctk.CTkButton(self.content_frame, text=song, width=600, anchor="w",
                          command=lambda x=song:self.play_song(x)
            ).pack(pady=2)

    def toggle_theme(self):
        mode="light" if ctk.get_appearance_mode()=="dark" else "dark"
        ctk.set_appearance_mode(mode)
        ico=self.icon_sun if mode=="dark" else self.icon_moon
        self.theme_btn.configure(image=ico)

if __name__ == "__main__":
    try:
        app = FOGRPlayer()
        app.mainloop()
    except Exception as e:
        print("❌ Startup error:", e)

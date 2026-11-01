import sys
import os
import json
import getpass
import subprocess
import time
import winreg
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import win32gui
import win32con
import win32process
import requests
import websocket

APP_NAME = "Мандарин"
HOME_URL = "https://mandarin.deploya.ru/"  # ТВОЙ САЙТ!
PROFILE_DIR = Path.home() / ".mandarin"
SETTINGS_FILE = PROFILE_DIR / "settings.json"

ORANGE = "#F57C00"
ORANGE_DARK = "#E65100"
ORANGE_DEEP = "#BF360C"
WHITE = "#FFFFFF"
CREAM = "#FFF3E0"
TEXT = "#4E2A00"
SERIF = "Georgia"

SEARCH_ENGINES = {
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q="),
    "google": ("Google", "https://www.google.com/search?q="),
    "yandex": ("Яндекс", "https://yandex.ru/search/?text="),
}
DEFAULT_SETTINGS = {"search": "duckduckgo", "theme": "light"}

class Settings:
    def __init__(self):
        self.data = dict(DEFAULT_SETTINGS)
        try:
            loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.data.update(loaded)
        except Exception: self._save()
    def _save(self):
        try:
            PROFILE_DIR.mkdir(exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception: pass
    def get(self, key, default=None): return self.data.get(key, default)
    def set(self, key, value): self.data[key] = value; self._save()
    @property
    def search_prefix(self): return SEARCH_ENGINES[self.get("search", "duckduckgo")][1]

class Profile:
    def __init__(self):
        try:
            self.data = json.loads((PROFILE_DIR/"profile.json").read_text(encoding="utf-8"))
        except Exception:
            self.data = {"name": self._sysname()}
            PROFILE_DIR.mkdir(exist_ok=True)
            (PROFILE_DIR/"profile.json").write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
    def _sysname(self):
        try: return getpass.getuser()
        except Exception: return "Гость"
    @property
    def name(self): return self.data["name"]

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Настройки")
        self.geometry("400x280")
        self.configure(fg_color=CREAM)
        self.grab_set()
        f = ctk.CTkFont(family=SERIF, size=14)
        ctk.CTkLabel(self, text="⚙ Настройки", font=(SERIF,18,"bold"), text_color=ORANGE_DARK).pack(pady=15)
        body = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=16); body.pack(fill="both", expand=True, padx=16, pady=10)
        row = ctk.CTkFrame(body, fg_color="transparent"); row.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(row, text="Поисковик:", font=f, text_color=TEXT).pack(side="left")
        self.search_var = tk.StringVar(value=self.app.settings.get("search", "duckduckgo"))
        ctk.CTkOptionMenu(row, values=list(SEARCH_ENGINES.keys()), variable=self.search_var, fg_color=ORANGE, button_color=ORANGE_DARK).pack(side="right")
        ctk.CTkButton(self, text="Сохранить", fg_color=ORANGE, hover_color=ORANGE_DARK, command=self._save).pack(pady=10)
    def _save(self):
        self.app.settings.set("search", self.search_var.get())
        self.app.apply_settings()
        self.destroy()

class ChromeEngine:
    def __init__(self, parent_hwnd, start_url):
        self.parent_hwnd = parent_hwnd
        self.process = None
        self.ws = None
        self.ws_id = 1
        self.port = 9222
        self._launch_chrome(start_url)

    def _find_chrome(self):
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in paths:
            if os.path.isfile(p): return p
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            path, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            if os.path.isfile(path): return path
        except Exception: pass
        return None

    def _launch_chrome(self, url):
        chrome_path = self._find_chrome()
        if not chrome_path:
            raise Exception("Google Chrome не найден на компьютере!")

        cmd = [
            chrome_path,
            f"--app={url}",
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={PROFILE_DIR / 'chrome_profile'}",
            "--window-size=1000,700",
            "--window-position=-3000,-3000"
        ]
        self.process = subprocess.Popen(cmd)
        time.sleep(2)
        self._embed_window()

    def _embed_window(self):
        def enum_cb(hwnd, results):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == self.process.pid:
                results.append(hwnd)
            return True
        
        hwnds = []
        win32gui.EnumWindows(enum_cb, hwnds)

        if not hwnds:
            raise Exception("Окно Хрома не найдено")

        chrome_hwnd = hwnds[0]
        style = win32gui.GetWindowLong(chrome_hwnd, win32con.GWL_STYLE)
        style = style & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME
        win32gui.SetWindowLong(chrome_hwnd, win32con.GWL_STYLE, style)
        win32gui.SetParent(chrome_hwnd, self.parent_hwnd)
        win32gui.MoveWindow(chrome_hwnd, 0, 0, 1000, 700, True)
        self.hwnd = chrome_hwnd

    def resize(self, w, h):
        if hasattr(self, 'hwnd'):
            win32gui.MoveWindow(self.hwnd, 0, 0, w, h, True)

    def _connect_cdp(self):
        try:
            res = requests.get(f"http://127.0.0.1:{self.port}/json")
            tabs = res.json()
            if tabs:
                ws_url = tabs[0]["webSocketDebuggerUrl"]
                self.ws = websocket.create_connection(ws_url)
        except Exception as e:
            print("CDP connect error:", e)

    def navigate(self, url):
        if not self.ws:
            self._connect_cdp()
        if self.ws:
            msg = {"id": self.ws_id, "method": "Page.navigate", "params": {"url": url}}
            self.ws.send(json.dumps(msg))
            self.ws_id += 1

    def go_back(self):
        if self.ws:
            self.ws.send(json.dumps({"id": self.ws_id, "method": "Page.goBack"}))
            self.ws_id += 1

    def go_forward(self):
        if self.ws:
            self.ws.send(json.dumps({"id": self.ws_id, "method": "Page.goForward"}))
            self.ws_id += 1

    def reload(self):
        if self.ws:
            self.ws.send(json.dumps({"id": self.ws_id, "method": "Page.reload"}))
            self.ws_id += 1

    def close(self):
        if self.process:
            self.process.terminate()

class Browser(ctk.CTk):
    def __init__(self):
        ctk.ScalingTracker.deactivate_automatic_dpi_awareness = True
        self.settings = Settings()
        ctk.set_appearance_mode(self.settings.get("theme", "light"))
        super().__init__(fg_color=CREAM)
        
        self.profile = Profile()
        self.title(APP_NAME)
        self.geometry("1200x800")
        self.minsize(800, 500)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self.engine = None
        
        f_btn = ctk.CTkFont(family=SERIF, size=18, weight="bold")
        f_txt = ctk.CTkFont(family=SERIF, size=14)
        
        bar = ctk.CTkFrame(self, fg_color=ORANGE, corner_radius=20)
        bar.pack(fill="x", padx=10, pady=(10, 5))
        
        def rbtn(text, cmd):
            return ctk.CTkButton(bar, text=text, command=cmd, width=38, height=38, corner_radius=19, font=f_btn, fg_color=ORANGE_DARK, hover_color=ORANGE_DEEP, text_color=WHITE)
        
        rbtn("←", self.go_back).pack(side="left", padx=(10, 2), pady=8)
        rbtn("→", self.go_forward).pack(side="left", padx=2)
        rbtn("⟳", self.reload).pack(side="left", padx=2)
        rbtn("⌂", lambda: self.navigate(HOME_URL)).pack(side="left", padx=2)
        rbtn("⚙", lambda: SettingsDialog(self)).pack(side="left", padx=2)
        
        self.url_var = tk.StringVar()
        entry = ctk.CTkEntry(bar, textvariable=self.url_var, height=38, corner_radius=19, border_width=0, fg_color=WHITE, text_color=TEXT, font=f_txt, placeholder_text="Поиск или адрес")
        entry.pack(side="left", fill="x", expand=True, padx=8, pady=8)
        entry.bind("<Return>", lambda e: self.navigate(self.url_var.get()))
        ctk.CTkButton(bar, text="Найти", command=lambda: self.navigate(self.url_var.get()), width=80, height=38, corner_radius=19, font=f_txt, fg_color=WHITE, hover_color=CREAM, text_color=ORANGE_DARK).pack(side="right", padx=(0, 10))
        
        self.browser_frame = tk.Frame(self, bg=WHITE)
        self.browser_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        self.browser_frame.bind("<Configure>", self._on_resize)
        
        self.after(500, self._init_engine)

    def _init_engine(self):
        try:
            self.engine = ChromeEngine(self.browser_frame.winfo_id(), HOME_URL)
        except Exception as e:
            messagebox.showerror("Ошибка запуска", str(e))
            self.destroy()

    def _on_resize(self, event=None):
        if self.engine:
            w = self.browser_frame.winfo_width()
            h = self.browser_frame.winfo_height()
            self.engine.resize(w, h)

    def normalize(self, text):
        text = text.strip()
        if not text: return HOME_URL
        if " " in text or ("." not in text and "://" not in text):
            return self.settings.search_prefix + text.replace(" ", "+")
        if not text.startswith(("http://", "https://", "file://")): text = "https://" + text
        return text

    def navigate(self, text):
        url = self.normalize(text)
        self.url_var.set(url if url != HOME_URL else "")
        if self.engine:
            self.engine.navigate(url)

    def go_back(self):
        if self.engine: self.engine.go_back()

    def go_forward(self):
        if self.engine: self.engine.go_forward()

    def reload(self):
        if self.engine: self.engine.reload()

    def apply_settings(self):
        ctk.set_appearance_mode(self.settings.get("theme", "light"))
        self.navigate(HOME_URL)

    def _on_close(self):
        if self.engine:
            self.engine.close()
        self.destroy()

if __name__ == "__main__":
    app = Browser()
    app.mainloop()import sys
import os
import json
import getpass
import subprocess
import time
import winreg
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import win32gui
import win32con
import win32process
import requests
import websocket

APP_NAME = "Мандарин"
HOME_URL = "https://mandarin.deploya.ru/"  # ТВОЙ САЙТ!
PROFILE_DIR = Path.home() / ".mandarin"
SETTINGS_FILE = PROFILE_DIR / "settings.json"

ORANGE = "#F57C00"
ORANGE_DARK = "#E65100"
ORANGE_DEEP = "#BF360C"
WHITE = "#FFFFFF"
CREAM = "#FFF3E0"
TEXT = "#4E2A00"
SERIF = "Georgia"

SEARCH_ENGINES = {
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q="),
    "google": ("Google", "https://www.google.com/search?q="),
    "yandex": ("Яндекс", "https://yandex.ru/search/?text="),
}
DEFAULT_SETTINGS = {"search": "duckduckgo", "theme": "light"}

class Settings:
    def __init__(self):
        self.data = dict(DEFAULT_SETTINGS)
        try:
            loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.data.update(loaded)
        except Exception: self._save()
    def _save(self):
        try:
            PROFILE_DIR.mkdir(exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception: pass
    def get(self, key, default=None): return self.data.get(key, default)
    def set(self, key, value): self.data[key] = value; self._save()
    @property
    def search_prefix(self): return SEARCH_ENGINES[self.get("search", "duckduckgo")][1]

class Profile:
    def __init__(self):
        try:
            self.data = json.loads((PROFILE_DIR/"profile.json").read_text(encoding="utf-8"))
        except Exception:
            self.data = {"name": self._sysname()}
            PROFILE_DIR.mkdir(exist_ok=True)
            (PROFILE_DIR/"profile.json").write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
    def _sysname(self):
        try: return getpass.getuser()
        except Exception: return "Гость"
    @property
    def name(self): return self.data["name"]

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Настройки")
        self.geometry("400x280")
        self.configure(fg_color=CREAM)
        self.grab_set()
        f = ctk.CTkFont(family=SERIF, size=14)
        ctk.CTkLabel(self, text="⚙ Настройки", font=(SERIF,18,"bold"), text_color=ORANGE_DARK).pack(pady=15)
        body = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=16); body.pack(fill="both", expand=True, padx=16, pady=10)
        row = ctk.CTkFrame(body, fg_color="transparent"); row.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(row, text="Поисковик:", font=f, text_color=TEXT).pack(side="left")
        self.search_var = tk.StringVar(value=self.app.settings.get("search", "duckduckgo"))
        ctk.CTkOptionMenu(row, values=list(SEARCH_ENGINES.keys()), variable=self.search_var, fg_color=ORANGE, button_color=ORANGE_DARK).pack(side="right")
        ctk.CTkButton(self, text="Сохранить", fg_color=ORANGE, hover_color=ORANGE_DARK, command=self._save).pack(pady=10)
    def _save(self):
        self.app.settings.set("search", self.search_var.get())
        self.app.apply_settings()
        self.destroy()

class ChromeEngine:
    def __init__(self, parent_hwnd, start_url):
        self.parent_hwnd = parent_hwnd
        self.process = None
        self.ws = None
        self.ws_id = 1
        self.port = 9222
        self._launch_chrome(start_url)

    def _find_chrome(self):
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in paths:
            if os.path.isfile(p): return p
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            path, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            if os.path.isfile(path): return path
        except Exception: pass
        return None

    def _launch_chrome(self, url):
        chrome_path = self._find_chrome()
        if not chrome_path:
            raise Exception("Google Chrome не найден на компьютере!")

        cmd = [
            chrome_path,
            f"--app={url}",
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={PROFILE_DIR / 'chrome_profile'}",
            "--window-size=1000,700",
            "--window-position=-3000,-3000"
        ]
        self.process = subprocess.Popen(cmd)
        time.sleep(2)
        self._embed_window()

    def _embed_window(self):
        def enum_cb(hwnd, results):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == self.process.pid:
                results.append(hwnd)
            return True
        
        hwnds = []
        win32gui.EnumWindows(enum_cb, hwnds)

        if not hwnds:
            raise Exception("Окно Хрома не найдено")

        chrome_hwnd = hwnds[0]
        style = win32gui.GetWindowLong(chrome_hwnd, win32con.GWL_STYLE)
        style = style & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME
        win32gui.SetWindowLong(chrome_hwnd, win32con.GWL_STYLE, style)
        win32gui.SetParent(chrome_hwnd, self.parent_hwnd)
        win32gui.MoveWindow(chrome_hwnd, 0, 0, 1000, 700, True)
        self.hwnd = chrome_hwnd

    def resize(self, w, h):
        if hasattr(self, 'hwnd'):
            win32gui.MoveWindow(self.hwnd, 0, 0, w, h, True)

    def _connect_cdp(self):
        try:
            res = requests.get(f"http://127.0.0.1:{self.port}/json")
            tabs = res.json()
            if tabs:
                ws_url = tabs[0]["webSocketDebuggerUrl"]
                self.ws = websocket.create_connection(ws_url)
        except Exception as e:
            print("CDP connect error:", e)

    def navigate(self, url):
        if not self.ws:
            self._connect_cdp()
        if self.ws:
            msg = {"id": self.ws_id, "method": "Page.navigate", "params": {"url": url}}
            self.ws.send(json.dumps(msg))
            self.ws_id += 1

    def go_back(self):
        if self.ws:
            self.ws.send(json.dumps({"id": self.ws_id, "method": "Page.goBack"}))
            self.ws_id += 1

    def go_forward(self):
        if self.ws:
            self.ws.send(json.dumps({"id": self.ws_id, "method": "Page.goForward"}))
            self.ws_id += 1

    def reload(self):
        if self.ws:
            self.ws.send(json.dumps({"id": self.ws_id, "method": "Page.reload"}))
            self.ws_id += 1

    def close(self):
        if self.process:
            self.process.terminate()

class Browser(ctk.CTk):
    def __init__(self):
        ctk.ScalingTracker.deactivate_automatic_dpi_awareness = True
        self.settings = Settings()
        ctk.set_appearance_mode(self.settings.get("theme", "light"))
        super().__init__(fg_color=CREAM)
        
        self.profile = Profile()
        self.title(APP_NAME)
        self.geometry("1200x800")
        self.minsize(800, 500)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self.engine = None
        
        f_btn = ctk.CTkFont(family=SERIF, size=18, weight="bold")
        f_txt = ctk.CTkFont(family=SERIF, size=14)
        
        bar = ctk.CTkFrame(self, fg_color=ORANGE, corner_radius=20)
        bar.pack(fill="x", padx=10, pady=(10, 5))
        
        def rbtn(text, cmd):
            return ctk.CTkButton(bar, text=text, command=cmd, width=38, height=38, corner_radius=19, font=f_btn, fg_color=ORANGE_DARK, hover_color=ORANGE_DEEP, text_color=WHITE)
        
        rbtn("←", self.go_back).pack(side="left", padx=(10, 2), pady=8)
        rbtn("→", self.go_forward).pack(side="left", padx=2)
        rbtn("⟳", self.reload).pack(side="left", padx=2)
        rbtn("⌂", lambda: self.navigate(HOME_URL)).pack(side="left", padx=2)
        rbtn("⚙", lambda: SettingsDialog(self)).pack(side="left", padx=2)
        
        self.url_var = tk.StringVar()
        entry = ctk.CTkEntry(bar, textvariable=self.url_var, height=38, corner_radius=19, border_width=0, fg_color=WHITE, text_color=TEXT, font=f_txt, placeholder_text="Поиск или адрес")
        entry.pack(side="left", fill="x", expand=True, padx=8, pady=8)
        entry.bind("<Return>", lambda e: self.navigate(self.url_var.get()))
        ctk.CTkButton(bar, text="Найти", command=lambda: self.navigate(self.url_var.get()), width=80, height=38, corner_radius=19, font=f_txt, fg_color=WHITE, hover_color=CREAM, text_color=ORANGE_DARK).pack(side="right", padx=(0, 10))
        
        self.browser_frame = tk.Frame(self, bg=WHITE)
        self.browser_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        self.browser_frame.bind("<Configure>", self._on_resize)
        
        self.after(500, self._init_engine)

    def _init_engine(self):
        try:
            self.engine = ChromeEngine(self.browser_frame.winfo_id(), HOME_URL)
        except Exception as e:
            messagebox.showerror("Ошибка запуска", str(e))
            self.destroy()

    def _on_resize(self, event=None):
        if self.engine:
            w = self.browser_frame.winfo_width()
            h = self.browser_frame.winfo_height()
            self.engine.resize(w, h)

    def normalize(self, text):
        text = text.strip()
        if not text: return HOME_URL
        if " " in text or ("." not in text and "://" not in text):
            return self.settings.search_prefix + text.replace(" ", "+")
        if not text.startswith(("http://", "https://", "file://")): text = "https://" + text
        return text

    def navigate(self, text):
        url = self.normalize(text)
        self.url_var.set(url if url != HOME_URL else "")
        if self.engine:
            self.engine.navigate(url)

    def go_back(self):
        if self.engine: self.engine.go_back()

    def go_forward(self):
        if self.engine: self.engine.go_forward()

    def reload(self):
        if self.engine: self.engine.reload()

    def apply_settings(self):
        ctk.set_appearance_mode(self.settings.get("theme", "light"))
        self.navigate(HOME_URL)

    def _on_close(self):
        if self.engine:
            self.engine.close()
        self.destroy()

if __name__ == "__main__":
    app = Browser()
    app.mainloop()

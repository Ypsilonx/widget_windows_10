"""Grafické okno widgetu – seznam projektů, vyhledávání, otevírání ve VS Code."""

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime

import customtkinter as ctk

from scanner import Project, find_projects
from settings_dialog import FolderSettingsDialog
from taskbar import show_in_taskbar

MIN_WIDTH = 220
MIN_HEIGHT = 280

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
EXAMPLE_CONFIG_PATH = os.path.join(BASE_DIR, "config.example.json")
ICON_PATH = os.path.join(BASE_DIR, "assets", "icon.ico")

# Hranice semaforu (ve dnech od poslední změny) a jim odpovídající barvy.
SEMAFOR_GREEN_DAYS = 7
SEMAFOR_YELLOW_DAYS = 30
SEMAFOR_COLORS = {"green": "#2ecc71", "yellow": "#f1c40f", "red": "#e74c3c"}


def load_config() -> dict:
    """Načte osobní config.json; pokud ještě neexistuje (čerstvý clone z GitHubu), založí ho ze šablony."""
    if not os.path.exists(CONFIG_PATH):
        shutil.copyfile(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config_data: dict) -> None:
    """Uloží config_data zpět do config.json (osobní, negitovaný soubor)."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)


def _semafor_color(last_modified: float) -> str:
    """Vrátí barvu tečky podle stáří poslední změny (zelená/žlutá/červená)."""
    days = (time.time() - last_modified) / 86400
    if days <= SEMAFOR_GREEN_DAYS:
        return SEMAFOR_COLORS["green"]
    if days <= SEMAFOR_YELLOW_DAYS:
        return SEMAFOR_COLORS["yellow"]
    return SEMAFOR_COLORS["red"]


def _format_date(last_modified: float) -> str:
    """Naformátuje unix timestamp na čitelné datum dd.mm.rrrr."""
    if last_modified <= 0:
        return "?"
    return datetime.fromtimestamp(last_modified).strftime("%d.%m.%Y")


class DashboardWidget(ctk.CTk):
    """Trvale zobrazené bezrámečkové okno v rohu obrazovky se seznamem projektů."""

    def __init__(self) -> None:
        super().__init__()
        self.config_data = load_config()
        self._all_projects: list[Project] = []
        self._drag_offset = (0, 0)
        self._scan_results: queue.Queue = queue.Queue()
        self._locked = bool(self.config_data["window"].get("locked", False))

        self._setup_window()
        self._build_ui()
        self.refresh_projects()

    def _setup_window(self) -> None:
        """Odstraní OS rámeček okna, umístí ho na uloženou pozici (je-li zamčeno) nebo do rohu a zařadí do taskbaru."""
        w_cfg = self.config_data["window"]
        self.title("Project Dashboard")
        self.overrideredirect(True)  # bez titulku a rámečku Windows
        self.attributes("-alpha", w_cfg.get("opacity", 1.0))

        position = w_cfg.get("position")
        if self._locked and position:
            x, y = position["x"], position["y"]
        else:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            margin_x = w_cfg.get("margin_x", 20)
            margin_y = w_cfg.get("margin_y", 20)
            corner = w_cfg.get("corner", "top-right")
            x = margin_x if "left" in corner else screen_w - w_cfg["width"] - margin_x
            y = margin_y if "top" in corner else screen_h - w_cfg["height"] - margin_y

        self.geometry(f"{w_cfg['width']}x{w_cfg['height']}+{x}+{y}")
        # Žádné "-topmost" – bez něj widget přirozeně zůstane v z-pořadí za jakýmkoliv
        # oknem, které aktivuješ (Windows to řeší samo), takže nikdy nepřekrývá práci.
        show_in_taskbar(self)
        # Ikona se nastavuje až po show_in_taskbar() (ten okno na moment schová/ukáže) –
        # jinak by taskbar stihl zaregistrovat tlačítko ještě s výchozí ikonou pythonu.
        self.after(50, lambda: self.iconbitmap(ICON_PATH))

    def _build_ui(self) -> None:
        """Sestaví ovládací prvky: vlastní hlavička (drag+zavření), vyhledávání, seznam."""
        # Viditelný okraj celého widgetu – bez OS rámečku by jinak nebyla vidět hranice okna.
        border = ctk.CTkFrame(self, border_width=1, border_color=("gray70", "gray30"))
        border.pack(fill="both", expand=True)

        self._build_header(border)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._render_list())
        search_entry = ctk.CTkEntry(border, textvariable=self.search_var, placeholder_text="Hledat...")
        search_entry.pack(fill="x", padx=10, pady=8)

        self.list_frame = ctk.CTkScrollableFrame(border, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=5, pady=(0, 10))

        self._build_resize_grip(border)

    def _build_resize_grip(self, parent) -> None:
        """Úchyt v pravém dolním rohu pro ruční změnu velikosti (bez OS rámečku by jinak nešla)."""
        grip = ctk.CTkLabel(parent, text="◢", text_color=("gray60", "gray50"), cursor="size_nw_se", width=16, height=16)
        grip.place(relx=1.0, rely=1.0, anchor="se")
        grip.bind("<ButtonPress-1>", self._start_resize)
        grip.bind("<B1-Motion>", self._on_resize)
        grip.bind("<ButtonRelease-1>", self._end_resize)

    def _start_resize(self, event) -> None:
        """Zapamatuje si výchozí rozměry a pozici kurzoru na začátku tažení úchytu (zamčené okno se neresizuje)."""
        if self._locked:
            return
        self._resize_start = (event.x_root, event.y_root, self.winfo_width(), self.winfo_height())

    def _on_resize(self, event) -> None:
        """Přepočítá a nastaví novou velikost okna podle tažení myší."""
        if self._locked or not hasattr(self, "_resize_start"):
            return
        start_x, start_y, start_w, start_h = self._resize_start
        new_w = max(MIN_WIDTH, start_w + (event.x_root - start_x))
        new_h = max(MIN_HEIGHT, start_h + (event.y_root - start_y))
        self.geometry(f"{new_w}x{new_h}")

    def _end_resize(self, _event) -> None:
        """Po puštění úchytu uloží novou velikost do configu, ať se zachová i po restartu."""
        if self._locked or not hasattr(self, "_resize_start"):
            return
        self.config_data["window"]["width"] = self.winfo_width()
        self.config_data["window"]["height"] = self.winfo_height()
        save_config(self.config_data)

    def _build_header(self, parent) -> None:
        """Vlastní hlavička nahrazující OS titulek – jde za ni okno tahat myší, má vlastní ovládací tlačítka."""
        header = ctk.CTkFrame(parent, fg_color="transparent", height=32)
        header.pack(fill="x", padx=10, pady=(8, 0))

        ctk.CTkLabel(header, text="📁 Projekty", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        close_btn = ctk.CTkButton(
            header, text="×", width=24, height=24, fg_color="transparent",
            hover_color="#e74c3c", text_color=("gray20", "gray90"), font=ctk.CTkFont(size=14),
            command=self.destroy,
        )
        close_btn.pack(side="right")

        self.lock_btn = ctk.CTkButton(
            header, text=self._lock_icon(), width=24, height=24, fg_color="transparent",
            command=self.toggle_lock,
        )
        self.lock_btn.pack(side="right", padx=(0, 4))

        ctk.CTkButton(header, text="⚙", width=24, height=24, command=self.open_settings).pack(
            side="right", padx=(0, 4)
        )

        refresh_btn = ctk.CTkButton(header, text="⟳", width=24, height=24, command=self.refresh_projects)
        refresh_btn.pack(side="right", padx=(0, 4))

        # Přetahování okna myší – bez OS titulku by jinak nešlo widget přesunout (pokud není zamčený).
        for widget in (header,):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

    def _lock_icon(self) -> str:
        """Vrátí ikonu zámku odpovídající aktuálnímu stavu."""
        return "🔒" if self._locked else "🔓"

    def toggle_lock(self) -> None:
        """Zamkne/odemkne pozici i velikost okna. Při zamčení se pozice trvale uloží a tažení/resize se zablokuje."""
        self._locked = not self._locked
        w_cfg = self.config_data["window"]
        w_cfg["locked"] = self._locked
        if self._locked:
            w_cfg["position"] = {"x": self.winfo_x(), "y": self.winfo_y()}
        save_config(self.config_data)
        self.lock_btn.configure(text=self._lock_icon())

    def open_settings(self) -> None:
        """Otevře dialog pro správu sledovaných složek."""
        FolderSettingsDialog(self, self.config_data["root_paths"], on_save=self._save_root_paths)

    def _save_root_paths(self, root_paths: list[str]) -> None:
        """Uloží nový seznam sledovaných složek do configu a spustí nový sken."""
        self.config_data["root_paths"] = root_paths
        save_config(self.config_data)
        self.refresh_projects()

    def _start_drag(self, event) -> None:
        """Zapamatuje si offset kliknutí vůči oknu na začátku tažení (ignorováno, pokud je okno zamčené)."""
        if self._locked:
            return
        self._drag_offset = (event.x, event.y)

    def _on_drag(self, event) -> None:
        """Přesune okno podle pohybu myši (kompenzace za chybějící OS titulek)."""
        if self._locked:
            return
        x = self.winfo_pointerx() - self._drag_offset[0]
        y = self.winfo_pointery() - self._drag_offset[1]
        self.geometry(f"+{x}+{y}")

    def refresh_projects(self) -> None:
        """Spustí sken disku na pozadí (vlákno), ať widget mezitím nezamrzne.

        Procházení všech souborů kvůli přesnému datu poslední změny může u víc
        projektů trvat řádově sekundy – proto běží mimo hlavní (UI) vlákno a
        výsledek se vyzvedne přes frontu ve `_poll_scan_result`.
        """
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.list_frame, text="Načítám...").pack(pady=20)

        cfg = self.config_data

        def worker() -> None:
            projects = find_projects(
                root_paths=cfg["root_paths"],
                marker_files=cfg["marker_files"],
                skip_dirs=cfg["skip_dirs"],
                max_depth=cfg.get("max_scan_depth", 3),
            )
            self._scan_results.put(projects)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_scan_result)

    def _poll_scan_result(self) -> None:
        """Kontroluje, jestli už sken na pozadí doběhl, a pokud ano, vykreslí výsledek."""
        try:
            projects = self._scan_results.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_scan_result)
            return
        self._all_projects = projects
        self._render_list()

    def _render_list(self) -> None:
        """Vykreslí (přefiltrovaný) seznam projektů – semafor, jméno, datum poslední změny."""
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        query = self.search_var.get().lower().strip()
        projects = [p for p in self._all_projects if query in p.name.lower()] if query else self._all_projects

        if not projects:
            ctk.CTkLabel(self.list_frame, text="Nic nenalezeno").pack(pady=20)
            return

        for project in projects:
            self._build_row(project)

    def _build_row(self, project: Project) -> None:
        """Sestaví jeden řádek seznamu: semafor tečka, jméno, datum – celý klikatelný."""
        row = ctk.CTkFrame(self.list_frame, fg_color="transparent", cursor="hand2")
        row.pack(fill="x", pady=1, padx=2)

        dot = ctk.CTkLabel(row, text="●", width=16, text_color=_semafor_color(project.last_modified))
        dot.pack(side="left", padx=(4, 4))

        name_label = ctk.CTkLabel(row, text=project.name, anchor="w")
        name_label.pack(side="left", fill="x", expand=True)

        date_label = ctk.CTkLabel(
            row, text=_format_date(project.last_modified),
            text_color=("gray45", "gray60"), font=ctk.CTkFont(size=11),
        )
        date_label.pack(side="right", padx=(6, 4))

        for widget in (row, dot, name_label, date_label):
            widget.bind("<Button-1>", lambda _e, p=project: self.open_project(p))
            widget.bind("<Enter>", lambda _e, r=row: r.configure(fg_color=("gray85", "gray25")))
            widget.bind("<Leave>", lambda _e, r=row: r.configure(fg_color="transparent"))

    def open_project(self, project: Project) -> None:
        """Otevře vybraný projekt v editoru definovaném v configu (výchozí: VS Code)."""
        editor = self.config_data.get("editor_command", "code")
        subprocess.Popen([editor, project.path], shell=True)


def run() -> None:
    """Spustí widget."""
    ctk.set_appearance_mode("system")
    app = DashboardWidget()
    app.mainloop()

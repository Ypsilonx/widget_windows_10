"""Modální okno pro správu sledovaných kořenových složek."""

from tkinter import filedialog

import customtkinter as ctk


class FolderSettingsDialog(ctk.CTkToplevel):
    """Dovolí přidat/odebrat složky, které widget prohledává, a uložit je do configu."""

    def __init__(self, parent, root_paths: list[str], on_save) -> None:
        super().__init__(parent)
        self.title("Sledované složky")
        self.geometry("420x360")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.grab_set()  # modální okno – blokuje interakci s widgetem pod ním

        self._paths = list(root_paths)
        self._on_save = on_save

        ctk.CTkLabel(self, text="Sledované složky", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 6))

        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=6)

        ctk.CTkButton(self, text="+ Přidat složku", command=self._add_folder).pack(pady=(6, 4))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(4, 12))
        ctk.CTkButton(btn_row, text="Uložit", command=self._save).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Zrušit", fg_color="gray40", command=self.destroy).pack(side="left", padx=6)

        self._render_list()

    def _render_list(self) -> None:
        """Překreslí seznam aktuálně přidaných složek."""
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if not self._paths:
            ctk.CTkLabel(self.list_frame, text="Zatím žádná složka").pack(pady=10)
            return

        for path in self._paths:
            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=path, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(
                row, text="🗑", width=28, fg_color="transparent", hover_color="#e74c3c",
                command=lambda p=path: self._remove_folder(p),
            ).pack(side="right")

    def _add_folder(self) -> None:
        """Otevře nativní dialog pro výběr složky a přidá ji do seznamu (bez duplicit)."""
        folder = filedialog.askdirectory(title="Vyber složku ke sledování", parent=self)
        if folder and folder not in self._paths:
            self._paths.append(folder)
            self._render_list()

    def _remove_folder(self, path: str) -> None:
        """Odebere složku ze seznamu."""
        self._paths.remove(path)
        self._render_list()

    def _save(self) -> None:
        """Předá výsledný seznam volajícímu (uložení do configu + rescan) a zavře dialog."""
        self._on_save(self._paths)
        self.destroy()

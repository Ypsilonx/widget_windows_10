"""Vynutí ikonu aplikace na hlavním panelu Windows i pro bezrámečkové (overrideredirect) okno."""

import ctypes

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080


def get_hwnd(root) -> int:
    """Vrátí skutečný top-level HWND okna (Tk `winfo_id()` sám o sobě vrací vnitřní kreslicí okno)."""
    return ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()


def show_in_taskbar(root) -> None:
    """Nastaví oknu příznak WS_EX_APPWINDOW – bez toho by se overrideredirect okno v taskbaru neobjevilo."""
    root.update_idletasks()
    hwnd = get_hwnd(root)
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    # Krátké schování a znovuzobrazení donutí Windows ikonu v taskbaru okamžitě aktualizovat.
    root.withdraw()
    root.after(10, root.deiconify)

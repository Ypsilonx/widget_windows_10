"""Vzhled okna ve stylu Windows 11 (kulaté rohy) pro bezrámečkové okno."""

import ctypes
from ctypes import wintypes

from taskbar import get_hwnd

DWMWA_WINDOW_CORNER_PREFERENCE = 33
# Varianty: 1 = hranaté, 2 = kulaté (standardní poloměr), 3 = kulaté malé.
DWMWCP_ROUND = 2


def apply_rounded_corners(root, preference: int = DWMWCP_ROUND) -> None:
    """Požádá DWM o zakulacení rohů okna; na Windows 10 volání tiše selže a okno zůstane hranaté."""
    hwnd = get_hwnd(root)
    value = ctypes.c_int(preference)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(value), ctypes.sizeof(value)
    )

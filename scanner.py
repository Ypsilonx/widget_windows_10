"""Vyhledávání projektových složek na disku.

Projekt = adresář, který obsahuje jeden z konfigurovaných "marker" souborů/složek
(.git, package.json, pyproject.toml apod.). Jakmile je projekt nalezen, dál se
do jeho podsložek nesestupuje (aby se do seznamu nedostaly vnořené podprojekty
typu node_modules balíčků).
"""

import fnmatch
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

# Kolik projektů se prochází souběžně při zjišťování data poslední změny.
# Jde o I/O (čekání na disk), takže i s Python GIL to reálně zrychluje.
MAX_SCAN_WORKERS = 8


@dataclass
class Project:
    """Jeden nalezený projekt – jméno, cesta a čas poslední úpravy."""

    name: str
    path: str
    last_modified: float


def _has_marker(dir_path: str, entries: list[os.DirEntry], marker_files: list[str]) -> bool:
    """Zjistí, jestli složka obsahuje některý z marker souborů/vzorů (i wildcard jako *.sln)."""
    names = [e.name for e in entries]
    for marker in marker_files:
        if any(ch in marker for ch in "*?[]"):
            if any(fnmatch.fnmatch(n, marker) for n in names):
                return True
        elif marker in names:
            return True
    return False


def _project_last_modified(dir_path: str, skip_set: set[str]) -> float:
    """Najde čas poslední změny mezi soubory v projektu (bez přeskakovaných podsložek).

    Mtime samotné složky projektu na Windows odráží jen změny přímo v jejím
    obsahu (přejmenování/smazání položky), ne úpravu souboru o úroveň níž –
    proto je potřeba reálně projít soubory a vzít z nich nejnovější mtime.
    """
    latest = 0.0

    def scan(current_path: str) -> None:
        nonlocal latest
        try:
            with os.scandir(current_path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name.lower() not in skip_set:
                                scan(entry.path)
                        else:
                            mtime = entry.stat(follow_symlinks=False).st_mtime
                            if mtime > latest:
                                latest = mtime
                    except OSError:
                        continue
        except OSError:
            pass

    scan(dir_path)

    if latest == 0.0:
        try:
            latest = os.path.getmtime(dir_path)
        except OSError:
            latest = 0.0
    return latest


def _find_candidate_dirs(root_paths: list[str], marker_files: list[str], skip_set: set[str], max_depth: int) -> list[str]:
    """Rychlý první průchod – jen najde cesty ke složkám s markerem, bez počítání data poslední změny."""
    candidates: list[str] = []

    def scan(dir_path: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(os.scandir(dir_path))
        except (PermissionError, FileNotFoundError, OSError):
            return

        if _has_marker(dir_path, entries, marker_files):
            candidates.append(dir_path)
            return  # nesestupovat dál do nalezeného projektu

        for entry in entries:
            if entry.is_dir(follow_symlinks=False) and entry.name.lower() not in skip_set:
                scan(entry.path, depth + 1)

    for root in root_paths:
        if os.path.isdir(root):
            scan(root, 0)
    return candidates


def find_projects(
    root_paths: list[str],
    marker_files: list[str],
    skip_dirs: list[str],
    max_depth: int = 3,
) -> list[Project]:
    """Najde projekty v zadaných kořenových cestách, seřazené od nejnovější změny.

    Ve dvou krocích: nejdřív rychle najde kandidáty podle markeru (`.git` apod.),
    pak pro ně souběžně (více vláken) zjistí datum poslední změny – to je totiž
    ta pomalá část (průchod všech souborů projektu), takže se dělá paralelně
    místo projekt po projektu.
    """
    skip_set = {d.lower() for d in skip_dirs}
    candidate_dirs = _find_candidate_dirs(root_paths, marker_files, skip_set, max_depth)

    with ThreadPoolExecutor(max_workers=MAX_SCAN_WORKERS) as executor:
        mtimes = executor.map(lambda path: _project_last_modified(path, skip_set), candidate_dirs)
        projects = [
            Project(name=os.path.basename(path), path=path, last_modified=mtime)
            for path, mtime in zip(candidate_dirs, mtimes)
        ]

    projects.sort(key=lambda p: p.last_modified, reverse=True)
    return projects

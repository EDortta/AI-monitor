#!/usr/bin/env python3
"""
AI Agent Activity Monitor — system tray app (Linux/MATE · macOS · Windows).
Watches ~/Sync/agent-log.md and ~/Sync/agent-status.json.

Threading model
───────────────
  Main thread   : tkinter root.mainloop() + queue poll every 50 ms
  Daemon thread : GTK StatusIcon (Linux/MATE) or pystray (macOS/Windows/fallback)
  Daemon thread : watchdog Observer — file change events

All cross-thread UI calls go through self._q (queue.Queue).
The main thread drains the queue every 50 ms — the only code that
touches tkinter runs there.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import queue
import re
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── logging ───────────────────────────────────────────────────────────────────
# Log outside ~/Sync/ so watchdog doesn't see its own writes
_LOG_PATH = Path.home() / ".local" / "share" / "agent-monitor" / "debug.log"
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=_LOG_PATH,
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
# Silence noisy watchdog internals
logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)
log = logging.getLogger("monitor")

# ── paths & tunables ──────────────────────────────────────────────────────────

SYNC_DIR      = Path.home() / "Sync"
LOG_FILE      = SYNC_DIR / "agent-log.md"
STATUS_FILE   = SYNC_DIR / "agent-status.json"
HEARTBEAT_TTL = 300    # seconds; older heartbeat → session not live
ICON_SIZE     = 64
WINDOW_W      = 540
WINDOW_H      = 620
POPUP_W       = 430
POPUP_H       = 420
DCLICK_MS     = 450    # double-click window in milliseconds

AGENT_COLORS = {
    "claude-code": "#E8870A",   # orange
    "codex":       "#10A37F",   # green
    "cursor":      "#146EF5",   # blue
}
GRAY = "#666666"

# dark theme
BG_DARK  = "#1e1e2e"
BG_CARD  = "#2a2a3e"
BG_INPUT = "#313244"
FG_MAIN  = "#cdd6f4"
FG_DIM   = "#6c7086"
FG_LIVE  = "#a6e3a1"
FG_NEXT  = "#89b4fa"

ENTRY_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · ([\w-]+) · (.+?)\n(.*?)(?=\n---|\Z)",
    re.MULTILINE | re.DOTALL,
)

# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class LiveSession:
    agent:     str
    project:   str
    task:      str
    started:   str
    heartbeat: str


@dataclass
class LogEntry:
    dt:        str
    agent:     str
    project:   str
    body:      str
    next_step: str


@dataclass
class AppState:
    live:    list[LiveSession] = field(default_factory=list)
    history: list[LogEntry]   = field(default_factory=list)

    @property
    def active_agents(self) -> list[str]:
        seen: list[str] = []
        for s in self.live:
            if s.agent not in seen:
                seen.append(s.agent)
        return seen


def _is_live(heartbeat: str) -> bool:
    try:
        dt  = datetime.datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
        age = datetime.datetime.now(datetime.timezone.utc) - dt
        return age.total_seconds() < HEARTBEAT_TTL
    except (ValueError, TypeError):
        return False


def load_state() -> AppState:
    state = AppState()

    if STATUS_FILE.exists():
        try:
            data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            for s in data.get("sessions", []):
                if _is_live(s.get("heartbeat", "")):
                    state.live.append(LiveSession(
                        agent     = s.get("agent",     "unknown"),
                        project   = s.get("project",   ""),
                        task      = s.get("task",      ""),
                        started   = s.get("started",   ""),
                        heartbeat = s.get("heartbeat", ""),
                    ))
        except (json.JSONDecodeError, OSError):
            pass

    if LOG_FILE.exists():
        try:
            text = LOG_FILE.read_text(encoding="utf-8")
            for m in ENTRY_RE.finditer(text):
                raw          = m.group(4).strip()
                body_lines: list[str] = []
                next_step    = "—"
                for line in raw.splitlines():
                    if line.startswith("**Next:**"):
                        next_step = line.removeprefix("**Next:**").strip()
                    else:
                        body_lines.append(line)
                state.history.append(LogEntry(
                    dt        = m.group(1),
                    agent     = m.group(2).lower(),
                    project   = m.group(3).strip(),
                    body      = "\n".join(body_lines).strip(),
                    next_step = next_step,
                ))
            state.history.reverse()
            state.history = state.history[:50]
        except OSError:
            pass

    return state


def _entry_matches(e: LogEntry, q: str) -> bool:
    q = q.lower()
    return (q in e.agent.lower() or q in e.project.lower()
            or q in e.body.lower() or q in e.next_step.lower())


# ── tray icon image ───────────────────────────────────────────────────────────

ICON_FILE = Path(__file__).parent / "tray-icon.png"
_pil_cache: Optional[Image.Image] = None


def _pil_icon() -> Image.Image:
    global _pil_cache
    if _pil_cache is None:
        if ICON_FILE.exists():
            _pil_cache = Image.open(ICON_FILE).convert("RGBA").resize(
                (ICON_SIZE, ICON_SIZE), Image.LANCZOS
            )
        else:
            img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
            ImageDraw.Draw(img).ellipse([6, 6, ICON_SIZE - 6, ICON_SIZE - 6], fill=GRAY)
            _pil_cache = img
    return _pil_cache


# ── GTK tray (Linux/MATE/Cinnamon/XFCE) ──────────────────────────────────────

def _has_gi() -> bool:
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk  # noqa: F401
        return True
    except Exception:
        return False


class _GtkTray:
    """GTK StatusIcon — runs Gtk.main() in its own daemon thread."""

    def __init__(self, event_q: queue.Queue) -> None:
        self._q   = event_q
        self._icon = None

    def start(self) -> None:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("GLib", "2.0")
        from gi.repository import Gtk, GLib

        self._Gtk  = Gtk
        self._GLib = GLib

        icon = Gtk.StatusIcon()
        icon.set_tooltip_text("Agent Monitor")
        if ICON_FILE.exists():
            icon.set_from_file(str(ICON_FILE))
        else:
            icon.set_from_icon_name("computer")
        icon.set_visible(True)
        self._icon = icon

        self._last_click: float = 0.0
        self._click_timer: Optional[threading.Timer] = None

        icon.connect("activate",    self._on_activate)
        icon.connect("popup-menu",  self._on_popup)

        log.info("GTK StatusIcon started")
        Gtk.main()

    def _on_activate(self, _icon) -> None:
        now = time.monotonic()
        log.debug("GTK activate, gap=%.3fs", now - self._last_click)
        if now - self._last_click < DCLICK_MS / 1000:
            if self._click_timer is not None:
                self._click_timer.cancel()
                self._click_timer = None
            log.debug("posting dclick")
            self._q.put("dclick")
        else:
            if self._click_timer is not None:
                self._click_timer.cancel()
            self._click_timer = threading.Timer(
                DCLICK_MS / 1000, lambda: self._q.put("click"))
            self._click_timer.daemon = True
            self._click_timer.start()
            log.debug("armed single-click timer")
        self._last_click = now

    def _on_popup(self, _icon, button, ts) -> None:
        Gtk = self._Gtk
        menu = Gtk.Menu()

        def _add(label, evt):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _: self._q.put(evt))
            menu.append(item)

        _add("Popup",        "click")
        _add("Open window",  "open")
        menu.append(Gtk.SeparatorMenuItem())
        _add("Quit",         "quit")
        menu.show_all()
        menu.popup(None, None,
                   lambda i, x, y, d: self._icon.position_menu(i, x, y, d) if hasattr(self._icon, 'position_menu') else (x, y, True),
                   _icon, button, ts)

    def stop(self) -> None:
        if self._GLib:
            self._GLib.idle_add(self._Gtk.main_quit)


# ── pystray tray (macOS / Windows / fallback) ─────────────────────────────────

class _PystrayTray:
    """pystray fallback for non-GTK systems."""

    def __init__(self, event_q: queue.Queue) -> None:
        self._q    = event_q
        self._icon = None
        self._last_click:  float                  = 0.0
        self._click_timer: Optional[threading.Timer] = None

    def start(self) -> None:
        import pystray

        def _click(*_) -> None:
            now = time.monotonic()
            if now - self._last_click < DCLICK_MS / 1000:
                if self._click_timer is not None:
                    self._click_timer.cancel()
                    self._click_timer = None
                self._q.put("dclick")
            else:
                if self._click_timer is not None:
                    self._click_timer.cancel()
                self._click_timer = threading.Timer(
                    DCLICK_MS / 1000, lambda: self._q.put("click"))
                self._click_timer.daemon = True
                self._click_timer.start()
            self._last_click = now

        menu = pystray.Menu(
            pystray.MenuItem("Popup",       _click, default=True),
            pystray.MenuItem("Open window", lambda *_: self._q.put("open")),
            pystray.MenuItem("Quit",        lambda *_: self._q.put("quit")),
        )
        self._icon = pystray.Icon(
            "agent-monitor", _pil_icon(), "Agent Monitor",
            menu, on_activate=_click,
        )
        log.info("pystray tray started")
        self._icon.run()   # blocks until stopped

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()


# ── shared card builders ──────────────────────────────────────────────────────

def _agent_color(agent: str) -> str:
    return AGENT_COLORS.get(agent, GRAY)


def _section_label(parent: tk.Frame, text: str, color: str) -> None:
    tk.Label(parent, text=text, bg=BG_DARK, fg=color,
             font=("monospace", 9, "bold"), pady=7, padx=14,
             anchor="w").pack(fill=tk.X)


def _live_card(parent: tk.Frame, s: LiveSession, wrap: int) -> None:
    color = _agent_color(s.agent)
    outer = tk.Frame(parent, bg=BG_DARK, pady=3, padx=14)
    outer.pack(fill=tk.X)
    card = tk.Frame(outer, bg=BG_CARD)
    card.pack(fill=tk.X)
    tk.Frame(card, bg=color, width=4).pack(side=tk.LEFT, fill=tk.Y)
    body = tk.Frame(card, bg=BG_CARD, padx=10, pady=8)
    body.pack(fill=tk.BOTH, expand=True)

    top = tk.Frame(body, bg=BG_CARD)
    top.pack(fill=tk.X)
    tk.Label(top, text=s.agent, bg=BG_CARD, fg=color,
             font=("monospace", 10, "bold")).pack(side=tk.LEFT)
    tk.Label(top, text=f"  {s.project}", bg=BG_CARD, fg=FG_DIM,
             font=("monospace", 9)).pack(side=tk.LEFT)
    tk.Label(top, text=" ● LIVE ", bg=FG_LIVE, fg=BG_DARK,
             font=("monospace", 8, "bold")).pack(side=tk.RIGHT)

    if s.task:
        tk.Label(body, text=s.task, bg=BG_CARD, fg=FG_MAIN,
                 font=("monospace", 9), wraplength=wrap,
                 justify=tk.LEFT, anchor="w").pack(fill=tk.X)
    if s.started:
        ts = s.started[:16].replace("T", " ")
        tk.Label(body, text=f"started {ts} UTC", bg=BG_CARD, fg=FG_DIM,
                 font=("monospace", 8), anchor="w").pack(fill=tk.X)


def _log_card(parent: tk.Frame, e: LogEntry, wrap: int) -> None:
    color = _agent_color(e.agent)
    outer = tk.Frame(parent, bg=BG_DARK, pady=2, padx=14)
    outer.pack(fill=tk.X)
    card = tk.Frame(outer, bg=BG_CARD)
    card.pack(fill=tk.X)
    tk.Frame(card, bg=color, width=4).pack(side=tk.LEFT, fill=tk.Y)
    body = tk.Frame(card, bg=BG_CARD, padx=10, pady=6)
    body.pack(fill=tk.BOTH, expand=True)

    top = tk.Frame(body, bg=BG_CARD)
    top.pack(fill=tk.X)
    tk.Label(top, text=e.agent, bg=BG_CARD, fg=color,
             font=("monospace", 9, "bold")).pack(side=tk.LEFT)
    tk.Label(top, text=f"  {e.project}", bg=BG_CARD, fg=FG_DIM,
             font=("monospace", 9)).pack(side=tk.LEFT)
    tk.Label(top, text=e.dt, bg=BG_CARD, fg=FG_DIM,
             font=("monospace", 8)).pack(side=tk.RIGHT)

    if e.body:
        tk.Label(body, text=e.body, bg=BG_CARD, fg=FG_MAIN,
                 font=("monospace", 9), wraplength=wrap,
                 justify=tk.LEFT, anchor="w").pack(fill=tk.X)

    if e.next_step and e.next_step not in ("—", "-", ""):
        tk.Label(body, text=f"Next: {e.next_step}", bg=BG_CARD, fg=FG_NEXT,
                 font=("monospace", 8, "italic"), wraplength=wrap,
                 justify=tk.LEFT, anchor="w").pack(fill=tk.X)


# ── full window ───────────────────────────────────────────────────────────────

def build_window(root: tk.Tk, state: AppState,
                 search_var: Optional[tk.StringVar] = None) -> tk.StringVar:
    for w in root.winfo_children():
        w.destroy()

    root.configure(bg=BG_DARK)
    root.title("Agent Monitor")
    root.geometry(f"{WINDOW_W}x{WINDOW_H}")

    # header
    hdr = tk.Frame(root, bg=BG_DARK, pady=8)
    hdr.pack(fill=tk.X, padx=14)
    tk.Label(hdr, text="Agent Monitor", bg=BG_DARK, fg=FG_MAIN,
             font=("monospace", 13, "bold")).pack(side=tk.LEFT)
    live_dot = ("●", FG_LIVE) if state.live else ("○", FG_DIM)
    tk.Label(hdr, text=live_dot[0], bg=BG_DARK, fg=live_dot[1],
             font=("monospace", 14)).pack(side=tk.RIGHT)

    # search bar
    if search_var is None:
        search_var = tk.StringVar()
    sf = tk.Frame(root, bg=BG_DARK, padx=14, pady=4)
    sf.pack(fill=tk.X)
    entry = tk.Entry(sf, textvariable=search_var, bg=BG_INPUT, fg=FG_MAIN,
                     insertbackground=FG_MAIN, relief=tk.FLAT,
                     font=("monospace", 10), bd=6)
    entry.pack(fill=tk.X)

    PLACEHOLDER = "Search…"

    def _fi(_e):
        if entry.get() == PLACEHOLDER:
            entry.delete(0, tk.END)
            entry.config(fg=FG_MAIN)

    def _fo(_e):
        if not entry.get():
            entry.insert(0, PLACEHOLDER)
            entry.config(fg=FG_DIM)

    entry.bind("<FocusIn>",  _fi)
    entry.bind("<FocusOut>", _fo)
    if not search_var.get():
        entry.insert(0, PLACEHOLDER)
        entry.config(fg=FG_DIM)

    # scrollable area
    canvas = tk.Canvas(root, bg=BG_DARK, bd=0, highlightthickness=0)
    vsb    = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
    inner  = tk.Frame(canvas, bg=BG_DARK)
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _scroll(ev):
        canvas.yview_scroll(-1 if (ev.num == 4 or ev.delta > 0) else 1, "units")

    canvas.bind_all("<MouseWheel>", _scroll)
    canvas.bind_all("<Button-4>",   _scroll)
    canvas.bind_all("<Button-5>",   _scroll)

    wrap = WINDOW_W - 70

    def _rebuild(*_):
        for w in inner.winfo_children():
            w.destroy()
        q = search_var.get().strip()
        if q == PLACEHOLDER:
            q = ""
        live    = state.live if not q else []
        history = [e for e in state.history if not q or _entry_matches(e, q)]
        history = history if q else history[:10]

        if live:
            _section_label(inner, "● LIVE", FG_LIVE)
            for s in live:
                _live_card(inner, s, wrap)
        if history:
            label = f"HISTORY  ({len(history)} results)" if q else "HISTORY"
            _section_label(inner, label, FG_DIM)
            for e in history:
                _log_card(inner, e, wrap)
        if not live and not history:
            tk.Label(inner, text="No results." if q else "No activity recorded yet.",
                     bg=BG_DARK, fg=FG_DIM, font=("monospace", 11), pady=50).pack()
        canvas.yview_moveto(0)

    search_var.trace_add("write", _rebuild)
    _rebuild()
    return search_var


# ── compact popup ─────────────────────────────────────────────────────────────

def build_popup(root: tk.Tk, state: AppState) -> tk.Toplevel:
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x  = sw - POPUP_W - 20
    y  = sh - POPUP_H - 60

    pop = tk.Toplevel(root)
    pop.overrideredirect(True)
    pop.geometry(f"{POPUP_W}x{POPUP_H}+{x}+{y}")
    pop.configure(bg=BG_DARK)
    pop.lift()
    pop.attributes("-topmost", True)

    border = tk.Frame(pop, bg="#45475a", padx=1, pady=1)
    border.pack(fill=tk.BOTH, expand=True)
    bg_frame = tk.Frame(border, bg=BG_DARK)
    bg_frame.pack(fill=tk.BOTH, expand=True)

    # title row
    tr = tk.Frame(bg_frame, bg=BG_DARK, pady=6, padx=10)
    tr.pack(fill=tk.X)
    live_dot = ("●", FG_LIVE) if state.live else ("○", FG_DIM)
    tk.Label(tr, text=live_dot[0], bg=BG_DARK, fg=live_dot[1],
             font=("monospace", 11)).pack(side=tk.LEFT)
    tk.Label(tr, text="  Agent Monitor", bg=BG_DARK, fg=FG_MAIN,
             font=("monospace", 10, "bold")).pack(side=tk.LEFT)
    close_btn = tk.Label(tr, text="✕", bg=BG_DARK, fg=FG_DIM,
                         font=("monospace", 11), cursor="hand2")
    close_btn.pack(side=tk.RIGHT)
    close_btn.bind("<Button-1>", lambda _: pop.destroy())

    # scrollable content
    canvas  = tk.Canvas(bg_frame, bg=BG_DARK, bd=0, highlightthickness=0)
    vsb     = tk.Scrollbar(bg_frame, orient="vertical", command=canvas.yview)
    content = tk.Frame(canvas, bg=BG_DARK)
    content.bind("<Configure>",
                 lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=content, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _scroll(ev):
        canvas.yview_scroll(-1 if (ev.num == 4 or ev.delta > 0) else 1, "units")
    canvas.bind_all("<MouseWheel>", _scroll)
    canvas.bind_all("<Button-4>",   _scroll)
    canvas.bind_all("<Button-5>",   _scroll)

    wrap = POPUP_W - 60
    if state.live:
        _section_label(content, "● LIVE", FG_LIVE)
        for s in state.live:
            _live_card(content, s, wrap)
    entries = state.history[:10]
    if entries:
        _section_label(content, "LAST 10 ACTIONS", FG_DIM)
        for e in entries:
            _log_card(content, e, wrap)
    if not state.live and not entries:
        tk.Label(content, text="No activity recorded yet.",
                 bg=BG_DARK, fg=FG_DIM, font=("monospace", 10), pady=30).pack()

    def _dismiss(e: tk.Event) -> None:
        try:
            focused = pop.focus_get()
        except Exception:
            focused = None
        if focused is None or not str(focused).startswith(str(pop)):
            pop.destroy()

    pop.bind("<FocusOut>", _dismiss)
    pop.bind("<Escape>",   lambda _: pop.destroy())
    pop.focus_force()
    return pop


# ── app controller ────────────────────────────────────────────────────────────

class App:
    def __init__(self) -> None:
        self.state      = load_state()
        self.root       = tk.Tk()
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self._hide)
        self._open:       bool                  = False
        self._search_var: Optional[tk.StringVar] = None
        self._popup:      Optional[tk.Toplevel]  = None
        self._q:          queue.Queue[str]       = queue.Queue()
        self._tray:       Optional[_GtkTray | _PystrayTray] = None

    # ── queue poll (main thread) ----------------------------------------------

    def _poll(self) -> None:
        try:
            while True:
                evt = self._q.get_nowait()
                log.debug("poll: %s", evt)
                if evt == "click":
                    self._show_popup_safe()
                elif evt == "dclick":
                    self._show_window()
                elif evt == "open":
                    self._show_window()
                elif evt == "refresh":
                    self._do_refresh()
                elif evt == "quit":
                    self._on_quit()
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    # ── popup -----------------------------------------------------------------

    def _show_popup_safe(self) -> None:
        log.debug("show_popup")
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return
        self._popup = build_popup(self.root, self.state)

    # ── full window -----------------------------------------------------------

    def _show_window(self) -> None:
        log.debug("show_window")
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
        if self._search_var is None:
            self._search_var = tk.StringVar()
        build_window(self.root, self.state, self._search_var)
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._open = True
        log.debug("show_window done")

    def _hide(self) -> None:
        self.root.withdraw()
        self._open = False

    # ── refresh ---------------------------------------------------------------

    def refresh(self) -> None:
        self._q.put("refresh")   # safe from any thread

    def _do_refresh(self) -> None:
        self.state = load_state()
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = build_popup(self.root, self.state)
        if self._open:
            build_window(self.root, self.state, self._search_var)

    # ── quit -----------------------------------------------------------------

    def _on_quit(self) -> None:
        if self._tray:
            self._tray.stop()
        self.root.quit()

    # ── run -------------------------------------------------------------------

    def run(self) -> None:
        # Watchdog
        handler  = _FileWatcher(self.refresh)
        observer = Observer()
        observer.schedule(handler, str(SYNC_DIR), recursive=False)
        observer.daemon = True
        observer.start()

        # Tray icon — prefer GTK on Linux, fall back to pystray
        if _has_gi():
            self._tray = _GtkTray(self._q)
        else:
            self._tray = _PystrayTray(self._q)

        t = threading.Thread(target=self._tray.start, daemon=True)
        t.start()

        # Start queue drain on main thread
        self.root.after(50, self._poll)
        log.info("entering mainloop (tray=%s)", type(self._tray).__name__)
        self.root.mainloop()

        observer.stop()
        observer.join(timeout=2)


# ── file watcher ──────────────────────────────────────────────────────────────

class _FileWatcher(FileSystemEventHandler):
    _watched = {LOG_FILE.name, STATUS_FILE.name}

    def __init__(self, callback):
        super().__init__()
        self._cb = callback

    def on_modified(self, event):
        if not event.is_directory and Path(event.src_path).name in self._watched:
            self._cb()

    on_created = on_modified


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    App().run()

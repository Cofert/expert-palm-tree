"""Thread‑safe terminal UI with regular + compact modes."""
from __future__ import annotations

import re
import sys
import threading
import time
from datetime import datetime


class C:
    RESET   = "\x1b[0m"
    DIM     = "\x1b[2m"
    BOLD    = "\x1b[1m"
    RED     = "\x1b[38;5;203m"
    GREEN   = "\x1b[38;5;82m"
    YELLOW  = "\x1b[38;5;221m"
    CYAN    = "\x1b[38;5;87m"
    MAGENTA = "\x1b[38;5;213m"
    GREY    = "\x1b[38;5;245m"
    BLUE    = "\x1b[38;5;111m"


_ISATTY = sys.stdout.isatty()
_ANSI   = re.compile(r"\x1b\[[0-9;]*m")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def c(code: str, s: str) -> str:
    return f"{code}{s}{C.RESET}" if _ISATTY else s


def _vislen(s: str) -> int:
    return len(_ANSI.sub("", s))


def _fmt_dur(seconds: float) -> str:
    if seconds < 60:   return f"{int(seconds)}s"
    if seconds < 3600: return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"
    return f"{int(seconds // 3600)}h{int((seconds % 3600) // 60):02d}m"


class UI:
    def __init__(self, title: str, compact: bool = False, total: int | None = None):
        self.title    = title
        self.compact  = compact
        self.total    = total if total and total > 0 else None
        self.start    = time.time()
        self.done     = 0
        self.ok       = 0
        self.fail     = 0
        self.suppressed = 0
        self.last     = ""
        self._spin_i  = 0
        self._lock    = threading.Lock()
        self._status_len = 0

    def _clear_status(self):
        if self._status_len > 0 and _ISATTY:
            sys.stdout.write("\r" + " " * self._status_len + "\r")
            self._status_len = 0

    def _draw_status(self, force: bool = False):
        if not self.compact:
            return
        if not _ISATTY:
            if force or self.done % 20 == 0:
                elapsed = max(0.001, time.time() - self.start)
                rate = self.done / elapsed
                tot = f"/{self.total}" if self.total else ""
                print(f"  progress: {self.done}{tot}  ok={self.ok}  fail={self.fail}  sup={self.suppressed}  {rate:.1f}/s", flush=True)
            return

        self._spin_i = (self._spin_i + 1) % len(SPINNER)
        spin    = SPINNER[self._spin_i]
        elapsed = max(0.001, time.time() - self.start)
        rate    = self.done / elapsed

        parts = [c(C.CYAN + C.BOLD, spin)]
        if self.total:
            pct    = self.done / self.total
            bar_w  = 20
            filled = int(pct * bar_w)
            bar    = c(C.GREEN, "█" * filled) + c(C.DIM, "░" * (bar_w - filled))
            parts.append(f"{bar} {c(C.BOLD, f'{self.done}/{self.total}')}")
            remaining = max(0, self.total - self.done)
            eta = remaining / rate if rate > 0 else 0
            parts.append(c(C.DIM, f"ETA {_fmt_dur(eta)}"))
        else:
            parts.append(c(C.BOLD, str(self.done)))
            parts.append(c(C.DIM, _fmt_dur(elapsed)))

        parts.append(c(C.GREEN + C.BOLD, f"✓{self.ok}"))
        parts.append(c(C.RED   + C.BOLD, f"✗{self.fail}"))
        if self.suppressed:
            sup_pct = f"{self.suppressed / max(1, self.ok) * 100:.0f}%"
            parts.append(c(C.CYAN, f"sup={sup_pct}"))
        parts.append(c(C.DIM, f"{rate:.1f}/s"))
        if self.last:
            tail = self.last if len(self.last) <= 24 else self.last[:21] + "..."
            parts.append(c(C.DIM, f"· {tail}"))

        line = "  ".join(parts)
        sys.stdout.write("\r" + line)
        sys.stdout.flush()
        self._status_len = _vislen(line)

    def event(self, worker: int, tag: str, msg: str, color: str = C.CYAN):
        if self.compact:
            return
        with self._lock:
            ts   = datetime.now().strftime("%H:%M:%S")
            line = f"  {c(C.DIM, ts)}  {c(C.MAGENTA, f'w{worker:<2}')}  {c(color + C.BOLD, f'{tag:<10}')}  {msg}"
            print(line, flush=True)

    def success(self, worker: int, tag: str, label: str, detail: str = "", color: str = C.GREEN):
        with self._lock:
            self._clear_status()
            ts     = datetime.now().strftime("%H:%M:%S")
            marker = c(color + C.BOLD, "▸")
            line   = f"  {c(C.DIM, ts)}  {c(C.MAGENTA, f'w{worker:<2}')}  {marker} {c(color + C.BOLD, f'{tag:<8}')}  {c(color, label)}"
            if detail:
                line += f"  {c(C.DIM, detail)}"
            print(line, flush=True)
            self._draw_status()

    def tick(self, ok: bool, suppressed: bool = False, label: str = ""):
        with self._lock:
            self.done += 1
            if ok:
                self.ok += 1
                if suppressed:
                    self.suppressed += 1
            else:
                self.fail += 1
            if label:
                self.last = label
            self._draw_status()

    def note(self, msg: str, color: str = C.YELLOW):
        with self._lock:
            self._clear_status()
            print(f"  {c(color, '!')} {msg}", flush=True)
            self._draw_status()

    def banner(self, subtitle: str, fields: list[tuple[str, str]]):
        bar = c(C.BOLD + C.CYAN, "━" * 62)
        print()
        print(bar)
        print(c(C.BOLD + C.CYAN, f"  {self.title}") + c(C.DIM, f"  ·  {subtitle}"))
        print(bar)
        width = max((len(k) for k, _ in fields), default=0)
        for k, v in fields:
            print(f"  {c(C.DIM, k.ljust(width))}   {v}")
        print()

    def summary(self, fields: list[tuple[str, str]]):
        if self.compact:
            with self._lock:
                self._clear_status()
                sys.stdout.write("\n")
        bar = c(C.BOLD + C.CYAN, "━" * 62)
        print()
        print(bar)
        print(c(C.BOLD + C.CYAN, "  Summary"))
        print(bar)
        width = max((len(k) for k, _ in fields), default=0)
        for k, v in fields:
            print(f"  {c(C.DIM, k.ljust(width))}   {v}")
        print()

    def close(self):
        if self.compact:
            with self._lock:
                self._clear_status()

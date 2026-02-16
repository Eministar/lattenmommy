from __future__ import annotations

import os
import sys


class Console:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"

    FG = {
        "red": "\033[38;5;196m",
        "green": "\033[38;5;82m",
        "yellow": "\033[38;5;220m",
        "blue": "\033[38;5;39m",
        "magenta": "\033[38;5;205m",
        "cyan": "\033[38;5;51m",
        "white": "\033[38;5;15m",
        "gray": "\033[38;5;245m",
    }

    def __init__(self):
        self.enabled = self._supports_color()

    def _supports_color(self) -> bool:
        if os.getenv("NO_COLOR"):
            return False
        if os.getenv("FORCE_COLOR"):
            return True
        if not sys.stdout or not getattr(sys.stdout, "isatty", lambda: False)():
            return False
        term = str(os.getenv("TERM", "")).lower()
        if term in {"", "dumb"}:
            return False
        if os.name != "nt":
            return True
        return bool(os.getenv("WT_SESSION") or os.getenv("ANSICON") or os.getenv("ConEmuANSI") == "ON")

    def style(self, text: str, color: str | None = None, bold: bool = False, dim: bool = False) -> str:
        if not self.enabled:
            return text
        seq = ""
        if bold:
            seq += self.BOLD
        if dim:
            seq += self.DIM
        if color:
            seq += self.FG.get(color, "")
        return f"{seq}{text}{self.RESET}"

    def line(self, tag: str, msg: str, color: str = "white"):
        label = self.style(f"[{tag}]", color=color, bold=True)
        print(f"{label} {msg}")

    def banner(self, app_name: str = "STARRY"):
        top = self.style("╔══════════════════════════════════════════════════════════════╗", "magenta")
        mid = self.style("║", "magenta")
        txt = self.style(f" {app_name} BOT BOOT ", "cyan", bold=True)
        sub = self.style("Design-Start • Module laden • Discord verbinden", "gray")
        bot = self.style("╚══════════════════════════════════════════════════════════════╝", "magenta")
        print(top)
        print(f"{mid}{txt.ljust(62)}{mid}")
        print(f"{mid} {sub.ljust(60)}{mid}")
        print(bot)


console = Console()

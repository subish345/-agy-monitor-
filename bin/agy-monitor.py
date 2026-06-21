#!/usr/bin/env python3
"""
AGY Download Monitor — A premium, highly readable terminal-based live download dashboard.
Supports monitoring up to 5 concurrent downloads in a split terminal card layout.

Features:
  • Responsive card layout (adapts to panel height and terminal size)
  • Boxed panels with neat unicode corners (┌ ┐ └ ┘ ─ │)
  • High-contrast color palette with clear status indicators
  • Shows application name, description, source, and detailed metadata
  • Animated progress bars, speed tracker, ETA calculation, and live log snippets
  • Supports: flatpak, apt, pip, npm, wget, curl, snap, and generic downloads
"""

import curses
import sys
import os
import re
import time
import json
import argparse
from collections import deque
from datetime import datetime

# Path definitions
ACTIVE_DIR = os.path.expanduser("~/Documents/agy-agent/downloads/active")
PID_FILE = os.path.expanduser("~/Documents/agy-agent/downloads/monitor.pid")

# ─── Progress Parsers ───────────────────────────────────────────────────────

class AptParser:
    name = "APT/DPKG"

    def parse(self, content):
        result = {
            "overall_percent": 0, "current_item": None, "item_percent": 0,
            "speed": "", "eta": "", "downloaded": "", "total_size": "",
            "status": "downloading", "phase": "Downloading packages", "log_lines": [],
        }
        if not content:
            return result

        lines = content.split("\n")
        log_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) > 3 and not re.match(r'^\d+%\s*\[', stripped):
                parts = stripped.split("\r")
                for p in parts:
                    p = p.strip()
                    if p and len(p) > 3 and not re.match(r'^\d+%\s*\[', p):
                        log_lines.append(p)
        result["log_lines"] = log_lines[-30:]

        all_progress = []
        for line in lines:
            parts = line.split("\r")
            for part in parts:
                part = part.strip()
                if re.match(r'^\d+%\s*\[', part):
                    all_progress.append(part)

        if all_progress:
            latest = all_progress[-1]
            m = re.match(r'^(\d+)%', latest)
            if m:
                result["overall_percent"] = int(m.group(1))

            pkg_match = re.search(r'\[\d+\s+(\S+)\s+([\d,]+\s*\w*B?)/([\d.]+\s*\w+B?)\s+(\d+)%\]', latest)
            if pkg_match:
                result["current_item"] = pkg_match.group(1)
                result["downloaded"] = pkg_match.group(2).replace(",", "")
                result["total_size"] = pkg_match.group(3)
                result["item_percent"] = int(pkg_match.group(4))
            else:
                pkg_match2 = re.search(r'\[\d+\s+(\S+)', latest)
                if pkg_match2:
                    result["current_item"] = pkg_match2.group(1)

            speed_match = re.search(r'(\d+[\d,.]*\s*[kMG]?B/s)', latest)
            if speed_match:
                result["speed"] = speed_match.group(1)

            eta_match = re.search(r'((?:\d+h\s*)?\d+min\s*\d+s|\d+s)\s*$', latest)
            if eta_match:
                result["eta"] = eta_match.group(1).strip()

        for line in lines[-30:]:
            if 'Unpacking' in line:
                result["status"] = "unpacking"
                result["phase"] = "Unpacking packages"
            elif 'Setting up' in line:
                result["status"] = "configuring"
                result["phase"] = "Configuring packages"
            elif 'Processing triggers' in line:
                result["status"] = "configuring"
                result["phase"] = "Processing triggers"
            elif 'is already the newest version' in line or 'newly installed' in line:
                result["status"] = "complete"
                result["phase"] = "Installation complete"
                result["overall_percent"] = 100

        if result["overall_percent"] >= 100 and result["status"] == "downloading":
            result["status"] = "unpacking"
            result["phase"] = "Download complete, processing..."

        return result


class PipParser:
    name = "PIP"

    def parse(self, content):
        result = {
            "overall_percent": 0, "current_item": None, "item_percent": 0,
            "speed": "", "eta": "", "downloaded": "", "total_size": "",
            "status": "downloading", "phase": "Downloading packages", "log_lines": [],
        }
        if not content:
            return result

        lines = content.strip().split("\n")
        result["log_lines"] = [l.strip() for l in lines[-30:] if l.strip()]

        for line in reversed(lines):
            dl = re.search(r'Downloading\s+(\S+).*?(\d+\.?\d*)\s*([kMG]?B)', line)
            if dl:
                result["current_item"] = dl.group(1).split("/")[-1]
                break
            inst = re.search(r'Installing collected packages:\s*(.+)', line)
            if inst:
                result["status"] = "configuring"
                result["phase"] = "Installing packages"
                result["current_item"] = inst.group(1).strip()
                result["overall_percent"] = 90
                break
            if 'Successfully installed' in line:
                result["status"] = "complete"
                result["phase"] = "Installation complete"
                result["overall_percent"] = 100
                break

        dl_lines = [l for l in lines if 'Downloading' in l]
        done_lines = [l for l in lines if 'already satisfied' in l.lower() or 'Using cached' in l]
        total = len(dl_lines) + len(done_lines)
        if total > 0 and result["status"] == "downloading":
            result["overall_percent"] = min(95, int((len(done_lines) + len(dl_lines)) / max(total, 1) * 95))

        return result


class FlatpakParser:
    name = "Flatpak"

    def parse(self, content):
        result = {
            "overall_percent": 0, "current_item": None, "item_percent": 0,
            "speed": "", "eta": "", "downloaded": "", "total_size": "",
            "status": "downloading", "phase": "Installing/Downloading", "log_lines": [],
        }
        if not content:
            return result

        lines = content.split("\n")
        result["log_lines"] = [l.strip() for l in lines[-30:] if l.strip()]

        for line in reversed(lines):
            pct_match = re.search(r'(\d+)%', line)
            if pct_match:
                result["overall_percent"] = int(pct_match.group(1))
            speed_match = re.search(r'(\d+[\d,.]*\s*[kMG]?B/s)', line)
            if speed_match:
                result["speed"] = speed_match.group(1)
            eta_match = re.search(r'(\d{2}:\d{2})', line)
            if eta_match:
                result["eta"] = eta_match.group(1)
            
            if pct_match or speed_match:
                break

        last_lines = " ".join(lines[-10:])
        if "Installing" in last_lines:
            result["status"] = "installing"
            result["phase"] = "Installing files..."
        if "complete" in last_lines.lower() or "installed" in last_lines.lower() or "which do you want to use" in last_lines.lower():
            if "which do you want to use" in last_lines.lower():
                result["status"] = "configuring"
                result["phase"] = "Waiting for configuration choice..."
            else:
                result["status"] = "complete"
                result["overall_percent"] = 100
                result["phase"] = "Complete"

        return result


class GenericParser:
    name = "Generic"

    def parse(self, content):
        result = {
            "overall_percent": 0, "current_item": None, "item_percent": 0,
            "speed": "", "eta": "", "downloaded": "", "total_size": "",
            "status": "downloading", "phase": "Processing", "log_lines": [],
        }
        if not content:
            return result

        lines = content.strip().split("\n")
        result["log_lines"] = [l.strip() for l in lines[-30:] if l.strip()]

        for line in reversed(lines):
            pct = re.search(r'(\d{1,3})%', line)
            if pct:
                result["overall_percent"] = min(100, int(pct.group(1)))
                break
            speed = re.search(r'(\d+[\d,.]*\s*[kMG]?B/s|\d+\s*[kMG]B/s)', line)
            if speed:
                result["speed"] = speed.group(1)

        if lines and ('done' in lines[-1].lower() or 'complete' in lines[-1].lower() or 'successfully' in lines[-1].lower()):
            result["status"] = "complete"
            result["overall_percent"] = 100

        return result


PARSERS = {
    "apt": AptParser,
    "pip": PipParser,
    "flatpak": FlatpakParser,
    "generic": GenericParser
}

# ─── Speed and Elapsed Trackers ─────────────────────────────────────────────

class SpeedTracker:
    def __init__(self):
        self.history = deque(maxlen=10)
        self.last_percent = 0
        self.last_time = time.time()
        self.start_time = time.time()

    def update(self, percent):
        now = time.time()
        dt = now - self.last_time
        if dt > 0.5 and percent != self.last_percent:
            rate = (percent - self.last_percent) / dt
            self.history.append(rate)
            self.last_percent = percent
            self.last_time = now

    def get_eta_seconds(self, current_percent):
        if not self.history or current_percent >= 100:
            return 0
        avg_rate = sum(self.history) / len(self.history)
        if avg_rate <= 0:
            return 0
        return (100 - current_percent) / avg_rate

    def get_elapsed(self):
        return time.time() - self.start_time


# ─── Layout Helpers ─────────────────────────────────────────────────────────

BLOCKS = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]

def draw_progress_bar(stdscr, y, x, width, percent, color_pair):
    """Draw a smooth progress bar with Unicode block characters."""
    bar_width = width - 2
    filled_exact = bar_width * (percent / 100.0)
    filled_full = int(filled_exact)
    partial_idx = int((filled_exact - filled_full) * 8)
    empty = bar_width - filled_full - (1 if partial_idx > 0 else 0)

    bar = BLOCKS[8] * filled_full
    if partial_idx > 0:
        bar += BLOCKS[partial_idx]
    bar += " " * empty

    try:
        stdscr.addstr(y, x, "▐", curses.color_pair(7) | curses.A_DIM)
        for i, ch in enumerate(bar):
            if i < filled_full:
                stdscr.addstr(y, x + 1 + i, ch, curses.color_pair(color_pair) | curses.A_BOLD)
            elif i == filled_full and partial_idx > 0:
                stdscr.addstr(y, x + 1 + i, ch, curses.color_pair(color_pair))
            else:
                stdscr.addstr(y, x + 1 + i, ch, curses.color_pair(8))
        stdscr.addstr(y, x + 1 + bar_width, "▌", curses.color_pair(7) | curses.A_DIM)
    except curses.error:
        pass


def format_time(seconds):
    if seconds <= 0:
        return "--:--"
    if seconds > 3600:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"


def get_status_info(status):
    mapping = {
        "downloading": ("▼", 2, "DOWNLOADING"),
        "unpacking":   ("⚙", 3, "UNPACKING"),
        "configuring": ("⚙", 3, "CONFIGURING"),
        "installing":  ("⚙", 3, "INSTALLING"),
        "complete":    ("✓", 4, "COMPLETE"),
    }
    return mapping.get(status, ("●", 1, status.upper()))


# ─── Curses UI Main loop ────────────────────────────────────────────────────

def main_loop(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(250)

    # Initialize Colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)       # default
    curses.init_pair(2, curses.COLOR_CYAN, -1)        # downloading
    curses.init_pair(3, curses.COLOR_YELLOW, -1)      # installing
    curses.init_pair(4, curses.COLOR_GREEN, -1)       # complete
    curses.init_pair(5, curses.COLOR_RED, -1)         # error
    curses.init_pair(6, curses.COLOR_MAGENTA, -1)     # purple headers
    curses.init_pair(7, curses.COLOR_BLUE, -1)        # border lines
    curses.init_pair(8, 236, -1)                      # dark bg progress track
    curses.init_pair(9, curses.COLOR_WHITE, curses.COLOR_BLUE)  # highlight active
    curses.init_pair(10, 245, -1)                     # gray details

    trackers = {}
    parsers = {}
    tick = 0

    while True:
        key = stdscr.getch()
        if key in (ord('q'), ord('Q'), 27):
            break

        tick += 1
        height, width = stdscr.getmaxyx()

        # Load active downloads from directory
        active_files = []
        if os.path.exists(ACTIVE_DIR):
            for entry in os.listdir(ACTIVE_DIR):
                if entry.endswith('.json'):
                    try:
                        with open(os.path.join(ACTIVE_DIR, entry)) as f:
                            data = json.load(f)
                            active_files.append((entry, data))
                    except Exception:
                        pass

        # Sort by started_at or filename
        active_files.sort(key=lambda x: x[1].get('started_at', x[0]))
        active_files = active_files[:5]  # limit to 5 active panels

        stdscr.erase()

        # Premium top header
        title_str = " ⚡ AGY DOWNLOAD MANAGER "
        desc_str = " Active Jobs: {} │ Q: Exit ".format(len(active_files))
        try:
            # Main border frame
            stdscr.addstr(0, 0, "┌" + "─" * (width - 2) + "┐", curses.color_pair(7))
            stdscr.addstr(1, 0, "│" + " " * (width - 2) + "│", curses.color_pair(7))
            stdscr.addstr(1, 2, title_str, curses.color_pair(6) | curses.A_BOLD)
            stdscr.addstr(1, width - len(desc_str) - 2, desc_str, curses.color_pair(10))
            stdscr.addstr(2, 0, "├" + "─" * (width - 2) + "┤", curses.color_pair(7))
        except curses.error:
            pass

        if not active_files:
            msg = "No active downloads registered. Waiting for jobs..."
            try:
                stdscr.addstr(height // 2, (width - len(msg)) // 2, msg, curses.color_pair(10) | curses.A_ITALIC)
                stdscr.addstr(height - 1, 0, "└" + "─" * (width - 2) + "┘", curses.color_pair(7))
            except curses.error:
                pass
            stdscr.refresh()
            continue

        # Render split panels with beautiful boxes
        avail_h = height - 4  # subtract header (3) and footer (1)
        panel_h = avail_h // len(active_files)
        y_offset = 3

        for idx, (entry_file, meta) in enumerate(active_files):
            task_id = meta.get('task_id', entry_file.replace('.json', ''))
            log_path = meta.get('log_file', '')
            app_name = meta.get('app_name', 'Unknown App')
            source = meta.get('source', 'Unknown Source')
            desc = meta.get('description', 'No description provided')
            ptype = meta.get('type', 'generic')

            # Initialize trackers/parsers for this task if new
            if task_id not in trackers:
                trackers[task_id] = SpeedTracker()
                parsers[task_id] = PARSERS.get(ptype, GenericParser)()

            tracker = trackers[task_id]
            parser = parsers[task_id]

            # Read log content
            content = ""
            if os.path.exists(log_path):
                try:
                    with open(log_path, 'r', errors='replace') as lf:
                        content = lf.read()
                except Exception:
                    pass

            # Parse details
            progress = parser.parse(content)
            tracker.update(progress["overall_percent"])

            # Status and progress bar variables
            pct = progress["overall_percent"]
            status_sym, color_pair, status_label = get_status_info(progress["status"])
            
            # Auto-cleanup complete downloads after a 10s linger
            if progress["status"] == "complete":
                meta['linger'] = meta.get('linger', 0) + 1
                if meta['linger'] > 40:  # 40 ticks = 10s
                    try:
                        os.remove(os.path.join(ACTIVE_DIR, entry_file))
                    except Exception:
                        pass

            # Compute panel box layout coordinates
            py = y_offset + idx * panel_h
            ph = panel_h - 1  # inner height of box

            card_w = min(width - 4, 116)
            cx = max(2, (width - card_w) // 2)

            # Draw card border
            try:
                # Top edge with app name
                header_title = " 📦 {} (Source: {}) ".format(app_name, source)
                stdscr.addstr(py, cx, "┌" + "─" * (card_w - 2) + "┐", curses.color_pair(7))
                stdscr.addstr(py, cx + 2, header_title, curses.color_pair(6) | curses.A_BOLD)

                # Draw vertical sides
                for line_offset in range(1, ph):
                    if py + line_offset < height - 1:
                        stdscr.addstr(py + line_offset, cx, "│", curses.color_pair(7))
                        stdscr.addstr(py + line_offset, cx + card_w - 1, "│", curses.color_pair(7))

                # Bottom edge
                if py + ph < height - 1:
                    stdscr.addstr(py + ph, cx, "└" + "─" * (card_w - 2) + "┘", curses.color_pair(7))
            except curses.error:
                pass

            # Draw Content (Responsive based on panel height)
            col_inner_w = card_w - 4
            content_x = cx + 2

            if ph >= 5:
                # Layout for larger panel size
                # Line 1: Status Banner
                status_str = "{} Status: {} │ Progress: {}%".format(status_sym, status_label, pct)
                try:
                    stdscr.addstr(py + 1, content_x, status_str, curses.color_pair(color_pair) | curses.A_BOLD)
                    stdscr.addstr(py + 1, content_x + len(status_str) + 4, "— " + desc[:col_inner_w - len(status_str) - 6], curses.color_pair(10))
                except curses.error:
                    pass

                # Line 2: Progress bar & stats
                bar_w = col_inner_w - 44
                draw_progress_bar(stdscr, py + 2, content_x, bar_w, pct, color_pair)

                speed_val = progress.get('speed') or "--"
                calc_eta = format_time(tracker.get_eta_seconds(pct))
                eta_val = progress.get('eta') or calc_eta
                elapsed = format_time(tracker.get_elapsed())
                stats_str = "⚡ {} │ ⏱ {} │ ⏳ {}".format(speed_val, eta_val, elapsed)
                try:
                    stdscr.addstr(py + 2, content_x + bar_w + 2, stats_str.rjust(card_w - bar_w - 6), curses.color_pair(1))
                except curses.error:
                    pass

                # Line 3: Log preview
                log_snippet = progress.get('log_lines', [])
                if log_snippet and py + 3 < py + ph:
                    latest_line = log_snippet[-1]
                    try:
                        stdscr.addstr(py + 3, content_x, "💬 Log: {}".format(latest_line[:col_inner_w - 8]), curses.color_pair(10))
                    except curses.error:
                        pass

            elif ph >= 3:
                # Compact Layout (smaller panels)
                # Line 1: Combine Status, Percent and Progress Bar
                status_str = "{} {} ({}%) ".format(status_sym, status_label, pct)
                try:
                    stdscr.addstr(py + 1, content_x, status_str, curses.color_pair(color_pair) | curses.A_BOLD)
                except curses.error:
                    pass

                bar_x = content_x + len(status_str)
                bar_w = col_inner_w - len(status_str) - 36
                if bar_w > 10:
                    draw_progress_bar(stdscr, py + 1, bar_x, bar_w, pct, color_pair)
                else:
                    bar_w = -2

                speed_val = progress.get('speed') or "--"
                calc_eta = format_time(tracker.get_eta_seconds(pct))
                eta_val = progress.get('eta') or calc_eta
                stats_str = "⚡ {} │ ⏱ {}".format(speed_val, eta_val)
                try:
                    stdscr.addstr(py + 1, content_x + len(status_str) + max(0, bar_w) + 2, stats_str.rjust(col_inner_w - len(status_str) - max(0, bar_w) - 2), curses.color_pair(1))
                except curses.error:
                    pass
            else:
                # Ultra compact (minimal line)
                status_line = "{} {} │ Progress: {}% │ Speed: {}".format(status_sym, app_name, pct, progress.get('speed') or "--")
                try:
                    stdscr.addstr(py + 1, content_x, status_line[:col_inner_w], curses.color_pair(color_pair))
                except curses.error:
                    pass

        # Global Bottom Border
        try:
            stdscr.addstr(height - 1, 0, "└" + "─" * (width - 2) + "┘", curses.color_pair(7))
        except curses.error:
            pass

        stdscr.refresh()

    # Clear PID file upon exit
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass


def check_single_instance():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            print("AGY Multi-Monitor is already running (PID: {}).".format(pid))
            return False
        except (ValueError, OSError):
            pass
    
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True


if __name__ == '__main__':
    if not check_single_instance():
        sys.exit(0)
        
    try:
        curses.wrapper(main_loop)
    except KeyboardInterrupt:
        pass
    finally:
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass

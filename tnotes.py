#!/usr/bin/env python3
"""tnotes - a modern-looking terminal notepad with multiple notes (stdlib only).

Usage:  python3 tnotes.py
Notes are stored as .txt files in ~/.tnotes (override with TNOTES_DIR).
On Windows, first run:  pip install windows-curses

List:    up/down select | enter open | n new | r rename | d delete | q quit
Editor:  ctrl+s save | ctrl+q back to list
"""
import curses
import locale
import os
import time

NOTES_DIR = os.environ.get("TNOTES_DIR", os.path.expanduser("~/.tnotes"))
DIM = curses.A_DIM
BOLD = curses.A_BOLD
GREEN = 0  # set to a color pair once curses starts


# ---------- drawing helpers ----------
def safe_add(scr, y, x, s, attr=0):
    h, w = scr.getmaxyx()
    if y < 0 or y >= h or x >= w - 1:
        return
    try:
        scr.addstr(y, x, s[:max(0, w - x - 1)], attr)
    except curses.error:
        pass


def draw_box(scr, y, x, bw, bh, attr=0):
    safe_add(scr, y, x, "┌" + "─" * (bw - 2) + "┐", attr)
    for r in range(1, bh - 1):
        safe_add(scr, y + r, x, "│" + " " * (bw - 2) + "│", attr)
    safe_add(scr, y + bh - 1, x, "└" + "─" * (bw - 2) + "┘", attr)


def header(scr, title, sub=""):
    safe_add(scr, 1, 2, "⬢", GREEN | BOLD)
    safe_add(scr, 1, 4, title, BOLD)
    if sub:
        safe_add(scr, 1, 5 + len(title), sub, DIM)


def input_box(scr, text, hint=""):
    """Three-row bordered box at the bottom, like a chat input."""
    h, w = scr.getmaxyx()
    for r in (h - 4, h - 3, h - 2):
        scr.move(r, 0)
        scr.clrtoeol()
    draw_box(scr, h - 4, 2, w - 4, 3, DIM)
    safe_add(scr, h - 3, 4, "→", DIM)
    safe_add(scr, h - 3, 6, text[-(w - 11):] if text else hint, 0 if text else DIM)
    return h - 3, 6 + min(len(text), w - 11)


def footer(scr, hints, msg=""):
    h, _ = scr.getmaxyx()
    scr.move(h - 1, 0)
    scr.clrtoeol()
    safe_add(scr, h - 1, 2, msg or hints, DIM)


def too_small(scr):
    h, w = scr.getmaxyx()
    if h < 10 or w < 30:
        scr.erase()
        safe_add(scr, 0, 0, "Window too small", DIM)
        scr.refresh()
        return True
    return False


def set_cursor(visible):
    try:
        curses.curs_set(1 if visible else 0)
    except curses.error:
        pass


def prompt(scr, label, initial=""):
    """Read a line inside the bottom input box. Esc cancels (returns '')."""
    buf = initial
    set_cursor(True)
    while True:
        y, x = input_box(scr, label + buf)
        footer(scr, "enter confirm · esc cancel")
        try:
            scr.move(y, x)
        except curses.error:
            pass
        scr.refresh()
        k = scr.get_wch()
        if k in ("\n", "\r"):
            return buf.strip()
        if k == "\x1b":
            return ""
        if k in ("\x7f", "\b", curses.KEY_BACKSPACE):
            buf = buf[:-1]
        elif isinstance(k, str) and k.isprintable():
            buf += k


def note_path(name):
    name = os.path.basename(name)
    if not name.endswith(".txt"):
        name += ".txt"
    return os.path.join(NOTES_DIR, name)


# ---------- editor ----------
class Editor:
    HINTS = "ctrl+s save · ctrl+q back to list"

    def __init__(self, path=None):
        self.path = path
        self.lines = [""]
        self.cy = self.cx = 0
        self.top = self.left = 0
        self.dirty = False
        self.quit_armed = False
        self.msg = ""
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.lines = f.read().split("\n")

    # file
    def save(self, scr):
        if not self.path:
            name = prompt(scr, "Note name: ")
            if not name:
                self.msg = "Save cancelled"
                return
            path = note_path(name)
            if os.path.exists(path):
                self.msg = "A note with that name already exists"
                return
            self.path = path
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.lines))
            self.dirty = False
            self.msg = "Saved"
        except OSError as e:
            self.msg = f"Error: {e}"

    # editing
    def insert(self, ch):
        line = self.lines[self.cy]
        self.lines[self.cy] = line[:self.cx] + ch + line[self.cx:]
        self.cx += len(ch)
        self.dirty = True

    def newline(self):
        line = self.lines[self.cy]
        self.lines[self.cy] = line[:self.cx]
        self.lines.insert(self.cy + 1, line[self.cx:])
        self.cy += 1
        self.cx = 0
        self.dirty = True

    def backspace(self):
        if self.cx > 0:
            line = self.lines[self.cy]
            self.lines[self.cy] = line[:self.cx - 1] + line[self.cx:]
            self.cx -= 1
            self.dirty = True
        elif self.cy > 0:
            prev = self.lines[self.cy - 1]
            self.cx = len(prev)
            self.lines[self.cy - 1] = prev + self.lines.pop(self.cy)
            self.cy -= 1
            self.dirty = True

    def delete(self):
        line = self.lines[self.cy]
        if self.cx < len(line):
            self.lines[self.cy] = line[:self.cx] + line[self.cx + 1:]
            self.dirty = True
        elif self.cy < len(self.lines) - 1:
            self.lines[self.cy] += self.lines.pop(self.cy + 1)
            self.dirty = True

    def move(self, dy, dx, page=0):
        if dx == -1 and self.cx == 0 and self.cy > 0:
            self.cy -= 1
            self.cx = len(self.lines[self.cy])
        elif dx == 1 and self.cx >= len(self.lines[self.cy]) and self.cy < len(self.lines) - 1:
            self.cy += 1
            self.cx = 0
        else:
            self.cx += dx
        self.cy = max(0, min(len(self.lines) - 1, self.cy + dy + page))
        self.cx = max(0, min(len(self.lines[self.cy]), self.cx))

    # drawing
    def draw(self, scr):
        if too_small(scr):
            return
        scr.erase()
        h, w = scr.getmaxyx()
        name = os.path.basename(self.path) if self.path else "untitled"
        header(scr, name + (" *" if self.dirty else ""),
               f"   Ln {self.cy + 1}, Col {self.cx + 1}")

        # text box occupies rows 2 .. h-3
        draw_box(scr, 2, 2, w - 4, h - 4, DIM)
        text_h = h - 6
        g = len(str(len(self.lines)))
        tx = 4 + g + 1
        text_w = max(1, w - 3 - tx)

        if self.cy < self.top:
            self.top = self.cy
        elif self.cy >= self.top + text_h:
            self.top = self.cy - text_h + 1
        if self.cx < self.left:
            self.left = self.cx
        elif self.cx >= self.left + text_w:
            self.left = self.cx - text_w + 1

        for row in range(text_h):
            i = self.top + row
            if i >= len(self.lines):
                break
            safe_add(scr, 3 + row, 4, str(i + 1).rjust(g), DIM)
            safe_add(scr, 3 + row, tx, self.lines[i][self.left:self.left + text_w])

        footer(scr, self.HINTS, self.msg)
        set_cursor(True)
        try:
            scr.move(3 + self.cy - self.top, tx + self.cx - self.left)
        except curses.error:
            pass
        scr.refresh()

    # input
    def handle(self, scr, k):
        h, _ = scr.getmaxyx()
        page = max(1, h - 7)
        if k != "\x11":
            self.quit_armed = False
        if k != "\x11" and k != "\x13":
            self.msg = ""

        if k == "\x11":  # ctrl+q
            if self.dirty and not self.quit_armed:
                self.quit_armed = True
                self.msg = "Unsaved! ctrl+q again to discard, ctrl+s to save"
            else:
                return False
        elif k == "\x13":  # ctrl+s
            self.save(scr)
        elif k == curses.KEY_UP:
            self.move(-1, 0)
        elif k == curses.KEY_DOWN:
            self.move(1, 0)
        elif k == curses.KEY_LEFT:
            self.move(0, -1)
        elif k == curses.KEY_RIGHT:
            self.move(0, 1)
        elif k == curses.KEY_HOME:
            self.cx = 0
        elif k == curses.KEY_END:
            self.cx = len(self.lines[self.cy])
        elif k == curses.KEY_PPAGE:
            self.move(0, 0, -page)
        elif k == curses.KEY_NPAGE:
            self.move(0, 0, page)
        elif k in ("\n", "\r", curses.KEY_ENTER):
            self.newline()
        elif k in ("\x7f", "\b", curses.KEY_BACKSPACE):
            self.backspace()
        elif k == curses.KEY_DC:
            self.delete()
        elif k == "\t":
            self.insert("    ")
        elif isinstance(k, str) and k.isprintable():
            self.insert(k)
        return True

    def run(self, scr):
        while True:
            self.draw(scr)
            try:
                k = scr.get_wch()
            except (KeyboardInterrupt, curses.error):
                continue
            if k == curses.KEY_RESIZE:
                continue
            if not self.handle(scr, k):
                return


# ---------- note list ----------
LIST_HINTS = "n new · r rename · d delete · q quit"


def list_notes():
    files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".txt")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(NOTES_DIR, f)), reverse=True)
    return files


def first_line(path, width):
    try:
        with open(path, encoding="utf-8") as f:
            return f.readline().strip()[:max(0, width)]
    except OSError:
        return ""


def list_screen(scr):
    sel = top = 0
    msg = ""
    while True:
        files = list_notes()
        sel = max(0, min(sel, len(files) - 1))
        if too_small(scr):
            scr.get_wch()
            continue
        h, w = scr.getmaxyx()
        rows = max(1, h - 8)
        if sel < top:
            top = sel
        elif sel >= top + rows:
            top = sel - rows + 1

        scr.erase()
        set_cursor(False)
        header(scr, "Notepad", f"   {len(files)} note{'' if len(files) == 1 else 's'}")
        if not files:
            safe_add(scr, 3, 4, "No notes yet.", DIM)
        for r in range(rows):
            i = top + r
            if i >= len(files):
                break
            path = os.path.join(NOTES_DIR, files[i])
            date = time.strftime("%b %d", time.localtime(os.path.getmtime(path)))
            name = files[i][:-4][:14].ljust(14)
            on = i == sel
            safe_add(scr, 3 + r, 2, "▸" if on else " ", GREEN | BOLD)
            safe_add(scr, 3 + r, 4, name, BOLD if on else DIM)
            safe_add(scr, 3 + r, 20, date, DIM)
            safe_add(scr, 3 + r, 28, first_line(path, w - 32), 0 if on else DIM)

        input_box(scr, "", "Press n to write a new note")
        footer(scr, LIST_HINTS, msg)
        scr.refresh()
        msg = ""

        try:
            k = scr.get_wch()
        except (KeyboardInterrupt, curses.error):
            continue
        cur = os.path.join(NOTES_DIR, files[sel]) if files else None

        if k in (curses.KEY_UP, "k"):
            sel -= 1
        elif k in (curses.KEY_DOWN, "j"):
            sel += 1
        elif k in ("\n", "\r", curses.KEY_ENTER) and cur:
            Editor(cur).run(scr)
        elif k == "n":
            Editor(None).run(scr)
        elif k == "r" and cur:
            new = prompt(scr, "Rename to: ", files[sel][:-4])
            if new:
                dest = note_path(new)
                if os.path.exists(dest) and dest != cur:
                    msg = "A note with that name already exists"
                else:
                    os.rename(cur, dest)
        elif k == "d" and cur:
            input_box(scr, f"Delete '{files[sel][:-4]}'? (y/n)")
            scr.refresh()
            if scr.get_wch() in ("y", "Y"):
                os.remove(cur)
                msg = "Deleted"
        elif k in ("q", "\x11"):
            return


def main():
    locale.setlocale(locale.LC_ALL, "")
    os.makedirs(NOTES_DIR, exist_ok=True)

    def run(scr):
        global GREEN
        curses.raw()  # lets ctrl+s / ctrl+q reach the program
        scr.keypad(True)
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            GREEN = curses.color_pair(1)
        except curses.error:
            GREEN = 0
        list_screen(scr)

    curses.wrapper(run)


if __name__ == "__main__":
    main()

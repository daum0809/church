"""주일예배 PDF 만들기 (창 프로그램).

주보 한글 파일(.hwp/.hwpx)을 창에 끌어다 놓거나 [주보 파일 선택]을 누르면
예배용 PDF 가 만들어지고 바로 열립니다.
exe 아이콘 위에 주보 파일을 끌어다 놓아도 됩니다.
"""

import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from worship import paths
from worship.run import ERRORS, HWP_EXT, run

try:  # 창에 끌어다 놓기 (없어도 동작)
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = TkinterDnD = None

TITLE = "주일예배 PDF 만들기"
FONT = ("맑은 고딕", 11) if sys.platform.startswith("win") else ("Noto Sans CJK KR", 11)
DARK, LIGHT, ACCENT = "#333333", "#f3f1ee", "#5b5148"


def open_path(path):
    path = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as e:
        messagebox.showinfo(TITLE, f"파일을 열 수 없습니다: {path}\n{e}")


class App:
    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self.pdf = None
        self.busy = False
        root.title(TITLE)
        root.geometry("720x560")
        root.minsize(560, 420)
        root.configure(bg=LIGHT)

        tk.Label(root, text=TITLE, font=(FONT[0], 18, "bold"), bg=LIGHT, fg=DARK).pack(pady=(14, 4))

        self.drop = tk.Label(
            root, bg="white", fg=ACCENT, font=(FONT[0], 13), relief="groove", bd=2, height=4,
            text=("여기에 주보 파일(.hwp / .hwpx)을 끌어다 놓으세요\n또는 아래 [주보 파일 선택] 을 누르세요"
                  if TkinterDnD else "아래 [주보 파일 선택] 을 눌러 주보 파일(.hwp / .hwpx)을 고르세요"))
        self.drop.pack(fill="x", padx=16, pady=8)
        if TkinterDnD:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self.on_drop)

        bar = tk.Frame(root, bg=LIGHT)
        bar.pack(fill="x", padx=16)
        self.buttons = [
            self._button(bar, "주보 파일 선택", self.choose, primary=True),
            self._button(bar, "입력 내용 고치기", self.edit_weekly),
            self._button(bar, "고친 내용으로 다시 만들기", self.rebuild),
        ]

        self.log_box = ScrolledText(root, font=(FONT[0], 10), height=14, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=16, pady=8)

        bottom = tk.Frame(root, bg=LIGHT)
        bottom.pack(fill="x", padx=16, pady=(0, 12))
        self.open_btn = self._button(bottom, "PDF 열기", lambda: self.pdf and open_path(self.pdf))
        self.open_btn.configure(state="disabled")
        self._button(bottom, "결과 폴더 열기", lambda: open_path(paths.OUTPUT))
        self._button(bottom, "악보 넣는 폴더", lambda: open_path(paths.INBOX))
        self.status = tk.Label(bottom, text="", bg=LIGHT, fg=ACCENT, font=FONT)
        self.status.pack(side="right")

        paths.setup()
        self.log("주보 한글 파일을 넣으면 예배 PDF 를 만듭니다.")
        self.log(f"작업 폴더: {paths.HOME}\n")
        root.after(100, self.poll)

    def _button(self, parent, text, command, primary=False):
        b = tk.Button(parent, text=text, command=command, font=FONT, padx=10, pady=4,
                      bg=DARK if primary else "white", fg="white" if primary else DARK,
                      activebackground=ACCENT, activeforeground="white", relief="flat", bd=1)
        b.pack(side="left", padx=(0, 8), pady=4)
        return b

    # ---------------------------------------------------------------- 동작
    def on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        if files:
            self.start(files[0])

    def choose(self):
        path = filedialog.askopenfilename(
            title="주보 파일 선택", initialdir=str(paths.BULLETIN_DIR),
            filetypes=[("한글 문서", "*.hwp *.hwpx"), ("모든 파일", "*.*")])
        if path:
            self.start(path)

    def edit_weekly(self):
        paths.setup()
        open_path(paths.WEEKLY)

    def rebuild(self):
        self.start(None)

    def start(self, path):
        if self.busy:
            return
        if path and Path(path).suffix.lower() not in HWP_EXT | {".yaml", ".yml"}:
            messagebox.showwarning(TITLE, "주보 한글 파일(.hwp / .hwpx)을 넣어 주세요.")
            return
        self.busy = True
        self.pdf = None
        self.open_btn.configure(state="disabled")
        for b in self.buttons:
            b.configure(state="disabled")
        self.status.configure(text="만드는 중...")
        self.log("─" * 40)
        threading.Thread(target=self.work, args=(path,), daemon=True).start()

    def work(self, path):
        try:
            pdf, todo = run(path, log=lambda m: self.queue.put(("log", m)))
            self.queue.put(("done", (pdf, todo)))
        except ERRORS as e:
            self.queue.put(("error", str(e)))
        except Exception:  # 예상 못 한 오류도 창에 보여 줌
            self.queue.put(("error", traceback.format_exc()))

    def poll(self):
        try:
            while True:
                kind, value = self.queue.get_nowait()
                if kind == "log":
                    self.log(value)
                elif kind == "done":
                    self.finish(*value)
                elif kind == "error":
                    self.fail(value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def finish(self, pdf, todo):
        self.busy = False
        self.pdf = pdf
        for b in self.buttons:
            b.configure(state="normal")
        self.open_btn.configure(state="normal")
        if todo:
            self.status.configure(text=f"완성 (확인 필요 {len(todo)}건)")
            self.log("\n※ [확인 필요] 항목은 [입력 내용 고치기] 로 채운 뒤 [고친 내용으로 다시 만들기] 를 누르세요.")
        else:
            self.status.configure(text="완성")
        open_path(pdf)

    def fail(self, message):
        self.busy = False
        for b in self.buttons:
            b.configure(state="normal")
        self.status.configure(text="오류")
        self.log(f"\n[오류] {message}")
        messagebox.showerror(TITLE, message.splitlines()[0] if message else "오류가 났습니다.")

    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


def main():
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    app = App(root)
    if len(sys.argv) > 1:  # exe 아이콘에 파일을 끌어다 놓은 경우
        root.after(300, lambda: app.start(sys.argv[1]))
    root.mainloop()


if __name__ == "__main__":
    main()

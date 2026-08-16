# -*- coding: utf-8 -*-
"""
座標區塊連結爬取工具（獨立，不影響筆記產生器）

用法：
1. 先開好 Chrome／Edge
2. 用「取得滑鼠座標.ahk」對準「目錄／列表區塊」按 F8 取得 X,Y
3. 在本工具填入頁面連結與座標 → 開始抓取
4. 輸出 [{存檔名稱, 素材連結}, ...] 供腳本產生器匯入
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
AHK_NAV = ROOT / "控制已開瀏覽器.ahk"
TASKS_DIR = ROOT / "tasks"
DEFAULT_CLASS = "sc-jqnqvi-1 dyUpZz"


def find_ahk_exe() -> str:
    cands = [
        r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe",
        r"C:\Program Files\AutoHotkey\v2\AutoHotkey32.exe",
        r"C:\Program Files\AutoHotkey\AutoHotkey64.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "AutoHotkey" / "v2" / "AutoHotkey64.exe"),
    ]
    for p in cands:
        if p and Path(p).is_file():
            return p
    return ""


def browser_exe_name(channel: str) -> str:
    return "msedge.exe" if channel == "msedge" else "chrome.exe"


def run_ahk(cmd: str, *args: str) -> subprocess.CompletedProcess:
    ahk = find_ahk_exe()
    if not ahk or not AHK_NAV.is_file():
        raise RuntimeError("找不到 AutoHotkey v2 或 控制已開瀏覽器.ahk")
    # 避免 AHK 錯誤視窗卡死；錯誤會寫 stdout 或 %TEMP%\ause_ahk_err.log
    return subprocess.run(
        [ahk, "/ErrorStdOut", str(AHK_NAV), cmd, *[str(a) for a in args]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )


def _ahk_err_text(r: subprocess.CompletedProcess) -> str:
    parts = [((r.stdout or "") + (r.stderr or "")).strip()]
    log = Path(os.environ.get("TEMP", tempfile.gettempdir())) / "ause_ahk_err.log"
    if log.is_file():
        try:
            parts.append(log.read_text(encoding="utf-8", errors="replace").strip()[-800:])
        except OSError:
            pass
    return "\n".join(p for p in parts if p)


def ahk_goto(url: str, channel: str) -> None:
    r = run_ahk("goto", url, browser_exe_name(channel))
    if r.returncode != 0:
        raise RuntimeError("無法開啟連結。請先手動打開瀏覽器。\n" + _ahk_err_text(r))


def ahk_click_xy(x: int, y: int, channel: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
        f.write(f"座標\n{x},{y}\n\n")
        path = f.name
    try:
        r = run_ahk("click", path, browser_exe_name(channel))
        if r.returncode != 0:
            raise RuntimeError("座標點擊失敗。\n" + _ahk_err_text(r))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def ahk_linklist(x: int, y: int, climb: int, channel: str) -> list[dict]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
        f.write(f"{x}\n{y}\n{climb}\n")
        param = f.name
    out = Path(tempfile.gettempdir()) / f"ause_linklist_{os.getpid()}.json"
    try:
        if out.exists():
            out.unlink()
        r = run_ahk("linklist", param, browser_exe_name(channel), str(out))
        err = _ahk_err_text(r)
        if r.returncode != 0 or not out.is_file():
            raise RuntimeError(
                "抓取連結失敗。請確認：\n"
                "1. Chrome 已開著目標頁\n"
                "2. 座標是對「目錄／列表」按 F8 取得\n"
                "3. 抓取時不要切走視窗\n\n" + err
            )
        raw = out.read_text(encoding="utf-8-sig").strip()
        data = json.loads(raw)
        if not isinstance(data, list):
            raise RuntimeError("回傳不是清單 JSON")
        items = []
        for it in data:
            if not isinstance(it, dict):
                continue
            name = str(it.get("存檔名稱") or "").strip()
            link = str(it.get("素材連結") or "").strip()
            if name and link:
                items.append({"存檔名稱": name, "素材連結": link})
        if not items:
            raise RuntimeError("沒有有效的存檔名稱／素材連結")
        return items
    finally:
        try:
            os.unlink(param)
        except OSError:
            pass
        try:
            if out.exists():
                out.unlink()
        except OSError:
            pass


def with_exec_steps(items: list[dict], click_x: int, click_y: int, css_class: str) -> list[dict]:
    """轉成可直接給 run_task_json / 產生器的完整任務。"""
    out = []
    for it in items:
        out.append(
            {
                "存檔名稱": it["存檔名稱"],
                "素材連結": it["素材連結"],
                "執行": [
                    {
                        "動作": "點擊",
                        "定位": "座標",
                        "X": click_x,
                        "Y": click_y,
                        "等待毫秒": 2000,
                        "_說明": "預設點「逐字稿」座標；請依實際頁面調整",
                    },
                    {
                        "動作": "爬蟲",
                        "定位": "class",
                        "值": css_class or DEFAULT_CLASS,
                        "範圍": "body",
                        "含底下全部": False,
                        "只取內文": True,
                    },
                ],
            }
        )
    return out


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("座標區塊連結爬取工具")
        self.geometry("780x700")
        self.minsize(700, 600)
        self.items: list[dict] = []
        self.last_saved = ""
        self._busy = False

        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        # 顯眼狀態條
        self.banner = tk.Label(
            frm,
            text="待命：填座標後按「開始抓取」",
            font=("Microsoft JhengHei UI", 12, "bold"),
            fg="#111",
            bg="#e9ecef",
            anchor="w",
            padx=12,
            pady=10,
        )
        self.banner.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        ttk.Label(frm, text="頁面連結（可先手動開好頁，再取消勾選「先開啟連結」）").grid(
            row=1, column=0, sticky="w", **pad
        )
        self.url = tk.StringVar()
        ttk.Entry(frm, textvariable=self.url).grid(row=2, column=0, columnspan=3, sticky="ew", **pad)

        row2 = ttk.Frame(frm)
        row2.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(row2, text="區塊座標 X").pack(side="left")
        self.x = tk.StringVar(value="0")
        ttk.Entry(row2, textvariable=self.x, width=8).pack(side="left", padx=(6, 16))
        ttk.Label(row2, text="Y").pack(side="left")
        self.y = tk.StringVar(value="0")
        ttk.Entry(row2, textvariable=self.y, width=8).pack(side="left", padx=(6, 16))
        ttk.Label(row2, text="向上找層數").pack(side="left")
        self.climb = tk.StringVar(value="8")
        ttk.Entry(row2, textvariable=self.climb, width=5).pack(side="left", padx=6)

        row3 = ttk.Frame(frm)
        row3.grid(row=4, column=0, columnspan=3, sticky="w", **pad)
        self.open_url = tk.BooleanVar(value=True)
        self.click_first = tk.BooleanVar(value=False)
        self.full_task = tk.BooleanVar(value=False)
        self.auto_save = tk.BooleanVar(value=True)
        ttk.Checkbutton(row3, text="先開啟連結", variable=self.open_url).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(row3, text="先點擊該座標再抓", variable=self.click_first).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(row3, text="輸出含預設執行步驟", variable=self.full_task).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(row3, text="成功後自動存到 tasks", variable=self.auto_save).pack(side="left")

        row4 = ttk.Frame(frm)
        row4.grid(row=5, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(row4, text="瀏覽器").pack(side="left")
        self.browser = tk.StringVar(value="chrome")
        ttk.Combobox(row4, textvariable=self.browser, values=["chrome", "msedge"], width=10, state="readonly").pack(
            side="left", padx=6
        )
        ttk.Label(row4, text="完整任務用 class").pack(side="left", padx=(16, 0))
        self.css = tk.StringVar(value=DEFAULT_CLASS)
        ttk.Entry(row4, textvariable=self.css, width=28).pack(side="left", padx=6)

        tip = (
            "流程：對準目錄列表按 F8 取座標 → 開始抓取 → 上方狀態條變綠色＝成功。\n"
            "執行中請勿操作瀏覽器；會短暫開啟 F12 Console。"
        )
        ttk.Label(frm, text=tip, foreground="#555").grid(row=6, column=0, columnspan=3, sticky="w", **pad)

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=3, sticky="ew", **pad)
        self.btn_run = ttk.Button(btns, text="▶ 開始抓取", command=self.on_run)
        self.btn_run.pack(side="left")
        self.btn_save = ttk.Button(btns, text="儲存 JSON", command=self.on_save)
        self.btn_save.pack(side="left", padx=8)
        self.btn_copy = ttk.Button(btns, text="複製 JSON", command=self.on_copy)
        self.btn_copy.pack(side="left")
        ttk.Button(btns, text="開 tasks 資料夾", command=self.on_open_tasks).pack(side="left", padx=8)

        self.count_var = tk.StringVar(value="結果：尚未抓取（0 筆）")
        ttk.Label(frm, textvariable=self.count_var, font=("Microsoft JhengHei UI", 10, "bold")).grid(
            row=8, column=0, columnspan=3, sticky="w", **pad
        )

        # 結果表格（比純 JSON 更容易看出有沒有抓到）
        tree_fr = ttk.Frame(frm)
        tree_fr.grid(row=9, column=0, columnspan=3, sticky="nsew", **pad)
        self.tree = ttk.Treeview(tree_fr, columns=("name", "url"), show="headings", height=10)
        self.tree.heading("name", text="存檔名稱")
        self.tree.heading("url", text="素材連結")
        self.tree.column("name", width=260, anchor="w")
        self.tree.column("url", width=420, anchor="w")
        sy = ttk.Scrollbar(tree_fr, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")

        ttk.Label(frm, text="JSON 預覽").grid(row=10, column=0, sticky="w", **pad)
        self.preview = tk.Text(frm, height=8, wrap="word")
        self.preview.grid(row=11, column=0, columnspan=3, sticky="nsew", **pad)

        frm.rowconfigure(9, weight=2)
        frm.rowconfigure(11, weight=1)
        frm.columnconfigure(0, weight=1)

    def set_banner(self, text: str, kind: str = "idle") -> None:
        colors = {
            "idle": ("#111", "#e9ecef"),
            "run": ("#7a4d00", "#fff3cd"),
            "ok": ("#0b3d1f", "#d1e7dd"),
            "err": ("#5c1010", "#f8d7da"),
        }
        fg, bg = colors.get(kind, colors["idle"])
        self.banner.configure(text=text, fg=fg, bg=bg)
        self.update_idletasks()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn_run.configure(state=state)
        self.btn_save.configure(state=state)
        self.btn_copy.configure(state=state)

    def fill_results(self, items: list[dict]) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        for idx, it in enumerate(items, 1):
            self.tree.insert(
                "",
                "end",
                values=(f"{idx}. {it.get('存檔名稱', '')}", it.get("素材連結", "")),
            )
        self.count_var.set(f"結果：已抓到 {len(items)} 筆")
        if self.full_task.get():
            x, y, _ = self._parse_xy()
            payload = with_exec_steps(items, x, y, self.css.get().strip())
        else:
            payload = items
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)

    def _parse_xy(self) -> tuple[int, int, int]:
        try:
            x = int(str(self.x.get()).strip())
            y = int(str(self.y.get()).strip())
            climb = int(str(self.climb.get()).strip() or "8")
        except ValueError as e:
            raise ValueError("X / Y / 層數必須是整數") from e
        if x < 0 or y < 0 or (x == 0 and y == 0):
            raise ValueError("請填有效座標（用取得滑鼠座標.ahk → F8）")
        return x, y, max(1, min(20, climb))

    def _payload(self) -> list[dict]:
        if not self.items:
            raise RuntimeError("尚無資料，請先抓取成功後再儲存／複製")
        x, y, _ = self._parse_xy()
        if self.full_task.get():
            return with_exec_steps(self.items, x, y, self.css.get().strip())
        return list(self.items)

    def _auto_save_tasks(self, data: list[dict]) -> str:
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = TASKS_DIR / f"區塊連結_{stamp}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.last_saved = str(path)
        return str(path)

    def on_run(self) -> None:
        if self._busy:
            return
        import time

        try:
            x, y, climb = self._parse_xy()
            channel = self.browser.get().strip() or "chrome"
            url = self.url.get().strip()
            self.set_busy(True)
            self.set_banner("執行中…請勿操作瀏覽器（約 10～30 秒）", "run")
            self.count_var.set("結果：抓取中…")
            self.update_idletasks()

            if self.open_url.get():
                if not url:
                    raise ValueError("已勾選「先開啟連結」，請填頁面 URL")
                self.set_banner("步驟 1/3：開啟頁面連結…", "run")
                ahk_goto(url, channel)
                time.sleep(2.5)

            if self.click_first.get():
                self.set_banner("步驟 2/3：點擊指定座標…", "run")
                ahk_click_xy(x, y, channel)
                time.sleep(1.2)

            self.set_banner("步驟 3/3：開 F12 抓取區塊連結…", "run")
            items = ahk_linklist(x, y, climb, channel)
            self.items = items
            self.fill_results(items)

            saved_msg = ""
            if self.auto_save.get():
                path = self._auto_save_tasks(self._payload())
                saved_msg = f"\n已自動存檔：\n{path}"

            self.set_banner(f"成功：抓到 {len(items)} 筆連結", "ok")
            messagebox.showinfo(
                "抓取成功",
                f"已成功抓到 {len(items)} 筆\n"
                f"（存檔名稱 + 素材連結）\n"
                f"請看上方綠條與下方列表確認。{saved_msg}",
            )
        except Exception as e:
            self.items = []
            for i in self.tree.get_children():
                self.tree.delete(i)
            self.count_var.set("結果：失敗（0 筆）")
            self.preview.delete("1.0", "end")
            self.set_banner("失敗：沒有抓到資料", "err")
            messagebox.showerror("抓取失敗", str(e))
        finally:
            self.set_busy(False)

    def on_save(self) -> None:
        try:
            data = self._payload()
            TASKS_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default = TASKS_DIR / f"區塊連結_{stamp}.json"
            path = filedialog.asksaveasfilename(
                title="儲存 JSON",
                initialdir=str(TASKS_DIR),
                initialfile=default.name,
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("全部", "*.*")],
            )
            if not path:
                self.set_banner("已取消儲存（資料仍在列表中）", "idle")
                return
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.last_saved = path
            self.set_banner(f"已儲存 {len(data)} 筆 JSON", "ok")
            messagebox.showinfo("儲存成功", f"已儲存 {len(data)} 筆\n{path}")
        except Exception as e:
            self.set_banner("儲存失敗", "err")
            messagebox.showerror("儲存失敗", str(e))

    def on_copy(self) -> None:
        try:
            text = json.dumps(self._payload(), ensure_ascii=False, indent=2)
            self.clipboard_clear()
            self.clipboard_append(text)
            self.set_banner(f"已複製 {len(self.items)} 筆 JSON 到剪貼簿", "ok")
            messagebox.showinfo("複製成功", f"已複製 {len(self.items)} 筆到剪貼簿")
        except Exception as e:
            self.set_banner("複製失敗", "err")
            messagebox.showerror("複製失敗", str(e))

    def on_open_tasks(self) -> None:
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(TASKS_DIR))
        self.set_banner("已開啟 tasks 資料夾", "idle")


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()

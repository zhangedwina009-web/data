# -*- coding: utf-8 -*-
"""
執行簡易任務 JSON
格式：
[
  {
    "存檔名稱": "...",
    "素材連結": "https://...",
    "執行": [ { "動作": "爬蟲", "定位": "class", "值": "...", "只取內文": true } ]
  }
]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
AHK_NAV = ROOT / "控制已開瀏覽器.ahk"


@dataclass
class RunControl:
    """暫停／停止控制（執行緒安全）。"""

    _stop: threading.Event = field(default_factory=threading.Event)
    _pause: threading.Event = field(default_factory=threading.Event)  # set = 暫停中

    def request_stop(self) -> None:
        self._pause.clear()  # 若卡在暫停，先解除才能跳出
        self._stop.set()

    def toggle_pause(self) -> bool:
        """回傳目前是否為暫停中。"""
        if self._stop.is_set():
            return False
        if self._pause.is_set():
            self._pause.clear()
            return False
        self._pause.set()
        return True

    def is_stop(self) -> bool:
        return self._stop.is_set()

    def is_paused(self) -> bool:
        return self._pause.is_set()

    def checkpoint(self, say=None) -> None:
        """每筆任務前後呼叫：處理暫停等待，若停止則丟出 InterruptedError。"""
        if self._pause.is_set() and not self._stop.is_set():
            # 只提示一次，避免洗版
            if say and not getattr(self, "_pause_said", False):
                say("已暫停…（按「繼續」恢復）")
                self._pause_said = True
            while self._pause.is_set() and not self._stop.is_set():
                time.sleep(0.15)
            self._pause_said = False
        if self._stop.is_set():
            raise InterruptedError("使用者停止")

    def sleep(self, seconds: float, say=None) -> None:
        """可被暫停／停止打斷的等待。"""
        end = time.time() + max(0.0, seconds)
        while time.time() < end:
            self.checkpoint(say)
            time.sleep(min(0.2, max(0.0, end - time.time())))


def safe_stem(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip())
    return name.strip(" .") or f"結果_{datetime.now():%Y%m%d_%H%M%S}"


def clean_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    out, blank = [], 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank <= 1:
                out.append("")
        else:
            blank = 0
            out.append(ln)
    return "\n".join(out).strip() + "\n"


def to_selector(by: str, value: str) -> str:
    by = (by or "class").strip().lower()
    value = (value or "").strip().strip("\"'")
    if not value:
        return ""
    if by == "id":
        return value if value.startswith("#") else f"#{value}"
    if by == "css":
        return value
    if by == "xpath":
        return value  # 呼叫端特殊處理
    # class：允許 "a b" → .a.b
    if value.startswith("."):
        return value
    parts = value.split()
    return "".join(f".{p}" for p in parts if p)


def load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("JSON 必須是陣列 [{存檔名稱, 素材連結, 執行}, …]")
    return data


BROWSER_CHOICES = [
    ("Google Chrome", "chrome"),
    ("Microsoft Edge", "msedge"),
    ("Playwright Chromium（內建）", "chromium"),
    ("Firefox", "firefox"),
]


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


def browser_exe_name(channel: str = "chrome") -> str:
    return "msedge.exe" if channel == "msedge" else "chrome.exe"


def run_ahk(cmd: str, *args: str) -> subprocess.CompletedProcess:
    """呼叫 AHK 操控已開視窗。絕不會關閉 Chrome。"""
    ahk = find_ahk_exe()
    if not ahk or not AHK_NAV.is_file():
        raise RuntimeError("找不到 AutoHotkey v2 或 控制已開瀏覽器.ahk")
    return subprocess.run(
        [ahk, str(AHK_NAV), cmd, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )


def ahk_goto(url: str, channel: str = "chrome") -> None:
    r = run_ahk("goto", url, browser_exe_name(channel))
    if r.returncode != 0:
        err = (r.stdout or "") + (r.stderr or "")
        raise RuntimeError(
            "無法操控已開著的瀏覽器。請先手動打開 Chrome/Edge。\n" + err.strip()
        )


def ahk_scrape(
    by: str,
    value: str,
    channel: str,
    out_file: Path,
    include_children: bool = True,
) -> str:
    """
    class 模式：在 body 用 getElementsByClassName('sc-jqnqvi-1 dyUpZz')
    include_children=True → 含底下全部可見文字
    include_children=False → 只取內文（去掉按鈕／選單等）
    """
    by = (by or "class").strip().lower()
    value = (value or "").strip()
    # 使用者常貼 class="..." 或前面多了點，清掉
    value = re.sub(r'^class\s*=\s*["\']?', "", value, flags=re.I)
    value = value.strip("\"'")
    if by == "class":
        value = value.lstrip(".")
        # 若被誤轉成 .a.b，還原成空白分隔
        if " " not in value and value.count(".") >= 1:
            value = value.replace(".", " ").strip()

    mode = "all" if include_children else "body"
    param = out_file.parent / f"_sel_{out_file.stem}.txt"
    param.write_text(f"{by}\n{value}\n{mode}\n", encoding="utf-8")
    try:
        r = run_ahk("scrape", str(param), browser_exe_name(channel), str(out_file))
        if r.returncode != 0 or not out_file.is_file():
            err = (r.stdout or "") + (r.stderr or "")
            raise RuntimeError(
                f"爬蟲失敗。\n定位：{by}\n值：{value}\n"
                "流程：開 Console → 依 class 複製區塊文字。\n"
                "請先確認已點開「逐字稿」、課程頁已載入，執行時不要搶鍵盤。\n"
                + err.strip()
            )
        text = out_file.read_text(encoding="utf-8").lstrip("\ufeff").strip()
        if not text or text.startswith("ERR:"):
            raise RuntimeError(
                f"頁面找不到內容。\n"
                f"搜尋 class：{value}\n"
                f"回傳：{text or '(空)'}\n"
                "提示：點「逐字稿」後可把「等待毫秒」加大（例如 3000）。"
            )
        # 若誤存到 JS 原始碼，視為失敗
        if "getElementsByClassName" in text and "copy(" in text:
            raise RuntimeError("抓到的是指令而非內文，請再試一次（執行時勿搶鍵盤）")
        return text
    finally:
        try:
            param.unlink(missing_ok=True)
        except Exception:
            pass


def ahk_click(
    by: str,
    value: str,
    channel: str,
    text_match: str = "",
    param_dir: Path | None = None,
    x: int | None = None,
    y: int | None = None,
) -> None:
    """點擊頁面元素。建議用座標模式（取得滑鼠座標.ahk → F8）。"""
    by = (by or "文字").strip()
    value = (value or "").strip()
    text_match = (text_match or "").strip()

    # 座標：支援 X/Y 參數，或 值 = "120,340"
    if by in ("座標", "coord", "xy") or (x is not None and y is not None):
        by = "座標"
        if x is not None and y is not None:
            value, text_match = str(int(x)), str(int(y))
        elif "," in value:
            parts = [p.strip() for p in value.split(",", 1)]
            value, text_match = parts[0], (parts[1] if len(parts) > 1 else "0")
        elif str(value).lstrip("-").isdigit() and str(text_match).lstrip("-").isdigit():
            pass
        else:
            raise ValueError("座標模式需要有效 X、Y（取得滑鼠座標.ahk → 移到按鈕 → F8）")
        try:
            ix, iy = int(float(value)), int(float(text_match))
        except ValueError as e:
            raise ValueError("座標不是數字") from e
        if ix < 0 or iy < 0:
            raise ValueError(
                f"座標無效 X={ix} Y={iy}（不能是負數）。\n"
                "請重新用「取得滑鼠座標.ahk」：滑鼠移到 Chrome 裡的按鈕上再按 F8，\n"
                "不要對著座標工具視窗按。"
            )
        value, text_match = str(ix), str(iy)

    if by == "class":
        value = value.lstrip(".")
        if " " not in value and value.count(".") >= 1:
            value = value.replace(".", " ").strip()

    folder = param_dir or OUTPUT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    param = folder / "_tmp_click.txt"
    param.write_text(f"{by}\n{value}\n{text_match}\n", encoding="utf-8")
    try:
        r = run_ahk("click", str(param), browser_exe_name(channel))
        if r.returncode != 0:
            err = (r.stdout or "") + (r.stderr or "")
            raise RuntimeError(
                f"點擊失敗。\n定位：{by}\n值：{value}\n文字/Y：{text_match or '(無)'}\n"
                "建議改用「座標」：雙擊 取得滑鼠座標.ahk → 滑鼠移到按鈕 → F8 → 填進產生器。\n"
                + err.strip()
            )
    finally:
        try:
            param.unlink(missing_ok=True)
        except Exception:
            pass


def ahk_screenshot(channel: str, out_file: Path) -> None:
    r = run_ahk("screenshot", browser_exe_name(channel), str(out_file))
    if r.returncode != 0 and not out_file.is_file():
        # bmp 後備
        bmp = out_file.with_suffix(".bmp")
        if bmp.is_file():
            bmp.replace(out_file)
            return
        err = (r.stdout or "") + (r.stderr or "")
        raise RuntimeError("截圖失敗\n" + err.strip())


def run_tasks_existing_window(
    tasks: list[dict],
    out_dir: Path,
    *,
    wait_ms: int = 4000,
    browser_channel: str = "chrome",
    log=None,
    control: RunControl | None = None,
) -> list[dict]:
    """只用已開著的視窗（AHK），絕不 taskkill / 重開瀏覽器。"""

    def say(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg)

    ctrl = control or RunControl()
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    say("模式：已開著的視窗（AHK 操控，不會關閉 Chrome）")
    say("可用「暫停／繼續」「停止」控制執行。")

    # 先確認視窗在
    r = run_ahk("activate", browser_exe_name(browser_channel))
    if r.returncode != 0:
        raise RuntimeError("找不到已開啟的瀏覽器視窗，請先手動打開 Chrome 並登入。")

    for i, task in enumerate(tasks, start=1):
        try:
            ctrl.checkpoint(say)
        except InterruptedError:
            say(f"已停止。完成到第 {i - 1}/{len(tasks)} 筆。")
            break

        name = str(task.get("存檔名稱") or f"未命名_{i}")
        url = str(task.get("素材連結") or "").strip()
        actions = task.get("執行") or []
        stem = safe_stem(name)
        saved: list[str] = []

        say(f"[{i}/{len(tasks)}] {name}")
        if not url:
            results.append({"ok": False, "name": name, "message": "缺少素材連結", "files": []})
            continue
        if not isinstance(actions, list) or not actions:
            results.append({"ok": False, "name": name, "message": "缺少執行內容", "files": []})
            continue

        try:
            ctrl.checkpoint(say)
            ahk_goto(url, browser_channel)
            ctrl.sleep(max(0.5, wait_ms / 1000), say)

            last_text = ""
            for act in actions:
                ctrl.checkpoint(say)
                kind = str(act.get("動作") or "").strip()

                if kind == "點擊":
                    by = str(act.get("定位") or "文字")
                    value = str(act.get("值") or "")
                    text_match = str(act.get("文字") or "")
                    cx = act.get("X", act.get("x"))
                    cy = act.get("Y", act.get("y"))
                    if by == "文字" and not value and text_match:
                        value = text_match
                    if by in ("座標", "coord", "xy") or cx is not None:
                        by = "座標"
                        if cx is not None and cy is not None:
                            value, text_match = str(cx), str(cy)
                        elif "," in value:
                            pass
                        else:
                            raise ValueError(
                                "座標點擊請填 X、Y。請用「取得滑鼠座標.ahk」移到按鈕上按 F8。"
                            )
                    if not value and not text_match and cx is None:
                        raise ValueError("點擊缺少定位值／文字／座標")
                    ahk_click(
                        by,
                        value,
                        browser_channel,
                        text_match,
                        out_dir,
                        x=int(cx) if cx is not None else None,
                        y=int(cy) if cy is not None else None,
                    )
                    wait_after = act.get("等待毫秒", act.get("點擊後等待"))
                    if wait_after is None:
                        wait_after = 2500
                    ctrl.sleep(max(0, float(wait_after)) / 1000, say)
                    if by == "座標":
                        say(f"  已點擊座標：{value},{text_match}")
                    else:
                        say(f"  已點擊：{text_match or value}")

                elif kind == "等待":
                    ms = act.get("毫秒", act.get("等待毫秒", 1000))
                    ctrl.sleep(max(0, float(ms)) / 1000, say)
                    say(f"  等待 {ms} ms")

                elif kind == "爬蟲":
                    by = str(act.get("定位") or "class")
                    value = str(act.get("值") or "")
                    if not value.strip():
                        raise ValueError("爬蟲缺少定位值")
                    # 含底下全部=true（預設）→ 全文字；false 或 只取內文=true → 只取內文
                    if "只取內文" in act:
                        include_children = not bool(act.get("只取內文"))
                    else:
                        include_children = bool(act.get("含底下全部", True))
                    tmp = out_dir / f"_tmp_scrape_{i}.txt"
                    raw = ahk_scrape(
                        by, value, browser_channel, tmp, include_children=include_children
                    )
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
                    last_text = clean_text(raw)
                    if not last_text.strip():
                        raise RuntimeError(f"找不到內容：{value}")
                    path = out_dir / f"{stem}.txt"
                    path.write_text(
                        f"來源：{url}\n"
                        f"定位：{by}\n"
                        f"值：{value}\n"
                        f"時間：{datetime.now():%Y-%m-%d %H:%M:%S}\n"
                        f"{'=' * 40}\n\n{last_text}",
                        encoding="utf-8",
                    )
                    saved.append(str(path))
                    say(f"  爬蟲完成 → {path.name}")

                elif kind == "截圖":
                    png = out_dir / f"{stem}.png"
                    ahk_screenshot(browser_channel, png)
                    # 若存成 bmp
                    if not png.is_file():
                        bmp = png.with_suffix(".bmp")
                        if bmp.is_file():
                            saved.append(str(bmp))
                            say(f"  截圖完成 → {bmp.name}")
                        else:
                            raise RuntimeError("截圖檔未產生")
                    else:
                        saved.append(str(png))
                        say(f"  截圖完成 → {png.name}")

                elif kind == "AI整理":
                    note = str(act.get("說明") or "")
                    src = last_text
                    if not src:
                        txt = out_dir / f"{stem}.txt"
                        if txt.exists():
                            src = txt.read_text(encoding="utf-8")
                    path = out_dir / f"{stem}_AI待整理.txt"
                    path.write_text(
                        f"【AI 說明】\n{note}\n\n【原始內容】\n{src}",
                        encoding="utf-8",
                    )
                    saved.append(str(path))
                    say(f"  AI 待整理 → {path.name}")

                elif kind == "開啟程式":
                    app = str(act.get("路徑") or "").strip()
                    if not app:
                        raise ValueError("開啟程式缺少路徑")
                    args = str(act.get("參數") or "").strip()
                    cmd = [app] + (args.split() if args else [])
                    subprocess.Popen(cmd, shell=False)
                    say(f"  已開啟程式：{app}")

                else:
                    say(f"  略過：{kind}")

            results.append({"ok": True, "name": name, "message": "成功", "files": saved})
        except InterruptedError:
            say(f"已停止於：{name}")
            results.append({"ok": False, "name": name, "message": "已停止", "files": saved})
            break
        except Exception as e:
            say(f"  失敗：{e}")
            results.append({"ok": False, "name": name, "message": str(e), "files": saved})
            if ctrl.is_stop():
                break

    return results


def run_tasks(
    tasks: list[dict],
    out_dir: Path,
    *,
    headless: bool = True,
    wait_ms: int = 3000,
    browser_channel: str = "chrome",
    use_existing: bool = True,
    debug_port: int = 9222,
    log=None,
    control: RunControl | None = None,
) -> list[dict]:
    # 預設：只操控已開視窗，絕不關閉瀏覽器
    if use_existing:
        return run_tasks_existing_window(
            tasks,
            out_dir,
            wait_ms=wait_ms,
            browser_channel=browser_channel,
            log=log,
            control=control,
        )

    # 以下僅在取消勾選「已開著的視窗」時才會走到（新開空白）
    from playwright.sync_api import sync_playwright

    def say(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg)

    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    say("模式：新開空白瀏覽器（非預設）")

    with sync_playwright() as p:
        channel = (browser_channel or "chrome").strip().lower()
        try:
            if channel == "msedge":
                browser = p.chromium.launch(channel="msedge", headless=headless)
            else:
                browser = p.chromium.launch(channel="chrome", headless=headless)
        except Exception:
            browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        for i, task in enumerate(tasks, start=1):
            name = str(task.get("存檔名稱") or f"未命名_{i}")
            url = str(task.get("素材連結") or "").strip()
            actions = task.get("執行") or []
            stem = safe_stem(name)
            saved: list[str] = []
            say(f"[{i}/{len(tasks)}] {name}")
            try:
                if not url:
                    raise ValueError("缺少素材連結")
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(wait_ms)
                last_text = ""
                for act in actions:
                    kind = str(act.get("動作") or "").strip()
                    if kind == "爬蟲":
                        selector = to_selector(str(act.get("定位") or "class"), str(act.get("值") or ""))
                        texts = page.eval_on_selector_all(
                            selector,
                            "els => els.map(el => (el.innerText || '').trim())",
                        )
                        items = [clean_text(t).strip() for t in texts if (t or "").strip()]
                        if not items:
                            raise RuntimeError(f"找不到內容：{selector}")
                        last_text = clean_text("\n\n-----\n\n".join(items))
                        path = out_dir / f"{stem}.txt"
                        path.write_text(
                            f"來源：{url}\n選擇器：{selector}\n{'=' * 40}\n\n{last_text}",
                            encoding="utf-8",
                        )
                        saved.append(str(path))
                        say(f"  爬蟲完成 → {path.name}")
                    elif kind == "截圖":
                        png = out_dir / f"{stem}.png"
                        page.screenshot(path=str(png), full_page=True)
                        saved.append(str(png))
                        say(f"  截圖完成 → {png.name}")
                    else:
                        say(f"  略過：{kind}")
                results.append({"ok": True, "name": name, "message": "成功", "files": saved})
            except Exception as e:
                say(f"  失敗：{e}")
                results.append({"ok": False, "name": name, "message": str(e), "files": saved})

        browser.close()
    return results


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("執行任務 JSON")
        self.geometry("780x640")
        self.path_var = tk.StringVar()
        self.existing_var = tk.BooleanVar(value=True)
        self.browser_var = tk.StringVar(value="Google Chrome")
        self.wait_var = tk.StringVar(value="4000")
        self.control: RunControl | None = None
        self._running = False
        self._build()

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(
            frm,
            text="用法：選 JSON → 開始執行｜可用暫停／停止",
            wraplength=720,
        ).pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(frm)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="任務 JSON").pack(side="left")
        ttk.Entry(row, textvariable=self.path_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="選檔…", command=self.pick).pack(side="left")

        brow = ttk.Frame(frm)
        brow.pack(fill="x", pady=6)
        ttk.Label(brow, text="瀏覽器").pack(side="left")
        ttk.Combobox(
            brow,
            textvariable=self.browser_var,
            values=["Google Chrome", "Microsoft Edge"],
            state="readonly",
            width=28,
        ).pack(side="left", padx=8)
        ttk.Label(brow, text="等待ms").pack(side="left", padx=(12, 0))
        ttk.Entry(brow, textvariable=self.wait_var, width=8).pack(side="left", padx=6)

        ttk.Checkbutton(
            frm,
            text="使用已開著的視窗（預設勾選）",
            variable=self.existing_var,
        ).pack(anchor="w", pady=4)

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=8)
        self.go_btn = ttk.Button(btns, text="開始執行", command=self.on_go)
        self.go_btn.pack(side="left")
        self.pause_btn = ttk.Button(btns, text="暫停", command=self.on_pause, state="disabled")
        self.pause_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(btns, text="停止", command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left")
        ttk.Button(btns, text="測試點擊「逐字稿」", command=self.test_click).pack(side="left", padx=8)
        ttk.Button(btns, text="開啟輸出資料夾", command=lambda: os.startfile(OUTPUT_DIR)).pack(
            side="left", padx=8
        )

        self.log = tk.Text(frm, height=22, wrap="word")
        self.log.pack(fill="both", expand=True, pady=(8, 0))
        self._log(
            "預設＝操控已開著的 Chrome（不會關閉重開）。\n"
            "爬蟲：開 Console → 依 class 複製區塊文字。\n"
            "開始後可用「暫停／繼續」「停止」。"
        )

    def _log(self, msg: str) -> None:
        self.log.insert("end", msg + ("\n" if not msg.endswith("\n") else ""))
        self.log.see("end")

    def pick(self) -> None:
        p = filedialog.askopenfilename(
            title="選擇任務 JSON",
            filetypes=[("JSON", "*.json"), ("全部", "*.*")],
            initialdir=str(ROOT),
        )
        if p:
            self.path_var.set(p)

    def _set_running_ui(self, running: bool) -> None:
        self._running = running
        self.go_btn.configure(state="disabled" if running else "normal")
        self.pause_btn.configure(state="normal" if running else "disabled", text="暫停")
        self.stop_btn.configure(state="normal" if running else "disabled")

    def test_click(self) -> None:
        """只測前置點擊，方便確認「逐字稿」找不找得到。"""
        if self._running:
            messagebox.showinfo("提醒", "請先停止目前任務再測")
            return
        name_to_ch = {n: c for n, c in BROWSER_CHOICES}
        channel = name_to_ch.get(self.browser_var.get(), "chrome")
        self._log("測試點擊：逐字稿 …")
        try:
            ahk_click("文字", "逐字稿", channel, "逐字稿", OUTPUT_DIR)
            self._log("測試點擊成功（若頁面有反應即可）")
            messagebox.showinfo("測試", "點擊指令已送出。\n請看 Chrome 是否打開了逐字稿。")
        except Exception as e:
            self._log(f"測試點擊失敗：{e}")
            messagebox.showerror("測試失敗", str(e))

    def on_pause(self) -> None:
        if not self.control or not self._running:
            return
        paused = self.control.toggle_pause()
        if paused:
            self.pause_btn.configure(text="繼續")
            self._log("▶ 已暫停（按「繼續」恢復）")
        else:
            self.pause_btn.configure(text="暫停")
            self._log("▶ 繼續執行")

    def on_stop(self) -> None:
        if not self.control or not self._running:
            return
        self.control.request_stop()
        self.pause_btn.configure(state="disabled")
        self._log("■ 正在停止（等目前步驟結束）…")

    def on_go(self) -> None:
        if self._running:
            return
        path = Path(self.path_var.get().strip())
        if not path.is_file():
            messagebox.showwarning("提醒", "請先選擇 JSON 檔")
            return
        try:
            tasks = load_tasks(path)
        except Exception as e:
            messagebox.showerror("讀檔失敗", str(e))
            return

        self.control = RunControl()
        self._set_running_ui(True)
        self._log(f"\n===== 開始 {datetime.now():%H:%M:%S}　共 {len(tasks)} 筆 =====")

        use_existing = bool(self.existing_var.get())
        name_to_ch = {n: c for n, c in BROWSER_CHOICES}
        channel = name_to_ch.get(self.browser_var.get(), "chrome")
        try:
            wait_ms = max(0, int(self.wait_var.get()))
        except ValueError:
            wait_ms = 4000

        ctrl = self.control

        def work() -> None:
            try:
                results = run_tasks(
                    tasks,
                    OUTPUT_DIR,
                    headless=False,
                    wait_ms=wait_ms,
                    browser_channel=channel,
                    use_existing=use_existing,
                    debug_port=9222,
                    log=lambda m: self.after(0, lambda: self._log(m)),
                    control=ctrl,
                )
                self.after(0, lambda: self._done(results, stopped=ctrl.is_stop()))
            except Exception as e:
                self.after(0, lambda: self._fail(e))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, results: list[dict], stopped: bool = False) -> None:
        self._set_running_ui(False)
        self.control = None
        ok = sum(1 for r in results if r["ok"])
        title = "已停止" if stopped else "完成"
        self._log(
            f"===== {title}：成功 {ok} / {len(results)} =====\n輸出：{OUTPUT_DIR}"
        )
        messagebox.showinfo(title, f"成功 {ok} / {len(results)}\n輸出資料夾：\n{OUTPUT_DIR}")

    def _fail(self, err: Exception) -> None:
        self._set_running_ui(False)
        self.control = None
        self._log(f"執行失敗：{err}")
        messagebox.showerror("失敗", str(err))


def main() -> None:
    if len(sys.argv) >= 2:
        path = Path(sys.argv[1])
        tasks = load_tasks(path)
        headless = "--headless" in sys.argv
        channel = "chrome"
        for flag, ch in (
            ("--edge", "msedge"),
            ("--firefox", "firefox"),
            ("--chromium", "chromium"),
            ("--chrome", "chrome"),
        ):
            if flag in sys.argv:
                channel = ch
                break
        results = run_tasks(
            tasks, OUTPUT_DIR, headless=headless, wait_ms=4000, browser_channel=channel
        )
        ok = sum(1 for r in results if r["ok"])
        print(f"完成：{ok}/{len(results)} → {OUTPUT_DIR}")
        sys.exit(0 if ok == len(results) else 2)

    App().mainloop()


if __name__ == "__main__":
    main()

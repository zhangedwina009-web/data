# -*- coding: utf-8 -*-
"""
多網址批次工具：每筆可選「爬蟲」或「截圖」（或兩者）
雙擊 啟動抓取工具.bat 開啟畫面。
"""

from __future__ import annotations

import csv
import os
import re
import sys
import threading
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
ACTIONS = ("爬蟲", "截圖", "兩者")

_HTML_TAGS = {
    "a", "article", "aside", "body", "button", "div", "footer", "form", "h1",
    "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "nav", "p", "section",
    "span", "table", "tbody", "td", "th", "tr", "ul", "ol", "pre", "code",
}


@dataclass
class Job:
    enabled: bool = True
    action: str = "爬蟲"  # 爬蟲 / 截圖 / 兩者
    url: str = ""
    selector: str = ""
    filename: str = ""
    full_page: bool = True


@dataclass
class JobResult:
    job: Job
    ok: bool
    message: str
    paths: list[Path] = field(default_factory=list)


def normalize_selector(raw: str) -> str:
    s = (raw or "").strip().strip("\"'")
    if not s:
        return ""
    m = re.search(r'class\s*=\s*["\']([^"\']+)["\']', s, re.I)
    if m:
        s = m.group(1).strip()
    if any(ch in s for ch in ".#[]:>+~()") or s.startswith("*"):
        return s
    parts = s.split()
    if len(parts) > 1 and all(re.fullmatch(r"[A-Za-z_][\w-]*", p) for p in parts):
        return "".join(f".{p}" for p in parts)
    if s.lower() in _HTML_TAGS:
        return s.lower()
    if re.fullmatch(r"[A-Za-z_][\w-]*", s):
        return f".{s}"
    return s


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            if blank <= 1:
                out.append("")
        else:
            blank = 0
            out.append(line)
    return "\n".join(out).strip() + "\n"


def safe_stem(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(" .")
    return name or f"結果_{datetime.now():%Y%m%d_%H%M%S}"


def ensure_ext(name: str, ext: str) -> str:
    stem = Path(name).stem if name else ""
    stem = safe_stem(stem or name)
    return f"{stem}{ext}"


def auto_name_from_url(url: str, index: int) -> str:
    try:
        host = urlparse(url).netloc.replace("www.", "") or "page"
        path = urlparse(url).path.strip("/").replace("/", "_")
        base = f"{index:02d}_{host}"
        if path:
            base += "_" + path[:40]
        return safe_stem(base)
    except Exception:
        return f"{index:02d}_page"


def fetch_static_texts(url: str, selector: str) -> list[str]:
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "lxml")
    results = []
    for node in soup.select(selector):
        t = clean_text(node.get_text("\n", strip=True))
        if t.strip():
            results.append(t.strip())
    return results


def run_jobs(jobs: list[Job], out_dir: Path, wait_ms: int = 2500) -> list[JobResult]:
    """用同一個瀏覽器批次處理，較快。"""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[JobResult] = []
    active = [j for j in jobs if j.enabled and j.url.strip()]

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        for i, job in enumerate(active, start=1):
            url = job.url.strip()
            try:
                if not url.startswith(("http://", "https://")):
                    raise ValueError("網址需以 http:// 或 https:// 開頭")

                action = job.action
                need_scrape = action in ("爬蟲", "兩者")
                need_shot = action in ("截圖", "兩者")
                selector = normalize_selector(job.selector) if job.selector.strip() else ""

                if need_scrape and not selector:
                    raise ValueError("爬蟲模式請填 class／選擇器")

                base = safe_stem(job.filename) if job.filename.strip() else auto_name_from_url(url, i)
                saved: list[Path] = []

                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(wait_ms)

                if need_scrape:
                    try:
                        page.wait_for_selector(selector, timeout=10000)
                    except Exception:
                        pass
                    texts = page.eval_on_selector_all(
                        selector,
                        "els => els.map(el => (el.innerText || el.textContent || '').trim())",
                    )
                    items = [clean_text(t or "").strip() for t in texts if (t or "").strip()]
                    if not items:
                        raise RuntimeError(f"找不到選擇器內容：{selector}")
                    body = clean_text("\n\n-----\n\n".join(items))
                    txt_path = out_dir / ensure_ext(base, ".txt")
                    header = (
                        f"來源：{url}\n"
                        f"選擇器：{selector}\n"
                        f"抓取時間：{datetime.now():%Y-%m-%d %H:%M:%S}\n"
                        f"筆數：{len(items)}\n"
                        f"{'=' * 40}\n\n"
                    )
                    txt_path.write_text(header + body, encoding="utf-8")
                    saved.append(txt_path)

                if need_shot:
                    png_path = out_dir / ensure_ext(base, ".png")
                    if selector:
                        try:
                            page.wait_for_selector(selector, timeout=8000)
                            loc = page.locator(selector).first
                            loc.screenshot(path=str(png_path))
                        except Exception:
                            # 區塊截圖失敗就退回整頁
                            page.screenshot(path=str(png_path), full_page=bool(job.full_page))
                    else:
                        page.screenshot(path=str(png_path), full_page=bool(job.full_page))
                    saved.append(png_path)

                results.append(JobResult(job, True, "成功", saved))
            except Exception as e:
                results.append(JobResult(job, False, str(e), []))

        browser.close()
    return results


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("多網址批次工具｜爬蟲 / 截圖")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.jobs: list[Job] = [Job(), Job(), Job()]
        self._build()
        self.refresh_table()

    def _build(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(
            top,
            text=(
                "每一列＝一個網址。動作可選「爬蟲／截圖／兩者」。\n"
                "爬蟲：填 class（F12 複製一次即可）。截圖：可不填 class＝整頁；有填＝只截該區塊。"
            ),
            justify="left",
        ).pack(anchor="w")

        opt = ttk.Frame(self, padding=(10, 0))
        opt.pack(fill="x")
        ttk.Label(opt, text="輸出資料夾").pack(side="left")
        self.dir_var = tk.StringVar(value=str(OUTPUT_DIR))
        ttk.Entry(opt, textvariable=self.dir_var, width=70).pack(side="left", padx=8)
        ttk.Button(opt, text="選擇…", command=self.pick_dir).pack(side="left")
        self.full_page_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="截圖用整頁（拉很長的頁也截完）", variable=self.full_page_var).pack(
            side="left", padx=12
        )

        # 批次貼上網址
        bulk = ttk.LabelFrame(self, text="一次貼很多網址（每行一個）", padding=8)
        bulk.pack(fill="x", padx=10, pady=6)
        self.bulk_text = tk.Text(bulk, height=4, wrap="none")
        self.bulk_text.pack(fill="x")
        bulk_row = ttk.Frame(bulk)
        bulk_row.pack(fill="x", pady=(6, 0))
        ttk.Label(bulk_row, text="預設動作").pack(side="left")
        self.bulk_action = tk.StringVar(value="爬蟲")
        ttk.Combobox(
            bulk_row, textvariable=self.bulk_action, values=ACTIONS, width=8, state="readonly"
        ).pack(side="left", padx=6)
        ttk.Label(bulk_row, text="預設 class").pack(side="left")
        self.bulk_sel = tk.StringVar()
        ttk.Entry(bulk_row, textvariable=self.bulk_sel, width=28).pack(side="left", padx=6)
        ttk.Button(bulk_row, text="加入清單", command=self.add_bulk).pack(side="left", padx=6)
        ttk.Button(bulk_row, text="清空清單", command=self.clear_jobs).pack(side="left")

        # 表格
        table_frm = ttk.Frame(self, padding=10)
        table_frm.pack(fill="both", expand=True)
        cols = ("on", "action", "url", "selector", "filename")
        self.tree = ttk.Treeview(table_frm, columns=cols, show="headings", height=12)
        self.tree.heading("on", text="啟用")
        self.tree.heading("action", text="動作")
        self.tree.heading("url", text="網址")
        self.tree.heading("selector", text="class / 選擇器")
        self.tree.heading("filename", text="檔名（不含副檔名也可）")
        self.tree.column("on", width=50, anchor="center")
        self.tree.column("action", width=70, anchor="center")
        self.tree.column("url", width=360)
        self.tree.column("selector", width=160)
        self.tree.column("filename", width=180)
        scroll = ttk.Scrollbar(table_frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # 編輯區
        edit = ttk.LabelFrame(self, text="編輯選取的那一列", padding=8)
        edit.pack(fill="x", padx=10)
        grid = ttk.Frame(edit)
        grid.pack(fill="x")

        self.e_on = tk.BooleanVar(value=True)
        self.e_action = tk.StringVar(value="爬蟲")
        self.e_url = tk.StringVar()
        self.e_sel = tk.StringVar()
        self.e_name = tk.StringVar()

        ttk.Checkbutton(grid, text="啟用", variable=self.e_on).grid(row=0, column=0, sticky="w")
        ttk.Label(grid, text="動作").grid(row=0, column=1, sticky="e", padx=(8, 4))
        ttk.Combobox(grid, textvariable=self.e_action, values=ACTIONS, width=8, state="readonly").grid(
            row=0, column=2, sticky="w"
        )
        ttk.Label(grid, text="網址").grid(row=1, column=0, sticky="e")
        ttk.Entry(grid, textvariable=self.e_url, width=90).grid(row=1, column=1, columnspan=4, sticky="we", pady=3)
        ttk.Label(grid, text="class").grid(row=2, column=0, sticky="e")
        ttk.Entry(grid, textvariable=self.e_sel, width=40).grid(row=2, column=1, columnspan=2, sticky="we", pady=3)
        ttk.Label(grid, text="檔名").grid(row=2, column=3, sticky="e", padx=(8, 4))
        ttk.Entry(grid, textvariable=self.e_name, width=28).grid(row=2, column=4, sticky="we", pady=3)
        grid.columnconfigure(1, weight=1)

        erow = ttk.Frame(edit)
        erow.pack(fill="x", pady=(6, 0))
        ttk.Button(erow, text="套用到選取列", command=self.apply_edit).pack(side="left")
        ttk.Button(erow, text="新增空白列", command=self.add_blank).pack(side="left", padx=6)
        ttk.Button(erow, text="刪除選取列", command=self.delete_selected).pack(side="left")
        ttk.Button(erow, text="匯入 CSV", command=self.import_csv).pack(side="left", padx=6)
        ttk.Button(erow, text="匯出 CSV 範本", command=self.export_csv).pack(side="left")

        # 底部按鈕
        bottom = ttk.Frame(self, padding=10)
        bottom.pack(fill="x")
        self.go_btn = ttk.Button(bottom, text="開始執行全部啟用項目", command=self.on_go)
        self.go_btn.pack(side="left")
        ttk.Button(bottom, text="開啟輸出資料夾", command=self.open_out).pack(side="left", padx=8)
        ttk.Button(bottom, text="使用說明", command=self.show_help).pack(side="left")
        self.status = tk.StringVar(value="就緒：可一次處理很多網址")
        ttk.Label(bottom, textvariable=self.status).pack(side="left", padx=16)

        logf = ttk.LabelFrame(self, text="執行紀錄", padding=6)
        logf.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log = tk.Text(logf, height=8, wrap="word")
        self.log.pack(fill="both", expand=True)

    def refresh_table(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for idx, job in enumerate(self.jobs):
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    "✓" if job.enabled else "–",
                    job.action,
                    job.url,
                    job.selector,
                    job.filename,
                ),
            )

    def selected_index(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return int(sel[0])

    def on_select(self, _evt=None) -> None:
        i = self.selected_index()
        if i is None or i >= len(self.jobs):
            return
        j = self.jobs[i]
        self.e_on.set(j.enabled)
        self.e_action.set(j.action)
        self.e_url.set(j.url)
        self.e_sel.set(j.selector)
        self.e_name.set(j.filename)

    def apply_edit(self) -> None:
        i = self.selected_index()
        if i is None:
            messagebox.showinfo("提示", "請先點選表格中的一列")
            return
        self.jobs[i] = Job(
            enabled=bool(self.e_on.get()),
            action=self.e_action.get() if self.e_action.get() in ACTIONS else "爬蟲",
            url=self.e_url.get().strip(),
            selector=self.e_sel.get().strip(),
            filename=self.e_name.get().strip(),
            full_page=bool(self.full_page_var.get()),
        )
        self.refresh_table()
        self.tree.selection_set(str(i))
        self.status.set(f"已更新第 {i + 1} 列")

    def add_blank(self) -> None:
        self.jobs.append(Job(full_page=bool(self.full_page_var.get())))
        self.refresh_table()
        self.tree.selection_set(str(len(self.jobs) - 1))
        self.on_select()

    def delete_selected(self) -> None:
        i = self.selected_index()
        if i is None:
            return
        del self.jobs[i]
        if not self.jobs:
            self.jobs = [Job()]
        self.refresh_table()

    def clear_jobs(self) -> None:
        if messagebox.askyesno("確認", "確定清空全部清單？"):
            self.jobs = [Job()]
            self.refresh_table()

    def add_bulk(self) -> None:
        lines = [ln.strip() for ln in self.bulk_text.get("1.0", "end").splitlines()]
        urls = [ln for ln in lines if ln and not ln.startswith("#")]
        if not urls:
            messagebox.showwarning("提醒", "請先在上方貼上網址（每行一個）")
            return
        # 若目前只有空白列，先清掉
        if len(self.jobs) == 1 and not self.jobs[0].url.strip():
            self.jobs = []
        action = self.bulk_action.get() if self.bulk_action.get() in ACTIONS else "爬蟲"
        sel = self.bulk_sel.get().strip()
        start = len(self.jobs) + 1
        for n, url in enumerate(urls, start=start):
            self.jobs.append(
                Job(
                    enabled=True,
                    action=action,
                    url=url,
                    selector=sel,
                    filename=auto_name_from_url(url, n),
                    full_page=bool(self.full_page_var.get()),
                )
            )
        self.bulk_text.delete("1.0", "end")
        self.refresh_table()
        self.status.set(f"已加入 {len(urls)} 個網址")

    def pick_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.dir_var.get() or str(OUTPUT_DIR))
        if d:
            self.dir_var.set(d)

    def open_out(self) -> None:
        path = Path(self.dir_var.get() or OUTPUT_DIR)
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def show_help(self) -> None:
        messagebox.showinfo(
            "使用說明",
            "【多網址】\n"
            "1. 把很多網址貼到「一次貼很多網址」，每行一個\n"
            "2. 選預設動作：爬蟲 / 截圖 / 兩者\n"
            "3. 爬蟲要填預設 class；截圖可不填（整頁截圖）\n"
            "4. 按「加入清單」→「開始執行」\n\n"
            "【單筆微調】\n"
            "點表格某一列 → 下方修改 →「套用到選取列」\n\n"
            "【檔名】\n"
            "爬蟲存 .txt，截圖存 .png；選「兩者」會各存一份\n"
            "檔名可只寫名稱，副檔名會自動加\n\n"
            "【找 class】\n"
            "瀏覽器 F12 → Ctrl+Shift+C → 點區塊 → 複製 class 名稱",
        )

    def export_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="jobs_template.csv",
            initialdir=str(Path(__file__).resolve().parent),
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["enabled", "action", "url", "selector", "filename"])
            w.writerow(["yes", "爬蟲", "https://example.com", "h1", "範例標題"])
            w.writerow(["yes", "截圖", "https://example.com", "", "範例整頁"])
            w.writerow(["yes", "兩者", "https://example.com", "h1", "範例兩者"])
        messagebox.showinfo("完成", f"已寫入：\n{path}\n\n用 Excel 編輯後可「匯入 CSV」")

    def import_csv(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("全部", "*.*")])
        if not path:
            return
        loaded: list[Job] = []
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                action = (row.get("action") or "爬蟲").strip()
                if action not in ACTIONS:
                    action = "爬蟲"
                en = str(row.get("enabled", "yes")).strip().lower()
                loaded.append(
                    Job(
                        enabled=en in ("1", "yes", "y", "true", "是", "✓"),
                        action=action,
                        url=(row.get("url") or "").strip(),
                        selector=(row.get("selector") or "").strip(),
                        filename=(row.get("filename") or "").strip(),
                        full_page=bool(self.full_page_var.get()),
                    )
                )
        if not loaded:
            messagebox.showwarning("提醒", "CSV 沒有讀到資料")
            return
        self.jobs = loaded
        self.refresh_table()
        self.status.set(f"已匯入 {len(loaded)} 筆")

    def on_go(self) -> None:
        # 同步整頁選項到每筆
        for j in self.jobs:
            j.full_page = bool(self.full_page_var.get())

        active = [j for j in self.jobs if j.enabled and j.url.strip()]
        if not active:
            messagebox.showwarning("提醒", "沒有可執行的項目（需啟用且有網址）")
            return

        # 套用編輯區（若有選取）避免忘記按套用
        i = self.selected_index()
        if i is not None:
            self.apply_edit()

        out_dir = Path(self.dir_var.get().strip() or OUTPUT_DIR)
        self.go_btn.configure(state="disabled")
        self.status.set(f"執行中：共 {len(active)} 筆…")
        self.log.delete("1.0", "end")
        self.log.insert("end", f"開始 {datetime.now():%H:%M:%S}，共 {len(active)} 筆\n")

        def work() -> None:
            try:
                results = run_jobs(active, out_dir)
                self.after(0, lambda: self._done(results, out_dir))
            except Exception as e:
                self.after(0, lambda: self._fail(e))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, results: list[JobResult], out_dir: Path) -> None:
        self.go_btn.configure(state="normal")
        ok_n = sum(1 for r in results if r.ok)
        fail_n = len(results) - ok_n
        lines = []
        for idx, r in enumerate(results, start=1):
            mark = "OK" if r.ok else "失敗"
            paths = "、".join(str(p.name) for p in r.paths) if r.paths else "-"
            lines.append(f"[{mark}] #{idx} {r.job.action} {r.job.url}\n  → {r.message} | 檔案：{paths}")
        self.log.insert("end", "\n".join(lines) + "\n")
        self.status.set(f"完成：成功 {ok_n}，失敗 {fail_n} → {out_dir}")
        messagebox.showinfo(
            "批次完成",
            f"成功 {ok_n} 筆，失敗 {fail_n} 筆\n輸出資料夾：\n{out_dir}",
        )

    def _fail(self, err: Exception) -> None:
        self.go_btn.configure(state="normal")
        self.status.set("失敗")
        messagebox.showerror("執行失敗", str(err))


def main() -> None:
    # 簡易 CLI：
    #   python web_scraper.py scrape <url> <selector> <filename>
    #   python web_scraper.py shot <url> [selector] <filename>
    if len(sys.argv) >= 2 and sys.argv[1] in ("scrape", "shot", "both"):
        mode = sys.argv[1]
        url = sys.argv[2]
        if mode == "shot":
            if len(sys.argv) >= 5:
                sel, fname = sys.argv[3], sys.argv[4]
            else:
                sel, fname = "", sys.argv[3]
            action = "截圖"
        elif mode == "both":
            sel, fname = sys.argv[3], sys.argv[4]
            action = "兩者"
        else:
            sel, fname = sys.argv[3], sys.argv[4]
            action = "爬蟲"
        job = Job(True, action, url, sel, fname, True)
        results = run_jobs([job], OUTPUT_DIR)
        r = results[0]
        if not r.ok:
            print(r.message, file=sys.stderr)
            sys.exit(2)
        for p in r.paths:
            print(p)
        return

    # 舊版 CLI 相容
    if len(sys.argv) >= 4:
        url, sel, fname = sys.argv[1], sys.argv[2], sys.argv[3]
        job = Job(True, "爬蟲", url, sel, fname, True)
        results = run_jobs([job], OUTPUT_DIR)
        r = results[0]
        if not r.ok:
            print(r.message, file=sys.stderr)
            sys.exit(2)
        for p in r.paths:
            print(p)
        return

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

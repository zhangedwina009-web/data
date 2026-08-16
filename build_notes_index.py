# -*- coding: utf-8 -*-
"""掃描 notes/ 產生 notes/index.html（僅資料夾按鈕）。"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from note_paths import FOLDER_LABELS

ROOT = Path(__file__).resolve().parent
NOTES = ROOT / "notes"
SKIP_DIRS = {"archive", "__pycache__"}
# 僅作舊網址導向的空殼資料夾，不顯示在瀏覽首頁
REDIRECT_ONLY_DIRS = {"公司治理", "簡單開公司"}


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _folder_label(name: str) -> str:
    return FOLDER_LABELS.get(name, name)


def _folder_href(d: Path) -> str | None:
    """資料夾按鈕連結：優先 index.html，否則第一篇 html（絕對路徑利於 Vercel）。"""
    idx = d / "index.html"
    if idx.is_file():
        return f"/notes/{d.name}/index.html".replace("\\", "/")
    htmls = sorted(
        [f for f in d.glob("*.html") if f.name.lower() != "index.html"],
        key=lambda p: p.name.lower(),
    )
    if htmls:
        return f"/notes/{d.name}/{htmls[0].name}".replace("\\", "/")
    return None


def collect() -> list[dict]:
    folders: list[dict] = []
    if not NOTES.is_dir():
        return folders
    for d in sorted(NOTES.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir() or d.name in SKIP_DIRS or d.name.startswith("."):
            continue
        if d.name in REDIRECT_ONLY_DIRS:
            continue
        href = _folder_href(d)
        if not href:
            continue
        count = len([f for f in d.glob("*.html") if f.name.lower() != "index.html"])
        folders.append(
            {
                "name": d.name,
                "label": _folder_label(d.name),
                "href": href,
                "count": count,
            }
        )
    return folders


def render(folders: list[dict]) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not folders:
        body = '<p class="empty">尚無講義資料夾。請先到「新增筆記」產生。</p>'
    else:
        btns = [
            f'<a class="folder-btn" href="{_esc(f["href"])}">'
            f'<span class="folder-name">{_esc(f["label"])}</span>'
            f'<span class="folder-go">開啟 →</span>'
            f"</a>"
            for f in folders
        ]
        body = f'<div class="folder-grid">{"".join(btns)}</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>瀏覽筆記</title>
<style>
:root{{
  --bg:#10151c; --card:#1a2330; --line:#334155; --text:#eef3f9; --muted:#94a3b8; --accent:#3b9eff; --mint:#34d399;
  --font:"Segoe UI","Microsoft JhengHei","Noto Sans TC",sans-serif;
}}
*{{box-sizing:border-box;}}
body{{
  margin:0; font-family:var(--font); color:var(--text);
  background:radial-gradient(900px 400px at 0% 0%,#1e3a5f66,transparent 60%),var(--bg);
  min-height:100vh;
}}
.wrap{{max-width:720px;margin:0 auto;padding:28px 18px 48px;}}
.top{{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:22px;}}
h1{{margin:0 0 6px;font-size:clamp(1.35rem,3.5vw,1.7rem);}}
.sub{{margin:0;color:var(--muted);line-height:1.5;}}
.nav{{display:flex;gap:8px;flex-wrap:wrap;}}
.nav a{{
  display:inline-flex;align-items:center;text-decoration:none;color:#071018;font-weight:700;
  background:linear-gradient(180deg,#3b9eff,#2563eb);border-radius:10px;padding:.55rem .9rem;
}}
.nav a.ghost{{background:transparent;color:var(--text);border:1px solid var(--line);}}
.folder-grid{{
  display:grid;grid-template-columns:1fr;gap:12px;
}}
@media (min-width:560px){{
  .folder-grid{{grid-template-columns:1fr 1fr;}}
}}
.folder-btn{{
  display:flex;align-items:center;justify-content:space-between;gap:12px;
  text-decoration:none;color:inherit;
  background:linear-gradient(165deg,#152a44,var(--card) 60%);
  border:1px solid #3b82f688;border-radius:14px;
  padding:1.1rem 1.15rem;min-height:74px;
  transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease;
}}
.folder-btn:hover{{
  transform:translateY(-2px);border-color:#5ec8ff;box-shadow:0 10px 24px #00000044;color:inherit;
}}
.folder-name{{font-size:1.08rem;font-weight:750;line-height:1.35;overflow-wrap:anywhere;}}
.folder-go{{color:var(--accent);font-weight:700;font-size:.9rem;white-space:nowrap;}}
.empty{{color:var(--muted);padding:.4rem .2rem;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1>瀏覽筆記</h1>
      <p class="sub">選擇資料夾進入 · 更新於 {stamp}</p>
    </div>
    <div class="nav">
      <a class="ghost" href="../">← 回首頁</a>
      <a href="../apps/note_generator.html">新增筆記</a>
    </div>
  </div>
  {body}
</div>
</body>
</html>
"""


def main() -> int:
    NOTES.mkdir(parents=True, exist_ok=True)
    folders = collect()
    out = NOTES / "index.html"
    out.write_text(render(folders), encoding="utf-8")
    print(f"OK {out}  folders={len(folders)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""把 _structured/*.json 全部重渲到 notes/simpany/（ASCII 安全檔名）。"""

from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from note_generator_server import save_note_from_data
from note_html_render import extract_source_url, normalize_note
from note_paths import TAX_DIR, TAX_DIR_LABEL, tax_slug
from note_shell import build_course_sidebar, chapters_from_note
from build_notes_index import main as rebuild_notes_index


def main() -> int:
    src_dir = ROOT / "_structured"
    files = sorted(src_dir.glob("*.json"))
    if not files:
        print("no json")
        return 1

    # 清除舊中文路徑，避免 Vercel 繼續 404
    legacy = ROOT / "notes" / "簡單開公司"
    if legacy.is_dir():
        shutil.rmtree(legacy)
        print("removed legacy", legacy)

    TAX_DIR.mkdir(parents=True, exist_ok=True)

    loaded: list[tuple[str, str, dict]] = []
    for path in files:
        full_stem = path.stem
        slug = tax_slug(full_stem)
        data = json.loads(path.read_text(encoding="utf-8"))
        txt = ROOT / "output" / f"{full_stem}.txt"
        if txt.is_file() and not data.get("source_url"):
            data["source_url"] = extract_source_url(
                txt.read_text(encoding="utf-8", errors="ignore")
            )
        if not data.get("badge"):
            data["badge"] = f"單元 {slug}"
        note = normalize_note(data, fallback_title=full_stem)
        loaded.append((slug, full_stem, note))

    books = [
        {
            "file": f"{slug}.html",
            "title": note.get("title") or full_stem,
            "chapters": chapters_from_note(note),
        }
        for slug, full_stem, note in loaded
    ]

    ok = 0
    for slug, full_stem, note in loaded:
        active_file = f"{slug}.html"
        sidebar_html = build_course_sidebar(
            brand=TAX_DIR_LABEL,
            brand_sub="課程目錄",
            books=books,
            active_file=active_file,
            home_href="../index.html",
        )
        save_note_from_data(
            slug,
            note,
            out_dir=TAX_DIR,
            sidebar_html=sidebar_html,
            course_brand=TAX_DIR_LABEL,
            active_file=active_file,
            books=books,
        )
        print("OK", slug, "←", full_stem)
        ok += 1

    if loaded:
        first = f"{loaded[0][0]}.html"
        (TAX_DIR / "index.html").write_text(
            "<!DOCTYPE html><html lang='zh-Hant'><head><meta charset='UTF-8'/>"
            f"<meta http-equiv='refresh' content='0;url={html.escape(first)}'/>"
            f"<title>導向講義</title></head><body>"
            f"<p>正在進入講義… <a href='{html.escape(first)}'>若未自動跳轉請點此</a></p>"
            "</body></html>\n",
            encoding="utf-8",
        )
        print("OK index.html ->", first)

    rebuild_notes_index()
    print(f"done {ok}/{len(files)} -> {TAX_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""把 _structured/*.json 全部重渲到 notes/（不呼叫 Ollama）。"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from note_generator_server import save_note_from_data
from note_html_render import extract_source_url, normalize_note
from note_shell import build_course_sidebar, chapters_from_note
from build_notes_index import main as rebuild_notes_index

TAX_NOTES_DIR = ROOT / "notes" / "簡單開公司"
COURSE_BRAND = "簡單開公司"


def main() -> int:
    src_dir = ROOT / "_structured"
    files = sorted(src_dir.glob("*.json"))
    if not files:
        print("no json")
        return 1
    TAX_NOTES_DIR.mkdir(parents=True, exist_ok=True)

    loaded: list[tuple[str, dict]] = []
    for path in files:
        stem = path.stem
        data = json.loads(path.read_text(encoding="utf-8"))
        txt = ROOT / "output" / f"{stem}.txt"
        if txt.is_file() and not data.get("source_url"):
            data["source_url"] = extract_source_url(
                txt.read_text(encoding="utf-8", errors="ignore")
            )
        if not data.get("badge"):
            m = stem.split(" ", 1)[0]
            if m:
                data["badge"] = f"單元 {m}"
        note = normalize_note(data, fallback_title=stem)
        loaded.append((stem, note))

    books = [
        {
            "file": f"{stem}.html",
            "title": note.get("title") or stem,
            "chapters": chapters_from_note(note),
        }
        for stem, note in loaded
    ]

    ok = 0
    for stem, note in loaded:
        active_file = f"{stem}.html"
        sidebar_html = build_course_sidebar(
            brand=COURSE_BRAND,
            brand_sub="課程目錄",
            books=books,
            active_file=active_file,
            home_href="../index.html",
        )
        save_note_from_data(
            stem,
            note,
            out_dir=TAX_NOTES_DIR,
            sidebar_html=sidebar_html,
            course_brand=COURSE_BRAND,
            active_file=active_file,
            books=books,
        )
        print("OK", stem)
        ok += 1

    if loaded:
        first = f"{loaded[0][0]}.html"
        (TAX_NOTES_DIR / "index.html").write_text(
            "<!DOCTYPE html><html lang='zh-Hant'><head><meta charset='UTF-8'/>"
            f"<meta http-equiv='refresh' content='0;url={html.escape(first)}'/>"
            f"<title>導向講義</title></head><body>"
            f"<p>正在進入講義… <a href='{html.escape(first)}'>若未自動跳轉請點此</a></p>"
            "</body></html>\n",
            encoding="utf-8",
        )
        print("OK index.html ->", first)

    print(f"done {ok}/{len(files)} -> {TAX_NOTES_DIR}")
    rebuild_notes_index()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

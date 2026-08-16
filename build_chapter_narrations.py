# -*- coding: utf-8 -*-
"""為各筆記小章節產生口語語音講解稿（規則整理，不呼叫 AI），並重渲 HTML。

文字稿：由 Cursor 維護的 compose_* 從講義結構化整理。
朗讀：瀏覽器 Web Speech API（系統語音，非 AI）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from note_generator_server import save_note_from_data  # noqa: E402
from note_html_render import extract_source_url, normalize_note  # noqa: E402
from note_narration import (  # noqa: E402
    compose_from_chapter,
    compose_from_ebook_kid,
    compose_from_ebook_section,
)
from note_shell import build_course_sidebar, chapters_from_note  # noqa: E402
from build_notes_index import main as rebuild_notes_index  # noqa: E402
from convert_ebook_md_to_html import (  # noqa: E402
    OUT_DIR as EBOOK_OUT,
    SRC_DIR as EBOOK_SRC,
    _chapter_sort_key,
    _parse_sections,
    main as convert_ebook_main,
)

TAX_DIR = ROOT / "notes" / "簡單開公司"
STRUCT_DIR = ROOT / "_structured"
EBOOK_NARR_CACHE = EBOOK_OUT / "_narrations.json"


def enrich_tax_notes(*, force: bool = True) -> int:
    files = sorted(STRUCT_DIR.glob("*.json"))
    if not files:
        print("no structured json")
        return 0
    items = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        txt = ROOT / "output" / f"{path.stem}.txt"
        if txt.is_file() and not data.get("source_url"):
            data["source_url"] = extract_source_url(
                txt.read_text(encoding="utf-8", errors="ignore")
            )
        if not data.get("badge"):
            m = path.stem.split(" ", 1)[0]
            if m:
                data["badge"] = f"單元 {m}"
        note = normalize_note(data, fallback_title=path.stem)
        changed = False
        for i, ch in enumerate(note.get("chapters") or [], 1):
            if not isinstance(ch, dict):
                continue
            if ch.get("narration") and not force:
                continue
            ch["narration"] = compose_from_chapter(ch)
            changed = True
            print(f"  講解稿：{path.stem} / {ch.get('title') or i} ({len(ch['narration'])}字)")
        if changed:
            path.write_text(
                json.dumps(note, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        items.append((path.stem, note))

    TAX_DIR.mkdir(parents=True, exist_ok=True)
    books = [
        {
            "file": f"{stem}.html",
            "title": note.get("title") or stem,
            "chapters": chapters_from_note(note),
        }
        for stem, note in items
    ]
    for stem, note in items:
        active = f"{stem}.html"
        sidebar = build_course_sidebar(
            brand="簡單開公司",
            brand_sub="課程目錄",
            books=books,
            active_file=active,
            home_href="../index.html",
        )
        save_note_from_data(
            stem,
            note,
            out_dir=TAX_DIR,
            sidebar_html=sidebar,
            course_brand="簡單開公司",
            active_file=active,
            books=books,
        )
        print("OK tax", stem)

    if books:
        first = books[0]["file"]
        (TAX_DIR / "index.html").write_text(
            "<!DOCTYPE html><html lang='zh-Hant'><head><meta charset='UTF-8'/>"
            f"<meta http-equiv='refresh' content='0;url={first}'/>"
            f"<title>導向講義</title></head><body>"
            f"<p>正在進入講義… <a href='{first}'>若未自動跳轉請點此</a></p>"
            "</body></html>\n",
            encoding="utf-8",
        )
    return len(items)


def enrich_ebook(*, force: bool = True) -> int:
    if not EBOOK_SRC.is_dir():
        print("ebook src missing:", EBOOK_SRC)
        return 0
    EBOOK_OUT.mkdir(parents=True, exist_ok=True)
    cache: dict[str, str] = {}
    if EBOOK_NARR_CACHE.is_file() and not force:
        try:
            cache = json.loads(EBOOK_NARR_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    files = sorted(EBOOK_SRC.glob("*.md"), key=_chapter_sort_key)
    n = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        _title, sections, _preface = _parse_sections(text)
        for sec in sections:
            sid = str(sec.get("id") or "")
            if sid and (force or not cache.get(sid)):
                cache[sid] = compose_from_ebook_section(sec)
                n += 1
                print(f"  講解稿：{path.stem} / {sec.get('title')} ({len(cache[sid])}字)")
            for kid in sec.get("kids") or []:
                kid_id = str(kid.get("id") or "")
                if kid_id and (force or not cache.get(kid_id)):
                    cache[kid_id] = compose_from_ebook_kid(kid)
                    n += 1
    EBOOK_NARR_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"ebook narrations: {len(cache)} -> {EBOOK_NARR_CACHE}")
    return n


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="產生章節語音講解稿（非 AI）")
    ap.add_argument("--force", action="store_true", default=True)
    ap.add_argument("--keep", action="store_true", help="保留既有講解稿")
    ap.add_argument("--tax-only", action="store_true")
    ap.add_argument("--ebook-only", action="store_true")
    args = ap.parse_args()
    force = not args.keep

    if not args.ebook_only:
        print("=== 財稅筆記：整理講解稿 + 重渲 ===")
        enrich_tax_notes(force=force)
    if not args.tax_only:
        print("=== 公司治理：整理講解稿 + 重渲 ===")
        enrich_ebook(force=force)
        convert_ebook_main()
    rebuild_notes_index()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

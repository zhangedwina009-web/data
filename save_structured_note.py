# -*- coding: utf-8 -*-
"""把結構化 note JSON 渲染成 HTML/MD，寫入 notes/（不呼叫 Ollama）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from note_generator_server import NOTES_DIR, save_note_from_data  # noqa: E402
from note_html_render import extract_source_url, normalize_note  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: save_structured_note.py <note.json> [stem]")
        return 2
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    stem = sys.argv[2] if len(sys.argv) > 2 else path.stem
    # 可選：從同名 output txt 補來源
    src_txt = ROOT / "output" / f"{stem}.txt"
    if src_txt.is_file() and not data.get("source_url"):
        data["source_url"] = extract_source_url(src_txt.read_text(encoding="utf-8", errors="ignore"))
    note = normalize_note(data, fallback_title=stem)
    saved = save_note_from_data(stem, note, out_dir=NOTES_DIR)
    print(saved["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

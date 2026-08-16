# -*- coding: utf-8 -*-
"""批次：把 output/*.txt 整理成架構化 HTML，覆蓋寫入 notes/。"""

from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# 降低記憶體壓力（可被環境變數覆寫）
os.environ.setdefault("OLLAMA_NUM_CTX", "3072")
os.environ.setdefault("OLLAMA_NUM_PREDICT", "2048")
os.environ.setdefault("NOTE_INPUT_CHARS", "10000")
os.environ.setdefault("CHAPTER_INPUT_CHARS", "5500")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from note_generator_server import (  # noqa: E402
    NOTES_DIR,
    OUTPUT_DIR,
    build_note_outputs,
    generate_note_multipass,
    read_text_file,
    save_note,
)

LOG = ROOT / "logs" / "batch_rebuild_notes.log"
DONE_FILE = ROOT / "logs" / "batch_rebuild_done.txt"
MODEL = os.environ.get("NOTE_BATCH_MODEL", "gemma2:2b")
STYLE = os.environ.get("NOTE_BATCH_STYLE", "詳細")
# 預設續跑：已在 done 清單的略過。強制全重做：設 NOTE_BATCH_RESUME=0
RESUME = os.environ.get("NOTE_BATCH_RESUME", "1") == "1"


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("cp950", errors="replace").decode("cp950", errors="replace"), flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_done() -> set[str]:
    if not DONE_FILE.is_file():
        return set()
    return {ln.strip() for ln in DONE_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()}


def mark_done(stem: str) -> None:
    with DONE_FILE.open("a", encoding="utf-8") as f:
        f.write(stem + "\n")


def main() -> int:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(OUTPUT_DIR.glob("*.txt"), key=lambda p: p.name)
    if not files:
        log(f"no txt in {OUTPUT_DIR}")
        return 1

    # 若 1-1 已在稍早成功寫入，補進 done
    stem_1_1 = "1-1 給創業者的財稅地圖：從個人到公司"
    html_1_1 = NOTES_DIR / f"{stem_1_1}.html"
    if html_1_1.is_file() and "自動產生失敗" not in html_1_1.read_text(encoding="utf-8", errors="ignore"):
        done0 = load_done()
        if stem_1_1 not in done0:
            mark_done(stem_1_1)

    done = load_done() if RESUME else set()
    log(f"START files={len(files)} model={MODEL} resume={RESUME} done={len(done)} out={NOTES_DIR}")
    ok, bad, skipped = 0, [], 0

    for i, path in enumerate(files, 1):
        stem = path.stem
        log(f"({i}/{len(files)}) {stem}")
        if RESUME and stem in done:
            skipped += 1
            ok += 1
            log("  SKIP")
            continue

        t0 = time.time()
        try:
            raw = read_text_file(path)
            note = generate_note_multipass(MODEL, stem, raw, STYLE)
            note_title, md, html_doc = build_note_outputs(note)
            saved = save_note(
                stem,
                md,
                title=note_title,
                out_dir=NOTES_DIR,
                html_doc=html_doc,
            )
            mark_done(stem)
            ok += 1
            secs = time.time() - t0
            nch = len(note.get("chapters") or [])
            log(f"  OK chapters={nch} secs={secs:.0f} html={saved['html']}")
        except Exception as e:
            bad.append((stem, str(e)))
            log(f"  FAIL: {e}")
            traceback.print_exc()
            try:
                fail_html = (
                    "<!DOCTYPE html><html lang='zh-Hant'><meta charset='utf-8'>"
                    f"<title>{stem}</title><body style='font-family:sans-serif;padding:2rem'>"
                    f"<h1>{stem}</h1><p>自動產生失敗：{e}</p></body></html>"
                )
                (NOTES_DIR / f"{stem}.html").write_text(fail_html, encoding="utf-8")
            except Exception:
                pass

    log(f"DONE ok={ok}/{len(files)} fail={len(bad)} skipped={skipped}")
    for stem, err in bad:
        log(f"  - {stem}: {err[:200]}")
    return 0 if not bad else 2


if __name__ == "__main__":
    raise SystemExit(main())

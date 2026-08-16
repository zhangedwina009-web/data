# -*- coding: utf-8 -*-
"""
教學筆記產生器本機伺服器
- 暗色響應式 UI（Bootstrap）
- 列出 / 讀取 output 與路徑下的 txt
- 代理本機 Ollama：JSON → Bootstrap HTML 筆記
"""

from __future__ import annotations

import html
import json
import mimetypes
import os
import re
import sys
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from note_html_render import (
    SYSTEM_PROMPT_CHAPTER,
    SYSTEM_PROMPT_JSON,
    SYSTEM_PROMPT_OUTLINE,
    assemble_note,
    clean_source_text,
    dedupe_texts,
    extract_json_object,
    extract_source_url,
    is_low_quality_chapter,
    is_weak_chapter_body,
    normalize_chapter,
    normalize_note,
    normalize_outline,
    note_to_markdown,
    render_note_body,
    text_similarity,
    wrap_bootstrap_document,
)

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
NOTES_DIR = ROOT / "notes"
INDEX_FILE = ROOT / "index.html"
HTML_FILE = ROOT / "apps" / "note_generator.html"
APPS_DIR = ROOT / "apps"
HOST = "127.0.0.1"
PORT = 8765
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip()
MAX_CHARS = 80000
# 限制上下文，避免 Ollama KV cache 爆記憶體（可用環境變數覆寫）
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "3072"))
NOTE_INPUT_CHARS = int(os.environ.get("NOTE_INPUT_CHARS", "12000"))
CHAPTER_INPUT_CHARS = int(os.environ.get("CHAPTER_INPUT_CHARS", "6000"))

SYSTEM_PROMPT = SYSTEM_PROMPT_JSON


def soft_trim(text: str, limit: int) -> str:
    body = (text or "").strip()
    if len(body) > limit:
        return body[:limit] + "\n\n…（素材過長，已截斷以節省記憶體）"
    return body


def prepare_content(content: str) -> str:
    """進模型前統一清洗爬蟲表頭／口播斷行。"""
    return clean_source_text(content or "")


def pick_material_for_chapter(content: str, chapter: dict, max_chars: int | None = None) -> str:
    """依章名／焦點關鍵字挑選較相關段落；找不到則退回截斷全文。"""
    limit = max_chars if max_chars is not None else CHAPTER_INPUT_CHARS
    body = prepare_content(content)
    if not body:
        return ""
    if len(body) <= limit:
        return body

    # 章名任務詞 + 焦點；略過太泛用的詞
    stop = {
        "說明", "整理", "比較", "注意", "事項", "背景", "適用", "情境", "方案",
        "線索", "素材", "重點", "如何", "以及", "還有", "本章", "這章",
    }
    keys: list[str] = []
    for raw in (chapter.get("title"), chapter.get("focus")):
        if not raw:
            continue
        for tok in re.split(r"[\s,，、；;：:。！？!?/｜|]+", str(raw)):
            tok = tok.strip()
            if len(tok) >= 2 and tok not in stop:
                keys.append(tok)
    # 主題詞加權
    for kw in ("小規模", "營業人", "行號", "公司", "發票", "起徵點", "營業稅", "資本", "有限"):
        if kw in (chapter.get("title") or "") or kw in (chapter.get("focus") or ""):
            keys.append(kw)
    seen: set[str] = set()
    keys = [k for k in keys if not (k in seen or seen.add(k))]

    paras = [p.strip() for p in re.split(r"\n\s*\n+", body) if p.strip()]
    scored: list[tuple[int, str]] = []
    for p in paras:
        score = sum(2 for k in keys if k in p)
        if re.search(r"\d", p):
            score += 1
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], -len(x[1])))

    if scored:
        chunks: list[str] = []
        total = 0
        for _, p in scored:
            if total >= limit:
                break
            take = p[: max(200, limit - total)]
            chunks.append(take)
            total += len(take) + 2
        picked = "\n\n".join(chunks)
        if len(picked) < min(600, limit // 3):
            # 補中段，避開開頭寒暄
            mid = body[len(body) // 5 :]
            head = mid[: max(0, limit - len(picked) - 20)]
            picked = (picked + "\n\n" + head).strip()
        return soft_trim(picked, limit)

    # 沒關鍵字命中：略過前 15% 開場，取中段
    start = min(len(body) // 6, 400)
    return soft_trim(body[start:], limit)


def ollama_base() -> str:
    h = OLLAMA_HOST
    if not h.startswith("http"):
        h = "http://" + h
    return h.rstrip("/")


def http_json(method: str, url: str, payload: dict | None = None, timeout: int = 30):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def safe_resolve(user_path: str) -> Path:
    if not user_path or not str(user_path).strip():
        raise ValueError("路徑空白")
    p = Path(user_path.strip().strip('"'))
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    try:
        p.relative_to(ROOT)
        in_root = True
    except ValueError:
        in_root = False
    if not in_root and not p.exists():
        raise ValueError(f"路徑不存在：{p}")
    return p


def list_txt(dir_path: Path) -> list[dict]:
    if not dir_path.exists():
        return []
    if dir_path.is_file():
        if dir_path.suffix.lower() == ".txt":
            st = dir_path.stat()
            return [
                {
                    "name": dir_path.name,
                    "path": str(dir_path),
                    "size": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                }
            ]
        return []
    items = []
    for f in sorted(dir_path.glob("*.txt"), key=lambda x: x.name):
        st = f.stat()
        items.append(
            {
                "name": f.name,
                "path": str(f),
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
        )
    return items


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def stem_from_path(path: Path) -> str:
    name = path.stem
    name = re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "note"
    return name[:120]


def build_user_prompt(title: str, content: str, style: str) -> str:
    style_line = (
        "風格：詳細。每章選最適 visual（cards／compare／mermaid／chart／table），輸出完整 JSON。"
        if style != "精簡"
        else "風格：精簡。章節少一點，但仍要 JSON，且每章盡量有 visual。"
    )
    t = (title or "").strip() or "（請依素材自訂標題）"
    body = soft_trim(content, min(MAX_CHARS, NOTE_INPUT_CHARS))
    return (
        f"{style_line}\n"
        f"建議 title：{t}\n"
        "只輸出 JSON 物件，不要其它文字。\n\n"
        f"===== 素材開始 =====\n{body}\n===== 素材結束 ====="
    )


def _ollama_error_hint(model: str, code: int, detail: str) -> str:
    return (
        f"Ollama 回傳錯誤 HTTP {code}（模型：{model}）。\n{detail}\n\n"
        "若看到 out-of-memory／failed to allocate：\n"
        "1. 改選較小模型（建議 gemma2:2b 或 qwen3.5:2b）\n"
        "2. 關掉其他佔記憶體的程式／其他 Ollama 對話\n"
        "3. 在終端機執行：ollama stop\n"
        "4. 仍不足可設較小上下文後重開伺服器：\n"
        "   set OLLAMA_NUM_CTX=2048\n"
    )


def call_ollama_json(
    model: str,
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    num_predict: int | None = None,
) -> dict:
    """呼叫 Ollama chat（format=json），回傳解析後的 dict。"""
    url = f"{ollama_base()}/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {
            "temperature": temperature,
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT if num_predict is None else num_predict,
        },
    }
    try:
        data = http_json("POST", url, payload, timeout=600)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(_ollama_error_hint(model, e.code, detail)) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"無法連線 Ollama（{ollama_base()}）。請先啟動 Ollama，並確認已 pull 模型。\n{e}"
        ) from e
    msg = (data.get("message") or {}).get("content") or ""
    if not msg.strip():
        raise RuntimeError("Ollama 回傳空白，請換模型或縮短素材再試。")
    try:
        return extract_json_object(msg)
    except Exception as e:
        raise RuntimeError(f"無法解析模型 JSON：{e}\n原文前 300 字：{msg[:300]}") from e


def call_ollama_outline(model: str, title: str, content: str, style: str) -> dict:
    """Pass 1：只產大綱。"""
    style_line = (
        "風格：詳細。請自主分成 3～5 個具體主題章節（章名要具體，不要「核心概念」）。"
        if style != "精簡"
        else "風格：精簡。請自主分成 2～3 個具體主題章節。"
    )
    t = (title or "").strip() or "（請依素材自訂標題）"
    body = soft_trim(prepare_content(content), min(MAX_CHARS, NOTE_INPUT_CHARS))
    user = (
        f"{style_line}\n"
        f"建議 title：{t}\n"
        "重要：summary 與 chapters 全部用繁體中文短句，禁止英文。\n"
        "focus 要寫「教學任務」不是口播原句；不要出現來源／網址／class。\n"
        "只輸出大綱 JSON（含 chapters 的 title／focus／visualHint），不要寫正文。\n\n"
        f"===== 素材開始 =====\n{body}\n===== 素材結束 ====="
    )
    raw = call_ollama_json(
        model,
        SYSTEM_PROMPT_OUTLINE,
        user,
        temperature=0.2,
        num_predict=min(OLLAMA_NUM_PREDICT, 2048),
    )
    outline = normalize_outline(raw, fallback_title=title, style=style, content=content)
    # 若章名仍太空泛或摘要太少，再逼一次
    titles = [c.get("title") for c in (outline.get("chapters") or [])]
    weak = (not outline.get("summary")) or any(
        t in ("核心概念", "重點整理", "章節") for t in titles
    )
    if weak:
        retry_user = (
            user
            + "\n\n【重做】上一輪還沒分好主題。請依素材重產大綱："
            "章名必須具體（例如門檻、比較、限制、轉換），summary 至少 3 條繁中短句。"
        )
        try:
            raw2 = call_ollama_json(
                model,
                SYSTEM_PROMPT_OUTLINE,
                retry_user,
                temperature=0.15,
                num_predict=min(OLLAMA_NUM_PREDICT, 2048),
            )
            outline = normalize_outline(
                raw2, fallback_title=title, style=style, content=content
            )
        except Exception:
            pass
    return outline


def _extract_numbered_blocks(chunk: str) -> list[tuple[str, str]]:
    """抓『第一／第二…』注意事項條列（略過『第一個階段』這類敘事）。"""
    text = re.sub(r"\s+", "", chunk or "")
    if not text:
        return []
    # 負向：第一個階段／第一步／第一種
    parts = re.split(r"(?=第[一二三四五六七八九十](?![個階種步]))", text)
    out: list[tuple[str, str]] = []
    for part in parts:
        m = re.match(r"(第[一二三四五六七八九十])(?![個階種步])(.+)", part)
        if not m:
            continue
        body = m.group(2).strip()
        if len(body) < 12:
            continue
        # 標題取前幾個實詞
        title = re.split(r"[，,。：:]", body)[0][:16] or m.group(1)
        content = body if body.endswith(("。", "？", "！")) else body + "。"
        if len(content) > 160:
            content = content[:160] + "…"
        out.append((title, content))
        if len(out) >= 5:
            break
    return out


def _diverse_paragraphs(chunk: str, limit: int = 4) -> list[str]:
    """挑選彼此差異大、資訊密度高的段落。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n+", chunk or "") if p.strip()]
    if not paras:
        paras = [p.strip() for p in re.split(r"(?<=[。！？])", chunk or "") if p.strip()]

    def score(p: str) -> int:
        s = 0
        for kw in ("公司", "行號", "小規模", "發票", "稅", "萬", "登記", "資本", "有限", "地址", "項目"):
            if kw in p:
                s += 2
        if re.search(r"\d", p):
            s += 2
        if p.endswith("？") or p.endswith("?"):
            s -= 3
        if "來源" in p or "http" in p:
            s -= 10
        # 太短或像碎句
        if len(re.sub(r"\s+", "", p)) < 18:
            s -= 4
        return s

    ranked = sorted(paras, key=score, reverse=True)
    picked: list[str] = []
    for p in ranked:
        if score(p) < 1:
            continue
        sentences = [x.strip() for x in re.split(r"(?<=[。！？])", p) if x.strip()]
        use = "".join(sentences[:3]) if sentences else p
        use = use.strip()
        if len(use) > 140:
            use = use[:140] + "…"
        if not use.endswith(("。", "？", "！", "…")):
            use += "。"
        if any(text_similarity(use, x) >= 0.5 for x in picked):
            continue
        picked.append(use)
        if len(picked) >= limit:
            break
    return dedupe_texts(picked, threshold=0.5)


def _chapter_from_material(
    chapter_spec: dict, content: str, fallback_title: str, visual_hint: str
) -> dict:
    """模型失敗時：組成『有架構』的後備章，禁止重複碎片要點卡。"""
    focus = (chapter_spec.get("focus") or fallback_title).strip()
    focus_clean = re.sub(r"線索[:：].*$", "", focus).strip(" ；;") or fallback_title
    chunk = pick_material_for_chapter(content, chapter_spec, max_chars=3200)

    numbered_all = _extract_numbered_blocks(chunk)
    # 條列需與章名／焦點有關，避免把別章的「第一／第二」塞進來
    topic = f"{fallback_title}{focus_clean}"
    topic_keys = [
        k
        for k in re.split(r"[\s,，、；;：:？?／/]+", topic)
        if len(k) >= 2 and k not in {"重點", "說明", "整理", "比較", "選擇", "哪一", "種？", "考量"}
    ]
    numbered: list[tuple[str, str]] = []
    for t, x in numbered_all:
        blob = t + x
        if topic_keys and sum(1 for k in topic_keys if k in blob) >= 1:
            numbered.append((t, x))
        elif any(k in blob for k in ("地址", "資本", "營業項目", "扣抵", "發票", "營收", "銷售")) and any(
            k in topic for k in ("注意", "限制", "小規模", "條件", "門檻")
        ):
            numbered.append((t, x))
    diverse = _diverse_paragraphs(chunk, limit=4)

    body_lines = [f"重點：{focus_clean}。"]
    visual: dict = {"type": "none"}

    if len(numbered) >= 2:
        body_lines.append("判斷或整理：可依下列條件理解本章。")
        for title, text in numbered[:4]:
            body_lines.append(f"{title}：{text}")
        visual = {
            "type": "cards",
            "items": [{"title": t, "text": x.rstrip("。")} for t, x in numbered[:4]],
        }
    elif diverse:
        body_lines.append("判斷或比較：")
        for i, p in enumerate(diverse[:3], 1):
            body_lines.append(f"{i}. {p}")
        if len(diverse) >= 2:
            # 用有意義短標，不要「要點 N」
            items = []
            for p in diverse[:3]:
                label = re.split(r"[，,：:。]", p)[0][:14] or "重點"
                items.append({"title": label, "text": p.rstrip("。")})
            # 若標題彼此太像就不放卡
            labels = [it["title"] for it in items]
            if len(dedupe_texts(labels, 0.6)) >= 2:
                visual = {"type": "cards", "items": items}
        body_lines.append("注意：以上由素材整理而成，細節請對照原文條件與例外。")
    else:
        body_lines.append("（素材對應段落不足，請換模型或加長素材後重跑。）")

    # 比較類章名：優先 compare（若有兩段差異夠大）
    title_l = fallback_title + focus_clean
    if any(k in title_l for k in ("比較", "選擇", "vs", "VS", "差異")) and len(diverse) >= 2:
        visual = {
            "type": "compare",
            "leftTitle": "面向 A",
            "rightTitle": "面向 B",
            "rows": [
                {"left": diverse[0][:80], "right": diverse[1][:80]},
            ],
        }

    body = "\n".join(body_lines)
    ch = normalize_chapter(
        {
            "title": fallback_title,
            "body": body,
            "visual": visual,
            "notes": ["此章為結構後備整理；若敘述偏簡，建議換較穩模型重跑。"],
            "warning": "",
        },
        fallback_title=fallback_title,
        visual_hint="none",
        focus=focus_clean,
    )
    return ch


def call_ollama_chapter(
    model: str,
    note_title: str,
    content: str,
    chapter_spec: dict,
    style: str,
    index: int,
    total: int,
) -> dict:
    """Pass 2：產生單一章節（低品質／重複碎片會重試，再結構後備）。"""
    style_line = (
        "風格：詳細教學筆記。body 用『重點／判斷或比較／注意』三段式改寫。"
        if style != "精簡"
        else "風格：精簡但仍要有重點、判斷、注意三段。"
    )
    ctitle = (chapter_spec.get("title") or f"第{index}章").strip()
    focus = (chapter_spec.get("focus") or "").strip()
    hint = (chapter_spec.get("visualHint") or "cards").strip()
    # 比較／選擇章預設 compare
    if any(k in (ctitle + focus) for k in ("比較", "選擇", "差異", "vs", "VS")):
        if hint in ("cards", "fact", "none", ""):
            hint = "compare"
    chunk = pick_material_for_chapter(content, chapter_spec, max_chars=3500)

    def _once(extra: str = "", temperature: float = 0.25) -> dict:
        user = (
            f"{style_line}\n"
            f"整篇標題：{(note_title or '').strip() or '教學筆記'}\n"
            f"這是第 {index}/{total} 章，只寫這一章。\n"
            f"章名：{ctitle}\n"
            f"本章焦點：{focus}\n"
            f"建議 visualHint：{hint}\n"
            "請整理成有邏輯的教學內容，不要剪貼相似口播句。\n"
            "body 範例格式（內容自填）：\n"
            "重點：…\n判斷或比較：…\n注意：…\n"
            "visual 的卡片標題禁止使用『要點1/2/3』。\n"
            "禁止英文；不要複製來源網址／定位／class。\n"
            f"{extra}\n"
            f"===== 本章相關素材 =====\n{chunk}\n===== 素材結束 ====="
        )
        raw = call_ollama_json(
            model,
            SYSTEM_PROMPT_CHAPTER,
            user,
            temperature=temperature,
            num_predict=min(OLLAMA_NUM_PREDICT, 2560),
        )
        return normalize_chapter(
            raw, fallback_title=ctitle, visual_hint=hint, focus=focus
        )

    ch = None
    try:
        ch = _once()
    except Exception:
        ch = None

    if ch is None or is_low_quality_chapter(ch) or is_weak_chapter_body(ch.get("body") or ""):
        try:
            ch = _once(
                "【重做】上一輪像在重複口播碎片。請改寫成教學架構："
                "重點（結論）→ 判斷條件／比較 → 實務注意；卡片標題要用有意義詞。",
                temperature=0.15,
            )
        except Exception:
            ch = None

    if ch is None or is_low_quality_chapter(ch) or is_weak_chapter_body(ch.get("body") or ""):
        return _chapter_from_material(chapter_spec, content, ctitle, hint)
    return ch


def generate_note_multipass(model: str, title: str, content: str, style: str) -> dict:
    """大綱 + 逐章生成，最後組合成完整 note。"""
    source_url = extract_source_url(content)
    cleaned = prepare_content(content)
    outline = call_ollama_outline(model, title, cleaned, style)
    specs = outline.get("chapters") or []
    total = len(specs)
    chapters: list[dict] = []
    for i, spec in enumerate(specs, 1):
        ch = call_ollama_chapter(
            model,
            outline.get("title") or title,
            cleaned,
            spec if isinstance(spec, dict) else {"title": str(spec)},
            style,
            i,
            total,
        )
        chapters.append(ch)
    return assemble_note(
        outline,
        chapters,
        fallback_title=title,
        content=cleaned,
        source_url=source_url,
    )


def call_ollama_note(model: str, title: str, content: str, style: str) -> dict:
    """呼叫 Ollama（大綱+逐章），回傳 note dict（已 normalize）。"""
    return generate_note_multipass(model, title, content, style)


def call_ollama(model: str, title: str, content: str, style: str) -> str:
    """相容舊介面：回傳 Markdown 摘要。"""
    note = call_ollama_note(model, title, content, style)
    return note_to_markdown(note)


def build_note_outputs(
    note: dict,
    *,
    sidebar_html: str = "",
    course_brand: str = "教學講義",
    active_file: str = "",
    books=None,
) -> tuple[str, str, str]:
    """回傳 (title, markdown, full_html)。"""
    title = note.get("title") or "教學筆記"
    body = render_note_body(note)
    full_html = wrap_bootstrap_document(
        title,
        body,
        sidebar_html=sidebar_html,
        course_brand=course_brand,
        active_file=active_file,
        books=books,
    )
    md = note_to_markdown(note)
    return title, md, full_html


def clean_markdown(text: str) -> str:
    t = text.strip()
    if t.startswith("```") and t.endswith("```"):
        lines = t.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    t = normalize_broken_fences(t)
    return ensure_visual(t)


def normalize_broken_fences(md: str) -> str:
    """修正小模型常見的錯誤輸出，讓前端／匯出能渲染。"""
    t = md.replace("\r\n", "\n")
    # 去掉「視覺：」前綴
    t = re.sub(r"(?m)^\s*視覺\s*[：:]\s*", "", t)
    # ```mermaid flowchart / ```mermaid graph → ```mermaid
    t = re.sub(r"```\s*mermaid\s+\w+", "```mermaid", t, flags=re.I)
    # ```cards 等若被寫成行內殘片「```cards」前有字，已在上面清視覺

    def fix_cards_body(body: str) -> str:
        out = []
        for ln in body.split("\n"):
            s = ln.strip()
            if not s:
                continue
            # 卡片1：說明 / 卡片1: 標題：說明
            m = re.match(r"^卡片\s*\d+\s*[：:]\s*(.+)$", s)
            if m:
                rest = m.group(1).strip()
                if "｜" in rest or "|" in rest:
                    out.append(rest.replace("|", "｜"))
                elif "：" in rest or ":" in rest:
                    parts = re.split(r"[：:]", rest, maxsplit=1)
                    out.append(f"{parts[0].strip()}｜{parts[1].strip()}")
                else:
                    out.append(f"重點｜{rest}")
                continue
            if "｜" not in s and "|" in s:
                s = s.replace("|", "｜", 1)
            if "｜" not in s and ("：" in s or ":" in s):
                parts = re.split(r"[：:]", s, maxsplit=1)
                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                    s = f"{parts[0].strip()}｜{parts[1].strip()}"
            out.append(s)
        return "\n".join(out)

    def fix_compare_body(body: str) -> str:
        lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
        if not lines:
            return body
        fixed = []
        for i, s in enumerate(lines):
            s = s.replace("|", "｜")
            # 左欄標題：行號
            s = re.sub(r"^左欄標題\s*[：:]\s*", "", s)
            s = re.sub(r"^右欄標題\s*[：:]\s*", "", s)
            s = re.sub(r"^左重點\s*\d*\s*[：:]\s*", "", s)
            s = re.sub(r"^右重點\s*\d*\s*[：:]\s*", "", s)
            if "｜" not in s and i == 0 and len(lines) >= 2:
                # 兩行分別是左右標題
                pass
            fixed.append(s)
        # 若模型拆成「左欄標題：A」「右欄標題：B」兩行 → 合成 A｜B
        if len(fixed) >= 2 and "｜" not in fixed[0] and "｜" not in fixed[1]:
            if re.search(r"左|行號|個人", fixed[0]) or True:
                head = f"{fixed[0]}｜{fixed[1]}"
                rest = fixed[2:]
                # 嘗試成對合併剩餘
                pairs = [head]
                i = 0
                while i < len(rest):
                    if i + 1 < len(rest) and "｜" not in rest[i]:
                        pairs.append(f"{rest[i]}｜{rest[i+1]}")
                        i += 2
                    else:
                        pairs.append(rest[i])
                        i += 1
                return "\n".join(pairs)
        return "\n".join(fixed)

    def repl_fence(m: re.Match) -> str:
        lang = (m.group(1) or "").strip().lower()
        body = m.group(2)
        if lang.startswith("mermaid"):
            lang = "mermaid"
        if lang == "cards":
            body = fix_cards_body(body)
        elif lang == "compare":
            body = fix_compare_body(body)
        elif lang in ("fact",):
            body = fix_cards_body(body)  # 同樣把冒號改｜
        return f"```{lang}\n{body.strip()}\n```"

    t = re.sub(r"```([^\n`]*)\n([\s\S]*?)```", repl_fence, t)
    return t


def ensure_visual(md: str) -> str:
    """若完全沒有任何視覺結構，才補一個輕量事實卡（不再硬塞 Mermaid）。"""
    if re.search(r"```\s*(mermaid|fact|cards|compare|matrix2x2|chart)\b", md, re.I):
        return md
    if re.search(r"^\|.+\|\s*$", md, re.M) and re.search(r"^\|\s*[-:]+", md, re.M):
        return md
    block = (
        "\n\n## 關鍵主張卡\n\n"
        "```fact\n"
        "核心重點｜請回到正文對照素材主軸\n"
        "（模型未產出視覺區塊時的後備呈現）\n"
        "```\n"
    )
    return md.rstrip() + block


_CHART_SEQ = 0


def render_chart_block(code: str) -> str:
    """把 ```chart JSON 轉成 canvas + 內嵌 JSON，供 Chart.js 初始化。"""
    global _CHART_SEQ
    raw = code.strip()
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        data = json.loads(m.group(0) if m else raw)
        if not isinstance(data, dict):
            raise ValueError("chart 必須是物件")
        payload = json.dumps(data, ensure_ascii=False)
    except Exception:
        return (
            f'<div class="alert alert-warning">無法解析 chart 區塊'
            f'<pre class="mb-0 mt-2"><code>{html.escape(raw[:800])}</code></pre></div>'
        )
    _CHART_SEQ += 1
    cid = f"chart_{_CHART_SEQ}"
    title = html.escape(str(data.get("title") or ""))
    title_html = f'<div class="chart-title">{title}</div>' if title else ""
    return (
        f'<div class="chart-box">'
        f"{title_html}"
        f'<canvas id="{cid}" class="note-chart" width="640" height="320"></canvas>'
        f'<script type="application/json" class="chart-config">{html.escape(payload)}</script>'
        f"</div>"
    )


def _inline_md(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def _split_pipe(line: str) -> list[str]:
    return [p.strip() for p in line.split("|")]


def render_fact_block(code: str) -> str:
    lines = [ln.strip() for ln in code.splitlines() if ln.strip()]
    if not lines:
        return ""
    head = _split_pipe(lines[0])
    title = head[0] if head else "事實"
    lead = head[1] if len(head) > 1 else ""
    rest = "<br />".join(_inline_md(x) for x in lines[1:])
    body_html = f'<div class="fact-body">{rest}</div>' if rest else ""
    return (
        f'<div class="fact-card"><div class="fact-title">{_inline_md(title)}</div>'
        f'<div class="fact-lead">{_inline_md(lead)}</div>{body_html}</div>'
    )


def render_cards_block(code: str) -> str:
    items = []
    for ln in code.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("---"):
            continue
        parts = _split_pipe(ln)
        title = parts[0] if parts else ""
        body = parts[1] if len(parts) > 1 else ""
        items.append(
            f'<div class="card-item"><h4>{_inline_md(title)}</h4>'
            f"<p>{_inline_md(body)}</p></div>"
        )
    if not items:
        return ""
    return f'<div class="cards-grid">{"".join(items)}</div>'


def render_compare_block(code: str) -> str:
    rows = [ln.strip() for ln in code.splitlines() if ln.strip()]
    if not rows:
        return ""
    heads = _split_pipe(rows[0])
    left_h = heads[0] if heads else "A"
    right_h = heads[1] if len(heads) > 1 else "B"
    left_items, right_items = [], []
    for ln in rows[1:]:
        parts = _split_pipe(ln)
        left_items.append(parts[0] if parts else "")
        right_items.append(parts[1] if len(parts) > 1 else "")
    left_html = "".join(f"<li>{_inline_md(x)}</li>" for x in left_items if x)
    right_html = "".join(f"<li>{_inline_md(x)}</li>" for x in right_items if x)
    return (
        '<div class="compare">'
        f'<div class="compare-col"><h4>{_inline_md(left_h)}</h4><ul>{left_html}</ul></div>'
        f'<div class="compare-col"><h4>{_inline_md(right_h)}</h4><ul>{right_html}</ul></div>'
        "</div>"
    )


def render_matrix2x2_block(code: str) -> str:
    cells = {"TL": ("", ""), "TR": ("", ""), "BL": ("", ""), "BR": ("", "")}
    for ln in code.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = _split_pipe(ln)
        key = (parts[0] if parts else "").upper()
        if key in cells:
            title = parts[1] if len(parts) > 1 else ""
            body = parts[2] if len(parts) > 2 else ""
            cells[key] = (title, body)
    def cell(k: str) -> str:
        t, b = cells[k]
        return (
            f'<div class="mx-cell mx-{k.lower()}">'
            f"<h4>{_inline_md(t)}</h4><p>{_inline_md(b)}</p></div>"
        )
    return (
        '<div class="matrix-2x2">'
        f"{cell('TL')}{cell('TR')}{cell('BL')}{cell('BR')}"
        "</div>"
    )


def render_md_table(header_line: str, sep_line: str, body_lines: list[str]) -> str:
    def cells(line: str) -> list[str]:
        raw = line.strip()
        if raw.startswith("|"):
            raw = raw[1:]
        if raw.endswith("|"):
            raw = raw[:-1]
        return [c.strip() for c in raw.split("|")]

    heads = cells(header_line)
    thead = "<tr>" + "".join(f"<th>{_inline_md(h)}</th>" for h in heads) + "</tr>"
    tbody = []
    for ln in body_lines:
        cols = cells(ln)
        # pad/trim
        while len(cols) < len(heads):
            cols.append("")
        cols = cols[: len(heads)]
        tbody.append("<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in cols) + "</tr>")
    return (
        '<div class="table-wrap"><table>'
        f"<thead>{thead}</thead><tbody>{''.join(tbody)}</tbody>"
        "</table></div>"
    )


def md_to_simple_html_body(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            close_lists()
            lang = line.strip()[3:].strip().split()[0].lower() if line.strip()[3:].strip() else ""
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            code = "\n".join(buf)
            if lang == "mermaid":
                out.append(f'<pre class="mermaid">{html.escape(code)}</pre>')
            elif lang == "fact":
                out.append(render_fact_block(code))
            elif lang == "cards":
                out.append(render_cards_block(code))
            elif lang == "compare":
                out.append(render_compare_block(code))
            elif lang in ("matrix2x2", "matrix"):
                out.append(render_matrix2x2_block(code))
            elif lang == "chart":
                out.append(render_chart_block(code))
            else:
                out.append(
                    f'<pre><code class="language-{html.escape(lang)}">{html.escape(code)}</code></pre>'
                )
            continue

        # GFM table
        if (
            "|" in line
            and i + 1 < len(lines)
            and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1])
        ):
            close_lists()
            header = line
            i += 2
            body = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                body.append(lines[i])
                i += 1
            out.append(render_md_table(header, "", body))
            continue

        if not line.strip():
            close_lists()
            i += 1
            continue

        if line.startswith("### "):
            close_lists()
            out.append(f"<h3>{_inline_md(line[4:].strip())}</h3>")
        elif line.startswith("## "):
            close_lists()
            title = line[3:].strip()
            hid = re.sub(r"\s+", "-", title)[:40]
            out.append(f'<h2 id="{html.escape(hid)}">{_inline_md(title)}</h2>')
        elif line.startswith("# "):
            close_lists()
            out.append(f"<h1>{_inline_md(line[2:].strip())}</h1>")
        elif line.startswith("> "):
            close_lists()
            out.append(f"<blockquote>{_inline_md(line[2:].strip())}</blockquote>")
        elif re.match(r"^[-*] ", line):
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline_md(line[2:].strip())}</li>")
        elif re.match(r"^\d+\.\s", line):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            item = re.sub(r"^\d+\.\s+", "", line).strip()
            out.append(f"<li>{_inline_md(item)}</li>")
        else:
            close_lists()
            out.append(f"<p>{_inline_md(line.strip())}</p>")
        i += 1
    close_lists()
    return "\n".join(out)


def wrap_note_html(title: str, md: str) -> str:
    body = md_to_simple_html_body(md)
    safe_title = html.escape(title or "教學筆記")
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{safe_title}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/styles/github-dark.min.css" />
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/highlight.min.js"></script>
<style>
:root {{
  --bg: #0e1218;
  --bg2: #151b24;
  --panel: #1a222e;
  --line: #2a3544;
  --text: #e7eef7;
  --muted: #93a4b8;
  --accent: #5eb0ff;
  --font: "Iowan Old Style", "Palatino Linotype", "Songti TC", "Noto Serif TC", Georgia, serif;
  --sans: "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  color: var(--text);
  font-family: var(--sans);
  line-height: 1.7;
  background:
    radial-gradient(900px 480px at 10% -10%, #1a335566, transparent 55%),
    radial-gradient(700px 400px at 100% 0%, #14352855, transparent 50%),
    var(--bg);
}}
.wrap {{
  max-width: 820px;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
}}
h1, h2, h3 {{
  font-family: var(--font);
  line-height: 1.35;
  letter-spacing: 0.01em;
}}
h1 {{ font-size: clamp(1.6rem, 4vw, 2.2rem); margin: 0 0 1rem; }}
h2 {{
  font-size: 1.35rem;
  margin: 2.2rem 0 0.8rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid var(--line);
}}
h3 {{ font-size: 1.1rem; margin: 1.4rem 0 0.5rem; color: #c9d7ea; }}
p {{ margin: 0.7rem 0; color: #d5deea; }}
ul, ol {{ padding-left: 1.3rem; }}
li {{ margin: 0.35rem 0; }}
blockquote {{
  margin: 1rem 0;
  padding: 0.75rem 1rem;
  border-left: 3px solid var(--accent);
  background: var(--panel);
  color: var(--muted);
  border-radius: 0 8px 8px 0;
}}
code {{
  font-family: Consolas, "Cascadia Mono", monospace;
  background: #0b0f14;
  padding: 0.1em 0.35em;
  border-radius: 4px;
  font-size: 0.92em;
}}
pre {{
  background: var(--bg2);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 1rem;
  overflow-x: auto;
}}
pre.mermaid {{
  background: #10161f;
  text-align: center;
}}
.meta {{
  color: var(--muted);
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
}}
.fact-card {{
  margin: 1rem 0;
  padding: 1rem 1.1rem;
  border: 1px solid var(--line);
  border-left: 4px solid var(--accent);
  border-radius: 10px;
  background: var(--panel);
}}
.fact-title {{ font-weight: 700; font-size: 1.05rem; margin-bottom: 0.35rem; }}
.fact-lead {{ color: #d7e6f7; font-size: 1.05rem; }}
.fact-body {{ color: var(--muted); margin-top: 0.5rem; font-size: 0.95rem; }}
.cards-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.75rem;
  margin: 1rem 0;
}}
.card-item {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.85rem 0.9rem;
}}
.card-item h4 {{ margin: 0 0 0.4rem; font-size: 1rem; color: #dce8f6; }}
.card-item p {{ margin: 0; color: var(--muted); font-size: 0.92rem; }}
.compare {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  margin: 1rem 0;
}}
.compare-col {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.9rem 1rem;
}}
.compare-col h4 {{ margin: 0 0 0.5rem; }}
.compare-col ul {{ margin: 0; padding-left: 1.1rem; }}
.matrix-2x2 {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 0.65rem;
  margin: 1rem 0;
  aspect-ratio: 1 / 0.85;
}}
.mx-cell {{
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.85rem;
  background: var(--panel);
  overflow: auto;
}}
.mx-cell h4 {{ margin: 0 0 0.35rem; font-size: 0.98rem; }}
.mx-cell p {{ margin: 0; color: var(--muted); font-size: 0.9rem; }}
.mx-tl {{ border-top: 3px solid #5eb0ff; }}
.mx-tr {{ border-top: 3px solid #3ecf8e; }}
.mx-bl {{ border-top: 3px solid #e6b35a; }}
.mx-br {{ border-top: 3px solid #f07178; }}
.table-wrap {{ overflow-x: auto; margin: 1rem 0; }}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}}
th, td {{
  border: 1px solid var(--line);
  padding: 0.55rem 0.65rem;
  text-align: left;
  vertical-align: top;
}}
th {{ background: #1c2836; color: #dce8f6; }}
td {{ background: #141b25; }}
.chart-box {{
  margin: 1.2rem 0;
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
}}
.chart-title {{
  font-weight: 600;
  margin-bottom: 0.65rem;
  color: #dce8f6;
}}
.chart-box canvas {{ max-height: 360px; }}
@media (max-width: 640px) {{
  .wrap {{ padding: 1.25rem 1rem 3rem; }}
  .compare, .matrix-2x2 {{ grid-template-columns: 1fr; aspect-ratio: auto; }}
}}
</style>
</head>
<body data-bs-theme="dark">
<main class="wrap">
  <p class="meta">教學筆記 · 暗色模式 · {html.escape(datetime.now().strftime("%Y-%m-%d %H:%M"))}</p>
  {body}
</main>
<script>
  mermaid.initialize({{ startOnLoad: true, theme: "dark", securityLevel: "loose" }});
  document.querySelectorAll("pre code").forEach((el) => {{
    if (window.hljs) hljs.highlightElement(el);
  }});
  (function() {{
    if (!window.Chart) return;
    const colors = ["#5eb0ff","#3ecf8e","#e6b35a","#f07178","#b48ef0","#5ad0e6"];
    document.querySelectorAll(".chart-box").forEach((box) => {{
      const canvas = box.querySelector("canvas");
      const cfgEl = box.querySelector(".chart-config");
      if (!canvas || !cfgEl) return;
      let cfg;
      try {{ cfg = JSON.parse(cfgEl.textContent); }} catch (e) {{ return; }}
      const type = cfg.type || "bar";
      const datasets = (cfg.datasets || []).map((ds, i) => ({{
        ...ds,
        backgroundColor: ds.backgroundColor || (type === "line" || type === "radar"
          ? colors[i % colors.length] + "66"
          : (Array.isArray(ds.data) ? ds.data.map((_, j) => colors[j % colors.length] + "cc") : colors[i % colors.length] + "cc")),
        borderColor: ds.borderColor || colors[i % colors.length],
        borderWidth: ds.borderWidth || 1.5,
      }}));
      new Chart(canvas, {{
        type,
        data: {{ labels: cfg.labels || [], datasets }},
        options: {{
          responsive: true,
          plugins: {{
            legend: {{ labels: {{ color: "#c9d7ea" }} }},
            title: {{ display: false }},
          }},
          scales: (type === "pie" || type === "doughnut") ? {{}} : {{
            x: {{ ticks: {{ color: "#93a4b8" }}, grid: {{ color: "#2a3544" }} }},
            y: {{ ticks: {{ color: "#93a4b8" }}, grid: {{ color: "#2a3544" }} }},
          }},
        }},
      }});
    }});
  }})();
</script>
</body>
</html>
"""


def resolve_out_dir(user_path: str | None) -> Path:
    """輸出目錄：空白＝預設 notes/；相對路徑相對專案根；不存在則建立。"""
    if not user_path or not str(user_path).strip():
        out = NOTES_DIR
    else:
        p = Path(str(user_path).strip().strip('"'))
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        else:
            p = p.resolve()
        out = p
    out.mkdir(parents=True, exist_ok=True)
    if not out.is_dir():
        raise ValueError(f"無法作為輸出資料夾：{out}")
    return out


def save_note(stem: str, md: str, title: str = "", out_dir: Path | None = None, html_doc: str = "") -> dict:
    dest = out_dir if out_dir is not None else NOTES_DIR
    dest.mkdir(parents=True, exist_ok=True)
    if not title:
        m = re.match(r"^#\s+(.+)$", md, re.M)
        title = m.group(1).strip() if m else stem
    html_path = dest / f"{stem}.html"
    if not html_doc:
        # 後備：舊 Markdown 管線
        html_doc = wrap_note_html(title, md)
    html_path.write_text(html_doc, encoding="utf-8")
    return {
        "stem": stem,
        "title": title,
        "md": "",
        "html": str(html_path),
        "out_dir": str(dest),
    }


def save_note_from_data(
    stem: str,
    note: dict,
    out_dir: Path | None = None,
    *,
    sidebar_html: str = "",
    course_brand: str = "教學講義",
    active_file: str = "",
    books=None,
) -> dict:
    title, md, html_doc = build_note_outputs(
        note,
        sidebar_html=sidebar_html,
        course_brand=course_brand,
        active_file=active_file,
        books=books,
    )
    return save_note(stem, md, title=title, out_dir=out_dir, html_doc=html_doc)


class Handler(BaseHTTPRequestHandler):
    server_version = "NoteGenerator/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code: int, obj: dict | list):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def _file(self, path: Path):
        if not path.is_file():
            self._json(404, {"error": "找不到檔案"})
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix.lower() == ".html":
            ctype = "text/html; charset=utf-8"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._file(INDEX_FILE if INDEX_FILE.is_file() else HTML_FILE)
            return
        if path in ("/new", "/apps/note_generator.html"):
            self._file(HTML_FILE)
            return
        if path == "/apps/ahk-script-generator.html":
            self._file(APPS_DIR / "ahk-script-generator.html")
            return
        if path == "/api/health":
            self._json(
                200,
                {
                    "ok": True,
                    "root": str(ROOT),
                    "output": str(OUTPUT_DIR),
                    "notes": str(NOTES_DIR),
                    "ollama": ollama_base(),
                },
            )
            return
        if path == "/api/models":
            try:
                data = http_json("GET", f"{ollama_base()}/api/tags", timeout=8)
                models = [m.get("name") for m in data.get("models") or [] if m.get("name")]
                self._json(200, {"models": models, "ollama": ollama_base()})
            except Exception as e:
                self._json(
                    503,
                    {
                        "error": f"無法連線 Ollama（{ollama_base()}）。請先啟動 Ollama。",
                        "detail": str(e),
                        "models": [],
                    },
                )
            return
        if path == "/api/list":
            raw_path = (qs.get("path") or ["output"])[0]
            try:
                if raw_path in ("", "output", ".", "./output"):
                    target = OUTPUT_DIR
                else:
                    target = safe_resolve(raw_path)
                items = list_txt(target)
                self._json(200, {"path": str(target), "folders": [], "files": items})
            except Exception as e:
                self._json(400, {"error": str(e), "files": []})
            return
        if path == "/api/notes-tree":
            try:
                skip = {"archive", "__pycache__"}
                folders = []
                if NOTES_DIR.is_dir():
                    for d in sorted(NOTES_DIR.iterdir(), key=lambda p: p.name.lower()):
                        if not d.is_dir() or d.name in skip or d.name.startswith("."):
                            continue
                        files = [
                            {
                                "name": f.name,
                                "rel": f"{d.name}/{f.name}".replace("\\", "/"),
                                "mtime": int(f.stat().st_mtime),
                            }
                            for f in sorted(d.glob("*.html"), key=lambda p: p.name.lower())
                            if f.name.lower() != "index.html"
                        ]
                        folders.append({"name": d.name, "files": files})
                self._json(200, {"notes": str(NOTES_DIR), "folders": folders})
            except Exception as e:
                self._json(400, {"error": str(e), "folders": []})
            return
        if path.startswith("/notes/"):
            rel = urllib.parse.unquote(path[len("/notes/") :])
            fp = (NOTES_DIR / rel).resolve()
            try:
                fp.relative_to(NOTES_DIR.resolve())
            except ValueError:
                self._json(403, {"error": "禁止存取"})
                return
            self._file(fp)
            return
        if path == "/api/open-saved":
            raw_p = (qs.get("path") or [""])[0]
            try:
                fp = Path(urllib.parse.unquote(raw_p)).resolve()
                if not fp.is_file() or fp.suffix.lower() not in (".html", ".md", ".txt"):
                    self._json(404, {"error": "找不到可開啟的檔案"})
                    return
                self._file(fp)
            except Exception as e:
                self._json(400, {"error": str(e)})
            return

        fp = (ROOT / path.lstrip("/")).resolve()
        try:
            fp.relative_to(ROOT)
        except ValueError:
            self._json(403, {"error": "禁止存取"})
            return
        if fp.is_file():
            self._file(fp)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "JSON 無效"})
            return

        try:
            if path == "/api/read":
                p = safe_resolve(body.get("path") or "")
                if not p.is_file():
                    self._json(400, {"error": f"不是檔案：{p}"})
                    return
                text = read_text_file(p)
                truncated = False
                if len(text) > MAX_CHARS:
                    text = text[:MAX_CHARS]
                    truncated = True
                self._json(
                    200,
                    {
                        "path": str(p),
                        "name": p.name,
                        "content": text,
                        "truncated": truncated,
                        "chars": len(text),
                    },
                )
                return

            if path == "/api/ensure-out":
                out = resolve_out_dir(body.get("out_dir"))
                self._json(200, {"out_dir": str(out)})
                return

            if path == "/api/outline":
                model = (body.get("model") or "").strip()
                content = prepare_content(body.get("content") or "")
                if not model:
                    self._json(400, {"error": "請選擇模型"})
                    return
                if not content:
                    self._json(400, {"error": "素材空白"})
                    return
                title = (body.get("title") or "").strip()
                style = (body.get("style") or "詳細").strip()
                outline = call_ollama_outline(model, title, content, style)
                self._json(
                    200,
                    {
                        "outline": outline,
                        "chapter_count": len(outline.get("chapters") or []),
                    },
                )
                return

            if path == "/api/chapter":
                model = (body.get("model") or "").strip()
                content = prepare_content(body.get("content") or "")
                chapter_spec = body.get("chapter") or {}
                if not model:
                    self._json(400, {"error": "請選擇模型"})
                    return
                if not content:
                    self._json(400, {"error": "素材空白"})
                    return
                if not isinstance(chapter_spec, dict):
                    self._json(400, {"error": "chapter 必須是物件"})
                    return
                style = (body.get("style") or "詳細").strip()
                note_title = (body.get("note_title") or body.get("title") or "").strip()
                try:
                    index = max(1, int(body.get("index") or 1))
                except (TypeError, ValueError):
                    index = 1
                try:
                    total = max(index, int(body.get("total") or index))
                except (TypeError, ValueError):
                    total = index
                chapter = call_ollama_chapter(
                    model, note_title, content, chapter_spec, style, index, total
                )
                self._json(200, {"chapter": chapter, "index": index, "total": total})
                return

            if path == "/api/assemble":
                outline = body.get("outline") or {}
                chapters = body.get("chapters") or []
                if not isinstance(outline, dict):
                    self._json(400, {"error": "outline 必須是物件"})
                    return
                if not isinstance(chapters, list) or not chapters:
                    self._json(400, {"error": "chapters 不可空白"})
                    return
                title = (body.get("title") or "").strip()
                save = bool(body.get("save", True))
                out_dir = resolve_out_dir(body.get("out_dir"))
                raw_content = body.get("content") or ""
                note = assemble_note(
                    outline,
                    chapters,
                    fallback_title=title,
                    content=raw_content,
                    source_url=extract_source_url(raw_content),
                )
                note_title, md, html_doc = build_note_outputs(note)
                result: dict = {
                    "markdown": md,
                    "html": html_doc,
                    "note": note,
                    "out_dir": str(out_dir),
                    "mode": "multipass",
                }
                if save:
                    stem = stem_from_path(Path(title or note_title or "note"))
                    if body.get("source_path"):
                        stem = stem_from_path(Path(body["source_path"]))
                    result["saved"] = save_note(
                        stem, md, title=note_title, out_dir=out_dir, html_doc=html_doc
                    )
                self._json(200, result)
                return

            if path == "/api/generate":
                model = (body.get("model") or "").strip()
                if not model:
                    self._json(400, {"error": "請選擇模型"})
                    return
                content = (body.get("content") or "").strip()
                if not content:
                    self._json(400, {"error": "素材空白"})
                    return
                title = (body.get("title") or "").strip()
                style = (body.get("style") or "詳細").strip()
                save = bool(body.get("save", True))
                out_dir = resolve_out_dir(body.get("out_dir"))
                # 伺服器端一氣呵成（batch 用）；前端建議走 outline→chapter→assemble
                note = call_ollama_note(model, title, content, style)
                note_title, md, html_doc = build_note_outputs(note)
                result: dict = {
                    "markdown": md,
                    "html": html_doc,
                    "note": note,
                    "out_dir": str(out_dir),
                    "mode": "multipass",
                }
                if save:
                    stem = stem_from_path(Path(title or note_title or "note"))
                    if body.get("source_path"):
                        stem = stem_from_path(Path(body["source_path"]))
                    result["saved"] = save_note(
                        stem, md, title=note_title, out_dir=out_dir, html_doc=html_doc
                    )
                self._json(200, result)
                return

            if path == "/api/generate-batch":
                model = (body.get("model") or "").strip()
                style = (body.get("style") or "詳細").strip()
                paths = body.get("paths") or []
                # separate＝一檔一篇；merge＝勾選檔合併成一篇
                mode = (body.get("mode") or "separate").strip().lower()
                if mode not in ("separate", "merge"):
                    mode = "separate"
                out_dir = resolve_out_dir(body.get("out_dir"))
                if not model:
                    self._json(400, {"error": "請選擇模型"})
                    return
                if not paths:
                    self._json(400, {"error": "未選取檔案"})
                    return

                if mode == "merge":
                    parts = []
                    names = []
                    try:
                        for raw_p in paths:
                            p = safe_resolve(raw_p)
                            text = read_text_file(p)
                            names.append(p.stem)
                            parts.append(f"===== 檔案：{p.name} =====\n{text.strip()}")
                        combined = "\n\n".join(parts)
                        if len(combined) > MAX_CHARS:
                            combined = combined[:MAX_CHARS] + "\n\n…（合併素材過長，已截斷）"
                        title = (body.get("title") or "").strip() or (
                            f"合併筆記（{len(names)}篇）"
                        )
                        note = call_ollama_note(model, title, combined, style)
                        note_title, md, html_doc = build_note_outputs(note)
                        stem = stem_from_path(Path(title))
                        saved = save_note(
                            stem, md, title=note_title, out_dir=out_dir, html_doc=html_doc
                        )
                        self._json(
                            200,
                            {
                                "mode": "merge",
                                "out_dir": str(out_dir),
                                "results": [
                                    {
                                        "ok": True,
                                        "path": ", ".join(names),
                                        "saved": saved,
                                        "markdown": md,
                                        "html": html_doc,
                                    }
                                ],
                            },
                        )
                    except Exception as e:
                        self._json(
                            500,
                            {
                                "mode": "merge",
                                "error": str(e),
                                "results": [{"ok": False, "error": str(e)}],
                            },
                        )
                    return

                results = []
                for raw_p in paths:
                    try:
                        p = safe_resolve(raw_p)
                        text = read_text_file(p)
                        title = p.stem
                        note = call_ollama_note(model, title, text, style)
                        note_title, md, html_doc = build_note_outputs(note)
                        saved = save_note(
                            stem_from_path(p),
                            md,
                            title=note_title,
                            out_dir=out_dir,
                            html_doc=html_doc,
                        )
                        results.append(
                            {
                                "ok": True,
                                "path": str(p),
                                "saved": saved,
                                "markdown": md,
                                "html": html_doc,
                            }
                        )
                    except Exception as e:
                        results.append({"ok": False, "path": str(raw_p), "error": str(e)})
                self._json(
                    200, {"mode": "separate", "results": results, "out_dir": str(out_dir)}
                )
                return

            self._json(404, {"error": "not found"})
        except Exception as e:
            traceback.print_exc()
            self._json(500, {"error": str(e)})


def main():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not HTML_FILE.is_file():
        print(f"找不到筆記產生器：{HTML_FILE}", file=sys.stderr)
        sys.exit(1)
    if not INDEX_FILE.is_file():
        print(f"警告：找不到入口頁 {INDEX_FILE}，/ 將導向筆記產生器", file=sys.stderr)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"筆記工具箱：{url}")
    print(f"新增筆記：{url}apps/note_generator.html")
    print(f"瀏覽筆記：{url}notes/")
    print(f"Ollama：{ollama_base()}")
    print(f"output：{OUTPUT_DIR}")
    print(f"notes：{NOTES_DIR}")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()

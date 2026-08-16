# -*- coding: utf-8 -*-
"""把筆記 JSON 結構渲染成 Bootstrap 暗色 HTML。"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any

from note_viz_bundle import (
    BOOT_SCRIPT,
    EXTRA_CSS,
    HEAD_LINKS,
    SCRIPT_TAGS,
    payload_from_tax_note,
    render_viz_tab,
)
from note_shell import (
    build_course_sidebar,
    chapters_from_note,
    wrap_with_sidebar,
)
from note_narration import NARRATION_CSS, NARRATION_JS

VISUAL_TYPES_DOC = """visual.type 只能是以下之一：
- fact：items 一筆 {title,text}
- cards：items 多筆並列卡片
- compare：{ "leftTitle":"行號", "rightTitle":"公司", "rows":[{"left":"…","right":"…"}] }
- matrix2x2：{ "tl":{"title":"","text":""}, "tr":{…}, "bl":{…}, "br":{…} }
- mermaid：{ "code": "flowchart TD\\n  A-->B" }  （不要包 ```）
- chart：{ "type":"bar", "title":"…", "labels":["甲","乙"], "datasets":[{"label":"分","data":[3,7]}] }
- table：{ "headers":["維度","甲","乙"], "rows":[["成本","低","高"]] }
- none：無視覺"""

SYSTEM_PROMPT_JSON = """你是繁體中文教學筆記編輯。你的任務是把素材整理成「可直接用 HTML 呈現」的結構化 JSON。

【只輸出一個 JSON 物件】不要 Markdown、不要前言、不要用 ``` 包起來。

JSON 格式（欄位名固定）：
{
  "title": "筆記標題",
  "strategy": ["主論法：…", "視覺：cards／compare／…"],
  "goals": ["學習目標1", "學習目標2"],
  "summary": ["重點1", "重點2"],
  "chapters": [
    {
      "title": "章名",
      "body": "2～6 句說明文字，不要放程式碼區塊",
      "visual": {
        "type": "cards",
        "items": [
          {"title": "短標題", "text": "說明"},
          {"title": "短標題", "text": "說明"}
        ]
      },
      "notes": ["注意事項"],
      "warning": "可選警告文字，沒有就空字串"
    }
  ]
}

""" + VISUAL_TYPES_DOC + """

規則：
1. 依素材判斷每章最適 visual，不要每章都 mermaid。
2. 並列→cards；對立→compare；因果→mermaid；量化→chart 或 table。
3. 不虛構素材沒有的事實；不足寫「（素材未提及）」。
4. 全程繁體中文。chapters 至少 2 章。
"""

SYSTEM_PROMPT_OUTLINE = """你是台灣繁體中文教學筆記企劃。只做「大綱」，不要寫正文、不要寫 visual 內容。

【只輸出一個 JSON 物件】不要 Markdown、不要前言、不要用 ``` 包起來。
【語言】title、strategy、goals、summary、chapters.title、chapters.focus 必須全部是繁體中文。禁止英文段落。

JSON 格式：
{
  "title": "筆記標題",
  "strategy": ["主論法：比較三種經營型態", "視覺：cards／compare"],
  "goals": ["能判斷何時要登記", "能分辨小規模／行號／公司"],
  "summary": ["重點一句", "重點一句", "重點一句"],
  "chapters": [
    {
      "title": "具體章名（依素材）",
      "focus": "本章要講清楚的 1～3 個重點（繁中句子）",
      "visualHint": "cards"
    }
  ]
}

visualHint 只能是：fact / cards / compare / matrix2x2 / mermaid / chart / table / none
規則：
1. 依素材自主分主題；章名要具體，禁止用「核心概念」「重點整理」這種空泛標題。
2. 詳細風格：3～5 章；精簡風格：2～3 章。
3. summary 至少 3 條短句，每條一句繁中。
4. 不虛構素材沒有的主題。
"""

SYSTEM_PROMPT_CHAPTER = """你是台灣繁體中文教學筆記作者。任務是把口播素材「整理成有邏輯架構」的單章筆記，不是剪貼逐字稿。

【只輸出一個 JSON 物件】不要 Markdown、不要前言、不要用 ``` 包起來。
【語言】全部繁體中文。
【寫作目標】讓讀者看完就懂「是什麼／怎麼判斷／要注意什麼」。

JSON 格式：
{
  "title": "章名",
  "body": "重點：…\\n判斷或比較：…\\n注意：…",
  "visual": { "type": "cards", "items": [{"title":"有意義標題","text":"一句說明"}] },
  "notes": ["可執行的提醒"],
  "warning": ""
}

body 寫作規範：
1. 用 4～8 句「改寫後」的說明，可換行分小段；禁止只重複相近句子。
2. 必須包含：定義或結論、判斷條件或比較、至少 1 個實務注意。
3. 禁止輸出意義不明的碎片（例如連續出現幾乎相同的「開發票的公司行號」句子）。
4. 禁止把問句當結論卻不回答。

visual 規範：
1. items.title 必須是有意義詞（如「地址限制」「資本額」「營收門檻」），禁止「要點1」「要點2」。
2. 每張卡的 text 要彼此不同；若湊不出差異，改 type 為 none。
3. matrix2x2／compare 若填不滿就不要用。

""" + VISUAL_TYPES_DOC + """

其他規則：
1. 只寫指定章。
2. 不虛構素材沒有的事實；不足寫「（素材未提及）」。
"""


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError("模型未回傳 JSON 物件")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON 根必須是物件")
    return data


def _esc(s: Any) -> str:
    return html.escape("" if s is None else str(s))


def _list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


_CHART_I = 0


def render_visual(visual: Any) -> str:
    global _CHART_I
    if not visual or not isinstance(visual, dict):
        return ""
    vtype = str(visual.get("type") or "none").lower().strip()
    if vtype in ("", "none", "null"):
        return ""

    if vtype == "fact":
        items = _list(visual.get("items"))
        if not items and (visual.get("title") or visual.get("text")):
            items = [{"title": visual.get("title"), "text": visual.get("text")}]
        it = items[0] if items else {}
        if isinstance(it, str):
            title, text = "重點", it
        else:
            title = it.get("title") or "重點"
            text = it.get("text") or it.get("body") or ""
        return (
            f'<div class="callout callout-fact mb-3">'
            f'<div class="callout-label">✦ {_esc(title)}</div>'
            f'<div class="callout-body">{_esc(text)}</div></div>'
        )

    if vtype == "cards":
        items = _list(visual.get("items"))
        accents = ("accent-cyan", "accent-mint", "accent-amber", "accent-coral", "accent-violet", "accent-sky")
        cols = []
        for i, it in enumerate(items):
            if isinstance(it, str):
                t, x = "重點", it
            else:
                t = it.get("title") or "重點"
                x = it.get("text") or it.get("body") or ""
            acc = accents[i % len(accents)]
            cols.append(
                f'<div class="col-md-4"><div class="card h-100 tip-card {acc}">'
                f'<div class="card-body"><h3 class="h6 card-title">{_esc(t)}</h3>'
                f'<p class="card-text small mb-0">{_esc(x)}</p>'
                f"</div></div></div>"
            )
        if not cols:
            return ""
        return f'<div class="row g-3 mb-3">{"".join(cols)}</div>'

    if vtype == "compare":
        left_t = visual.get("leftTitle") or visual.get("left") or "A"
        right_t = visual.get("rightTitle") or visual.get("right") or "B"
        rows = _list(visual.get("rows") or visual.get("items"))
        left_li, right_li = [], []
        for r in rows:
            if isinstance(r, dict):
                if r.get("left"):
                    left_li.append(f"<li>{_esc(r.get('left'))}</li>")
                if r.get("right"):
                    right_li.append(f"<li>{_esc(r.get('right'))}</li>")
            elif isinstance(r, str) and "｜" in r:
                a, b = r.split("｜", 1)
                left_li.append(f"<li>{_esc(a)}</li>")
                right_li.append(f"<li>{_esc(b)}</li>")
        if not left_li and not right_li:
            return ""
        return (
            '<div class="row g-3 mb-3">'
            f'<div class="col-md-6"><div class="card h-100 tip-card accent-cyan">'
            f'<div class="card-header">{_esc(left_t)}</div>'
            f'<div class="card-body"><ul class="mb-0">{"".join(left_li)}</ul></div></div></div>'
            f'<div class="col-md-6"><div class="card h-100 tip-card accent-mint">'
            f'<div class="card-header">{_esc(right_t)}</div>'
            f'<div class="card-body"><ul class="mb-0">{"".join(right_li)}</ul></div></div></div>'
            "</div>"
        )

    if vtype == "matrix2x2":
        def cell_data(key: str) -> tuple[str, str]:
            c = visual.get(key) or visual.get(key.upper()) or {}
            if isinstance(c, str):
                return key.upper(), c.strip()
            if not isinstance(c, dict):
                return "", ""
            t = str(c.get("title") or "").strip()
            x = str(c.get("text") or c.get("body") or "").strip()
            return t, x

        cells = [cell_data(k) for k in ("tl", "tr", "bl", "br")]
        # 全空或只剩 TL/TR/BL/BR 佔位 → 不渲染
        if not any(t or x for t, x in cells):
            return ""
        if all((not x) and (not t or t.upper() == k.upper()) for k, (t, x) in zip(("tl", "tr", "bl", "br"), cells)):
            return ""

        def cell(key: str, accent: str) -> str:
            t, x = cell_data(key)
            if not t:
                t = key.upper()
            return (
                f'<div class="col-6"><div class="card h-100 tip-card {accent}">'
                f'<div class="card-body"><h3 class="h6">{_esc(t)}</h3>'
                f'<p class="small mb-0">{_esc(x)}</p></div></div></div>'
            )
        return (
            '<div class="row g-2 mb-3">'
            f'{cell("tl", "accent-cyan")}{cell("tr", "accent-mint")}'
            f'{cell("bl", "accent-amber")}{cell("br", "accent-coral")}'
            "</div>"
        )

    if vtype == "mermaid":
        code = visual.get("code") or visual.get("mermaid") or ""
        code = str(code).strip()
        if not code:
            return ""
        return f'<pre class="mermaid p-3 rounded bg-black mb-3">{_esc(code)}</pre>'

    if vtype == "chart":
        chart_kind = visual.get("chartType") or visual.get("chart_type") or "bar"
        if str(chart_kind).lower() == "chart":
            chart_kind = "bar"
        cfg = {
            "type": chart_kind,
            "title": visual.get("title") or "",
            "labels": visual.get("labels") or [],
            "datasets": visual.get("datasets") or [],
        }
        _CHART_I += 1
        cid = f"c{_CHART_I}"
        payload = html.escape(json.dumps(cfg, ensure_ascii=False))
        title = _esc(cfg.get("title") or "")
        title_html = f'<h3 class="h6">{title}</h3>' if title else ""
        return (
            f'<div class="card mb-3"><div class="card-body chart-box">'
            f"{title_html}"
            f'<canvas id="{cid}" height="140"></canvas>'
            f'<script type="application/json" class="chart-config">{payload}</script>'
            f"</div></div>"
        )

    if vtype == "table":
        headers = _list(visual.get("headers"))
        rows = _list(visual.get("rows"))
        thead = "".join(f"<th>{_esc(h)}</th>" for h in headers)
        body = []
        for row in rows:
            cells = row if isinstance(row, list) else [row]
            body.append("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in cells) + "</tr>")
        return (
            '<div class="table-responsive mb-3"><table class="table table-dark table-striped table-bordered">'
            f"<thead><tr>{thead}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
        )

    return ""


def _render_body_paragraph(para: str) -> str:
    """依開頭關鍵字把段落做成彩色提醒塊。"""
    p = para.strip()
    if not p:
        return ""
    rules = (
        ("重點", "callout-key", "重點"),
        ("判斷或比較", "callout-judge", "判斷／比較"),
        ("判斷或整理", "callout-judge", "判斷／整理"),
        ("判斷", "callout-judge", "判斷"),
        ("比較", "callout-judge", "比較"),
        ("注意", "callout-note", "注意"),
        ("提醒", "callout-note", "提醒"),
        ("警告", "callout-warn", "警告"),
        ("詳解", "callout-fact", "詳解"),
        ("案例", "callout-judge", "案例"),
    )
    for prefix, cls, label in rules:
        if p.startswith(prefix):
            rest = p[len(prefix) :].lstrip("：:．. ")
            return (
                f'<div class="callout {cls} mb-3">'
                f'<div class="callout-label">{_esc(label)}</div>'
                f'<div class="callout-body">{_esc(rest or p)}</div></div>'
            )
    return f'<p class="lh-lg body-p">{_esc(p)}</p>'


def _chip_row(items: list[str], kind: str = "tag") -> str:
    if not items:
        return ""
    accents = ("chip-cyan", "chip-mint", "chip-amber", "chip-coral", "chip-violet", "chip-sky")
    wrap = "chip-row" if kind == "tag" else "summary-chips"
    bits = [f'<div class="{wrap}">']
    for i, x in enumerate(items):
        s = str(x).strip()
        if not s:
            continue
        if kind == "tag":
            bits.append(f'<span class="tag-chip {accents[i % len(accents)]}">{_esc(s)}</span>')
        else:
            bits.append(f'<div class="summary-chip {accents[i % len(accents)]}">{_esc(s)}</div>')
    bits.append("</div>")
    return "\n".join(bits)


def _derive_milestones(note: dict[str, Any]) -> list[dict[str, Any]]:
    ms = note.get("milestones")
    if isinstance(ms, list) and ms:
        out = []
        for i, m in enumerate(ms, 1):
            if isinstance(m, str):
                out.append({"label": m, "desc": "", "chapter": i})
            elif isinstance(m, dict):
                out.append(
                    {
                        "label": str(m.get("label") or m.get("title") or f"里程碑 {i}"),
                        "desc": str(m.get("desc") or m.get("text") or ""),
                        "chapter": int(m.get("chapter") or i),
                    }
                )
        return out
    chapters = [c for c in _list(note.get("chapters")) if isinstance(c, dict)]
    out = []
    for i, ch in enumerate(chapters, 1):
        label = str(ch.get("milestone") or ch.get("title") or f"第 {i} 站").strip()
        # 取 body 第一句當 desc
        body = str(ch.get("body") or "")
        first = re.split(r"[\n。]", body)[0].strip()
        first = re.sub(r"^(重點|判斷或比較|注意)[:：]\s*", "", first)
        out.append({"label": label[:28], "desc": first[:80], "chapter": i})
    return out


def _render_chapter_block(ch: dict[str, Any], index: int) -> str:
    parts: list[str] = []
    mid = ch.get("milestone") or f"第 {index} 站"
    parts.append(f'<article class="chapter-block" id="ch-{index}">')
    parts.append('<div class="chapter-head">')
    parts.append(f'<span class="milestone-badge">{_esc(mid)}</span>')
    parts.append(
        f"<h2 class='chapter-title'><span class='chapter-num'>{index}</span>"
        f"{_esc(ch.get('title') or f'第{index}章')}</h2>"
    )
    parts.append("</div>")

    tags = [str(x) for x in _list(ch.get("tags")) if str(x).strip()]
    if tags:
        parts.append(_chip_row(tags, kind="tag"))

    narration = str(ch.get("narration") or ch.get("audio_script") or "").strip()
    if not narration:
        from note_narration import compose_from_chapter

        narration = compose_from_chapter(ch)
    if narration:
        from note_narration import render_narration_panel

        parts.append(
            render_narration_panel(
                narration, uid=f"ch-{index}", title="語音講解（適合用聽的）"
            )
        )

    # 詳盡 sections（可選）
    for sec in _list(ch.get("sections")):
        if not isinstance(sec, dict):
            continue
        heading = str(sec.get("heading") or sec.get("title") or "").strip()
        if heading:
            parts.append(f'<h3 class="subhead">{_esc(heading)}</h3>')
        for para in _list(sec.get("paras") or sec.get("paragraphs")):
            p = str(para).strip()
            if p:
                parts.append(_render_body_paragraph(p) if re.match(r"^(重點|判斷|比較|注意|提醒|警告|詳解|案例)", p) else f'<p class="lh-lg body-p">{_esc(p)}</p>')
        bullets = [str(b).strip() for b in _list(sec.get("bullets")) if str(b).strip()]
        if bullets:
            parts.append('<ul class="lecture-list">')
            parts.extend(f"<li>{_esc(b)}</li>" for b in bullets)
            parts.append("</ul>")

    body = ch.get("body") or ch.get("text") or ""
    if body:
        for para in str(body).split("\n"):
            html_p = _render_body_paragraph(para)
            if html_p:
                parts.append(html_p)

    key_points = [str(x).strip() for x in _list(ch.get("key_points")) if str(x).strip()]
    if key_points:
        parts.append('<div class="kp-box"><div class="callout-label">關鍵知識點</div>')
        parts.append(_chip_row(key_points, kind="tag"))
        parts.append("</div>")

    parts.append(render_visual(ch.get("visual")))

    checklist = [str(x).strip() for x in _list(ch.get("checklist")) if str(x).strip()]
    if checklist:
        parts.append('<div class="callout callout-tip mb-3"><div class="callout-label">學習檢核</div><ul class="mb-0 check-list">')
        parts.extend(f"<li>{_esc(c)}</li>" for c in checklist)
        parts.append("</ul></div>")

    notes = _list(ch.get("notes"))
    if notes:
        parts.append(
            '<div class="callout callout-tip mb-3">'
            '<div class="callout-label">提醒／小結</div><ul class="mb-0 callout-list">'
        )
        parts.extend(f"<li>{_esc(n)}</li>" for n in notes)
        parts.append("</ul></div>")
    warning = (ch.get("warning") or "").strip()
    if warning:
        parts.append(
            f'<div class="callout callout-warn mb-3">'
            f'<div class="callout-label">警告</div>'
            f'<div class="callout-body">{_esc(warning)}</div></div>'
        )
    parts.append("</article>")
    return "\n".join(parts)


def _normalize_quiz_items(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, it in enumerate(_list(raw), 1):
        if isinstance(it, str) and it.strip():
            out.append(
                {
                    "kind": "knowledge",
                    "topic": f"題 {i}",
                    "question": it.strip(),
                    "answer": "",
                    "explain": "",
                }
            )
            continue
        if not isinstance(it, dict):
            continue
        kind = str(it.get("kind") or "knowledge").strip().lower()
        if kind in ("data", "數字", "關鍵數據", "數據", "辨別"):
            kind = "data"
        else:
            kind = "knowledge"
        q = str(it.get("question") or it.get("q") or "").strip()
        a = str(it.get("answer") or it.get("a") or "").strip()
        if not q or not a:
            continue
        out.append(
            {
                "kind": kind,
                "topic": str(it.get("topic") or it.get("tag") or ("關鍵數據" if kind == "data" else "知識點")).strip(),
                "question": q,
                "answer": a,
                "explain": str(it.get("explain") or it.get("hint") or "").strip(),
            }
        )
    return out


def _derive_quiz(note: dict[str, Any]) -> dict[str, Any]:
    """若 JSON 已有 quiz 則正規化；否則依 key_points／警告數字自動出題。"""
    quiz = note.get("quiz")
    if isinstance(quiz, dict):
        items = _normalize_quiz_items(quiz.get("items") or quiz.get("questions"))
        if items:
            return {
                "intro": str(
                    quiz.get("intro")
                    or "完成講義後自我檢核。答案預設以密碼樣式隱藏，點「顯示答案」才揭曉。"
                ).strip(),
                "items": items,
            }
    items: list[dict[str, Any]] = []
    chapters = [c for c in _list(note.get("chapters")) if isinstance(c, dict)]
    for i, ch in enumerate(chapters, 1):
        title = str(ch.get("title") or f"第 {i} 章").strip()
        for kp in _list(ch.get("key_points")):
            s = str(kp).strip()
            if not s:
                continue
            items.append(
                {
                    "kind": "knowledge",
                    "topic": title[:18],
                    "question": f"關於「{title}」，下列關鍵知識點的正確表述是？",
                    "answer": s,
                    "explain": f"對應第 {i} 章關鍵知識點。",
                }
            )
        # 從 warning / fact 抽數字辨別
        blob = " ".join(
            [
                str(ch.get("warning") or ""),
                str(ch.get("body") or ""),
                " ".join(str(n) for n in _list(ch.get("notes"))),
            ]
        )
        visual = ch.get("visual") if isinstance(ch.get("visual"), dict) else {}
        for it in _list(visual.get("items")):
            if isinstance(it, dict):
                blob += " " + str(it.get("title") or "") + " " + str(it.get("text") or "")
        for m in re.finditer(
            r"([^\n。；]{0,24}?)(\d+\s*[～~\-－至到]\s*\d+\s*萬(?:元)?|\d+\s*%|\d+\s*萬(?:元)?|1\s*[～~]\s*5\s*萬)",
            blob,
        ):
            ctx = (m.group(1) or "").strip(" ：:，,")
            num = m.group(2).strip()
            topic = (ctx[-12:] if ctx else title) or "關鍵數據"
            items.append(
                {
                    "kind": "data",
                    "topic": topic[:18],
                    "question": f"講義提到的關鍵數據／區間是什麼？（提示：{topic}）",
                    "answer": num,
                    "explain": f"出自第 {i} 章「{title}」相關敘述。",
                }
            )
    # 去重（同答案只留一題）
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for it in items:
        key = it["answer"] + "|" + it["question"][:40]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    # 知識點與數據交錯，最多 14 題
    know = [x for x in uniq if x["kind"] == "knowledge"]
    data = [x for x in uniq if x["kind"] == "data"]
    merged: list[dict[str, Any]] = []
    while know or data:
        if know:
            merged.append(know.pop(0))
        if data:
            merged.append(data.pop(0))
        if len(merged) >= 14:
            break
    return {
        "intro": "完成講義後自我檢核。答案預設以密碼樣式隱藏，點「顯示答案」才揭曉。涵蓋知識點與關鍵數據辨別。",
        "items": merged,
    }


def _render_quiz_panel(quiz: dict[str, Any]) -> str:
    items = _list(quiz.get("items"))
    if not items:
        return '<p class="text-secondary">本單元尚無課後測驗。</p>'
    parts: list[str] = []
    intro = str(quiz.get("intro") or "").strip()
    if intro:
        parts.append(f'<p class="quiz-intro">{_esc(intro)}</p>')
    parts.append('<div class="quiz-toolbar">')
    parts.append(
        '<button type="button" class="btn btn-sm quiz-tool-btn" id="quiz-reveal-all">全部顯示答案</button>'
        '<button type="button" class="btn btn-sm quiz-tool-btn" id="quiz-hide-all">全部隱藏答案</button>'
    )
    parts.append(
        f'<span class="quiz-count">共 {len(items)} 題'
        f'・知識點 {sum(1 for x in items if str(x.get("kind"))=="knowledge")}・'
        f'關鍵數據 {sum(1 for x in items if str(x.get("kind"))=="data")}</span>'
    )
    parts.append("</div>")
    parts.append('<ol class="quiz-list">')
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        kind = str(it.get("kind") or "knowledge")
        kind_label = "關鍵數據" if kind == "data" else "知識點"
        kind_cls = "quiz-kind-data" if kind == "data" else "quiz-kind-know"
        parts.append(f'<li class="quiz-item" data-quiz-item>')
        parts.append('<div class="quiz-item-head">')
        parts.append(f'<span class="quiz-no">Q{i}</span>')
        parts.append(f'<span class="quiz-kind {kind_cls}">{kind_label}</span>')
        parts.append(f'<span class="quiz-topic">{_esc(it.get("topic") or "")}</span>')
        parts.append("</div>")
        parts.append(f'<p class="quiz-q">{_esc(it.get("question") or "")}</p>')
        parts.append('<div class="quiz-answer-row">')
        parts.append(
            '<button type="button" class="quiz-reveal-btn" aria-pressed="false" data-reveal-answer>'
            "顯示答案</button>"
        )
        parts.append('<div class="quiz-secret-box is-masked" data-secret-box>')
        parts.append(
            f'<span class="quiz-secret-text" data-secret-text>{_esc(it.get("answer") or "")}</span>'
        )
        parts.append("</div></div>")
        explain = str(it.get("explain") or "").strip()
        if explain:
            parts.append(
                f'<div class="quiz-explain is-hidden" data-quiz-explain>'
                f'<span class="quiz-explain-label">解析</span>{_esc(explain)}</div>'
            )
        parts.append("</li>")
    parts.append("</ol>")
    return "\n".join(parts)


def render_note_body(note: dict[str, Any]) -> str:
    title = note.get("title") or "教學講義"
    source_url = str(note.get("source_url") or "").strip()
    badge = str(note.get("badge") or "").strip()
    tags = [str(x).strip() for x in _list(note.get("tags")) if str(x).strip()]
    milestones = _derive_milestones(note)
    chapters = [c for c in _list(note.get("chapters")) if isinstance(c, dict)]
    goals = _list(note.get("goals"))
    summary = _list(note.get("summary"))
    strategy = _list(note.get("strategy"))
    quiz = _derive_quiz(note)

    parts: list[str] = []

    # Hero
    parts.append('<header class="lecture-hero">')
    if badge:
        parts.append(f'<span class="unit-badge">{_esc(badge)}</span>')
    if source_url and source_url.startswith(("http://", "https://")):
        parts.append(
            f"<h1 class='note-title mb-2'>"
            f"<a class='title-link' href='{_esc(source_url)}' "
            f"target='_blank' rel='noopener noreferrer'>{_esc(title)}</a></h1>"
        )
        parts.append(
            f"<p class='source-line mb-3'><a href='{_esc(source_url)}' target='_blank' "
            f"rel='noopener noreferrer'>來源連結 ↗</a></p>"
        )
    else:
        parts.append(f"<h1 class='note-title mb-3'>{_esc(title)}</h1>")
    if tags:
        parts.append(_chip_row(tags, kind="tag"))
    parts.append("</header>")

    # Milestone track
    if milestones:
        parts.append('<section class="milestone-wrap" aria-label="學習里程碑">')
        parts.append('<div class="section-kicker">學習路徑</div>')
        parts.append('<h2 class="section-title">里程碑</h2>')
        parts.append('<ol class="milestone-track">')
        for i, m in enumerate(milestones, 1):
            ch_i = int(m.get("chapter") or i)
            parts.append(
                f'<li class="milestone-item">'
                f'<a class="milestone-link" href="#ch-{ch_i}">'
                f'<span class="ms-dot">{i}</span>'
                f'<span class="ms-label">{_esc(m.get("label") or f"站 {i}")}</span>'
                f'<span class="ms-desc">{_esc(m.get("desc") or "")}</span>'
                f"</a></li>"
            )
        parts.append("</ol></section>")

    # Tabs
    parts.append('<div class="lecture-tabs">')
    parts.append(
        '<ul class="nav nav-pills lecture-nav" role="tablist">'
        '<li class="nav-item" role="presentation">'
        '<button class="nav-link active" id="tab-overview-btn" data-bs-toggle="pill" '
        'data-bs-target="#tab-overview" type="button" role="tab">總覽</button></li>'
        '<li class="nav-item" role="presentation">'
        '<button class="nav-link" id="tab-charts-btn" data-bs-toggle="pill" '
        'data-bs-target="#tab-charts" type="button" role="tab">圖表</button></li>'
        '<li class="nav-item" role="presentation">'
        '<button class="nav-link" id="tab-path-btn" data-bs-toggle="pill" '
        'data-bs-target="#tab-path" type="button" role="tab">學習路徑</button></li>'
        '<li class="nav-item" role="presentation">'
        '<button class="nav-link" id="tab-lecture-btn" data-bs-toggle="pill" '
        'data-bs-target="#tab-lecture" type="button" role="tab">章節講義</button></li>'
        '<li class="nav-item" role="presentation">'
        '<button class="nav-link" id="tab-quick-btn" data-bs-toggle="pill" '
        'data-bs-target="#tab-quick" type="button" role="tab">速查卡片</button></li>'
        '<li class="nav-item" role="presentation">'
        '<button class="nav-link" id="tab-quiz-btn" data-bs-toggle="pill" '
        'data-bs-target="#tab-quiz" type="button" role="tab">課後測驗</button></li>'
        "</ul>"
    )
    parts.append('<div class="tab-content lecture-tab-content">')

    # Tab: 總覽
    parts.append('<div class="tab-pane fade show active" id="tab-overview" role="tabpanel">')
    if goals:
        parts.append('<section class="mb-4 panel panel-mint"><h2 class="section-title">學習目標</h2><ul class="mb-0">')
        parts.extend(f"<li>{_esc(x)}</li>" for x in goals)
        parts.append("</ul></section>")
    if summary:
        parts.append('<section class="mb-4"><h2 class="section-title">重點摘要</h2>')
        parts.append(_chip_row([str(x) for x in summary], kind="summary"))
        parts.append("</section>")
    if strategy:
        parts.append('<section class="mb-4 panel panel-violet"><h2 class="section-title">講義結構說明</h2><ul class="mb-0">')
        parts.extend(f"<li>{_esc(x)}</li>" for x in strategy)
        parts.append("</ul></section>")
    parts.append(
        '<p class="tab-hint">下一步：到「圖表」看互動視覺化，或到「章節講義」逐站精讀。</p>'
    )
    parts.append("</div>")

    # Tab: 圖表
    parts.append('<div class="tab-pane fade" id="tab-charts" role="tabpanel">')
    parts.append(render_viz_tab(payload_from_tax_note(note)))
    parts.append("</div>")

    # Tab: 學習路徑
    parts.append('<div class="tab-pane fade" id="tab-path" role="tabpanel">')
    if milestones:
        parts.append('<div class="path-cards">')
        for i, m in enumerate(milestones, 1):
            ch_i = int(m.get("chapter") or i)
            parts.append(
                f'<a class="path-card" href="#ch-{ch_i}" data-bs-toggle="pill" data-bs-target="#tab-lecture">'
                f'<div class="path-idx">站 {i}</div>'
                f'<div class="path-title">{_esc(m.get("label") or "")}</div>'
                f'<div class="path-desc">{_esc(m.get("desc") or "")}</div>'
                f'<div class="path-go">前往講義 →</div></a>'
            )
        parts.append("</div>")
    else:
        parts.append('<p class="text-secondary">尚無里程碑資料。</p>')
    parts.append("</div>")

    # Tab: 章節講義
    parts.append('<div class="tab-pane fade" id="tab-lecture" role="tabpanel">')
    for i, ch in enumerate(chapters, 1):
        parts.append(_render_chapter_block(ch, i))
    parts.append("</div>")

    # Tab: 速查
    parts.append('<div class="tab-pane fade" id="tab-quick" role="tabpanel">')
    parts.append('<div class="row g-3">')
    for i, ch in enumerate(chapters, 1):
        kps = [str(x).strip() for x in _list(ch.get("key_points")) if str(x).strip()]
        if not kps:
            # 從 notes / body 抽一句
            for n in _list(ch.get("notes")):
                if str(n).strip():
                    kps.append(str(n).strip())
            body = str(ch.get("body") or "")
            for line in body.split("\n"):
                if line.startswith("重點"):
                    kps.append(re.sub(r"^重點[:：]\s*", "", line).strip()[:90])
                    break
        parts.append('<div class="col-md-6">')
        parts.append(f'<div class="quick-card tip-card accent-cyan">')
        parts.append(f'<div class="card-body">')
        parts.append(f'<div class="quick-kicker">第 {i} 章</div>')
        parts.append(f'<h3 class="h6">{_esc(ch.get("title") or "")}</h3>')
        if kps:
            parts.append("<ul class='mb-0 small'>")
            parts.extend(f"<li>{_esc(k)}</li>" for k in kps[:5])
            parts.append("</ul>")
        parts.append(f'<a class="small" href="#ch-{i}" data-jump-lecture>看完整講義</a>')
        parts.append("</div></div></div>")
    parts.append("</div></div>")

    # Tab: 課後測驗
    parts.append('<div class="tab-pane fade" id="tab-quiz" role="tabpanel">')
    parts.append('<section class="quiz-wrap" aria-label="課後測驗">')
    parts.append('<div class="section-kicker">自我檢核</div>')
    parts.append('<h2 class="section-title">課後測驗</h2>')
    parts.append(_render_quiz_panel(quiz))
    parts.append("</section></div>")

    parts.append("</div></div>")  # tab-content + lecture-tabs
    return "\n".join(parts)


_LECTURE_PAGE_CSS = """
:root{
  --bg:#0b0f14; --bg2:#121821; --text:#e8eef7; --muted:#9fb0c6;
  --cyan:#5ec8ff; --mint:#3ee0a2; --amber:#ffc857; --coral:#ff7b72;
  --violet:#c3a6ff; --sky:#6ee7f5;
}
body{
  background:
    radial-gradient(1100px 480px at 8% -8%, rgba(94,200,255,.15), transparent 55%),
    radial-gradient(900px 420px at 92% 0%, rgba(195,166,255,.12), transparent 50%),
    radial-gradient(700px 360px at 50% 110%, rgba(62,224,162,.08), transparent 45%),
    var(--bg);
  color:var(--text);
}
.meta-line{color:var(--muted);font-size:.85rem;}
.lecture-hero{margin-bottom:1.4rem;}
.unit-badge{display:inline-block;font-size:.75rem;font-weight:800;letter-spacing:.04em;padding:.28rem .7rem;border-radius:999px;background:linear-gradient(135deg,rgba(94,200,255,.25),rgba(195,166,255,.25));border:1px solid rgba(255,255,255,.1);margin-bottom:.65rem;}
.note-title{font-weight:780;letter-spacing:.01em;line-height:1.28;font-size:clamp(1.45rem,3vw,2rem);}
.title-link{text-decoration:none;background:linear-gradient(90deg,var(--cyan),var(--violet));-webkit-background-clip:text;background-clip:text;color:transparent;}
.source-line a{color:var(--sky);text-decoration:none;border-bottom:1px dashed rgba(110,231,245,.45);}
.section-kicker{font-size:.75rem;font-weight:800;letter-spacing:.08em;color:var(--cyan);margin-bottom:.25rem;}
.section-title{font-size:1.15rem;font-weight:720;margin-bottom:.85rem;}
.panel{background:rgba(18,24,33,.88);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:1rem 1.1rem;}
.panel-violet{border-left:4px solid var(--violet);}
.panel-mint{border-left:4px solid var(--mint);}
.chip-row{display:flex;flex-wrap:wrap;gap:.45rem;margin:.35rem 0 1rem;}
.tag-chip{display:inline-flex;align-items:center;padding:.28rem .7rem;border-radius:999px;font-size:.78rem;font-weight:650;border:1px solid transparent;background:rgba(18,24,33,.95);}
.summary-chips{display:flex;flex-direction:column;gap:.65rem;}
.summary-chip{border-radius:12px;padding:.75rem .95rem;border:1px solid transparent;background:rgba(18,24,33,.9);}
.chip-cyan,.tag-chip.chip-cyan{border-color:rgba(94,200,255,.4);box-shadow:inset 3px 0 0 var(--cyan);}
.chip-mint,.tag-chip.chip-mint{border-color:rgba(62,224,162,.4);box-shadow:inset 3px 0 0 var(--mint);}
.chip-amber,.tag-chip.chip-amber{border-color:rgba(255,200,87,.4);box-shadow:inset 3px 0 0 var(--amber);}
.chip-coral,.tag-chip.chip-coral{border-color:rgba(255,123,114,.4);box-shadow:inset 3px 0 0 var(--coral);}
.chip-violet,.tag-chip.chip-violet{border-color:rgba(195,166,255,.4);box-shadow:inset 3px 0 0 var(--violet);}
.chip-sky,.tag-chip.chip-sky{border-color:rgba(110,231,245,.4);box-shadow:inset 3px 0 0 var(--sky);}
.milestone-wrap{margin:1.25rem 0 1.5rem;}
.milestone-track{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.75rem;position:relative;}
.milestone-item{margin:0;}
.milestone-link{display:flex;flex-direction:column;gap:.35rem;height:100%;padding:.85rem .9rem;border-radius:14px;text-decoration:none;color:inherit;background:rgba(16,22,30,.92);border:1px solid rgba(255,255,255,.08);transition:transform .15s ease,border-color .15s ease;}
.milestone-link:hover{transform:translateY(-2px);border-color:rgba(94,200,255,.45);color:inherit;}
.ms-dot{width:1.7rem;height:1.7rem;border-radius:999px;display:grid;place-items:center;font-size:.8rem;font-weight:800;color:#071018;background:linear-gradient(135deg,var(--cyan),var(--mint));}
.ms-label{font-weight:720;font-size:.95rem;}
.ms-desc{font-size:.78rem;color:var(--muted);line-height:1.45;}
.lecture-nav{gap:.4rem;margin-bottom:1rem;flex-wrap:wrap;}
.lecture-nav .nav-link{border-radius:999px;color:var(--muted);background:rgba(18,24,33,.8);border:1px solid rgba(255,255,255,.08);padding:.4rem .9rem;}
.lecture-nav .nav-link.active{color:#071018;background:linear-gradient(135deg,var(--cyan),var(--mint));border-color:transparent;font-weight:750;}
.lecture-tab-content{background:rgba(12,16,22,.45);border:1px solid rgba(255,255,255,.05);border-radius:16px;padding:1.1rem 1rem 1.4rem;}
.tab-hint{color:var(--muted);font-size:.9rem;margin-top:.5rem;}
.path-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.8rem;}
.path-card{display:block;padding:1rem;border-radius:14px;text-decoration:none;color:inherit;background:rgba(16,22,30,.95);border:1px solid rgba(255,255,255,.08);}
.path-card:hover{border-color:rgba(195,166,255,.5);color:inherit;}
.path-idx{font-size:.75rem;font-weight:800;color:var(--violet);}
.path-title{font-weight:720;margin:.25rem 0;}
.path-desc{font-size:.82rem;color:var(--muted);}
.path-go{margin-top:.55rem;font-size:.82rem;color:var(--cyan);}
.chapter-block{padding:1rem 0 1.4rem;border-bottom:1px solid rgba(255,255,255,.06);scroll-margin-top:1rem;}
.chapter-block:last-child{border-bottom:0;}
.chapter-head{margin-bottom:.55rem;}
.milestone-badge{display:inline-block;font-size:.72rem;font-weight:800;color:var(--amber);margin-bottom:.35rem;letter-spacing:.04em;}
.chapter-title{display:flex;align-items:center;gap:.65rem;font-size:1.2rem;font-weight:720;margin:0;}
.chapter-num{display:inline-grid;place-items:center;min-width:1.85rem;height:1.85rem;padding:0 .35rem;border-radius:999px;font-size:.9rem;font-weight:800;color:#071018;background:linear-gradient(135deg,var(--cyan),var(--mint));}
.subhead{font-size:1rem;font-weight:700;margin:1rem 0 .5rem;color:var(--sky);}
.lecture-list,.check-list{padding-left:1.15rem;color:#d7e2f0;}
.lecture-list li,.check-list li{margin:.25rem 0;}
.body-p{color:#d7e2f0;}
.kp-box{margin:.75rem 0 1rem;padding:.75rem .85rem;border-radius:12px;border:1px dashed rgba(94,200,255,.35);background:rgba(94,200,255,.06);}
.callout{border-radius:14px;padding:.9rem 1rem;border:1px solid rgba(255,255,255,.08);background:rgba(16,22,30,.92);}
.callout-label{font-size:.78rem;font-weight:800;letter-spacing:.06em;margin-bottom:.35rem;}
.callout-body,.callout-list{color:#e8eef7;}
.callout-list{padding-left:1.1rem;}
.callout-key{border-color:rgba(94,200,255,.4);background:linear-gradient(135deg,rgba(94,200,255,.16),rgba(16,22,30,.95));}
.callout-key .callout-label{color:var(--cyan);}
.callout-judge{border-color:rgba(195,166,255,.4);background:linear-gradient(135deg,rgba(195,166,255,.14),rgba(16,22,30,.95));}
.callout-judge .callout-label{color:var(--violet);}
.callout-note,.callout-tip{border-color:rgba(62,224,162,.4);background:linear-gradient(135deg,rgba(62,224,162,.14),rgba(16,22,30,.95));}
.callout-note .callout-label,.callout-tip .callout-label{color:var(--mint);}
.callout-warn{border-color:rgba(255,200,87,.45);background:linear-gradient(135deg,rgba(255,200,87,.16),rgba(16,22,30,.95));}
.callout-warn .callout-label{color:var(--amber);}
.callout-fact{border-color:rgba(110,231,245,.4);background:linear-gradient(135deg,rgba(110,231,245,.14),rgba(16,22,30,.95));}
.callout-fact .callout-label{color:var(--sky);}
.tip-card{background:rgba(16,22,30,.95);border:1px solid rgba(255,255,255,.08);border-radius:14px;overflow:hidden;}
.tip-card .card-header{background:transparent;border-bottom:1px solid rgba(255,255,255,.08);font-weight:700;}
.tip-card .card-title{font-weight:720;}
.tip-card .card-text,.tip-card li{color:#c9d7ea;}
.accent-cyan{box-shadow:inset 0 3px 0 var(--cyan);}
.accent-mint{box-shadow:inset 0 3px 0 var(--mint);}
.accent-amber{box-shadow:inset 0 3px 0 var(--amber);}
.accent-coral{box-shadow:inset 0 3px 0 var(--coral);}
.accent-violet{box-shadow:inset 0 3px 0 var(--violet);}
.accent-sky{box-shadow:inset 0 3px 0 var(--sky);}
.quick-kicker{font-size:.72rem;font-weight:800;color:var(--cyan);margin-bottom:.2rem;}
.table{--bs-table-bg:rgba(16,22,30,.9);--bs-table-color:var(--text);}
.mermaid{text-align:center;border-radius:14px;border:1px solid rgba(255,255,255,.06);}
.quiz-intro{color:var(--muted);font-size:.92rem;margin-bottom:.9rem;}
.quiz-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:.55rem;margin-bottom:1rem;}
.quiz-tool-btn{border:1px solid rgba(255,255,255,.12);background:rgba(18,24,33,.9);color:var(--text);border-radius:999px;padding:.28rem .75rem;}
.quiz-tool-btn:hover{border-color:rgba(94,200,255,.45);color:var(--cyan);}
.quiz-count{font-size:.8rem;color:var(--muted);margin-left:.25rem;}
.quiz-list{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:.9rem;}
.quiz-item{padding:1rem 1.05rem;border-radius:14px;background:rgba(16,22,30,.95);border:1px solid rgba(255,255,255,.08);}
.quiz-item-head{display:flex;flex-wrap:wrap;align-items:center;gap:.45rem;margin-bottom:.45rem;}
.quiz-no{font-weight:800;font-size:.85rem;color:var(--cyan);}
.quiz-kind{font-size:.72rem;font-weight:800;letter-spacing:.04em;padding:.18rem .55rem;border-radius:999px;}
.quiz-kind-know{background:rgba(62,224,162,.16);color:var(--mint);border:1px solid rgba(62,224,162,.35);}
.quiz-kind-data{background:rgba(255,200,87,.14);color:var(--amber);border:1px solid rgba(255,200,87,.4);}
.quiz-topic{font-size:.8rem;color:var(--muted);}
.quiz-q{margin:0 0 .7rem;font-weight:650;line-height:1.55;}
.quiz-answer-row{display:flex;flex-wrap:wrap;align-items:stretch;gap:.55rem;}
.quiz-reveal-btn{flex:0 0 auto;border-radius:10px;border:1px solid rgba(195,166,255,.4);background:rgba(195,166,255,.12);color:var(--violet);font-size:.82rem;font-weight:700;padding:.4rem .75rem;}
.quiz-reveal-btn[aria-pressed="true"]{background:rgba(94,200,255,.14);border-color:rgba(94,200,255,.4);color:var(--cyan);}
.quiz-secret-box{flex:1 1 200px;min-height:2.4rem;display:flex;align-items:center;padding:.45rem .75rem;border-radius:10px;border:1px solid rgba(255,255,255,.1);background:#0a0e14;font-family:ui-monospace,Consolas,monospace;}
.quiz-secret-text{letter-spacing:.04em;color:var(--mint);}
.quiz-secret-box.is-masked .quiz-secret-text{
  -webkit-text-security:disc;
  text-security:disc;
  color:var(--muted);
  user-select:none;
  filter:blur(.5px);
}
.quiz-explain{margin-top:.55rem;font-size:.86rem;color:#c9d7ea;padding:.55rem .7rem;border-radius:10px;background:rgba(94,200,255,.08);border:1px dashed rgba(94,200,255,.3);}
.quiz-explain-label{display:inline-block;font-size:.72rem;font-weight:800;color:var(--cyan);margin-right:.4rem;}
.quiz-explain.is-hidden{display:none;}
a{color:var(--cyan);}
@media (max-width:576px){
  .lecture-tab-content{padding:.85rem .7rem 1.1rem;}
}
""".strip()

_QUIZ_CHART_INIT_SCRIPT = """
<script>
try {
  if (window.mermaid) mermaid.initialize({ startOnLoad: true, theme: "dark", securityLevel: "loose" });
} catch (e) {}
(function(){
  function setReveal(box, btn, explain, show){
    if(!box || !btn) return;
    box.classList.toggle('is-masked', !show);
    btn.setAttribute('aria-pressed', show ? 'true' : 'false');
    btn.textContent = show ? '隱藏答案' : '顯示答案';
    if(explain) explain.classList.toggle('is-hidden', !show);
  }
  document.querySelectorAll('[data-reveal-answer]').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      const item = btn.closest('[data-quiz-item]');
      const box = item && item.querySelector('[data-secret-box]');
      const explain = item && item.querySelector('[data-quiz-explain]');
      const show = btn.getAttribute('aria-pressed') !== 'true';
      setReveal(box, btn, explain, show);
    });
  });
  const allShow = document.getElementById('quiz-reveal-all');
  const allHide = document.getElementById('quiz-hide-all');
  if(allShow) allShow.addEventListener('click', ()=>{
    document.querySelectorAll('[data-quiz-item]').forEach(item=>{
      setReveal(item.querySelector('[data-secret-box]'), item.querySelector('[data-reveal-answer]'), item.querySelector('[data-quiz-explain]'), true);
    });
  });
  if(allHide) allHide.addEventListener('click', ()=>{
    document.querySelectorAll('[data-quiz-item]').forEach(item=>{
      setReveal(item.querySelector('[data-secret-box]'), item.querySelector('[data-reveal-answer]'), item.querySelector('[data-quiz-explain]'), false);
    });
  });
  if(!window.Chart) return;
  const colors=["#5eb0ff","#3ecf8e","#e6b35a","#f07178","#b48ef0","#5ad0e6"];
  document.querySelectorAll(".chart-box").forEach(box=>{
    const canvas=box.querySelector("canvas");
    const cfgEl=box.querySelector(".chart-config");
    if(!canvas||!cfgEl) return;
    let cfg; try{ cfg=JSON.parse(cfgEl.textContent); }catch(e){ return; }
    const type=cfg.type||"bar";
    const datasets=(cfg.datasets||[]).map((ds,i)=>({
      ...ds,
      backgroundColor: ds.backgroundColor || colors[i%colors.length]+"cc",
      borderColor: ds.borderColor || colors[i%colors.length],
      borderWidth: 1.5
    }));
    new Chart(canvas,{
      type,
      data:{ labels: cfg.labels||[], datasets },
      options:{
        responsive:true,
        plugins:{ legend:{ labels:{ color:"#c9d7ea" } } },
        scales:(type==="pie"||type==="doughnut")?{} : {
          x:{ ticks:{ color:"#93a4b8" }, grid:{ color:"#2a3544" } },
          y:{ ticks:{ color:"#93a4b8" }, grid:{ color:"#2a3544" } }
        }
      }
    });
  });
})();
</script>
""".strip()


def wrap_bootstrap_document(
    title: str,
    body_html: str,
    *,
    sidebar_html: str = "",
    course_brand: str = "教學講義",
    active_file: str = "",
    books: list | None = None,
) -> str:
    if not sidebar_html:
        book_list = books
        if not book_list:
            book_list = [{"file": active_file, "title": title, "chapters": []}]
        sidebar_html = build_course_sidebar(
            brand=course_brand,
            books=book_list,
            active_file=active_file,
            home_href="../index.html",
        )

    style_extra = f"{EXTRA_CSS}\n{NARRATION_CSS}\n{_LECTURE_PAGE_CSS}"
    scripts_before = f"{SCRIPT_TAGS}\n{_QUIZ_CHART_INIT_SCRIPT}"
    meta_line = (
        "學習講義 · 語音講解／左側目錄／Tabs／Chips／測驗 · "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    return wrap_with_sidebar(
        title=title,
        body_html=body_html,
        sidebar_html=sidebar_html,
        head_extra=HEAD_LINKS,
        style_extra=style_extra,
        scripts_before=scripts_before,
        scripts_after=f"{BOOT_SCRIPT}\n<script>\n{NARRATION_JS}\n</script>",
        meta_line=meta_line,
        storage_key="tax-note-side-collapsed",
    )


def note_to_markdown(note: dict[str, Any]) -> str:
    title = note.get("title") or "教學筆記"
    source_url = str(note.get("source_url") or "").strip()
    if source_url.startswith(("http://", "https://")):
        lines = [f"# [{title}]({source_url})", "", f"來源：{source_url}", ""]
    else:
        lines = [f"# {title}", ""]
    if note.get("strategy"):
        lines += ["## 呈現策略", ""] + [f"- {x}" for x in _list(note["strategy"])] + [""]
    if note.get("goals"):
        lines += ["## 學習目標", ""] + [f"- {x}" for x in _list(note["goals"])] + [""]
    if note.get("summary"):
        lines += ["## 重點摘要", ""] + [f"- {x}" for x in _list(note["summary"])] + [""]
    for i, ch in enumerate(_list(note.get("chapters")), 1):
        if not isinstance(ch, dict):
            continue
        lines += [f"## {i}. {ch.get('title') or '章節'}", "", str(ch.get("body") or ""), ""]
        vis = ch.get("visual") or {}
        if isinstance(vis, dict) and vis.get("type") not in (None, "", "none"):
            lines += [f"（HTML 視覺：{vis.get('type')}）", ""]
        for n in _list(ch.get("notes")):
            lines.append(f"- {n}")
        if ch.get("warning"):
            lines += ["", f"> **警告**：{ch['warning']}", ""]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def extract_source_url(text: str) -> str:
    """從爬蟲 txt／貼上內容取出來源網址（清洗前呼叫）。"""
    raw = text or ""
    m = re.search(r"來源\s*[:：]\s*(https?://[^\s<>\"']+)", raw, flags=re.I)
    if m:
        return m.group(1).rstrip(")。.,，、；;")
    m = re.search(r"(https?://(?:www\.)?hahow\.in/[^\s<>\"']+)", raw, flags=re.I)
    if m:
        return m.group(1).rstrip(")。.,，、；;")
    m = re.search(r"(https?://[^\s<>\"']+)", raw, flags=re.I)
    if m:
        url = m.group(1).rstrip(")。.,，、；;")
        # 略過明顯不是教材的連結噪音
        if any(x in url.lower() for x in ("cdn.", "jsdelivr", "bootstrap", "chart.js")):
            return ""
        return url
    return ""


def normalize_note(note: dict[str, Any], fallback_title: str = "") -> dict[str, Any]:
    note = dict(note)
    note["title"] = (note.get("title") or fallback_title or "教學講義").strip()
    src = str(note.get("source_url") or "").strip()
    if src.startswith(("http://", "https://")):
        note["source_url"] = src
    else:
        note["source_url"] = ""
    note["badge"] = str(note.get("badge") or "").strip()
    note["tags"] = [str(x).strip() for x in _list(note.get("tags")) if str(x).strip()]
    note["strategy"] = [str(x) for x in _list(note.get("strategy"))]
    note["goals"] = [str(x) for x in _list(note.get("goals"))]
    note["summary"] = [str(x) for x in _list(note.get("summary"))]
    # milestones
    ms_out: list[dict[str, Any]] = []
    for i, m in enumerate(_list(note.get("milestones")), 1):
        if isinstance(m, str) and m.strip():
            ms_out.append({"label": m.strip(), "desc": "", "chapter": i})
        elif isinstance(m, dict):
            ms_out.append(
                {
                    "label": str(m.get("label") or m.get("title") or f"里程碑 {i}").strip(),
                    "desc": str(m.get("desc") or m.get("text") or "").strip(),
                    "chapter": int(m.get("chapter") or i),
                }
            )
    note["milestones"] = ms_out
    chapters = []
    for ch in _list(note.get("chapters")):
        if isinstance(ch, dict):
            c = dict(ch)
            c["tags"] = [str(x).strip() for x in _list(c.get("tags")) if str(x).strip()]
            c["key_points"] = [str(x).strip() for x in _list(c.get("key_points")) if str(x).strip()]
            c["checklist"] = [str(x).strip() for x in _list(c.get("checklist")) if str(x).strip()]
            c["milestone"] = str(c.get("milestone") or "").strip()
            c["narration"] = str(
                c.get("narration") or c.get("audio_script") or ""
            ).strip()
            secs = []
            for sec in _list(c.get("sections")):
                if isinstance(sec, dict):
                    secs.append(
                        {
                            "heading": str(sec.get("heading") or sec.get("title") or "").strip(),
                            "paras": [str(x).strip() for x in _list(sec.get("paras") or sec.get("paragraphs")) if str(x).strip()],
                            "bullets": [str(x).strip() for x in _list(sec.get("bullets")) if str(x).strip()],
                        }
                    )
            c["sections"] = secs
            chapters.append(c)
        elif isinstance(ch, str):
            chapters.append({"title": "說明", "body": ch, "visual": {"type": "none"}})
    if not chapters:
        chapters = [{
            "title": "整理",
            "body": "（尚無章節內容）",
            "visual": {"type": "fact", "items": [{"title": "提示", "text": "請補充講義"}]},
            "notes": [],
            "warning": "",
        }]
    note["chapters"] = chapters
    # quiz
    quiz_raw = note.get("quiz")
    if isinstance(quiz_raw, dict):
        note["quiz"] = {
            "intro": str(quiz_raw.get("intro") or "").strip(),
            "items": _normalize_quiz_items(quiz_raw.get("items") or quiz_raw.get("questions")),
        }
    elif isinstance(quiz_raw, list):
        note["quiz"] = {"intro": "", "items": _normalize_quiz_items(quiz_raw)}
    else:
        note["quiz"] = {"intro": "", "items": []}
    return note


_ALLOWED_VISUAL = {
    "fact", "cards", "compare", "matrix2x2", "mermaid", "chart", "table", "none",
}

_GENERIC_CHAPTER_TITLES = {"核心概念", "重點整理", "章節", "整理", "補充與注意"}
_EMPTY_BODY_MARKERS = ("本章內容不足", "請依素材補充", "內容不足")


def is_mostly_english(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 12:
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 12:
        return False
    ascii_letters = sum(1 for c in letters if "a" <= c.lower() <= "z")
    return (ascii_letters / len(letters)) >= 0.65


def filter_zh_list(items: Any, *, keep_if_empty: bool = False) -> list[str]:
    out: list[str] = []
    for x in _list(items):
        s = str(x).strip()
        if not s or is_mostly_english(s):
            continue
        out.append(s)
    if keep_if_empty and not out:
        return [str(x).strip() for x in _list(items) if str(x).strip()]
    return out


_META_LINE = re.compile(
    r"^(來源|定位|值|時間|url|class)\s*[:：]|^(https?://)|^=+|sc-[\w-]+",
    re.I,
)
_FILLER_LINE = re.compile(
    r"^(你好|哈囉|各位|同學們|這個單元我們|我們要介紹的是|除此之外|"
    r"在這個單元|我們就來|你可能想知道|可能就成為|今天要|接下來)"
)
_TOPIC_HINT = re.compile(
    r"(公司|行號|稅|發票|登記|資本|有限|股份|小規模|營業|萬元|門檻|扣抵|負責人)"
)


def clean_source_text(text: str) -> str:
    """去掉爬蟲表頭、口播寒暄，並把斷行口播併成可讀段落。"""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if "=====" in raw:
        # 取最後一段正文（表頭常在 ===== 之前）
        parts = re.split(r"\n?={5,}\n?", raw)
        raw = parts[-1] if parts else raw

    kept: list[str] = []
    for ln in raw.split("\n"):
        s = ln.strip()
        if not s:
            kept.append("")  # 保留空行當段界
            continue
        if _META_LINE.search(s):
            continue
        if _FILLER_LINE.search(s) and len(s) < 18:
            continue
        if is_mostly_english(s) and not re.search(r"[\u4e00-\u9fff]", s):
            continue
        kept.append(s)

    # 口播短行合併
    paras: list[str] = []
    buf = ""
    for s in kept:
        if not s:
            if buf:
                paras.append(buf)
                buf = ""
            continue
        # 已是長句就直接成段
        if len(s) >= 36:
            if buf:
                paras.append(buf)
                buf = ""
            paras.append(s)
            continue
        buf += s
        if len(buf) >= 42 and (buf.endswith(("。", "？", "！", "呢", "嗎", "了")) or len(buf) >= 70):
            paras.append(buf)
            buf = ""
    if buf:
        paras.append(buf)

    # 去重保序
    out: list[str] = []
    seen: set[str] = set()
    for p in paras:
        p = re.sub(r"\s+", "", p) if len(p) < 80 else p.strip()
        p = p.strip()
        if len(p) < 6 or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return "\n\n".join(out)


def _snippet_score(p: str) -> int:
    if _META_LINE.search(p) or _FILLER_LINE.search(p):
        return -10
    score = 0
    if _TOPIC_HINT.search(p):
        score += 3
    if re.search(r"\d", p):
        score += 1
    if 12 <= len(p) <= 48:
        score += 1
    return score


def chinese_snippets_from_text(content: str, limit: int = 5) -> list[str]:
    """從素材抽出可當摘要的繁中短句（略過表頭／開場白）。"""
    body = clean_source_text(content)
    parts = re.split(r"[\n。！？!?]+", body)
    scored: list[tuple[int, str]] = []
    for p in parts:
        p = re.sub(r"\s+", "", p)
        if len(p) < 10 or len(p) > 56:
            continue
        if is_mostly_english(p) or not re.search(r"[\u4e00-\u9fff]", p):
            continue
        scored.append((_snippet_score(p), p))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    out: list[str] = []
    seen: set[str] = set()
    for sc, p in scored:
        if sc < 0 or p in seen:
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= limit:
            break
    return out


def fallback_chapters_from_content(content: str, style: str = "詳細") -> list[dict[str, Any]]:
    """模型大綱失敗時的後備章：用具體任務描述當 focus，不要貼口播原句。"""
    snippets = chinese_snippets_from_text(content, limit=6)
    hint_blob = "、".join(snippets[:4]) if snippets else "依素材整理重點"
    if style == "精簡":
        plans = [
            ("背景與門檻", f"說明何時需要登記；素材線索：{hint_blob}", "cards"),
            ("如何選擇", f"比較可行方案與注意點；素材線索：{hint_blob}", "compare"),
        ]
    else:
        plans = [
            ("背景與適用情境", f"說明為何要討論登記、適用對象；線索：{hint_blob}", "cards"),
            ("方案比較", "比較小規模營業人、行號、公司的差異與適用時機", "compare"),
            ("門檻、限制與轉換", "整理營業額／稅務門檻、限制，以及何時要升級轉換", "table"),
            ("實務注意事項", "整理登記、發票、常見誤解與實務提醒", "fact"),
        ]
    return [
        {"title": title, "focus": focus, "visualHint": hint}
        for title, focus, hint in plans
    ]


def _visual_text_blob(visual: dict[str, Any]) -> str:
    bits: list[str] = []
    items = visual.get("items")
    if isinstance(items, list):
        for it in items:
            if isinstance(it, str) and it.strip():
                bits.append(it.strip())
            elif isinstance(it, dict):
                t = str(it.get("title") or "").strip()
                x = str(it.get("text") or it.get("body") or "").strip()
                if t and x:
                    bits.append(f"{t}：{x}")
                elif x:
                    bits.append(x)
                elif t:
                    bits.append(t)
    rows = visual.get("rows")
    if isinstance(rows, list):
        for row in rows[:6]:
            if isinstance(row, dict):
                left = str(row.get("left") or "").strip()
                right = str(row.get("right") or "").strip()
                if left or right:
                    bits.append(f"{left}／{right}".strip("／"))
            elif isinstance(row, list):
                bits.append("、".join(str(c) for c in row if str(c).strip()))
    for key in ("tl", "tr", "bl", "br"):
        cell = visual.get(key)
        if isinstance(cell, dict):
            t = str(cell.get("title") or "").strip()
            x = str(cell.get("text") or "").strip()
            if t or x:
                bits.append(f"{t}：{x}".strip("："))
    code = str(visual.get("code") or "").strip()
    if code and not is_mostly_english(code):
        bits.append(code[:200])
    return "\n".join(bits).strip()


def extract_chapter_body(data: dict[str, Any], visual: dict[str, Any] | None = None) -> str:
    """從各種常見欄位撈出章節正文。"""
    for key in ("body", "text", "content", "description", "說明", "內容", "paragraph", "summary"):
        v = data.get(key)
        if isinstance(v, list):
            joined = "\n".join(str(x).strip() for x in v if str(x).strip())
            if joined:
                return joined
        elif v is not None and str(v).strip():
            return str(v).strip()
    paras = data.get("paragraphs") or data.get("points")
    if isinstance(paras, list) and paras:
        return "\n".join(str(x).strip() for x in paras if str(x).strip())
    if isinstance(visual, dict):
        blob = _visual_text_blob(visual)
        if blob and not is_mostly_english(blob):
            return blob
    return ""


def is_weak_chapter_body(body: str) -> bool:
    b = (body or "").strip()
    if not b:
        return True
    if any(m in b for m in _EMPTY_BODY_MARKERS):
        return True
    if is_mostly_english(b):
        return True
    if len(re.sub(r"\s+", "", b)) < 20:
        return True
    return False


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    s = re.sub(r"\s+", "", text or "")
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def text_similarity(a: str, b: str) -> float:
    A, B = _char_ngrams(a), _char_ngrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def dedupe_texts(texts: list[str], threshold: float = 0.52) -> list[str]:
    """去掉高度相似的句子／段落。"""
    out: list[str] = []
    for t in texts:
        s = re.sub(r"\s+", "", (t or "").strip())
        if len(s) < 8:
            continue
        if any(text_similarity(s, re.sub(r"\s+", "", x)) >= threshold for x in out):
            continue
        out.append((t or "").strip())
    return out


def _dominant_phrase_hit_ratio(parts: list[str], gram_n: int = 4) -> float:
    """若多句都共享同一關鍵片語（如『開發票的公司行號』），比值會偏高。"""
    from collections import Counter

    clean = [re.sub(r"\s+", "", p) for p in parts if re.sub(r"\s+", "", p)]
    if len(clean) < 2:
        return 0.0
    grams: Counter[str] = Counter()
    for s in clean:
        if len(s) < gram_n:
            continue
        local = {s[i : i + gram_n] for i in range(len(s) - gram_n + 1)}
        for g in local:
            # 略過太泛用
            if g in {"我們可以", "這個時候", "就是說你", "因此可以"}:
                continue
            grams[g] += 1
    if not grams:
        return 0.0
    # 取出現在最多句子中的片語
    best = 0
    for g, _ in grams.most_common(30):
        hit = sum(1 for s in clean if g in s)
        if hit > best:
            best = hit
    return best / len(clean)


def is_low_quality_chapter(chapter: dict[str, Any]) -> bool:
    """偵測「看起來有字但沒有整理」的章節。"""
    if not isinstance(chapter, dict):
        return True
    body = str(chapter.get("body") or "").strip()
    if is_weak_chapter_body(body):
        return True

    parts = [p.strip() for p in re.split(r"[\n。！？!?]+", body) if p.strip()]
    parts = [p for p in parts if len(re.sub(r"\s+", "", p)) >= 8]
    if len(parts) >= 3 and _dominant_phrase_hit_ratio(parts) >= 0.75:
        return True
    if len(parts) >= 2:
        sims = []
        for i in range(len(parts)):
            for j in range(i + 1, len(parts)):
                sims.append(text_similarity(parts[i], parts[j]))
        if sims and (sum(sims) / len(sims)) >= 0.45:
            return True
        uniq = dedupe_texts(parts, threshold=0.45)
        if len(uniq) <= max(1, len(parts) // 2):
            return True

    # 只有問句、沒有答
    if parts and sum(1 for p in parts if p.endswith("？") or p.endswith("?")) >= max(2, len(parts) - 1):
        return True

    visual = chapter.get("visual") if isinstance(chapter.get("visual"), dict) else {}
    items = _list(visual.get("items")) if visual else []
    card_texts = []
    pointy = 0
    for it in items:
        if isinstance(it, dict):
            t = str(it.get("title") or "")
            x = str(it.get("text") or "")
            if re.match(r"^要點\s*\d+", t):
                pointy += 1
            if x.strip():
                card_texts.append(x.strip())
        elif isinstance(it, str) and it.strip():
            card_texts.append(it.strip())
    # 「要點1/2/3」本身就是未整理訊號
    if pointy >= 2:
        return True
    if len(card_texts) >= 3 and _dominant_phrase_hit_ratio(card_texts) >= 0.67:
        return True
    if len(card_texts) >= 3 and len(dedupe_texts(card_texts, 0.42)) <= 2:
        return True
    return False


def normalize_outline(
    data: dict[str, Any],
    fallback_title: str = "",
    style: str = "詳細",
    content: str = "",
) -> dict[str, Any]:
    """正規化大綱 JSON。"""
    data = dict(data or {})
    title = (data.get("title") or fallback_title or "教學筆記").strip()
    if is_mostly_english(title):
        title = (fallback_title or "教學筆記").strip()

    chapters_in = _list(
        data.get("chapters")
        or data.get("sections")
        or data.get("topics")
        or data.get("outline")
        or data.get("章節")
    )
    chapters: list[dict[str, Any]] = []
    for ch in chapters_in:
        if isinstance(ch, str) and ch.strip():
            if is_mostly_english(ch):
                continue
            chapters.append({"title": ch.strip(), "focus": ch.strip(), "visualHint": "cards"})
            continue
        if not isinstance(ch, dict):
            continue
        ctitle = (
            ch.get("title") or ch.get("name") or ch.get("topic") or ch.get("章名") or ""
        )
        ctitle = str(ctitle).strip() or "章節"
        if is_mostly_english(ctitle):
            continue
        focus = (
            ch.get("focus")
            or ch.get("body")
            or ch.get("summary")
            or ch.get("points")
            or ch.get("焦點")
            or ctitle
        )
        if isinstance(focus, list):
            focus = "；".join(str(x).strip() for x in focus if str(x).strip())
        focus = str(focus).strip()
        if is_mostly_english(focus):
            focus = ctitle
        hint = str(ch.get("visualHint") or ch.get("visual_hint") or ch.get("visual") or "cards")
        if isinstance(ch.get("visual"), dict):
            hint = str(ch["visual"].get("type") or hint)
        hint = hint.lower().strip()
        if hint not in _ALLOWED_VISUAL:
            hint = "cards"
        chapters.append({"title": ctitle, "focus": focus, "visualHint": hint})

    # 若幾乎都是空泛章名，改用素材推章
    generic_ratio = 0.0
    if chapters:
        generic_ratio = sum(1 for c in chapters if c["title"] in _GENERIC_CHAPTER_TITLES) / len(chapters)

    min_ch, max_ch = (2, 3) if style == "精簡" else (3, 5)
    if len(chapters) > max_ch:
        chapters = chapters[:max_ch]
    if not chapters or generic_ratio >= 0.67:
        chapters = fallback_chapters_from_content(content, style)
    elif len(chapters) < min_ch:
        chapters.append(
            {"title": "實務注意與提醒", "focus": "補齊其餘重點與常見誤解", "visualHint": "fact"}
        )

    summary = filter_zh_list(data.get("summary"))
    if len(summary) < 2:
        summary = chinese_snippets_from_text(content, limit=4) or [c["focus"] for c in chapters[:4]]

    return {
        "title": title,
        "strategy": filter_zh_list(data.get("strategy")),
        "goals": filter_zh_list(data.get("goals")),
        "summary": summary[:6],
        "chapters": chapters,
    }


def sanitize_visual(visual: dict[str, Any]) -> dict[str, Any]:
    """丟掉空壳 visual（例如 compare 只有 A/B）。"""
    if not isinstance(visual, dict):
        return {"type": "none"}
    v = dict(visual)
    vtype = str(v.get("type") or "none").lower().strip()
    if vtype not in _ALLOWED_VISUAL:
        return {"type": "none"}
    v["type"] = vtype
    if vtype == "none":
        return v
    if vtype == "compare":
        rows = v.get("rows") or []
        good = []
        for row in rows:
            if isinstance(row, dict):
                left = str(row.get("left") or "").strip()
                right = str(row.get("right") or "").strip()
                if left in {"", "A", "a", "左", "…", "..."} and right in {"", "B", "b", "右", "…", "..."}:
                    continue
                if left or right:
                    good.append(row)
        if not good:
            return {"type": "none"}
        v["rows"] = good
        return v
    if vtype == "cards":
        items = [it for it in _list(v.get("items")) if it]
        cleaned = []
        seen_texts: list[str] = []
        pointy = 0
        for it in items:
            if isinstance(it, str) and it.strip() and it.strip() not in {"A", "B"}:
                if any(text_similarity(it, x) >= 0.55 for x in seen_texts):
                    continue
                cleaned.append({"title": "重點", "text": it.strip()})
                seen_texts.append(it.strip())
            elif isinstance(it, dict):
                t = str(it.get("title") or "").strip()
                x = str(it.get("text") or "").strip()
                if not x or _META_LINE.search(t + x):
                    continue
                if any(text_similarity(x, prev) >= 0.55 for prev in seen_texts):
                    continue
                if re.match(r"^要點\s*\d+$", t):
                    pointy += 1
                    t = re.split(r"[，,：:]", x)[0][:12] or "重點"
                cleaned.append({"title": t or "重點", "text": x})
                seen_texts.append(x)
        if len(cleaned) < 2:
            return {"type": "none"}
        texts = [c["text"] for c in cleaned]
        # 未整理的「要點N」或同義碎片卡 → 整組丟掉
        if pointy >= 2:
            return {"type": "none"}
        if _dominant_phrase_hit_ratio(texts) >= 0.67:
            return {"type": "none"}
        if len(dedupe_texts(texts, 0.42)) < 2:
            return {"type": "none"}
        v["items"] = cleaned
        return v
    if vtype == "fact":
        blob = _visual_text_blob(v)
        if not blob or _META_LINE.search(blob):
            return {"type": "none"}
        return v
    if vtype == "matrix2x2":
        filled = 0
        for key in ("tl", "tr", "bl", "br"):
            c = v.get(key) or v.get(key.upper())
            if isinstance(c, str) and c.strip():
                filled += 1
            elif isinstance(c, dict):
                t = str(c.get("title") or "").strip()
                x = str(c.get("text") or c.get("body") or "").strip()
                # 只有 TL/TR 這種鍵名佔位不算有內容
                if x or (t and t.upper() not in {"TL", "TR", "BL", "BR"}):
                    filled += 1
        if filled < 2:
            return {"type": "none"}
        return v
    return v


def scrub_meta_from_text(text: str) -> str:
    lines = []
    for ln in str(text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if _META_LINE.search(s):
            continue
        if "hahow.in" in s or "sc-jqnqvi" in s:
            continue
        lines.append(s)
    return "\n".join(lines).strip()


def normalize_chapter(
    data: dict[str, Any],
    fallback_title: str = "",
    visual_hint: str = "cards",
    focus: str = "",
) -> dict[str, Any]:
    """正規化單章 JSON。"""
    data = dict(data or {})
    title = (data.get("title") or fallback_title or "章節").strip()
    if is_mostly_english(title):
        title = (fallback_title or "章節").strip()

    visual = data.get("visual")
    if not isinstance(visual, dict):
        visual = {"type": visual_hint if visual_hint in _ALLOWED_VISUAL else "none"}
    else:
        vtype = str(visual.get("type") or visual_hint or "none").lower().strip()
        if vtype not in _ALLOWED_VISUAL:
            vtype = "none"
        visual = dict(visual)
        visual["type"] = vtype
    visual = sanitize_visual(visual)

    body = scrub_meta_from_text(extract_chapter_body(data, visual))
    if is_weak_chapter_body(body):
        parts = []
        fc = scrub_meta_from_text(focus)
        # 不要把「線索：口播」整段當正文
        fc = re.sub(r"線索[:：].*$", "", fc).strip(" ；;")
        if fc and not is_mostly_english(fc) and "線索" not in fc:
            parts.append(fc)
        blob = scrub_meta_from_text(_visual_text_blob(visual))
        if blob and not is_mostly_english(blob):
            parts.append(blob)
        body = "\n".join(parts).strip()
    if is_weak_chapter_body(body):
        body = "（本章內容不足，請依素材補充）"

    notes = filter_zh_list(data.get("notes"))
    warning = str(data.get("warning") or "").strip()
    if is_mostly_english(warning):
        warning = ""

    return {
        "title": title,
        "body": body,
        "visual": visual,
        "notes": notes,
        "warning": warning,
    }


def assemble_note(
    outline: dict[str, Any],
    chapters: list[dict[str, Any]],
    fallback_title: str = "",
    content: str = "",
    source_url: str = "",
) -> dict[str, Any]:
    """把大綱 + 各章內容組成完整 note。"""
    summary = filter_zh_list(outline.get("summary"))
    if len(summary) < 2:
        summary = []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            b = str(ch.get("body") or "").strip()
            if b and not is_weak_chapter_body(b):
                # 取第一句當摘要
                first = re.split(r"[。\n]", b)[0].strip()
                if first and not is_mostly_english(first):
                    summary.append(first)
            if len(summary) >= 5:
                break
        if len(summary) < 2:
            summary = chinese_snippets_from_text(content, limit=4)
    src = (source_url or "").strip() or extract_source_url(content)
    note = {
        "title": (outline.get("title") or fallback_title or "教學筆記").strip(),
        "source_url": src,
        "strategy": filter_zh_list(outline.get("strategy")),
        "goals": filter_zh_list(outline.get("goals")),
        "summary": summary[:6],
        "chapters": [c for c in chapters if isinstance(c, dict)],
    }
    return normalize_note(note, fallback_title=fallback_title)


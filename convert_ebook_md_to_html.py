# -*- coding: utf-8 -*-
"""公司治理 md → HTML：下拉收折目錄、置中收折鈕、chips／tabs 結構化呈現。"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

import markdown2

from note_viz_bundle import (
    BOOT_SCRIPT,
    EXTRA_CSS,
    HEAD_LINKS,
    SCRIPT_TAGS,
    payload_from_ebook,
    render_viz_tab,
)
from note_narration import (
    NARRATION_CSS,
    NARRATION_JS,
    compose_from_ebook_kid,
    compose_from_ebook_section,
    render_narration_panel,
)

from note_paths import EBOOK_DIR, EBOOK_DIR_LABEL, ebook_slug

ROOT = Path(__file__).resolve().parent
SRC_DIR = Path(r"T:\電子書截圖\公司治理\md")
OUT_DIR = EBOOK_DIR
NARR_CACHE = OUT_DIR / "_narrations.json"


def _load_narration_cache() -> dict[str, str]:
    if not NARR_CACHE.is_file():
        return {}
    try:
        data = json.loads(NARR_CACHE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if str(v).strip()}
    except Exception:
        pass
    return {}


def _apply_narration_cache(sections: list[dict], cache: dict[str, str]) -> None:
    if not cache:
        return
    for sec in sections:
        sid = str(sec.get("id") or "")
        if sid and cache.get(sid):
            sec["narration"] = cache[sid]
        for kid in sec.get("kids") or []:
            kid_id = str(kid.get("id") or "")
            if kid_id and cache.get(kid_id):
                kid["narration"] = cache[kid_id]

CHIP_ACCENTS = ("chip-cyan", "chip-mint", "chip-amber", "chip-coral", "chip-violet", "chip-sky")


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _chapter_sort_key(path: Path) -> tuple:
    m = re.search(r"第\s*(\d+)\s*章?", path.stem)
    return (int(m.group(1)) if m else 999, path.stem)


def _slug(text: str) -> str:
    s = re.sub(r"<[^>]+>", "", text).strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", s, flags=re.U)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "sec"


def _md_inline(text: str) -> str:
    return markdown2.markdown(text.strip(), extras=["strike"]).strip()


def _md_block(text: str) -> str:
    return markdown2.markdown(
        text.strip(),
        extras=["tables", "fenced-code-blocks", "strike", "cuddled-lists"],
    )


def _title_from_md(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _normalize_md(text: str) -> str:
    """把非標準標題（8.1 |、8.1 前言、OCR 斷行）正規成 # / ## / ###。"""
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")

    # 合併「10.1」下一行「 | 前言」
    merged: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", s) and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt.startswith("|"):
                merged.append(f"{s} {nxt}")
                i += 2
                continue
        merged.append(ln)
        i += 1

    # 若沒有任何 # 標題，把第一個非空當書名
    has_hash = any(l.startswith("#") for l in merged)
    out: list[str] = []
    if not has_hash:
        # 組 title：可能是「第 10」+「永續…」兩行
        title_parts: list[str] = []
        start = 0
        for j, ln in enumerate(merged):
            s = ln.strip()
            if not s:
                if title_parts:
                    start = j + 1
                    break
                continue
            if re.match(r"^\d+\.\d+", s):
                start = j
                break
            title_parts.append(s)
            if len(title_parts) >= 2:
                start = j + 1
                break
        if title_parts:
            out.append("# " + " ".join(title_parts))
            merged = merged[start:]

    # 略過開頭目錄清單（連續的 x.y | 標題，直到出現正文或頁碼）
    # 先轉換標題列
    converted: list[str] = []
    for ln in merged:
        s = ln.strip()
        # 已是 markdown 標題
        if s.startswith("#### "):
            # 章內真正小節常被標成 #### 2.1
            rest = s[5:].strip()
            if re.match(r"\d+\.\d+\.\d+", rest):
                converted.append(f"### {rest}")
            elif re.match(r"\d+\.\d+", rest):
                converted.append(f"## {rest}")
            else:
                converted.append(f"## {rest}")
            continue
        if s.startswith("### "):
            converted.append(ln)
            continue
        if s.startswith("## "):
            converted.append(ln)
            continue
        if s.startswith("# "):
            converted.append(ln)
            continue
        if s.startswith("#"):
            converted.append(ln)
            continue
        m3 = re.match(r"^(\d+\.\d+\.\d+)\s*[|｜]?\s*(.+)$", s)
        if m3 and len(m3.group(2)) < 80:
            converted.append(f"### {m3.group(1)} {m3.group(2).lstrip('|｜ ').strip()}")
            continue
        m2 = re.match(r"^(\d+\.\d+)\s*[|｜]\s*(.+)$", s)
        if m2 and len(m2.group(2)) < 80:
            converted.append(f"## {m2.group(1)} | {m2.group(2).strip()}")
            continue
        m2b = re.match(r"^(\d+\.\d+)\s+([^\d].+)$", s)
        if m2b and len(m2b.group(2)) < 80 and not s.endswith("。"):
            converted.append(f"## {m2b.group(1)} {m2b.group(2).strip()}")
            continue
        m3b = re.match(r"^(\d+\.\d+\.\d+)\s+([^\d].+)$", s)
        if m3b and len(m3b.group(2)) < 80 and not s.endswith("。"):
            converted.append(f"### {m3b.group(1)} {m3b.group(2).strip()}")
            continue
        # **2.2.1 標題**
        mb = re.match(r"^\*\*(\d+\.\d+\.\d+)\s*(.+?)\*\*\s*$", s)
        if mb:
            converted.append(f"### {mb.group(1)} {mb.group(2).strip()}")
            continue
        # 孤立編號
        if re.fullmatch(r"\d+\.\d+", s):
            converted.append(f"## {s}")
            continue
        if re.fullmatch(r"\d+\.\d+\.\d+", s):
            converted.append(f"### {s}")
            continue
        converted.append(ln)

    result = "\n".join(out + converted if out else converted)
    # 若仍無 h1
    if not re.search(r"(?m)^# ", result):
        result = "# 筆記\n\n" + result
    return result


def _parse_sections(md: str) -> tuple[str, list[dict], str]:
    """回傳 (title, sections[{id,title,lead,kids,kind}], preface)。"""
    md = _normalize_md(md)
    lines = md.split("\n")
    title = _title_from_md(md, "筆記")

    cleaned: list[str] = []
    for ln in lines:
        if re.fullmatch(r"\s*-{3,}\s*", ln):
            continue
        if re.fullmatch(r"\s*\d{2,4}\s*", ln):
            continue
        cleaned.append(ln)

    body_start = 0
    for i, ln in enumerate(cleaned):
        if ln.startswith("# "):
            body_start = i + 1
            break

    chunks: list[tuple[str, str]] = []
    cur_title = ""
    buf: list[str] = []
    preface_buf: list[str] = []
    seen_h2 = False

    def flush():
        nonlocal cur_title, buf
        if cur_title:
            chunks.append((cur_title, "\n".join(buf).strip()))
        cur_title, buf = "", []

    for ln in cleaned[body_start:]:
        if ln.startswith("## ") and not ln.startswith("###"):
            flush()
            seen_h2 = True
            cur_title = ln[3:].strip()
            continue
        if not seen_h2:
            preface_buf.append(ln)
        else:
            buf.append(ln)
    flush()

    # 若開頭有「目錄型」連續空 h2，後面又有同號實心章節，去掉空目錄
    # 先收集有內容的編號
    content_nums = set()
    for h2, raw in chunks:
        if not raw:
            continue
        m = re.match(r"(\d+\.\d+)", h2)
        if m:
            content_nums.add(m.group(1))
    filtered: list[tuple[str, str]] = []
    for h2, raw in chunks:
        m = re.match(r"(\d+\.\d+)", h2)
        if not raw and m and m.group(1) in content_nums:
            continue
        if not raw and not m:
            continue
        filtered.append((h2, raw))
    if not any(r for _, r in filtered):
        filtered = chunks

    # 若仍幾乎只有一大包（目錄空節被刪光後剩練習題），嘗試從正文再切
    if len(filtered) <= 2 and filtered:
        big = max(filtered, key=lambda x: len(x[1]))
        if len(big[1]) > 800 and sum(1 for _, r in filtered if r) <= 1:
            # 用粗體小標 **2.2.1 xxx** 當 h3 已在 kids；另用段落內 ## 重建
            pass

    sections: list[dict] = []
    for h2, raw in filtered:
        sid = _slug(h2)
        kids: list[dict] = []
        parts = re.split(r"(?m)^(### .+)$", raw)
        lead = parts[0].strip() if parts else ""
        i = 1
        while i + 1 < len(parts):
            h3 = parts[i][4:].strip()
            kid_body = parts[i + 1].strip()
            kids.append({"id": _slug(h3), "title": h3, "body": kid_body})
            i += 2
        if not lead and not kids:
            continue
        sections.append(
            {
                "id": sid,
                "title": h2,
                "lead": lead,
                "kids": kids,
                "kind": _section_kind(h2),
            }
        )

    # 同號章節去重：保留內容較長者，再依編號排序
    by_num: dict[str, dict] = {}
    no_num: list[dict] = []
    for sec in sections:
        m = re.match(r"(\d+\.\d+)", sec["title"])
        if not m:
            no_num.append(sec)
            continue
        key = m.group(1)
        score = len(sec.get("lead") or "") + sum(len(k.get("body") or "") for k in sec.get("kids") or [])
        prev = by_num.get(key)
        if not prev or score > prev["_score"]:
            sec = dict(sec)
            sec["_score"] = score
            by_num[key] = sec
    ordered = sorted(by_num.values(), key=lambda s: [int(x) for x in re.match(r"(\d+)\.(\d+)", s["title"]).groups()])
    for s in ordered:
        s.pop("_score", None)
    sections = ordered + no_num
    preface = "\n".join(preface_buf).strip()
    return title, sections, preface


def _section_kind(title: str) -> str:
    t = title.lower()
    if "練習" in title or "測驗" in title:
        return "quiz"
    if "結語" in title or "前言" in title:
        return "meta"
    if "小百科" in title or "實務" in title:
        return "tips"
    if "國際" in title or "比較" in title:
        return "compare"
    return "lecture"


def _extract_chips(title: str, sections: list[dict]) -> list[str]:
    chips: list[str] = ["公司治理"]
    # 從章名抽關鍵詞
    for key in ("董事", "股東", "審計", "薪資", "併購", "揭露", "內線", "永續", "ESG", "委託書", "守則"):
        if key in title or any(key in s["title"] for s in sections):
            chips.append(key)
    for s in sections:
        if s["kind"] == "quiz":
            chips.append("練習題")
            break
    # 去重保序
    out, seen = [], set()
    for c in chips:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:8]


def _render_chips(items: list[str]) -> str:
    bits = ['<div class="chip-row">']
    for i, x in enumerate(items):
        bits.append(f'<span class="tag-chip {CHIP_ACCENTS[i % len(CHIP_ACCENTS)]}">{_esc(x)}</span>')
    bits.append("</div>")
    return "\n".join(bits)


def _enhance_quiz_html(block: str) -> str:
    def repl(m: re.Match[str]) -> str:
        ans = m.group(1).strip()
        return (
            '<div class="ans-row">'
            '<button type="button" class="ans-btn" data-reveal-answer aria-pressed="false">顯示解答</button>'
            f'<div class="ans-box is-masked" data-secret-box>'
            f'<span class="ans-text">{_esc(ans)}</span></div></div>'
        )

    block = re.sub(
        r"(?m)^(?:<li>|<p>)?\s*(?:解答|答案)\s*[：:]\s*(.+?)\s*(?:</li>|</p>)?$",
        lambda m: repl(m) if m.group(1) else m.group(0),
        block,
    )
    block = re.sub(r"(?:解答|答案)\s*[：:]\s*([^<\n]+)", lambda m: repl(m), block)
    return block


def _short_bullets_to_chips(md_html: str) -> str:
    """短清單改 chips；但含年份／對照的清單留給表格處理，不轉 chips。"""

    def convert_ul(m: re.Match[str]) -> str:
        inner = m.group(1)
        items = re.findall(r"<li>(.*?)</li>", inner, flags=re.S)
        plain = [re.sub(r"<[^>]+>", "", x).strip() for x in items]
        if not plain or any(len(x) > 42 for x in plain) or len(plain) > 10:
            return m.group(0)
        # 有年份或長對照句 → 不轉 chips
        if any(re.search(r"(19|20)\d{2}|民國\s*\d+|第?\d+條|vs\.?|／|對照", x) for x in plain):
            return m.group(0)
        return _render_chips(plain)

    return re.sub(r"<ul>\s*(.*?)\s*</ul>", convert_ul, md_html, flags=re.S)


_YEAR_LINE = re.compile(
    r"(?m)^\s*(?:[\*\-]\s+)?"
    r"\*?\*?(?P<when>"
    r"(?:民國\s*)?\d{2,4}\s*年(?:\s*\d{1,2}\s*月)?(?:起)?"
    r"|(?:19|20)\d{2}\s*年(?:\s*\d{1,2}\s*月)?(?:起)?"
    r"|(?:19|20)\d{2}"
    r")\*?\*?\s*[：:]\s*(?P<what>.+?)\s*$"
)


def _extract_timeline(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _YEAR_LINE.finditer(text or ""):
        when = re.sub(r"\s+", "", m.group("when"))
        what = re.sub(r"\*+", "", m.group("what")).strip(" 。；;")
        what = re.sub(r"\s+", " ", what)
        if len(what) < 4:
            continue
        key = when + "|" + what[:40]
        if key in seen:
            continue
        seen.add(key)
        rows.append({"when": when, "what": what[:160]})
    # 也抓「於YYYY年…」敘述句
    for m in re.finditer(
        r"(?:於|自|迄|到)?\s*((?:民國\s*)?(?:19|20)?\d{2,3}\s*年(?:\s*\d{1,2}\s*月)?)\s*([^。\n]{6,80})",
        text or "",
    ):
        when = re.sub(r"\s+", "", m.group(1))
        what = re.sub(r"\*+", "", m.group(2)).strip(" ，,：:")
        if re.match(r"^(發布|訂定|修正|推動|成立|公布|實施|施行|增訂|通過)", what) or "藍圖" in what or "辦法" in what:
            key = when + "|" + what[:40]
            if key not in seen and len(what) >= 6:
                seen.add(key)
                rows.append({"when": when, "what": what[:160]})
    # 依年份粗排序
    def sort_key(r: dict[str, str]):
        m = re.search(r"(\d{2,4})", r["when"])
        y = int(m.group(1)) if m else 0
        if y < 200:  # 民國年
            y += 1911
        return y

    rows.sort(key=sort_key)
    return rows[:20]


def _extract_evolution(text: str, title: str = "") -> list[dict[str, str]]:
    """演進／藍圖／階段：編號清單或『第N階段』。"""
    rows: list[dict[str, str]] = []
    # 編號清單
    for m in re.finditer(r"(?m)^\s*(?:(\d+)[\.、\)]\s*|(?:第\s*([一二三四五六七八九十\d]+)\s*(?:大)?(?:主軸|階段|點)))\s*(.+?)\s*$", text or ""):
        n = m.group(1) or m.group(2) or ""
        body = re.sub(r"\*+", "", m.group(3)).strip()
        if len(body) < 4:
            continue
        rows.append({"stage": f"階段 {n}" if n else f"步驟 {len(rows)+1}", "content": body[:160]})
    # 「從A到B／延伸」句
    if not rows and re.search(r"演進|發展|藍圖|從.+到|延伸", title + text[:80]):
        for m in re.finditer(r"(从|從)?([^，。；]{4,30})(到|至|→|->|延伸)([^，。；]{4,40})", text or ""):
            rows.append({"stage": "演進", "content": f"{m.group(2).strip()} → {m.group(4).strip()}"})
    # 去重
    out, seen = [], set()
    for r in rows:
        k = r["stage"] + r["content"][:30]
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out[:12]


def _extract_compare_rows(text: str) -> tuple[list[str], list[list[str]]]:
    """從既有 markdown table 或『A／B』句抽出對照列。"""
    # markdown pipe tables
    blocks = re.findall(r"(?:^\|.+\|\s*\n)+", text or "", flags=re.M)
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip().startswith("|")]
        if len(lines) < 2:
            continue
        def cells(ln: str) -> list[str]:
            parts = [c.strip() for c in ln.strip("|").split("|")]
            return [re.sub(r"\*+", "", c) for c in parts]
        header = cells(lines[0])
        # skip separator
        data_lines = [ln for ln in lines[1:] if not re.match(r"^\|?\s*:?-{2,}", ln)]
        rows = [cells(ln) for ln in data_lines]
        rows = [r for r in rows if any(r) and not all(re.fullmatch(r":?-{2,}:?", c or "") for c in r)]
        if header and rows:
            # normalize width
            w = len(header)
            rows = [(r + [""] * w)[:w] for r in rows]
            return header, rows[:12]

    # 「傳統內部人／準內部人」類對照、左右句
    rows2: list[list[str]] = []
    for m in re.finditer(
        r"(?m)^\s*[\*\-]?\s*\*?\*?([^*\n：:]{2,24})\*?\*?[：:]\s*(.+)$",
        text or "",
    ):
        left, right = m.group(1).strip(), re.sub(r"\*+", "", m.group(2)).strip()
        if re.search(r"(19|20)\d{2}", left):
            continue  # 留給時序
        if len(right) >= 4:
            rows2.append([left, right[:140]])
    if len(rows2) >= 2:
        return ["項目", "說明／對照"], rows2[:12]
    return [], []


def _render_struct_table(
    caption: str,
    headers: list[str],
    rows: list[list[str]],
    kind: str = "timeline",
) -> str:
    if not rows:
        return ""
    kind_cls = {
        "timeline": "table-timeline",
        "compare": "table-compare",
        "evolve": "table-evolve",
    }.get(kind, "table-struct")
    label = {"timeline": "時序表", "compare": "對照表", "evolve": "演進表"}.get(kind, "結構表")
    bits = [
        f'<div class="struct-table {kind_cls}">',
        f'<div class="struct-cap"><span class="struct-badge">{label}</span>{_esc(caption)}</div>',
        '<div class="table-responsive"><table class="table table-sm align-middle mb-0"><thead><tr>',
    ]
    bits.extend(f"<th>{_esc(h)}</th>" for h in headers)
    bits.append("</tr></thead><tbody>")
    for r in rows:
        bits.append("<tr>")
        bits.extend(f"<td>{_esc(c)}</td>" for c in r)
        bits.append("</tr>")
    bits.append("</tbody></table></div></div>")
    return "\n".join(bits)


def _section_struct_tables(sec: dict) -> str:
    """依本節內容產生時序／對照／演進表。"""
    blob = (sec.get("lead") or "") + "\n"
    for k in sec.get("kids") or []:
        blob += f"{k.get('title','')}\n{k.get('body','')}\n"
    title = sec.get("title") or ""
    parts: list[str] = []

    timeline = _extract_timeline(blob)
    short_title = re.sub(r"^\d+[\.．]\d+\s*[|｜]?\s*", "", title)
    # 標題含發展／歷程／沿革優先當時序
    if timeline and (len(timeline) >= 2 or re.search(r"發展|歷程|沿革|年表|時序", title)):
        parts.append(
            _render_struct_table(
                f"{short_title}｜時序",
                ["時點", "事件／規範重點"],
                [[r["when"], r["what"]] for r in timeline],
                "timeline",
            )
        )

    headers, rows = _extract_compare_rows(blob)
    if headers and rows and (
        sec.get("kind") == "compare"
        or len(rows) >= 2
        or "對照" in title
        or "比較" in title
        or "|" in blob
    ):
        if not all(re.search(r"(19|20)\d{2}|年", r[0]) for r in rows if r):
            parts.append(
                _render_struct_table(f"{short_title}｜對照", headers, rows, "compare")
            )

    if re.search(r"演進|藍圖|主軸|未來發展|階段", title) or sec.get("kind") in ("compare", "lecture"):
        evo = _extract_evolution(blob, title)
        if len(evo) >= 2:
            parts.append(
                _render_struct_table(
                    f"{short_title}｜演進／架構",
                    ["階段", "重點內容"],
                    [[r["stage"], r["content"]] for r in evo],
                    "evolve",
                )
            )
    return "\n".join(parts)


def _chapter_struct_bundle(title: str, sections: list[dict], preface: str) -> dict:
    """整章彙整：時序、對照、演進三大表。"""
    blob = (preface or "") + "\n"
    for s in sections:
        blob += (s.get("lead") or "") + "\n"
        for k in s.get("kids") or []:
            blob += (k.get("body") or "") + "\n"

    timeline = _extract_timeline(blob)
    # 合併各節 compare
    all_compare: list[tuple[list[str], list[list[str]]]] = []
    for s in sections:
        b = (s.get("lead") or "") + "\n" + "\n".join(k.get("body") or "" for k in s.get("kids") or [])
        h, rows = _extract_compare_rows(b)
        if h and rows:
            all_compare.append((h, rows))
    # 演進：優先標題含藍圖／演進的節
    evo_rows: list[dict[str, str]] = []
    for s in sections:
        if re.search(r"演進|藍圖|未來|主軸|發展", s.get("title") or ""):
            evo_rows.extend(_extract_evolution((s.get("lead") or "") + "\n" + "\n".join(k.get("body") or "" for k in s.get("kids") or []), s["title"]))
    if not evo_rows:
        evo_rows = _extract_evolution(blob, title)

    return {
        "timeline": timeline,
        "compares": all_compare[:3],
        "evolution": evo_rows[:12],
    }



TOC_MARKS = ("◆", "◇", "›", "▹", "●", "○", "■", "□", "✦", "✧")


def _build_page_toc(sections: list[dict], *, href_prefix: str = "") -> str:
    """大章節下拉；底下小節用特殊字元目錄。"""
    if not sections:
        return '<p class="side-empty">尚無目錄</p>'
    bits: list[str] = []
    for sec in sections:
        kids = sec.get("kids") or []
        bits.append('<details class="toc-drop" open>')
        bits.append(
            f'<summary><a class="toc-sum-link" href="{_esc(href_prefix)}#{_esc(sec["id"])}" '
            f'data-nav-jump="{_esc(href_prefix)}">{_esc(sec["title"])}</a></summary>'
        )
        bits.append('<div class="toc-kids">')
        if kids:
            for j, k in enumerate(kids):
                mark = TOC_MARKS[j % len(TOC_MARKS)]
                bits.append(
                    f'<a class="toc-h3" href="{_esc(href_prefix)}#{_esc(k["id"])}" data-nav-jump="{_esc(href_prefix)}">'
                    f'<span class="toc-mark" aria-hidden="true">{mark}</span>'
                    f'<span class="toc-text">{_esc(k["title"])}</span></a>'
                )
        else:
            # 無 h3 時仍給一筆「本節」特殊字目錄
            mark = TOC_MARKS[0]
            bits.append(
                f'<a class="toc-h3" href="{_esc(href_prefix)}#{_esc(sec["id"])}" data-nav-jump="{_esc(href_prefix)}">'
                f'<span class="toc-mark" aria-hidden="true">{mark}</span>'
                f'<span class="toc-text">{_esc(sec["title"])}</span></a>'
            )
        bits.append("</div></details>")
    return "\n".join(bits)


def _build_book_sidebar(
    books: list[tuple[str, str, list[dict]]],
    active_file: str,
) -> str:
    """左側藍欄：各大章下拉 + 特殊字元小目錄（無首頁目錄）。"""
    bits = [
        '<div class="side-brand-block">'
        '<div class="side-brand">公司治理</div>'
        '<div class="side-sub">詳盡學習講義</div>'
        '<a class="side-home" href="../index.html">← 筆記首頁</a>'
        "</div>"
    ]
    for title, out_name, sections in books:
        is_active = out_name == active_file
        open_attr = " open" if is_active else ""
        bits.append(f'<details class="chap-drop{" active-chap" if is_active else ""}"{open_attr}>')
        bits.append(
            f'<summary><a class="chap-sum-link" href="{_esc(out_name)}">{_esc(title)}</a></summary>'
        )
        bits.append('<div class="toc-kids">')
        if not sections:
            bits.append(
                f'<a class="toc-h3" href="{_esc(out_name)}">'
                f'<span class="toc-mark">◆</span><span class="toc-text">進入本章</span></a>'
            )
        else:
            for j, sec in enumerate(sections):
                mark = TOC_MARKS[j % len(TOC_MARKS)]
                bits.append(
                    f'<a class="toc-h3 toc-sec" href="{_esc(out_name)}#{_esc(sec["id"])}" '
                    f'data-nav-jump="{_esc(out_name)}">'
                    f'<span class="toc-mark">{mark}</span>'
                    f'<span class="toc-text">{_esc(sec["title"])}</span></a>'
                )
                for k_i, kid in enumerate(sec.get("kids") or []):
                    kmark = TOC_MARKS[(j + k_i + 1) % len(TOC_MARKS)]
                    bits.append(
                        f'<a class="toc-h3 toc-sub" href="{_esc(out_name)}#{_esc(kid["id"])}" '
                        f'data-nav-jump="{_esc(out_name)}">'
                        f'<span class="toc-mark">{kmark}</span>'
                        f'<span class="toc-text">{_esc(kid["title"])}</span></a>'
                    )
        bits.append("</div></details>")
    return "\n".join(bits)


def _plain(text: str) -> str:
    s = re.sub(r"<[^>]+>", "", text or "")
    s = re.sub(r"\*+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _first_sentences(text: str, n: int = 2, limit: int = 160) -> str:
    plain = _plain(text)
    if not plain:
        return ""
    parts = re.split(r"(?<=[。！？])\s*", plain)
    out = "".join(parts[:n]).strip()
    if len(out) > limit:
        out = out[: limit - 1] + "…"
    return out


def _extract_key_points(sec: dict) -> list[str]:
    """從段落／清單抽出可讀的關鍵知識點。"""
    points: list[str] = []
    blob = (sec.get("lead") or "") + "\n"
    for k in sec.get("kids") or []:
        blob += (k.get("body") or "") + "\n"
    # 粗體短句
    for m in re.finditer(r"\*\*([^*]{4,48})\*\*", blob):
        s = m.group(1).strip(" ：:")
        if s and s not in points:
            points.append(s)
    # 清單項
    for m in re.finditer(r"(?m)^\s*[\*\-]\s+(.+)$", blob):
        s = re.sub(r"\*\*", "", m.group(1)).strip()
        if 6 <= len(s) <= 60 and s not in points:
            points.append(s)
    # 編號項
    for m in re.finditer(r"(?m)^\s*\d+[\.、]\s+(.+)$", blob):
        s = re.sub(r"\*\*", "", m.group(1)).strip()
        if 6 <= len(s) <= 70 and s not in points:
            points.append(s)
    if not points:
        tip = _first_sentences(blob, 1, 70)
        if tip:
            points.append(tip)
    return points[:5]


def _enrich_lecture(title: str, sections: list[dict], preface: str) -> dict:
    """整理成講義資料架構：目標／摘要／里程碑／分節知識點。"""
    lecture_secs = [s for s in sections if s["kind"] != "quiz"]
    quiz_secs = [s for s in sections if s["kind"] == "quiz"]

    goals: list[str] = []
    for s in lecture_secs[:4]:
        short = re.sub(r"^\d+[\.．]\d+\s*[|｜]?\s*", "", s["title"])
        goals.append(f"能說明「{short}」的重點")
    if quiz_secs:
        goals.append("能完成本章練習題並核對解答")

    summary: list[str] = []
    if preface:
        summary.append(_first_sentences(preface, 2, 140))
    for s in lecture_secs[:5]:
        tip = _first_sentences(s.get("lead") or (s["kids"][0]["body"] if s.get("kids") else ""), 1, 120)
        if tip:
            summary.append(tip)
    summary = [x for x in summary if x][:6]

    milestones = []
    for i, s in enumerate(lecture_secs, 1):
        milestones.append(
            {
                "label": re.sub(r"^\d+[\.．]\d+\s*[|｜]?\s*", "", s["title"])[:22],
                "desc": _first_sentences(s.get("lead") or "", 1, 70)
                or (s["kids"][0]["title"] if s.get("kids") else "進入本節"),
                "chapter": i,
                "id": s["id"],
            }
        )

    for i, s in enumerate(lecture_secs, 1):
        s["key_points"] = _extract_key_points(s)
        short = re.sub(r"^\d+[\.．]\d+\s*[|｜]?\s*", "", s["title"])
        s["milestone"] = f"站 {i}｜{short}"
    for s in quiz_secs:
        s["key_points"] = _extract_key_points(s)
        s["milestone"] = "課後練習"

    return {
        "goals": goals[:5],
        "summary": summary,
        "milestones": milestones,
        "lecture_secs": lecture_secs,
        "quiz_secs": quiz_secs,
        "structs": _chapter_struct_bundle(title, lecture_secs, preface),
    }


def _strip_year_bullets(text: str) -> str:
    """已轉成時序表的年份清單，從正文移除避免重複。"""
    if not text:
        return ""
    return _YEAR_LINE.sub("", text)


def _render_body_with_callouts(md_text: str) -> str:
    """把段落整理成較好讀的 callout／清單。"""
    if not (md_text or "").strip():
        return ""
    html_block = _short_bullets_to_chips(_md_block(md_text))
    html_block = re.sub(
        r"<p>((?:注意|提醒|警告|重要)[：:].+?)</p>",
        r'<div class="callout callout-warn"><div class="callout-label">注意</div><div class="callout-body">\1</div></div>',
        html_block,
        flags=re.S,
    )
    return html_block


def _render_section_block(sec: dict, index: int) -> str:
    mid = sec.get("milestone") or f"第 {index} 站"
    parts = [
        f'<article class="sec-block" id="{_esc(sec["id"])}">',
        f'<div class="sec-kicker">{_esc(mid)}</div>',
        f'<div class="sec-head"><span class="sec-num">{index}</span>'
        f'<h2 class="sec-title">{_esc(sec["title"])}</h2></div>',
    ]
    kind_chip = {
        "meta": "導讀／收束",
        "quiz": "練習檢核",
        "tips": "實務小百科",
        "compare": "比較對照",
        "lecture": "核心講義",
    }.get(sec.get("kind") or "lecture", "核心講義")
    parts.append(_render_chips([kind_chip] + (sec.get("tags") or [])[:3]))

    narr = str(sec.get("narration") or "").strip()
    if not narr:
        narr = compose_from_ebook_section(sec)
    if narr:
        parts.append(
            render_narration_panel(
                narr, uid=sec.get("id") or f"sec-{index}", title="語音講解（適合用聽的）"
            )
        )

    # 結構表（時序／對照／演進）放在正文前，方便掃讀
    struct_html = _section_struct_tables(sec)
    if struct_html:
        parts.append(struct_html)

    lead = sec.get("lead") or ""
    # 若本節已有時序表，去掉年份清單避免重複
    if "table-timeline" in struct_html:
        lead = _strip_year_bullets(lead)

    if lead.strip():
        html_lead = _render_body_with_callouts(lead)
        if sec["kind"] == "quiz":
            html_lead = _enhance_quiz_html(html_lead)
        parts.append(f'<div class="sec-body">{html_lead}</div>')

    for kid in sec.get("kids") or []:
        parts.append(f'<section class="sub-sec" id="{_esc(kid["id"])}">')
        parts.append(f'<h3 class="subhead">{_esc(kid["title"])}</h3>')
        kid_narr = str(kid.get("narration") or "").strip()
        if not kid_narr:
            kid_narr = compose_from_ebook_kid(kid)
        if kid_narr:
            parts.append(
                render_narration_panel(
                    kid_narr,
                    uid=kid.get("id") or f"kid-{index}",
                    title="小節語音講解",
                )
            )
        kid_body = kid.get("body") or ""
        kid_html = _render_body_with_callouts(kid_body)
        if sec["kind"] == "quiz":
            kid_html = _enhance_quiz_html(kid_html)
        parts.append(kid_html)
        parts.append("</section>")

    kps = sec.get("key_points") or []
    if kps:
        parts.append('<div class="kp-box"><div class="callout-label">關鍵知識點</div>')
        parts.append(_render_chips(kps))
        parts.append("</div>")

    parts.append("</article>")
    return "\n".join(parts)


def _render_structs_tab(
    structs: dict, *, title: str = "", lecture_secs: list | None = None
) -> str:
    """圖表分頁：有資料才放結構表；互動圖表各自獨立一格。"""
    parts: list[str] = []
    tl = structs.get("timeline") or []
    if tl:
        parts.append(
            _render_struct_table(
                "全章時序總表",
                ["時點", "事件／規範重點"],
                [[r["when"], r["what"]] for r in tl],
                "timeline",
            )
        )

    comps = structs.get("compares") or []
    for i, (headers, rows) in enumerate(comps, 1):
        parts.append(_render_struct_table(f"對照表 {i}", headers, rows, "compare"))

    evo = structs.get("evolution") or []
    if evo:
        parts.append(
            _render_struct_table(
                "演進／架構總表",
                ["階段", "重點內容"],
                [[r["stage"], r["content"]] for r in evo],
                "evolve",
            )
        )

    payload = payload_from_ebook(
        title=title, structs=structs, lecture_secs=lecture_secs or []
    )
    static = "\n".join(parts)
    viz = render_viz_tab(payload)
    if static:
        return f'<div class="structs-wrap">{static}</div>\n{viz}'
    return viz


def _build_quick_cards(sections: list[dict]) -> str:
    cards = ['<div class="row g-3">']
    for i, sec in enumerate(sections, 1):
        if sec["kind"] == "quiz":
            continue
        kps = sec.get("key_points") or []
        cards.append('<div class="col-md-6">')
        cards.append('<div class="quick-card">')
        cards.append(f'<div class="quick-kicker">速查 · 第 {i} 節</div>')
        cards.append(f'<h3 class="h6">{_esc(sec["title"])}</h3>')
        if kps:
            cards.append("<ul class='mb-2 small'>")
            cards.extend(f"<li>{_esc(k)}</li>" for k in kps[:4])
            cards.append("</ul>")
        else:
            tip = _first_sentences(sec.get("lead") or "", 1, 90)
            if tip:
                cards.append(f'<p class="small text-secondary mb-2">{_esc(tip)}</p>')
        cards.append(f'<a class="small" href="#{_esc(sec["id"])}" data-jump-lecture>看完整講義</a>')
        cards.append("</div></div>")
    cards.append("</div>")
    return "\n".join(cards)


def _render_milestones(milestones: list[dict]) -> str:
    if not milestones:
        return ""
    bits = [
        '<section class="milestone-wrap" aria-label="學習里程碑">',
        '<div class="section-kicker">學習路徑</div>',
        '<h2 class="section-title">本章里程碑</h2>',
        '<ol class="milestone-track">',
    ]
    for i, m in enumerate(milestones, 1):
        bits.append(
            f'<li class="milestone-item">'
            f'<a class="milestone-link" href="#{_esc(m["id"])}" data-jump-lecture>'
            f'<span class="ms-dot">{i}</span>'
            f'<span class="ms-label">{_esc(m["label"])}</span>'
            f'<span class="ms-desc">{_esc(m["desc"])}</span>'
            f"</a></li>"
        )
    bits.append("</ol></section>")
    return "\n".join(bits)


def _render_path_cards(milestones: list[dict]) -> str:
    bits = ['<div class="path-cards">']
    for i, m in enumerate(milestones, 1):
        bits.append(
            f'<a class="path-card" href="#{_esc(m["id"])}" data-jump-lecture>'
            f'<div class="path-idx">站 {i}</div>'
            f'<div class="path-title">{_esc(m["label"])}</div>'
            f'<div class="path-desc">{_esc(m["desc"])}</div>'
            f'<div class="path-go">前往講義 →</div></a>'
        )
    bits.append("</div>")
    return "\n".join(bits)



def wrap_document(
    title: str,
    chips: list[str],
    sections: list[dict],
    preface: str,
    sidebar_html: str,
) -> str:
    stamp = _esc(datetime.now().strftime("%Y-%m-%d %H:%M"))
    meta = _enrich_lecture(title, sections, preface)
    lecture_secs = meta["lecture_secs"]
    quiz_secs = meta["quiz_secs"]
    milestones = meta["milestones"]

    lecture_html = "\n".join(_render_section_block(s, i) for i, s in enumerate(lecture_secs, 1))
    quiz_panel = (
        "\n".join(_render_section_block(s, i) for i, s in enumerate(quiz_secs, 1))
        if quiz_secs
        else '<p class="text-secondary">本篇沒有練習題。</p>'
    )

    overview: list[str] = [
        '<header class="lecture-hero">',
        '<span class="unit-badge">公司治理 · 詳盡講義</span>',
        f"<h1 class='note-title'>{_esc(title)}</h1>",
        _render_chips(chips),
        "</header>",
        _render_milestones(milestones),
    ]
    if meta["goals"]:
        overview.append('<section class="panel panel-mint mb-3"><h2 class="section-title">學習目標</h2><ul class="mb-0">')
        overview.extend(f"<li>{_esc(g)}</li>" for g in meta["goals"])
        overview.append("</ul></section>")
    if meta["summary"]:
        overview.append('<section class="mb-3"><h2 class="section-title">重點摘要</h2><div class="summary-chips">')
        for i, s in enumerate(meta["summary"]):
            overview.append(
                f'<div class="summary-chip {CHIP_ACCENTS[i % len(CHIP_ACCENTS)]}">{_esc(s)}</div>'
            )
        overview.append("</div></section>")
    overview.append(
        '<p class="tab-hint">建議路徑：總覽 → 圖表（時序／對照／演進）→ 學習路徑 → 章節講義 → 速查 → 練習。</p>'
    )
    # 總覽也放精簡時序預覽
    structs = meta.get("structs") or {}
    if structs.get("timeline"):
        overview.append(
            _render_struct_table(
                "本章時序速覽（完整見「圖表」分頁）",
                ["時點", "事件／規範重點"],
                [[r["when"], r["what"]] for r in structs["timeline"][:8]],
                "timeline",
            )
        )

    structs_panel = _render_structs_tab(
        structs, title=title, lecture_secs=lecture_secs
    )

    tabs_html = f"""
<div class="lecture-tabs">
  <ul class="nav nav-pills lecture-nav" role="tablist">
    <li class="nav-item" role="presentation"><button class="nav-link active" id="tab-overview-btn" data-bs-toggle="pill" data-bs-target="#tab-overview" type="button" role="tab">總覽</button></li>
    <li class="nav-item" role="presentation"><button class="nav-link" id="tab-charts-btn" data-bs-toggle="pill" data-bs-target="#tab-charts" type="button" role="tab">圖表</button></li>
    <li class="nav-item" role="presentation"><button class="nav-link" id="tab-path-btn" data-bs-toggle="pill" data-bs-target="#tab-path" type="button" role="tab">學習路徑</button></li>
    <li class="nav-item" role="presentation"><button class="nav-link" id="tab-lecture-btn" data-bs-toggle="pill" data-bs-target="#tab-lecture" type="button" role="tab">章節講義</button></li>
    <li class="nav-item" role="presentation"><button class="nav-link" id="tab-quick-btn" data-bs-toggle="pill" data-bs-target="#tab-quick" type="button" role="tab">速查卡片</button></li>
    <li class="nav-item" role="presentation"><button class="nav-link" id="tab-quiz-btn" data-bs-toggle="pill" data-bs-target="#tab-quiz" type="button" role="tab">練習</button></li>
  </ul>
  <div class="tab-content lecture-tab-content">
    <div class="tab-pane fade show active" id="tab-overview" role="tabpanel">{"".join(overview)}</div>
    <div class="tab-pane fade" id="tab-charts" role="tabpanel">{structs_panel}</div>
    <div class="tab-pane fade" id="tab-path" role="tabpanel">{_render_path_cards(milestones)}</div>
    <div class="tab-pane fade" id="tab-lecture" role="tabpanel">{lecture_html}</div>
    <div class="tab-pane fade" id="tab-quick" role="tabpanel">{_build_quick_cards(lecture_secs)}</div>
    <div class="tab-pane fade" id="tab-quiz" role="tabpanel">{quiz_panel}</div>
  </div>
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-bs-theme="dark">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>{_esc(title)}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" />
{HEAD_LINKS}
<style>
{EXTRA_CSS}
{NARRATION_CSS}
:root{{
  --bg:#0b0f14; --text:#e8eef7; --muted:#9fb0c6;
  --cyan:#5ec8ff; --mint:#3ee0a2; --amber:#ffc857; --coral:#ff7b72;
  --violet:#c3a6ff; --sky:#6ee7f5; --side-w:320px; --side-blue:#0d2137;
}}
*{{box-sizing:border-box;}}
html,body{{height:100%;margin:0;}}
body{{
  background:
    radial-gradient(1100px 480px at 8% -8%, rgba(94,200,255,.12), transparent 55%),
    radial-gradient(900px 420px at 92% 0%, rgba(195,166,255,.10), transparent 50%),
    var(--bg);
  color:var(--text);
}}

.layout{{min-height:100vh;}}
.sidebar{{
  position:fixed; inset:0 auto 0 0; width:min(var(--side-w), 88vw); z-index:40;
  background:linear-gradient(180deg, #0a2744 0%, var(--side-blue) 40%, #0b1a2a 100%);
  border-right:1px solid rgba(94,200,255,.18);
  display:flex; flex-direction:column;
  transform:translateX(0); transition:transform .22s ease;
  box-shadow:8px 0 28px rgba(0,0,0,.25);
}}
body.side-collapsed .sidebar{{transform:translateX(-105%);}}
.side-scroll{{overflow:auto; -webkit-overflow-scrolling:touch; padding:.85rem .75rem 5rem; flex:1;}}
.side-brand-block{{padding:.35rem .45rem 0.85rem; border-bottom:1px solid rgba(94,200,255,.15); margin-bottom:.75rem;}}
.side-brand{{font-weight:850; font-size:1.05rem; color:#fff; letter-spacing:.04em;}}
.side-sub{{font-size:.75rem; color:rgba(158,200,230,.85); margin-top:.15rem;}}
.side-home{{
  display:inline-flex; margin-top:.55rem; font-size:.78rem; font-weight:700;
  color:var(--cyan); text-decoration:none;
}}
.side-home:hover{{color:#fff;}}
.chap-drop{{
  border:1px solid rgba(94,200,255,.14); border-radius:12px;
  background:rgba(8,24,40,.72); margin:0 0 .45rem; overflow:hidden;
}}
.chap-drop.active-chap{{border-color:rgba(94,200,255,.45); box-shadow:inset 3px 0 0 var(--cyan);}}
.chap-drop > summary{{
  list-style:none; cursor:pointer; padding:.55rem .65rem;
  display:flex; align-items:center; gap:.35rem;
  font-size:.84rem; font-weight:750; color:#e8f4ff;
}}
.chap-drop > summary::-webkit-details-marker{{display:none;}}
.chap-drop > summary::before{{content:"▸"; color:rgba(158,200,230,.7); width:1rem; flex:0 0 auto;}}
.chap-drop[open] > summary::before{{content:"▾"; color:var(--cyan);}}
.chap-sum-link{{color:inherit; text-decoration:none; flex:1; min-width:0; word-break:break-word;}}
.chap-sum-link:hover{{color:var(--cyan);}}
.toc-kids{{padding:0 .35rem .55rem .35rem; display:flex; flex-direction:column; gap:.08rem;}}
.toc-h3{{
  display:flex; align-items:flex-start; gap:.4rem; text-decoration:none; color:rgba(200,220,235,.88);
  font-size:.78rem; padding:.32rem .45rem; border-radius:8px; line-height:1.35;
}}
.toc-h3:hover{{background:rgba(94,200,255,.12); color:#fff;}}
.toc-sub{{padding-left:1.15rem; font-size:.74rem; color:rgba(170,195,215,.8);}}
.toc-mark{{flex:0 0 auto; width:1.1rem; text-align:center; color:var(--cyan); font-size:.85rem;}}
.toc-sub .toc-mark{{color:var(--amber); font-size:.78rem;}}
.toc-text{{flex:1; min-width:0; overflow-wrap:anywhere;}}
.edge-toggle{{
  position:fixed; left:calc(min(var(--side-w), 88vw) - 16px); top:max(12px, env(safe-area-inset-top));
  z-index:50; width:32px; height:32px; border-radius:10px;
  border:1px solid rgba(255,255,255,.14);
  background:rgba(13,33,55,.95); color:#fff; cursor:pointer;
  display:grid; place-items:center; transition:left .22s ease, opacity .2s ease;
}}
body.side-collapsed .edge-toggle{{display:none;}}
.burger-fab{{
  display:none; position:fixed;
  left:max(12px, env(safe-area-inset-left));
  top:max(12px, env(safe-area-inset-top));
  z-index:55; width:42px; height:42px; border-radius:12px;
  border:1px solid rgba(255,255,255,.14);
  background:linear-gradient(135deg,rgba(94,200,255,.45),rgba(62,224,162,.32));
  color:#071018; font-size:1.1rem; font-weight:800; cursor:pointer;
  box-shadow:0 8px 22px rgba(0,0,0,.35);
}}
body.side-collapsed .burger-fab{{display:grid; place-items:center;}}
.content{{margin-left:min(var(--side-w), 88vw); min-width:0; width:auto; transition:margin-left .22s ease;}}
body.side-collapsed .content{{margin-left:0;}}
.wrap{{max-width:980px; margin:0 auto; padding:1.25rem 1.15rem 3.2rem; overflow-x:clip;}}
body.side-collapsed .wrap{{padding-top:4.2rem;}}
.meta-line{{color:var(--muted); font-size:.82rem; margin-bottom:.9rem;}}
.backdrop{{display:none; position:fixed; inset:0; z-index:35; background:rgba(0,0,0,.45);}}
body.side-open-mobile .backdrop{{display:block;}}

@media (max-width:1100px){{
  :root{{ --side-w:280px; }}
  .milestone-track{{grid-template-columns:repeat(auto-fit,minmax(132px,1fr));}}
}}
@media (max-width:900px){{
  .sidebar{{
    width:min(86vw, 320px);
    transform:translateX(-105%);
    box-shadow:12px 0 40px rgba(0,0,0,.45);
  }}
  body.side-open-mobile .sidebar{{transform:translateX(0);}}
  body.side-collapsed .sidebar{{transform:translateX(-105%);}}
  /* 開啟時必須蓋過 collapsed，否則漢堡按了側欄仍關著 */
  body.side-collapsed.side-open-mobile .sidebar{{transform:translateX(0);}}
  .content{{margin-left:0 !important; width:100%;}}
  .edge-toggle{{display:none !important;}}
  .burger-fab{{display:grid !important; place-items:center;}}
  body.side-open-mobile .burger-fab{{opacity:1;}}
  .wrap{{
    padding:4.4rem max(.85rem, env(safe-area-inset-right))
            calc(2.5rem + env(safe-area-inset-bottom))
            max(.85rem, env(safe-area-inset-left));
  }}
  .note-title{{font-size:clamp(1.2rem, 5.5vw, 1.65rem);}}
  .lecture-nav{{
    display:flex; flex-wrap:nowrap; gap:.35rem;
    overflow-x:auto; -webkit-overflow-scrolling:touch;
    padding-bottom:.35rem; margin-bottom:.75rem;
    scrollbar-width:thin;
  }}
  .lecture-nav .nav-item{{flex:0 0 auto;}}
  .lecture-nav .nav-link{{padding:.38rem .75rem; font-size:.82rem; white-space:nowrap;}}
  .lecture-tab-content{{padding:.85rem .7rem 1.1rem; border-radius:12px;}}
  .milestone-track{{grid-template-columns:1fr 1fr; gap:.55rem;}}
  .path-cards{{grid-template-columns:1fr;}}
  .sec-head{{align-items:flex-start;}}
  .sec-title{{font-size:1.05rem; line-height:1.35;}}
  .sec-num{{flex:0 0 auto;}}
  .struct-table td:first-child{{white-space:normal; min-width:4.5rem;}}
  .struct-table table{{font-size:.8rem;}}
  .struct-cap{{flex-wrap:wrap; font-size:.86rem;}}
  .row.g-3 > [class*="col-"]{{flex:0 0 100%; max-width:100%;}}
  .ans-row{{flex-direction:column;}}
  .ans-box{{width:100%;}}
}}
@media (max-width:560px){{
  .milestone-track{{grid-template-columns:1fr;}}
  .chip-row{{gap:.35rem;}}
  .tag-chip{{font-size:.72rem; padding:.22rem .55rem;}}
  .summary-chip{{padding:.65rem .75rem; font-size:.9rem;}}
  .unit-badge{{font-size:.7rem;}}
  .ms-desc,.path-desc{{font-size:.74rem;}}
  .table-responsive{{margin:0 -.15rem; border-radius:0 0 12px 12px;}}
  .struct-table .table th,.struct-table .table td{{padding:.4rem .45rem;}}
}}
@media (min-width:901px){{
  body.side-open-mobile .backdrop{{display:none;}}
}}
@media (prefers-reduced-motion:reduce){{
  .sidebar,.content,.edge-toggle{{transition:none;}}
}}
@media print{{
  .sidebar,.burger-fab,.edge-toggle,.backdrop,.lecture-nav{{display:none !important;}}
  .content{{margin-left:0 !important;}}
  .wrap{{padding:0; max-width:100%;}}
  .tab-pane{{display:block !important; opacity:1 !important;}}
}}

.lecture-hero{{margin-bottom:1rem;}}
.unit-badge{{display:inline-block;font-size:.75rem;font-weight:800;padding:.28rem .7rem;border-radius:999px;background:linear-gradient(135deg,rgba(94,200,255,.25),rgba(195,166,255,.25));border:1px solid rgba(255,255,255,.1);margin-bottom:.55rem;}}
.note-title{{font-weight:780;line-height:1.28;font-size:clamp(1.4rem,3vw,1.95rem);margin:0 0 .7rem;}}
.chip-row{{display:flex;flex-wrap:wrap;gap:.45rem;margin:.35rem 0 1rem;}}
.tag-chip{{display:inline-flex;align-items:center;padding:.28rem .7rem;border-radius:999px;font-size:.78rem;font-weight:650;border:1px solid transparent;background:rgba(18,24,33,.95);}}
.chip-cyan{{border-color:rgba(94,200,255,.4);box-shadow:inset 3px 0 0 var(--cyan);}}
.chip-mint{{border-color:rgba(62,224,162,.4);box-shadow:inset 3px 0 0 var(--mint);}}
.chip-amber{{border-color:rgba(255,200,87,.4);box-shadow:inset 3px 0 0 var(--amber);}}
.chip-coral{{border-color:rgba(255,123,114,.4);box-shadow:inset 3px 0 0 var(--coral);}}
.chip-violet{{border-color:rgba(195,166,255,.4);box-shadow:inset 3px 0 0 var(--violet);}}
.chip-sky{{border-color:rgba(110,231,245,.4);box-shadow:inset 3px 0 0 var(--sky);}}
.summary-chips{{display:flex;flex-direction:column;gap:.55rem;}}
.summary-chip{{border-radius:12px;padding:.75rem .95rem;border:1px solid transparent;background:rgba(18,24,33,.9);line-height:1.55;}}
.panel{{background:rgba(18,24,33,.88);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:1rem 1.1rem;}}
.panel-mint{{border-left:4px solid var(--mint);}}
.section-kicker{{font-size:.75rem;font-weight:800;letter-spacing:.08em;color:var(--cyan);margin-bottom:.25rem;}}
.section-title{{font-size:1.1rem;font-weight:720;margin-bottom:.7rem;}}
.tab-hint{{color:var(--muted);font-size:.9rem;}}
.milestone-wrap{{margin:0 0 1.2rem;}}
.milestone-track{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.7rem;}}
.milestone-link{{display:flex;flex-direction:column;gap:.3rem;height:100%;padding:.8rem .85rem;border-radius:14px;text-decoration:none;color:inherit;background:rgba(16,22,30,.92);border:1px solid rgba(255,255,255,.08);}}
.milestone-link:hover{{border-color:rgba(94,200,255,.45);color:inherit;}}
.ms-dot{{width:1.6rem;height:1.6rem;border-radius:999px;display:grid;place-items:center;font-size:.78rem;font-weight:800;color:#071018;background:linear-gradient(135deg,var(--cyan),var(--mint));}}
.ms-label{{font-weight:720;font-size:.92rem;}}
.ms-desc{{font-size:.76rem;color:var(--muted);line-height:1.4;}}
.path-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.8rem;}}
.path-card{{display:block;padding:1rem;border-radius:14px;text-decoration:none;color:inherit;background:rgba(16,22,30,.95);border:1px solid rgba(255,255,255,.08);}}
.path-card:hover{{border-color:rgba(195,166,255,.5);color:inherit;}}
.path-idx{{font-size:.75rem;font-weight:800;color:var(--violet);}}
.path-title{{font-weight:720;margin:.25rem 0;}}
.path-desc{{font-size:.82rem;color:var(--muted);}}
.path-go{{margin-top:.5rem;font-size:.82rem;color:var(--cyan);}}
.lecture-nav{{gap:.4rem;margin-bottom:1rem;flex-wrap:wrap;}}
.lecture-nav .nav-link{{border-radius:999px;color:var(--muted);background:rgba(18,24,33,.8);border:1px solid rgba(255,255,255,.08);padding:.4rem .9rem;}}
.lecture-nav .nav-link.active{{color:#071018;background:linear-gradient(135deg,var(--cyan),var(--mint));border-color:transparent;font-weight:750;}}
.lecture-tab-content{{background:rgba(12,16,22,.45);border:1px solid rgba(255,255,255,.05);border-radius:16px;padding:1.1rem 1rem 1.4rem;}}
.sec-block{{padding:1rem 0 1.35rem;border-bottom:1px solid rgba(255,255,255,.06);scroll-margin-top:1.2rem;}}
.sec-block:last-child{{border-bottom:0;}}
.sec-kicker{{font-size:.72rem;font-weight:800;color:var(--amber);letter-spacing:.04em;margin-bottom:.3rem;}}
.sec-head{{display:flex;align-items:center;gap:.65rem;margin-bottom:.45rem;}}
.sec-num{{display:inline-grid;place-items:center;min-width:1.85rem;height:1.85rem;border-radius:999px;font-size:.9rem;font-weight:800;color:#071018;background:linear-gradient(135deg,var(--cyan),var(--mint));flex:0 0 auto;}}
.sec-title{{margin:0;font-size:1.15rem;font-weight:720;}}
.subhead{{font-size:1rem;font-weight:700;margin:1rem 0 .45rem;color:var(--sky);scroll-margin-top:1.2rem;}}
.sec-body p,.sec-body li,.sub-sec p,.sub-sec li{{line-height:1.75;color:#d7e2f0;overflow-wrap:anywhere;}}
.sec-body table,.sub-sec table{{width:100%;margin:1rem 0;border-collapse:collapse;font-size:.88rem;}}
.sec-body th,.sec-body td,.sub-sec th,.sub-sec td{{border:1px solid rgba(255,255,255,.12);padding:.45rem .55rem;}}
.sec-body th,.sub-sec th{{background:rgba(94,200,255,.12);}}
.sec-body blockquote,.sub-sec blockquote{{border-left:3px solid var(--violet);margin:1rem 0;padding:.4rem .9rem;color:var(--muted);background:rgba(195,166,255,.06);}}
.kp-box{{margin:.75rem 0 .2rem;padding:.75rem .85rem;border-radius:12px;border:1px dashed rgba(94,200,255,.35);background:rgba(94,200,255,.06);}}
.callout{{border-radius:14px;padding:.85rem 1rem;border:1px solid rgba(255,255,255,.08);background:rgba(16,22,30,.92);margin:.7rem 0;}}
.callout-label{{font-size:.75rem;font-weight:800;letter-spacing:.06em;margin-bottom:.3rem;color:var(--cyan);}}
.callout-warn{{border-color:rgba(255,200,87,.45);background:linear-gradient(135deg,rgba(255,200,87,.14),rgba(16,22,30,.95));}}
.callout-warn .callout-label{{color:var(--amber);}}
.quick-card{{padding:1rem;border-radius:14px;background:rgba(16,22,30,.95);border:1px solid rgba(255,255,255,.08);height:100%;}}
.quick-kicker{{font-size:.72rem;font-weight:800;color:var(--cyan);}}
.ans-row{{display:flex;flex-wrap:wrap;gap:.5rem;align-items:stretch;margin:.35rem 0 .7rem;}}
.ans-btn{{border-radius:10px;border:1px solid rgba(195,166,255,.4);background:rgba(195,166,255,.12);color:var(--violet);font-size:.82rem;font-weight:700;padding:.35rem .7rem;}}
.ans-box{{flex:1 1 180px;min-height:2.2rem;display:flex;align-items:center;padding:.4rem .7rem;border-radius:10px;border:1px solid rgba(255,255,255,.1);background:#0a0e14;font-family:ui-monospace,Consolas,monospace;}}
.ans-text{{color:var(--mint);overflow-wrap:anywhere;}}
.ans-box.is-masked .ans-text{{-webkit-text-security:disc;text-security:disc;color:var(--muted);user-select:none;}}
.struct-table{{margin:1rem 0 1.25rem;border:1px solid rgba(255,255,255,.08);border-radius:14px;overflow:hidden;background:rgba(16,22,30,.92);}}
.struct-cap{{display:flex;align-items:center;gap:.55rem;padding:.65rem .85rem;border-bottom:1px solid rgba(255,255,255,.08);font-weight:700;font-size:.92rem;}}
.struct-badge{{font-size:.72rem;font-weight:800;padding:.18rem .5rem;border-radius:999px;letter-spacing:.04em;}}
.table-timeline .struct-badge{{background:rgba(94,200,255,.18);color:var(--cyan);}}
.table-compare .struct-badge{{background:rgba(195,166,255,.18);color:var(--violet);}}
.table-evolve .struct-badge{{background:rgba(62,224,162,.16);color:var(--mint);}}
.struct-table .table-responsive{{overflow-x:auto; -webkit-overflow-scrolling:touch;}}
.struct-table table{{margin:0;--bs-table-bg:transparent;--bs-table-color:var(--text);font-size:.88rem;min-width:100%;}}
.struct-table thead th{{background:rgba(94,200,255,.1);color:#e8eef7;}}
.table-compare thead th{{background:rgba(195,166,255,.12);}}
.table-evolve thead th{{background:rgba(62,224,162,.1);}}
.struct-table td:first-child{{font-weight:700;color:var(--amber);vertical-align:top;}}
.table-compare td:first-child{{color:var(--violet);}}
.table-evolve td:first-child{{color:var(--mint);}}
.structs-wrap .struct-table{{margin-bottom:1.35rem;}}
</style>
</head>
<body>
<div class="backdrop" id="side-backdrop" hidden></div>
<button type="button" class="burger-fab" id="burger-fab" title="打開目錄" aria-label="打開目錄">☰</button>
<button type="button" class="edge-toggle" id="edge-toggle" title="收起目錄" aria-label="收起目錄">‹</button>
<div class="layout">
  <aside class="sidebar" id="sidebar" aria-label="左側目錄">
    <div class="side-scroll">{sidebar_html}</div>
  </aside>
  <div class="content">
    <main class="wrap">
      <p class="meta-line">公司治理講義 · 全套視覺化 · 里程碑／Tabs／Chips · {stamp}</p>
      {tabs_html}
    </main>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
{SCRIPT_TAGS}
<script>
(function(){{
  try {{
    if (window.mermaid) mermaid.initialize({{ startOnLoad: true, theme: "dark", securityLevel: "loose" }});
  }} catch (e) {{}}
}})();
</script>
<script>
(function(){{
  const body = document.body;
  const key = 'gov-ebook-side-collapsed';
  const backdrop = document.getElementById('side-backdrop');
  const mq = window.matchMedia('(max-width:900px)');
  const isMobile = () => mq.matches;
  const edge = document.getElementById('edge-toggle');
  const burger = document.getElementById('burger-fab');
  function setCollapsed(v){{
    body.classList.toggle('side-collapsed', !!v);
    try{{ localStorage.setItem(key, v ? '1' : '0'); }}catch(e){{}}
  }}
  function openMobile(v){{
    body.classList.toggle('side-open-mobile', !!v);
    if(backdrop) backdrop.hidden = !v;
    body.style.overflow = v ? 'hidden' : '';
    if(burger){{
      burger.setAttribute('aria-expanded', v ? 'true' : 'false');
      burger.title = v ? '關閉目錄' : '打開目錄';
      burger.setAttribute('aria-label', v ? '關閉目錄' : '打開目錄');
    }}
  }}
  function syncViewport(){{
    if(isMobile()){{
      setCollapsed(true);
      openMobile(false);
    }} else {{
      openMobile(false);
      try{{
        setCollapsed(localStorage.getItem(key)==='1');
      }}catch(e){{ setCollapsed(false); }}
    }}
  }}
  syncViewport();
  if(mq.addEventListener) mq.addEventListener('change', syncViewport);
  else if(mq.addListener) mq.addListener(syncViewport);
  if(edge) edge.addEventListener('click', ()=>{{ if(isMobile()) openMobile(false); else setCollapsed(true); }});
  if(burger) burger.addEventListener('click', (e)=>{{
    e.preventDefault();
    e.stopPropagation();
    if(isMobile()){{
      openMobile(!body.classList.contains('side-open-mobile'));
    }} else {{
      setCollapsed(false);
    }}
  }});
  if(backdrop) backdrop.addEventListener('click', ()=> openMobile(false));

  document.querySelectorAll('[data-nav-jump], [data-jump-lecture], .milestone-link, .path-card').forEach(a=>{{
    a.addEventListener('click', (e)=>{{
      const href = a.getAttribute('href')||'';
      const hashIdx = href.indexOf('#');
      if(hashIdx < 0) return;
      const hash = href.slice(hashIdx);
      const file = href.slice(0, hashIdx);
      const cur = decodeURIComponent(location.pathname.split('/').pop()||'');
      if(file && file !== cur) return;
      const btn = document.getElementById('tab-lecture-btn');
      if(btn && window.bootstrap){{
        e.preventDefault();
        bootstrap.Tab.getOrCreateInstance(btn).show();
        if(isMobile()) openMobile(false);
        setTimeout(()=>{{ const t=document.querySelector(hash); if(t) t.scrollIntoView({{behavior:'smooth', block:'start'}}); }}, 160);
      }}
    }});
  }});

  document.querySelectorAll('[data-reveal-answer]').forEach(btn=>{{
    btn.addEventListener('click', ()=>{{
      const row = btn.closest('.ans-row');
      const box = row && row.querySelector('[data-secret-box]');
      const show = btn.getAttribute('aria-pressed') !== 'true';
      if(box) box.classList.toggle('is-masked', !show);
      btn.setAttribute('aria-pressed', show ? 'true' : 'false');
      btn.textContent = show ? '隱藏解答' : '顯示解答';
    }});
  }});
}})();
</script>
{BOOT_SCRIPT}
<script>
{NARRATION_JS}
</script>
</body>
</html>
"""


def main() -> int:
    import shutil

    if not SRC_DIR.is_dir():
        print(f"missing: {SRC_DIR}")
        return 1
    files = sorted(SRC_DIR.glob("*.md"), key=_chapter_sort_key)

    legacy = ROOT / "notes" / "公司治理"
    if legacy.is_dir() and legacy.resolve() != OUT_DIR.resolve():
        old_cache = legacy / "_narrations.json"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        if old_cache.is_file() and not NARR_CACHE.is_file():
            shutil.copy2(old_cache, NARR_CACHE)
            print("migrated narrations cache")
        shutil.rmtree(legacy)
        print("removed legacy", legacy)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    parsed: list[tuple[str, str, list[dict], str]] = []
    narr_cache = _load_narration_cache()
    for i, path in enumerate(files, 1):
        text = path.read_text(encoding="utf-8")
        title, sections, preface = _parse_sections(text)
        _apply_narration_cache(sections, narr_cache)
        out_name = f"{ebook_slug(path.stem, i)}.html"
        parsed.append((title, out_name, sections, preface))

    books = [(t, n, secs) for t, n, secs, _ in parsed]

    # 移除首頁目錄：index 僅導向第一章
    first = parsed[0][1] if parsed else ""
    if first:
        (OUT_DIR / "index.html").write_text(
            "<!DOCTYPE html><html lang='zh-Hant'><head><meta charset='UTF-8'/>"
            f"<meta http-equiv='refresh' content='0;url={html.escape(first)}'/>"
            f"<title>導向講義</title></head><body>"
            f"<p>正在進入講義… <a href='{html.escape(first)}'>若未自動跳轉請點此</a></p>"
            "</body></html>\n",
            encoding="utf-8",
        )
        print("OK index.html ->", first)

    # 清掉舊的中文檔名 html
    for old in OUT_DIR.glob("*.html"):
        if old.name == "index.html":
            continue
        if not re.fullmatch(r"ch\d{2}\.html", old.name):
            old.unlink(missing_ok=True)

    for title, out_name, sections, preface in parsed:
        chips = _extract_chips(title, sections)
        doc = wrap_document(
            title,
            chips,
            sections,
            preface,
            _build_book_sidebar(books, out_name),
        )
        (OUT_DIR / out_name).write_text(doc, encoding="utf-8")
        print(f"OK {out_name}  sections={len(sections)}")

    print(f"done {len(parsed)} -> {OUT_DIR}")
    try:
        from build_notes_index import main as rebuild_notes_index

        rebuild_notes_index()
    except Exception as e:
        print("notes index skip:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

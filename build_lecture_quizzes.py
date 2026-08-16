# -*- coding: utf-8 -*-
"""為 _structured/*.json 建立課後測驗（知識點 + 關鍵數據／辨別點）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STRUCT = ROOT / "_structured"

NUM_RE = re.compile(
    r"(?P<label>[^\n。；，,]{0,24}?)"
    r"(?P<num>"
    r"\d+\s*[～~\-－至到]\s*\d+\s*萬(?:元)?"
    r"|\d+(?:\.\d+)?\s*%"
    r"|\d+\s*萬(?:元)?"
    r"|1\s*[～~]\s*\s*5\s*萬(?:元)?"
    r"|\d{1,3}(?:,\d{3})+\s*元"
    r"|\d+\s*元"
    r")"
)

DISC_PATTERNS = [
    (r"(書審|查帳)", "申報方式辨別：書審 vs 查帳的差異重點是？"),
    (r"(公司|行號).{0,8}(公司|行號)", "組織型態辨別：公司與行號的關鍵差異是？"),
    (r"(應登記|免登記)", "登記辨別：應登記與免登記的判斷關鍵是？"),
    (r"(扣抵|不可扣|不能扣)", "扣抵辨別：什麼情況可扣／不可扣？"),
    (r"(貨車|客貨|小客車|自用)", "車種辨別：哪類車較適合公司購車扣抵？"),
]


def _list(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def _norm_ans(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    s = s.replace("～", "~").replace("－", "-").replace("—", "-")
    return s


def _kp_question(title: str, kp: str) -> str:
    if "→" in kp or "->" in kp:
        left = kp.split("→")[0].split("->")[0].strip(" ：:")
        return f"請寫出「{left or title}」相關的完整對照／流程。"
    if "：" in kp or ":" in kp:
        head = re.split(r"[：:]", kp, 1)[0].strip()
        return f"「{head}」的正確關鍵表述是什麼？"
    short_t = title if len(title) <= 22 else title[:20] + "…"
    return f"關於「{short_t}」，本課的關鍵知識點是？"


def build_quiz(note: dict) -> dict:
    items: list[dict] = []
    seen_ans: set[str] = set()
    checklist_n = 0

    for i, ch in enumerate(_list(note.get("chapters")), 1):
        if not isinstance(ch, dict):
            continue
        title = str(ch.get("title") or f"第 {i} 章").strip()

        for kp in _list(ch.get("key_points")):
            s = str(kp).strip()
            key = "k:" + _norm_ans(s)
            if not s or key in seen_ans:
                continue
            seen_ans.add(key)
            items.append(
                {
                    "kind": "knowledge",
                    "topic": title[:20],
                    "question": _kp_question(title, s),
                    "answer": s,
                    "explain": f"出自第 {i} 章「{title}」關鍵知識點。",
                }
            )

        for ck in _list(ch.get("checklist")):
            if checklist_n >= 3:
                break
            s = str(ck).strip()
            key = "c:" + _norm_ans(s)
            if not s or key in seen_ans:
                continue
            if not re.search(r"能說出|能說明|能列出|能判斷|理解", s):
                continue
            seen_ans.add(key)
            checklist_n += 1
            items.append(
                {
                    "kind": "knowledge",
                    "topic": f"{title[:12]}・檢核",
                    "question": "學習檢核：完成本章後你應能做到哪一項？",
                    "answer": s,
                    "explain": f"第 {i} 章學習檢核。",
                }
            )

        chunks: list[str] = [str(ch.get("warning") or ""), str(ch.get("body") or "")]
        for n in _list(ch.get("notes")):
            chunks.append(str(n))
        for sec in _list(ch.get("sections")):
            if isinstance(sec, dict):
                chunks.extend(str(p) for p in _list(sec.get("paras")))
                chunks.extend(str(b) for b in _list(sec.get("bullets")))
        visual = ch.get("visual") if isinstance(ch.get("visual"), dict) else {}
        for it in _list(visual.get("items")):
            if isinstance(it, dict):
                chunks.append(f"{it.get('title', '')}：{it.get('text', '')}")
            else:
                chunks.append(str(it))
        for row in _list(visual.get("rows")):
            if isinstance(row, dict):
                chunks.append(f"{row.get('left', '')}／{row.get('right', '')}")

        blob = "\n".join(chunks)

        for m in NUM_RE.finditer(blob):
            raw_num = m.group("num").strip()
            num = re.sub(r"\s+", "", raw_num)
            label = (m.group("label") or "").strip(" ：:　")
            key = "d:" + _norm_ans(num)
            if len(num) < 2 or key in seen_ans:
                continue
            # 過濾章節編號噪音（如「第 3 章」）
            if re.fullmatch(r"\d+章?", num):
                continue
            seen_ans.add(key)
            hint = label[-18:] if label else title
            items.append(
                {
                    "kind": "data",
                    "topic": (hint or "關鍵數據")[:18],
                    "question": f"關鍵數據辨別：與「{hint or title}」相關的數字／區間是？",
                    "answer": num,
                    "explain": f"第 {i} 章「{title}」的關鍵數據。",
                }
            )

        # 辨別點（非純數字）：從 compare / fact 標題抽
        for it in _list(visual.get("items")):
            if not isinstance(it, dict):
                continue
            ht = str(it.get("title") or "").strip()
            tx = str(it.get("text") or "").strip()
            if not ht or not tx or len(tx) < 8:
                continue
            key = "disc:" + _norm_ans(ht)
            if key in seen_ans:
                continue
            seen_ans.add(key)
            items.append(
                {
                    "kind": "data",
                    "topic": ht[:18],
                    "question": f"關鍵辨別點：「{ht}」應如何理解？",
                    "answer": tx if len(tx) <= 80 else tx[:78] + "…",
                    "explain": f"第 {i} 章「{title}」視覺重點／辨別點。",
                }
            )

        for row in _list(visual.get("rows")):
            if not isinstance(row, dict):
                continue
            left = str(row.get("left") or "").strip()
            right = str(row.get("right") or "").strip()
            if not left or not right:
                continue
            key = "cmp:" + _norm_ans(left + right)
            if key in seen_ans:
                continue
            seen_ans.add(key)
            items.append(
                {
                    "kind": "data",
                    "topic": "對照辨別",
                    "question": f"對照辨別：當情況是「{left}」時，對應重點是？",
                    "answer": right,
                    "explain": f"第 {i} 章「{title}」compare 對照。",
                }
            )

    know = [x for x in items if x["kind"] == "knowledge"]
    data = [x for x in items if x["kind"] == "data"]
    # 知識最多 9、數據／辨別最多 9
    know = know[:9]
    data = data[:9]
    final: list[dict] = []
    while know or data:
        if know:
            final.append(know.pop(0))
        if data:
            final.append(data.pop(0))
        if len(final) >= 16:
            break

    return {
        "intro": "完成講義後自我檢核。答案預設以密碼樣式（圓點）隱藏，點「顯示答案」才揭曉。題型含：知識點、關鍵數據與辨別點。",
        "items": final,
    }


# 精修單元（覆蓋自動產生）
CURATED: dict[str, dict] = {
    "1-1 給創業者的財稅地圖：從個人到公司": {
        "intro": "完成講義後自我檢核。答案預設以密碼樣式隱藏，點「顯示答案」才揭曉。",
        "items": [
            {
                "kind": "knowledge",
                "topic": "學習地圖",
                "question": "創業者從個人到公司的三個歷程（依序）是什麼？",
                "answer": "籌備期 → 起步期 → 營運與節稅期",
                "explain": "本課主軸地圖；完成登記只是起點。",
            },
            {
                "kind": "data",
                "topic": "學習起點",
                "question": "已是公司負責人或行號老闆，講師建議從哪一段開始較有效？",
                "answer": "章節三起（營運單據／營業稅／營所稅）",
                "explain": "未登記者從第一章；已負責人可跳到營運稅務。",
            },
            {
                "kind": "knowledge",
                "topic": "登記原則",
                "question": "什麼情況下「原則上」應在開始營業前申請登記？",
                "answer": "有銷售行為",
                "explain": "營業稅法原則；細節另看起徵點。",
            },
            {
                "kind": "data",
                "topic": "免登記",
                "question": "什麼條件下規模較小者可能依法免登記？",
                "answer": "每月營業未達起徵點",
                "explain": "起徵點與組織選擇細節在後續章節。",
            },
            {
                "kind": "data",
                "topic": "未登記風險",
                "question": "未辦理登記，罰鍰金額大約落在哪個區間？",
                "answer": "1～5 萬元",
                "explain": "還可能被補稅及罰款；未登記≠沒風險。",
            },
            {
                "kind": "knowledge",
                "topic": "起步期",
                "question": "起步期要備齊的五大登記前決策是哪些？",
                "answer": "組織／名稱／資本額／地址／負責人勞健保",
                "explain": "完成登記後仍要進入稅務學習。",
            },
            {
                "kind": "knowledge",
                "topic": "營運期",
                "question": "營運後必學的三大稅務主題是？",
                "answer": "營業稅、營所稅、節稅",
                "explain": "建議順序：邏輯／單據 → 申報 → 節稅。",
            },
            {
                "kind": "data",
                "topic": "學習順序辨別",
                "question": "比起先蒐集「省稅撇步」，更建議的學習順序是？",
                "answer": "先懂單據與稅種邏輯，再談申報與節稅",
                "explain": "避免本末倒置。",
            },
        ],
    },
    "5-4 節稅解析 2：買車、買房該不該登記在公司名下？": {
        "intro": "完成講義後自我檢核。答案以密碼樣式隱藏；著重車種／扣抵／買房風險辨別。",
        "items": [
            {
                "kind": "knowledge",
                "topic": "先問清楚",
                "question": "為什麼「登記在公司名下」不一定能節稅？",
                "answer": "可能買時不能扣營業稅，賣時還要開發票",
                "explain": "要先分析進項、折舊與處分成本。",
            },
            {
                "kind": "data",
                "topic": "車種辨別",
                "question": "哪類車較適合以公司名義購車並爭取營業稅扣抵？",
                "answer": "貨車／客貨兩用車",
                "explain": "自用小客車通常不划算。",
            },
            {
                "kind": "data",
                "topic": "車種辨別",
                "question": "自用小客車以公司名義購買，常見問題是？",
                "answer": "營業稅多半不能扣，整體不划算",
                "explain": "車種決定能不能扣。",
            },
            {
                "kind": "knowledge",
                "topic": "油錢維修",
                "question": "油錢與維修費要扣抵，是否一定要把車登記成公司車？",
                "answer": "不必；只要合理且打統編即可評估扣抵",
                "explain": "用途合理比「掛公司名」更關鍵。",
            },
            {
                "kind": "data",
                "topic": "營所稅辨別",
                "question": "書審申報下，折舊對營所稅的影響通常如何？",
                "answer": "影響有限（相對查帳）",
                "explain": "查帳較有機會反映折舊效益。",
            },
            {
                "kind": "knowledge",
                "topic": "公司買房",
                "question": "公司買房除稅負外，還要特別留意哪些風險面向？",
                "answer": "房地合一、未來出售開發票、盈餘分配與貸款成數限制",
                "explain": "除非長期收租，否則多半不建議。",
            },
            {
                "kind": "data",
                "topic": "行動辨別",
                "question": "什麼情境下較不建議把房登記在公司名下？",
                "answer": "非長期收租、又未算清買／賣兩端稅務與貸款限制",
                "explain": "貿然登記常得不償失。",
            },
        ],
    },
}


def main() -> int:
    files = sorted(STRUCT.glob("*.json"))
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        stem = path.stem
        if stem in CURATED:
            data["quiz"] = CURATED[stem]
        else:
            data["quiz"] = build_quiz(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        items = data["quiz"]["items"]
        k = sum(1 for x in items if x["kind"] == "knowledge")
        print(f"OK {stem}  n={len(items)} knowledge={k} data={len(items)-k}")
    print(f"done {len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

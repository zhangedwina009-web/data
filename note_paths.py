# -*- coding: utf-8 -*-
"""講義輸出路徑：Vercel／網頁用 ASCII 安全檔名。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTES = ROOT / "notes"

# 資料夾：URL 用英文；畫面顯示中文
TAX_DIR_NAME = "simpany"
TAX_DIR_LABEL = "簡單開公司"
TAX_DIR = NOTES / TAX_DIR_NAME

EBOOK_DIR_NAME = "governance"
EBOOK_DIR_LABEL = "公司治理"
EBOOK_DIR = NOTES / EBOOK_DIR_NAME

FOLDER_LABELS = {
    TAX_DIR_NAME: TAX_DIR_LABEL,
    EBOOK_DIR_NAME: EBOOK_DIR_LABEL,
}


def tax_slug(stem: str) -> str:
    """『1-1 給創業者…』→『1-1』"""
    head = (stem or "").strip().split(" ", 1)[0].strip()
    if re.fullmatch(r"\d+-\d+", head):
        return head
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", head).strip("-")
    return safe or "note"


def ebook_slug(stem: str, index: int) -> str:
    """『第1章 …』→『ch01』"""
    m = re.search(r"第\s*(\d+)\s*章?", stem or "")
    n = int(m.group(1)) if m else index
    return f"ch{n:02d}"

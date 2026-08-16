# 筆記／任務工具箱

## 怎麼開

1. 安裝 [AutoHotkey v2](https://www.autohotkey.com/)
2. **雙擊根目錄 `啟動工具.ahk`**
3. 選：
   - **0** 首頁（新增筆記／瀏覽筆記）
   - **1** 腳本產生器（匯入 `[{存檔名稱, 素材連結}]`）
   - **2** 執行任務 JSON
   - **3** 取得按鈕座標
   - **4** 開 `output` 結果資料夾
   - **5** 筆記產生器伺服器（本機 Ollama → HTML 講義）
   - **6** 座標區塊連結爬取
   - **7** 瀏覽已生成筆記

也可直接開 `index.html`，或執行：

```bash
python note_generator_server.py
```

## 目錄結構

| 路徑 | 用途 |
|------|------|
| `index.html` | **入口**：新增筆記／瀏覽筆記 |
| `apps/` | 前端 UI（筆記產生器、腳本產生器） |
| `notes/` | 已生成講義 + `notes/index.html` 瀏覽頁 |
| `output/` | 爬蟲／截圖素材 |
| `tools/` | AutoHotkey 輔助腳本 |
| `docs/` | 說明與 JSON schema |
| `*.py` | 伺服器／轉換／重渲 |
| `_structured/` | 結構化筆記 JSON |
| `logs/` | 批次紀錄 |

## 主要檔案

| 檔案 | 用途 |
|------|------|
| `啟動工具.ahk` | 啟動選單 |
| `apps/ahk-script-generator.html` | 產生／匯入 JSON |
| `apps/note_generator.html` | 筆記產生器 UI |
| `note_generator_server.py` | 筆記產生器伺服器 |
| `build_notes_index.py` | 重建 `notes/index.html` |
| `run_task_json.py` | 執行 JSON（爬蟲／截圖等） |
| `link_block_scraper.py` | 座標區塊抓連結清單 |
| `examples/` | 範例任務 |
| `output/` | 爬蟲結果 |
| `notes/` | 教學筆記 HTML |

## 簡易 JSON 格式

```json
[
  {
    "存檔名稱": "課名",
    "素材連結": "https://..."
  }
]
```

產生器可再加上 `執行`；執行視窗可選 Chrome / Edge / Chromium / Firefox。

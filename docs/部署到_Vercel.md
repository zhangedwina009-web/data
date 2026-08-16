# 部署到 Vercel（靜態講義站）

本專案在 Vercel 上部署的是**靜態網頁**（`index.html`、`notes/`、`apps/`、`docs/`）。  
Python 伺服器、Ollama、AHK、爬蟲**不會**在 Vercel 上跑，請繼續在本機使用。

## 一鍵流程（建議）

1. 安裝 [Node.js](https://nodejs.org/) 與 [Vercel CLI](https://vercel.com/docs/cli)：
   ```bash
   npm i -g vercel
   ```
2. 在本機先重渲講義（可選，確保最新）：
   ```bash
   D:\system\Python310\python.exe rerender_all_notes.py
   D:\system\Python310\python.exe convert_ebook_md_to_html.py
   ```
3. 在專案根目錄登入並部署：
   ```bash
   cd "d:\AI_ause\project\code\腳本"
   vercel login
   vercel
   ```
4. 正式上線：
   ```bash
   vercel --prod
   ```

第一次會問專案名稱、是否連結 Git；選 **No**（只上傳目前目錄）也可以。

## 用 GitHub 自動部署

1. 把本資料夾推到 GitHub（勿提交 `output/`、`_structured/` 若含敏感內容可再調整）。
2. 到 [vercel.com](https://vercel.com) → **Add New Project** → Import 該 repo。
3. Framework Preset 選 **Other**；Build Command 留空；Output 用根目錄即可。
4. Deploy。之後每次 `git push` 會自動更新。

## 部署後網址

- 首頁：`https://你的專案.vercel.app/`
- 筆記瀏覽：`https://你的專案.vercel.app/notes/`
- 各講義：`/notes/簡單開公司/….html`、`/notes/公司治理/….html`

## 語音說明

朗讀用瀏覽器 **Web Speech**（非伺服器 AI）。  
**Google 中文語音**在 **Chrome** 最容易出現；請用 Chrome 開站，預設會優先選 Google。

## 不上線的功能

| 功能 | 原因 |
|------|------|
| 筆記產生器（Ollama） | 需本機 Python + Ollama |
| 任務 JSON／爬蟲／AHK | 需本機環境 |

本機仍用 `啟動工具.ahk` 或 `python note_generator_server.py`。

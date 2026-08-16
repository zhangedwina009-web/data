#Requires AutoHotkey v2.0
#SingleInstance Force

; ========================================
; 雙擊本檔啟動（請用 AutoHotkey v2 開啟）
; ========================================

Dir := A_ScriptDir
IndexHtml := Dir "\index.html"
GenHtml := Dir "\apps\ahk-script-generator.html"
NotesBrowse := Dir "\notes\index.html"
Runner := Dir "\run_task_json.py"
OutDir := Dir "\output"
ToolsDir := Dir "\tools"

PythonExe := FindPython()

MainGui := Gui("+AlwaysOnTop", "筆記／任務工具啟動器")
MainGui.SetFont("s11", "Microsoft JhengHei UI")
MainGui.AddText(, "選要開的功能：")
MainGui.AddText("c666666 w360", "建議先開「首頁」：可新增筆記或瀏覽已生成講義")

MainGui.AddButton("w360 h36", "0. 打開首頁（新增／瀏覽筆記）").OnEvent("Click", OpenIndex)
MainGui.AddButton("w360 h36", "1. 開啟腳本產生器（匯入 JSON）").OnEvent("Click", OpenGenerator)
MainGui.AddButton("w360 h36", "2. 執行任務 JSON（已開視窗）").OnEvent("Click", OpenRunner)
MainGui.AddButton("w360 h36", "3. 取得按鈕座標（F8）").OnEvent("Click", OpenCoord)
MainGui.AddButton("w360 h36", "4. 開啟結果資料夾 output").OnEvent("Click", OpenOutput)
MainGui.AddButton("w360 h36", "5. 教學筆記產生器伺服器（Ollama）").OnEvent("Click", OpenNotes)
MainGui.AddButton("w360 h36", "6. 座標區塊連結爬取（目錄→JSON）").OnEvent("Click", OpenLinkScraper)
MainGui.AddButton("w360 h36", "7. 瀏覽已生成筆記").OnEvent("Click", OpenBrowse)
MainGui.AddButton("w360 h32", "關閉").OnEvent("Click", (*) => ExitApp())

MainGui.AddText("c666666 w360", "Python：`n" (PythonExe ? PythonExe : "找不到，請先安裝 Python"))
MainGui.OnEvent("Close", (*) => ExitApp())
MainGui.Show()

OpenIndex(*) {
    global IndexHtml
    if !FileExist(IndexHtml) {
        MsgBox "找不到：`n" IndexHtml, "錯誤", "Iconx"
        return
    }
    Run IndexHtml
}

OpenBrowse(*) {
    global NotesBrowse, Dir, PythonExe
    ; 先重建索引再開
    idxPy := Dir "\build_notes_index.py"
    if PythonExe && FileExist(idxPy)
        RunWait Format('"{1}" "{2}"', PythonExe, idxPy), Dir, "Hide"
    if !FileExist(NotesBrowse) {
        MsgBox "找不到：`n" NotesBrowse "`n請先產生筆記或執行 build_notes_index.py", "錯誤", "Iconx"
        return
    }
    Run NotesBrowse
}

OpenGenerator(*) {
    global GenHtml
    if !FileExist(GenHtml) {
        MsgBox "找不到：`n" GenHtml, "錯誤", "Iconx"
        return
    }
    Run GenHtml
}

OpenRunner(*) {
    global Runner, PythonExe
    if !PythonExe {
        MsgBox "找不到 Python。`n請安裝 Python 3 後再試。", "錯誤", "Iconx"
        return
    }
    if !FileExist(Runner) {
        MsgBox "找不到：`n" Runner, "錯誤", "Iconx"
        return
    }
    Run Format('"{1}" "{2}"', PythonExe, Runner)
}

OpenCoord(*) {
    global ToolsDir
    f := ToolsDir "\取得滑鼠座標.ahk"
    if !FileExist(f) {
        MsgBox "找不到：`n" f, "錯誤", "Iconx"
        return
    }
    Run f
}

OpenOutput(*) {
    global OutDir
    if !DirExist(OutDir)
        DirCreate OutDir
    Run OutDir
}

OpenNotes(*) {
    global Dir, PythonExe
    f := Dir "\note_generator_server.py"
    if !PythonExe {
        MsgBox "找不到 Python。`n請安裝 Python 3 後再試。", "錯誤", "Iconx"
        return
    }
    if !FileExist(f) {
        MsgBox "找不到：`n" f, "錯誤", "Iconx"
        return
    }
    ; 啟動本機伺服器（會自動開瀏覽器到首頁）
    Run Format('"{1}" "{2}"', PythonExe, f), Dir
}

OpenLinkScraper(*) {
    global Dir, PythonExe
    f := Dir "\link_block_scraper.py"
    if !PythonExe {
        MsgBox "找不到 Python。`n請安裝 Python 3 後再試。", "錯誤", "Iconx"
        return
    }
    if !FileExist(f) {
        MsgBox "找不到：`n" f, "錯誤", "Iconx"
        return
    }
    Run Format('"{1}" "{2}"', PythonExe, f), Dir
}

FindPython() {
    candidates := [
        "D:\system\Python310\python.exe",
        EnvGet("LocalAppData") "\Programs\Python\Python312\python.exe",
        EnvGet("LocalAppData") "\Programs\Python\Python311\python.exe",
        EnvGet("LocalAppData") "\Programs\Python\Python310\python.exe",
    ]
    for p in candidates {
        if FileExist(p)
            return p
    }
    ; try py launcher
    try {
        shell := ComObject("WScript.Shell")
        exec := shell.Exec('py -3 -c "import sys; print(sys.executable)"')
        out := Trim(exec.StdOut.ReadAll())
        if out && FileExist(out)
            return out
    }
    return ""
}

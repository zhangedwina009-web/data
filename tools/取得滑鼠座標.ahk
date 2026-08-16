#Requires AutoHotkey v2.0
#SingleInstance Force

; ============================================================
; 取得按鈕座標（相對 Chrome／Edge 客戶區，不是這個小視窗）
;
; 1. 開好課程頁
; 2. 滑鼠移到「逐字稿」上
; 3. 按 F8
; 4. 把 X、Y 填進產生器
; Esc 結束
; ============================================================

CoordMode "Mouse", "Screen"

MainGui := Gui("+AlwaysOnTop", "取得按鈕座標")
MainGui.SetFont("s11", "Microsoft JhengHei UI")
MainGui.AddText("w400", "步驟：`n1. 開好 Chrome 課程頁`n2. 滑鼠移到「逐字稿」上（先不要點）`n3. 按 F8`n4. 填進產生器的座標 X / Y`n`n座標是相對「瀏覽器內容區」，不是這個工具視窗。")
MainGui.AddText("w400 c666666", "瀏覽器：")
browserText := MainGui.AddText("w400 vBrowser", "(尋找中…)")
MainGui.AddText("w400 c666666", "目前座標（相對瀏覽器）：")
xyText := MainGui.AddText("w400 h28 vXY", "移動滑鼠…")
MainGui.AddText("w400 c666666", "上次 F8：")
lastText := MainGui.AddText("w400 h50 vLast", "(尚未)")
MainGui.AddButton("w190", "複製上次座標").OnEvent("Click", CopyLast)
MainGui.AddButton("w190 xp+200", "結束").OnEvent("Click", (*) => ExitApp())
MainGui.OnEvent("Close", (*) => ExitApp())
MainGui.Show("x20 y20")

lastXY := ""
lastX := 0
lastY := 0

SetTimer WatchMouse, 80

WatchMouse() {
    global xyText, browserText
    hwnd := FindBrowserHwnd()
    if !hwnd {
        browserText.Value := "找不到 Chrome / Edge，請先打開瀏覽器"
        xyText.Value := "-"
        return
    }
    title := WinGetTitle(hwnd)
    if (StrLen(title) > 40)
        title := SubStr(title, 1, 40) "…"
    browserText.Value := title

    MouseGetPos &sx, &sy
    pt := ScreenToClientPt(hwnd, sx, sy)
    x := pt[1]
    y := pt[2]
    tip := "X = " x "　Y = " y
    if (x < 0 || y < 0)
        tip .= "　⚠ 在視窗外，請移到瀏覽器內容上"
    xyText.Value := tip
}

F8:: {
    global lastXY, lastX, lastY, lastText
    hwnd := FindBrowserHwnd()
    if !hwnd {
        MsgBox "找不到 Chrome / Edge 視窗。", "錯誤", "Iconx"
        return
    }
    MouseGetPos &sx, &sy
    pt := ScreenToClientPt(hwnd, sx, sy)
    x := pt[1]
    y := pt[2]
    if (x < 0 || y < 0) {
        MsgBox (
            "座標無效：X=" x " Y=" y "`n`n"
            "滑鼠不在瀏覽器內容區內。`n"
            "請把滑鼠移到「逐字稿」按鈕上再按 F8。`n"
            "（不要對著這個座標工具視窗按）"
        ), "座標無效", "Icon!"
        return
    }
    ; 也檢查是否超出客戶區
    WinGetClientPos , , &cw, &ch, hwnd
    if (x > cw || y > ch) {
        MsgBox "座標超出視窗範圍，請再對準按鈕按 F8。", "座標無效", "Icon!"
        return
    }

    lastX := x
    lastY := y
    lastXY := x "," y
    A_Clipboard := lastXY
    lastText.Value := "X = " x "`nY = " y "`n已複製：" lastXY
    TrayTip "已複製座標", "X=" x "  Y=" y, 3
    SoundBeep 1000, 80
}

CopyLast(*) {
    global lastXY, lastX, lastY
    if (lastXY = "") {
        MsgBox "請先把滑鼠移到按鈕上，按 F8。", "尚未取得", "Icon!"
        return
    }
    A_Clipboard := lastXY
    ; 也複製分行方便看
    A_Clipboard := lastX "`n" lastY
    Sleep 50
    A_Clipboard := lastXY
    TrayTip "已複製", lastXY, 2
}

Esc:: ExitApp

FindBrowserHwnd() {
    for exe in ["chrome.exe", "msedge.exe"] {
        for hwnd in WinGetList("ahk_exe " exe) {
            title := WinGetTitle(hwnd)
            if (title = "")
                continue
            if InStr(title, "DevTools")
                continue
            if InStr(title, "取得按鈕座標")
                continue
            return hwnd
        }
    }
    return 0
}

ScreenToClientPt(hwnd, sx, sy) {
    pt := Buffer(8, 0)
    NumPut("int", sx, pt, 0)
    NumPut("int", sy, pt, 4)
    DllCall("ScreenToClient", "ptr", hwnd, "ptr", pt)
    return [NumGet(pt, 0, "int"), NumGet(pt, 4, "int")]
}

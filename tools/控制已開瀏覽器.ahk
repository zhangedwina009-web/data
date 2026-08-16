#Requires AutoHotkey v2.0
#SingleInstance Off

; ============================================================
; 操控已開著的瀏覽器（不關閉、不重開）
;
; scrape：開 Console → 依 class 取 innerText → copy 到剪貼簿存檔
; ============================================================

cmd := A_Args.Length >= 1 ? Trim(StrLower(A_Args[1])) : ""
arg2 := A_Args.Length >= 2 ? A_Args[2] : ""
arg3 := A_Args.Length >= 3 ? A_Args[3] : ""
arg4 := A_Args.Length >= 4 ? A_Args[4] : ""

switch cmd {
case "activate":
    exe := arg2 != "" ? arg2 : "chrome.exe"
    ok := ActivateBrowser(exe)
    ExitApp ok ? 0 : 2

case "goto":
    url := arg2
    exe := arg3 != "" ? arg3 : "chrome.exe"
    if !ActivateBrowser(exe)
        ExitApp 2
    DoGoto(url)
    ExitApp 0

case "scrape":
    paramFile := arg2
    exe := arg3 != "" ? arg3 : "chrome.exe"
    outPath := arg4
    if !ActivateBrowser(exe)
        ExitApp 2
    ok := DoScrape(paramFile, outPath, exe)
    ExitApp ok ? 0 : 5

case "click":
    ; click <參數檔> [chrome.exe]
    paramFile := arg2
    exe := arg3 != "" ? arg3 : "chrome.exe"
    if !ActivateBrowser(exe)
        ExitApp 2
    ok := DoClick(paramFile)
    ExitApp ok ? 0 : 7

case "screenshot":
    exe := arg2 != "" ? arg2 : "chrome.exe"
    outPath := arg3 != "" ? arg3 : (A_Temp "\ahk_shot.bmp")
    if !ActivateBrowser(exe)
        ExitApp 2
    ok := CaptureClientToBmp(outPath)
    ExitApp ok ? 0 : 6

case "linklist":
    ; linklist <參數檔> [chrome.exe] [out.json]
    ; 參數檔：X\nY\n[向上找層數，預設 8]
    paramFile := arg2
    exe := arg3 != "" ? arg3 : "chrome.exe"
    outPath := arg4
    if !ActivateBrowser(exe)
        ExitApp 2
    ok := DoLinkList(paramFile, outPath, exe)
    ExitApp ok ? 0 : 8

default:
    SafeLog "ERR unknown cmd: [" cmd "] args=" A_Args.Length
    ExitApp 1
}

; 避免 FileAppend "*" 在無主控台時丟「控制代碼無效」
SafeLog(msg) {
    try FileAppend msg "`n", "*", "`n"
    catch {
        try FileAppend msg "`n", A_Temp "\ause_ahk_err.log", "UTF-8"
    }
}

SafeRestoreClip(clipSaved) {
    try {
        A_Clipboard := clipSaved
    } catch {
    }
}

ActivateBrowser(exe) {
    if !WinExist("ahk_exe " exe) {
        FileAppend "ERR no window`n", "*", "`n"
        return false
    }
    WinActivate "ahk_exe " exe
    if !WinWaitActive("ahk_exe " exe, , 5) {
        FileAppend "ERR cannot activate`n", "*", "`n"
        return false
    }
    Sleep 200
    return true
}

DoGoto(url) {
    if (url = "")
        return
    Send "^t"
    Sleep 300
    Send "^l"
    Sleep 180
    Send "^a"
    Sleep 40
    old := ClipboardAll()
    A_Clipboard := url
    ClipWait 1
    Send "^v"
    Sleep 100
    Send "{Enter}"
    Sleep 200
    Clipboard := old
}

; ---------- 座標區塊抓連結清單 ----------
; 參數檔：
;   X
;   Y
;   climb（可選，預設 8）
DoLinkList(paramFile, outPath := "", exe := "chrome.exe") {
    if (paramFile = "" || !FileExist(paramFile)) {
        SafeLog "ERR no param file"
        return false
    }
    raw := FileRead(paramFile, "UTF-8")
    raw := StrReplace(raw, "`r", "")
    lines := StrSplit(raw, "`n")
    try x := lines.Length >= 1 ? Integer(Trim(lines[1])) : 0
    catch
        x := 0
    try y := lines.Length >= 2 ? Integer(Trim(lines[2])) : 0
    catch
        y := 0
    try climb := lines.Length >= 3 && Trim(lines[3]) != "" ? Integer(Trim(lines[3])) : 8
    catch
        climb := 8
    if (x < 0 || y < 0 || (x = 0 && y = 0)) {
        SafeLog "ERR bad coords"
        return false
    }
    if (climb < 1)
        climb := 1
    if (climb > 20)
        climb := 20

    marker := "###AUSE_LINKLIST###"
    clipSaved := ClipboardAll()
    if !ActivateMainChrome(exe) {
        SafeLog "ERR no chrome for linklist"
        SafeRestoreClip clipSaved
        return false
    }
    Sleep 200

    text := ""
    try {
        loop 2 {
            Send "^+j"
            Sleep 1100
            if (A_Index = 1) {
                SendText "allow pasting"
                Sleep 80
                Send "{Enter}"
                Sleep 250
            }

            js := BuildLinkListJS(x, y, climb, marker)
            try A_Clipboard := js
            catch {
                Sleep 200
                try A_Clipboard := js
            }
            if !ClipWait(2)
                Sleep 200
            Sleep 100
            Send "^v"
            Sleep 280
            try A_Clipboard := ""
            Sleep 80
            Send "{Enter}"

            got := ""
            loop 30 {
                Sleep 180
                try cur := A_Clipboard
                catch
                    cur := ""
                if (cur = "")
                    continue
                if (InStr(cur, "elementFromPoint") && InStr(cur, "copy("))
                    continue
                if InStr(cur, marker) {
                    got := cur
                    break
                }
                if (InStr(cur, "ERR:") = 1) {
                    got := cur
                    break
                }
            }

            Sleep 100
            Send "{F12}"
            Sleep 250
            ActivateMainChrome(exe)

            if (got != "" && InStr(got, marker)) {
                text := got
                break
            }
            if (InStr(got, "ERR:") = 1) {
                text := got
                break
            }
            Sleep 500
        }
    } finally {
        SafeRestoreClip clipSaved
    }

    if (text = "" || InStr(text, "ERR:") = 1) {
        SafeLog "ERR linklist: " text
        return false
    }
    text := RegExReplace(text, "^\x{FEFF}?" marker "\r?\n?", "")
    text := Trim(text)
    if (text = "" || InStr(text, "ERR:") = 1) {
        SafeLog "ERR empty linklist"
        return false
    }
    if (InStr(text, "elementFromPoint") && InStr(text, "copy(")) {
        SafeLog "ERR got script not json"
        return false
    }

    if (outPath != "") {
        try FileDelete outPath
        try FileAppend text "`n", outPath, "UTF-8"
        catch as e {
            SafeLog "ERR write out: " e.Message
            return false
        }
    }
    return true
}

BuildLinkListJS(x, y, climb, marker) {
    return (
        "(() => {"
        . "try {"
        . "  const X = " x ";"
        . "  const Y = " y ";"
        . "  const CLIMB = " climb ";"
        . "  const marker = " QuoteJS(marker) ";"
        . "  function norm(s){return (s||'').replace(/\\s+/g,' ').trim();}"
        . "  function pickName(a){"
        . "    let n = norm(a.innerText) || norm(a.getAttribute('aria-label')) || norm(a.title) || norm(a.getAttribute('data-title'));"
        . "    if (!n) {"
        . "      const img = a.querySelector('img[alt]');"
        . "      if (img) n = norm(img.alt);"
        . "    }"
        . "    if (n.length > 140) n = n.slice(0,140);"
        . "    return n;"
        . "  }"
        . "  function absUrl(href){"
        . "    try { return new URL(href, location.href).href; } catch(e) { return href || ''; }"
        . "  }"
        . "  let el = document.elementFromPoint(X, Y);"
        . "  if (!el) { copy('ERR:NOPOINT'); return; }"
        . "  let best = el;"
        . "  let bestCount = 0;"
        . "  for (let i = 0; i <= CLIMB && el; i++) {"
        . "    const n = el.querySelectorAll ? el.querySelectorAll('a[href]').length : 0;"
        . "    if (n > bestCount) { bestCount = n; best = el; }"
        . "    if (n >= 3) { best = el; break; }"
        . "    el = el.parentElement;"
        . "  }"
        . "  const root = best || document.body;"
        . "  const seen = new Set();"
        . "  const items = [];"
        . "  root.querySelectorAll('a[href]').forEach(a => {"
        . "    let href = absUrl(a.getAttribute('href') || a.href || '');"
        . "    if (!href || href.startsWith('javascript:') || href === '#' || href.endsWith('#')) return;"
        . "    if (/^(mailto:|tel:)/i.test(href)) return;"
        . "    let name = pickName(a);"
        . "    if (!name || name.length < 2) return;"
        . "    // 略過明顯 UI"
        . "    if (/^(登入|註冊|分享|下載|下一課|上一課|首頁|搜尋)$/.test(name)) return;"
        . "    const key = href.split('#')[0] + '|' + name;"
        . "    if (seen.has(key)) return;"
        . "    seen.add(key);"
        . "    items.push({'\u5b58\u6a94\u540d\u7a31': name, '\u7d20\u6750\u9023\u7d50': href.split('#')[0]});"
        . "  });"
        . "  if (!items.length) {"
        . "    copy('ERR:EMPTY');"
        . "    return;"
        . "  }"
        . "  copy(marker + '\\n' + JSON.stringify(items, null, 2));"
        . "} catch(e) { copy('ERR:' + e); }"
        . "})();"
    )
}

; ---------- 點擊 ----------
; 參數檔：
;   座標模式：
;     座標
;     120
;     340
;   或：
;     座標
;     120,340
;   文字／class 模式（較不穩，可改用座標）：
;     文字
;     逐字稿
;     逐字稿
DoClick(paramFile) {
    if (paramFile = "" || !FileExist(paramFile)) {
        FileAppend "ERR no param file`n", "*", "`n"
        return false
    }
    raw := FileRead(paramFile, "UTF-8")
    raw := StrReplace(raw, "`r", "")
    lines := StrSplit(raw, "`n")
    by := lines.Length >= 1 ? Trim(lines[1]) : "文字"
    value := lines.Length >= 2 ? Trim(lines[2]) : ""
    textMatch := lines.Length >= 3 ? Trim(lines[3]) : ""

    ; ===== 座標點擊（最穩，建議）=====
    if (by = "座標" || by = "coord" || by = "xy") {
        x := 0
        y := 0
        if RegExMatch(value, "^\s*(\d+)\s*,\s*(\d+)\s*$", &m) {
            x := Integer(m[1])
            y := Integer(m[2])
        } else {
            x := Integer(value)
            y := Integer(textMatch)
        }
        if (x < 0 || y < 0) {
            FileAppend "ERR bad coords (negative). Re-capture with 取得滑鼠座標.ahk F8 on Chrome page.`n", "*", "`n"
            return false
        }
        if (x = 0 && y = 0) {
            FileAppend "ERR bad coords (0,0). Fill X/Y from F8.`n", "*", "`n"
            return false
        }
        if !ActivateMainChrome() {
            FileAppend "ERR no chrome`n", "*", "`n"
            return false
        }
        Sleep 200
        CoordMode "Mouse", "Client"
        Click x, y
        Sleep 180
        Click x, y
        Sleep 120
        return true
    }

    marker := "###AUSE_CLICK_OK###"
    ; 回傳：marker + 換行 + clientX,clientY
    js := (
        "(() => {"
        . "try {"
        . "  const by = " QuoteJS(by) ";"
        . "  const value = " QuoteJS(value) ";"
        . "  const textMatch = " QuoteJS(textMatch) ";"
        . "  const want = (textMatch || (by === '文字' ? value : '') || '').trim();"
        . "  function norm(s){return (s||'').replace(/\\s+/g,'').trim();}"
        . "  function findEl(){"
        . "    let el = null;"
        . "    const cand = Array.from(document.body.querySelectorAll('div,button,a,span,li,p,label'));"
        . "    if (want) {"
        . "      el = cand.find(e => (e.innerText||'').trim() === want);"
        . "      if (!el) el = cand.find(e => {"
        . "        const t = (e.innerText||'').trim();"
        . "        return t === want || (t.length < 24 && t.includes(want));"
        . "      });"
        . "    }"
        . "    if (!el && value && (by === 'class' || by.indexOf('class') >= 0)) {"
        . "      const nodes = Array.from(document.body.getElementsByClassName(value));"
        . "      if (want) el = nodes.find(e => (e.innerText||'').includes(want)) || null;"
        . "      if (!el) el = nodes[0] || null;"
        . "    }"
        . "    if (!el && by === 'id' && value) el = document.getElementById(value.replace(/^#/,''));"
        . "    if (!el && by === 'css' && value) el = document.querySelector(value);"
        . "    return el;"
        . "  }"
        . "  let el = findEl();"
        . "  if (!el) { copy('ERR:NOTFOUND'); return; }"
        . "  el.scrollIntoView({block:'center', inline:'center'});"
        . "  const r = el.getBoundingClientRect();"
        . "  const x = Math.round(r.left + r.width/2);"
        . "  const y = Math.round(r.top + r.height/2);"
        . "  try {"
        . "    el.focus();"
        . "    ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type => {"
        . "      el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));"
        . "    });"
        . "    el.click();"
        . "  } catch(e) {}"
        . "  copy(" QuoteJS(marker) " + '\\n' + x + ',' + y);"
        . "} catch(e) { copy('ERR:' + e); }"
        . "})();"
    )

    oldClip := ClipboardAll()
    ActivateMainChrome()
    Sleep 200

    ; 開 Console 執行定位腳本
    Send "^+j"
    Sleep 1100
    A_Clipboard := js
    ClipWait 2
    Sleep 100
    Send "^v"
    Sleep 250
    A_Clipboard := ""
    Sleep 100
    Send "{Enter}"

    result := ""
    loop 25 {
        Sleep 160
        cur := A_Clipboard
        if (cur != "" && InStr(cur, marker) = 1) {
            result := cur
            break
        }
        if (cur != "" && InStr(cur, "ERR:") = 1) {
            result := cur
            break
        }
    }

    ; 關掉 Console，回到頁面再實體點一次（React 按鈕較穩）
    Send "^+j"
    Sleep 300
    ActivateMainChrome()
    Sleep 250

    if (InStr(result, "ERR:") = 1 || result = "") {
        Clipboard := oldClip
        FileAppend "ERR click: " result "`n", "*", "`n"
        return false
    }

    ; 解析座標並用滑鼠點客戶區
    if RegExMatch(result, "m)^" marker "\R(\d+),(\d+)", &m) {
        cx := Integer(m[1])
        cy := Integer(m[2])
        hwnd := WinExist("A")
        if hwnd {
            CoordMode "Mouse", "Client"
            Click cx, cy
            Sleep 200
            ; 再點一次防漏
            Click cx, cy
            Sleep 150
        }
    }

    Clipboard := oldClip
    return true
}

; 啟用「頁面」視窗（略過 DevTools）
ActivateMainChrome(exe := "chrome.exe") {
    for hwnd in WinGetList("ahk_exe " exe) {
        title := WinGetTitle(hwnd)
        if (title = "")
            continue
        if InStr(title, "DevTools")
            continue
        WinActivate "ahk_id " hwnd
        WinWaitActive "ahk_id " hwnd, , 3
        return true
    }
    if WinExist("ahk_exe " exe) {
        WinActivate "ahk_exe " exe
        return true
    }
    return false
}

; ---------- 爬蟲：Console 依 class 複製內容（比 Elements Ctrl+F 穩）----------
DoScrape(paramFile, outPath, exe) {
    if (paramFile = "" || !FileExist(paramFile)) {
        FileAppend "ERR no param file`n", "*", "`n"
        return false
    }
    raw := FileRead(paramFile, "UTF-8")
    raw := StrReplace(raw, "`r", "")
    lines := StrSplit(raw, "`n")
    by := lines.Length >= 1 ? Trim(lines[1]) : "class"
    value := lines.Length >= 2 ? Trim(lines[2]) : ""
    ; 第 3 行：all＝含底下全部文字；body＝只取內文（去按鈕／選單）
    mode := lines.Length >= 3 ? Trim(lines[3]) : "all"
    if (mode = "" || mode = "true" || mode = "1" || mode = "含底下全部")
        mode := "all"
    if (mode = "false" || mode = "0" || mode = "只取內文" || mode = "body" || mode = "inner")
        mode := "body"
    if (value = "") {
        FileAppend "ERR empty value`n", "*", "`n"
        return false
    }

    ; class：不加點（例 sc-jqnqvi-1 dyUpZz）
    searchText := value
    if (by = "class") {
        searchText := RegExReplace(value, "^\.+", "")
        searchText := StrReplace(searchText, ".", " ")
        searchText := RegExReplace(searchText, "\s+", " ")
        searchText := Trim(searchText)
    } else if (by = "id") {
        searchText := RegExReplace(value, "^#", "")
    }

    marker := "###AUSE_OK###"
    oldClip := ClipboardAll()
    text := ""

    ; 點完「逐字稿」後 DOM 可能晚一點才出現 → 多試幾次
    loop 5 {
        if !ActivateMainChrome(exe) {
            FileAppend "ERR no chrome`n", "*", "`n"
            Clipboard := oldClip
            return false
        }
        Sleep 300

        ; 開 Console（Ctrl+Shift+J），直接在頁面執行取文
        Send "^+j"
        Sleep 1100

        ; Chrome 有時要求先輸入 allow pasting
        if (A_Index = 1) {
            SendText "allow pasting"
            Sleep 80
            Send "{Enter}"
            Sleep 250
        }

        js := BuildScrapeJS(by, searchText, marker, mode)
        A_Clipboard := js
        if !ClipWait(2) {
            Sleep 200
        }
        Sleep 100
        Send "^v"
        Sleep 280
        A_Clipboard := ""
        Sleep 80
        Send "{Enter}"

        got := ""
        loop 25 {
            Sleep 180
            cur := A_Clipboard
            if (cur = "")
                continue
            ; 還沒執行完時剪貼簿可能仍是腳本
            if (InStr(cur, "getElementsByClassName") && InStr(cur, "copy("))
                continue
            if (InStr(cur, "querySelectorAll") && InStr(cur, "copy("))
                continue
            if InStr(cur, marker) {
                got := cur
                break
            }
            if (InStr(cur, "ERR:") = 1) {
                got := cur
                break
            }
        }

        ; 關 DevTools，回到頁面
        Sleep 100
        Send "{F12}"
        Sleep 250
        ActivateMainChrome(exe)

        if (got != "" && InStr(got, marker)) {
            text := got
            break
        }
        ; EMPTY：等逐字稿面板載入再試
        if (InStr(got, "ERR:EMPTY") = 1 || got = "") {
            Sleep 900
            continue
        }
        text := got
        break
    }

    Clipboard := oldClip

    if (text = "" || InStr(text, "ERR:") = 1) {
        FileAppend "ERR scrape: " text "`n", "*", "`n"
        return false
    }

    text := RegExReplace(text, "^\x{FEFF}?" marker "\r?\n?", "")
    text := Trim(text)
    if (text = "" || InStr(text, "ERR:") = 1) {
        FileAppend "ERR empty`n", "*", "`n"
        return false
    }
    if (InStr(text, "getElementsByClassName") && InStr(text, "copy(")) {
        FileAppend "ERR got script not content`n", "*", "`n"
        return false
    }

    if (outPath != "") {
        try FileDelete outPath
        FileAppend text "`n", outPath, "UTF-8"
    }
    return true
}

BuildScrapeJS(by, searchText, marker, mode := "all") {
    ; mode=all：全部可見文字；mode=body：只取內文
    extractHelpers := (
        "  const MODE = " QuoteJS(mode) ";"
        . "  const SKIP = 'button,a,nav,header,footer,script,style,svg,input,select,textarea,video,audio,[role=button],[role=tab],[role=menuitem]';"
        . "  const UI_LINE = /^(逐字稿|講義|討論|目錄|分享|下載|複製|回到頂部|展開|收合|播放|暫停|留言|讚|收藏|下一課|上一課)$/;"
        . "  function bodyText(el){"
        . "    if (!el) return '';"
        . "    if (MODE != 'body') return (el.innerText||el.textContent||'').trim();"
        . "    const clone = el.cloneNode(true);"
        . "    try { clone.querySelectorAll(SKIP).forEach(n => n.remove()); } catch(e) {}"
        . "    let t = (clone.innerText||clone.textContent||'').trim();"
        . "    t = t.split(/\r?\n/).map(s => s.replace(/[ \t\u00a0]+/g,' ').trim())"
        . "      .filter(s => !s || !UI_LINE.test(s))"
        . "      .join('\n').replace(/\n{3,}/g,'\n\n').trim();"
        . "    return t;"
        . "  }"
        . "  function texts(nodes){"
        . "    return nodes.map(bodyText).filter(Boolean);"
        . "  }"
    )

    if (by = "class") {
        return (
            "(() => {"
            . "try {"
            . "  const cls = " QuoteJS(searchText) ";"
            . "  const marker = " QuoteJS(marker) ";"
            . extractHelpers
            . "  let nodes = Array.from(document.body.getElementsByClassName(cls));"
            . "  if (!nodes.length) {"
            . "    try {"
            . "      const sel = '.' + cls.trim().split(/\s+/).filter(Boolean)"
            . "        .map(c => (window.CSS && CSS.escape) ? CSS.escape(c) : c.replace(/([^a-zA-Z0-9_-])/g,'\\$1')).join('.');"
            . "      nodes = Array.from(document.body.querySelectorAll(sel));"
            . "    } catch(e) {}"
            . "  }"
            . "  if (!nodes.length && typeof $0 != 'undefined' && $0 && $0.innerText) {"
            . "    const cn = ($0.className && $0.className.toString) ? $0.className.toString() : '';"
            . "    if (!cls || cn.includes(cls.split(/\s+/)[0])) nodes = [$0];"
            . "  }"
            . "  const parts = texts(nodes);"
            . "  if (!parts.length) { copy('ERR:EMPTY'); return; }"
            . "  copy(marker + '\n' + parts.join('\n\n=====\n\n'));"
            . "} catch(e) { copy('ERR:' + e); }"
            . "})();"
        )
    }
    if (by = "id") {
        return (
            "(() => {"
            . "try {"
            . "  const id = " QuoteJS(searchText) ";"
            . "  const marker = " QuoteJS(marker) ";"
            . extractHelpers
            . "  const el = document.getElementById(id);"
            . "  if (!el) { copy('ERR:EMPTY'); return; }"
            . "  const t = bodyText(el);"
            . "  if (!t) { copy('ERR:EMPTY'); return; }"
            . "  copy(marker + '\n' + t);"
            . "} catch(e) { copy('ERR:' + e); }"
            . "})();"
        )
    }
    return (
        "(() => {"
        . "try {"
        . "  const sel = " QuoteJS(searchText) ";"
        . "  const marker = " QuoteJS(marker) ";"
        . extractHelpers
        . "  const nodes = Array.from(document.body.querySelectorAll(sel));"
        . "  const parts = texts(nodes);"
        . "  if (!parts.length) { copy('ERR:EMPTY'); return; }"
        . "  copy(marker + '\n' + parts.join('\n\n=====\n\n'));"
        . "} catch(e) { copy('ERR:' + e); }"
        . "})();"
    )
}

QuoteJS(s) {
    s := StrReplace(s, "\", "\\")
    s := StrReplace(s, "'", "\'")
    return "'" s "'"
}

CaptureClientToBmp(path) {
    hwnd := WinExist("A")
    if !hwnd
        return false
    WinGetClientPos &cx, &cy, &cw, &ch, hwnd
    if (cw < 10 || ch < 10)
        return false
    pt := Buffer(8, 0)
    DllCall("ClientToScreen", "ptr", hwnd, "ptr", pt)
    sx := NumGet(pt, 0, "int")
    sy := NumGet(pt, 4, "int")
    hdcScreen := DllCall("GetDC", "ptr", 0, "ptr")
    hdcMem := DllCall("CreateCompatibleDC", "ptr", hdcScreen, "ptr")
    hbm := DllCall("CreateCompatibleBitmap", "ptr", hdcScreen, "int", cw, "int", ch, "ptr")
    obm := DllCall("SelectObject", "ptr", hdcMem, "ptr", hbm, "ptr")
    DllCall("BitBlt", "ptr", hdcMem, "int", 0, "int", 0, "int", cw, "int", ch,
        "ptr", hdcScreen, "int", sx, "int", sy, "uint", 0x00CC0020)
    bmp := path
    if RegExMatch(path, "i)\.png$")
        bmp := RegExReplace(path, "i)\.png$", ".bmp")
    ok := SaveHBitmapToBmp(hbm, cw, ch, bmp)
    DllCall("SelectObject", "ptr", hdcMem, "ptr", obm)
    DllCall("DeleteObject", "ptr", hbm)
    DllCall("DeleteDC", "ptr", hdcMem)
    DllCall("ReleaseDC", "ptr", 0, "ptr", hdcScreen)
    if ok && bmp != path {
        try FileMove bmp, path, 1
        catch {
            try FileCopy bmp, path, 1
        }
    }
    return ok && (FileExist(path) || FileExist(bmp))
}

SaveHBitmapToBmp(hBitmap, w, h, file) {
    hdc := DllCall("CreateCompatibleDC", "ptr", 0, "ptr")
    bi := Buffer(40, 0)
    NumPut("uint", 40, bi, 0)
    NumPut("int", w, bi, 4)
    NumPut("int", -h, bi, 8)
    NumPut("ushort", 1, bi, 12)
    NumPut("ushort", 24, bi, 14)
    cb := ((w * 3 + 3) & ~3) * h
    bits := Buffer(cb, 0)
    DllCall("GetDIBits", "ptr", hdc, "ptr", hBitmap, "uint", 0, "uint", h,
        "ptr", bits, "ptr", bi, "uint", 0)
    DllCall("DeleteDC", "ptr", hdc)
    fSize := 14 + 40 + cb
    hdr := Buffer(14, 0)
    NumPut("ushort", 0x4D42, hdr, 0)
    NumPut("uint", fSize, hdr, 2)
    NumPut("uint", 54, hdr, 10)
    f := FileOpen(file, "w")
    if !f
        return false
    f.RawWrite(hdr)
    f.RawWrite(bi)
    f.RawWrite(bits)
    f.Close()
    return true
}

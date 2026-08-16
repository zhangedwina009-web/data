# -*- coding: utf-8 -*-
"""章節語音講解：口語文字稿渲染 + 瀏覽器 SpeechSynthesis 播放。"""

from __future__ import annotations

import html
import json
import re
from typing import Any


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


NARRATION_CSS = """
.narration-box{
  margin:.85rem 0 1.1rem;border:1px solid rgba(110,231,245,.28);border-radius:14px;
  background:linear-gradient(135deg,rgba(110,231,245,.08),rgba(16,22,30,.95));
  overflow:hidden;
}
.narration-box > summary{
  list-style:none;cursor:pointer;padding:.7rem .9rem;font-weight:750;
  display:flex;align-items:center;gap:.45rem;color:#e8eef7;
}
.narration-box > summary::-webkit-details-marker{display:none;}
.narration-box > summary::before{content:"▸";color:var(--sky,#6ee7f5);}
.narration-box[open] > summary::before{content:"▾";}
.narration-badge{
  font-size:.7rem;font-weight:800;padding:.14rem .45rem;border-radius:999px;
  background:rgba(110,231,245,.18);color:var(--sky,#6ee7f5);
}
.narration-body{padding:0 .9rem 1rem;}
.narration-toolbar{
  display:flex;flex-wrap:wrap;align-items:center;gap:.45rem;margin:0 0 .65rem;
}
.narration-toolbar button{
  border:1px solid rgba(255,255,255,.14);border-radius:999px;
  background:rgba(18,24,33,.9);color:#e8eef7;padding:.32rem .75rem;
  font-size:.82rem;font-weight:700;cursor:pointer;
}
.narration-toolbar button.main{
  background:linear-gradient(135deg,rgba(94,200,255,.9),rgba(62,224,162,.75));
  color:#071018;border:0;
}
.narration-toolbar button:hover{filter:brightness(1.08);}
.narration-toolbar button:disabled{opacity:.45;cursor:not-allowed;}
.narration-rate{display:inline-flex;align-items:center;gap:.35rem;font-size:.78rem;color:var(--muted,#9fb0c6);}
.narration-rate input{width:90px;accent-color:#5ec8ff;}
.narration-voice{
  display:inline-flex;align-items:center;gap:.35rem;font-size:.78rem;color:var(--muted,#9fb0c6);
  flex:1 1 220px;min-width:180px;
}
.narration-voice select{
  flex:1;min-width:0;max-width:100%;
  border:1px solid rgba(255,255,255,.16);border-radius:999px;
  background:rgba(18,24,33,.95);color:#e8eef7;
  padding:.28rem .7rem;font-size:.78rem;
}
.narration-hint{font-size:.72rem;color:var(--muted,#9fb0c6);margin:.15rem 0 .45rem;line-height:1.45;}
.narration-status{font-size:.78rem;color:var(--mint,#3ee0a2);min-height:1.1em;}
.narration-script{
  white-space:pre-wrap;line-height:1.75;color:#d7e2f0;font-size:.92rem;
  padding:.75rem .85rem;border-radius:12px;border:1px dashed rgba(110,231,245,.25);
  background:rgba(10,14,20,.72);max-height:280px;overflow:auto;-webkit-overflow-scrolling:touch;
}
.narration-script.is-speaking{border-color:rgba(62,224,162,.55);box-shadow:inset 3px 0 0 var(--mint,#3ee0a2);}
@media (max-width:560px){
  .narration-toolbar{gap:.35rem;}
  .narration-voice{flex-basis:100%;}
  .narration-script{max-height:220px;font-size:.88rem;}
}
""".strip()


NARRATION_JS = r"""
(function(){
  if(!('speechSynthesis' in window)){
    document.querySelectorAll('[data-tts-root]').forEach(root=>{
      const st = root.querySelector('[data-tts-status]');
      if(st) st.textContent = '此瀏覽器不支援語音播放，仍可閱讀講解稿。';
      root.querySelectorAll('button[data-tts-play],button[data-tts-pause],button[data-tts-stop]').forEach(b=> b.disabled = true);
      root.querySelectorAll('[data-tts-voice]').forEach(s=> s.disabled = true);
    });
    return;
  }
  const synth = window.speechSynthesis;
  const STORE_KEY = 'note-tts-voice-uri-v2';
  let currentRoot = null;
  let currentUtter = null;
  let voicesReady = false;

  function voiceScore(v){
    const blob = ((v.name||'') + ' ' + (v.lang||'')).toLowerCase();
    let s = 0;
    if(/zh|chinese|中文|國語|台|hong|澳門|yue/.test(blob)) s += 100;
    // 預設優先 Google 中文語音
    if(/google/.test(blob)) s += 200;
    if(/zh-tw|taiwan|國語（台灣）|國語 \(台灣\)|chinese \(taiwan\)/.test(blob)) s += 90;
    if(/hanhan|hsia.?chen|yunjhe|yun-jie|zhiwei|meijia|tingting/.test(blob)) s += 70;
    if(/zh-cn|xiaoxiao|xiaoyi|yunxi|yunyang|huihui|普通话|國語（中國）/.test(blob)) s += 50;
    if(/natural|neural|online|自然|神經|雲端/.test(blob)) s += 35;
    if(/microsoft|edge/.test(blob)) s += 8;
    if(/desktop|sapi|espeak|compact/.test(blob)) s -= 15;
    return s;
  }
  function listVoices(){
    const all = synth.getVoices() || [];
    const zh = all.filter(v => voiceScore(v) >= 100).sort((a,b)=> voiceScore(b)-voiceScore(a));
    if(zh.length) return zh;
    return all.slice().sort((a,b)=> voiceScore(b)-voiceScore(a));
  }
  function voiceKey(v){
    return (v.voiceURI || (v.name + '|' + v.lang) || '').trim();
  }
  function savedVoiceKey(){
    try{ return localStorage.getItem(STORE_KEY) || ''; }catch(e){ return ''; }
  }
  function saveVoiceKey(key){
    try{ localStorage.setItem(STORE_KEY, key || ''); }catch(e){}
  }
  function findVoiceByKey(key){
    if(!key) return null;
    const voices = synth.getVoices() || [];
    return voices.find(v => voiceKey(v) === key) || null;
  }
  function defaultVoice(){
    const voices = listVoices();
    if(!voices.length) return null;
    const saved = findVoiceByKey(savedVoiceKey());
    if(saved) return saved;
    const googleTw = voices.find(v => /google/i.test(v.name) && /zh-tw|taiwan|台灣|台湾/i.test(v.name + v.lang));
    const googleZh = voices.find(v => /google/i.test(v.name) && /zh|chinese|中文|國語|普通话/i.test(v.name + v.lang));
    const googleAny = voices.find(v => /google/i.test(v.name));
    return googleTw || googleZh || googleAny || voices[0];
  }
  function fillVoiceSelects(){
    const voices = listVoices();
    const preferred = defaultVoice();
    const preferredKey = preferred ? voiceKey(preferred) : '';
    document.querySelectorAll('[data-tts-voice]').forEach(sel=>{
      const prev = sel.value;
      sel.innerHTML = '';
      if(!voices.length){
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '（尚無可用語音）';
        sel.appendChild(opt);
        return;
      }
      voices.forEach(v=>{
        const opt = document.createElement('option');
        opt.value = voiceKey(v);
        let tag = '';
        if(/google/i.test(v.name)) tag = ' ★Google';
        else if(/natural|neural|online|自然/i.test(v.name)) tag = ' ★較自然';
        opt.textContent = (v.name || '語音') + '（' + (v.lang || '?') + '）' + tag;
        sel.appendChild(opt);
      });
      const want = prev || preferredKey || voiceKey(voices[0]);
      if([...sel.options].some(o => o.value === want)) sel.value = want;
      else sel.selectedIndex = 0;
    });
    voicesReady = true;
  }
  function selectedVoice(root){
    const sel = root && root.querySelector('[data-tts-voice]');
    const key = sel && sel.value;
    return findVoiceByKey(key) || defaultVoice();
  }
  function setStatus(root, text){
    const st = root && root.querySelector('[data-tts-status]');
    if(st) st.textContent = text || '';
  }
  function setSpeaking(root, on){
    const box = root && root.querySelector('[data-tts-text]');
    if(box) box.classList.toggle('is-speaking', !!on);
  }
  function stopAll(){
    try{ synth.cancel(); }catch(e){}
    if(currentRoot){
      setSpeaking(currentRoot, false);
      setStatus(currentRoot, '使用系統語音朗讀（可自選聲線）');
    }
    currentRoot = null;
    currentUtter = null;
  }
  function playRoot(root){
    const textEl = root.querySelector('[data-tts-text]');
    const text = (textEl && (textEl.innerText || textEl.textContent) || '').trim();
    if(!text){ setStatus(root, '尚無講解稿'); return; }
    if(!voicesReady) fillVoiceSelects();
    stopAll();
    const u = new SpeechSynthesisUtterance(text);
    const voice = selectedVoice(root);
    if(voice){
      u.voice = voice;
      u.lang = voice.lang || 'zh-TW';
      saveVoiceKey(voiceKey(voice));
    }else{
      u.lang = 'zh-TW';
    }
    const rateEl = root.querySelector('[data-tts-rate]');
    u.rate = rateEl ? Number(rateEl.value || 1) : 1;
    u.pitch = 1;
    u.onstart = ()=>{
      currentRoot = root;
      setSpeaking(root, true);
      setStatus(root, '播放中… ' + ((voice && voice.name) || ''));
    };
    u.onend = ()=>{
      setSpeaking(root, false);
      setStatus(root, '播放結束');
      currentRoot = null;
      currentUtter = null;
    };
    u.onerror = ()=>{
      setSpeaking(root, false);
      setStatus(root, '播放中斷（可改選其他語音）');
      currentRoot = null;
      currentUtter = null;
    };
    currentUtter = u;
    // Chrome 偶發 cancel 後立刻 speak 會失敗
    setTimeout(()=> synth.speak(u), 40);
  }

  function bindRoots(){
    document.querySelectorAll('[data-tts-root]').forEach(root=>{
      if(root.dataset.ttsBound) return;
      root.dataset.ttsBound = '1';
      const play = root.querySelector('[data-tts-play]');
      const pause = root.querySelector('[data-tts-pause]');
      const stop = root.querySelector('[data-tts-stop]');
      const voiceSel = root.querySelector('[data-tts-voice]');
      if(play) play.addEventListener('click', ()=>{
        if(synth.paused && currentRoot === root){ synth.resume(); setStatus(root, '繼續播放…'); return; }
        playRoot(root);
      });
      if(pause) pause.addEventListener('click', ()=>{
        if(synth.speaking && !synth.paused){ synth.pause(); setStatus(root, '已暫停'); }
      });
      if(stop) stop.addEventListener('click', ()=> stopAll());
      if(voiceSel) voiceSel.addEventListener('change', ()=>{
        saveVoiceKey(voiceSel.value);
        document.querySelectorAll('[data-tts-voice]').forEach(other=>{
          if(other !== voiceSel) other.value = voiceSel.value;
        });
        setStatus(root, '已選語音，按朗讀試聽');
      });
    });
  }

  fillVoiceSelects();
  bindRoots();
  try{
    synth.getVoices();
    synth.addEventListener('voiceschanged', ()=>{ fillVoiceSelects(); });
  }catch(e){}
})();
""".strip()


def render_narration_panel(script: str, *, uid: str, title: str = "語音講解") -> str:
    text = (script or "").strip()
    if not text:
        return ""
    return f"""
<details class="narration-box" data-tts-root id="narration-{_esc(uid)}" open>
  <summary><span class="narration-badge">聽讀</span>{_esc(title)}</summary>
  <div class="narration-body">
    <div class="narration-toolbar">
      <button type="button" class="main" data-tts-play>▶ 朗讀</button>
      <button type="button" data-tts-pause>⏸ 暫停</button>
      <button type="button" data-tts-stop>⏹ 停止</button>
      <label class="narration-rate">語速 <input type="range" data-tts-rate min="0.7" max="1.35" step="0.05" value="1" /></label>
      <label class="narration-voice">語音 <select data-tts-voice></select></label>
    </div>
    <div class="narration-hint">預設優先 Google 中文語音（Chrome／Edge 較容易有）。可改選其他聲線；標 ★Google／★較自然 通常較好聽。</div>
    <div class="narration-status" data-tts-status>預設 Google 語音（可改選）</div>
    <div class="narration-script" data-tts-text>{_esc(text)}</div>
  </div>
</details>
""".strip()


def _plain(s: str) -> str:
    t = str(s or "")
    t = re.sub(r"[`*_>#]+", "", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip("・•●○-–— ")
    return t


def _sentences_from(text: str, *, limit: int = 4) -> list[str]:
    t = _plain(text)
    if not t:
        return []
    parts = re.split(r"(?<=[。！？；])\s*", t)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) < 6:
            continue
        if not p.endswith(("。", "！", "？")):
            p += "。"
        out.append(p)
        if len(out) >= limit:
            break
    if not out and len(t) >= 6:
        out.append(t if t.endswith(("。", "！", "？")) else t + "。")
    return out


def compose_listening_script(
    title: str,
    *,
    sections: list[dict[str, Any]] | None = None,
    paragraphs: list[str] | None = None,
    bullets: list[str] | None = None,
    key_points: list[str] | None = None,
    notes: list[str] | None = None,
    checklist: list[str] | None = None,
    body: str = "",
    max_chars: int = 900,
) -> str:
    """把講義素材整理成適合用聽的口語講解稿（規則整理，不呼叫 AI）。"""
    title = _plain(title) or "這一節"
    lines: list[str] = [f"這一節我們用聽的方式複習「{title}」。"]

    connectors = ["首先，", "接著，", "另外，", "再來，", "最後，"]
    ci = 0

    def add_block(label: str, sentences: list[str]) -> None:
        nonlocal ci
        cleaned = [_plain(s) for s in sentences if _plain(s)]
        if not cleaned:
            return
        head = connectors[min(ci, len(connectors) - 1)]
        ci += 1
        if label:
            lines.append(f"{head}關於{label}。")
            rest = cleaned
        else:
            lines.append(head + cleaned[0])
            rest = cleaned[1:]
        for s in rest:
            if not s.endswith(("。", "！", "？")):
                s += "。"
            lines.append(s)

    for sec in sections or []:
        if not isinstance(sec, dict):
            continue
        heading = _plain(str(sec.get("heading") or sec.get("title") or ""))
        bits: list[str] = []
        for p in sec.get("paras") or sec.get("paragraphs") or []:
            bits.extend(_sentences_from(str(p), limit=3))
        for b in sec.get("bullets") or []:
            bb = _plain(str(b))
            if bb:
                bits.append(bb if bb.endswith(("。", "！", "？")) else bb + "。")
        add_block(heading, bits[:6])

    para_bits: list[str] = []
    for p in paragraphs or []:
        para_bits.extend(_sentences_from(str(p), limit=3))
    if body:
        para_bits.extend(_sentences_from(body, limit=5))
    if para_bits and not (sections or []):
        add_block("", para_bits[:8])
    elif para_bits and ci < 2:
        add_block("補充說明", para_bits[:4])

    bull = [_plain(str(b)) for b in (bullets or []) if _plain(str(b))]
    if bull:
        joined = "；".join(bull[:5])
        add_block("可以這樣記", [joined + "。"])

    kps = [_plain(str(x)) for x in (key_points or []) if _plain(str(x))]
    if kps:
        lines.append("請特別記住這幾個重點。")
        for i, kp in enumerate(kps[:5], 1):
            lines.append(f"第{i}點，{kp if kp.endswith(('。', '！', '？')) else kp + '。'}")

    note_bits = [_plain(str(n)) for n in (notes or []) if _plain(str(n))]
    if note_bits:
        add_block("實務提醒", [note_bits[0] + ("。" if not note_bits[0].endswith(("。", "！", "？")) else "")])

    checks = [_plain(str(c)) for c in (checklist or []) if _plain(str(c))]
    if checks:
        lines.append("聽完可以自問：" + "；".join(checks[:3]) + "。")

    lines.append("以上是這一節的聽讀重點，建議你對照畫面再掃一次。")
    script = "".join(lines)
    if len(script) > max_chars:
        script = script[: max_chars - 1].rstrip("，、； ") + "。"
        if "以上是這一節" not in script:
            script += "以上是這一節的聽讀重點。"
    return script


def compose_from_chapter(ch: dict[str, Any]) -> str:
    return compose_listening_script(
        str(ch.get("title") or ""),
        sections=[s for s in (ch.get("sections") or []) if isinstance(s, dict)],
        key_points=[str(x) for x in (ch.get("key_points") or [])],
        notes=[str(x) for x in (ch.get("notes") or [])],
        checklist=[str(x) for x in (ch.get("checklist") or [])],
        body=str(ch.get("body") or ch.get("text") or ""),
    )


def compose_from_ebook_section(sec: dict[str, Any]) -> str:
    paras = [str(sec.get("lead") or "")]
    bullets: list[str] = []
    for kid in sec.get("kids") or []:
        if not isinstance(kid, dict):
            continue
        title = _plain(str(kid.get("title") or ""))
        body = _plain(str(kid.get("body") or ""))
        if title and body:
            bullets.append(f"{title}：{body[:180]}")
        elif body:
            bullets.append(body[:220])
    return compose_listening_script(
        str(sec.get("title") or ""),
        paragraphs=paras,
        bullets=bullets,
        max_chars=850,
    )


def compose_from_ebook_kid(kid: dict[str, Any]) -> str:
    return compose_listening_script(
        str(kid.get("title") or "小節"),
        paragraphs=[str(kid.get("body") or "")],
        max_chars=650,
    )


def fallback_narration(title: str, parts: list[str]) -> str:
    """後備：素材不足時仍產出可聽稿。"""
    return compose_listening_script(title, paragraphs=list(parts or []))


def chapter_source_blob(ch: dict[str, Any]) -> str:
    bits: list[str] = []
    bits.append(str(ch.get("title") or ""))
    for sec in ch.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        bits.append(str(sec.get("heading") or sec.get("title") or ""))
        for p in sec.get("paras") or sec.get("paragraphs") or []:
            bits.append(str(p))
        for b in sec.get("bullets") or []:
            bits.append(str(b))
    bits.append(str(ch.get("body") or ch.get("text") or ""))
    for kp in ch.get("key_points") or []:
        bits.append(str(kp))
    for n in ch.get("notes") or []:
        bits.append(str(n))
    text = "\n".join(x.strip() for x in bits if str(x).strip())
    return text[:4500]

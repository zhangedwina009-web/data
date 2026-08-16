# -*- coding: utf-8 -*-
"""講義共用左側邊欄殼層（與公司治理講義同一套互動）。"""

from __future__ import annotations

import html
from typing import Any

TOC_MARKS = ("◆", "◇", "›", "▹", "●", "○", "■", "□", "✦", "✧")


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


SIDEBAR_CSS = """
:root{
  --side-w:320px; --side-blue:#0d2137;
}
.layout{min-height:100vh;}
.sidebar{
  position:fixed; inset:0 auto 0 0; width:min(var(--side-w), 88vw); z-index:40;
  background:linear-gradient(180deg, #0a2744 0%, var(--side-blue) 40%, #0b1a2a 100%);
  border-right:1px solid rgba(94,200,255,.18);
  display:flex; flex-direction:column;
  transform:translateX(0); transition:transform .22s ease;
  box-shadow:8px 0 28px rgba(0,0,0,.25);
}
body.side-collapsed .sidebar{transform:translateX(-105%);}
.side-scroll{overflow:auto; -webkit-overflow-scrolling:touch; padding:.85rem .75rem 5rem; flex:1;}
.side-brand-block{padding:.35rem .45rem 0.85rem; border-bottom:1px solid rgba(94,200,255,.15); margin-bottom:.75rem;}
.side-brand{font-weight:850; font-size:1.05rem; color:#fff; letter-spacing:.04em;}
.side-sub{font-size:.75rem; color:rgba(158,200,230,.85); margin-top:.15rem;}
.side-home{
  display:inline-flex; margin-top:.55rem; font-size:.78rem; font-weight:700;
  color:var(--cyan); text-decoration:none;
}
.side-home:hover{color:#fff;}
.chap-drop{
  border:1px solid rgba(94,200,255,.14); border-radius:12px;
  background:rgba(8,24,40,.72); margin:0 0 .45rem; overflow:hidden;
}
.chap-drop.active-chap{border-color:rgba(94,200,255,.45); box-shadow:inset 3px 0 0 var(--cyan);}
.chap-drop > summary{
  list-style:none; cursor:pointer; padding:.55rem .65rem;
  display:flex; align-items:center; gap:.35rem;
  font-size:.84rem; font-weight:750; color:#e8f4ff;
}
.chap-drop > summary::-webkit-details-marker{display:none;}
.chap-drop > summary::before{content:"▸"; color:rgba(158,200,230,.7); width:1rem; flex:0 0 auto;}
.chap-drop[open] > summary::before{content:"▾"; color:var(--cyan);}
.chap-sum-link{color:inherit; text-decoration:none; flex:1; min-width:0; word-break:break-word;}
.chap-sum-link:hover{color:var(--cyan);}
.toc-kids{padding:0 .35rem .55rem .35rem; display:flex; flex-direction:column; gap:.08rem;}
.toc-h3{
  display:flex; align-items:flex-start; gap:.4rem; text-decoration:none; color:rgba(200,220,235,.88);
  font-size:.78rem; padding:.32rem .45rem; border-radius:8px; line-height:1.35;
}
.toc-h3:hover{background:rgba(94,200,255,.12); color:#fff;}
.toc-sub{padding-left:1.15rem; font-size:.74rem; color:rgba(170,195,215,.8);}
.toc-mark{flex:0 0 auto; width:1.1rem; text-align:center; color:var(--cyan); font-size:.85rem;}
.toc-sub .toc-mark{color:var(--amber); font-size:.78rem;}
.toc-text{flex:1; min-width:0; overflow-wrap:anywhere;}
.edge-toggle{
  position:fixed; left:calc(min(var(--side-w), 88vw) - 16px); top:max(12px, env(safe-area-inset-top));
  z-index:50; width:32px; height:32px; border-radius:10px;
  border:1px solid rgba(255,255,255,.14);
  background:rgba(13,33,55,.95); color:#fff; cursor:pointer;
  display:grid; place-items:center; transition:left .22s ease, opacity .2s ease;
}
body.side-collapsed .edge-toggle{display:none;}
.burger-fab{
  display:none; position:fixed;
  left:max(12px, env(safe-area-inset-left));
  top:max(12px, env(safe-area-inset-top));
  z-index:55; width:42px; height:42px; border-radius:12px;
  border:1px solid rgba(255,255,255,.14);
  background:linear-gradient(135deg,rgba(94,200,255,.45),rgba(62,224,162,.32));
  color:#071018; font-size:1.1rem; font-weight:800; cursor:pointer;
  box-shadow:0 8px 22px rgba(0,0,0,.35);
}
body.side-collapsed .burger-fab{display:grid; place-items:center;}
.content{margin-left:min(var(--side-w), 88vw); min-width:0; width:auto; transition:margin-left .22s ease;}
body.side-collapsed .content{margin-left:0;}
.note-wrap,.wrap{
  max-width:980px; margin:0 auto;
  padding:1.25rem 1.15rem 3.2rem; overflow-x:clip;
}
body.side-collapsed .note-wrap, body.side-collapsed .wrap{padding-top:4.2rem;}
.backdrop{display:none; position:fixed; inset:0; z-index:35; background:rgba(0,0,0,.45);}
body.side-open-mobile .backdrop{display:block;}
@media (max-width:900px){
  .sidebar{
    width:min(86vw, 320px);
    transform:translateX(-105%);
    box-shadow:12px 0 40px rgba(0,0,0,.45);
  }
  body.side-open-mobile .sidebar{transform:translateX(0);}
  body.side-collapsed .sidebar{transform:translateX(-105%);}
  body.side-collapsed.side-open-mobile .sidebar{transform:translateX(0);}
  .content{margin-left:0 !important; width:100%;}
  .edge-toggle{display:none !important;}
  .burger-fab{display:grid !important; place-items:center;}
  .note-wrap,.wrap{
    padding:4.4rem max(.85rem, env(safe-area-inset-right))
            calc(2.5rem + env(safe-area-inset-bottom))
            max(.85rem, env(safe-area-inset-left));
  }
}
@media (min-width:901px){
  body.side-open-mobile .backdrop{display:none;}
}
@media (prefers-reduced-motion:reduce){
  .sidebar,.content,.edge-toggle{transition:none;}
}
@media print{
  .sidebar,.burger-fab,.edge-toggle,.backdrop{display:none !important;}
  .content{margin-left:0 !important;}
}
""".strip()


SIDEBAR_JS = r"""
(function(){
  const body = document.body;
  const key = 'note-side-collapsed';
  const backdrop = document.getElementById('side-backdrop');
  const mq = window.matchMedia('(max-width:900px)');
  const isMobile = () => mq.matches;
  const edge = document.getElementById('edge-toggle');
  const burger = document.getElementById('burger-fab');
  function setCollapsed(v){
    body.classList.toggle('side-collapsed', !!v);
    try{ localStorage.setItem(key, v ? '1' : '0'); }catch(e){}
  }
  function openMobile(v){
    body.classList.toggle('side-open-mobile', !!v);
    if(backdrop) backdrop.hidden = !v;
    body.style.overflow = v ? 'hidden' : '';
    if(burger){
      burger.setAttribute('aria-expanded', v ? 'true' : 'false');
      burger.title = v ? '關閉目錄' : '打開目錄';
      burger.setAttribute('aria-label', v ? '關閉目錄' : '打開目錄');
    }
  }
  function syncViewport(){
    if(isMobile()){
      setCollapsed(true);
      openMobile(false);
    } else {
      openMobile(false);
      try{ setCollapsed(localStorage.getItem(key)==='1'); }
      catch(e){ setCollapsed(false); }
    }
  }
  syncViewport();
  if(mq.addEventListener) mq.addEventListener('change', syncViewport);
  else if(mq.addListener) mq.addListener(syncViewport);
  if(edge) edge.addEventListener('click', ()=>{ if(isMobile()) openMobile(false); else setCollapsed(true); });
  if(burger) burger.addEventListener('click', (e)=>{
    e.preventDefault(); e.stopPropagation();
    if(isMobile()) openMobile(!body.classList.contains('side-open-mobile'));
    else setCollapsed(false);
  });
  if(backdrop) backdrop.addEventListener('click', ()=> openMobile(false));

  document.querySelectorAll('[data-nav-jump], [data-jump-lecture], .milestone-link, .path-card').forEach(a=>{
    a.addEventListener('click', (e)=>{
      const href = a.getAttribute('href')||'';
      const hashIdx = href.indexOf('#');
      if(hashIdx < 0) return;
      const hash = href.slice(hashIdx);
      const file = href.slice(0, hashIdx);
      const cur = decodeURIComponent(location.pathname.split('/').pop()||'');
      if(file && file !== cur && !hash.startsWith('#ch-') && !hash.startsWith('#sec-')) return;
      if(file && file !== cur) return;
      const btn = document.getElementById('tab-lecture-btn');
      if(btn && window.bootstrap){
        e.preventDefault();
        bootstrap.Tab.getOrCreateInstance(btn).show();
        if(isMobile()) openMobile(false);
        setTimeout(()=>{ const t=document.querySelector(hash); if(t) t.scrollIntoView({behavior:'smooth', block:'start'}); }, 160);
      } else if(isMobile()) {
        openMobile(false);
      }
    });
  });
})();
""".strip()


def build_course_sidebar(
    *,
    brand: str,
    brand_sub: str = "講義目錄",
    books: list[dict[str, Any]],
    active_file: str,
    home_href: str = "../index.html",
) -> str:
    """books: [{file, title, chapters:[{id,title}]}]"""
    bits = [
        '<div class="side-brand-block">',
        f'<div class="side-brand">{_esc(brand)}</div>',
        f'<div class="side-sub">{_esc(brand_sub)}</div>',
        f'<a class="side-home" href="{_esc(home_href)}">← 筆記首頁</a>',
        "</div>",
    ]
    if not books:
        bits.append('<p class="side-sub" style="padding:.4rem">尚無目錄</p>')
        return "\n".join(bits)

    for book in books:
        out_name = str(book.get("file") or "")
        title = str(book.get("title") or out_name)
        chapters = [c for c in (book.get("chapters") or []) if isinstance(c, dict)]
        active = out_name == active_file
        open_attr = " open" if active else ""
        active_cls = " active-chap" if active else ""
        bits.append(f'<details class="chap-drop{active_cls}"{open_attr}>')
        bits.append(
            f'<summary><a class="chap-sum-link" href="{_esc(out_name)}" '
            f'data-nav-jump="{_esc(out_name)}">{_esc(title)}</a></summary>'
        )
        bits.append('<div class="toc-kids">')
        if not chapters:
            bits.append(
                f'<a class="toc-h3" href="{_esc(out_name)}">'
                f'<span class="toc-mark">◆</span><span class="toc-text">進入本篇</span></a>'
            )
        else:
            for j, ch in enumerate(chapters):
                mark = TOC_MARKS[j % len(TOC_MARKS)]
                cid = str(ch.get("id") or f"ch-{j+1}")
                ctitle = str(ch.get("title") or cid)
                href = f"{out_name}#{cid}" if out_name else f"#{cid}"
                bits.append(
                    f'<a class="toc-h3" href="{_esc(href)}" data-nav-jump="{_esc(out_name)}" data-jump-lecture>'
                    f'<span class="toc-mark">{mark}</span>'
                    f'<span class="toc-text">{_esc(ctitle)}</span></a>'
                )
        bits.append("</div></details>")
    return "\n".join(bits)


def chapters_from_note(note: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i, ch in enumerate(note.get("chapters") or [], 1):
        if not isinstance(ch, dict):
            continue
        title = str(ch.get("title") or f"第 {i} 章").strip()
        out.append({"id": f"ch-{i}", "title": title})
    return out


def wrap_with_sidebar(
    *,
    title: str,
    body_html: str,
    sidebar_html: str,
    head_extra: str = "",
    style_extra: str = "",
    scripts_before: str = "",
    scripts_after: str = "",
    meta_line: str = "",
    storage_key: str = "note-side-collapsed",
) -> str:
    safe_title = _esc(title or "教學講義")
    meta = meta_line or "學習講義 · 左側目錄／Tabs"
    # allow custom storage key via tiny replace in JS
    side_js = SIDEBAR_JS.replace("note-side-collapsed", storage_key)
    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-bs-theme="dark">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>{safe_title}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" />
{head_extra}
<style>
{SIDEBAR_CSS}
{style_extra}
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
    <main class="note-wrap">
      <p class="meta-line mb-3">{_esc(meta)}</p>
      {body_html}
    </main>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
{scripts_before}
<script>
{side_js}
</script>
{scripts_after}
</body>
</html>
"""

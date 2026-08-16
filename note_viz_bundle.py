# -*- coding: utf-8 -*-
"""講義共用視覺化套件：CDN、面板 HTML、啟動腳本。

涵蓋：Tabulator / Grid.js / DataTables / AG Grid /
Chart.js / ECharts / Plotly / D3 / Mermaid /
Cytoscape / vis-network / markmap / vis-timeline
"""

from __future__ import annotations

import html
import json
from typing import Any


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


HEAD_LINKS = """
<link href="https://cdn.jsdelivr.net/npm/tabulator-tables@6.3.0/dist/css/tabulator_midnight.min.css" rel="stylesheet" />
<link href="https://cdn.jsdelivr.net/npm/gridjs@6.2.0/dist/theme/mermaid.min.css" rel="stylesheet" />
<link href="https://cdn.jsdelivr.net/npm/datatables.net-bs5@2.1.8/css/dataTables.bootstrap5.min.css" rel="stylesheet" />
<link href="https://cdn.jsdelivr.net/npm/ag-grid-community@32.3.3/styles/ag-grid.css" rel="stylesheet" />
<link href="https://cdn.jsdelivr.net/npm/ag-grid-community@32.3.3/styles/ag-theme-alpine-dark.css" rel="stylesheet" />
<link href="https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/styles/vis-timeline-graph2d.min.css" rel="stylesheet" />
<link href="https://cdn.jsdelivr.net/npm/vis-network@9.1.9/styles/vis-network.min.css" rel="stylesheet" />
""".strip()


SCRIPT_TAGS = """
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/tabulator-tables@6.3.0/dist/js/tabulator.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/gridjs@6.2.0/dist/gridjs.umd.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/datatables.net@2.1.8/js/dataTables.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/datatables.net-bs5@2.1.8/js/dataTables.bootstrap5.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/ag-grid-community@32.3.3/dist/ag-grid-community.min.noStyle.js"></script>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/standalone/umd/vis-timeline-graph2d.min.js"></script>
<script>
window.markmap = {
  autoLoader: {
    manual: true,
    toolbar: true
  }
};
</script>
<script src="https://cdn.jsdelivr.net/npm/markmap-autoloader@0.18.11"></script>
""".strip()


EXTRA_CSS = """
.viz-toolkit-badge{display:inline-flex;flex-wrap:wrap;gap:.35rem;margin:.35rem 0 1rem;}
.viz-pill{font-size:.68rem;font-weight:750;padding:.18rem .5rem;border-radius:999px;border:1px solid rgba(255,255,255,.12);color:var(--muted);background:rgba(18,24,33,.85);}
.viz-grid{
  display:grid;
  grid-template-columns:1fr;
  gap:.9rem;
  align-items:stretch;
}
@media (min-width:768px){
  .viz-grid{grid-template-columns:repeat(2, minmax(0, 1fr));}
}
@media (min-width:1200px){
  .viz-grid.viz-grid-dense{grid-template-columns:repeat(2, minmax(0, 1fr));}
}
.viz-cell{
  margin:0;
  border:1px solid rgba(255,255,255,.08);
  border-radius:14px;
  overflow:hidden;
  background:rgba(16,22,30,.92);
  max-width:100%;
  min-width:0;
  display:flex;
  flex-direction:column;
}
.viz-cell-wide{grid-column:1 / -1;}
.viz-panel-h,.viz-cell-h{
  display:flex;flex-wrap:wrap;align-items:center;gap:.45rem;
  padding:.65rem .85rem;border-bottom:1px solid rgba(255,255,255,.08);font-weight:720;
}
.viz-lib{font-size:.7rem;font-weight:800;padding:.15rem .45rem;border-radius:999px;background:rgba(94,200,255,.16);color:var(--cyan);}
.viz-body,.viz-cell-b{padding:.75rem .85rem 1rem;overflow-x:auto;-webkit-overflow-scrolling:touch;flex:1;min-height:0;}
.viz-box{min-height:clamp(180px,42vw,260px);width:100%;max-width:100%;position:relative;}
.viz-box-sm{min-height:clamp(160px,38vw,220px);}
.viz-box-lg{min-height:clamp(220px,48vw,340px);}
.viz-empty{color:var(--muted);font-size:.9rem;padding:.4rem 0;}
.viz-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%;}
.tabulator,.tabulator-header,.tabulator-row{background:transparent !important;color:var(--text) !important;}
.tabulator{border:1px solid rgba(255,255,255,.08) !important;border-radius:10px;overflow:hidden;max-width:100%;}
.gridjs-wrapper{overflow-x:auto !important;max-width:100%;}
.gridjs-th,.gridjs-td{background:#121821 !important;border-color:rgba(255,255,255,.1) !important;color:#e8eef7 !important;}
table.dataTable{color:var(--text);width:100% !important;}
.ag-theme-alpine-dark{--ag-background-color:#121821;--ag-header-background-color:#0d1520;height:clamp(220px,50vw,300px);width:100%;max-width:100%;}
.markmap-host{position:relative;width:100%;max-width:100%;height:clamp(280px,58vw,420px);border-radius:10px;border:1px solid rgba(255,255,255,.08);background:#0a0e14;overflow:hidden;}
.markmap-host .markmap{position:relative;width:100%;height:100%;}
.markmap-host .markmap > svg,
.markmap > svg{width:100% !important;height:100% !important;min-height:260px;display:block;}
.cy-host,.vis-host{height:clamp(240px,55vw,340px);width:100%;max-width:100%;border-radius:10px;border:1px solid rgba(255,255,255,.08);background:#0a0e14;}
.vis-timeline{border:0 !important;background:transparent !important;width:100% !important;}
.vis-item{background:rgba(94,200,255,.25) !important;border-color:rgba(94,200,255,.55) !important;color:#e8eef7 !important;font-size:12px !important;}
.d3-host{height:clamp(220px,50vw,300px);width:100%;max-width:100%;overflow:auto;-webkit-overflow-scrolling:touch;}
.d3-host text{fill:#c9d7ea;font-size:11px;}
.d3-host .link{stroke:rgba(94,200,255,.35);}
.d3-host .node circle{fill:#5ec8ff;}
.mermaid-host{padding:.5rem;border-radius:10px;border:1px solid rgba(255,255,255,.06);background:#0a0e14;overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%;}
.mermaid-host .mermaid,.mermaid-host svg{max-width:100%;}
@media (max-width:767px){
  .viz-cell-b{padding:.65rem .7rem .85rem;}
  .viz-cell-h{padding:.55rem .7rem;font-size:.92rem;}
  .viz-toolkit-badge{gap:.28rem;}
  .viz-pill{font-size:.62rem;padding:.14rem .42rem;}
  .tabulator .tabulator-header-filter input{font-size:12px;}
}
@media (max-width:420px){
  .markmap-host{height:260px;}
  .cy-host,.vis-host{height:220px;}
}
""".strip()


def _viz_cell(lib: str, title: str, body: str, *, wide: bool = False) -> str:
    wide_cls = " viz-cell-wide" if wide else ""
    return (
        f'<article class="viz-cell{wide_cls}">'
        f'<div class="viz-cell-h"><span class="viz-lib">{_esc(lib)}</span>{_esc(title)}</div>'
        f'<div class="viz-cell-b">{body}</div>'
        f"</article>"
    )


def render_viz_tab(payload: dict[str, Any], *, hint: str = "") -> str:
    """圖表分頁：僅輸出本章有資料的區塊；每張圖獨立一格。"""
    p = payload or {}
    timeline = p.get("timeline") or []
    compares = p.get("compares") or []
    evolution = p.get("evolution") or []
    outline = p.get("outline") or []
    nodes = p.get("nodes") or []
    charts = p.get("charts") or []
    mermaids = p.get("mermaids") or []

    has_outline = any(str((o or {}).get("title") or "").strip() for o in outline if isinstance(o, dict))
    has_timeline = len(timeline) > 0
    has_compare = len(compares) > 0
    has_evolve = len(evolution) > 0
    # 關係網：僅當大綱有下層節點，或明確 nodes≥2
    has_kids = any(
        isinstance(o, dict) and (o.get("kids") or [])
        for o in outline
    )
    has_graph = (len(nodes) >= 2 and has_kids) or (
        has_kids and sum(1 for o in outline if isinstance(o, dict)) >= 2
    )
    has_extra = len(charts) > 0 or len(mermaids) > 0

    used_libs: list[str] = []
    cells: list[str] = []

    if has_outline:
        used_libs.append("markmap")
        cells.append(
            _viz_cell(
                "markmap",
                "章節心智圖",
                '<div class="markmap-host" id="viz-markmap" aria-label="章節心智圖"></div>',
                wide=True,
            )
        )

    if has_timeline:
        used_libs.extend(["Tabulator", "Chart.js", "ECharts", "vis-timeline", "Plotly"])
        cells.append(
            _viz_cell(
                "Tabulator",
                "時序表",
                '<div id="viz-tabulator-timeline"></div>',
                wide=True,
            )
        )
        cells.append(
            _viz_cell(
                "Chart.js",
                "時序長條圖",
                '<div class="viz-box viz-box-sm"><canvas id="viz-chartjs-timeline"></canvas></div>',
            )
        )
        cells.append(
            _viz_cell(
                "ECharts",
                "時序折線",
                '<div class="viz-box" id="viz-echarts-timeline"></div>',
            )
        )
        cells.append(
            _viz_cell(
                "vis-timeline",
                "時間軸",
                '<div class="viz-box" id="viz-vis-timeline"></div>',
            )
        )
        cells.append(
            _viz_cell(
                "Plotly",
                "時序互動圖",
                '<div class="viz-box" id="viz-plotly-timeline"></div>',
            )
        )

    if has_compare:
        used_libs.append("Tabulator")
        cells.append(
            _viz_cell(
                "Tabulator",
                "對照表",
                '<div id="viz-tabulator-compare"></div>',
                wide=True,
            )
        )
        # 第二套表格僅在有對照資料時給一格（避免四套重複）
        used_libs.append("Grid.js")
        cells.append(
            _viz_cell(
                "Grid.js",
                "對照表（可搜尋）",
                '<div id="viz-gridjs-compare"></div>',
                wide=True,
            )
        )

    if has_evolve:
        used_libs.extend(["Tabulator", "Mermaid", "ECharts", "D3"])
        cells.append(
            _viz_cell(
                "Tabulator",
                "演進表",
                '<div id="viz-tabulator-evolve"></div>',
                wide=True,
            )
        )
        cells.append(
            _viz_cell(
                "Mermaid",
                "演進流程",
                '<div class="mermaid-host"><pre class="mermaid" id="viz-mermaid-evolve"></pre></div>',
            )
        )
        cells.append(
            _viz_cell(
                "ECharts",
                "演進關係",
                '<div class="viz-box" id="viz-echarts-evolve"></div>',
            )
        )
        cells.append(
            _viz_cell(
                "D3",
                "演進樹狀圖",
                '<div class="d3-host viz-box" id="viz-d3-evolve"></div>',
            )
        )

    if has_graph:
        used_libs.extend(["Cytoscape", "vis-network"])
        cells.append(
            _viz_cell(
                "Cytoscape",
                "章節關係網",
                '<div class="cy-host" id="viz-cytoscape"></div>',
            )
        )
        cells.append(
            _viz_cell(
                "vis-network",
                "概念網路",
                '<div class="vis-host" id="viz-vis-network"></div>',
            )
        )

    if has_extra:
        if charts:
            used_libs.append("Chart.js")
            for i, c in enumerate(charts):
                title = str((c or {}).get("title") or f"量化圖表 {i+1}")
                cells.append(
                    _viz_cell(
                        "Chart.js",
                        title,
                        f'<div class="viz-box viz-box-sm"><canvas id="viz-extra-chart-{i}"></canvas></div>',
                    )
                )
        if mermaids:
            used_libs.append("Mermaid")
            cells.append(
                _viz_cell(
                    "Mermaid",
                    "講義流程圖",
                    '<div id="viz-extra-mermaids"></div>',
                    wide=True,
                )
            )

    # 去重 pills，只顯示本章實際用到的
    seen = set()
    pills_libs = []
    for x in used_libs:
        if x not in seen:
            seen.add(x)
            pills_libs.append(x)

    if not cells:
        return (
            '<div class="structs-wrap viz-root" id="viz-root">'
            '<p class="tab-hint mb-0">本章沒有可繪製的圖表資料。</p>'
            f'<script type="application/json" id="note-viz-data">{_json(p)}</script>'
            "</div>"
        )

    hint = hint or "以下僅顯示本章有資料的圖表；每張圖獨立一格，可分別操作。"
    pills = "".join(f'<span class="viz-pill">{_esc(x)}</span>' for x in pills_libs)
    data = _json(p)
    return f"""
<div class="structs-wrap viz-root" id="viz-root">
  <p class="tab-hint mb-2">{_esc(hint)}</p>
  <div class="viz-toolkit-badge">{pills}</div>
  <script type="application/json" id="note-viz-data">{data}</script>
  <div class="viz-grid viz-grid-dense">
    {"".join(cells)}
  </div>
</div>
""".strip()


BOOT_SCRIPT = r"""
<script>
(function(){
  function parsePayload(){
    const el = document.getElementById('note-viz-data');
    if(!el) return {};
    try { return JSON.parse(el.textContent || '{}'); } catch(e){ return {}; }
  }
  const data = parsePayload();
  const timeline = Array.isArray(data.timeline) ? data.timeline : [];
  const compares = Array.isArray(data.compares) ? data.compares : [];
  const evolution = Array.isArray(data.evolution) ? data.evolution : [];
  const outline = Array.isArray(data.outline) ? data.outline : [];
  const nodes = Array.isArray(data.nodes) ? data.nodes : [];
  const edges = Array.isArray(data.edges) ? data.edges : [];
  const charts = Array.isArray(data.charts) ? data.charts : [];
  const mermaids = Array.isArray(data.mermaids) ? data.mermaids : [];

  const state = {
    ready: false,
    echarts: [],
    cy: null,
    network: null,
    timeline: null,
    markmapSvg: null
  };

  function showEmpty(id, on){
    const el = document.getElementById(id);
    if(el) el.classList.toggle('d-none', !on);
  }
  function short(s, n){
    s = String(s||'');
    return s.length > n ? s.slice(0, n-1) + '…' : s;
  }
  function isNarrow(){ return window.matchMedia('(max-width:767px)').matches; }
  function tableH(desktop){ return isNarrow() ? Math.max(180, Math.min(260, Math.round(window.innerHeight*0.32))) + 'px' : desktop; }
  function boxSize(el){
    if(!el) return { w: 320, h: 240 };
    const w = Math.max(el.clientWidth || el.offsetWidth || 0, 280);
    const h = Math.max(el.clientHeight || el.offsetHeight || 0, 200);
    return { w, h };
  }
  function chartsTabVisible(){
    const pane = document.getElementById('tab-charts');
    if(!pane) return true;
    return pane.classList.contains('active') || pane.classList.contains('show');
  }

  function buildOutlineMd(){
    let md = '# 講義大綱\n';
    if(outline.length){
      outline.forEach((o,i)=>{
        const title = String(o.title||('節 '+(i+1))).replace(/\n/g,' ');
        md += `\n## ${i+1}. ${title}`;
        (o.kids||[]).forEach(k=>{
          md += `\n- ${String(k).replace(/\n/g,' ')}`;
        });
      });
    } else if(nodes.length){
      nodes.forEach(n=>{ md += `\n## ${n.label||n.id}`; });
    } else {
      md += '\n## （尚無大綱）\n- 請見章節講義';
    }
    return md;
  }

  function waitMarkmapReady(){
    return new Promise((resolve)=>{
      const al = window.markmap && markmap.autoLoader;
      if(!al){ resolve(false); return; }
      if(al.ready && typeof al.ready.then === 'function'){
        al.ready.then(()=>resolve(true)).catch(()=>resolve(!!al.renderAll));
        return;
      }
      let n = 0;
      const t = setInterval(()=>{
        n++;
        const ok = !!(window.markmap && markmap.autoLoader && (markmap.autoLoader.render || markmap.autoLoader.renderAll));
        if(ok || n > 50){ clearInterval(t); resolve(ok); }
      }, 120);
    });
  }

  async function renderMarkmap(){
    const host = document.getElementById('viz-markmap');
    if(!host) return;
    const md = buildOutlineMd();
    host.innerHTML = '';
    const el = document.createElement('div');
    el.className = 'markmap';
    const tpl = document.createElement('script');
    tpl.type = 'text/template';
    tpl.textContent = md;
    el.appendChild(tpl);
    host.appendChild(el);

    const ok = await waitMarkmapReady();
    const al = window.markmap && markmap.autoLoader;
    if(!ok || !al){
      host.innerHTML = '<p class="viz-empty">心智圖套件尚未載入完成，請重新整理頁面。</p>';
      return;
    }
    try {
      if(typeof al.render === 'function') await al.render(el);
      else if(typeof al.renderAllUnder === 'function') await al.renderAllUnder(host);
      else if(typeof al.renderAll === 'function') await al.renderAll();
      // 強制 SVG 填滿容器
      const svg = host.querySelector('svg');
      if(svg){
        svg.style.width = '100%';
        svg.style.height = '100%';
        state.markmapSvg = svg;
      }
      // 觸發 fit：模擬 resize
      setTimeout(()=> window.dispatchEvent(new Event('resize')), 60);
    } catch(e){
      console.warn('markmap render', e);
      host.innerHTML = '<p class="viz-empty">心智圖渲染失敗：' + String(e && e.message || e) + '</p>';
    }
  }

  function fitAll(){
    state.echarts.forEach(c=>{ try{ c.resize(); }catch(e){} });
    if(state.cy){ try{ state.cy.resize(); state.cy.fit(undefined, 24); }catch(e){} }
    if(state.network){ try{ state.network.redraw(); state.network.fit(); }catch(e){} }
    if(state.timeline){ try{ state.timeline.redraw(); }catch(e){} }
    if(window.Plotly){
      document.querySelectorAll('#viz-plotly-timeline .js-plotly-plot, #viz-plotly-timeline').forEach(el=>{
        try{ Plotly.Plots.resize(el); }catch(e){}
      });
    }
    const host = document.getElementById('viz-markmap');
    const svg = host && host.querySelector('svg');
    if(svg){
      svg.style.width = '100%';
      svg.style.height = '100%';
    }
    // D3 重畫交由 init 內的資料；窄螢幕時僅調整既有 svg 寬度
    const d3svg = document.querySelector('#viz-d3-evolve svg');
    if(d3svg){
      const wrap = document.getElementById('viz-d3-evolve');
      const { w } = boxSize(wrap);
      d3svg.setAttribute('width', String(w));
    }
  }

  function initViz(){
    if(state.ready){ fitAll(); return; }
    state.ready = true;

    /* —— markmap —— */
    renderMarkmap();

    /* —— timeline —— */
    if(timeline.length){
      const rows = timeline.map(r=>({ when:r.when||r[0]||'', what:r.what||r[1]||'' }));
      if(window.Tabulator && document.getElementById('viz-tabulator-timeline')){
        new Tabulator('#viz-tabulator-timeline', {
          data: rows, layout:'fitDataStretch', height: tableH('220px'),
          columns:[
            {title:'時點', field:'when', minWidth:88, widthGrow:1, headerFilter: isNarrow()?false:'input'},
            {title:'事件／規範重點', field:'what', minWidth:160, widthGrow:3, headerFilter: isNarrow()?false:'input', formatter:'textarea'}
          ]
        });
      }
      if(window.Chart){
        const ctx = document.getElementById('viz-chartjs-timeline');
        if(ctx){
          new Chart(ctx, {
            type:'bar',
            data:{
              labels: rows.map(r=>short(r.when, isNarrow()?8:12)),
              datasets:[{ label:'事件數', data: rows.map(()=>1), backgroundColor:'rgba(94,200,255,.55)' }]
            },
            options:{
              responsive:true, maintainAspectRatio:false,
              plugins:{ legend:{ labels:{ color:'#c9d7ea', boxWidth:12 } } },
              scales:{
                x:{ ticks:{ color:'#93a4b8', maxRotation:45, minRotation:0, autoSkip:true }, grid:{ color:'#2a3544' } },
                y:{ ticks:{ color:'#93a4b8', stepSize:1 }, grid:{ color:'#2a3544' }, beginAtZero:true }
              }
            }
          });
        }
      }
      if(window.echarts){
        const el = document.getElementById('viz-echarts-timeline');
        if(el){
          const chart = echarts.init(el, 'dark');
          chart.setOption({
            backgroundColor:'transparent',
            grid:{ left:36, right:16, top:24, bottom: isNarrow()?64:40, containLabel:true },
            tooltip:{ trigger:'axis' },
            xAxis:{ type:'category', data: rows.map(r=>short(r.when, isNarrow()?8:14)), axisLabel:{ color:'#9fb0c6', hideOverlap:true } },
            yAxis:{ type:'value', show:false },
            series:[{
              type:'line', smooth:true, symbolSize:10,
              data: rows.map((_,i)=>i+1),
              areaStyle:{ color:'rgba(94,200,255,.15)' },
              lineStyle:{ color:'#5ec8ff' },
              itemStyle:{ color:'#3ee0a2' }
            }]
          });
          state.echarts.push(chart);
        }
      }
      if(window.vis && vis.Timeline){
        const el = document.getElementById('viz-vis-timeline');
        if(el){
          const items = new vis.DataSet(rows.map((r,i)=>{
            const y = String(r.when).match(/(19|20)\d{2}/);
            const start = y ? (y[0]+'-01-01') : (`2020-0${(i%9)+1}-01`);
            return { id:i+1, content: short(r.what, isNarrow()?22:40), start };
          }));
          state.timeline = new vis.Timeline(el, items, {
            stack:true, horizontalScroll:true, zoomKey:'ctrlKey',
            orientation:'top', margin:{ item:8 },
            height: isNarrow() ? 200 : 240
          });
        }
      }
      if(window.Plotly){
        const el = document.getElementById('viz-plotly-timeline');
        if(el){
          Plotly.newPlot(el, [{
            type:'scatter', mode:'lines+markers',
            x: rows.map(r=>r.when), y: rows.map((_,i)=>i+1),
            text: rows.map(r=>r.what),
            marker:{ color:'#5ec8ff', size:10 },
            line:{ color:'#3ee0a2' }
          }], {
            paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
            font:{ color:'#c9d7ea', size: isNarrow()?11:12 },
            margin:{ t:20,r:12,b: isNarrow()?70:40, l:36 },
            yaxis:{ title:'序', gridcolor:'#2a3544' },
            xaxis:{ gridcolor:'#2a3544', tickangle: isNarrow()?-35:0 }
          }, {responsive:true, displayModeBar:false});
        }
      }
    }

    /* —— compare —— */
    const firstCompare = compares[0] || null;
    if(firstCompare){
      const headers = firstCompare.headers || firstCompare[0] || [];
      const body = firstCompare.rows || firstCompare[1] || [];
      const fields = headers.map((h,i)=> 'c'+i);
      const dataRows = body.map(r=>{
        const o={}; fields.forEach((f,i)=>{ o[f]= (r&&r[i]!=null)? String(r[i]) : ''; }); return o;
      });
      if(window.Tabulator && document.getElementById('viz-tabulator-compare')){
        new Tabulator('#viz-tabulator-compare', {
          data: dataRows, layout:'fitDataStretch', height: tableH('240px'),
          columns: headers.map((h,i)=>({
            title:String(h), field:fields[i], minWidth:100, widthGrow:1,
            headerFilter: isNarrow()?false:'input', formatter:'textarea'
          }))
        });
      }
      if(window.gridjs && document.getElementById('viz-gridjs-compare')){
        new gridjs.Grid({
          columns: headers.map(String),
          data: body.map(r=> (r||[]).map(c=> String(c??''))),
          search: !isNarrow(), sort: true,
          pagination: { enabled:true, limit: isNarrow()?5:8 },
          style: { table:{ 'font-size': isNarrow()?'12px':'13px' } }
        }).render(document.getElementById('viz-gridjs-compare'));
      }
    }

    /* —— evolution —— */
    if(evolution.length){
      const rows = evolution.map(r=>({ stage:r.stage||r[0]||'', content:r.content||r[1]||'' }));
      if(window.Tabulator && document.getElementById('viz-tabulator-evolve')){
        new Tabulator('#viz-tabulator-evolve', {
          data: rows, layout:'fitDataStretch', height: tableH('200px'),
          columns:[
            {title:'階段', field:'stage', minWidth:90, widthGrow:1, headerFilter:isNarrow()?false:'input'},
            {title:'重點內容', field:'content', minWidth:140, widthGrow:3, headerFilter:isNarrow()?false:'input', formatter:'textarea'}
          ]
        });
      }
      const mEl = document.getElementById('viz-mermaid-evolve');
      if(mEl && window.mermaid){
        const dir = isNarrow() ? 'TD' : 'LR';
        let code = 'flowchart ' + dir + '\n';
        rows.forEach((r,i)=>{
          const id = 'S'+(i+1);
          const label = short(r.stage, isNarrow()?14:18).replace(/"/g,"'");
          code += `  ${id}["${label}"]\n`;
          if(i>0) code += `  S${i} --> ${id}\n`;
        });
        mEl.removeAttribute('data-processed');
        mEl.textContent = code;
        try { mermaid.run({ nodes: [mEl] }); } catch(e){
          try { mermaid.init(undefined, mEl); } catch(_e){}
        }
      }
      if(window.echarts){
        const el = document.getElementById('viz-echarts-evolve');
        if(el){
          const { w, h } = boxSize(el);
          const chart = echarts.init(el, 'dark');
          const n = rows.length || 1;
          chart.setOption({
            backgroundColor:'transparent',
            tooltip:{ formatter: p => (p.data && (p.data.name + '<br/>' + (p.data.value||''))) || '' },
            series:[{
              type:'graph', layout:'none', roam:true,
              label:{ show:true, color:'#e8eef7', fontSize: isNarrow()?10:12 },
              edgeSymbol:['none','arrow'],
              data: rows.map((r,i)=>({
                name: short(r.stage, isNarrow()?10:12),
                x: isNarrow() ? (w*0.5) : (40 + i * Math.max(70, (w-80)/Math.max(n-1,1))),
                y: isNarrow() ? (30 + i * Math.max(42, (h-60)/Math.max(n-1,1))) : (h*0.45),
                value: r.content
              })),
              links: rows.slice(1).map((_,i)=>({ source:i, target:i+1 }))
            }]
          });
          state.echarts.push(chart);
        }
      }
      if(window.d3){
        const el = document.getElementById('viz-d3-evolve');
        if(el){
          el.innerHTML = '';
          const { w } = boxSize(el);
          const height = Math.max(el.clientHeight || 240, 200);
          const svg = d3.select(el).append('svg').attr('width', w).attr('height', height);
          const root = { name:'演進', children: rows.map(r=>({ name: short(r.stage, isNarrow()?12:16), children:[{ name: short(r.content, isNarrow()?20:28) }] })) };
          const hier = d3.hierarchy(root);
          d3.tree().size([height-36, Math.max(120, w-120)])(hier);
          const g = svg.append('g').attr('transform','translate(56,18)');
          g.selectAll('.link').data(hier.links()).enter().append('path')
            .attr('class','link').attr('fill','none')
            .attr('d', d3.linkHorizontal().x(d=>d.y).y(d=>d.x));
          const node = g.selectAll('.node').data(hier.descendants()).enter().append('g')
            .attr('class','node').attr('transform', d=>`translate(${d.y},${d.x})`);
          node.append('circle').attr('r',4);
          node.append('text').attr('dy',3).attr('x', d=> d.children? -8:8)
            .attr('text-anchor', d=> d.children? 'end':'start').text(d=>d.data.name);
        }
      }
    }

    /* —— graphs —— */
    if(document.getElementById('viz-cytoscape') || document.getElementById('viz-vis-network')){
      const gNodes = nodes.length ? nodes : outline.map((o,i)=>({ id:'n'+i, label: short(o.title||('節'+(i+1)), 18) }));
      const gEdges = edges.length ? edges : gNodes.slice(1).map((n,i)=>({ from: gNodes[i].id, to: n.id }));
      if(window.cytoscape && gNodes.length && document.getElementById('viz-cytoscape')){
        state.cy = cytoscape({
          container: document.getElementById('viz-cytoscape'),
          elements: [
            ...gNodes.map(n=>({ data:{ id:String(n.id), label:n.label||String(n.id) } })),
            ...gEdges.map((e,i)=>({ data:{ id:'e'+i, source:String(e.from||e.source), target:String(e.to||e.target) } }))
          ],
          style:[
            { selector:'node', style:{ 'background-color':'#5ec8ff', 'label':'data(label)', 'color':'#e8eef7', 'font-size': isNarrow()?'9px':'10px', 'text-wrap':'wrap', 'text-max-width': isNarrow()?64:80 } },
            { selector:'edge', style:{ 'width':2, 'line-color':'#3ee0a2', 'target-arrow-color':'#3ee0a2', 'target-arrow-shape':'triangle', 'curve-style':'bezier' } }
          ],
          layout:{ name:'cose', animate:false, padding:16 }
        });
      }
      if(window.vis && vis.Network && gNodes.length && document.getElementById('viz-vis-network')){
        const el = document.getElementById('viz-vis-network');
        const ns = new vis.DataSet(gNodes.map(n=>({ id:n.id, label:n.label||String(n.id) })));
        const es = new vis.DataSet(gEdges.map((e,i)=>({ id:i, from:e.from||e.source, to:e.to||e.target })));
        state.network = new vis.Network(el, { nodes:ns, edges:es }, {
          nodes:{ shape:'dot', size: isNarrow()?11:14, font:{ color:'#e8eef7', size: isNarrow()?11:13 }, color:{ background:'#5ec8ff', border:'#3ee0a2' } },
          edges:{ color:'#6ee7f5', arrows:'to' },
          physics:{ stabilization:true },
          interaction:{ zoomView:true, dragView:true }
        });
      }
    }

    /* —— extra（HTML 已為每張圖建獨立格） —— */
    if(charts.length && window.Chart){
      charts.forEach((c, i)=>{
        const canvas = document.getElementById('viz-extra-chart-'+i);
        if(!canvas) return;
        const cfg = c.config || {};
        new Chart(canvas, {
          type: cfg.type || c.type || 'bar',
          data: cfg.data || { labels:c.labels||[], datasets:c.datasets||[] },
          options: Object.assign({
            responsive:true, maintainAspectRatio:false,
            plugins:{ legend:{ labels:{ color:'#c9d7ea' } } },
            scales:{
              x:{ ticks:{ color:'#93a4b8' }, grid:{ color:'#2a3544' } },
              y:{ ticks:{ color:'#93a4b8' }, grid:{ color:'#2a3544' } }
            }
          }, cfg.options||{})
        });
      });
    }
    const mHost = document.getElementById('viz-extra-mermaids');
    if(mHost && mermaids.length){
      mermaids.forEach((code)=>{
        const wrap = document.createElement('div');
        wrap.className = 'mb-3 mermaid-host';
        const pre = document.createElement('pre');
        pre.className = 'mermaid';
        pre.textContent = code;
        wrap.appendChild(pre);
        mHost.appendChild(wrap);
      });
      if(window.mermaid){
        try { mermaid.run({ querySelector: '#viz-extra-mermaids .mermaid' }); } catch(e){}
      }
    }

    setTimeout(fitAll, 80);
    setTimeout(fitAll, 320);
  }

  function requestInit(){
    // 等一幀確保 tab 已顯示、容器有寬度
    requestAnimationFrame(()=> requestAnimationFrame(initViz));
  }

  // 圖表 tab 顯示後才初始化（避免隱藏 tab 寬度為 0）
  const chartsBtn = document.getElementById('tab-charts-btn');
  if(chartsBtn){
    chartsBtn.addEventListener('shown.bs.tab', ()=> requestInit());
  }
  document.querySelectorAll('[data-bs-toggle="pill"]').forEach(btn=>{
    btn.addEventListener('shown.bs.tab', (ev)=>{
      const target = (ev.target && ev.target.getAttribute('data-bs-target')) || '';
      if(target === '#tab-charts') requestInit();
      else if(state.ready) setTimeout(fitAll, 50);
    });
  });

  // 若圖表本來就是作用中（或沒有 tabs），直接初始化
  if(chartsTabVisible()){
    requestInit();
  }

  let resizeTimer = null;
  window.addEventListener('resize', ()=>{
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(()=>{ if(state.ready) fitAll(); }, 120);
  });
  if(window.visualViewport){
    visualViewport.addEventListener('resize', ()=>{
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(()=>{ if(state.ready) fitAll(); }, 120);
    });
  }
})();
</script>
""".strip()


def payload_from_ebook(
    *,
    title: str,
    structs: dict[str, Any],
    lecture_secs: list[dict],
) -> dict[str, Any]:
    timeline = []
    for r in structs.get("timeline") or []:
        if isinstance(r, dict):
            timeline.append({"when": r.get("when", ""), "what": r.get("what", "")})
    compares = []
    for item in structs.get("compares") or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            compares.append({"headers": list(item[0]), "rows": [list(x) for x in item[1]]})
        elif isinstance(item, dict):
            compares.append(item)
    evolution = []
    for r in structs.get("evolution") or []:
        if isinstance(r, dict):
            evolution.append({"stage": r.get("stage", ""), "content": r.get("content", "")})
    outline = []
    nodes = []
    edges = []
    for i, sec in enumerate(lecture_secs or []):
        kids = [str(k.get("title") or "") for k in (sec.get("kids") or []) if k.get("title")]
        outline.append({"title": sec.get("title") or f"節 {i+1}", "kids": kids[:8]})
        nid = f"n{i}"
        nodes.append({"id": nid, "label": (sec.get("title") or f"節{i+1}")[:22]})
        if i:
            edges.append({"from": f"n{i-1}", "to": nid})
        for j, ktitle in enumerate(kids[:4]):
            kid_id = f"n{i}k{j}"
            nodes.append({"id": kid_id, "label": ktitle[:18]})
            edges.append({"from": nid, "to": kid_id})
    return {
        "title": title,
        "timeline": timeline,
        "compares": compares,
        "evolution": evolution,
        "outline": outline,
        "nodes": nodes[:40],
        "edges": edges[:50],
        "charts": [],
        "mermaids": [],
    }


def payload_from_tax_note(note: dict[str, Any]) -> dict[str, Any]:
    chapters = [c for c in (note.get("chapters") or []) if isinstance(c, dict)]
    outline = []
    nodes = []
    edges = []
    compares: list[dict] = []
    charts: list[dict] = []
    mermaids: list[str] = []
    timeline: list[dict] = []
    evolution: list[dict] = []

    for i, ch in enumerate(chapters):
        title = str(ch.get("title") or f"第 {i+1} 章")
        kps = [str(x) for x in (ch.get("key_points") or []) if str(x).strip()][:6]
        outline.append({"title": title, "kids": kps})
        nid = f"n{i}"
        nodes.append({"id": nid, "label": title[:22]})
        if i:
            edges.append({"from": f"n{i-1}", "to": nid})

        vis = ch.get("visual") if isinstance(ch.get("visual"), dict) else {}
        vtype = str(vis.get("type") or "").lower()
        if vtype == "table":
            headers = [str(h) for h in (vis.get("headers") or [])]
            rows = [[str(c) for c in (r if isinstance(r, (list, tuple)) else [r])] for r in (vis.get("rows") or [])]
            if headers and rows:
                compares.append({"headers": headers, "rows": rows})
                # 若首欄像年份，也塞進時序
                if any(re_year(h) for h in headers[:1]) or any(re_year(str(r[0])) for r in rows if r):
                    for r in rows:
                        if r:
                            timeline.append({"when": str(r[0]), "what": " / ".join(str(x) for x in r[1:])})
        if vtype == "compare":
            left_t = vis.get("leftTitle") or vis.get("left") or "A"
            right_t = vis.get("rightTitle") or vis.get("right") or "B"
            rows_out = []
            for r in vis.get("rows") or vis.get("items") or []:
                if isinstance(r, dict):
                    rows_out.append([str(r.get("left") or ""), str(r.get("right") or "")])
                elif isinstance(r, str) and "｜" in r:
                    a, b = r.split("｜", 1)
                    rows_out.append([a, b])
            if rows_out:
                compares.append({"headers": [str(left_t), str(right_t)], "rows": rows_out})
        if vtype == "chart":
            charts.append(
                {
                    "lib": "Chart.js",
                    "title": vis.get("title") or title,
                    "type": vis.get("chartType") or vis.get("chart_type") or "bar",
                    "labels": vis.get("labels") or [],
                    "datasets": vis.get("datasets") or [],
                }
            )
        if vtype == "mermaid":
            code = str(vis.get("code") or vis.get("mermaid") or "").strip()
            if code:
                mermaids.append(code)
        if vtype == "cards":
            for j, it in enumerate(vis.get("items") or []):
                if isinstance(it, dict):
                    evolution.append(
                        {
                            "stage": str(it.get("title") or f"重點{j+1}"),
                            "content": str(it.get("text") or it.get("body") or ""),
                        }
                    )
                elif isinstance(it, str):
                    evolution.append({"stage": f"重點{j+1}", "content": it})

    # dedupe evolution
    seen = set()
    evo2 = []
    for r in evolution:
        key = (r.get("stage"), r.get("content"))
        if key in seen:
            continue
        seen.add(key)
        evo2.append(r)

    return {
        "title": note.get("title") or "",
        "timeline": timeline[:30],
        "compares": compares[:4],
        "evolution": evo2[:16],
        "outline": outline,
        "nodes": nodes,
        "edges": edges,
        "charts": charts[:6],
        "mermaids": mermaids[:6],
    }


def re_year(s: str) -> bool:
    import re

    return bool(re.search(r"(19|20)\d{2}|年", s or ""))

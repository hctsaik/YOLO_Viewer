// === 由 index.html 內嵌 <script> 抽出的外部腳本(2026-07-08 離線/受限網路加固)===
// 內嵌 script 會被『內容過濾 proxy 剝除』或『CSP script-src 'self' 禁止執行』——那會讓
// componentReady 送不出去、觸發 Streamlit 60s『trouble loading』橫幅。改為同源外部 .js 後,
// 內容過濾器不剝外部 script、'self' 也允許同源外部 script,元件與主畫面一樣穩。行為與內嵌版逐字節相同。

// ---- Streamlit 元件協定(手寫,無 build;同 viewer_component 寫法)----
function post(m){ window.parent.postMessage(Object.assign({isStreamlitMessage:true}, m), "*"); }
function setH(h){ post({type:"streamlit:setFrameHeight", height:h}); }
function setVal(v){ post({type:"streamlit:setComponentValue", value:v, dataType:"json"}); }

const wall = document.getElementById('wall');
let evtN = 0;
let lastSig = null;

function render(items, selected, height, horizontal, markable){
  wall.className = horizontal ? 'horiz' : '';
  wall.innerHTML = '';
  (items || []).forEach((it, i) => {
    const cell = document.createElement('div');
    cell.className = 'cell' + (i === selected ? ' sel' : '');
    if (it.label != null) cell.title = String(it.label);  // 完整檔名 tooltip(角標可能被 ellipsis 截斷)

    const img = document.createElement('img');
    img.src = it.img || '';
    img.alt = (it.label != null ? String(it.label) : String(i + 1));
    img.draggable = false;
    cell.appendChild(img);

    // 角標(label 數字)
    const corner = document.createElement('div');
    corner.className = 'corner';
    corner.textContent = (it.label != null ? String(it.label) : String(i + 1));
    cell.appendChild(corner);

    // mark(⭐/✓)
    if (it.mark){
      const m = document.createElement('div');
      m.className = 'mark';
      m.textContent = it.mark;
      cell.appendChild(m);
    }

    // 偵測數徽章(nd>0)
    const nd = it.nd || 0;
    if (nd > 0){
      const b = document.createElement('div');
      b.className = 'badge';
      b.textContent = '🟥' + nd;
      cell.appendChild(b);
    }

    // 兩圖疊圖比較標記(左下角;自己的 click 用 stopPropagation 避免同時觸發整格選取)
    if (markable){
      const cm = document.createElement('div');
      const mk = it.cmpmark || '';
      cm.className = 'cmpmark' + (mk === '1' ? ' m1' : mk === '2' ? ' m2' : '');
      cm.textContent = mk === '1' ? '①' : (mk === '2' ? '②' : '○');
      cm.title = '標記此圖用於兩圖疊圖比較(最多同時標記 2 張)';
      cm.addEventListener('click', (e) => {
        e.stopPropagation();
        setVal({ type: 'mark', index: i, n: ++evtN });
      });
      cell.appendChild(cm);
    }

    // 整張可點 → 回該 index(選取/導覽)
    cell.addEventListener('click', () => {
      setVal({ type: 'select', index: i, n: ++evtN });
    });

    wall.appendChild(cell);
  });

  // setFrameHeight:用傳入 height(讓 Streamlit 容器夠高顯示整牆)
  setH(Math.max(120, height || 620));
}

window.addEventListener('message', (e) => {
  const d = e.data; if (!d || d.type !== 'streamlit:render') return;
  const args = d.args || {};
  const items = args.items || [];
  const selected = (args.selected != null) ? args.selected : 0;
  const height = args.height || 620;
  const horizontal = !!args.horizontal;
  const markable = !!args.markable;
  // 內容簽名(items 的 img/mark/nd/label/cmpmark + selected + horizontal + markable):變動才重繪
  const sig = JSON.stringify({ n: items.length, sel: selected, h: horizontal, mk: markable,
      s: items.map(it => [it.img, it.mark, it.nd, it.label, it.cmpmark]) });
  if (sig !== lastSig){
    lastSig = sig;
    render(items, selected, height, horizontal, markable);
  } else {
    setH(Math.max(120, height));
  }
});
post({type:"streamlit:componentReady", apiVersion:1}); setH(620);

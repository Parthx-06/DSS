/* ═══════════════════════════════════════════════
   NEXT CORE AI — DASHBOARD JS
   ═══════════════════════════════════════════════ */

let chartInstances = {};
let pipelineData = null;

// ─── Chart.js Defaults ───
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.padding = 14;

// ─── INIT ───
document.addEventListener('DOMContentLoaded', () => { loadAnalysis(); });

// ─── LOAD ANALYSIS ───
async function loadAnalysis() {
  try {
    const resp = await fetch('/api/analyze', { method: 'POST' });
    const data = await resp.json();
    if (data.error) { toast(data.error, 'error'); return; }
    updateKPIs(data.analysis);
    renderAllCharts(data.charts);
    renderAnomalies(data.anomalies);
    toast('Data loaded & charts rendered', 'success');
  } catch (e) { toast('Failed to load data: ' + e.message, 'error'); }
}

// ─── KPIs ───
function updateKPIs(a) {
  animateValue('kpiRevenue', (a.kpi_total_1 || 0).toLocaleString());
  animateValue('kpiProfit', (a.kpi_total_2 || 0).toLocaleString());
  animateValue('kpiMargin', (a.kpi_ratio || 0) + '%');
  animateValue('kpiTop', a.kpi_top || '—');
  
  // Also update KPI labels if available
  const labels = a.kpi_labels || {};
  if (labels.total_1) document.querySelector('#kpiRevenue').previousElementSibling.textContent = labels.total_1;
  if (labels.total_2) document.querySelector('#kpiProfit').previousElementSibling.textContent = labels.total_2;
  if (labels.ratio) document.querySelector('#kpiMargin').previousElementSibling.textContent = labels.ratio;
  if (labels.top) document.querySelector('#kpiTop').previousElementSibling.textContent = labels.top;
}
function animateValue(id, valStr) {
  const el = document.getElementById(id);
  if (!el) return;
  
  let prefix = '';
  let suffix = '';
  let cleanStr = String(valStr);
  if (cleanStr.includes('%')) { suffix = '%'; cleanStr = cleanStr.replace('%', ''); }
  else if (el.textContent.includes('%')) { suffix = '%'; }
  if (el.textContent.includes('$')) { prefix = '$'; }
  
  const target = parseFloat(cleanStr.replace(/,/g, ''));
  if (isNaN(target)) {
    el.style.opacity = '0'; el.style.transform = 'translateY(10px)';
    setTimeout(() => { el.textContent = `${prefix}${valStr}${suffix}`; el.style.transition = 'all .4s'; el.style.opacity = '1'; el.style.transform = 'none'; }, 100);
    return;
  }
  
  const duration = 1200; // ms
  const stepTime = 20;
  const steps = duration / stepTime;
  const inc = target / steps;
  let current = 0;
  
  el.style.opacity = '1'; el.style.transform = 'none';
  
  const timer = setInterval(() => {
    current += inc;
    if (current >= target) {
      current = target;
      clearInterval(timer);
    }
    const isDec = target % 1 !== 0;
    el.textContent = prefix + current.toLocaleString('en-US', { minimumFractionDigits: isDec ? 2 : 0, maximumFractionDigits: isDec ? 2 : 0 }) + suffix;
  }, stepTime);
}

// ─── RENDER DYNAMIC CHARTS ───
function renderAllCharts(charts) {
  const grid = document.getElementById('chartsGrid');
  const keys = Object.keys(charts).sort();
  document.getElementById('chartCount').textContent = keys.length + ' Charts';
  
  if (keys.length === 0) {
    grid.innerHTML = '<div class="chart-card" style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text2);">No charts available.</div>';
    return;
  }
  
  grid.innerHTML = '';
  
  keys.forEach((key, i) => {
    const cd = charts[key];
    if (!cd) return;
    
    // Create DOM element
    const card = document.createElement('div');
    card.className = 'chart-card' + (cd.type === 'pie' || cd.type === 'doughnut' || cd.type === 'radar' || cd.indexAxis === 'y' ? ' chart-sm' : '');
    card.id = 'cc_' + key;
    card.innerHTML = `<div class="chart-header">${cd.title || key}</div><canvas id="canvas_${key}"></canvas>`;
    grid.appendChild(card);
    
    // Destroy existing if any (shouldn't happen with innerHTML='')
    if (chartInstances[key]) chartInstances[key].destroy();

    const ctx = document.getElementById('canvas_' + key).getContext('2d');
    const cfg = { type: cd.type, data: cd.data, options: getChartOptions(cd) };
    chartInstances[key] = new Chart(ctx, cfg);
  });
}

function getChartOptions(cd) {
  const opts = {
    responsive: true, maintainAspectRatio: false,
    animation: { duration: 1200, easing: 'easeOutQuart' },
    plugins: {
      legend: { display: true, position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
      tooltip: {
        backgroundColor: 'rgba(15,23,42,0.95)', titleColor: '#f1f5f9', bodyColor: '#94a3b8',
        borderColor: 'rgba(99,102,241,0.3)', borderWidth: 1, padding: 12, cornerRadius: 10,
        displayColors: true, boxPadding: 4,
      },
    },
    scales: {},
  };

  if (cd.type === 'bar' || cd.type === 'line') {
    opts.scales = {
      x: { grid: { display: false }, ticks: { font: { size: 11 } } },
      y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { font: { size: 11 } }, beginAtZero: true },
    };
  }
  if (cd.indexAxis === 'y') opts.indexAxis = 'y';
  if (cd.stacked) {
    opts.scales.x.stacked = true;
    opts.scales.y.stacked = true;
  }
  if (cd.type === 'pie' || cd.type === 'doughnut') {
    opts.scales = {};
    opts.plugins.legend.position = 'right';
  }
  if (cd.type === 'radar') {
    opts.scales = { r: { grid: { color: 'rgba(255,255,255,0.06)' }, angleLines: { color: 'rgba(255,255,255,0.06)' },
      pointLabels: { font: { size: 10 } }, ticks: { display: false }, beginAtZero: true, max: 100 } };
  }
  return opts;
}

// ─── ANOMALIES ───
function renderAnomalies(anomalies) {
  const el = document.getElementById('anomalyPanel');
  if (!anomalies || anomalies.length === 0) { el.innerHTML = '<div class="step-placeholder">✅ No anomalies detected</div>'; return; }
  el.innerHTML = anomalies.map(a =>
    `<div class="anomaly-item anom-${a.severity}">⚠️ ${a.message}</div>`
  ).join('');
}

// ─── RUN FULL PIPELINE ───
async function runFullPipeline() {
  const dot = document.querySelector('.dot');
  const label = document.getElementById('pipelineLabel');
  const stepsEl = document.getElementById('pipelineSteps');

  dot.className = 'dot dot-running'; label.textContent = 'Running...';
  const defSteps = [
    {step:1,name:'Analyzing CSV',icon:'📊',status:'pending'},
    {step:2,name:'Generating Charts',icon:'📈',status:'pending'},
    {step:3,name:'Detecting Anomalies',icon:'🔍',status:'pending'},
    {step:4,name:'Fetching News',icon:'📰',status:'pending'},
    {step:5,name:'AI Predictions',icon:'🤖',status:'pending'},
    {step:6,name:'Email Report',icon:'📧',status:'pending'},
    {step:7,name:'Supplier Alerts',icon:'📦',status:'pending'},
  ];
  stepsEl.innerHTML = defSteps.map(renderPipelineStep).join('');
  toast('Agentic pipeline started...', 'info');

  try {
    const resp = await fetch('/api/run-pipeline', { method: 'POST' });
    const data = await resp.json();
    pipelineData = data;

    if (data.steps) stepsEl.innerHTML = data.steps.map(renderPipelineStep).join('');

    if (data.status === 'completed') {
      dot.className = 'dot dot-done'; label.textContent = 'Completed';
      toast('✅ Pipeline completed successfully!', 'success');
      // Refresh charts
      if (data.charts) renderAllCharts(data.charts);
      if (data.data) updateKPIs(data.data);
      if (data.anomalies) renderAnomalies(data.anomalies);
      if (data.predictions) renderPredictions(data.predictions);
      if (data.news) renderNews(data.news);
      // Update outlook KPI
      if (data.predictions) {
        const o = data.predictions.overall_outlook || '—';
        const el = document.getElementById('kpiOutlook');
        el.textContent = o.toUpperCase();
        el.style.color = o === 'bullish' ? '#34d399' : o === 'bearish' ? '#ef4444' : '#fbbf24';
      }
    } else {
      dot.className = 'dot dot-fail'; label.textContent = 'Failed';
      toast('❌ Pipeline failed: ' + (data.error || ''), 'error');
    }
  } catch (e) {
    dot.className = 'dot dot-fail'; label.textContent = 'Error';
    toast('Network error: ' + e.message, 'error');
  }
}

function renderPipelineStep(s) {
  let dc = 'psd-pending', di = '';
  if (s.status === 'running') { dc = 'psd-running'; di = '⏳'; }
  else if (s.status === 'completed') { dc = 'psd-done'; di = '✓'; }
  else if (s.status === 'warning') { dc = 'psd-warn'; di = '!'; }
  return `<div class="p-step">
    <div class="p-step-icon">${s.icon}</div>
    <div class="p-step-info"><div class="p-step-name">${s.name}</div>
    ${s.result ? `<div class="p-step-result">${s.result}</div>` : ''}</div>
    <div class="p-step-dot ${dc}">${di}</div></div>`;
}

// ─── PREDICTIONS ───
function renderPredictions(preds) {
  const el = document.getElementById('predictionsPanel');
  if (!preds || !preds.product_predictions || preds.product_predictions.length === 0) {
    el.innerHTML = '<div class="step-placeholder">No predictions</div>'; return;
  }
  let html = `<div class="pred-card" style="margin-bottom:12px;border-left:3px solid var(--indigo);padding-left:14px;">
    <div style="font-size:.78rem;color:var(--text2);">Overall Outlook</div>
    <div style="font-size:1.1rem;font-weight:800;color:${preds.overall_outlook==='bullish'?'var(--green)':preds.overall_outlook==='bearish'?'var(--red)':'var(--amber)'};">
      ${(preds.overall_outlook||'').toUpperCase()} · ${preds.confidence||0}%
    </div>
    <div style="font-size:.78rem;color:var(--text2);margin-top:4px;">${preds.summary||''}</div>
  </div>`;

  preds.product_predictions.forEach(p => {
    const tc = p.trend === 'increasing' ? 'var(--green)' : p.trend === 'decreasing' ? 'var(--red)' : 'var(--amber)';
    const ti = p.trend === 'increasing' ? '📈' : p.trend === 'decreasing' ? '📉' : '➡️';
    const ai = p.action === 'increase_stock' ? '🟢' : p.action === 'decrease_stock' ? '🔴' : '🟡';
    html += `<div class="pred-card">
      <div class="pred-prod">${p.product}</div>
      <div class="pred-trend" style="color:${tc};">${ti} ${p.trend} · ${(p.predicted_change_percent||0) > 0 ? '+' : ''}${p.predicted_change_percent||0}% · Conf: ${p.confidence||0}%</div>
      <div class="pred-action">${ai} ${(p.action||'').replace(/_/g,' ')} — ${p.reasoning||''}</div>
    </div>`;
  });

  if (preds.key_insights && preds.key_insights.length) {
    html += '<div style="margin-top:10px;font-size:.78rem;font-weight:700;color:var(--text2);">Key Insights</div>';
    preds.key_insights.forEach(x => { html += `<div style="font-size:.76rem;color:var(--muted);margin:3px 0;">💡 ${x}</div>`; });
  }
  el.innerHTML = html;
}

// ─── NEWS ───
function renderNews(news) {
  const el = document.getElementById('newsPanel');
  if (!news || !news.articles || news.articles.length === 0) {
    el.innerHTML = '<div class="step-placeholder">No news found</div>'; return;
  }
  el.innerHTML = news.articles.slice(0, 10).map(a =>
    `<div class="news-item">
      <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px;">
        <span class="news-badge">${a.product}</span>
        <span style="font-size:.65rem;color:var(--muted);">${a.source}</span>
      </div>
      <div class="news-title">${a.url ? `<a href="${a.url}" target="_blank" style="color:var(--text);text-decoration:none;">${a.title}</a>` : a.title}</div>
      <div class="news-meta"><span>${a.publishedAt ? new Date(a.publishedAt).toLocaleDateString() : ''}</span></div>
    </div>`
  ).join('');
}

// ─── WHAT-IF SCENARIO ───
async function runWhatIf() {
  const input = document.getElementById('whatifInput');
  const result = document.getElementById('whatifResult');
  const scenario = input.value.trim();
  if (!scenario) { toast('Enter a scenario first', 'error'); return; }

  result.innerHTML = '<div style="color:var(--amber);font-size:.82rem;">⏳ Analyzing scenario...</div>';
  try {
    const resp = await fetch('/api/what-if', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({scenario}) });
    const data = await resp.json();
    if (data.error) { result.innerHTML = `<div style="color:var(--red);">❌ ${data.error}</div>`; return; }

    let html = `<div style="margin-top:8px;">
      <div style="font-weight:700;font-size:.85rem;">${data.scenario || scenario}</div>
      <div style="font-size:.8rem;color:var(--text2);margin:6px 0;">${data.impact_summary || ''}</div>
      <div style="font-size:.75rem;color:var(--muted);">Risk: <span style="color:${data.overall_risk==='high'?'var(--red)':data.overall_risk==='medium'?'var(--amber)':'var(--green)'};">${(data.overall_risk||'').toUpperCase()}</span></div>`;
    if (data.product_impacts) {
      data.product_impacts.forEach(p => {
        html += `<div style="font-size:.78rem;margin-top:6px;padding:6px 10px;background:rgba(255,255,255,.02);border-radius:8px;">
          <strong>${p.product}</strong>: Sales ${(p.sales_change_percent||0)>0?'+':''}${p.sales_change_percent||0}%, Profit ${(p.profit_change_percent||0)>0?'+':''}${p.profit_change_percent||0}%
          <div style="font-size:.72rem;color:var(--muted);">${p.explanation||''}</div></div>`;
      });
    }
    html += `<div style="font-size:.78rem;color:var(--green);margin-top:8px;">💡 ${data.recommendation || ''}</div></div>`;
    result.innerHTML = html;
  } catch (e) { result.innerHTML = `<div style="color:var(--red);">❌ ${e.message}</div>`; }
}

// ─── QUICK ACTIONS ───
async function emailReport() {
  toast('📧 Generating & sending report...', 'info');
  try {
    const resp = await fetch('/api/manager-report', { method: 'POST' });
    const data = await resp.json();
    toast(data.success ? '✅ Report emailed to manager!' : '❌ ' + data.message, data.success ? 'success' : 'error');
  } catch (e) { toast('❌ ' + e.message, 'error'); }
}

async function alertSuppliers() {
  if (!pipelineData || !pipelineData.predictions) { toast('Run the pipeline first', 'error'); return; }
  toast('📦 Sending supplier alerts...', 'info');
  try {
    const resp = await fetch('/api/supplier-alert', { method: 'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({predictions: pipelineData.predictions}) });
    const data = await resp.json();
    const count = data.results ? data.results.length : 0;
    toast(`✅ Sent ${count} supplier alerts`, 'success');
  } catch (e) { toast('❌ ' + e.message, 'error'); }
}

function toggleCalcs() {
  const el = document.getElementById('calcsSection');
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
  if (el.style.display === 'block') el.scrollIntoView({behavior: 'smooth'});
}

// ─── CALCULATORS ───
function calcEOQ() {
  const D=parseFloat(document.getElementById('eoqD').value), S=parseFloat(document.getElementById('eoqS').value), H=parseFloat(document.getElementById('eoqH').value);
  if(D>0&&S>0&&H>0){const q=Math.sqrt(2*D*S/H),o=D/q,c=(q/2)*H+(D/q)*S;
    document.getElementById('eoqRes').innerHTML=`📦 EOQ: <strong>${q.toFixed(0)}</strong> units | Orders/yr: <strong>${o.toFixed(1)}</strong> | Cost: <strong>$${c.toFixed(2)}</strong>`;
  }else toast('Enter positive values','error');
}
function calcROP() {
  const d=parseFloat(document.getElementById('ropD').value),s=parseFloat(document.getElementById('ropS').value),
    l=parseFloat(document.getElementById('ropL').value),sl=parseFloat(document.getElementById('ropSL').value)/100;
  let z; if(sl<=.9)z=1.28;else if(sl<=.95)z=1.28+(1.645-1.28)*((sl-.9)/.05);else if(sl<=.99)z=1.645+(2.33-1.645)*((sl-.95)/.04);else z=2.33;
  const ss=z*s*Math.sqrt(l),rop=d*l+ss;
  document.getElementById('ropRes').innerHTML=`🛡️ Safety Stock: <strong>${ss.toFixed(0)}</strong> | Reorder Point: <strong>${rop.toFixed(0)}</strong>`;
}
function calcBE() {
  const f=parseFloat(document.getElementById('beF').value),v=parseFloat(document.getElementById('beV').value),p=parseFloat(document.getElementById('beP').value);
  if(p>v){const u=f/(p-v),r=u*p;document.getElementById('beRes').innerHTML=`📊 BEP: <strong>${u.toFixed(0)}</strong> units | Revenue: <strong>$${r.toFixed(0)}</strong>`;}
  else toast('Price must exceed variable cost','error');
}
function calcMOB() {
  const f=parseFloat(document.getElementById('mobF').value),v=parseFloat(document.getElementById('mobV').value),
    b=parseFloat(document.getElementById('mobB').value),q=parseFloat(document.getElementById('mobQ').value);
  const mc=f+v*q,bc=b*q,d=mc<bc?'MAKE ✅':bc<mc?'BUY ✅':'INDIFFERENT';
  document.getElementById('mobRes').innerHTML=`🏭 Make: <strong>$${mc.toFixed(0)}</strong> | Buy: <strong>$${bc.toFixed(0)}</strong> | Decision: <strong>${d}</strong>`;
}

// ─── TOAST ───
function toast(msg, type='info') {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity='0'; t.style.transition='opacity .4s'; setTimeout(()=>t.remove(),400); }, 4000);
}

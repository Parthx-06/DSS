/* ═══════════════════════════════════════════════
   NEXUS DSS — DASHBOARD JS (Decision Support System)
   ═══════════════════════════════════════════════ */

let chartInstances = {};
let pipelineData = null;
let dssData = null;

// ─── Chart.js Defaults ───
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(255,255,255,0.05)';
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.padding = 12;

// ─── INIT ───
document.addEventListener('DOMContentLoaded', () => { loadAnalysis(); loadDSS(); });

// ─── TAB SWITCHING ───
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');
  document.getElementById('tab-' + tabId).classList.add('active');
}

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

// ─── LOAD DSS ───
async function loadDSS() {
  try {
    const resp = await fetch('/api/dss-analysis', { method: 'POST' });
    const data = await resp.json();
    if (data.error) { toast(data.error, 'error'); return; }
    dssData = data;
    renderDSSTab(data);
    renderForecastTab(data);
  } catch (e) { console.error('DSS load error:', e); }
}

// ─── KPIs ───
function updateKPIs(a) {
  animateValue('kpiRevenue', (a.kpi_total_1 || 0).toLocaleString());
  animateValue('kpiProfit', (a.kpi_total_2 || 0).toLocaleString());
  animateValue('kpiMargin', (a.kpi_ratio || 0) + '%');
  animateValue('kpiTop', a.kpi_top || '—');
  const labels = a.kpi_labels || {};
  if (labels.total_1) document.querySelector('#kpiRevenue').previousElementSibling.textContent = labels.total_1;
  if (labels.total_2) document.querySelector('#kpiProfit').previousElementSibling.textContent = labels.total_2;
  if (labels.ratio) document.querySelector('#kpiMargin').previousElementSibling.textContent = labels.ratio;
  if (labels.top) document.querySelector('#kpiTop').previousElementSibling.textContent = labels.top;
}

function animateValue(id, valStr) {
  const el = document.getElementById(id);
  if (!el) return;
  let prefix = '', suffix = '', cleanStr = String(valStr);
  if (cleanStr.includes('%')) { suffix = '%'; cleanStr = cleanStr.replace('%', ''); }
  else if (el.textContent.includes('%')) { suffix = '%'; }
  if (el.textContent.includes('$')) { prefix = '$'; }
  const target = parseFloat(cleanStr.replace(/,/g, ''));
  if (isNaN(target)) { el.textContent = `${prefix}${valStr}${suffix}`; return; }
  const duration = 1200, stepTime = 20, steps = duration / stepTime, inc = target / steps;
  let current = 0;
  const timer = setInterval(() => {
    current += inc;
    if (current >= target) { current = target; clearInterval(timer); }
    const isDec = target % 1 !== 0;
    el.textContent = prefix + current.toLocaleString('en-US', { minimumFractionDigits: isDec ? 2 : 0, maximumFractionDigits: isDec ? 2 : 0 }) + suffix;
  }, stepTime);
}

// ─── RENDER CHARTS ───
function renderAllCharts(charts) {
  const grid = document.getElementById('chartsGrid');
  const keys = Object.keys(charts).sort();
  document.getElementById('chartCount').textContent = keys.length + ' Charts';
  if (keys.length === 0) { grid.innerHTML = '<div class="chart-card" style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text2);">No charts available.</div>'; return; }
  grid.innerHTML = '';
  keys.forEach((key) => {
    const cd = charts[key];
    if (!cd) return;
    const card = document.createElement('div');
    const isSmall = cd.type === 'pie' || cd.type === 'doughnut' || cd.type === 'radar' || cd.type === 'polarArea' || cd.indexAxis === 'y';
    card.className = 'chart-card' + (isSmall ? ' chart-sm' : '');
    card.id = 'cc_' + key;
    const badge = cd.type === 'scatter' ? '<span class="chart-badge" style="background:rgba(34,211,238,.1);color:#22d3ee;">SCATTER</span>'
      : cd.type === 'bubble' ? '<span class="chart-badge" style="background:rgba(168,85,247,.1);color:#a855f7;">BUBBLE</span>'
      : cd.type === 'polarArea' ? '<span class="chart-badge" style="background:rgba(244,114,182,.1);color:#f472b6;">POLAR</span>'
      : '';
    card.innerHTML = `<div class="chart-header">${cd.title || key}${badge}</div><canvas id="canvas_${key}"></canvas>`;
    grid.appendChild(card);
    if (chartInstances[key]) chartInstances[key].destroy();
    const ctx = document.getElementById('canvas_' + key).getContext('2d');
    chartInstances[key] = new Chart(ctx, { type: cd.type, data: cd.data, options: getChartOptions(cd) });
  });
}

function getChartOptions(cd) {
  const opts = {
    responsive: true, maintainAspectRatio: false,
    animation: { duration: 1000, easing: 'easeOutQuart' },
    plugins: {
      legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } },
      tooltip: { backgroundColor: 'rgba(6,10,19,0.95)', titleColor: '#f1f5f9', bodyColor: '#94a3b8',
        borderColor: 'rgba(129,140,248,0.25)', borderWidth: 1, padding: 10, cornerRadius: 8 },
    },
    scales: {},
  };
  if (cd.type === 'bar' || cd.type === 'line') {
    opts.scales = {
      x: { grid: { display: false }, ticks: { font: { size: 10 } } },
      y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { font: { size: 10 } }, beginAtZero: true },
    };
  }
  if (cd.type === 'scatter' || cd.type === 'bubble') {
    opts.scales = {
      x: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { font: { size: 10 } } },
      y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { font: { size: 10 } } },
    };
  }
  if (cd.indexAxis === 'y') opts.indexAxis = 'y';
  if (cd.stacked) { opts.scales.x.stacked = true; opts.scales.y.stacked = true; }
  if (cd.type === 'pie' || cd.type === 'doughnut' || cd.type === 'polarArea') {
    opts.scales = {};
    opts.plugins.legend.position = 'right';
  }
  if (cd.type === 'radar') {
    opts.scales = { r: { grid: { color: 'rgba(255,255,255,0.05)' }, angleLines: { color: 'rgba(255,255,255,0.05)' },
      pointLabels: { font: { size: 9 } }, ticks: { display: false }, beginAtZero: true, max: 100 } };
  }
  return opts;
}

// ═══════════════════════════════════════════════
// DSS TAB RENDERING
// ═══════════════════════════════════════════════
function renderDSSTab(dss) {
  const grid = document.getElementById('dssGrid');
  let html = '';

  // ── Pareto / ABC Analysis ──
  const pareto = dss.pareto || {};
  if (pareto.tiers && Object.keys(pareto.tiers).length > 0) {
    html += `<div class="dss-card dss-card-full"><div class="dss-card-title">📊 Pareto / ABC Analysis <span class="dss-badge" style="background:rgba(52,211,153,.1);color:#34d399;">PRIORITIZATION</span></div>
      <canvas id="paretoChart" style="max-height:260px;"></canvas>
      <div style="margin-top:12px;overflow-x:auto;"><table class="dss-table"><thead><tr><th>Category</th><th>Value</th><th>Share %</th><th>Cumulative %</th><th>Tier</th></tr></thead><tbody>`;
    for (const [cat, t] of Object.entries(pareto.tiers)) {
      html += `<tr><td style="font-weight:600;">${cat}</td><td>$${t.value.toLocaleString()}</td><td>${t.pct}%</td><td>${t.cumulative_pct}%</td><td><span class="tier-${t.tier}">${t.tier}</span></td></tr>`;
    }
    html += `</tbody></table></div></div>`;
  }

  // ── Decision Matrix ──
  const dm = dss.decision_matrix || {};
  if (dm.matrix && dm.matrix.length > 0) {
    html += `<div class="dss-card dss-card-full"><div class="dss-card-title">🎯 Decision Matrix <span class="dss-badge" style="background:rgba(129,140,248,.1);color:#818cf8;">WEIGHTED SCORING (${dm.weight_per_criteria}% each)</span></div>
      <div style="overflow-x:auto;"><table class="dss-table"><thead><tr><th>#</th><th>Category</th>`;
    dm.criteria.forEach(c => { html += `<th>${c}</th>`; });
    html += `<th>Score</th></tr></thead><tbody>`;
    dm.matrix.forEach(m => {
      html += `<tr><td class="rank-cell">${m.rank}</td><td style="font-weight:600;">${m.category}</td>`;
      dm.criteria.forEach(c => {
        const n = m.scores[c]?.normalized || 0;
        const color = n > 70 ? 'var(--green)' : n > 40 ? 'var(--amber)' : 'var(--red)';
        html += `<td><span style="color:${color};font-weight:600;">${n}</span><span style="color:var(--muted);font-size:.65rem;"> /100</span></td>`;
      });
      const sc = m.weighted_total;
      html += `<td><span style="font-weight:800;font-size:.9rem;color:${sc > 70 ? 'var(--green)' : sc > 40 ? 'var(--amber)' : 'var(--red)'};">${sc}</span></td></tr>`;
    });
    html += `</tbody></table></div></div>`;
  }

  // ── Risk Scoring ──
  const risk = dss.risk || {};
  if (risk.risks && risk.risks.length > 0) {
    html += `<div class="dss-card"><div class="dss-card-title">🛡️ Risk Assessment</div>
      <div style="overflow-x:auto;"><table class="dss-table"><thead><tr><th>Category</th><th>Risk</th><th>Level</th><th>Share</th></tr></thead><tbody>`;
    risk.risks.forEach(r => {
      html += `<tr><td style="font-weight:600;">${r.category}</td><td style="font-weight:700;">${r.risk_score}</td><td><span class="risk-${r.risk_level}">${r.risk_level}</span></td><td>${r.share_pct}%</td></tr>`;
    });
    html += `</tbody></table></div></div>`;
  }

  // ── Concentration / HHI ──
  const hhi = dss.concentration || {};
  if (hhi.hhi !== undefined) {
    const pct = Math.min(hhi.hhi / 10000 * 100, 100);
    const hhiColor = hhi.hhi > 2500 ? 'var(--red)' : hhi.hhi > 1500 ? 'var(--amber)' : 'var(--green)';
    const gradColor = hhi.hhi > 2500 ? '#f87171,#ef4444' : hhi.hhi > 1500 ? '#fbbf24,#f59e0b' : '#34d399,#10b981';
    html += `<div class="dss-card"><div class="dss-card-title">📏 Concentration Index (HHI)</div>
      <div class="hhi-gauge"><div class="hhi-bar-container"><div class="hhi-bar" style="width:${pct}%;background:linear-gradient(90deg,${gradColor});"></div></div>
        <div class="hhi-value" style="color:${hhiColor};">${hhi.hhi}</div></div>
      <div class="hhi-interpretation">${hhi.interpretation}</div>
      <div style="font-size:.68rem;color:var(--muted);margin-top:6px;">Scale: 0 (Perfect diversification) → 10,000 (Single monopoly)</div></div>`;
  }

  // ── Period Comparison ──
  const pc = dss.period_comparison || {};
  if (pc.comparison && pc.comparison.length > 0) {
    html += `<div class="dss-card dss-card-full"><div class="dss-card-title">📅 Period Comparison <span class="dss-badge" style="background:rgba(56,189,248,.1);color:#38bdf8;">${pc.period_1_label || 'P1'} vs ${pc.period_2_label || 'P2'}</span></div>
      <canvas id="periodChart" style="max-height:240px;"></canvas>
      <div style="margin-top:10px;overflow-x:auto;"><table class="dss-table"><thead><tr><th>Category</th><th>${pc.period_1_label || 'Period 1'}</th><th>${pc.period_2_label || 'Period 2'}</th><th>Change</th><th>Momentum</th></tr></thead><tbody>`;
    pc.comparison.forEach(c => {
      html += `<tr><td style="font-weight:600;">${c.category}</td><td>$${c.period_1.toLocaleString()}</td><td>$${c.period_2.toLocaleString()}</td>
        <td style="color:${c.change_pct > 0 ? 'var(--green)' : c.change_pct < 0 ? 'var(--red)' : 'var(--amber)'};">${c.change_pct > 0 ? '+' : ''}${c.change_pct}%</td>
        <td class="momentum-${c.momentum}">${c.momentum === 'Accelerating' ? '🚀' : c.momentum === 'Decelerating' ? '📉' : '➡️'} ${c.momentum}</td></tr>`;
    });
    html += `</tbody></table></div></div>`;
  }

  grid.innerHTML = html || '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text2);">No DSS data available. Upload data first.</div>';

  // Render Pareto Chart
  setTimeout(() => {
    if (pareto.chart_data && pareto.chart_data.labels) renderParetoChart(pareto.chart_data);
    if (pc.comparison && pc.comparison.length > 0) renderPeriodChart(pc);
  }, 100);
}

function renderParetoChart(cd) {
  const ctx = document.getElementById('paretoChart');
  if (!ctx) return;
  if (chartInstances['pareto']) chartInstances['pareto'].destroy();
  chartInstances['pareto'] = new Chart(ctx.getContext('2d'), {
    type: 'bar',
    data: {
      labels: cd.labels,
      datasets: [
        { label: 'Value', data: cd.values, backgroundColor: cd.tier_colors.map(c => c + '99'), borderColor: cd.tier_colors, borderWidth: 2, borderRadius: 6, order: 2, yAxisID: 'y' },
        { label: 'Cumulative %', data: cd.cumulative, type: 'line', borderColor: '#818cf8', backgroundColor: 'rgba(129,140,248,.1)',
          tension: 0.4, fill: true, pointRadius: 5, pointBackgroundColor: '#818cf8', pointBorderColor: '#fff', pointBorderWidth: 2, order: 1, yAxisID: 'y1' }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 1200 },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } },
        tooltip: { backgroundColor: 'rgba(6,10,19,0.95)', borderColor: 'rgba(129,140,248,0.25)', borderWidth: 1, padding: 10, cornerRadius: 8 }},
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10 } } },
        y: { position: 'left', grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { font: { size: 10 } }, beginAtZero: true },
        y1: { position: 'right', grid: { display: false }, ticks: { font: { size: 10 }, callback: v => v + '%' }, min: 0, max: 100 }
      }
    }
  });
}

function renderPeriodChart(pc) {
  const ctx = document.getElementById('periodChart');
  if (!ctx) return;
  if (chartInstances['period']) chartInstances['period'].destroy();
  const labels = pc.comparison.map(c => c.category);
  chartInstances['period'] = new Chart(ctx.getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: pc.period_1_label || 'Period 1', data: pc.comparison.map(c => c.period_1), backgroundColor: 'rgba(129,140,248,.6)', borderColor: '#818cf8', borderWidth: 2, borderRadius: 6 },
        { label: pc.period_2_label || 'Period 2', data: pc.comparison.map(c => c.period_2), backgroundColor: 'rgba(34,211,238,.6)', borderColor: '#22d3ee', borderWidth: 2, borderRadius: 6 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 1000 },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } },
      scales: { x: { grid: { display: false } }, y: { grid: { color: 'rgba(255,255,255,0.03)' }, beginAtZero: true } }
    }
  });
}

// ═══════════════════════════════════════════════
// FORECASTING TAB
// ═══════════════════════════════════════════════
function renderForecastTab(dss) {
  const grid = document.getElementById('forecastGrid');
  let html = '';
  const fc = dss.forecast || {};

  // ── Forecast Chart ──
  if (fc.actual && fc.actual.length > 0) {
    const trendColor = fc.trend === 'growing' ? 'var(--green)' : fc.trend === 'declining' ? 'var(--red)' : 'var(--amber)';
    const trendIcon = fc.trend === 'growing' ? '📈' : fc.trend === 'declining' ? '📉' : '➡️';
    html += `<div class="dss-card dss-card-full"><div class="dss-card-title">📈 Statistical Forecast <span class="dss-badge" style="background:rgba(52,211,153,.1);color:#34d399;">LINEAR REGRESSION + MA</span></div>
      <div class="forecast-metric">
        <div class="forecast-stat"><div class="forecast-stat-label">Trend</div><div class="forecast-stat-value" style="color:${trendColor};">${trendIcon} ${fc.trend?.toUpperCase()}</div></div>
        <div class="forecast-stat"><div class="forecast-stat-label">Slope</div><div class="forecast-stat-value">${fc.slope}</div></div>
        <div class="forecast-stat"><div class="forecast-stat-label">Std Error</div><div class="forecast-stat-value">±${fc.std_error}</div></div>`;
    if (fc.forecast && fc.forecast.length > 0) {
      html += `<div class="forecast-stat"><div class="forecast-stat-label">Next Period</div><div class="forecast-stat-value" style="color:var(--indigo);">$${fc.forecast[0].value.toLocaleString()}</div></div>`;
    }
    html += `</div><canvas id="forecastChart" style="max-height:280px;"></canvas></div>`;
  }

  // ── Sensitivity ──
  const sens = dss.sensitivity || {};
  if (sens.sensitivities && sens.sensitivities.length > 0) {
    const maxRank = Math.max(...sens.sensitivities.map(s => s.sensitivity_rank));
    html += `<div class="dss-card"><div class="dss-card-title">🎚️ Sensitivity Analysis <span class="dss-badge" style="background:rgba(248,113,113,.1);color:#f87171;">IMPACT RANKING</span></div>`;
    sens.sensitivities.forEach((s, i) => {
      const pct = maxRank > 0 ? (s.sensitivity_rank / maxRank * 100) : 0;
      const colors = ['#818cf8', '#f472b6', '#22d3ee', '#a78bfa', '#34d399', '#fbbf24', '#f87171', '#38bdf8'];
      const c = colors[i % colors.length];
      html += `<div class="sensitivity-bar"><div class="sensitivity-label">${s.category}</div>
        <div class="sensitivity-track"><div class="sensitivity-fill" style="width:${pct}%;background:${c};"></div></div>
        <div class="sensitivity-val">${s.share_pct}%</div></div>`;
    });
    html += `<div style="margin-top:10px;font-size:.68rem;color:var(--muted);">Ranked by share × volatility. Higher = more sensitive to market changes.</div></div>`;
  }

  // ── Sensitivity Impact Table ──
  if (sens.sensitivities && sens.sensitivities.length > 0) {
    html += `<div class="dss-card"><div class="dss-card-title">💥 10% Change Impact</div>
      <div style="overflow-x:auto;"><table class="dss-table"><thead><tr><th>Category</th><th>Current</th><th>10% Impact</th><th>CV %</th></tr></thead><tbody>`;
    sens.sensitivities.forEach(s => {
      html += `<tr><td style="font-weight:600;">${s.category}</td><td>$${s.current_value.toLocaleString()}</td>
        <td style="color:var(--amber);font-weight:700;">±$${s.impact_of_10pct_change.toLocaleString()}</td>
        <td style="color:${s.volatility_cv > 30 ? 'var(--red)' : s.volatility_cv > 15 ? 'var(--amber)' : 'var(--green)'};">${s.volatility_cv}%</td></tr>`;
    });
    html += `</tbody></table></div></div>`;
  }

  grid.innerHTML = html || '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text2);">No forecast data available.</div>';

  // Render forecast chart
  setTimeout(() => {
    if (fc.actual && fc.actual.length > 0) renderForecastChart(fc);
  }, 100);
}

function renderForecastChart(fc) {
  const ctx = document.getElementById('forecastChart');
  if (!ctx) return;
  if (chartInstances['forecast']) chartInstances['forecast'].destroy();
  const labels = [...fc.labels];
  const actualData = [...fc.actual];
  const fittedData = [...fc.fitted];
  const maData = [...fc.moving_avg];
  const upperData = new Array(fc.actual.length).fill(null);
  const lowerData = new Array(fc.actual.length).fill(null);
  fc.forecast.forEach(f => {
    labels.push(f.period);
    actualData.push(null);
    fittedData.push(f.value);
    maData.push(null);
    upperData.push(f.upper);
    lowerData.push(f.lower);
  });
  chartInstances['forecast'] = new Chart(ctx.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Actual', data: actualData, borderColor: '#818cf8', backgroundColor: 'rgba(129,140,248,.1)', tension: 0.4, fill: false, pointRadius: 5, pointBackgroundColor: '#818cf8', borderWidth: 2.5 },
        { label: 'Trend Line', data: fittedData, borderColor: '#f472b6', borderDash: [6, 4], tension: 0.2, fill: false, pointRadius: 3, borderWidth: 2 },
        { label: 'Moving Avg', data: maData, borderColor: '#22d3ee', borderDash: [3, 3], tension: 0.4, fill: false, pointRadius: 0, borderWidth: 1.5 },
        { label: 'Upper 95% CI', data: upperData, borderColor: 'rgba(52,211,153,.4)', borderDash: [4, 4], fill: false, pointRadius: 0, borderWidth: 1 },
        { label: 'Lower 95% CI', data: lowerData, borderColor: 'rgba(248,113,113,.4)', borderDash: [4, 4], fill: '-1', backgroundColor: 'rgba(129,140,248,.05)', pointRadius: 0, borderWidth: 1 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 1200 },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } },
      scales: { x: { grid: { display: false } }, y: { grid: { color: 'rgba(255,255,255,0.03)' }, beginAtZero: false } }
    }
  });
}

// ─── ANOMALIES ───
function renderAnomalies(anomalies) {
  const el = document.getElementById('anomalyPanel');
  if (!anomalies || anomalies.length === 0) { el.innerHTML = '<div class="step-placeholder">✅ No anomalies detected</div>'; return; }
  el.innerHTML = anomalies.map(a => `<div class="anomaly-item anom-${a.severity}">⚠️ ${a.message}</div>`).join('');
}

// ─── PIPELINE ───
async function runFullPipeline() {
  const dot = document.querySelector('.dot');
  const label = document.getElementById('pipelineLabel');
  const stepsEl = document.getElementById('pipelineSteps');
  dot.className = 'dot dot-running'; label.textContent = 'Running...';
  const defSteps = [
    {step:1,name:'Analyzing CSV',icon:'📊',status:'pending'},{step:2,name:'Generating Charts',icon:'📈',status:'pending'},
    {step:3,name:'Detecting Anomalies',icon:'🔍',status:'pending'},{step:4,name:'Fetching News',icon:'📰',status:'pending'},
    {step:5,name:'AI Predictions',icon:'🤖',status:'pending'},{step:6,name:'Email Report',icon:'📧',status:'pending'},
    {step:7,name:'Supplier Alerts',icon:'📦',status:'pending'},{step:8,name:'DSS Analytics',icon:'🎯',status:'pending'},
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
      if (data.charts) renderAllCharts(data.charts);
      if (data.data) updateKPIs(data.data);
      if (data.anomalies) renderAnomalies(data.anomalies);
      if (data.predictions) renderPredictions(data.predictions);
      if (data.news) renderNews(data.news);
      if (data.dss) { dssData = data.dss; renderDSSTab(data.dss); renderForecastTab(data.dss); }
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
  } catch (e) { dot.className = 'dot dot-fail'; label.textContent = 'Error'; toast('Network error: ' + e.message, 'error'); }
}

function renderPipelineStep(s) {
  let dc = 'psd-pending', di = '';
  if (s.status === 'running') { dc = 'psd-running'; di = '⏳'; }
  else if (s.status === 'completed') { dc = 'psd-done'; di = '✓'; }
  else if (s.status === 'warning') { dc = 'psd-warn'; di = '!'; }
  return `<div class="p-step"><div class="p-step-icon">${s.icon}</div>
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
  let html = `<div class="pred-card" style="margin-bottom:10px;border-left:3px solid var(--indigo);padding-left:12px;">
    <div style="font-size:.72rem;color:var(--text2);">Overall Outlook</div>
    <div style="font-size:1rem;font-weight:800;color:${preds.overall_outlook==='bullish'?'var(--green)':preds.overall_outlook==='bearish'?'var(--red)':'var(--amber)'};">
      ${(preds.overall_outlook||'').toUpperCase()} · ${preds.confidence||0}%</div>
    <div style="font-size:.72rem;color:var(--text2);margin-top:3px;">${preds.summary||''}</div></div>`;
  preds.product_predictions.forEach(p => {
    const tc = p.trend === 'increasing' ? 'var(--green)' : p.trend === 'decreasing' ? 'var(--red)' : 'var(--amber)';
    const ti = p.trend === 'increasing' ? '📈' : p.trend === 'decreasing' ? '📉' : '➡️';
    const ai = p.action === 'increase_stock' ? '🟢' : p.action === 'decrease_stock' ? '🔴' : '🟡';
    html += `<div class="pred-card"><div class="pred-prod">${p.product}</div>
      <div class="pred-trend" style="color:${tc};">${ti} ${p.trend} · ${(p.predicted_change_percent||0)>0?'+':''}${p.predicted_change_percent||0}% · Conf: ${p.confidence||0}%</div>
      <div class="pred-action">${ai} ${(p.action||'').replace(/_/g,' ')} — ${p.reasoning||''}</div></div>`;
  });
  if (preds.key_insights && preds.key_insights.length) {
    html += '<div style="margin-top:8px;font-size:.72rem;font-weight:700;color:var(--text2);">Key Insights</div>';
    preds.key_insights.forEach(x => { html += `<div style="font-size:.7rem;color:var(--muted);margin:2px 0;">💡 ${x}</div>`; });
  }
  el.innerHTML = html;
}

// ─── NEWS ───
function renderNews(news) {
  const el = document.getElementById('newsPanel');
  if (!news || !news.articles || news.articles.length === 0) { el.innerHTML = '<div class="step-placeholder">No news found</div>'; return; }
  el.innerHTML = news.articles.slice(0, 8).map(a =>
    `<div class="news-item"><div style="display:flex;gap:5px;align-items:center;margin-bottom:3px;">
      <span class="news-badge">${a.product}</span><span style="font-size:.6rem;color:var(--muted);">${a.source}</span></div>
      <div class="news-title">${a.url ? `<a href="${a.url}" target="_blank" style="color:var(--text);text-decoration:none;">${a.title}</a>` : a.title}</div>
      <div class="news-meta"><span>${a.publishedAt ? new Date(a.publishedAt).toLocaleDateString() : ''}</span></div></div>`
  ).join('');
}

// ─── WHAT-IF ───
async function runWhatIf() {
  const input = document.getElementById('whatifInput');
  const result = document.getElementById('whatifResult');
  const scenario = input.value.trim();
  if (!scenario) { toast('Enter a scenario first', 'error'); return; }
  result.innerHTML = '<div style="color:var(--amber);font-size:.78rem;">⏳ Analyzing scenario...</div>';
  try {
    const resp = await fetch('/api/what-if', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({scenario}) });
    const data = await resp.json();
    if (data.error) { result.innerHTML = `<div style="color:var(--red);">❌ ${data.error}</div>`; return; }
    let html = `<div style="margin-top:6px;"><div style="font-weight:700;font-size:.82rem;">${data.scenario || scenario}</div>
      <div style="font-size:.76rem;color:var(--text2);margin:5px 0;">${data.impact_summary || ''}</div>
      <div style="font-size:.72rem;color:var(--muted);">Risk: <span style="color:${data.overall_risk==='high'?'var(--red)':data.overall_risk==='medium'?'var(--amber)':'var(--green)'};">${(data.overall_risk||'').toUpperCase()}</span></div>`;
    if (data.product_impacts) {
      data.product_impacts.forEach(p => {
        html += `<div style="font-size:.74rem;margin-top:5px;padding:5px 9px;background:rgba(255,255,255,.015);border-radius:8px;">
          <strong>${p.product}</strong>: Sales ${(p.sales_change_percent||0)>0?'+':''}${p.sales_change_percent||0}%, Profit ${(p.profit_change_percent||0)>0?'+':''}${p.profit_change_percent||0}%
          <div style="font-size:.68rem;color:var(--muted);">${p.explanation||''}</div></div>`;
      });
    }
    html += `<div style="font-size:.74rem;color:var(--green);margin-top:6px;">💡 ${data.recommendation || ''}</div></div>`;
    result.innerHTML = html;
  } catch (e) { result.innerHTML = `<div style="color:var(--red);">❌ ${e.message}</div>`; }
}

// ═══════════════════════════════════════════════
// STRATEGIC ADVISOR TAB
// ═══════════════════════════════════════════════
async function loadAdvisor() {
  const grid = document.getElementById('advisorGrid');
  grid.innerHTML = '<div class="dss-card dss-card-full advisor-loading"><div class="spinner"></div><div style="font-weight:700;">AI is analyzing data, identifying gaps, and generating strategies...</div><div style="font-size:.75rem;color:var(--text2);margin-top:6px;">This may take 15-30 seconds.</div></div>';
  try {
    const resp = await fetch('/api/strategic-advisor', { method: 'POST' });
    const data = await resp.json();
    if (data.error) { grid.innerHTML = `<div class="dss-card dss-card-full" style="color:var(--red);text-align:center;">❌ ${data.error}</div>`; return; }
    renderAdvisor(data);
  } catch (e) {
    grid.innerHTML = `<div class="dss-card dss-card-full" style="color:var(--red);text-align:center;">❌ Network Error: ${e.message}</div>`;
  }
}

function renderAdvisor(data) {
  const grid = document.getElementById('advisorGrid');
  let html = '';

  // 1. Health Status
  const health = data.current_status_summary || {};
  let hColor = 'var(--amber)';
  if(health.overall_health === 'excellent' || health.overall_health === 'good') hColor = 'var(--green)';
  if(health.overall_health === 'concerning' || health.overall_health === 'critical') hColor = 'var(--red)';
  html += `<div class="dss-card dss-card-full">
    <div class="advisor-health">
      <div class="health-ring" style="--health-color:${hColor};--health-pct:${health.health_score||50}%;"><span>${health.health_score||50}</span></div>
      <div class="health-info">
        <div class="health-label">System Health</div>
        <div class="health-status" style="color:${hColor};">${(health.overall_health||'Unknown').toUpperCase()}</div>
        <div class="health-detail"><strong>Strength:</strong> ${health.top_strength||'—'} <br> <strong>Weakness:</strong> ${health.top_weakness||'—'}</div>
      </div>
    </div>
  </div>`;

  // 2. Immediate Actions
  if(data.immediate_actions && data.immediate_actions.length) {
    html += `<div class="dss-card"><div class="dss-card-title">🔥 Priority Actions Needed</div>`;
    data.immediate_actions.forEach(a => {
      html += `<div class="action-item pri-${a.priority}">
        <div class="action-priority">${a.priority}</div>
        <div class="action-text">${a.action}</div>
        <div class="action-meta"><span>🎯 ${a.category}</span><span>⏱️ ${a.timeline}</span></div>
        <div style="font-size:.7rem;color:var(--indigo);margin-top:4px;">↳ Impact: ${a.expected_impact}</div>
      </div>`;
    });
    html += `</div>`;
  }

  // 3. Gap Analysis
  if(data.gap_analysis && data.gap_analysis.length) {
    html += `<div class="dss-card"><div class="dss-card-title">📉 Current Gaps & Lags</div>`;
    data.gap_analysis.forEach(g => {
      html += `<div class="gap-item gap-${g.severity}">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div style="font-weight:700;font-size:.8rem;">${g.area}</div>
          <div class="gap-severity">${g.severity}</div>
        </div>
        <div class="gap-states">
          <div><div style="color:var(--muted);font-size:.6rem;text-transform:uppercase;">Current</div><div style="color:var(--red);font-weight:700;">${g.current_state}</div></div>
          <div class="gap-arrow">→</div>
          <div style="text-align:right;"><div style="color:var(--muted);font-size:.6rem;text-transform:uppercase;">Desired</div><div style="color:var(--green);font-weight:700;">${g.desired_state}</div></div>
        </div>
        <div style="font-size:.7rem;margin-top:6px;color:var(--text2);"><strong>Fix:</strong> ${g.action_plan}</div>
      </div>`;
    });
    html += `</div>`;
  }

  // 4. Sales Growth Strategies
  if(data.sales_growth_strategies && data.sales_growth_strategies.length) {
    html += `<div class="dss-card dss-card-full"><div class="dss-card-title">🚀 Sales Growth Strategies</div><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;">`;
    data.sales_growth_strategies.forEach(s => {
      html += `<div class="strategy-card">
        <div class="strategy-name">${s.strategy}</div>
        <div class="strategy-desc">${s.description}</div>
        <div class="strategy-tags">
          <span class="strategy-tag" style="background:rgba(52,211,153,.1);color:var(--green);">+${s.estimated_impact_pct}% Impact</span>
          <span class="strategy-tag" style="background:rgba(255,255,255,.05);">${s.effort_level} effort</span>
          <span class="strategy-tag" style="background:rgba(255,255,255,.05);">${s.timeline}</span>
        </div>
      </div>`;
    });
    html += `</div></div>`;
  }

  // 5. Stock Replenishment (Reorder)
  if(data.stock_recommendations && data.stock_recommendations.length) {
    html += `<div class="dss-card"><div class="dss-card-title">📦 Inventory & Reorder Advisor</div>`;
    data.stock_recommendations.forEach(s => {
      let stColor = 'var(--text2)', icon = '📦';
      if(s.current_status==='understocked'||s.current_status==='at_risk') {stColor='var(--amber)'; icon='⚠️';}
      if(s.current_status==='overstocked') {stColor='var(--cyan)'; icon='📉';}
      
      let badgeColor = 'rgba(255,255,255,.1)'; let badgeText = 'var(--text)';
      if(s.action==='urgent_reorder'){badgeColor='var(--red)'; badgeText='#fff';}
      else if(s.action==='increase'){badgeColor='rgba(52,211,153,.2)'; badgeText='var(--green)';}
      
      html += `<div class="stock-item">
        <div class="stock-icon" style="background:rgba(255,255,255,.05);">${icon}</div>
        <div class="stock-info">
          <div class="stock-cat">${s.category} <span style="font-size:.65rem;font-weight:400;color:${stColor};">(${s.current_status})</span></div>
          <div class="stock-detail">${s.reasoning}. <strong>Reorder:</strong> ${s.reorder_timeline}</div>
        </div>
        <div class="stock-action" style="background:${badgeColor};color:${badgeText};">${s.action.toUpperCase()} ${Math.abs(s.quantity_change_pct)}%</div>
      </div>`;
    });
    html += `</div>`;
  }

  // 6. Future Predictions
  if(data.future_predictions && data.future_predictions.length) {
    html += `<div class="dss-card"><div class="dss-card-title">🔮 Future Outlook</div>`;
    data.future_predictions.forEach(p => {
      html += `<div class="prediction-card">
        <div class="prediction-timeframe">${p.timeframe.replace('_',' ').toUpperCase()}</div>
        <div class="prediction-text">${p.prediction}</div>
        <div class="prediction-meta"><strong>Conf:</strong> ${p.confidence}% | <strong>Risk:</strong> ${p.risk_factors}</div>
        <div style="font-size:.7rem;font-weight:600;color:var(--green);margin-top:4px;">💡 Opp: ${p.opportunity}</div>
      </div>`;
    });
    html += `</div>`;
  }

  grid.innerHTML = html;
}

// ─── QUICK ACTIONS ───
async function emailReport() {
  toast('📧 Generating & sending report...', 'info');
  try {
    const resp = await fetch('/api/manager-report', { method: 'POST' });
    const data = await resp.json();
    toast(data.success ? '✅ Report emailed!' : '❌ ' + data.message, data.success ? 'success' : 'error');
  } catch (e) { toast('❌ ' + e.message, 'error'); }
}
async function alertSuppliers() {
  if (!pipelineData || !pipelineData.predictions) { toast('Run the pipeline first', 'error'); return; }
  toast('📦 Sending supplier alerts...', 'info');
  try {
    const resp = await fetch('/api/supplier-alert', { method: 'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({predictions: pipelineData.predictions}) });
    const data = await resp.json();
    toast(`✅ Sent ${data.results ? data.results.length : 0} supplier alerts`, 'success');
  } catch (e) { toast('❌ ' + e.message, 'error'); }
}
function toggleCalcs() {
  const el = document.getElementById('calcsSection');
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
  if (el.style.display === 'block') el.scrollIntoView({behavior: 'smooth'});
}

// ─── CALCULATORS ───
function calcEOQ(){const D=parseFloat(document.getElementById('eoqD').value),S=parseFloat(document.getElementById('eoqS').value),H=parseFloat(document.getElementById('eoqH').value);if(D>0&&S>0&&H>0){const q=Math.sqrt(2*D*S/H),o=D/q,c=(q/2)*H+(D/q)*S;document.getElementById('eoqRes').innerHTML=`📦 EOQ: <strong>${q.toFixed(0)}</strong> units | Orders/yr: <strong>${o.toFixed(1)}</strong> | Cost: <strong>$${c.toFixed(2)}</strong>`;}else toast('Enter positive values','error');}
function calcROP(){const d=parseFloat(document.getElementById('ropD').value),s=parseFloat(document.getElementById('ropS').value),l=parseFloat(document.getElementById('ropL').value),sl=parseFloat(document.getElementById('ropSL').value)/100;let z;if(sl<=.9)z=1.28;else if(sl<=.95)z=1.28+(1.645-1.28)*((sl-.9)/.05);else if(sl<=.99)z=1.645+(2.33-1.645)*((sl-.95)/.04);else z=2.33;const ss=z*s*Math.sqrt(l),rop=d*l+ss;document.getElementById('ropRes').innerHTML=`🛡️ Safety Stock: <strong>${ss.toFixed(0)}</strong> | Reorder: <strong>${rop.toFixed(0)}</strong>`;}
function calcBE(){const f=parseFloat(document.getElementById('beF').value),v=parseFloat(document.getElementById('beV').value),p=parseFloat(document.getElementById('beP').value);if(p>v){const u=f/(p-v),r=u*p;document.getElementById('beRes').innerHTML=`📊 BEP: <strong>${u.toFixed(0)}</strong> units | Revenue: <strong>$${r.toFixed(0)}</strong>`;}else toast('Price must exceed variable cost','error');}
function calcMOB(){const f=parseFloat(document.getElementById('mobF').value),v=parseFloat(document.getElementById('mobV').value),b=parseFloat(document.getElementById('mobB').value),q=parseFloat(document.getElementById('mobQ').value);const mc=f+v*q,bc=b*q,d=mc<bc?'MAKE ✅':bc<mc?'BUY ✅':'INDIFFERENT';document.getElementById('mobRes').innerHTML=`🏭 Make: <strong>$${mc.toFixed(0)}</strong> | Buy: <strong>$${bc.toFixed(0)}</strong> | Decision: <strong>${d}</strong>`;}

// ─── TOAST ───
function toast(msg, type='info') {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity='0'; t.style.transition='opacity .35s'; setTimeout(()=>t.remove(),350); }, 3500);
}

/**
 * app.js — FinLife Web: Pyodide bootstrap + UI controller
 *
 * Flow:
 *   Page load → loadDefaultConfig() → user edits → click Run →
 *   pyodide.runPython(_run(...)) → renderResults()
 */

// ── State ──
let pyodide = null;

// ── DOM refs ──
const $ = (id) => document.getElementById(id);
const editor = $('configEditor');
const runBtn = $('runBtn');
const loadDefaultBtn = $('loadDefaultBtn');
const uploadFile = $('uploadFile');
const samplesSelect = $('samplesSelect');
const overlay = $('loadingOverlay');
const loadingText = $('loadingText');
const placeholder = $('placeholder');
const resultsContent = $('resultsContent');

// ── Default config ──
const DEFAULT_CONFIG = `# life_config.txt
[simulation]
start_year = 2027
end_year = 2060
n_samples = 200
seed = 123
inflation_adjusted = false

[initial_assets]
cash = 300000
investments = 150000
real_estate = 0
other_assets = 0
liabilities = 0

[salary]
value = 400000 ~ N(400000, 40000)
annual_change_rate = 3%

[living_expense]
value = 100000 ~ N(100000, 10000)
annual_change_rate = 3%

[investment_return]
value = 8% ~ N(8%, 18%)

[inflation_rate]
value = 3% ~ N(3%, 2%)

[events]
marriage | 2029 | partner_income=100000 | extra_expense=30000
birth | 2030 | child_cost=30000 | edu_start_age=6 | edu_cost=10000
buy_car | 2028 | car_price=100000 | down_pct=50% | loan_years=3 | loan_rate=2.6%
buy_house | 2035 | house_price=3000000 | down_pct=30% | mortgage_years=30 | mortgage_rate=3.5% | appreciation=3%
job_change | 2033 | new_salary=300000 ~ N(300000, 30000)
change_invest_return | 2045 | new_return=6% ~ N(4%, 2%)
retirement | 2060
redistribute_invest | auto
`;

// ── Bootstrap Pyodide ──

async function initPyodide() {
  overlay.classList.remove('hidden');
  loadingText.textContent = '正在加载 Pyodide (首次约 10-15 MB)...';

  pyodide = await loadPyodide({
    indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.25.1/full/',
  });
  loadingText.textContent = '正在安装依赖 (numpy, matplotlib)...';
  await pyodide.loadPackage(['numpy', 'matplotlib']);

  // Fetch Python source files and write into Pyodide's virtual FS
  loadingText.textContent = '正在加载模拟模块...';
  // Dev: page at /web/ → .py files at / (use ../)
  // Deployed: all files flat at same level (use ./)
  const inWebDir = window.location.pathname.includes('/web/');
  const root = inWebDir ? '../' : './';
  const pyFiles = [
    { name: 'lifeclass.py',     path: root + 'lifeclass.py' },
    { name: 'config_parser.py', path: root + 'config_parser.py' },
    { name: 'events_factory.py',path: root + 'events_factory.py' },
    { name: 'bridge.py',        path: 'bridge.py' },
  ];

  for (const { name, path } of pyFiles) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`Failed to fetch ${path} (${resp.status})`);
    const code = await resp.text();
    // Write to virtual filesystem so imports work
    pyodide.FS.writeFile(name, code);
  }

  // Parse bridge.py into a Python module we can call
  pyodide.runPython(`
import sys
sys.path.insert(0, '.')
from bridge import _run
  `);

  overlay.classList.add('hidden');
}

// ── Run Simulation ──

async function runSimulation() {
  runBtn.disabled = true;
  runBtn.textContent = '⏳ 运行中...';
  overlay.classList.remove('hidden');
  loadingText.textContent = '正在运行蒙特卡洛模拟...';

  // Yield to browser to show loading state
  await new Promise(r => setTimeout(r, 50));

  try {
    const configText = editor.value;
    const nSamples = parseInt(samplesSelect.value, 10);

    // Call Python runner — bridge._run returns a plain dict
    const result = pyodide.globals.get('_run')(configText, nSamples);
    const data = result.toJs({ dict_converter: Object.fromEntries });

    placeholder.classList.add('hidden');
    resultsContent.classList.remove('hidden');
    renderResults(data);
  } catch (err) {
    alert('模拟出错:\n' + err.message);
    console.error(err);
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = '▶ 运行模拟';
    overlay.classList.add('hidden');
  }
}

// ── Render Results ──

function renderResults(data) {
  renderDetStats(data.det_stats);
  renderMCStats(data.mc_stats);
  renderEventLog(data.event_log);
  renderFITable(data.fi_table);
  renderPlots(data.plots);
}

function renderDetStats(stats) {
  const container = $('detStats');
  container.innerHTML = '';
  const items = [
    ['净值', stats.net_worth, 'W'],
    ['总资产', stats.total_assets, 'W'],
    ['现金', stats.cash, 'W'],
    ['投资', stats.investments, 'W'],
    ['房产', stats.real_estate, 'W'],
    ['负债', stats.liabilities, 'W'],
  ];
  for (const [label, value, unit] of items) {
    const card = document.createElement('div');
    card.className = 'stat-card';
    card.innerHTML = `<div class="stat-label">${label}</div>
                      <div class="stat-value">${value} ${unit}</div>`;
    container.appendChild(card);
  }
}

function renderMCStats(stats) {
  const container = $('mcStats');
  container.innerHTML = '';
  const items = [
    ['均值净值', stats.mean[stats.mean.length - 1]],
    ['中位数净值', stats.p50[stats.p50.length - 1]],
    ['5% 分位', stats.p5[stats.p5.length - 1]],
    ['95% 分位', stats.p95[stats.p95.length - 1]],
  ];
  for (const [label, value] of items) {
    const card = document.createElement('div');
    card.className = 'stat-card';
    card.innerHTML = `<div class="stat-label">${label}</div>
                      <div class="stat-value">${value} W</div>`;
    container.appendChild(card);
  }
}

function renderEventLog(log) {
  const container = $('eventLog');
  container.innerHTML = log.map(e =>
    `<div><strong>${e.year}年:</strong> [${e.event}] ${e.detail}</div>`
  ).join('');
}

function renderFITable(fiTable) {
  const container = $('fiTable');
  if (fiTable.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:0.82rem;">未达到财务自由阈值</p>';
    return;
  }
  let html = '<table><thead><tr><th>年份</th><th>财务自由概率</th></tr></thead><tbody>';
  for (const row of fiTable) {
    html += `<tr><td>${row.year}</td><td>${row.prob}%</td></tr>`;
  }
  html += '</tbody></table>';
  container.innerHTML = html;
}

function renderPlots(plots) {
  const container = $('plotGrid');
  const labels = {
    net_worth: '净值预测',
    assets_breakdown: '资产结构',
    income_expense: '收支明细',
    financial_freedom: '财富自由度',
  };
  container.innerHTML = '';
  for (const [key, url] of Object.entries(plots)) {
    const div = document.createElement('div');
    div.innerHTML = `<p style="font-size:0.82rem;font-weight:500;margin-bottom:4px;">${labels[key] || key}</p>
                     <img src="${url}" alt="${labels[key] || key}">`;
    container.appendChild(div);
  }
}

// ── Editor Helpers ──

function loadDefaultConfig() {
  const idx = DEFAULT_CONFIG.indexOf('n_samples =');
  const lineEnd = DEFAULT_CONFIG.indexOf('\n', idx);
  editor.value = DEFAULT_CONFIG.slice(0, idx) +
    'n_samples = ' + samplesSelect.value +
    DEFAULT_CONFIG.slice(lineEnd);
}

function handleFileUpload(file) {
  const reader = new FileReader();
  reader.onload = (e) => { editor.value = e.target.result; };
  reader.readAsText(file);
}

// ── Init ──

(async function() {
  loadDefaultConfig();
  try {
    await initPyodide();
  } catch (err) {
    loadingText.textContent = '❌ 加载失败: ' + err.message;
    console.error(err);
  }

  // Event listeners
  runBtn.addEventListener('click', runSimulation);
  loadDefaultBtn.addEventListener('click', loadDefaultConfig);
  uploadFile.addEventListener('change', (e) => {
    if (e.target.files[0]) handleFileUpload(e.target.files[0]);
  });
})();
/**
 * app.js — FinLife Web: Pyodide bootstrap + form UI controller
 *
 * Flow:
 *   Load → initPyodide() → user fills form + events → click Run →
 *   buildConfigText() → pyodide._run() → renderResults()
 */

// ════════════════════════════════════════════
//  State
// ════════════════════════════════════════════

let pyodide = null;
let events = [];
let isExpertMode = false;

// ════════════════════════════════════════════
//  DOM refs
// ════════════════════════════════════════════

const $ = (id) => document.getElementById(id);

// ── Distribution show/hide ──
const DIST_CHANGE_IDS = [
  'f_salary_dist', 'f_expense_dist', 'f_invret_dist', 'f_infl_dist',
];

// ════════════════════════════════════════════
//  Bootstrap
// ════════════════════════════════════════════

async function initPyodide() {
  const overlay = $('loadingOverlay');
  const loadingText = $('loadingText');
  overlay.classList.remove('hidden');

  loadingText.textContent = '正在加载 Pyodide (首次约 10-15 MB)...';
  pyodide = await loadPyodide({
    indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.25.1/full/',
  });

  loadingText.textContent = '正在安装依赖 (numpy, matplotlib)...';
  await pyodide.loadPackage(['numpy', 'matplotlib']);

  loadingText.textContent = '正在加载模拟模块...';
  const inWebDir = window.location.pathname.includes('/web/');
  const root = inWebDir ? '../' : './';
  const pyFiles = [
    { name: 'lifeclass.py',      path: root + 'lifeclass.py' },
    { name: 'config_parser.py',  path: root + 'config_parser.py' },
    { name: 'events_factory.py', path: root + 'events_factory.py' },
    { name: 'bridge.py',         path: 'bridge.py' },
  ];

  for (const { name, path } of pyFiles) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`Failed to fetch ${path} (${resp.status})`);
    pyodide.FS.writeFile(name, await resp.text());
  }

  pyodide.runPython(`
import sys
sys.path.insert(0, '.')
from bridge import _run
  `);

  overlay.classList.add('hidden');
}

// ════════════════════════════════════════════
//  Distribution field show/hide
// ════════════════════════════════════════════

function setupDistToggle(selectId) {
  const sel = $(selectId);
  if (!sel) return;
  sel.addEventListener('change', () => updateDistFields(selectId));
}

function updateDistFields(selectId) {
  const sel = $(selectId);
  const container = sel.closest('.section-body') || sel.closest('.modal-body');
  const chosen = sel.value;
  container.querySelectorAll(`[data-dist]`).forEach(el => {
    el.style.display = el.dataset.dist === chosen ? 'flex' : 'none';
  });
}

// Modal distribution toggles
function setupModalDistToggle(selectId) {
  const sel = $(selectId);
  if (!sel) return;
  sel.addEventListener('change', () => updateModalDistFields(selectId));
}

function updateModalDistFields(selectId) {
  const sel = $(selectId);
  const chosen = sel.value;
  const parent = sel.closest('.em-fields-group');
  parent.querySelectorAll('.em-dist-params [data-dist]').forEach(el => {
    el.style.display = el.dataset.dist === chosen ? 'flex' : 'none';
  });
  // Also the dist-params container visibility
  const container = parent.querySelector('.em-dist-params');
  if (container) container.style.display = chosen === 'fixed' ? 'none' : 'block';
}

// ════════════════════════════════════════════
//  Event Modal
// ════════════════════════════════════════════

function openEventModal(idx) {
  const modal = $('eventModal');
  modal.classList.remove('hidden');
  $('modalTitle').textContent = idx >= 0 ? '编辑事件' : '添加事件';
  $('em_edit_idx').value = idx;

  const evt = idx >= 0 ? events[idx] : null;

  // Reset form
  $('em_type').value = evt ? evt.type : 'marriage';
  $('em_trigger_year').value = evt && evt.year !== 'auto' ? evt.year : 2030;
  $('em_trigger_auto').checked = evt ? evt.year === 'auto' : false;
  $('em_trigger_year').disabled = $('em_trigger_auto').checked;

  // Reset all event-specific field groups
  document.querySelectorAll('.em-fields-group').forEach(g => g.classList.remove('hidden'));
  document.querySelectorAll('.em-fields-group input').forEach(inp => {
    if (inp.type !== 'radio' && inp.type !== 'checkbox') inp.disabled = true;
  });

  // Fill specific fields
  if (evt) {
    fillModalFields(evt);
  } else {
    enableModalFields('marriage');
  }

  // Reset job_change radios
  document.querySelectorAll('input[name="jc_mode"]').forEach(r => {
    r.checked = r.value === 'salary';
  });
  document.querySelectorAll('input[name="cle_mode"]').forEach(r => {
    r.checked = r.value === 'expense';
  });
  updateJobChangeMode();
  updateCLEMode();

  enableModalFields($('em_type').value);
  updateModalDistFields('em_jc_dist');
  updateModalDistFields('em_cle_dist');
  updateModalDistFields('em_cir_dist');
}

function fillModalFields(evt) {
  const p = evt.params || {};
  switch (evt.type) {
    case 'marriage':
      $('em_marriage_income').value = p.partner_income || 100000;
      $('em_marriage_expense').value = p.extra_expense || 30000;
      break;
    case 'birth':
      $('em_birth_cost').value = p.child_cost || 30000;
      $('em_birth_edu_start').value = p.edu_start_age || 6;
      $('em_birth_edu_cost').value = p.edu_cost || 10000;
      break;
    case 'buy_house':
      $('em_bh_price').value = p.house_price || 3000000;
      $('em_bh_down').value = p.down_pct != null ? p.down_pct * 100 : 30;
      $('em_bh_years').value = p.mortgage_years || 30;
      $('em_bh_rate').value = p.mortgage_rate != null ? p.mortgage_rate * 100 : 3.5;
      $('em_bh_appr').value = p.appreciation != null ? p.appreciation * 100 : 3;
      break;
    case 'buy_car':
      $('em_bc_price').value = p.car_price || 100000;
      $('em_bc_down').value = p.down_pct != null ? p.down_pct * 100 : 50;
      $('em_bc_years').value = p.loan_years || 3;
      $('em_bc_rate').value = p.loan_rate != null ? p.loan_rate * 100 : 2.6;
      break;
    case 'job_change':
      if (p.raise_pct != null) {
        document.querySelector('input[name="jc_mode"][value="pct"]').checked = true;
        $('em_jc_pct').value = p.raise_pct * 100;
      } else if (p.raise_value != null) {
        document.querySelector('input[name="jc_mode"][value="value"]').checked = true;
        $('em_jc_value').value = p.raise_value;
      } else {
        document.querySelector('input[name="jc_mode"][value="salary"]').checked = true;
        const sv = p.new_salary || {};
        $('em_jc_salary').value = sv.base_value || 300000;
        $('em_jc_dist').value = sv.dist_type || 'fixed';
        if (sv.dist_params) {
          fillModalDistParams('em_jc', sv.dist_type, sv.dist_params);
        }
      }
      updateJobChangeMode();
      break;
    case 'change_living_expense':
      if (p.raise_pct != null) {
        document.querySelector('input[name="cle_mode"][value="pct"]').checked = true;
        $('em_cle_pct').value = p.raise_pct * 100;
      } else if (p.raise_value != null) {
        document.querySelector('input[name="cle_mode"][value="value"]').checked = true;
        $('em_cle_value').value = p.raise_value;
      } else {
        document.querySelector('input[name="cle_mode"][value="expense"]').checked = true;
        const ne = p.new_expense || {};
        $('em_cle_expense').value = ne.base_value || 120000;
        $('em_cle_dist').value = ne.dist_type || 'fixed';
        if (ne.dist_params) {
          fillModalDistParams('em_cle', ne.dist_type, ne.dist_params);
        }
      }
      updateCLEMode();
      break;
    case 'change_invest_return':
      const nr = p.new_return || {};
      $('em_cir_val').value = nr.base_value != null ? nr.base_value * 100 : 6;
      $('em_cir_dist').value = nr.dist_type || 'fixed';
      if (nr.dist_params) {
        fillModalDistParams('em_cir', nr.dist_type, nr.dist_params);
      }
      break;
    // retirement and redistribute_invest: no params
  }
}

function fillModalDistParams(prefix, distType, params) {
  const arr = Array.isArray(params) ? params : Object.values(params);
  if (distType === 'normal' && arr.length >= 2) {
    $(`${prefix}_n_mean`).value = arr[0];
    $(`${prefix}_n_std`).value = arr[1];
  } else if (distType === 'uniform' && arr.length >= 2) {
    $(`${prefix}_u_lo`).value = arr[0];
    $(`${prefix}_u_hi`).value = arr[1];
  } else if (distType === 'triangular' && arr.length >= 3) {
    $(`${prefix}_t_lo`).value = arr[0];
    $(`${prefix}_t_mode`).value = arr[1];
    $(`${prefix}_t_hi`).value = arr[2];
  }
}

function enableModalFields(type) {
  document.querySelectorAll('.em-fields-group').forEach(g => g.classList.add('hidden'));
  const group = document.querySelector(`.em-fields-group[data-type="${type}"]`);
  if (group) {
    group.classList.remove('hidden');
    group.querySelectorAll('input, select').forEach(inp => {
      if (inp.type !== 'radio' || inp.name.startsWith('em_')) inp.disabled = false;
    });
  }
  // Show/hide trigger year row
  $('em_trigger_row').style.display = (type === 'retirement' || type === 'redistribute_invest') ? 'none' : 'flex';
}

function showEventTypeFields(type) {
  // Deprecated — now handled by enableModalFields
}

function saveEventFromModal() {
  const idx = parseInt($('em_edit_idx').value, 10);
  const type = $('em_type').value;
  const year = $('em_trigger_auto').checked ? 'auto' : parseInt($('em_trigger_year').value, 10);

  const params = {};
  switch (type) {
    case 'marriage':
      params.partner_income = parseFloat($('em_marriage_income').value) || 0;
      params.extra_expense = parseFloat($('em_marriage_expense').value) || 0;
      break;
    case 'birth':
      params.child_cost = parseFloat($('em_birth_cost').value) || 0;
      params.edu_start_age = parseInt($('em_birth_edu_start').value, 10) || 6;
      params.edu_cost = parseFloat($('em_birth_edu_cost').value) || 0;
      break;
    case 'buy_house':
      params.house_price = parseFloat($('em_bh_price').value) || 0;
      params.down_pct = (parseFloat($('em_bh_down').value) || 0) / 100;
      params.mortgage_years = parseInt($('em_bh_years').value, 10) || 30;
      params.mortgage_rate = (parseFloat($('em_bh_rate').value) || 0) / 100;
      params.appreciation = (parseFloat($('em_bh_appr').value) || 0) / 100;
      break;
    case 'buy_car':
      params.car_price = parseFloat($('em_bc_price').value) || 0;
      params.down_pct = (parseFloat($('em_bc_down').value) || 0) / 100;
      params.loan_years = parseInt($('em_bc_years').value, 10) || 3;
      params.loan_rate = (parseFloat($('em_bc_rate').value) || 0) / 100;
      break;
    case 'job_change': {
      const mode = document.querySelector('input[name="jc_mode"]:checked').value;
      if (mode === 'pct') {
        params.raise_pct = (parseFloat($('em_jc_pct').value) || 0) / 100;
      } else if (mode === 'value') {
        params.raise_value = parseFloat($('em_jc_value').value) || 0;
      } else {
        params.new_salary = {
          base_value: parseFloat($('em_jc_salary').value) || 0,
          dist_type: $('em_jc_dist').value,
          dist_params: readModalDistParams('em_jc', $('em_jc_dist').value),
        };
      }
      break;
    }
    case 'change_living_expense': {
      const mode = document.querySelector('input[name="cle_mode"]:checked').value;
      if (mode === 'pct') {
        params.raise_pct = (parseFloat($('em_cle_pct').value) || 0) / 100;
      } else if (mode === 'value') {
        params.raise_value = parseFloat($('em_cle_value').value) || 0;
      } else {
        params.new_expense = {
          base_value: parseFloat($('em_cle_expense').value) || 0,
          dist_type: $('em_cle_dist').value,
          dist_params: readModalDistParams('em_cle', $('em_cle_dist').value),
        };
      }
      break;
    }
    case 'change_invest_return':
      params.new_return = {
        base_value: (parseFloat($('em_cir_val').value) || 0) / 100,
        dist_type: $('em_cir_dist').value,
        dist_params: readModalDistParams('em_cir', $('em_cir_dist').value),
      };
      break;
    // retirement, redistribute_invest: no params
  }

  const evt = { type, year, params };
  if (idx >= 0 && idx < events.length) {
    events[idx] = evt;
  } else {
    events.push(evt);
  }

  renderEventList();
  closeEventModal();
}

function readModalDistParams(prefix, distType) {
  if (distType === 'fixed') return null;
  if (distType === 'normal') return [parseFloat($(`${prefix}_n_mean`).value) || 0, parseFloat($(`${prefix}_n_std`).value) || 0];
  if (distType === 'uniform') return [parseFloat($(`${prefix}_u_lo`).value) || 0, parseFloat($(`${prefix}_u_hi`).value) || 0];
  if (distType === 'triangular') return [parseFloat($(`${prefix}_t_lo`).value) || 0, parseFloat($(`${prefix}_t_mode`).value) || 0];
  return null;
}

function closeEventModal() {
  $('eventModal').classList.add('hidden');
}

// ════════════════════════════════════════════
//  Event List
// ════════════════════════════════════════════

const EVENT_LABELS = {
  marriage: '结婚', birth: '生子', buy_house: '买房', buy_car: '买车',
  job_change: '换工作', change_living_expense: '改变生活成本',
  change_invest_return: '改变投资回报', retirement: '退休',
  redistribute_invest: '投资再平衡',
};

function renderEventList() {
  const container = $('eventList');
  if (events.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:0.78rem;padding:6px 0;">暂无事件，点击「添加事件」</p>';
    return;
  }
  let html = '<table><thead><tr><th>类型</th><th>年份</th><th>参数摘要</th><th></th></tr></thead><tbody>';
  events.forEach((e, i) => {
    const label = EVENT_LABELS[e.type] || e.type;
    const yearStr = e.year === 'auto' ? '每年' : e.year;
    const summary = eventSummary(e);
    html += `<tr>
      <td>${label}</td>
      <td>${yearStr}</td>
      <td class="event-summary">${summary}</td>
      <td><button class="event-del-btn" data-idx="${i}" title="删除">&times;</button></td>
    </tr>`;
  });
  html += '</tbody></table>';
  container.innerHTML = html;

  // Delete handlers
  container.querySelectorAll('.event-del-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx, 10);
      events.splice(idx, 1);
      renderEventList();
    });
  });
}

function eventSummary(e) {
  const p = e.params || {};
  switch (e.type) {
    case 'marriage': return `收入+${(p.partner_income/1e4).toFixed(0)}W 支出+${(p.extra_expense/1e4).toFixed(1)}W`;
    case 'birth': return `年支出+${(p.child_cost/1e4).toFixed(1)}W 教育${p.edu_start_age}岁起`;
    case 'buy_house': return `房价${(p.house_price/1e4).toFixed(0)}W 首付${(p.down_pct*100).toFixed(0)}%`;
    case 'buy_car': return `车价${(p.car_price/1e4).toFixed(0)}W 首付${(p.down_pct*100).toFixed(0)}%`;
    case 'job_change': return p.raise_pct ? `涨薪${(p.raise_pct*100).toFixed(0)}%` : p.raise_value ? `涨薪${(p.raise_value/1e4).toFixed(1)}W` : '换工作';
    case 'change_living_expense': return p.raise_pct ? `+${(p.raise_pct*100).toFixed(0)}%` : p.raise_value ? `+${(p.raise_value/1e4).toFixed(1)}W` : '调整生活成本';
    case 'change_invest_return': return `回报率→${(p.new_return?.base_value*100).toFixed(1)||'?'}%`;
    case 'retirement': return '工资归零';
    case 'redistribute_invest': return '每年自动执行';
    default: return '';
  }
}

// ════════════════════════════════════════════
//  Job Change mode toggle
// ════════════════════════════════════════════

function updateJobChangeMode() {
  const mode = document.querySelector('input[name="jc_mode"]:checked').value;
  const group = document.querySelector('.em-fields-group[data-type="job_change"]');
  group.querySelectorAll('.jc-dist-group').forEach(el => el.style.display = mode === 'salary' ? 'flex' : 'none');
  group.querySelector('.jc-pct-row').style.display = mode === 'pct' ? 'flex' : 'none';
  group.querySelector('.jc-value-row').style.display = mode === 'value' ? 'flex' : 'none';
  const distContainer = group.querySelector('.em-dist-params[data-target="em_jc_dist"]');
  if (distContainer) distContainer.style.display = mode === 'salary' ? 'block' : 'none';
}

function updateCLEMode() {
  const mode = document.querySelector('input[name="cle_mode"]:checked').value;
  const group = document.querySelector('.em-fields-group[data-type="change_living_expense"]');
  group.querySelectorAll('.cle-dist-group').forEach(el => el.style.display = mode === 'expense' ? 'flex' : 'none');
  group.querySelector('.cle-pct-row').style.display = mode === 'pct' ? 'flex' : 'none';
  group.querySelector('.cle-value-row').style.display = mode === 'value' ? 'flex' : 'none';
  const distContainer = group.querySelector('.em-dist-params[data-target="em_cle_dist"]');
  if (distContainer) distContainer.style.display = mode === 'expense' ? 'block' : 'none';
}

// ════════════════════════════════════════════
//  Serialize Form → INI Text
// ════════════════════════════════════════════

function collectFormValue(id) {
  return parseFloat($(id).value) || 0;
}

function formatValue(val, isPct) {
  if (isPct) return (val / 100).toFixed(4);
  return Math.round(val).toString();
}

function formatDistValue(val, isPct) {
  if (isPct) return (val / 100).toFixed(4);
  return val.toString();
}

function valueLine(key, baseVal, distType, distParams, isPct, annChange) {
  let valStr;
  if (isPct) {
    valStr = baseVal.toFixed(1) + '%';
  } else {
    valStr = Math.round(baseVal).toString();
  }

  if (distType !== 'fixed' && distParams) {
    const params = distParams.map(v => isPct ? v.toFixed(1) + '%' : v.toString()).join(', ');
    const distMap = { normal: 'N', uniform: 'U', triangular: 'T', lognormal: 'LN' };
    const abbrev = distMap[distType] || distType;
    valStr += ` ~ ${abbrev}(${params})`;
  }

  let result = `value = ${valStr}\n`;
  if (annChange != null && annChange !== 0) {
    result += `annual_change_rate = ${(annChange / 100).toFixed(2)}%\n`;
  }
  return result;
}

function eventToString(e) {
  const parts = [e.type, e.year === 'auto' ? 'auto' : String(e.year)];
  const p = e.params || {};
  switch (e.type) {
    case 'marriage':
      parts.push(`partner_income=${Math.round(p.partner_income)}`, `extra_expense=${Math.round(p.extra_expense)}`);
      break;
    case 'birth':
      parts.push(`child_cost=${Math.round(p.child_cost)}`, `edu_start_age=${p.edu_start_age}`, `edu_cost=${Math.round(p.edu_cost)}`);
      break;
    case 'buy_house':
      parts.push(`house_price=${Math.round(p.house_price)}`, `down_pct=${(p.down_pct*100).toFixed(0)}%`, `mortgage_years=${p.mortgage_years}`, `mortgage_rate=${(p.mortgage_rate*100).toFixed(1)}%`, `appreciation=${(p.appreciation*100).toFixed(0)}%`);
      break;
    case 'buy_car':
      parts.push(`car_price=${Math.round(p.car_price)}`, `down_pct=${(p.down_pct*100).toFixed(0)}%`, `loan_years=${p.loan_years}`, `loan_rate=${(p.loan_rate*100).toFixed(1)}%`);
      break;
    case 'job_change':
      if (p.raise_pct != null) {
        parts.push(`raise_pct=${(p.raise_pct*100).toFixed(0)}%`);
      } else if (p.raise_value != null) {
        parts.push(`raise_value=${Math.round(p.raise_value)}`);
      } else if (p.new_salary) {
        const ns = p.new_salary;
        const base = ns.dist_type === 'fixed' ? Math.round(ns.base_value).toString() : Math.round(ns.base_value) + ` ~ ${distAbbrev(ns)}(${distParamsStr(ns)})`;
        parts.push(`new_salary=${base}`);
      }
      break;
    case 'change_living_expense':
      if (p.raise_pct != null) {
        parts.push(`raise_pct=${(p.raise_pct*100).toFixed(0)}%`);
      } else if (p.raise_value != null) {
        parts.push(`raise_value=${Math.round(p.raise_value)}`);
      } else if (p.new_expense) {
        const ne = p.new_expense;
        const base = ne.dist_type === 'fixed' ? Math.round(ne.base_value).toString() : Math.round(ne.base_value) + ` ~ ${distAbbrev(ne)}(${distParamsStr(ne)})`;
        parts.push(`new_expense=${base}`);
      }
      break;
    case 'change_invest_return':
      if (p.new_return) {
        const nr = p.new_return;
        const base = nr.dist_type === 'fixed' ? (nr.base_value*100).toFixed(0)+'%' : (nr.base_value*100).toFixed(0)+'%' + ` ~ ${distAbbrev(nr)}(${distParamsPctStr(nr)})`;
        parts.push(`new_return=${base}`);
      }
      break;
    // retirement, redistribute_invest: no extra params
  }
  return parts.join(' | ');
}

function distAbbrev(param) {
  return { normal: 'N', uniform: 'U', triangular: 'T', lognormal: 'LN' }[param.dist_type] || param.dist_type;
}

function distParamsStr(param) {
  const dp = param.dist_params;
  if (!dp) return '';
  return dp.join(', ');
}

function distParamsPctStr(param) {
  const dp = param.dist_params;
  if (!dp) return '';
  return dp.map(v => (v*100).toFixed(0)+'%').join(', ');
}

function buildConfigText(nSamples) {
  const lines = [];

  lines.push('# Generated by FinLife Web Form');
  lines.push('');

  // simulation
  lines.push('[simulation]');
  lines.push(`start_year = ${parseInt($('f_start_year').value, 10) || 2027}`);
  lines.push(`end_year = ${parseInt($('f_end_year').value, 10) || 2060}`);
  lines.push(`n_samples = ${nSamples}`);
  lines.push(`seed = ${parseInt($('f_seed').value, 10) || 123}`);
  lines.push(`inflation_adjusted = ${$('f_inflation_adj').checked ? 'true' : 'false'}`);
  lines.push('');

  // initial_assets
  lines.push('[initial_assets]');
  lines.push(`cash = ${Math.round(collectFormValue('f_cash'))}`);
  lines.push(`investments = ${Math.round(collectFormValue('f_investments'))}`);
  lines.push(`real_estate = ${Math.round(collectFormValue('f_real_estate'))}`);
  lines.push(`other_assets = ${Math.round(collectFormValue('f_other_assets'))}`);
  lines.push(`liabilities = ${Math.round(collectFormValue('f_liabilities'))}`);
  lines.push('');

  // salary
  lines.push('[salary]');
  lines.push(valueLine('value',
    collectFormValue('f_salary_val'),
    $('f_salary_dist').value,
    readDistParams('f_salary'),
    false,
    collectFormValue('f_salary_ann')));
  lines.push('');

  // living_expense
  lines.push('[living_expense]');
  lines.push(valueLine('value',
    collectFormValue('f_expense_val'),
    $('f_expense_dist').value,
    readDistParams('f_expense'),
    false,
    collectFormValue('f_expense_ann')));
  lines.push('');

  // investment_return (percentages)
  lines.push('[investment_return]');
  lines.push(valueLine('value',
    collectFormValue('f_invret_val'),
    $('f_invret_dist').value,
    readDistParams('f_invret'),
    true,
    null));
  lines.push('');

  // inflation_rate (percentages)
  lines.push('[inflation_rate]');
  lines.push(valueLine('value',
    collectFormValue('f_infl_val'),
    $('f_infl_dist').value,
    readDistParams('f_infl'),
    true,
    null));
  lines.push('');

  // events
  if (events.length > 0) {
    lines.push('[events]');
    events.forEach(e => lines.push(eventToString(e)));
    lines.push('');
  }

  return lines.join('\n');
}

function readDistParams(prefix) {
  const distType = $(`${prefix}_dist`).value;
  if (distType === 'fixed') return null;
  if (distType === 'normal') return [collectFormValue(`${prefix}_n_mean`) || collectFormValue(`${prefix}_val`), collectFormValue(`${prefix}_n_std`)];
  if (distType === 'lognormal') return [parseFloat($(`${prefix}_ln_mu`).value) || 0, parseFloat($(`${prefix}_ln_sigma`).value) || 0];
  if (distType === 'uniform') return [collectFormValue(`${prefix}_u_lo`), collectFormValue(`${prefix}_u_hi`)];
  if (distType === 'triangular') return [collectFormValue(`${prefix}_t_lo`), collectFormValue(`${prefix}_t_mode`) || collectFormValue(`${prefix}_val`), collectFormValue(`${prefix}_t_hi`)];
  return null;
}

// ════════════════════════════════════════════
//  Run Simulation
// ════════════════════════════════════════════

async function runSimulation() {
  const runBtn = $('runBtn');
  runBtn.disabled = true;
  runBtn.textContent = '⏳ 运行中...';
  const overlay = $('loadingOverlay');
  const loadingText = $('loadingText');
  overlay.classList.remove('hidden');
  loadingText.textContent = '正在运行蒙特卡洛模拟...';

  await new Promise(r => setTimeout(r, 50));

  try {
    let configText;
    if (isExpertMode) {
      configText = $('configEditor').value;
    } else {
      const nSamples = parseInt($('samplesSelect').value, 10);
      configText = buildConfigText(nSamples);
      $('configEditor').value = configText;
    }

    const nSamples = parseInt($('samplesSelect').value, 10);
    const result = pyodide.globals.get('_run')(configText, nSamples);
    const data = result.toJs({ dict_converter: Object.fromEntries });

    $('placeholder').classList.add('hidden');
    $('resultsContent').classList.remove('hidden');
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

// ════════════════════════════════════════════
//  Render Results
// ════════════════════════════════════════════

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
    card.innerHTML = `<div class="stat-label">${label}</div><div class="stat-value">${value} ${unit}</div>`;
    container.appendChild(card);
  }
}

function renderMCStats(stats) {
  const container = $('mcStats');
  container.innerHTML = '';
  const last = arr => arr[arr.length - 1];
  const items = [
    ['均值净值', last(stats.mean)],
    ['中位数净值', last(stats.p50)],
    ['5% 分位', last(stats.p5)],
    ['95% 分位', last(stats.p95)],
  ];
  for (const [label, value] of items) {
    const card = document.createElement('div');
    card.className = 'stat-card';
    card.innerHTML = `<div class="stat-label">${label}</div><div class="stat-value">${value} W</div>`;
    container.appendChild(card);
  }
}

function renderEventLog(log) {
  $('eventLog').innerHTML = log.map(e =>
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
  fiTable.forEach(row => { html += `<tr><td>${row.year}</td><td>${row.prob}%</td></tr>`; });
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

// ════════════════════════════════════════════
//  Mode Toggle
// ════════════════════════════════════════════

function toggleMode() {
  isExpertMode = !isExpertMode;
  const formMode = $('formMode');
  const expertMode = $('expertMode');
  const editor = $('configEditor');

  if (isExpertMode) {
    // Switch to expert: serialize form → textarea
    const nSamples = parseInt($('samplesSelect').value, 10);
    editor.value = buildConfigText(nSamples);
    formMode.style.display = 'none';
    expertMode.style.display = 'flex';
    $('toggleModeBtn').textContent = '表单模式';
  } else {
    // Switch back to form
    expertMode.style.display = 'none';
    formMode.style.display = 'flex';
    $('toggleModeBtn').textContent = '专家模式';
  }
}

// ════════════════════════════════════════════
//  Reset to Default
// ════════════════════════════════════════════

function resetToDefault() {
  // Reset number fields to their default values based on HTML
  // We'll just reload the defaults from the HTML attributes
  const defaults = {
    f_start_year: 2027, f_end_year: 2060, f_seed: 123,
    f_cash: 300000, f_investments: 150000, f_real_estate: 0, f_other_assets: 0, f_liabilities: 0,
    f_salary_val: 400000, f_salary_n_mean: 400000, f_salary_n_std: 40000,
    f_salary_ln_mu: 12.9, f_salary_ln_sigma: 0.1,
    f_salary_u_lo: 360000, f_salary_u_hi: 440000,
    f_salary_t_lo: 350000, f_salary_t_mode: 400000, f_salary_t_hi: 450000,
    f_salary_ann: 3,
    f_expense_val: 100000, f_expense_n_mean: 100000, f_expense_n_std: 10000,
    f_expense_ln_mu: 11.5, f_expense_ln_sigma: 0.1,
    f_expense_u_lo: 90000, f_expense_u_hi: 110000,
    f_expense_t_lo: 80000, f_expense_t_mode: 100000, f_expense_t_hi: 120000,
    f_expense_ann: 3,
    f_invret_val: 8, f_invret_n_mean: 8, f_invret_n_std: 18,
    f_invret_u_lo: 5, f_invret_u_hi: 11,
    f_invret_t_lo: 3, f_invret_t_mode: 8, f_invret_t_hi: 13,
    f_infl_val: 3, f_infl_n_mean: 3, f_infl_n_std: 2,
    f_infl_u_lo: 1, f_infl_u_hi: 5,
    f_infl_t_lo: 1, f_infl_t_mode: 3, f_infl_t_hi: 5,
  };

  for (const [id, val] of Object.entries(defaults)) {
    const el = $(id);
    if (el) el.value = val;
  }

  // Reset selects
  $('f_salary_dist').value = 'normal';
  $('f_expense_dist').value = 'normal';
  $('f_invret_dist').value = 'normal';
  $('f_infl_dist').value = 'normal';

  // Checkbox
  $('f_inflation_adj').checked = false;

  // Update all distribution fields
  DIST_CHANGE_IDS.forEach(id => updateDistFields(id));

  // Reset events
  events = [];
  renderEventList();

  // Clear results
  $('resultsContent').classList.add('hidden');
  $('placeholder').classList.remove('hidden');
}

// ════════════════════════════════════════════
//  Init
// ════════════════════════════════════════════

(async function() {
  // Distribution field toggles
  DIST_CHANGE_IDS.forEach(id => setupDistToggle(id));
  // Init dist fields
  DIST_CHANGE_IDS.forEach(id => updateDistFields(id));
  // Modal dist toggles
  ['em_jc_dist', 'em_cle_dist', 'em_cir_dist'].forEach(id => setupModalDistToggle(id));

  // Event type change in modal
  $('em_type').addEventListener('change', () => {
    enableModalFields($('em_type').value);
  });

  // Auto checkbox
  $('em_trigger_auto').addEventListener('change', () => {
    $('em_trigger_year').disabled = $('em_trigger_auto').checked;
  });

  // Job change mode radios
  document.querySelectorAll('input[name="jc_mode"]').forEach(r => {
    r.addEventListener('change', updateJobChangeMode);
  });

  // CLE mode radios
  document.querySelectorAll('input[name="cle_mode"]').forEach(r => {
    r.addEventListener('change', updateCLEMode);
  });

  // Modal buttons
  $('addEventBtn').addEventListener('click', () => openEventModal(-1));
  $('modalSaveBtn').addEventListener('click', saveEventFromModal);
  $('modalCancelBtn').addEventListener('click', closeEventModal);
  $('modalCloseBtn').addEventListener('click', closeEventModal);

  // Close modal on overlay click
  $('eventModal').addEventListener('click', (e) => {
    if (e.target === $('eventModal')) closeEventModal();
  });

  // Mode toggle
  $('toggleModeBtn').addEventListener('click', toggleMode);

  // Reset
  $('loadDefaultBtn').addEventListener('click', resetToDefault);

  // Run
  $('runBtn').addEventListener('click', runSimulation);

  // Init default events
  events = [
    { type: 'marriage', year: 2029, params: { partner_income: 100000, extra_expense: 30000 } },
    { type: 'birth', year: 2030, params: { child_cost: 30000, edu_start_age: 6, edu_cost: 10000 } },
    { type: 'buy_car', year: 2028, params: { car_price: 100000, down_pct: 0.5, loan_years: 3, loan_rate: 0.026 } },
    { type: 'buy_house', year: 2035, params: { house_price: 3000000, down_pct: 0.3, mortgage_years: 30, mortgage_rate: 0.035, appreciation: 0.03 } },
    { type: 'job_change', year: 2033, params: { new_salary: { base_value: 300000, dist_type: 'normal', dist_params: [300000, 30000] } } },
    { type: 'change_invest_return', year: 2045, params: { new_return: { base_value: 0.06, dist_type: 'normal', dist_params: [0.04, 0.02] } } },
    { type: 'retirement', year: 2060, params: {} },
    { type: 'redistribute_invest', year: 'auto', params: {} },
  ];
  renderEventList();

  // Bootstrap Pyodide
  try {
    await initPyodide();
  } catch (err) {
    $('loadingText').textContent = '❌ 加载失败: ' + err.message;
    console.error(err);
  }
})();
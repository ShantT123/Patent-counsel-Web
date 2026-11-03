const $ = (id) => document.getElementById(id);
const state = { user: null, matters: [], detail: null, skill: 'portfolio-strategy', mode: 'draft', output: null, busy: false };
const skills = {
  'portfolio-strategy': { title: 'Portfolio Strategy', description: 'Connect technology areas, product priorities and supplied patent records. Keep inventory signals separate from claim coverage.', deliverable: 'Ownership map, target matrix, inventory and next actions', number: '01' },
  'invention-intake': { title: 'Invention Intake', description: 'Turn rough technical materials into an evidence linked disclosure, focused follow up questions and a counsel review packet.', deliverable: 'Technical disclosure, source references and open questions', number: '02' },
  'filing-review': { title: 'Filing Review', description: 'Review strategic fit against a supplied business rubric and calculate filing budget scenarios from explicit assumptions.', deliverable: 'Business review, portfolio candidates and budget scenarios', number: '03' }
};
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function showError(id, error) { $(id).textContent = error?.message || String(error || ''); $(id).hidden = !error; }
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; setTimeout(() => $('toast').hidden = true, 6000); }
async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, { credentials: 'same-origin', ...options, headers: { 'Content-Type': 'application/json', ...options.headers } }); }
  catch { throw new Error('The website could not reach the server. Check the connection and refresh before repeating a run.'); }
  let data;
  try { data = await response.json(); } catch { throw new Error('The server did not return a valid response. Refresh to check the run history.'); }
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') { state.user = null; showLogin(); }
    throw new Error(data.error || `Request failed (${response.status}).`);
  }
  return data;
}
function post(path, body, method = 'POST') { return api(path, { method, body: JSON.stringify(body) }); }
function date(value) { return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); }
function showLogin() { $('workspace').hidden = true; $('login').hidden = false; $('boot').hidden = true; }
function setView(view) {
  document.querySelectorAll('.view').forEach(n => n.hidden = n.id !== `view-${view}`);
  document.querySelectorAll('[data-view]').forEach(n => n.classList.toggle('active', n.dataset.view === view || (view === 'detail' && n.dataset.view === 'matters')));
  $('breadcrumb-current').textContent = view === 'detail' ? state.detail.matter.title : ({ matters: 'Matters', skills: 'Skill library', team: 'Team access' }[view] || view);
  $('global-error').hidden = true; $('toast').hidden = true;
}
// Safe DOM rendering: supplied sources and model output never become HTML.
function inline(node, text) {
  const pieces = text.split(/(\*\*[^*]+\*\*)/g);
  for (const piece of pieces) node.append(piece.startsWith('**') && piece.endsWith('**') ? element('strong', piece.slice(2, -2)) : document.createTextNode(piece));
}
function markdown(container, text) {
  container.replaceChildren();
  const lines = text.split('\n'); let code = null, list = null, paragraph = [];
  const flush = () => { if (paragraph.length) { const p = element('p'); inline(p, paragraph.join('\n')); container.append(p); paragraph = []; } };
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    if (line.startsWith('```')) { flush(); list = null; if (code) code = null; else { code = element('pre'); container.append(code); } continue; }
    if (code) { code.textContent += line + '\n'; continue; }
    if (line.trim().startsWith('|') && /^\s*\|?[\s:|\-]+\|\s*$/.test(lines[index + 1] || '')) {
      flush(); list = null;
      const cells = value => value.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
      const headers = cells(line), rows = []; index += 1;
      while (index + 1 < lines.length && lines[index + 1].trim().startsWith('|')) rows.push(cells(lines[++index]));
      container.append(reportTable(headers, rows)); continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)/);
    const item = line.match(/^\s*(?:[-*]|\d+[.)])\s+(.+)/);
    if (heading) { flush(); list = null; const h = element(heading[1].length <= 2 ? 'h2' : 'h3'); inline(h, heading[2]); container.append(h); }
    else if (item) { flush(); if (!list) { list = element('ul'); container.append(list); } const li = element('li'); inline(li, item[1]); list.append(li); }
    else if (!line.trim()) { flush(); list = null; }
    else if (/^\s*---+\s*$/.test(line)) { flush(); list = null; }
    else { list = null; paragraph.push(line); }
  }
  flush();
}
function renderMatters() {
  const term = $('search').value.toLowerCase();
  const rows = state.matters.filter(m => `${m.title} ${m.company}`.toLowerCase().includes(term));
  $('matter-list').replaceChildren();
  for (const m of rows) {
    const card = element('button', undefined, 'matter-card'); card.type = 'button';
    const top = element('div', undefined, 'matter-card-top'); top.append(element('span', m.company.toUpperCase(), 'eyebrow'), element('span', 'Working matter', 'draft-tag'));
    const bottom = element('div', undefined, 'matter-card-footer'); bottom.append(element('span', `${m.source_count} source${m.source_count === 1 ? '' : 's'}`), element('span', `${m.run_count} run${m.run_count === 1 ? '' : 's'}`), element('span', '↗', 'arrow'));
    card.append(top, element('h3', m.title), element('p', m.objective), bottom);
    card.addEventListener('click', () => openMatter(m.id).catch(e => showError('global-error', e))); $('matter-list').append(card);
  }
  $('empty-matters').hidden = state.matters.length > 0;
  if (!rows.length && state.matters.length) $('matter-list').append(element('p', 'No matters match your search.', 'helper'));
  $('matter-count').textContent = $('stat-matters').textContent = state.matters.length;
  $('stat-sources').textContent = state.matters.reduce((n, m) => n + m.source_count, 0);
  $('stat-runs').textContent = state.matters.reduce((n, m) => n + m.run_count, 0);
}
async function refreshMatters() { state.matters = await api('/api/matters'); renderMatters(); }
function setTab(tab) {
  document.querySelectorAll('[data-tab]').forEach(n => { const active = n.dataset.tab === tab; n.classList.toggle('active', active); n.setAttribute('aria-selected', String(active)); n.tabIndex = active ? 0 : -1; });
  document.querySelectorAll('.tab-panel').forEach(n => n.hidden = n.id !== `panel-${tab}`);
  if (tab === 'activity') loadActivity().catch(e => showError('global-error', e));
}
async function openMatter(id) {
  const detail = await api(`/api/matters/${id}`); state.detail = detail;
  $('detail-company').textContent = detail.matter.company.toUpperCase(); $('detail-title').textContent = detail.matter.title;
  $('detail-objective').textContent = detail.matter.objective; $('detail-horizon').textContent = detail.matter.horizon;
  $('question').value = ''; $('calculator-input').value = ''; showError('run-error', ''); showError('source-error', '');
  renderSources(); renderHistory(); updateSkill(); setView('detail'); setTab('work');
}
function updateSkill() {
  showError('run-error', '');
  state.skill = $('skill-select').value; $('skill-description').textContent = skills[state.skill].description;
  $('mode-calculation').disabled = state.skill === 'invention-intake';
  if (state.skill === 'invention-intake') state.mode = 'draft';
  updateMode();
  const latest = state.detail?.runs.filter(r => r.skill === state.skill && r.status === 'completed' && r.kind === (state.mode === 'draft' ? 'draft' : 'calculation')).at(-1);
  renderOutput(latest || null);
}
function updateMode() {
  $('mode-draft').classList.toggle('active', state.mode === 'draft'); $('mode-calculation').classList.toggle('active', state.mode === 'calculation');
  $('draft-fields').hidden = state.mode !== 'draft'; $('calculation-fields').hidden = state.mode !== 'calculation';
  $('run-skill').textContent = state.mode === 'draft' ? 'Generate draft ↗' : 'Run calculator ↗';
}
function renderOutput(run) {
  state.output = run; $('output-empty').hidden = Boolean(run); $('output-content').hidden = !run; $('download-output').disabled = !run; $('output-meta').textContent = '';
  $('output-heading').textContent = run ? `${skills[run.skill].title} · ${run.kind === 'draft' ? 'Draft' : 'Calculated result'}` : 'Ready when you are';
  if (!run) { $('output-content').replaceChildren(); return; }
  const result = typeof run.result === 'string' ? JSON.parse(run.result) : run.result;
  if (run.kind === 'calculation') { renderCalculation($('output-content'), result.calculation, run.skill); }
  else markdown($('output-content'), result.text);
  $('output-meta').textContent = `${date(run.created)} · ${run.kind === 'draft' ? 'AI generated · Human review required' : 'Original skill calculator · Supplied inputs only'}`;
}
function reportTable(headers, rows) {
  const wrap = element('div', undefined, 'table-wrap'), table = element('table'), head = element('thead'), heading = element('tr'), body = element('tbody');
  for (const title of headers) { const cell = element('th', title); cell.scope = 'col'; heading.append(cell); }
  head.append(heading);
  for (const row of rows) { const tr = element('tr'); for (const value of row) tr.append(element('td', String(value ?? 'Unknown'))); body.append(tr); }
  table.append(head, body); wrap.append(table); return wrap;
}
function renderCalculation(container, result, skill) {
  container.replaceChildren();
  if (skill === 'portfolio-strategy') {
    container.append(element('h2', 'Supplied portfolio inventory'), element('p', result.inventory_scope));
    const values = result.portfolio_inventory;
    container.append(reportTable(['Application records', 'Known families', 'Unknown family rows'], [[values.records, values.known_families, values.records_with_unknown_family]]));
    container.append(element('h3', 'Targets requiring review'), reportTable(['Feature', 'Jurisdiction', 'Inventory signal', 'Recorded assessment'], result.target_reviews.map(row => [row.target.feature, row.target.jurisdiction, row.inventory_signal.replaceAll('_', ' '), row.current_recorded_assessment.replaceAll('_', ' ')])));
    container.append(element('p', 'These are inventory signals within the supplied scope. They do not establish claim coverage, filing quotas or legal gaps.'));
    if (result.data_quality_warnings.length) container.append(element('h3', 'Data quality notes'), element('pre', JSON.stringify(result.data_quality_warnings, null, 2)));
  } else {
    container.append(element('h2', 'Filing review calculations'), element('p', `Policy: ${result.policy_id} · ${result.policy_state}. Currency: ${result.currency}. Budget period: ${result.budget_period.start} to ${result.budget_period.end}.`));
    container.append(reportTable(['Invention', 'Business score', 'Score state'], result.invention_reviews.map(row => [row.title, row.business_score === null ? 'Incomplete' : row.business_score, row.score_status.replaceAll('_', ' ')])));
    container.append(element('h3', 'Budget scenarios'), reportTable(['Scenario', 'Forecast total', 'Headroom', 'Budget state'], result.scenarios.map(row => [row.id, `${result.currency} ${row.forecast_total}`, `${result.currency} ${row.headroom}`, row.over_budget ? 'Over budget' : 'Within supplied budget'])));
    container.append(element('p', 'Scores reflect supplied business ratings. Costs reflect supplied assumptions. No filing or timing authorization is implied.'));
  }
  const details = element('details', undefined, 'calculation-details'); details.append(element('summary', 'Full calculation and source details'), element('pre', JSON.stringify(result, null, 2))); container.append(details);
}
function renderSources() {
  const sources = state.detail.sources; $('source-list').replaceChildren();
  $('source-tab-count').textContent = sources.length; $('context-summary').textContent = sources.length ? `${sources.length} source${sources.length === 1 ? '' : 's'} available to AI drafts` : 'No sources added yet';
  if (!sources.length) $('source-list').append(element('p', 'Add the notes, roadmap or portfolio records your team will use as evidence.', 'helper'));
  for (const source of sources) {
    const row = element('details', undefined, 'source-row'), summary = element('summary');
    summary.append(element('span', source.name), element('small', `${source.body.length.toLocaleString()} characters · ${date(source.created)}`));
    row.append(summary, element('p', source.id, 'helper'), element('pre', source.body)); $('source-list').append(row);
  }
}
function renderHistory() {
  $('run-history').replaceChildren();
  if (!state.detail.runs.length) $('run-history').append(element('p', 'No runs yet. Generate a draft or run a calculator from the workspace.', 'helper'));
  for (const run of [...state.detail.runs].reverse()) {
    const row = element('button', undefined, 'history-row'), top = element('div', undefined, 'history-top');
    top.append(element('strong', `${skills[run.skill].title} · ${run.kind === 'draft' ? 'AI draft' : 'Calculator'}`), element('small', `${run.status} · ${date(run.created)}`));
    row.append(top, element('p', run.status === 'failed' ? run.error : run.question));
    if (run.status !== 'completed') row.disabled = true;
    row.onclick = () => { $('skill-select').value = run.skill; state.mode = run.kind === 'draft' ? 'draft' : 'calculation'; updateSkill(); renderOutput(run); setTab('work'); };
    $('run-history').append(row);
  }
}
async function loadActivity() {
  const id = state.detail.matter.id, rows = await api(`/api/matters/${id}/audit`);
  if (state.detail.matter.id !== id) return;
  $('activity-list').replaceChildren();
  for (const row of rows) { const item = element('div', undefined, 'activity-row'); item.append(element('span', `${row.name || 'Team member'} · ${row.action.replaceAll('.', ' ')}`), element('small', date(row.created))); $('activity-list').append(item); }
}
function download(name, content, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([content], { type })), a = element('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function addSource(name, text) {
  await post(`/api/matters/${state.detail.matter.id}/sources`, { name, text });
  state.detail = await api(`/api/matters/${state.detail.matter.id}`); renderSources(); await refreshMatters();
}
async function renderTeam() {
  const rows = await api('/api/team'); $('team-list').replaceChildren();
  for (const member of rows) {
    const row = element('div', undefined, `team-row${member.active ? '' : ' inactive'}`), info = element('div');
    info.append(element('strong', member.name), element('small', member.email)); row.append(element('span', member.name.charAt(0).toUpperCase(), 'avatar'), info, element('span', member.role, 'draft-tag'));
    if (member.id !== state.user.id) { const button = element('button', member.active ? 'Disable' : 'Enable', 'text-button'); button.onclick = async () => { try { await post(`/api/team/${member.id}`, { active: !member.active }, 'PATCH'); await renderTeam(); } catch (e) { showError('team-error', e); } }; row.append(button); }
    $('team-list').append(row);
  }
}
async function init() {
  const session = await api('/api/session');
  $('boot').hidden = true; $('setup-note').hidden = !session.setup_required;
  if (!session.user) { showLogin(); return; }
  state.user = session.user; $('login').hidden = true; $('workspace').hidden = false;
  $('user-name').textContent = state.user.name; $('user-role').textContent = state.user.role === 'admin' ? 'Administrator' : 'Member'; $('avatar').textContent = state.user.name.charAt(0).toUpperCase();
  $('team-nav').hidden = state.user.role !== 'admin';
  $('ai-dot').classList.toggle('muted', !session.ai_ready);
  $('ai-status').replaceChildren(document.createTextNode(session.ai_ready ? 'AI configured' : 'AI setup needed'), element('small', session.ai_ready ? 'Connection not yet verified' : 'Calculators available'));
  await refreshMatters(); setView('matters');
}
$('login-form').onsubmit = async event => { event.preventDefault(); const button = event.submitter; button.disabled = true; button.textContent = 'Signing in…'; showError('login-error', ''); try { await post('/api/login', { email: $('login-email').value, password: $('login-password').value }); $('login-password').value = ''; await init(); } catch (e) { showError('login-error', e); } finally { button.disabled = false; button.textContent = 'Sign in ↗'; } };
$('logout').onclick = async () => { try { await post('/api/logout', {}); location.reload(); } catch (e) { showError('global-error', e); } };
document.querySelectorAll('[data-view]').forEach(button => button.onclick = async () => { const view = button.dataset.view; try { if (view === 'matters') await refreshMatters(); if (view === 'team') await renderTeam(); setView(view); document.querySelector('.sidebar').classList.remove('open'); $('mobile-menu').setAttribute('aria-expanded', 'false'); } catch (e) { showError('global-error', e); } });
$('mobile-menu').onclick = () => { const open = document.querySelector('.sidebar').classList.toggle('open'); $('mobile-menu').setAttribute('aria-expanded', String(open)); };
document.addEventListener('keydown', event => { if (event.key === 'Escape') { document.querySelector('.sidebar').classList.remove('open'); $('mobile-menu').setAttribute('aria-expanded', 'false'); } });
$('search').oninput = renderMatters;
for (const id of ['new-matter', 'empty-create']) $(id).onclick = () => { $('matter-form').reset(); $('matter-horizon').value = 'Next 12 months'; showError('matter-error', ''); $('matter-dialog').showModal(); };
$('close-dialog').onclick = () => $('matter-dialog').close();
$('matter-form').onsubmit = async event => { event.preventDefault(); event.submitter.disabled = true; try { const matter = await post('/api/matters', { title: $('matter-title').value, company: $('matter-company').value, objective: $('matter-objective').value, horizon: $('matter-horizon').value }); $('matter-dialog').close(); await refreshMatters(); await openMatter(matter.id); } catch (e) { showError('matter-error', e); } finally { event.submitter.disabled = false; } };
$('back-matters').onclick = async () => { try { await refreshMatters(); setView('matters'); } catch (e) { showError('global-error', e); } };
document.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => setTab(button.dataset.tab));
document.querySelector('.tabs').addEventListener('keydown', event => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return; event.preventDefault(); const tabs = [...document.querySelectorAll('[data-tab]')], index = tabs.indexOf(document.activeElement); const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length; tabs[next].focus(); setTab(tabs[next].dataset.tab); });
$('skill-select').onchange = updateSkill;
for (const mode of ['draft', 'calculation']) $(`mode-${mode}`).onclick = () => { state.mode = mode; updateSkill(); };
document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => { $('question').value = button.dataset.prompt; $('question').focus(); });
$('add-source-shortcut').onclick = () => setTab('sources');
$('source-files').onchange = async event => { showError('source-error', ''); const input = event.target; input.disabled = true; try { for (const file of input.files) { if (file.size > 100000) throw new Error(`${file.name} exceeds 100 KB.`); const bytes = new Uint8Array(await file.arrayBuffer()); const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes); await addSource(file.name, text); } toast('Source materials added.'); } catch (e) { showError('source-error', e); } finally { input.value = ''; input.disabled = false; } };
$('note-form').onsubmit = async event => { event.preventDefault(); event.submitter.disabled = true; try { let name = $('note-name').value; if (!/\.(txt|md|json|csv)$/i.test(name)) name += '.md'; await addSource(name, $('note-text').value); event.target.reset(); toast('Source note saved.'); } catch (e) { showError('source-error', e); } finally { event.submitter.disabled = false; } };
$('calculator-file').onchange = async event => { try { const file = event.target.files[0]; if (!file) return; if (file.size > 300000) throw new Error('Calculator input exceeds 300 KB.'); $('calculator-input').value = await file.text(); } catch (e) { showError('run-error', e); } };
$('schema-guide').onclick = async () => { try { const response = await fetch(`/guides/${state.skill}.md`); if (!response.ok) throw new Error('Input requirements could not be loaded.'); $('guide-content').textContent = await response.text(); $('guide-dialog').showModal(); } catch (e) { showError('run-error', e); } };
$('close-guide').onclick = () => $('guide-dialog').close();
$('run-skill').onclick = async () => {
  if (state.busy) return;
  showError('run-error', ''); const id = state.detail.matter.id;
  const question = state.mode === 'draft' ? $('question').value.trim() : 'Calculate the supplied structured input using the original skill calculator.';
  if (!question) { showError('run-error', new Error('Describe what you would like the skill to prepare.')); return; }
  if (state.mode === 'calculation') { try { JSON.parse($('calculator-input').value); } catch { showError('run-error', new Error('Provide valid calculator JSON before running.')); return; } }
  const payload = { skill: state.skill, kind: state.mode, question, calculator_input: state.mode === 'calculation' ? $('calculator-input').value : undefined, request_id: crypto.randomUUID() };
  state.busy = true; $('run-skill').disabled = true; $('skill-select').disabled = true; $('mode-draft').disabled = true; $('mode-calculation').disabled = true;
  $('run-loading').hidden = false; $('output-empty').hidden = true; $('output-content').hidden = true; $('output-meta').textContent = ''; $('output-heading').textContent = state.mode === 'draft' ? 'Preparing a draft…' : 'Calculating…';
  try {
    const run = await post(`/api/matters/${id}/runs`, payload);
    if (state.detail?.matter.id === id) { state.detail = await api(`/api/matters/${id}`); renderHistory(); renderOutput(run); }
    await refreshMatters(); toast('Run completed and saved to the shared matter.');
  } catch (e) {
    showError('run-error', e); $('output-empty').hidden = false; $('output-heading').textContent = 'Run did not complete';
    if (state.detail?.matter.id === id) { try { state.detail = await api(`/api/matters/${id}`); renderHistory(); } catch { /* Preserve the original failure. */ } }
  } finally {
    state.busy = false; $('run-skill').disabled = false; $('skill-select').disabled = false; $('mode-draft').disabled = false; $('mode-calculation').disabled = state.skill === 'invention-intake'; $('run-loading').hidden = true;
  }
};
$('download-output').onclick = () => { const run = state.output; if (!run) return; const result = JSON.parse(run.result); download(`${run.skill}-${run.id}.${run.kind === 'draft' ? 'md' : 'json'}`, run.kind === 'draft' ? result.text : JSON.stringify(result, null, 2), run.kind === 'draft' ? 'text/markdown' : 'application/json'); };
$('export-matter').onclick = async () => { try { const result = await api(`/api/matters/${state.detail.matter.id}/export`); download(`matter-${result.matter.id}.json`, JSON.stringify(result, null, 2), 'application/json'); } catch (e) { showError('global-error', e); } };
$('team-form').onsubmit = async event => { event.preventDefault(); event.submitter.disabled = true; showError('team-error', ''); try { await post('/api/team', { name: $('team-name').value, email: $('team-email').value, password: $('team-password').value, role: $('team-role').value }); event.target.reset(); await renderTeam(); toast('Account created. Share the credentials through your secure channel.'); } catch (e) { showError('team-error', e); } finally { event.submitter.disabled = false; } };
for (const [key, skill] of Object.entries(skills)) { const card = element('article', undefined, 'skill-card'), info = element('div'); info.append(element('h2', skill.title), element('p', skill.description)); card.append(element('span', skill.number, 'skill-number'), info, element('small', skill.deliverable)); $('skill-library').append(card); }
init().catch(error => { $('boot').hidden = true; showLogin(); showError('login-error', error); });

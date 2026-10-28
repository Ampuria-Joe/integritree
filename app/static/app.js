const $ = s => document.querySelector(s);
const state = {season: "", crop: "", region: ""};
let mode = "index", page = 0;
const COLORS = {maize: "#D9A21B", beans: "#B4472F", sorghum: "#7A5C8C", potato: "#3B6E9E", wheat: "#1F6B4F"};
const charts = {};
const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const num = (v, d = 0) => v == null ? "–" : Number(v).toLocaleString(undefined, {maximumFractionDigits: d});
const qs = () => new URLSearchParams(Object.entries(state).filter(([, v]) => v)).toString();
const get = async (p, extra = "") => {
  const r = await fetch(`/api/${p}?${qs()}${extra}`);
  if (!r.ok) throw new Error(`${p}: ${r.status}`);
  return r.json();
};
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.color = getComputedStyle(document.body).getPropertyValue("--muted").trim() || "#5B6B63";
const draw = (id, cfg) => { charts[id]?.destroy(); charts[id] = new Chart($(id), {options: {maintainAspectRatio: false, ...cfg.options}, ...cfg, options: {maintainAspectRatio: false, ...cfg.options}}); };
const noData = (id, msg) => { charts[id]?.destroy(); const c = $(id).getContext("2d"); c.clearRect(0, 0, 9999, 9999); c.fillText(msg, 10, 20); };

async function loadFilters() {
  const f = await get("filters");
  for (const k of ["season", "crop", "region"]) {
    $(`#f-${k}`).innerHTML = $(`#f-${k}`).firstElementChild.outerHTML + f[k].map(v => `<option>${esc(v)}</option>`).join("");
    $(`#f-${k}`).value = state[k];
  }
}

async function loadSync() {
  const runs = await fetch("/api/runs").then(r => r.json());
  const ok = runs.find(r => r.status === "success"), bad = runs[0]?.status === "failed";
  $("#sync").textContent = ok
    ? `Last successful sync ${ok.finished_at.replace("T", " ")} UTC, ${num(ok.rows_loaded)} records loaded.` + (bad ? " The most recent run failed; check the run log below." : "")
    : "No data yet. Run: flask synth, then flask ingest --csv data/incoming/odk_batch_1.csv";
  $("#runs tbody").innerHTML = runs.map(r => `<tr><td>${esc(r.started_at.replace("T", " "))}</td><td>${esc(r.source)}</td>
    <td><span class="tag ${r.status === "success" ? "ok" : r.status === "failed" ? "err" : "warn"}">${esc(r.status)}</span></td>
    <td class="num">${num(r.rows_extracted)}</td><td class="num">${num(r.rows_loaded)}</td><td class="num">${num(r.rows_rejected)}</td><td class="num">${num(r.rows_warned)}</td></tr>`).join("");
}

async function loadKpis() {
  const k = await get("kpis");
  const items = [["Records", num(k.records)], ["Area (ha)", num(k.area_ha)], ["Yield (kg/ha)", num(k.yield_kg_ha)],
    ["Margin (KES/ha)", num(k.margin_ha)], ["Records flagged", k.flagged_pct == null ? "–" : k.flagged_pct + "%"]];
  $("#kpis").innerHTML = items.map(([t, v]) => `<div><dt>${t}</dt><dd>${v}</dd></div>`).join("");
  const ins = await get("insights");
  $("#insights").innerHTML = ins.map(t => `<li>${esc(t)}</li>`).join("");
}

async function loadTrend() {
  const t = await get("trend");
  if (!t.seasons.length) return noData("#c-trend", "No records for this filter");
  const idx = mode === "index";
  $("#t-trend").textContent = idx ? "Yield index by season (100 = each crop's average)" : "Yield by season (kg/ha)";
  const ds = idx ? [{label: "All crops", data: t.index, borderColor: "#1F6B4F", backgroundColor: "#1F6B4F", tension: .25}]
    : Object.entries(t.series).map(([c, d]) => ({label: c, data: d, borderColor: COLORS[c], backgroundColor: COLORS[c], tension: .25, spanGaps: true}));
  draw("#c-trend", {type: "line", data: {labels: t.seasons, datasets: ds}, options: {scales: {y: {beginAtZero: !idx}}}});
}

async function loadRegions() {
  const r = await get("regions");
  if (!r.labels.length) return noData("#c-region", "No records for this filter");
  const kg = !!state.crop;
  $("#t-region").textContent = kg ? `${state.crop[0].toUpperCase() + state.crop.slice(1)} yield by region (kg/ha)` : "Yield index by region (100 = crop average)";
  draw("#c-region", {type: "bar", data: {labels: r.labels, datasets: [{data: kg ? r.kg_ha : r.index, backgroundColor: "#1F6B4F"}]}, options: {indexAxis: "y", plugins: {legend: {display: false}}}});
}

async function loadMargins() {
  const m = await get("margins");
  if (!m.labels.length) return noData("#c-margin", "No records for this filter");
  draw("#c-margin", {type: "bar", data: {labels: m.labels, datasets: [{data: m.margin_ha, backgroundColor: m.margin_ha.map(v => v < 0 ? "#B4472F" : "#D9A21B")}]}, options: {plugins: {legend: {display: false}}}});
}

async function loadInput() {
  const d = await get("input-response");
  if (!d.fit) return noData("#c-input", "Not enough records for this filter");
  const kg = !!state.crop;
  $("#t-input").textContent = kg ? "Fertiliser (kg/ha) vs yield (kg/ha)" : "Fertiliser (kg/ha) vs yield index";
  const mx = Math.max(...d.points.map(p => p.x));
  const line = [0, mx].map(x => ({x, y: d.fit.intercept_idx + d.fit.slope_idx * x}));
  const sets = [{type: "scatter", label: "Plots", data: d.points.map(p => ({x: p.x, y: kg ? p.y_kg_ha : p.y_idx})), backgroundColor: "rgba(31,107,79,.45)", pointRadius: 3}];
  if (!kg) sets.push({type: "line", label: "Trend", data: line, borderColor: "#B4472F", pointRadius: 0});
  draw("#c-input", {type: "scatter", data: {datasets: sets}, options: {scales: {x: {title: {display: true, text: "Fertiliser kg/ha"}}}}});
}

async function loadDq() {
  const d = await fetch("/api/dq").then(r => r.json()), f = d.funnel;
  $("#funnel").textContent = `${num(f.received)} submissions received. ${num(f.loaded)} passed every gate (${num(f.flagged)} of them carry warnings) and ${num(f.rejected)} were rejected. A check that fires on more than 30% of submissions is marked: look for a fault in the check before blaming the field team.`;
  $("#rules tbody").innerHTML = d.rules.map(r => `<tr><td>${esc(r.rule)}</td><td>${esc(r.description)}</td><td>${esc(r.gate)}</td>
    <td><span class="tag ${r.severity === "error" ? "err" : "warn"}">${r.severity === "error" ? "Rejects" : "Flags"}</span></td>
    <td class="num">${num(r.records)}</td><td class="num ${r.suspect ? "suspect" : ""}">${r.rate}%${r.suspect ? " – check the rule" : ""}</td></tr>`).join("");
}

async function loadRecords() {
  const d = await get("records", `&page=${page}`);
  $("#records tbody").innerHTML = d.rows.length ? d.rows.map(r => `<tr><td>${esc(String(r.submitted_at).slice(0, 10))}</td><td>${esc(r.farmer_id)}</td><td>${esc(r.region)}</td>
    <td>${esc(r.season)}</td><td>${esc(r.crop)}</td><td class="num">${num(r.area_ha, 2)}</td><td class="num">${num(r.yield_kg_ha)}</td><td class="num">${num(r.gross_margin)}</td>
    <td><span class="tag ${r.has_warning ? "warn" : "ok"}">${r.has_warning ? "Flagged" : "Clean"}</span></td></tr>`).join("")
    : `<tr><td colspan="9" class="empty">No records match these filters.</td></tr>`;
  const pages = Math.max(1, Math.ceil(d.total / 15));
  $("#page").textContent = `Page ${page + 1} of ${pages} (${num(d.total)} records)`;
  $("#prev").disabled = page === 0; $("#next").disabled = page + 1 >= pages;
}

const refresh = () => Promise.all([loadKpis(), loadTrend(), loadRegions(), loadMargins(), loadInput(), loadRecords()]);
for (const k of ["season", "crop", "region"]) $(`#f-${k}`).onchange = e => { state[k] = e.target.value; page = 0; refresh(); };
$("#reset").onclick = () => { for (const k in state) { state[k] = ""; $(`#f-${k}`).value = ""; } page = 0; refresh(); };
$("#m-index").onclick = () => { mode = "index"; $("#m-index").classList.add("on"); $("#m-kg").classList.remove("on"); loadTrend(); };
$("#m-kg").onclick = () => { mode = "kg"; $("#m-kg").classList.add("on"); $("#m-index").classList.remove("on"); loadTrend(); };
$("#prev").onclick = () => { page--; loadRecords(); };
$("#next").onclick = () => { page++; loadRecords(); };
loadSync().then(loadFilters).then(refresh).then(loadDq).catch(e => { $("#sync").textContent = "Could not load data: " + e.message; });

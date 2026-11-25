const state = {
  token: localStorage.getItem("bmkg_token") || null,
  user: null,
  filters: { stations: [], parameters: [] },
  dashboardData: null,
  chartMode: "station", // 'station' | 'parameter'
  barChart: null,
  pieChart: null,
  currentCaseId: null,
};

const ROLE_LABELS = {
  staf_qc: "Staf QC / Datin",
  teknisi: "Teknisi / Unit Observasi",
  manajemen: "Manajemen",
};

const PAGE_TITLES = {
  dashboard: ["Beranda (Dashboard Ringkasan Kualitas Data)", "Pemantauan kesehatan data observasi AWS lintas stasiun"],
  etl: ["Import Data & Mesin QC Otomatis (Modul ETL)", "Standardisasi skema & validasi otomatis standar WMO-No. 8"],
  anomalies: ["Monitoring Anomali & Tindak Lanjut", "Pelacakan anomali, penugasan RACI otomatis, panduan SOP & eskalasi"],
  governance: ["Modul Tata Kelola & Jejak Audit", "Rekam jejak audit permanen, Data Dictionary & RACI Registry"],
};

async function apiFetch(url, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    logout();
    throw new Error("Sesi berakhir, silakan login ulang.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "Terjadi kesalahan pada server.");
  }
  return data;
}

function showToast(msg, type = "success") {
  const box = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function fmtDateTime(isoStr) {
  if (!isoStr) return "-";
  const d = new Date(isoStr.endsWith("Z") ? isoStr : isoStr + "Z");
  if (isNaN(d.getTime())) return isoStr;
  return d.toLocaleString("id-ID", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ==================== AUTH ====================

async function login(username, password) {
  const errBox = document.getElementById("login-error");
  errBox.classList.add("hidden");
  try {
    const data = await apiFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("bmkg_token", data.token);
    await enterApp();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
}

function logout() {
  state.token = null;
  state.user = null;
  localStorage.setItem("bmkg_token", "");
  localStorage.removeItem("bmkg_token");
  document.getElementById("app-view").classList.add("hidden");
  document.getElementById("login-view").classList.remove("hidden");
}

async function enterApp() {
  try {
    const me = await apiFetch("/api/auth/me");
    state.user = me.user;
    updateUserHeader(me.notifications);
    await loadFilterOptions();

    document.getElementById("login-view").classList.add("hidden");
    document.getElementById("app-view").classList.remove("hidden");

    applyRolePermissions();
    switchPage("dashboard");
  } catch (err) {
    logout();
  }
}

function updateUserHeader(notifs) {
  const u = state.user;
  document.getElementById("sidebar-role-pill").textContent = ROLE_LABELS[u.role] || u.role;
  document.getElementById("sidebar-user-name").textContent = u.full_name;
  document.getElementById("sidebar-user-unit").textContent = u.unit_name;

  const openBadge = document.getElementById("nav-open-badge");
  if (notifs && notifs.total_open_cases > 0) {
    openBadge.textContent = notifs.total_open_cases;
    openBadge.classList.remove("hidden");
  } else {
    openBadge.classList.add("hidden");
  }

  const notifPill = document.getElementById("role-notif-pill");
  const notifText = document.getElementById("role-notif-text");
  if (u.role === "teknisi") {
    notifPill.classList.remove("hidden");
    notifText.textContent = `${notifs.assigned_open_cases} kasus anomali ditugaskan ke Anda`;
  } else if (u.role === "staf_qc") {
    notifPill.classList.remove("hidden");
    notifText.textContent = `${notifs.total_open_cases} kasus anomali aktif`;
  } else {
    notifPill.classList.add("hidden");
  }
}

function applyRolePermissions() {
  const role = state.user.role;
  const uploadPanel = document.getElementById("etl-upload-panel");
  const readonlyBanner = document.getElementById("etl-readonly-banner");

  if (role === "staf_qc") {
    uploadPanel.classList.remove("hidden");
    readonlyBanner.classList.add("hidden");
  } else {
    uploadPanel.classList.add("hidden");
    readonlyBanner.classList.remove("hidden");
    document.getElementById("etl-role-label").textContent = ROLE_LABELS[role] || role;
  }

  // Teknisi defaults "Tugas Saya" unchecked or checked? Leave unchecked so all cases are visible,
  // but notif pill lets them jump straight to assigned cases!
}

async function refreshNotifications() {
  try {
    const me = await apiFetch("/api/auth/me");
    updateUserHeader(me.notifications);
  } catch (_) {}
}

async function loadFilterOptions() {
  const meta = await apiFetch("/api/meta/filters");
  state.filters = meta;

  const populateSelect = (id, items, valKey, labelKey, defaultLabel) => {
    const sel = document.getElementById(id);
    sel.innerHTML = `<option value="ALL">${defaultLabel}</option>`;
    for (const item of items) {
      const opt = document.createElement("option");
      opt.value = item[valKey];
      opt.textContent = `${item[valKey]} — ${item[labelKey]}`;
      sel.appendChild(opt);
    }
  };

  populateSelect("dash-station", meta.stations, "station_code", "station_name", "Semua Stasiun");
  populateSelect("anom-station", meta.stations, "station_code", "station_name", "Semua Stasiun");
  populateSelect("dash-param", meta.parameters, "parameter_code", "display_name", "Semua Parameter");
  populateSelect("anom-param", meta.parameters, "parameter_code", "display_name", "Semua Parameter");
}

function switchPage(pageName) {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === pageName);
  });
  document.querySelectorAll(".page-section").forEach((sec) => {
    sec.classList.toggle("hidden", sec.id !== `page-${pageName}`);
  });

  const [title, sub] = PAGE_TITLES[pageName] || ["", ""];
  document.getElementById("page-title").textContent = title;
  document.getElementById("page-subtitle").textContent = sub;

  if (pageName === "dashboard") loadDashboard();
  if (pageName === "etl") loadEtlPage();
  if (pageName === "anomalies") loadAnomalies();
  if (pageName === "governance") loadGovernancePage();
}

// ==================== PAGE 1: DASHBOARD ====================

async function loadDashboard() {
  const params = new URLSearchParams();
  const sDate = document.getElementById("dash-start").value;
  const eDate = document.getElementById("dash-end").value;
  const st = document.getElementById("dash-station").value;
  const pm = document.getElementById("dash-param").value;
  if (sDate) params.set("start_date", sDate);
  if (eDate) params.set("end_date", eDate);
  if (st && st !== "ALL") params.set("station_code", st);
  if (pm && pm !== "ALL") params.set("parameter_code", pm);

  const data = await apiFetch(`/api/dashboard?${params.toString()}`);
  state.dashboardData = data;
  renderDashboardKPIs(data.kpis);
  renderDashboardCharts(data);
  renderStationSummaryTable(data.by_station);
}

function renderDashboardKPIs(kpis) {
  document.getElementById("kpi-completeness").textContent = `${kpis.completeness_pct}%`;
  document.getElementById("bar-completeness").style.width = `${kpis.completeness_pct}%`;
  document.getElementById("kpi-total-obs").textContent = `${kpis.total_observations} total observasi`;

  document.getElementById("kpi-validity").textContent = `${kpis.validity_pct}%`;
  document.getElementById("bar-validity").style.width = `${kpis.validity_pct}%`;
  document.getElementById("kpi-valid-qc").textContent = `${kpis.valid_qc_pct}% lulus seluruh aturan WMO-No. 8`;

  document.getElementById("kpi-anomalies").textContent = kpis.total_anomalies;
  document.getElementById("kpi-unhandled").textContent = kpis.unhandled_cases;
  document.getElementById("kpi-escalated-sub").textContent = `${kpis.escalated_cases} eskalasi / lewat SLA`;

  document.getElementById("kpi-compliance").textContent = `${kpis.sop_compliance_pct}%`;
  document.getElementById("kpi-resolved-sub").textContent = `${kpis.resolved_cases} kasus selesai / terverifikasi`;
}

function renderDashboardCharts(data) {
  if (typeof Chart === "undefined") return;

  const isStation = state.chartMode === "station";
  const rows = isStation ? data.by_station : data.by_parameter;
  const labels = rows.map((r) => (isStation ? r.station_code : r.parameter_name));

  if (state.barChart) state.barChart.destroy();
  const barCtx = document.getElementById("chart-quality-bar").getContext("2d");
  state.barChart = new Chart(barCtx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Valid", data: rows.map((r) => r.valid), backgroundColor: "#2563eb", borderRadius: 5 },
        { label: "Warning/Suspect", data: rows.map((r) => r.warning), backgroundColor: "#f59e0b", borderRadius: 5 },
        { label: "Critical/Missing", data: rows.map((r) => r.critical), backgroundColor: "#e11d48", borderRadius: 5 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, beginAtZero: true, grid: { color: "#eef2f6" } },
      },
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, padding: 16 } } },
    },
  });

  if (state.pieChart) state.pieChart.destroy();
  const pieCtx = document.getElementById("chart-violation-pie").getContext("2d");
  const vRows = data.by_violation;
  state.pieChart = new Chart(pieCtx, {
    type: "doughnut",
    data: {
      labels: vRows.length ? vRows.map((v) => v.violation_type) : ["Tidak ada anomali"],
      datasets: [
        {
          data: vRows.length ? vRows.map((v) => v.count) : [1],
          backgroundColor: vRows.length ? ["#2563eb", "#0ea5e9", "#f59e0b", "#e11d48"] : ["#cbd5e1"],
          borderWidth: 2,
          borderColor: "#ffffff",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "66%",
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, padding: 14 } } },
    },
  });
}

function renderStationSummaryTable(rows) {
  const tbody = document.getElementById("dash-station-tbody");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="muted">Belum ada data observasi untuk filter ini.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(
      (r) => `
    <tr>
      <td><strong>${escapeHtml(r.station_code)}</strong></td>
      <td>${escapeHtml(r.station_name)}</td>
      <td>${r.total}</td>
      <td><span class="badge badge-blue">${r.completeness_pct}%</span></td>
      <td><span class="badge badge-success">${r.valid}</span></td>
      <td><span class="badge badge-warning">${r.warning}</span></td>
      <td><span class="badge badge-danger">${r.critical}</span></td>
      <td><strong>${r.open_cases}</strong></td>
      <td>${r.resolved_cases}</td>
      <td>${r.escalated_cases > 0 ? `<span class="badge badge-danger">${r.escalated_cases}</span>` : "0"}</td>
    </tr>`
    )
    .join("");
}

// ==================== PAGE 2: ETL ====================

async function loadEtlPage() {
  const [batches, samples] = await Promise.all([
    apiFetch("/api/etl/batches"),
    apiFetch("/api/samples/list"),
  ]);

  const sampleUl = document.getElementById("sample-files-list");
  sampleUl.innerHTML = samples
    .map(
      (s) => `
    <li>
      <span>📄 <strong>${escapeHtml(s.filename)}</strong> <span class="muted">(${s.size_bytes} B)</span></span>
      <a class="btn btn-outline btn-sm" href="/api/samples/download/${encodeURIComponent(s.filename)}" download>Unduh</a>
    </li>`
    )
    .join("");

  const tbody = document.getElementById("etl-batches-tbody");
  tbody.innerHTML = batches
    .map(
      (b) => `
    <tr>
      <td><code>${escapeHtml(b.batch_code)}</code></td>
      <td>${escapeHtml(b.filename)}</td>
      <td>${escapeHtml(b.uploaded_by)}</td>
      <td>${fmtDateTime(b.uploaded_at)}</td>
      <td>${escapeHtml(b.stations_detected)}</td>
      <td><strong>${b.total_rows}</strong></td>
      <td><span class="badge badge-success">${b.valid_count}</span></td>
      <td><span class="badge badge-warning">${b.warning_count}</span></td>
      <td><span class="badge badge-danger">${b.critical_count}</span></td>
    </tr>`
    )
    .join("");
}

function renderEtlResult(resp) {
  const card = document.getElementById("etl-result-card");
  const body = document.getElementById("etl-result-body");
  card.classList.remove("hidden");

  const rowsHtml = resp.batches
    .map(
      (b) => `
    <tr>
      <td><code>${escapeHtml(b.batch_code)}</code></td>
      <td>${escapeHtml(b.filename)}</td>
      <td>${escapeHtml((b.stations_detected || []).join(", "))}</td>
      <td>${b.total_rows}</td>
      <td><span class="badge badge-success">${b.valid_count}</span></td>
      <td><span class="badge badge-warning">${b.warning_count}</span></td>
      <td><span class="badge badge-danger">${b.critical_count}</span></td>
      <td><strong>${b.new_anomaly_cases} kasus baru</strong></td>
    </tr>`
    )
    .join("");

  body.innerHTML = `
    <div class="alert alert-info">${escapeHtml(resp.message)}</div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Batch</th><th>File</th><th>Stasiun</th><th>Observasi</th>
            <th>Valid</th><th>Warning</th><th>Critical/Missing</th><th>Kasus Dibuat</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>`;
}

// ==================== PAGE 3: ANOMALIES & MODAL ====================

function statusBadge(status) {
  if (status === "Open") return `<span class="badge badge-danger">Open</span>`;
  if (status === "In Progress") return `<span class="badge badge-warning">In Progress</span>`;
  if (status === "Resolved") return `<span class="badge badge-blue">Resolved</span>`;
  return `<span class="badge badge-success">Verified</span>`;
}

async function loadAnomalies() {
  const params = new URLSearchParams();
  const st = document.getElementById("anom-station").value;
  const pm = document.getElementById("anom-param").value;
  const sev = document.getElementById("anom-severity").value;
  const statusVal = document.getElementById("anom-status").value;
  const search = document.getElementById("anom-search").value.trim();
  const mineOnly = document.getElementById("anom-mine-only").checked;

  if (st !== "ALL") params.set("station_code", st);
  if (pm !== "ALL") params.set("parameter_code", pm);
  if (sev !== "ALL") params.set("severity", sev);
  if (statusVal !== "ALL") params.set("status", statusVal);
  if (search) params.set("search", search);
  if (mineOnly) params.set("assigned_to_me", "true");

  const cases = await apiFetch(`/api/anomalies?${params.toString()}`);
  const tbody = document.getElementById("anomalies-tbody");
  if (!cases.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="muted">Tidak ada kasus anomali yang cocok dengan filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = cases
    .map((c) => {
      const rowCls = c.severity === "Critical/Missing" ? "row-critical" : "row-warning";
      const sevBadge =
        c.severity === "Critical/Missing"
          ? `<span class="badge badge-danger">Critical/Missing</span>`
          : `<span class="badge badge-warning">Warning/Suspect</span>`;
      const slaTag = c.is_escalated
        ? `<span class="badge badge-danger">ESKALASI</span>`
        : c.is_overdue
        ? `<span class="badge badge-danger">LEWAT SLA</span>`
        : "";
      return `
      <tr class="clickable-row ${rowCls}" data-case-id="${c.id}">
        <td><strong>${escapeHtml(c.case_code)}</strong></td>
        <td>${fmtDateTime(c.observed_at)}</td>
        <td>${escapeHtml(c.station_code)}<br><span class="muted small">${escapeHtml(c.station_name)}</span></td>
        <td>${escapeHtml(c.parameter_name)}</td>
        <td><code>${escapeHtml(c.raw_value)}</code></td>
        <td>${sevBadge}</td>
        <td><strong>${escapeHtml(c.violation_type)}</strong></td>
        <td>${escapeHtml(c.assigned_pic_name)}<br><span class="muted small">${escapeHtml(c.sop_code)}</span></td>
        <td>${statusBadge(c.status)} ${slaTag}</td>
        <td><button type="button" class="btn btn-outline btn-sm">Detail</button></td>
      </tr>`;
    })
    .join("");

  tbody.querySelectorAll("tr.clickable-row").forEach((tr) => {
    tr.addEventListener("click", () => openCaseModal(Number(tr.dataset.caseId)));
  });
}

async function openCaseModal(caseId) {
  state.currentCaseId = caseId;
  const detail = await apiFetch(`/api/anomalies/${caseId}`);

  document.getElementById("modal-case-code").textContent = `${detail.case_code} · ${detail.severity}`;
  document.getElementById("modal-case-title").textContent = `${detail.station_name} — ${detail.parameter_name}`;

  document.getElementById("modal-error-details").innerHTML = `
    <div class="kv-item"><span class="muted">Waktu Observasi</span><strong>${fmtDateTime(detail.observed_at)}</strong></div>
    <div class="kv-item"><span class="muted">Nilai Tercatat</span><code>${escapeHtml(detail.raw_value)} ${escapeHtml(detail.unit)}</code></div>
    <div class="kv-item"><span class="muted">Pelanggaran QC</span><strong>${escapeHtml(detail.violation_type)}</strong></div>
    <div class="kv-item"><span class="muted">Diagnosa Sistem</span><span>${escapeHtml(detail.diagnostic_message)}</span></div>
  `;

  document.getElementById("modal-raci-details").innerHTML = `
    <div class="raci-row"><span class="raci-letter">R</span><div><strong>Responsible (PIC Lapangan):</strong><br>${escapeHtml(detail.raci.assigned_pic_name)} — ${escapeHtml(detail.raci.responsible)}</div></div>
    <div class="raci-row"><span class="raci-letter">A</span><div><strong>Accountable (Data Owner):</strong><br>${escapeHtml(detail.raci.accountable)}</div></div>
    <div class="raci-row"><span class="raci-letter">C</span><div><strong>Consulted (Data Steward):</strong><br>${escapeHtml(detail.raci.consulted)}</div></div>
    <div class="raci-row"><span class="raci-letter">I</span><div><strong>Informed:</strong><br>${escapeHtml(detail.raci.informed)}</div></div>
  `;

  document.getElementById("modal-sop-title").textContent = `3. Panduan SOP (${detail.sop.sop_code}): ${detail.sop.title}`;
  document.getElementById("modal-sop-steps").innerHTML = detail.sop.steps
    .map((s) => `<li>${escapeHtml(s.replace(/^\d+\.\s*/, ""))}</li>`)
    .join("");

  const statusSelect = document.getElementById("modal-status-select");
  statusSelect.value = detail.status;
  // Teknisi cannot verify
  const verifyOpt = statusSelect.querySelector('option[value="Verified"]');
  if (verifyOpt) verifyOpt.disabled = state.user.role === "teknisi";

  document.getElementById("modal-notes-input").value = detail.resolution_notes || "";

  const slaInfo = document.getElementById("modal-sla-info");
  if (detail.is_escalated) {
    slaInfo.innerHTML = `<span class="badge badge-danger">ESKALASI AKTIF</span> Sejak ${fmtDateTime(detail.escalated_at)}`;
  } else if (detail.is_overdue) {
    slaInfo.innerHTML = `<span class="badge badge-danger">MELEWATI SLA</span> Batas: ${fmtDateTime(detail.sla_due_at)}`;
  } else {
    slaInfo.innerHTML = `<span class="badge badge-success">Dalam SLA</span> Batas: ${fmtDateTime(detail.sla_due_at)}`;
  }

  const canModify = state.user.role === "staf_qc" || state.user.role === "teknisi";
  document.getElementById("modal-save-btn").disabled = !canModify;
  document.getElementById("modal-escalate-btn").disabled = !canModify || detail.status === "Resolved" || detail.status === "Verified";
  document.getElementById("modal-readonly-note").classList.toggle("hidden", canModify);
  statusSelect.disabled = !canModify;
  document.getElementById("modal-notes-input").disabled = !canModify;

  const histBox = document.getElementById("modal-history-list");
  histBox.innerHTML = detail.history
    .map(
      (h) => `
    <div class="history-item">
      <div><strong>${escapeHtml(h.action_type)}</strong> · ${fmtDateTime(h.event_time)} · oleh <em>${escapeHtml(h.actor_name)}</em> (${escapeHtml(h.actor_role)})</div>
      <div class="muted">${h.previous_status ? `${escapeHtml(h.previous_status)} → ` : ""}${escapeHtml(h.new_status || "")}</div>
      <div>${escapeHtml(h.notes)}</div>
    </div>`
    )
    .join("");

  document.getElementById("case-modal").classList.remove("hidden");
}

// ==================== PAGE 4: GOVERNANCE & AUDIT ====================

async function loadGovernancePage() {
  await Promise.all([loadAuditTrail(), loadDataDictionary(), loadRaciAndSops()]);
}

async function loadAuditTrail() {
  const params = new URLSearchParams();
  const cFilter = document.getElementById("audit-case-filter").value.trim();
  const aFilter = document.getElementById("audit-action-filter").value;
  if (cFilter) params.set("case_code", cFilter);
  if (aFilter !== "ALL") params.set("action_type", aFilter);

  const logs = await apiFetch(`/api/governance/audit-trail?${params.toString()}`);
  const tbody = document.getElementById("audit-tbody");
  tbody.innerHTML = logs
    .map(
      (l) => `
    <tr>
      <td><code>${escapeHtml(l.audit_code)}</code></td>
      <td>${fmtDateTime(l.event_time)}</td>
      <td><strong>${escapeHtml(l.case_code)}</strong></td>
      <td><span class="badge badge-slate">${escapeHtml(l.action_type)}</span></td>
      <td>${escapeHtml(l.actor_name)}<br><span class="muted small">${escapeHtml(l.actor_role)}</span></td>
      <td>${escapeHtml(l.previous_status)} → <strong>${escapeHtml(l.new_status)}</strong></td>
      <td>${escapeHtml(l.assigned_pic)}</td>
      <td>${escapeHtml(l.notes)}</td>
    </tr>`
    )
    .join("");
}

async function loadDataDictionary() {
  const items = await apiFetch("/api/governance/data-dictionary");
  document.getElementById("dd-tbody").innerHTML = items
    .map(
      (d) => `
    <tr>
      <td><code>${escapeHtml(d.parameter_code)}</code></td>
      <td><strong>${escapeHtml(d.display_name)}</strong></td>
      <td>${escapeHtml(d.standard_unit)}</td>
      <td><span class="small muted">${escapeHtml(d.accepted_aliases)}</span></td>
      <td>${d.valid_min} .. ${d.valid_max}</td>
      <td>${d.physical_min} .. ${d.physical_max}</td>
      <td>${d.max_step_per_hour} ${escapeHtml(d.standard_unit)}/jam</td>
      <td>${d.persistence_limit}x konstan</td>
      <td><span class="badge badge-blue">${escapeHtml(d.wmo_reference)}</span></td>
    </tr>`
    )
    .join("");
}

async function loadRaciAndSops() {
  const [raci, sops] = await Promise.all([
    apiFetch("/api/governance/raci"),
    apiFetch("/api/governance/sops"),
  ]);

  document.getElementById("raci-tbody").innerHTML = raci
    .map(
      (r) => `
    <tr>
      <td><strong>${escapeHtml(r.station_code)}</strong></td>
      <td>${escapeHtml(r.station_name)}</td>
      <td>${escapeHtml(r.responsible_role)}</td>
      <td>${escapeHtml(r.accountable_role)}</td>
      <td>${escapeHtml(r.consulted_role)}</td>
      <td>${escapeHtml(r.informed_role)}</td>
      <td><strong>${escapeHtml(r.assigned_pic_name)}</strong></td>
      <td>${r.sla_hours_critical}j / ${r.sla_hours_warning}j</td>
    </tr>`
    )
    .join("");

  document.getElementById("sop-cards-grid").innerHTML = sops
    .map(
      (s) => `
    <div class="sop-card">
      <div><span class="badge badge-blue">${escapeHtml(s.sop_code)}</span> <span class="badge badge-slate">${escapeHtml(s.violation_type)}</span></div>
      <h4>${escapeHtml(s.title)}</h4>
      <ol class="sop-steps">${s.steps.map((st) => `<li>${escapeHtml(st.replace(/^\d+\.\s*/, ""))}</li>`).join("")}</ol>
      <div class="muted small mt-12">Target SLA: <strong>${s.sla_target_hours} jam</strong> · Eskalasi: ${escapeHtml(s.escalation_target)}</div>
    </div>`
    )
    .join("");
}

// ==================== EVENT WIRING ====================

document.addEventListener("DOMContentLoaded", () => {
  // Login form & quick demo buttons
  document.getElementById("login-form").addEventListener("submit", (e) => {
    e.preventDefault();
    login(
      document.getElementById("login-username").value.trim(),
      document.getElementById("login-password").value
    );
  });

  document.querySelectorAll(".demo-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("login-username").value = btn.dataset.user;
      document.getElementById("login-password").value = btn.dataset.pass;
      login(btn.dataset.user, btn.dataset.pass);
    });
  });

  document.getElementById("logout-btn").addEventListener("click", logout);

  // Sidebar navigation
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchPage(btn.dataset.page));
  });

  document.getElementById("role-notif-pill").addEventListener("click", () => {
    if (state.user && state.user.role === "teknisi") {
      document.getElementById("anom-mine-only").checked = true;
    }
    switchPage("anomalies");
  });

  // Dashboard filters & chart toggle
  document.getElementById("dash-apply-btn").addEventListener("click", loadDashboard);
  document.getElementById("dash-reset-btn").addEventListener("click", () => {
    document.getElementById("dash-start").value = "";
    document.getElementById("dash-end").value = "";
    document.getElementById("dash-station").value = "ALL";
    document.getElementById("dash-param").value = "ALL";
    loadDashboard();
  });

  document.getElementById("chart-mode-station").addEventListener("click", () => {
    state.chartMode = "station";
    document.getElementById("chart-mode-station").classList.add("active");
    document.getElementById("chart-mode-param").classList.remove("active");
    if (state.dashboardData) renderDashboardCharts(state.dashboardData);
  });

  document.getElementById("chart-mode-param").addEventListener("click", () => {
    state.chartMode = "parameter";
    document.getElementById("chart-mode-param").classList.add("active");
    document.getElementById("chart-mode-station").classList.remove("active");
    if (state.dashboardData) renderDashboardCharts(state.dashboardData);
  });

  // ETL upload & demo controls
  const fileInput = document.getElementById("etl-file-input");
  fileInput.addEventListener("change", () => {
    const names = Array.from(fileInput.files).map((f) => f.name);
    document.getElementById("etl-selected-files").textContent = names.length
      ? `${names.length} file dipilih: ${names.join(", ")}`
      : "Belum ada file dipilih";
  });

  document.getElementById("etl-upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!fileInput.files.length) {
      showToast("Pilih minimal satu file CSV atau Excel terlebih dahulu.", "error");
      return;
    }
    const formData = new FormData();
    Array.from(fileInput.files).forEach((f) => formData.append("files", f));
    try {
      const resp = await apiFetch("/api/etl/upload", { method: "POST", body: formData });
      renderEtlResult(resp);
      showToast(resp.message, "success");
      fileInput.value = "";
      document.getElementById("etl-selected-files").textContent = "Belum ada file dipilih";
      await Promise.all([loadEtlPage(), refreshNotifications()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("etl-demo-sample-btn").addEventListener("click", async () => {
    try {
      const resp = await apiFetch("/api/etl/import-samples", { method: "POST" });
      renderEtlResult(resp);
      showToast(resp.message, "success");
      await Promise.all([loadEtlPage(), refreshNotifications()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("etl-reset-demo-btn").addEventListener("click", async () => {
    try {
      const resp = await apiFetch("/api/etl/reset-demo", { method: "POST" });
      document.getElementById("etl-result-card").classList.add("hidden");
      showToast(resp.message, "success");
      await Promise.all([loadEtlPage(), refreshNotifications()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Anomaly filters
  document.getElementById("anom-filter-btn").addEventListener("click", loadAnomalies);
  document.getElementById("anom-mine-only").addEventListener("change", loadAnomalies);

  // Modal handlers
  document.getElementById("modal-close-btn").addEventListener("click", () => {
    document.getElementById("case-modal").classList.add("hidden");
  });
  document.getElementById("case-modal").addEventListener("click", (e) => {
    if (e.target.id === "case-modal") {
      document.getElementById("case-modal").classList.add("hidden");
    }
  });

  document.getElementById("modal-update-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.currentCaseId) return;
    try {
      await apiFetch(`/api/anomalies/${state.currentCaseId}/status`, {
        method: "PATCH",
        body: JSON.stringify({
          status: document.getElementById("modal-status-select").value,
          resolution_notes: document.getElementById("modal-notes-input").value,
        }),
      });
      showToast("Status kasus & jejak audit berhasil diperbarui.", "success");
      await Promise.all([openCaseModal(state.currentCaseId), loadAnomalies(), refreshNotifications()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("modal-escalate-btn").addEventListener("click", async () => {
    if (!state.currentCaseId) return;
    try {
      await apiFetch(`/api/anomalies/${state.currentCaseId}/escalate`, {
        method: "POST",
        body: JSON.stringify({
          reason: "Simulasi Eskalasi: Penanganan melewati target waktu SLA pada SOP terkait.",
        }),
      });
      showToast("Eskalasi berhasil dicatat ke Data Owner & Audit Trail.", "success");
      await Promise.all([openCaseModal(state.currentCaseId), loadAnomalies(), refreshNotifications()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Governance subtabs
  document.querySelectorAll(".subtab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".subtab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const target = btn.dataset.subtab;
      document.querySelectorAll(".subtab-panel").forEach((p) => {
        p.classList.toggle("hidden", p.id !== `subtab-${target}`);
      });
    });
  });

  document.getElementById("audit-filter-btn").addEventListener("click", loadAuditTrail);

  // Resume session if token exists
  if (state.token) {
    enterApp();
  }
});

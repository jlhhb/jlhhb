const $ = (id) => document.getElementById(id);

let jobId = null;
let pollTimer = null;
let lastSheets = [];

function setBusy(btn, busy, label) {
  btn.disabled = busy;
  if (label) btn.textContent = label;
}

function renderTable(table, headers, rows) {
  table.innerHTML = `<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = row.map((cell) => `<td>${escapeHtml(cell || "—")}</td>`).join("");
    body.appendChild(tr);
  }
  table.appendChild(body);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderSummary(counts) {
  $("summary").classList.remove("hidden");
  $("summary").innerHTML = [
    ["总行数", counts.rows],
    ["未到货", counts.pending],
    ["已签收(跳过)", counts.delivered],
    ["无单号", counts.missing],
  ]
    .map(([label, value]) => `<div class="stat"><b>${value}</b><span>${label}</span></div>`)
    .join("");
}

function fillSelect(select, options, selected) {
  select.innerHTML = options
    .map((opt) => `<option value="${opt.value}" ${String(opt.value) === String(selected) ? "selected" : ""}>${opt.label}</option>`)
    .join("");
}

function currentSheet() {
  const name = $("sheetName").value;
  return lastSheets.find((item) => item.name === name) || lastSheets[0];
}

function renderMapping(data) {
  lastSheets = data.sheets || [];
  $("mapCard").classList.remove("hidden");
  fillSelect(
    $("sheetName"),
    lastSheets.map((item) => ({ value: item.name, label: item.name + (item.active ? "（当前）" : "") })),
    data.sheet_name
  );
  renderColumnSelects(data);
}

function renderColumnSelects(data) {
  const sheet = currentSheet();
  const headers = (sheet && sheet.headers) || [];
  const cols = headers.map((h) => ({
    value: h.index,
    label: `${h.letter}  ${h.title}`,
  }));
  fillSelect($("trackingCol"), cols, data.columns && data.columns.tracking);
  fillSelect($("carrierCol"), [{ value: "", label: "（不使用）" }, ...cols], data.columns && data.columns.carrier);
  fillSelect($("statusCol"), cols, data.columns && data.columns.status);
}

function mappingBody() {
  const carrier = $("carrierCol").value;
  return {
    sheet_name: $("sheetName").value,
    tracking_col: Number($("trackingCol").value),
    carrier_col: carrier === "" ? null : Number(carrier),
    status_col: Number($("statusCol").value),
  };
}

function applyJob(data) {
  jobId = data.job_id;
  if (data.sheets) renderMapping(data);
  renderSummary(data.counts);
  $("actions").classList.remove("hidden");
  $("pendingCard").classList.remove("hidden");
  $("logCard").classList.remove("hidden");
  const pendingRows = data.pending.map((row) => [row.excel_row, row.recipient, row.carrier, row.tracking, row.status]);
  const missingRows = (data.missing || []).map((row) => [row.excel_row, row.recipient, "", "", "未填单号"]);
  renderTable(
    $("pendingTable"),
    ["行", "收件人", "运输公司", "运单号", "当前状态"],
    pendingRows.concat(missingRows)
  );
  $("logs").textContent = (data.logs || []).join("\n");
  $("progress").textContent = data.status === "running"
    ? `查询中 ${data.done}/${data.total}`
    : data.status === "done"
      ? "查询完成"
      : data.error || "";
  if (data.results && data.results.length) {
    $("resultCard").classList.remove("hidden");
    renderTable(
      $("resultTable"),
      ["行", "收件人", "运单号", "新状态", "最新轨迹", "来源"],
      data.results.map((row) => [row.excel_row, row.recipient, row.tracking, row.status, row.latest, row.source])
    );
  }
  const dl = $("downloadBtn");
  if (data.download_ready) {
    dl.classList.remove("hidden");
    dl.href = `/api/jobs/${jobId}/xlsx`;
  } else {
    dl.classList.add("hidden");
  }
  if (data.status === "running") {
    startPoll();
  } else {
    stopPoll();
    setBusy($("runBtn"), false, "刷新未到货");
  }
}

function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    const res = await fetch(`/api/jobs/${jobId}`);
    applyJob(await res.json());
  }, 1500);
}

function stopPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

async function readError(res) {
  try {
    const data = await res.json();
    return data.detail || JSON.stringify(data);
  } catch {
    return res.statusText;
  }
}

$("loadBtn").addEventListener("click", async () => {
  setBusy($("loadBtn"), true, "读取中…");
  try {
    const res = await fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: $("url").value.trim() }),
    });
    if (!res.ok) throw new Error(await readError(res));
    $("resultCard").classList.add("hidden");
    applyJob(await res.json());
  } catch (err) {
    alert(err.message || err);
  } finally {
    setBusy($("loadBtn"), false, "读取表格");
  }
});

$("demoBtn").addEventListener("click", async () => {
  setBusy($("demoBtn"), true, "加载中…");
  try {
    const fileRes = await fetch("/demo.xlsx");
    if (!fileRes.ok) throw new Error("示例表不存在");
    const blob = await fileRes.blob();
    const body = new FormData();
    body.append("file", blob, "demo.xlsx");
    const res = await fetch("/api/preview-file", { method: "POST", body });
    if (!res.ok) throw new Error(await readError(res));
    $("resultCard").classList.add("hidden");
    applyJob(await res.json());
  } catch (err) {
    alert(err.message || err);
  } finally {
    setBusy($("demoBtn"), false, "加载示例表");
  }
});

$("file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  setBusy($("loadBtn"), true, "读取中…");
  try {
    const res = await fetch("/api/preview-file", { method: "POST", body });
    if (!res.ok) throw new Error(await readError(res));
    $("resultCard").classList.add("hidden");
    applyJob(await res.json());
  } catch (err) {
    alert(err.message || err);
  } finally {
    setBusy($("loadBtn"), false, "读取表格");
  }
});

$("sheetName").addEventListener("change", () => {
  if (!jobId) return;
  renderColumnSelects({ columns: { tracking: $("trackingCol").value, carrier: $("carrierCol").value, status: $("statusCol").value } });
});

$("bindBtn").addEventListener("click", async () => {
  if (!jobId) return;
  setBusy($("bindBtn"), true, "预览中…");
  try {
    const res = await fetch(`/api/jobs/${jobId}/bind`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(mappingBody()),
    });
    if (!res.ok) throw new Error(await readError(res));
    $("resultCard").classList.add("hidden");
    applyJob(await res.json());
  } catch (err) {
    alert(err.message || err);
  } finally {
    setBusy($("bindBtn"), false, "按此列预览");
  }
});

$("runBtn").addEventListener("click", async () => {
  if (!jobId) return;
  setBusy($("runBtn"), true, "查询中…");
  $("resultCard").classList.add("hidden");
  try {
    const res = await fetch(`/api/jobs/${jobId}/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ use_ai: $("useAi").checked, ...mappingBody() }),
    });
    if (!res.ok) throw new Error(await readError(res));
    applyJob(await res.json());
  } catch (err) {
    setBusy($("runBtn"), false, "刷新未到货");
    alert(err.message || err);
  }
});

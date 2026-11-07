const $ = (id) => document.getElementById(id);
let token = "";
let jobId = "";
let source = null;

function setLog(line) {
  const el = $("log");
  el.textContent += line + "\n";
  el.scrollTop = el.scrollHeight;
}

async function rpc(method, params) {
  const res = await fetch("/rpc", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Sidecar-Token": token },
    body: JSON.stringify({ method, params: params || {} }),
  });
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "rpc failed");
  return data.result;
}

async function boot() {
  const res = await fetch("/session");
  const info = await res.json();
  token = info.token;
  $("engine").textContent = "sidecar: " + info.host + ":" + info.port;
  const data = await rpc("data.sync");
  $("data").textContent = "keys: " + data.keysCount + " · index: " + data.indexDepots;
  setLog("[boot] sidecar ready, keys=" + data.keysCount + " depots=" + data.indexDepots);
}

function renderCoverage(report) {
  const ok = report.downloadable;
  $("verdict").innerHTML = ok
    ? "<span class=\"ok\">✔ 可以下载</span> · " + report.depots_total + " 个 depot · " + (report.size_bytes / 1073741824).toFixed(2) + " GiB"
    : "<span class=\"bad\">✘ 不能下载</span> · 缺 " + (report.depots_total - report.downloadable_depots) + " 个 depot";
  const rows = ["<tr><th>depot</th><th>gid</th><th>key</th><th>manifest</th><th>size</th></tr>"];
  for (const d of report.depots) {
    rows.push("<tr><td>" + d.depot_id + "</td><td class=\"muted\">" + d.gid + "</td><td>" +
      (d.has_key ? "<span class=\"ok\">有</span>" : "<span class=\"bad\">缺</span>") + "</td><td>" +
      (d.manifest_status === 200 ? "<span class=\"ok\">200</span>" : (d.index_gids > 0 ? "回退(" + d.index_gids + ")" : "<span class=\"bad\">" + d.manifest_status + "</span>")) +
      "</td><td>" + (d.size / 1048576).toFixed(1) + " MB</td></tr>");
  }
  $("depots").innerHTML = rows.join("");
  $("start").disabled = !ok;
}

async function check() {
  const appid = Number($("appid").value);
  setLog("[coverage] appid=" + appid + " …");
  try {
    const report = await rpc("coverage.check", { appid });
    renderCoverage(report);
    setLog("[coverage] downloadable=" + report.downloadable + " depots=" + report.depots_total);
  } catch (err) {
    setLog("[coverage] 失败: " + err.message);
  }
}

function subscribe(id) {
  const es = new EventSource("/events?job=" + encodeURIComponent(id) + "&since=0&token=" + encodeURIComponent(token));
  let bytes = 0;
  es.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "progress") {
      const m = /^(\d+) (\w+)/.exec(data.line || "");
      if (m) setLog("[depot " + m[1] + "] " + m[2]);
    } else if (data.type === "done") {
      const r = data.result || {};
      setLog("[done] ok=" + r.ok + " depots=" + r.restored + "/" + r.depots_total + " files=" + r.files_ok + "/" + r.files_total + " bytes=" + r.bytes);
      $("stats").textContent = "完成 · " + (r.bytes / 1048576).toFixed(1) + " MB";
      $("fill").style.width = "100%";
      $("start").disabled = false; $("cancel").disabled = true;
      es.close();
    } else if (data.type === "error") {
      setLog("[error] " + data.error);
      $("start").disabled = false; $("cancel").disabled = true;
      es.close();
    } else if (data.type === "started") {
      setLog("[job] " + data.jobId + " started");
    }
  };
  es.onerror = () => { setLog("[sse] 连接中断"); es.close(); };
}

async function start() {
  const appid = Number($("appid").value);
  const target = $("target").value;
  $("start").disabled = true; $("cancel").disabled = false;
  $("fill").style.width = "5%";
  $("stats").textContent = "starting…";
  try {
    const res = await rpc("restore.start", { appid, target, depotWorkers: 2, workers: 6 });
    jobId = res.jobId;
    setLog("[restore] jobId=" + jobId);
    subscribe(jobId);
  } catch (err) {
    setLog("[restore] 失败: " + err.message);
    $("start").disabled = false; $("cancel").disabled = true;
  }
}

async function cancel() {
  if (!jobId) return;
  try { await rpc("restore.cancel", { jobId }); setLog("[cancel] 已请求取消"); }
  catch (err) { setLog("[cancel] 失败: " + err.message); }
}

$("check").addEventListener("click", check);
$("start").addEventListener("click", start);
$("cancel").addEventListener("click", cancel);
boot().catch((err) => setLog("[boot] 失败: " + err.message));

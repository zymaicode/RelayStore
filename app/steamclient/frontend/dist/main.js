const $ = (id) => document.getElementById(id);
const app = () => window.go.main.App;

function log(line) {
  const el = $("log");
  el.textContent += line + "\n";
  el.scrollTop = el.scrollHeight;
}

async function boot() {
  try {
    const data = await app().DataSync();
    $("data").textContent = "keys: " + data.keys + " · depots: " + data.depots;
    log("[boot] keys=" + data.keys + " depots=" + data.depots);
  } catch (err) {
    log("[boot] 失败: " + err);
  }
  window.runtime.EventsOn("restore:start", (appid) => log("[job] appid=" + appid + " 开始"));
  window.runtime.EventsOn("restore:depot", (row) => {
    log("[depot " + row.depot_id + "] " + row.status + " files=" + row.files_ok + " bytes=" + row.bytes);
    $("stats").textContent = "depot " + row.depot_id + " " + row.status;
  });
  window.runtime.EventsOn("restore:error", (msg) => { log("[error] " + msg); $("start").disabled = false; });
  window.runtime.EventsOn("restore:done", (result) => {
    log("[done] ok=" + result.ok + " depots=" + result.depots.length + " files=" + result.files_ok + " bytes=" + result.bytes);
    $("stats").textContent = "完成 · " + (result.bytes / 1048576).toFixed(1) + " MB";
    $("fill").style.width = "100%";
    $("start").disabled = false;
  });
}

function render(report) {
  $("verdict").innerHTML = report.downloadable
    ? "<span class=\"ok\">✔ 可以下载</span> · " + report.depots_total + " 个 depot · " + (report.size_bytes / 1073741824).toFixed(2) + " GiB"
    : "<span class=\"bad\">✘ 不能下载</span> · 缺 " + (report.depots_total - report.downloadable_depots) + " 个 depot";
  const rows = ["<tr><th>depot</th><th>gid</th><th>key</th><th>manifest</th><th>size</th></tr>"];
  for (const d of report.depots) {
    rows.push("<tr><td>" + d.depot_id + "</td><td class=\"muted\">" + (d.gid || "").slice(0, 18) + "</td><td>" +
      (d.has_key ? "<span class=\"ok\">有</span>" : "<span class=\"bad\">缺</span>") + "</td><td>" +
      (d.manifest_status === 200 ? "<span class=\"ok\">200</span>" : (d.index_gids > 0 ? "回退(" + d.index_gids + ")" : "<span class=\"bad\">" + d.manifest_status + "</span>")) +
      "</td><td>" + (d.size / 1048576).toFixed(1) + " MB</td></tr>");
  }
  $("depots").innerHTML = rows.join("");
  $("start").disabled = !report.downloadable;
}

async function check() {
  const appid = Number($("appid").value);
  log("[coverage] appid=" + appid + " …");
  try {
    render(JSON.parse(await app().Coverage(appid)));
    log("[coverage] 完成");
  } catch (err) {
    log("[coverage] 失败: " + err);
  }
}

async function start() {
  const appid = Number($("appid").value);
  const target = $("target").value;
  const depotWorkers = Number($("depotWorkers").value) || 1;
  $("start").disabled = true;
  $("fill").style.width = "5%";
  log("[restore] appid=" + appid + " -> " + target);
  try {
    await app().Restore(appid, target, depotWorkers);
  } catch (err) {
    log("[restore] 失败: " + err);
    $("start").disabled = false;
  }
}

$("check").addEventListener("click", check);
$("start").addEventListener("click", start);
boot();

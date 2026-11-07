const $ = (id) => document.getElementById(id);
const app = () => window.go.main.App;

function log(line) {
  const el = $("log");
  el.textContent += line + "\n";
  el.scrollTop = el.scrollHeight;
}

function setData(keys, depots) {
  $("data").textContent = "keys: " + keys + " · depots: " + depots;
}

async function refreshData() {
  const data = await app().DataSync();
  setData(data.keys, data.depots);
  if (data.needsData) {
    $("overlay").classList.add("show");
    $("dataStatus").textContent = "数据目录：" + data.dataDir;
  } else {
    $("overlay").classList.remove("show");
  }
  return data;
}

async function boot() {
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
  window.runtime.EventsOn("data:progress", (info) => {
    if (info.stage === "download") {
      $("dataFill").style.width = info.percent + "%";
      $("dataStatus").textContent = "正在下载第 " + info.index + "/" + info.total + " 个数据源…";
      log("[data] 下载 " + info.source);
    } else if (info.stage === "warn") {
      $("dataStatus").textContent = "一个数据源失败，继续尝试下一个…";
      log("[data] 警告: " + info.message);
    } else if (info.stage === "save") {
      $("dataFill").style.width = "95%";
      $("dataStatus").textContent = "正在写入本地…";
    }
  });
  window.runtime.EventsOn("data:error", (msg) => {
    $("dataStatus").textContent = "失败：" + msg;
    $("downloadData").disabled = false;
    log("[data] 失败: " + msg);
  });
  window.runtime.EventsOn("data:done", async (info) => {
    $("dataFill").style.width = "100%";
    $("dataStatus").textContent = "完成：载入 " + info.keys + " 条密钥";
    log("[data] 完成 keys=" + info.keys + " -> " + info.path);
    await refreshData();
  });

  const data = await refreshData();
  log("[boot] keys=" + data.keys + " depots=" + data.depots + " dir=" + data.dataDir);
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
$("later").addEventListener("click", () => $("overlay").classList.remove("show"));
$("downloadData").addEventListener("click", async () => {
  $("downloadData").disabled = true;
  $("dataStatus").textContent = "准备下载…";
  try {
    await app().BootstrapData();
  } catch (err) {
    $("dataStatus").textContent = "失败：" + err;
    $("downloadData").disabled = false;
  }
});

boot();

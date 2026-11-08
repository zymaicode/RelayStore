const $ = (id) => document.getElementById(id);
const app = () => window.go.main.App;

let updateStatus = null;

function log(line) {
  const el = $("log");
  const ts = new Date().toLocaleTimeString();
  el.textContent += "[" + ts + "] " + line + "\n";
  el.scrollTop = el.scrollHeight;
}

function showPage(name) {
  document.querySelectorAll(".nav").forEach((n) => n.classList.toggle("active", n.dataset.page === name));
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
}

document.querySelectorAll(".nav").forEach((nav) => nav.addEventListener("click", () => showPage(nav.dataset.page)));

// keyboard shortcuts: Ctrl+1..4 switch pages (also used by UI automation tests)
document.addEventListener("keydown", (e) => {
  if (!e.ctrlKey) return;
  const map = { "1": "library", "2": "tasks", "3": "settings", "4": "about" };
  if (map[e.key]) { e.preventDefault(); showPage(map[e.key]); }
  if (e.key === "Enter") { e.preventDefault(); check(); }
});

async function refreshData() {
  const data = await app().DataSync();
  $("version").textContent = data.version;
  $("modeTag").textContent = data.portable ? "便携版" : "安装版";
  $("keyCount").textContent = data.keys;
  $("depotCount").textContent = data.depots;
  $("settingsPath").textContent = "配置：" + data.settings.split(/[\\/]/).pop();
  $("settingsPath").title = data.settings;
  $("aboutVersion").textContent = data.version;
  $("aboutMode").textContent = data.portable ? "便携版" : "安装版";
  $("aboutKeys").textContent = data.keys;
  $("aboutDepots").textContent = data.depots;
  if (data.needsData) {
    $("overlay").classList.add("show");
    $("dataStatus").textContent = "数据目录：" + data.dataDir;
  } else {
    $("overlay").classList.remove("show");
  }
  return data;
}

async function loadSettings() {
  const s = await app().GetSettings();
  $("dataDir").value = s.dataDir;
  $("gameDir").value = s.gameDir;
  $("cfgDepot").value = s.depotWorkers;
  $("cfgChunk").value = s.chunkWorkers;
  $("depotWorkers").value = s.depotWorkers;
}

async function syncTarget() {
  const appid = Number($("libAppid").value || $("appid").value);
  $("target").value = await app().GamePath(appid);
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
  const appid = Number($("libAppid").value || $("appid").value);
  $("verdict").textContent = "检查中…";
  log("[coverage] appid=" + appid);
  try {
    render(JSON.parse(await app().Coverage(appid)));
    log("[coverage] 完成");
  } catch (err) {
    $("verdict").textContent = "检查失败：" + err;
    log("[coverage] 失败: " + err);
  }
}

async function start() {
  const appid = Number($("libAppid").value || $("appid").value);
  const target = $("target").value;
  const depotWorkers = Number($("depotWorkers").value) || 1;
  $("start").disabled = true;
  $("fill").style.width = "5%";
  $("taskBadge").textContent = "进行中";
  showPage("tasks");
  log("[restore] appid=" + appid + " -> " + target);
  try {
    await app().Restore(appid, target, depotWorkers);
  } catch (err) {
    log("[restore] 失败: " + err);
    $("start").disabled = false;
  }
}

async function saveSettings() {
  const next = {
    dataDir: $("dataDir").value,
    gameDir: $("gameDir").value,
    depotWorkers: Number($("cfgDepot").value) || 2,
    chunkWorkers: Number($("cfgChunk").value) || 8,
    checkUpdates: true,
  };
  $("saveHint").textContent = "保存中…";
  try {
    const msg = await app().SaveSettings(next);
    $("saveHint").textContent = msg;
    log("[settings] " + msg);
    await refreshData();
    await syncTarget();
  } catch (err) {
    $("saveHint").textContent = "失败：" + err;
    log("[settings] 失败: " + err);
  }
}

function renderUpdate(status) {
  updateStatus = status;
  $("updateBarWrap").style.display = "none";
  if (status.error) {
    $("updateInfo").textContent = "当前 " + status.current + " · 检查失败：" + status.error;
    $("doUpdate").style.display = "none";
    $("updateBadge").style.display = "none";
    return;
  }
  if (status.hasUpdate) {
    $("updateInfo").innerHTML = "当前 " + status.current + " → <span class=\"ok\">" + status.latest + "</span> 可用";
    $("doUpdate").style.display = "inline-block";
    $("doUpdate").textContent = status.portable ? "前往下载" : "立即更新";
    $("updateBadge").style.display = "inline-block";
    $("updateBadge").textContent = "更新 " + status.latest;
    log("[update] 发现新版本 " + status.latest);
  } else {
    $("updateInfo").textContent = "当前 " + status.current + " · 已是最新";
    $("doUpdate").style.display = "none";
    $("updateBadge").style.display = "none";
  }
}

async function checkUpdate() {
  $("updateInfo").textContent = "检查中…";
  try { renderUpdate(await app().CheckUpdate()); }
  catch (err) { $("updateInfo").textContent = "检查失败：" + err; }
}

async function doUpdate() {
  if (!updateStatus) return;
  if (updateStatus.portable) {
    await app().OpenReleasePage(updateStatus.releaseUrl);
    $("updateHint").textContent = "已打开下载页，下载新 exe 覆盖即可";
    return;
  }
  $("doUpdate").disabled = true;
  $("updateBarWrap").style.display = "block";
  try {
    const path = await app().DownloadInstaller(updateStatus.installerUrl, updateStatus.installerName, updateStatus.installerSha256);
    $("updateHint").textContent = "校验通过，正在启动安装程序…";
    await app().RunInstaller(path);
  } catch (err) {
    $("updateHint").textContent = "更新失败：" + err;
    $("doUpdate").disabled = false;
  }
}

$("check").addEventListener("click", check);
$("start").addEventListener("click", start);
$("saveSettings").addEventListener("click", saveSettings);
$("checkUpdate").addEventListener("click", checkUpdate);
$("doUpdate").addEventListener("click", doUpdate);
$("updateBadge").addEventListener("click", () => { showPage("settings"); checkUpdate(); });
$("appid").addEventListener("change", async () => { $("libAppid").value = $("appid").value; await syncTarget(); check(); });
$("appid").addEventListener("keydown", async (e) => { if (e.key === "Enter") { $("libAppid").value = $("appid").value; await syncTarget(); check(); } });
$("libAppid").addEventListener("change", syncTarget);
$("pickData").addEventListener("click", async () => { const d = await app().PickFolder("选择数据目录", $("dataDir").value); if (d) $("dataDir").value = d; });
$("pickGame").addEventListener("click", async () => { const d = await app().PickFolder("选择游戏目录", $("gameDir").value); if (d) $("gameDir").value = d; });
$("openData").addEventListener("click", () => app().OpenFolder($("dataDir").value));
$("openGame").addEventListener("click", () => app().OpenFolder($("gameDir").value));
$("later").addEventListener("click", () => $("overlay").classList.remove("show"));
$("downloadData").addEventListener("click", async () => {
  $("downloadData").disabled = true;
  $("dataStatus").textContent = "准备下载…";
  try { await app().BootstrapData(); } catch (err) {
    $("dataStatus").textContent = "失败：" + err;
    $("downloadData").disabled = false;
  }
});

window.runtime.EventsOn("restore:start", (appid) => log("[job] appid=" + appid + " 开始"));
window.runtime.EventsOn("restore:depot", (row) => {
  log("[depot " + row.depot_id + "] " + row.status + " files=" + row.files_ok + " bytes=" + row.bytes);
  $("stats").textContent = "depot " + row.depot_id + " " + row.status;
});
window.runtime.EventsOn("restore:error", (msg) => { log("[error] " + msg); $("start").disabled = false; $("taskBadge").textContent = "失败"; });
window.runtime.EventsOn("restore:done", (result) => {
  log("[done] ok=" + result.ok + " depots=" + result.depots.length + " files=" + result.files_ok + " bytes=" + result.bytes);
  $("stats").textContent = "完成 · " + (result.bytes / 1048576).toFixed(1) + " MB";
  $("fill").style.width = "100%";
  $("start").disabled = false;
  $("taskBadge").textContent = result.ok ? "完成" : "失败";
});
window.runtime.EventsOn("data:progress", (info) => {
  if (info.stage === "download") {
    $("dataFill").style.width = info.percent + "%";
    $("dataStatus").textContent = "正在下载第 " + info.index + "/" + info.total + " 个数据源…";
    log("[data] 下载 " + info.source);
  } else if (info.stage === "warn") {
    $("dataStatus").textContent = "一个数据源失败，继续尝试下一个…";
  } else if (info.stage === "save") {
    $("dataFill").style.width = "95%";
    $("dataStatus").textContent = "正在写入本地…";
  } else if (info.stage === "prepare") {
    $("dataStatus").textContent = "准备写入 " + info.target;
  }
});
window.runtime.EventsOn("data:error", (msg) => { $("dataStatus").textContent = "失败：" + msg; $("downloadData").disabled = false; });
window.runtime.EventsOn("data:done", async (info) => {
  $("dataFill").style.width = "100%";
  $("dataStatus").textContent = "完成：载入 " + info.keys + " 条密钥";
  log("[data] 完成 keys=" + info.keys);
  await refreshData();
});
window.runtime.EventsOn("update:progress", (info) => {
  $("updateBarWrap").style.display = "block";
  $("updateFill").style.width = (info.percent || 0) + "%";
  if (info.stage === "download") $("updateHint").textContent = "下载中 " + (info.percent || 0).toFixed(0) + "%";
  if (info.stage === "verify") $("updateHint").textContent = "校验 sha256…";
  if (info.stage === "verified") $("updateHint").textContent = "校验通过";
});

(async function boot() {
  log("[boot] 云驿启动");
  await loadSettings();
  const data = await refreshData();
  await syncTarget();
  await checkUpdate();
  if (data.needsData) log("[boot] 缺少数据，请按提示下载");
})();
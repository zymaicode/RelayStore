const $ = (id) => document.getElementById(id);
const app = () => window.go.main.App;

let updateStatus = null;

/* ---------- utils ---------- */
function fmtBytes(n) {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(v >= 100 || i === 0 ? 0 : 1) + " " + u[i];
}

function toast(text, kind) {
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  el.textContent = text;
  $("toasts").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 300); }, 3200);
}

function log(line) {
  const el = $("log");
  el.textContent += "[" + new Date().toLocaleTimeString() + "] " + line + "\n";
  el.scrollTop = el.scrollHeight;
}

/* ---------- theme (four CodeForge themes) ---------- */
const THEMES = [
  { id: "system", name: "跟随系统", thumb: "./thumbs/theme-system.png" },
  { id: "light", name: "浅色", thumb: "./thumbs/theme-light.png" },
  { id: "dark", name: "深色", thumb: "./thumbs/theme-dark.png" },
  { id: "animal", name: "森友会", thumb: "./thumbs/theme-animal.png" },
  { id: "wenyang", name: "纹样", thumb: "./thumbs/theme-wenyang.png" },
];

const SIZES = [
  { id: "compact", name: "紧凑" },
  { id: "standard", name: "标准" },
  { id: "relaxed", name: "宽松" },
];

function applySize(name) {
  document.body.dataset.size = name || "standard";
  document.querySelectorAll(".size-opt").forEach((el) => el.classList.toggle("active", el.dataset.size === name));
}

function renderSizePicker(current) {
  const box = $("sizePicker");
  if (!box) return;
  box.innerHTML = SIZES.map((s) =>
    '<button class="size-opt' + (s.id === current ? " active" : "") + '" data-size="' + s.id + '">' + s.name + "</button>"
  ).join("");
  box.querySelectorAll(".size-opt").forEach((el) => el.addEventListener("click", async () => {
    const id = el.dataset.size;
    applySize(id);
    try { await app().SetFontSize(id); renderSizePicker(id); toast("字号：" + (SIZES.find((s) => s.id === id) || {}).name, "ok"); }
    catch (err) { toast("字号保存失败：" + err, "bad"); }
  }));
}

let themeChoice = "system";

function resolveTheme(choice) {
  if (choice === "system") {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return choice || "light";
}

function applyTheme(choice) {
  themeChoice = choice || "system";
  const resolved = resolveTheme(themeChoice);
  document.documentElement.dataset.theme = resolved;
  const btn = $("themeBtn");
  if (btn) btn.textContent = resolved === "dark" ? "☀" : "☾";
  document.querySelectorAll(".theme-opt").forEach((el) => el.classList.toggle("active", el.dataset.theme === themeChoice));
}

if (window.matchMedia) {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const onChange = () => { if (themeChoice === "system") applyTheme("system"); };
  if (mq.addEventListener) mq.addEventListener("change", onChange);
  else if (mq.addListener) mq.addListener(onChange);
}

function renderThemePicker(current) {
  const box = $("themePicker");
  if (!box) return;
  box.innerHTML = THEMES.map((t) =>
    '<div class="theme-opt' + (t.id === current ? " active" : "") + '" data-theme="' + t.id + '" title="' + t.name + '">' +
    '<img src="' + t.thumb + '" alt="' + t.name + '" />' +
    "<span>" + t.name + "</span></div>"
  ).join("");
  box.querySelectorAll(".theme-opt").forEach((el) => el.addEventListener("click", async () => {
    const id = el.dataset.theme;
    applyTheme(id);
    try { await app().SetTheme(id); renderThemePicker(id); toast("已切换主题：" + (THEMES.find((t) => t.id === id) || {}).name, "ok"); }
    catch (err) { toast("主题保存失败：" + err, "bad"); }
  }));
}

$("themeBtn").addEventListener("click", async () => {
  const cur = document.documentElement.dataset.theme || "light";
  const idx = THEMES.findIndex((t) => t.id === cur);
  const next = THEMES[(idx + 1) % THEMES.length].id;
  applyTheme(next);
  renderThemePicker(next);
  try { await app().SetTheme(next); } catch (e) {}
});

/* ---------- navigation ---------- */
function showPage(name) {
  document.querySelectorAll(".nav").forEach((n) => n.classList.toggle("active", n.dataset.page === name));
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
}

document.querySelectorAll(".nav").forEach((nav) => nav.addEventListener("click", () => showPage(nav.dataset.page)));
document.addEventListener("keydown", (e) => {
  if (!e.ctrlKey) return;
  const map = { "1": "library", "2": "store", "3": "tasks", "4": "settings", "5": "about" };
  if (map[e.key]) { e.preventDefault(); showPage(map[e.key]); }
});

/* ---------- store sources (second level) ---------- */
let storeSources = [];
let currentSource = "builtin";

function renderSources() {
  const box = $("storeSources");
  box.innerHTML = storeSources.map((s) =>
    '<div class="subitem' + (s.id === currentSource ? " active" : "") + (s.available ? "" : " disabled") + '" data-source="' + s.id + '" title="' + (s.note || "") + '">' +
    '<span class="dot"></span><span>' + s.name + '</span></div>'
  ).join("");
  box.querySelectorAll("[data-source]").forEach((item) => item.addEventListener("click", async (e) => {
    e.stopPropagation();
    const src = storeSources.find((s) => s.id === item.dataset.source);
    if (!src) return;
    if (!src.available) { toast(src.name + " 暂不可用：" + (src.note || ""), "bad"); return; }
    currentSource = src.id;
    renderSources();
    showPage("store");
    $("storeQuery").value = "";
    await loadStore("");
  }));
}

async function initSources() {
  try { storeSources = await app().StoreSources(); } catch (e) { storeSources = [{ id: "builtin", name: "云驿榜单", available: true }]; }
  renderSources();
}

function toggleStoreNav() {
  const box = $("storeSources");
  const open = box.classList.toggle("open");
  $("storeChevron").classList.toggle("open", open);
}

$("navStore").addEventListener("click", () => { showPage("store"); toggleStoreNav(); });
/* ---------- data ---------- */
async function refreshData() {
  const data = await app().DataSync();
  $("version").textContent = data.version;
  $("modeTag").textContent = data.portable ? "便携版" : "安装版";
  $("keyCount").textContent = data.keys;
  $("depotCount").textContent = data.depots;
  $("aboutVersion").textContent = data.version;
  $("aboutMode").textContent = data.portable ? "便携版" : "安装版";
  $("aboutKeys").textContent = data.keys;
  $("aboutDepots").textContent = data.depots;
  const short = data.settings.split(/[\\/]/).pop();
  $("settingsPath").textContent = "配置：" + short;
  $("settingsPath").title = data.settings;
  if (data.needsData) {
    $("overlay").classList.add("show");
    $("dataStatus").textContent = "数据目录：" + data.dataDir;
  } else {
    $("overlay").classList.remove("show");
  }
  return data;
}

const VERDICT_TEXT = {
  ready: "可启动",
  needs_steam: "需 Steam 授权",
  drm_locked: "DRM 锁定",
  anticheat: "含反作弊",
  no_exe: "无可执行文件",
  missing: "未安装",
};

async function loadGames() {
  const games = await app().InstalledGames();
  const list = $("gameList");
  if (!games.length) {
    list.innerHTML = '<div class="empty">还没有安装游戏<br/><span style="font-size:11.5px">在下方输入 AppID 检查并下载后，会显示在这里</span></div>';
    return;
  }
  let metas = {};
  try { metas = await app().GameMetas(games.map((g) => g.appid)); } catch (e) { metas = {}; }
  const checks = await Promise.all(games.map(async (g) => {
    try { return await app().InspectGame(g.appid); } catch (e) { return null; }
  }));
  const runtimes = await Promise.all(games.map(async (g) => {
    try { return await app().RuntimeStatus(g.appid); } catch (e) { return null; }
  }));
  list.innerHTML = games.map((g, i) => {
    const meta = metas[g.appid] || metas[String(g.appid)] || {};
    const check = checks[i] || { verdict: "missing", detail: "无法预检" };
    const title = meta.name || ("AppID " + g.appid);
    const initial = (meta.name || String(g.appid)).trim().slice(0, 1).toUpperCase();
    const runtime = runtimes[i] || { installed: false };
    const canLaunch = check.verdict === "ready" || check.verdict === "anticheat" || check.verdict === "needs_steam";
    const needsRuntime = check.verdict === "needs_steam";
    return '<div class="game">' +
      '<div class="cover">' + initial + '</div>' +
      '<div class="meta"><div class="title">' + title +
      ' <span class="verdict ' + check.verdict + '" title="' + (check.detail || "") + '">' + (VERDICT_TEXT[check.verdict] || check.verdict) + "</span></div>" +
      '<div class="path" title="' + g.path + '">AppID ' + g.appid + ' · ' + g.path + '</div>' +
      (check.detail ? '<div class="path">' + check.detail + "</div>" : "") +
      (check.lastExit && check.lastExit !== 0 ? '<div class="path bad">上次启动崩溃：退出码 ' + check.lastExit + '（0x' + (check.lastExit < 0 ? (check.lastExit >>> 0).toString(16).toUpperCase() : check.lastExit.toString(16).toUpperCase()) + '）</div>' : "") +
      "</div>" +
      '<div class="size">' + fmtBytes(g.bytes) + ' · ' + g.files + ' 个文件</div>' +
      (canLaunch ? '<button data-launch="' + g.appid + '">启动</button>' : "") +
      (needsRuntime ? '<button class="ghost" data-runtime="' + g.appid + '" data-on="' + (runtime.installed ? "1" : "0") + '" title="' + (runtime.installed ? "移除运行时层" : "启用运行时层（gse_fork，按需下载）") + '">' + (runtime.installed ? "移除运行时" : "启用运行时") + '</button>' : "") +
      '<button class="ghost" data-exe="' + g.appid + '" title="指定主程序">主程序</button>' +
      '<button class="ghost" data-refresh="' + g.appid + '" title="重新检测">重检</button>' +
      '<button class="ghost" data-open="' + g.path.replace(/"/g, "&quot;") + '">打开目录</button>' +
      '</div>';
  }).join("");
  list.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => app().OpenPath(btn.dataset.open)));
  list.querySelectorAll("[data-runtime]").forEach((btn) => btn.addEventListener("click", async () => {
    const appid = Number(btn.dataset.runtime);
    const on = btn.dataset.on === "1";
    btn.disabled = true;
    try {
      const msg = on ? await app().RemoveRuntime(appid) : await app().InstallRuntimeLoader(appid);
      if (on) { try { await app().RemoveRuntimeLoader(appid); } catch (e) {} }
      toast(msg, "ok");
    } catch (err) { toast((on ? "移除" : "启用") + "运行时层失败：" + err, "bad"); }
    await loadGames();
  }));
  list.querySelectorAll("[data-refresh]").forEach((btn) => btn.addEventListener("click", async () => {
    await app().RefreshInspection(Number(btn.dataset.refresh));
    await loadGames();
    toast("已重新检测", "ok");
  }));
  list.querySelectorAll("[data-exe]").forEach((btn) => btn.addEventListener("click", async () => {
    const chosen = await app().PickGameExe(Number(btn.dataset.exe));
    if (chosen) { await loadGames(); toast("已指定主程序", "ok"); }
  }));
  list.querySelectorAll("[data-launch]").forEach((btn) => btn.addEventListener("click", async () => {
    btn.disabled = true;
    const msg = await app().LaunchGame(Number(btn.dataset.launch));
    btn.disabled = false;
    if (msg && msg.startsWith("运行时层不可用")) toast(msg, "bad");
    else if (msg) toast(msg + "，正在启动…", "ok");
    else toast("已启动 AppID " + btn.dataset.launch, "ok");
  }));
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
  $("target").value = await app().InstallPathFor(appid);
}

/* ---------- coverage / restore ---------- */
function render(report) {
  $("verdict").innerHTML = report.downloadable
    ? '<span class="ok">✔ 可以下载</span> · ' + report.depots_total + " 个 depot · " + (report.size_bytes / 1073741824).toFixed(2) + " GiB"
    : '<span class="bad">✘ 不能下载</span> · 缺 ' + (report.depots_total - report.downloadable_depots) + " 个 depot";
  const rows = ["<tr><th>depot</th><th>gid</th><th>key</th><th>manifest</th><th>size</th></tr>"];
  for (const d of report.depots) {
    rows.push("<tr><td>" + d.depot_id + '</td><td class="muted">' + (d.gid || "").slice(0, 18) + "</td><td>" +
      (d.has_key ? '<span class="ok">有</span>' : '<span class="bad">缺</span>') + "</td><td>" +
      (d.manifest_status === 200 ? '<span class="ok">200</span>' : (d.index_gids > 0 ? "回退(" + d.index_gids + ")" : '<span class="bad">' + d.manifest_status + "</span>")) +
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
    const report = JSON.parse(await app().Coverage(appid));
    render(report);
    toast(report.downloadable ? "AppID " + appid + " 可以下载" : "AppID " + appid + " 缺少依赖", report.downloadable ? "ok" : "bad");
  } catch (err) {
    $("verdict").textContent = "检查失败：" + err;
    toast("检查失败：" + err, "bad");
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
  try { await app().Restore(appid, target, depotWorkers); }
  catch (err) { log("[restore] 失败: " + err); toast("下载启动失败：" + err, "bad"); $("start").disabled = false; }
}

/* ---------- settings / update ---------- */
async function saveSettings() {
  const next = {
    dataDir: $("dataDir").value, gameDir: $("gameDir").value,
    depotWorkers: Number($("cfgDepot").value) || 2,
    chunkWorkers: Number($("cfgChunk").value) || 8, checkUpdates: true,
  };
  $("saveHint").textContent = "保存中…";
  try {
    const msg = await app().SaveSettings(next);
    $("saveHint").textContent = msg;
    toast(msg, "ok");
    await refreshData(); await loadGames(); await syncTarget();
  } catch (err) { $("saveHint").textContent = "失败：" + err; toast("保存失败：" + err, "bad"); }
}

function renderUpdate(status) {
  updateStatus = status;
  $("updateBarWrap").style.display = "none";
  if (status.error) {
    $("updateInfo").textContent = "当前 " + status.current + " · 检查失败：" + status.error;
    $("doUpdate").style.display = "none"; $("updateBadge").style.display = "none"; return;
  }
  if (status.hasUpdate) {
    $("updateInfo").innerHTML = "当前 " + status.current + ' → <span class="ok">' + status.latest + "</span> 可用";
    $("doUpdate").style.display = "inline-block";
    $("doUpdate").textContent = status.portable ? "前往下载" : "立即更新";
    $("updateBadge").style.display = "inline-block";
    $("updateBadge").textContent = "更新 " + status.latest;
  } else {
    $("updateInfo").textContent = "当前 " + status.current + " · 已是最新";
    $("doUpdate").style.display = "none"; $("updateBadge").style.display = "none";
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
  } catch (err) { $("updateHint").textContent = "更新失败：" + err; toast("更新失败：" + err, "bad"); $("doUpdate").disabled = false; }
}

/* ---------- wiring ---------- */
$("check").addEventListener("click", check);
$("start").addEventListener("click", start);
$("saveSettings").addEventListener("click", saveSettings);
$("checkUpdate").addEventListener("click", checkUpdate);
$("doUpdate").addEventListener("click", doUpdate);
$("refreshGames").addEventListener("click", async () => { await loadGames(); toast("已刷新"); });
$("updateBadge").addEventListener("click", () => { showPage("settings"); checkUpdate(); });
$("appid").addEventListener("change", async () => { $("libAppid").value = $("appid").value; await syncTarget(); check(); });
$("appid").addEventListener("keydown", async (e) => { if (e.key === "Enter") { $("libAppid").value = $("appid").value; await syncTarget(); check(); } });
$("libAppid").addEventListener("change", syncTarget);
$("pickData").addEventListener("click", async () => { const d = await app().PickFolder("选择数据目录", $("dataDir").value); if (d) $("dataDir").value = d; });
$("pickGame").addEventListener("click", async () => { const d = await app().PickFolder("选择游戏目录", $("gameDir").value); if (d) $("gameDir").value = d; });
$("openData").addEventListener("click", () => app().OpenPath($("dataDir").value));
$("openGame").addEventListener("click", () => app().OpenPath($("gameDir").value));
$("later").addEventListener("click", () => $("overlay").classList.remove("show"));
$("downloadData").addEventListener("click", async () => {
  $("downloadData").disabled = true;
  $("dataStatus").textContent = "准备下载…";
  try { await app().BootstrapData(); }
  catch (err) { $("dataStatus").textContent = "失败：" + err; $("downloadData").disabled = false; }
});

window.runtime.EventsOn("restore:start", (appid) => log("[job] appid=" + appid + " 开始"));
window.runtime.EventsOn("restore:depot", (row) => {
  log("[depot " + row.depot_id + "] " + row.status + " files=" + row.files_ok + " bytes=" + row.bytes);
  $("stats").textContent = "depot " + row.depot_id + " " + row.status;
});
window.runtime.EventsOn("restore:error", (msg) => { log("[error] " + msg); $("start").disabled = false; $("taskBadge").textContent = "失败"; toast("下载失败：" + msg, "bad"); });
window.runtime.EventsOn("restore:done", async (result) => {
  log("[done] ok=" + result.ok + " depots=" + result.depots.length + " files=" + result.files_ok + " bytes=" + result.bytes);
  $("stats").textContent = "完成 · " + fmtBytes(result.bytes);
  $("fill").style.width = "100%";
  $("start").disabled = false;
  $("taskBadge").textContent = result.ok ? "完成" : "失败";
  toast(result.ok ? "下载完成 · " + fmtBytes(result.bytes) : "下载结束但有失败项", result.ok ? "ok" : "bad");
  await loadGames();
});
window.runtime.EventsOn("data:progress", (info) => {
  if (info.stage === "download") { $("dataFill").style.width = info.percent + "%"; $("dataStatus").textContent = "正在下载第 " + info.index + "/" + info.total + " 个数据源…"; }
  else if (info.stage === "warn") { $("dataStatus").textContent = "一个数据源失败，继续尝试下一个…"; }
  else if (info.stage === "save") { $("dataFill").style.width = "95%"; $("dataStatus").textContent = "正在写入本地…"; }
  else if (info.stage === "prepare") { $("dataStatus").textContent = "准备写入 " + info.target; }
});
window.runtime.EventsOn("data:error", (msg) => { $("dataStatus").textContent = "失败：" + msg; $("downloadData").disabled = false; toast("数据下载失败：" + msg, "bad"); });
window.runtime.EventsOn("data:done", async (info) => {
  $("dataFill").style.width = "100%";
  $("dataStatus").textContent = "完成：载入 " + info.keys + " 条密钥";
  toast("数据就绪 · " + info.keys + " 条密钥", "ok");
  await refreshData();
});
window.runtime.EventsOn("update:progress", (info) => {
  $("updateBarWrap").style.display = "block";
  $("updateFill").style.width = (info.percent || 0) + "%";
  if (info.stage === "download") $("updateHint").textContent = "下载中 " + (info.percent || 0).toFixed(0) + "%";
  if (info.stage === "verify") $("updateHint").textContent = "校验 sha256…";
  if (info.stage === "verified") $("updateHint").textContent = "校验通过";
});

/* ---------- store ---------- */
let storeSelected = null;

function renderStoreList(games) {
  const list = $("storeList");
  if (!games.length) {
    list.innerHTML = '<div class="empty">没有匹配的游戏<br/><span style="font-size:11.5px">换个关键字，或直接输入 AppID</span></div>';
    return;
  }
  list.innerHTML = games.map((g, i) => {
    const name = g.name || ("AppID " + g.appid);
    const initial = name.trim().slice(0, 1).toUpperCase();
    return '<div class="game" data-appid="' + g.appid + '" data-name="' + name.replace(/"/g, "&quot;") + '" style="cursor:pointer">' +
      '<div class="cover">' + initial + '</div>' +
      '<div class="meta"><div class="title">' + name + '</div>' +
      '<div class="path">AppID ' + g.appid + (g.name ? "" : " · 未在内置榜单") + '</div></div>' +
      '<div class="size">#' + (i + 1) + '</div>' +
      '</div>';
  }).join("");
  list.querySelectorAll("[data-appid]").forEach((row) => row.addEventListener("click", () => {
    selectStoreGame(Number(row.dataset.appid), row.dataset.name);
  }));
}

async function loadStore(query) {
  try {
    const result = await app().StoreList(currentSource, query || "");
    renderStoreList(result.games || []);
    if (result.updated) $("storeUpdated").textContent = "榜单 " + result.updated;
    if (result.error) toast(result.error, "bad");
    if (result.hint) toast(result.hint, "bad");
    if ((!result.games || !result.games.length) && result.hint) {
      $("storeList").innerHTML = '<div class="empty">' + result.hint + '</div>';
    }
  } catch (err) { toast("商店加载失败：" + err, "bad"); }
}

async function selectStoreGame(appid, name) {
  storeSelected = { appid, name };
  $("storeDetail").style.display = "block";
  $("storeDetailName").textContent = name || ("AppID " + appid);
  $("storeDetailAppid").textContent = "AppID " + appid;
  $("storeVerdict").textContent = "先检查可用性";
  $("storeStart").disabled = true;
  $("storeDepots").innerHTML = "";
  const path = await app().InstallPathFor(appid);
  $("storeDetailPath").textContent = "安装到：" + path;
  storeSelected.path = path;
  $("storeDetail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function storeCheck() {
  if (!storeSelected) return;
  $("storeVerdict").textContent = "检查中…";
  try {
    const report = JSON.parse(await app().Coverage(storeSelected.appid));
    $("storeVerdict").innerHTML = report.downloadable
      ? '<span class="ok">✔ 可以下载</span> · ' + report.depots_total + " depot · " + fmtBytes(report.size_bytes)
      : '<span class="bad">✘ 缺少依赖</span> · 缺 ' + (report.depots_total - report.downloadable_depots) + " 个 depot";
    const rows = ["<tr><th>depot</th><th>key</th><th>manifest</th><th>size</th></tr>"];
    for (const d of report.depots) {
      rows.push("<tr><td>" + d.depot_id + "</td><td>" + (d.has_key ? '<span class="ok">有</span>' : '<span class="bad">缺</span>') + "</td><td>" +
        (d.manifest_status === 200 ? '<span class="ok">200</span>' : (d.index_gids > 0 ? "回退(" + d.index_gids + ")" : '<span class="bad">' + d.manifest_status + "</span>")) +
        "</td><td>" + (d.size / 1048576).toFixed(1) + " MB</td></tr>");
    }
    $("storeDepots").innerHTML = rows.join("");
    $("storeStart").disabled = !report.downloadable;
  } catch (err) { $("storeVerdict").textContent = "检查失败：" + err; }
}

async function storeStartDownload() {
  if (!storeSelected) return;
  const depotWorkers = Number($("depotWorkers").value) || 2;
  $("storeStart").disabled = true;
  $("fill").style.width = "5%";
  $("taskBadge").textContent = "进行中";
  showPage("tasks");
  log("[store] 下载 " + (storeSelected.name || storeSelected.appid) + " -> " + storeSelected.path);
  try { await app().Restore(storeSelected.appid, storeSelected.path, depotWorkers); }
  catch (err) { log("[store] 失败: " + err); toast("下载启动失败：" + err, "bad"); $("storeStart").disabled = false; }
}

$("storeSearch").addEventListener("click", () => loadStore($("storeQuery").value));
$("storeQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") loadStore($("storeQuery").value); });
$("storeReset").addEventListener("click", () => { $("storeQuery").value = ""; loadStore(""); });
$("storeCheck").addEventListener("click", storeCheck);
$("storeStart").addEventListener("click", storeStartDownload);

(async function boot() {
  log("[boot] 云驿启动");
  await loadSettings();
  const data = await refreshData();
  applyTheme(data.theme || "light");
  renderThemePicker(data.theme || "light");
  applySize(data.fontSize || "standard");
  renderSizePicker(data.fontSize || "standard");
  await loadGames();
  await initSources();
  await loadStore("");
  await syncTarget();
  await checkUpdate();
  if (data.needsData) log("[boot] 缺少数据，请按提示下载");
})();
// Book Builder desktop shell (Electron). tools/package_app.py puts this folder in the app's
// resources/app. It starts the bundled Python server and shows Book Builder in its own window,
// or in your web browser if you chose that in Settings › Preferences.
"use strict";
const { app, BrowserWindow, Menu, shell, dialog } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const os = require("os");
const path = require("path");

app.setName("Book Builder");
const RES = process.resourcesPath;
const WIN = process.platform === "win32";
const PY = WIN ? path.join(RES, "runtime", "python", "python.exe") : path.join(RES, "runtime", "python", "bin", "python3");
const HOME = process.env.BOOK_BUILDER_HOME || path.join(os.homedir(), ".book-builder");
let port = 0;
let server = null;
let win = null;
let quitting = false;
let lastError = "";

if (!app.requestSingleInstanceLock()) app.quit();
app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); } });

function note(msg) {
  try { fs.appendFileSync(path.join(HOME, "logs", "app.log"), `[desktop ${new Date().toISOString()}] ${msg}\n`); } catch { /* no log folder yet */ }
}

const url = (p = "/") => `http://127.0.0.1:${port}${p}`;

function request(method, p, body) {
  const data = body ? JSON.stringify(body) : "";
  return new Promise(resolve => {
    const headers = { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data), Origin: url("") };
    const req = http.request(url(p), { method, timeout: 10000, headers, agent: false }, res => {
      let data = "";
      res.on("data", c => (data += c));
      res.on("end", () => { try { resolve(JSON.parse(data)); } catch { resolve(null); } });
    });
    req.on("error", e => { if (p !== "/api/ping" || port) lastError = `${p}: ${e.code || e.message}`; resolve(null); });
    req.on("timeout", () => { lastError = `${p}: no answer in 10 s`; req.destroy(); resolve(null); });
    req.end(data);
  });
}

function portFree(p) {
  return new Promise(resolve => {
    const s = net.createServer().once("error", () => resolve(false)).once("listening", () => s.close(() => resolve(true)));
    s.listen(p, "127.0.0.1");
  });
}

async function pickPort() {
  for (let p = 8765; p < 8785; p++) if (await portFree(p)) return p;
  throw new Error("No free port between 8765 and 8784.");
}

function startServer() {
  fs.mkdirSync(path.join(HOME, "logs"), { recursive: true });
  const log = fs.openSync(path.join(HOME, "logs", "app.log"), "a");
  server = spawn(PY, [path.join(RES, "bookbuilder", "tools", "start_packaged.py"), "--no-open", "--port", String(port), "--exact-port"], {
    env: { ...process.env, BB_RUNTIME_BIN: path.join(RES, "runtime", "bin"), BB_SAMPLE_BOOK: path.join(RES, "sample-book"),
           BB_PACKAGED: "1", PYTHONDONTWRITEBYTECODE: "1", PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", log, log], windowsHide: true,
  });
}

async function waitForServer(seconds) {
  for (let i = 0; i < seconds * 4; i++) {
    const r = await request("GET", "/api/ping");
    if (r) return true;
    await new Promise(r2 => setTimeout(r2, 250));
  }
  return false;
}

// The page's Quit button stops the server; the window follows. Switching books restarts the
// server for a moment, so only a long silence counts.
function watchServer() {
  let misses = 0;
  setInterval(async () => {
    if (quitting) return;
    const ok = await request("GET", "/api/ping");
    if (!ok) note(`Ping failed (${misses + 1}): ${lastError}`);
    misses = ok ? 0 : misses + 1;
    if (misses >= 6) { note("The server stopped answering; closing."); quitting = true; app.quit(); }
  }, 2500);
}

function openInBrowser() { shell.openExternal(url(win ? new URL(win.webContents.getURL() || url()).pathname : "/")); }

function isLocal(u) { try { const x = new URL(u); return x.hostname === "127.0.0.1" && Number(x.port) === port; } catch { return false; } }

function makeWindow(page) {
  win = new BrowserWindow({ width: 1320, height: 900, minWidth: 900, minHeight: 600, title: "Book Builder", show: false,
                            webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true } });
  if (!process.env.BB_HIDE_WINDOW) win.once("ready-to-show", () => win.show());   // hidden only for automated tests
  win.on("closed", () => { win = null; });
  win.webContents.on("render-process-gone", (_e, d) => note(`Page process ended: ${d.reason} (${d.exitCode})`));
  win.webContents.on("unresponsive", () => note("Page stopped responding."));
  // Links to other sites open in the browser; Book Builder's own pages (previews, downloads) stay here.
  win.webContents.setWindowOpenHandler(({ url: u }) => {
    if (isLocal(u)) return { action: "allow" };
    shell.openExternal(u);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, u) => { if (!isLocal(u) && !u.startsWith("data:")) { e.preventDefault(); shell.openExternal(u); } });
  win.loadURL(page);
}

function browserModeWindow() {
  const html = `<!doctype html><meta charset="utf-8"><title>Book Builder</title>
  <style>body{font:15px -apple-system,Segoe UI,sans-serif;margin:28px;color:#222;background:#fafafa}button{font:inherit;margin:6px 8px 0 0;padding:7px 14px}</style>
  <h2 style="margin-top:0">Book Builder is running in your browser</h2>
  <p>Keep this window open while you work. Closing it stops Book Builder.</p>
  <p><a href="${url()}" target="_blank">${url()}</a></p>`;
  makeWindow("data:text/html;charset=utf-8," + encodeURIComponent(html));
  win.setSize(520, 260);
  win.center();
}

function buildMenu() {
  const mac = process.platform === "darwin";
  const template = [
    ...(mac ? [{ role: "appMenu" }] : []),
    { label: "File", submenu: [
      { label: "Open in Browser", accelerator: "CmdOrCtrl+Shift+B", click: openInBrowser },
      { label: "Show Logs", click: () => shell.openPath(path.join(HOME, "logs")) },
      { type: "separator" },
      mac ? { role: "close" } : { role: "quit" },
    ] },
    { role: "editMenu" },
    { label: "View", submenu: [{ role: "reload" }, { type: "separator" }, { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" },
                               { type: "separator" }, { role: "togglefullscreen" }, { role: "toggleDevTools" }] },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(async () => {
  buildMenu();
  try {
    port = await pickPort();
    startServer();
    if (!(await waitForServer(60))) throw new Error("The Book Builder server didn't start.");
  } catch (e) {
    dialog.showErrorBox("Book Builder couldn't start", `${e.message}\n\nDetails are in ${path.join(HOME, "logs", "app.log")}`);
    quitting = true;
    if (server) server.kill();
    app.quit();
    return;
  }
  note(`Server ready on port ${port}.`);
  const info = await request("GET", "/api/app");
  if (info && info.settings && info.settings.openIn === "browser") {
    shell.openExternal(url());
    browserModeWindow();
  } else {
    makeWindow(url());
  }
  watchServer();
});

app.on("child-process-gone", (_e, d) => note(`${d.type} process ended: ${d.reason} (${d.exitCode})`));
app.on("window-all-closed", () => { note("Window closed; quitting."); app.quit(); });
app.on("activate", () => { if (!win && port) makeWindow(url()); });
app.on("before-quit", e => {
  if (!server || server.exitCode !== null || server.__stopping) return;
  e.preventDefault();
  quitting = true;
  server.__stopping = true;
  request("POST", "/api/quit", {}).then(() => setTimeout(() => { try { server.kill(); } catch { /* already gone */ } app.quit(); }, 800));
});

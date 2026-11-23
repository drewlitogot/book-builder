// Book Builder: application shell (navigation, Library, project dashboards and management pages).
// Loaded after the main page script; reuses its helpers ($, $$, esc, api, toast, busy, ask, ic, S,
// store, showView, go, byN, num, chName, pill, tourStart, promptPack, load).
// Existing workflows (Chapter, Batch, Build, Games, Website, Git, Workspace, Help) are reused as
// sub-pages; nothing here changes how they work.
"use strict";

// ---------------------------------------------------------------- navigation definitions
// One place for every menu, sub-page and icon. `view` reuses an existing screen; otherwise the
// page renderer in PAGES with the key "section/sub" draws into #v-page.
const APP_NAV = [
  { id: "library", label: "Library", icon: "library-big", subs: [
    ["all", "All Books", "library"], ["recent", "Recent", "clock-3"], ["archived", "Archived", "archive"]] },
  { id: "new", label: "New Book", icon: "circle-plus", subs: [
    ["blank", "Blank Project", "file-plus"], ["template", "From Template", "layout-template"], ["import", "Import Project", "folder-input"]] },
  { id: "templates", label: "Templates", icon: "layout-template", subs: [
    ["book", "Book Templates", "book-copy"], ["brand", "Brand Templates", "palette"], ["prompt", "Prompt Templates", "message-square"]] },
  { id: "activity", label: "Activity", icon: "history", subs: [
    ["changes", "Recent Changes", "list-checks"], ["approvals", "Approvals", "circle-check"], ["builds", "Build History", "package-check"]] },
  { id: "settings", label: "Settings", icon: "settings-2", subs: [
    ["ai", "AI Providers", "bot"], ["integrations", "Integrations", "github"], ["storage", "Storage", "folder"],
    ["preferences", "Preferences", "sliders-horizontal"], ["privacy", "Privacy", "shield"], ["trash", "Trash", "trash-2"]] },
];
const PROJECT_NAV = [
  { id: "overview", label: "Overview", icon: "layout-dashboard", key: "1", subs: [
    ["dashboard", "Dashboard", "house"], ["statistics", "Statistics", "chart-column"], ["health", "Book Health", "heart-pulse"],
    ["checklist", "Release Checklist", "list-checks"], ["details", "Book Details", "info"]] },
  { id: "chapters", label: "Chapters", icon: "file-text", key: "2", sidebar: "chapters", subs: [
    ["list", "Chapter List", "list-tree"], ["editor", "Editor", "file-pen-line", "chapter"], ["reorder", "Reorder", "arrow-up-down"],
    ["revisions", "Revisions", "git-compare"], ["approvals", "Approvals", "check-check"]] },
  { id: "research", label: "Research", icon: "search-check", key: "3", subs: [
    ["sources", "Source Library", "library"], ["bibliography", "Bibliography", "book-marked"], ["audit", "Citation Audit", "scan-search"],
    ["gaps", "Evidence Gaps", "file-warning"], ["import", "Import Sources", "upload"]] },
  { id: "ai", label: "AI Studio", icon: "bot", key: "4", sidebar: "chapters", subs: [
    ["prompts", "Prompt Generator", "wand-sparkles", "workspace"], ["batch", "Batch Operations", "layers", "batch"],
    ["review", "AI Review", "clipboard-check"], ["workflows", "Workflows", "workflow"], ["handoff", "ChatGPT Handoff", "message-square", "workspace"],
    ["saved", "Saved Prompts", "file-text"]] },
  { id: "design", label: "Design", icon: "palette", key: "5", subs: [
    ["brand", "Brand Kit", "swatch-book"], ["fonts", "Fonts", "type"], ["graphics", "Graphics", "image"],
    ["layout", "Interior Layout", "book-open"], ["previews", "Previews", "scan-eye"], ["images", "Image Prompts", "sparkles"]] },
  { id: "build", label: "Build", icon: "hammer", key: "6", subs: [
    ["settings", "Build Settings", "settings-2", "build"], ["pdf", "PDF", "file-type"], ["epub", "EPUB", "book-text"], ["docx", "DOCX", "file"],
    ["export", "Export Center", "download"], ["kindle", "Send to Kindle", "mail"], ["history", "Build History", "history"],
    ["git", "Save Work", "git-commit-horizontal", "git"]] },
  { id: "website", label: "Website", icon: "globe", key: "7", subs: [
    ["preview", "Site Preview", "monitor", "website"], ["layout", "Layout", "layout-template"], ["pages", "GitHub Pages", "github", "website"],
    ["hosting", "Custom Hosting", "server"], ["domain", "Domain", "link"], ["zip", "Website ZIP", "package"], ["publish", "Publish", "rocket", "website"]] },
  { id: "interactive", label: "Interactive", icon: "gamepad-2", key: "8", subs: [
    ["games", "Games", "gamepad-2", "games"], ["quizzes", "Quizzes", "list-checks"], ["activities", "Activities", "puzzle"],
    ["config", "Configuration", "sliders-horizontal"], ["preview", "Preview", "eye", "games"]] },
];
// Old view names (shortcuts, tutorial, links in existing screens) → new locations.
const LEGACY = { "research-library": ["research", "sources"], "brand-studio": ["design", "brand"], "image-studio": ["design", "images"], "new-book": ["new", "blank"], overview: ["overview", "dashboard"], chapter: ["chapters", "editor"], batch: ["ai", "batch"],
  build: ["build", "settings"], games: ["interactive", "games"], website: ["website", "publish"],
  workspace: ["ai", "handoff"], prompts: ["ai", "prompts"], git: ["build", "git"], help: ["help", "help"] };

const BB = { app: null, route: null, cache: {} };
const fmtBytes = b => b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`;
const fmtDate = t => t ? new Date(t * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—";
const bbWhen = t => {
  if (!t) return "—";
  const s = Date.now() / 1000 - t;
  return s < 90 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago`
    : s < 86400 * 14 ? `${Math.round(s / 86400)} days ago` : fmtDate(t);
};
const STATUS_TXT = { pass: "Passed", warn: "Warning", fail: "Failed", unchecked: "Not checked", na: "Not applicable" };
const STATUS_ICON = { pass: "circle-check", warn: "circle-alert", fail: "circle-x", unchecked: "circle-minus", na: "circle-minus" };
const badge = st => `<span class="st st-${st}">${ic(STATUS_ICON[st])}${STATUS_TXT[st]}</span>`;
const link = (sec, sub, label) => `<a href="#/p/${sec}/${sub}" class="nav-link">${esc(label)}</a>`;
const planned = (what, need) => `<div class="planned">${ic("info")}<div><b>Not available yet.</b> ${what}<div class="muted-note">${need}</div></div></div>`;
async function data(name, fresh = false) {
  if (fresh || !BB.cache[name]) BB.cache[name] = await api(`/api/insights/${name}`);
  return BB.cache[name];
}
const projectPath = () => BB.app?.project;
const openedHere = () => store.get("openProject", null) === projectPath();

// ---------------------------------------------------------------- routing
function parseHash() {
  const m = location.hash.match(/^#\/(a|p|u)\/([\w-]+)\/([\w-]+)/);
  return m ? { scope: m[1], sec: m[2], sub: m[3] } : null;
}
function navFor(scope) { return scope === "a" ? APP_NAV : PROJECT_NAV; }
function bbGo(sec, sub, scope) {
  if (sec === "help") return setHash("u", "help", "help");
  scope = scope || (APP_NAV.some(n => n.id === sec) ? "a" : "p");
  const nav = navFor(scope).find(n => n.id === sec) || navFor(scope)[0];
  sub = sub && nav.subs.some(s => s[0] === sub) ? sub : nav.subs[0][0];
  setHash(scope, nav.id, sub);
}
function setHash(scope, sec, sub) {
  const h = `#/${scope}/${sec}/${sub}`;
  if (location.hash === h) bbRender(); else location.hash = h;
}
window.addEventListener("hashchange", () => bbRender());

function bbRender() {
  let r = parseHash();
  if (!r) r = openedHere() ? { scope: "p", sec: "overview", sub: "dashboard" } : { scope: "a", sec: "library", sub: "all" };
  if (r.scope === "p" && !openedHere()) r = { scope: "a", sec: "library", sub: "all" };   // pick a book first
  BB.route = r;
  store.set("route", r);
  const body = document.body.classList;
  body.toggle("lib", r.scope === "a" || r.scope === "u" && !openedHere());
  renderHeader();
  if (r.scope === "u") { renderSubnav(null); setSidebar(null); return showView("help"); }
  const nav = navFor(r.scope).find(n => n.id === r.sec);
  const sub = nav.subs.find(s => s[0] === r.sub) || nav.subs[0];
  renderSubnav(nav, sub);
  revealActiveTab();
  setSidebar(r.scope === "p" ? nav : null);
  if (sub[3]) {
    showView(sub[3]);
    if (sub[3] === "workspace") requestAnimationFrame(() => {
      const target = r.sub === "prompts" ? $("#pk-ch")?.closest(".card") : $("#v-workspace .card");
      target?.scrollIntoView({ block: "start" });
      memoryNote();
    });
  } else {
    showView("page");
  }
}
function renderPage() {
  const r = BB.route, host = $("#v-page");
  const fn = PAGES[`${r.sec}/${r.sub}`];
  // Each visit renders into a fresh container, so a slow page that finishes after you've moved on
  // writes into a detached element instead of over the page you're looking at.
  const el = document.createElement("div");
  host.replaceChildren(el);
  el.innerHTML = `<p class="muted small">Loading…</p>`;
  Promise.resolve(fn ? fn(el) : (el.innerHTML = planned("This page isn't built yet.", ""))).catch(e => {
    el.innerHTML = `<div class="card"><p class="alert bad">Couldn't load this page: ${esc(e.message)}</p></div>`;
  });
}

// ---------------------------------------------------------------- header, sub-navigation, sidebar
function renderHeader() {
  const r = BB.route, inProject = r.scope === "p";
  const cur = BB.app?.library?.find(b => b.path === projectPath());
  $("#proj-sum").innerHTML = `${ic("book-open")}<span class="pname">${esc(inProject || openedHere() ? cur?.title || "Book" : "Choose a book")}</span>`;
  $("#proj-pop").innerHTML = `
    <div class="pop-h">Books</div>
    ${(BB.app?.library || []).filter(b => !b.archived && !b.missing).map(b => `
      <button role="menuitem" data-open="${esc(b.path)}" class="${b.path === projectPath() && openedHere() ? "on" : ""}">${ic("book-open")}${esc(b.title)}</button>`).join("")}
    <hr><button role="menuitem" data-go="library/all">${ic("library-big")}Library</button>
    <button role="menuitem" data-go="new/blank">${ic("circle-plus")}New book</button>`;
  $$("#proj-pop [data-open]").forEach(b => b.onclick = () => openProject(b.dataset.open));
  $$("#proj-pop [data-go]").forEach(b => b.onclick = () => { $("#proj").open = false; const [s, u] = b.dataset.go.split("/"); bbGo(s, u, "a"); });
  const nav = inProject ? PROJECT_NAV : APP_NAV;
  $("#views").innerHTML = nav.map(n => `
    <button data-sec="${n.id}" class="${n.id === r.sec ? "on" : ""}" title="${esc(n.label)}${n.key ? ` (${n.key})` : ""}" aria-current="${n.id === r.sec ? "page" : "false"}">
      ${ic(n.icon)}<span class="full">${esc(n.label)}</span></button>`).join("");
  $$("#views [data-sec]").forEach(b => b.onclick = () => bbGo(b.dataset.sec, null, inProject ? "p" : "a"));
  $("#topprog").classList.toggle("hidden", !inProject);
  $("#app-settings").classList.toggle("on", r.scope === "a" && r.sec === "settings");
}
function renderSubnav(nav, sub) {
  const r = BB.route, el = $("#subnav");
  const cur = BB.app?.library?.find(b => b.path === projectPath());
  const crumbs = [`<a href="#/a/library/all">Book Builder</a>`];
  if (r.scope === "p") crumbs.push(`<a href="#/a/library/all">Library</a>`, `<span>${esc(cur?.title || "Book")}</span>`);
  else if (r.scope === "u") crumbs.push(`<span>Help</span>`);
  else crumbs.push(`<span>${esc(nav.label)}</span>`);
  el.innerHTML = `<nav class="crumbs" aria-label="Breadcrumb">${crumbs.join(`<span class="sep">›</span>`)}</nav>
    ${nav ? `<nav class="subs" aria-label="${esc(nav.label)} pages">${nav.subs.map(s => `
      <a href="#/${r.scope}/${nav.id}/${s[0]}" class="${s[0] === sub[0] ? "on" : ""}" aria-current="${s[0] === sub[0] ? "page" : "false"}" title="${esc(s[1])}">${ic(s[2])}<span>${esc(s[1])}</span></a>`).join("")}</nav>` : ""}`;
}
function revealActiveTab() {
  const subs = $("#subnav .subs"), on = subs?.querySelector("a.on");
  if (subs && on && subs.scrollWidth > subs.clientWidth) subs.scrollLeft = Math.max(0, on.offsetLeft - subs.offsetLeft - 24);
}
function setSidebar(nav) {
  const mode = !nav ? "none" : nav.sidebar === "chapters" ? "chapters" : "ctx";
  document.body.dataset.side = mode;
  if (mode === "ctx") renderCtx(nav);
}
async function renderCtx(nav) {
  const el = $("#ctx");
  const cur = BB.app?.library?.find(b => b.path === projectPath());
  const subs = nav.subs.map(s => `<a href="#/p/${nav.id}/${s[0]}" class="${BB.route.sub === s[0] ? "on" : ""}">${ic(s[2])}${esc(s[1])}</a>`).join("");
  let extra = "";
  if (nav.id === "overview" && cur) {
    extra = `<div class="ctx-book">${cur.cover ? `<img src="/pfile/${esc(cur.cover)}" alt="Cover of ${esc(cur.title)}">` : `<div class="cover-ph">${ic("book-open")}</div>`}
      <div><b>${esc(cur.title)}</b><div class="muted-note">${esc(cur.author)}</div><div class="muted-note">${cur.counts.approved}/${cur.counts.total} approved</div></div></div>`;
  } else if (nav.id === "build") {
    const a = await data("activity").catch(() => null);
    // Latest build of each format (newest first): file name, build time, whether chapters changed since.
    const seen = new Set(), latest = (a?.outputs || []).filter(o => o.current && !seen.has(o.format) && seen.add(o.format));
    extra = `<div class="ctx-h">Latest files</div>${latest.map(o => `<div class="ctx-file" title="${esc(o.name)} · ${fmtBytes(o.bytes)} · built ${new Date(o.mtime * 1000).toLocaleString()}">
        <span class="fmt">${esc(o.format)}</span><span class="${o.stale ? "st st-warn" : "muted-note"}">${o.stale ? "out of date" : bbWhen(o.mtime)}</span>
        <button class="sm ghost" data-open-file="${esc(o.path)}" aria-label="Open ${esc(o.name)}" title="Open ${esc(o.name)}">${ic("external-link")}</button>
        <span class="fname">${esc(o.name)}${o.stale ? ` · ${bbWhen(o.mtime)}` : ""}</span></div>`).join("") || `<p class="muted-note" style="padding:0 8px">Nothing built yet.</p>`}
      ${(a?.outputs || []).length > latest.length ? `<a class="ctx-more" href="#/p/build/history">All files (${a.outputs.length})</a>` : ""}`;
  } else if (nav.id === "research") {
    const r = await data("research").catch(() => null);
    if (r) extra = `<div class="ctx-h">Evidence</div>
      <div class="ctx-row"><span>Bibliography</span><b>${r.bib.entries.length}</b></div>
      <div class="ctx-row"><span>Missing keys</span><b>${r.missingKeys.length}</b></div>
      <div class="ctx-row"><span>Open gaps</span><b>${r.gaps.length}</b></div>
      <div class="ctx-row"><span>Source files</span><b>${r.sources.count}</b></div>`;
  } else if (nav.id === "design") {
    const b = await data("brand").catch(() => null);
    if (b?.exists) extra = `<div class="ctx-h">Book fonts</div>${Object.entries(b.fonts).map(([k, v]) => `<div class="ctx-row"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("")}
      <div class="ctx-h">Colors</div><div class="swatches">${Object.entries(b.colors).map(([k, v]) => `<span title="${esc(k)} ${v}" style="background:${v}"></span>`).join("")}</div>`;
  }
  el.innerHTML = `<nav class="ctx-nav" aria-label="${esc(nav.label)}">${subs}</nav>${extra}`;
  wireOpen(el);
}
function memoryNote() {
  const box = $("#ws-memory");
  if (box) box.classList.toggle("hidden", !S?.memoryStale);
}

// ---------------------------------------------------------------- projects
async function loadApp() {
  BB.app = await api("/api/app");
  document.title = BB.route?.scope === "p" ? `${BB.app.library.find(b => b.path === projectPath())?.title || "Book"} · Book Builder` : "Book Builder";
  const th = BB.app.settings.theme;
  if (!store.get("theme", null) && th !== "system") document.documentElement.dataset.theme = th;
  document.body.classList.toggle("compact", BB.app.settings.density === "compact");
  document.body.classList.toggle("expert", BB.app.settings.guidance === false);
}
async function openProject(path) {
  $("#proj").open = false;
  if (path === projectPath()) {
    await api("/api/projects/open", { path });
    store.set("openProject", path);
    return bbGo("overview", "dashboard", "p");
  }
  const r = await api("/api/projects/open", { path });
  if (!r.ok) return toast(r.message, "bad", 6000);
  store.set("openProject", path);
  store.set("route", null);
  $("#busytext").textContent = "Opening the book…"; $("#busy").classList.remove("hidden");
  for (let i = 0; i < 60; i++) {           // the server restarts on the other project
    await new Promise(res => setTimeout(res, 400));
    try { const a = await (await fetch("/api/app")).json(); if (a.project === path) { location.hash = "#/p/overview/dashboard"; location.reload(); return; } } catch { /* restarting */ }
  }
  $("#busy").classList.add("hidden");
  toast("The book didn't open in time. Refresh the page.", "bad", 8000);
}

function bookCard(b, compact = false) {
  const pct = b.counts?.total ? Math.round(b.counts.approved / b.counts.total * 100) : 0;
  const isOpen = b.path === projectPath() && openedHere();
  return `<article class="book ${b.missing ? "missing" : ""}">
    <button class="cover" data-open="${esc(b.path)}" ${b.missing ? "disabled" : ""} aria-label="Open ${esc(b.title)}">
      ${b.cover && b.path === projectPath() ? `<img src="/pfile/${esc(b.cover)}" alt="">` : `<span class="cover-ph">${ic("book-open")}<span>${esc(b.title)}</span></span>`}</button>
    <div class="book-body">
      <div class="book-t">${esc(b.title)}</div>
      <div class="muted-note">${esc(b.author || "")}</div>
      ${b.missing ? `<p class="alert bad small">Folder not found: ${esc(b.path)}</p>` : `
      <div class="bk-meta"><span class="chip-s">${esc(b.status)}</span>${isOpen ? `<span class="chip-s on">Open</span>` : ""}</div>
      <div class="miniprog" title="${b.counts.approved} of ${b.counts.total} approved"><span style="width:${pct}%"></span></div>
      <div class="muted-note">${b.counts.approved}/${b.counts.total} chapters approved · edited ${bbWhen(b.modified)}</div>`}
      ${compact ? "" : `<div class="row">
        <button class="primary sm" data-open="${esc(b.path)}" ${b.missing ? "disabled" : ""}>${ic("book-open")}Open</button>
        <details class="menu"><summary class="sm" aria-label="Actions for ${esc(b.title)}">${ic("ellipsis")}</summary><div class="pop" role="menu">
          <button role="menuitem" data-export="${esc(b.path)}">Export book…</button>
          <button role="menuitem" data-reveal="${esc(b.path)}">Show folder path</button>
          <button role="menuitem" data-archive="${esc(b.path)}" data-v="${b.archived ? "0" : "1"}">${b.archived ? "Unarchive" : "Archive"}</button>
          ${b.home || b.path === projectPath() ? "" : `<button role="menuitem" class="danger" data-forget="${esc(b.path)}">Remove from Library</button>
          <button role="menuitem" class="danger" data-delbook="${esc(b.path)}" data-title="${esc(b.title)}">Delete book…</button>`}
        </div></details></div>`}
    </div></article>`;
}
function wireBooks(root) {
  $$("[data-open]", root).forEach(b => b.onclick = () => openProject(b.dataset.open));
  $$("[data-export]", root).forEach(b => b.onclick = () => exportBook(b.dataset.export));
  $$("[data-reveal]", root).forEach(b => b.onclick = () => ask(`<h3>Project folder</h3><p><code>${esc(b.dataset.reveal)}</code></p>`, [["Close", null]]));
  $$("[data-archive]", root).forEach(b => b.onclick = async () => {
    await api("/api/projects/archive", { path: b.dataset.archive, archived: b.dataset.v === "1" });
    await loadApp(); bbRender();
  });
  $$("[data-delbook]", root).forEach(b => b.onclick = async () => {
    if (!await ask(`<h3>Delete “${esc(b.dataset.title)}”?</h3><p>The whole book folder moves to Book Builder's Trash: chapters, drafts, research, images and outputs.</p>
      <p><code>${esc(b.dataset.delbook)}</code></p><p>You can restore it from Settings › Trash until you empty the Trash.</p>`,
      [["Cancel", false], ["Delete book", true, "danger"]])) return;
    const r = await api("/api/projects/delete", { path: b.dataset.delbook, confirm: true });
    toast(r.message, r.ok ? "good" : "bad"); await loadApp(); bbRender();
  });
  $$("[data-forget]", root).forEach(b => b.onclick = async () => {
    if (await ask(`<h3>Remove from the Library?</h3><p>The folder and its files are not deleted. You can import it again later.</p>`, [["Cancel", false], ["Remove", true, "danger"]])) {
      const r = await api("/api/projects/forget", { path: b.dataset.forget }); toast(r.message, r.ok ? "good" : "bad"); await loadApp(); bbRender();
    }
  });
}

// ---------------------------------------------------------------- pages
const PAGES = {};
const card = (title, body, extra = "") => `<div class="card"><div class="sec-h"><h3>${title}</h3>${extra}</div>${body}</div>`;

// ---- Library
PAGES["library/all"] = async el => {
  await loadApp();
  const books = BB.app.library.filter(b => !b.archived);
  const recent = [...books].filter(b => b.lastOpened).sort((a, b) => b.lastOpened - a.lastOpened)[0] || books.find(b => b.path === projectPath());
  const tpls = Object.entries(BB.app.templates);
  let act = null;
  try { act = await data("activity"); } catch { /* optional */ }
  el.innerHTML = `
    <div class="page-h"><h2>Library</h2><span class="grow"></span><button class="primary" id="lib-new">${ic("circle-plus")}New book</button></div>
    ${recent ? card("Continue working", `<div class="continue">${bookCard(recent, true)}
      <div><p style="margin-top:0"><b>${esc(recent.title)}</b> · last opened ${bbWhen(recent.lastOpened)}</p>
      <p class="muted-note">Next: ${recent.counts && recent.counts.approved < recent.counts.total ? "keep drafting and approving chapters" : "check Book Health, then build and publish"}.</p>
      <button class="primary" data-open="${esc(recent.path)}">${ic("book-open")}Open project</button></div></div>`) : ""}
    ${card(`My books <span class="small muted">${books.length}</span>`, `<div class="books">${books.map(b => bookCard(b)).join("")}</div>`)}
    <div class="grid2">
      ${card("Create a new book", `<div class="tiles">
        <a class="tile" href="#/a/new/blank">${ic("file-plus")}<b>Blank project</b><span>An empty outline to shape yourself.</span></a>
        <a class="tile" href="#/a/new/template">${ic("layout-template")}<b>From a template</b><span>Fiction, nonfiction, academic and more.</span></a>
        <a class="tile" href="#/a/new/import">${ic("folder-input")}<b>Import a project</b><span>Add a folder that has a book.yml.</span></a></div>`)}
      ${card("Recent activity", act && act.commits.length ? `<ul class="feed">${act.commits.slice(0, 6).map(c => `<li><span class="muted-note">${bbWhen(c.time)}</span> ${esc(c.subject)}</li>`).join("")}</ul>
        <p class="muted-note">From the open book's git history. ${link("", "", "")}</p>` : `<p class="muted-note">No recorded activity yet. Activity comes from each book's git history and build files.</p>`)}
    </div>
    ${card("Templates", `<div class="tiles">${tpls.map(([k, t]) => `<a class="tile" href="#/a/new/template" data-tpl="${k}">${ic(t.icon)}<b>${esc(t.name)}</b><span>${esc(t.desc)}</span></a>`).join("")}</div>
      <p class="muted-note">Templates are starting points: they set the first outline and folders. You can change everything afterwards.</p>`)}`;
  el.querySelector(".feed + p")?.remove();
  wireBooks(el);
  $("#lib-new").onclick = () => bbGo("new", "blank", "a");
  $$("[data-tpl]", el).forEach(a => a.onclick = () => store.set("tpl", a.dataset.tpl));
};
PAGES["library/recent"] = async el => {
  await loadApp();
  const books = BB.app.library.filter(b => b.lastOpened).sort((a, b) => b.lastOpened - a.lastOpened);
  el.innerHTML = `<div class="page-h"><h2>Recent</h2></div>${card("Recently opened", books.length ? `<div class="books">${books.map(b => bookCard(b)).join("")}</div>` : `<p class="muted-note">No book has been opened from the Library yet.</p>`)}`;
  wireBooks(el);
};
PAGES["library/archived"] = async el => {
  await loadApp();
  const books = BB.app.library.filter(b => b.archived);
  el.innerHTML = `<div class="page-h"><h2>Archived</h2></div>${card("Archived books", books.length ? `<div class="books">${books.map(b => bookCard(b)).join("")}</div>` : `<p class="muted-note">Nothing archived. Archive a book from its ⋯ menu to hide it from the Library without deleting anything.</p>`)}`;
  wireBooks(el);
};

// ---- Full-book export / import (tools/bookpack.py)
async function exportBook(path) {
  const priv = await ask(`<h3>Export the whole book</h3><p>One ZIP with everything needed to open and rebuild this book elsewhere: chapters, drafts, reviews, research, the Research Library, prompts, games, branding, build templates and settings. Builds, git history and Book Builder itself are left out.</p>
    <p>Include <code>sources-private/</code> (private copies of copyrighted sources)? Only do this if the ZIP stays with you.</p>`, [["Cancel", null], ["Export without private sources", false, "primary"], ["Include them", true]]);
  if (priv === null) return;
  const r = await busy("Exporting the book…", () => api("/api/projects/export", { path, private: priv }));
  if (!r.ok) return toast(r.message, "bad", 7000);
  location.href = r.download;
  toast(`Exported “${r.title}”: ${r.files} files, ${fmtBytes(r.bytes)}. The ZIP is downloading (a copy stays in the book's dist/book-exports/).`, "good", 9000);
}

// ---- New book
// Create Book wizard: identity → direction → brand → graphics → structure → outputs → finish.
// Everything except the title is optional and can be changed later.
const WZ_STEPS = ["Identity", "Direction", "Brand", "Graphics", "Structure", "Outputs", "Finish"];
function wizardDefaults(tpl) {
  const t = BB.app.templates[tpl] || BB.app.templates.custom;
  return { step: 0, template: tpl, title: "", subtitle: "", author: "", lang: "en-US", description: "", subject: t.name, audience: "", keywords: "",
           brand: { accent: "#2f6db3", titleFont: BB.app.settings.defaultFonts.title, bodyFont: BB.app.settings.defaultFonts.body, mood: "" },
           cover: null, parts: (t.parts || [["Part one", ["First chapter"]]]).map(([name, chs]) => ({ name, chapters: [...chs] })),
           formats: ["pdf", "epub"], folder: "" };
}
function newForm(el, mode) {
  const tplKey = store.get("tpl", mode === "blank" ? "custom" : "nonfiction");
  if (!BB.wz || BB.wz.mode !== mode) BB.wz = { mode, ...wizardDefaults(mode === "blank" ? "custom" : tplKey) };
  const w = BB.wz, tpls = Object.entries(BB.app.templates);
  const field = (id, label, val, hint = "", area = false) => `<label for="wz-${id}">${label}</label>${area ? `<textarea id="wz-${id}" rows="3" style="font-family:inherit">${esc(val)}</textarea>` : `<input id="wz-${id}" value="${esc(val)}">`}<span class="muted-note">${hint}</span>`;
  const steps = [
    () => `<div class="bkform">${field("title", "Title", w.title, "Required. You can change it later in Book Details.")}${field("subtitle", "Subtitle", w.subtitle)}${field("author", "Author or imprint", w.author, "A person, pen name or publishing name.")}${field("lang", "Language", w.lang, "A code such as en-US.")}</div>`,
    () => `${mode === "template" ? `<div class="tiles">${tpls.map(([k, x]) => `<label class="tile pick"><input type="radio" name="wz-tpl" value="${k}" ${k === w.template ? "checked" : ""}>${ic(x.icon)}<b>${esc(x.name)}</b><span>${esc(x.desc)}</span></label>`).join("")}</div>` : ""}
      <div class="bkform" style="margin-top:12px">${field("subject", "Genre or category", w.subject)}${field("audience", "Intended audience", w.audience)}${field("description", "Short description", w.description, "", true)}${field("keywords", "Keywords", w.keywords, "Separate with commas.")}</div>`,
    () => `<p class="muted-note" style="margin-top:0">A starting point for the book's look (book outputs only, never the Book Builder interface). Saved as a placeholder; refine it later in Design.</p>
      <div class="bkform"><label for="wz-accent">Accent color</label><input type="color" id="wz-accent" value="${esc(w.brand.accent)}"><span></span>
      ${field("titleFont", "Title font", w.brand.titleFont, "Any Google Fonts family; install it later in Design › Fonts.")}${field("bodyFont", "Body font", w.brand.bodyFont)}${field("mood", "Mood or vibe", w.brand.mood, "For example: warm, calm, practical.")}</div>`,
    () => `<p class="muted-note" style="margin-top:0">Optional. A front cover (JPEG or PNG). Other graphics can be added later.</p>
      <div class="row"><label class="btn" for="wz-cover">${ic("image")}${w.cover ? "Replace cover" : "Choose a cover"}</label><input type="file" id="wz-cover" accept=".jpg,.jpeg,.png" class="hidden">
      ${w.cover ? `<span class="muted-note">${esc(w.cover.name)}</span><button class="ghost sm" id="wz-nocover">Remove</button>` : `<span class="muted-note">No cover yet: a placeholder is used.</span>`}</div>`,
    () => `<p class="muted-note" style="margin-top:0">Parts and chapters for the outline. Reorder or rename any time in Chapters › Reorder.</p><div id="wz-parts">${w.parts.map((pt, i) => `
      <div class="wz-part"><div class="row"><input data-pn="${i}" value="${esc(pt.name)}" aria-label="Part ${i + 1} name" class="grow"><button class="ghost sm" data-prm="${i}" ${w.parts.length < 2 ? "disabled" : ""}>Remove part</button></div>
      <ol>${pt.chapters.map((c, j) => `<li><input data-cn="${i}:${j}" value="${esc(c)}" aria-label="Chapter title"><button class="ghost sm" data-crm="${i}:${j}" aria-label="Remove chapter" ${pt.chapters.length < 2 ? "disabled" : ""}>${ic("x")}</button></li>`).join("")}</ol>
      <button class="sm" data-cadd="${i}">${ic("plus")}Add chapter</button></div>`).join("")}</div><button class="sm" id="wz-padd">${ic("plus")}Add part</button>`,
    () => `<p class="muted-note" style="margin-top:0">Formats this book will usually build. The website stays <b>off</b> for a new book until you set it up on purpose.</p>
      <div class="row">${["pdf", "epub", "docx", "html"].map(f => `<label class="chk"><input type="checkbox" data-fmt="${f}" ${w.formats.includes(f) ? "checked" : ""}> ${f.toUpperCase()}</label>`).join("")}</div>
      <div class="bkform" style="margin-top:12px">${field("folder", "Folder", w.folder, `Leave empty for ${esc(BB.app.settings.projectsDir)}/&lt;title&gt;. Must be new or empty, and not inside another book.`)}</div>`,
    () => `<table class="tbl"><tbody>
      <tr><th>Title</th><td>${esc(w.title) || `<span class="st st-fail">missing</span>`}${w.subtitle ? `: ${esc(w.subtitle)}` : ""}</td></tr>
      <tr><th>Author</th><td>${esc(w.author || "Author name")}</td></tr><tr><th>Template</th><td>${esc(BB.app.templates[w.template]?.name || "")}</td></tr>
      <tr><th>Structure</th><td>${w.parts.length} part(s), ${w.parts.reduce((a, x) => a + x.chapters.filter(Boolean).length, 0)} chapter(s)</td></tr>
      <tr><th>Brand</th><td><span class="swatch" style="background:${esc(w.brand.accent)}"></span> ${esc(w.brand.titleFont)} / ${esc(w.brand.bodyFont)}</td></tr>
      <tr><th>Cover</th><td>${w.cover ? esc(w.cover.name) : "placeholder"}</td></tr><tr><th>Outputs</th><td>${w.formats.map(f => f.toUpperCase()).join(", ")} · website off</td></tr>
      <tr><th>Folder</th><td>${esc(w.folder || BB.app.settings.projectsDir + "/…")}</td></tr></tbody></table>
      <p class="muted-note">Creates the book's own folder with book.yml, an outline, placeholder chapters, build templates and fonts. Nothing else on your computer changes.</p>`,
  ];
  el.innerHTML = `<div class="page-h"><h2>${mode === "blank" ? "New book" : "New book from a template"}</h2><span class="grow"></span><button class="linkbtn guide-btn" id="wz-tour">Guide me</button></div>
    <ol class="wz-steps">${WZ_STEPS.map((s, i) => `<li class="${i === w.step ? "on" : i < w.step ? "done" : ""}"><button data-go="${i}" ${i > w.step + 1 || (i > 0 && !w.title.trim() && i > w.step) ? "disabled" : ""}>${i + 1}. ${s}</button></li>`).join("")}</ol>
    ${card(WZ_STEPS[w.step], steps[w.step]())}
    <div class="row"><button id="wz-back" ${w.step === 0 ? "disabled" : ""}>Back</button><span class="grow"></span>
      ${w.step < WZ_STEPS.length - 1 ? `${w.step > 0 ? `<button class="ghost" id="wz-skip">Skip</button>` : ""}<button class="primary" id="wz-next">Next</button>` : `<button class="primary" id="wz-go">${ic("book-plus")}Create book</button>`}</div>`;
  const collect = () => {
    const v = id => $(`#wz-${id}`)?.value;
    ["title", "subtitle", "author", "lang", "subject", "audience", "description", "keywords", "folder"].forEach(k => { if (v(k) !== undefined) w[k] = v(k); });
    if ($("#wz-accent")) Object.assign(w.brand, { accent: v("accent"), titleFont: v("titleFont"), bodyFont: v("bodyFont"), mood: v("mood") });
    const tp = el.querySelector("input[name=wz-tpl]:checked"); if (tp && tp.value !== w.template) { const d = wizardDefaults(tp.value); w.template = tp.value; w.parts = d.parts; if (!w.subject || BB.app.templates[w.template]) w.subject = BB.app.templates[tp.value].name; }
    $$("[data-pn]", el).forEach(i => w.parts[+i.dataset.pn].name = i.value);
    $$("[data-cn]", el).forEach(i => { const [a, b] = i.dataset.cn.split(":").map(Number); w.parts[a].chapters[b] = i.value; });
    if ($$("[data-fmt]", el).length) w.formats = $$("[data-fmt]", el).filter(c => c.checked).map(c => c.dataset.fmt);
  };
  const go = i => { collect(); if (i > 0 && !w.title.trim()) { w.step = 0; newForm(el, mode); return toast("Give the book a title first.", "bad"); } w.step = i; newForm(el, mode); };
  $("#wz-tour").onclick = () => tourStartGroup("wizard");
  $("#wz-back").onclick = () => go(w.step - 1);
  if ($("#wz-next")) $("#wz-next").onclick = () => go(w.step + 1);
  if ($("#wz-skip")) $("#wz-skip").onclick = () => go(w.step + 1);
  $$(".wz-steps [data-go]", el).forEach(b => b.onclick = () => go(+b.dataset.go));
  if ($("#wz-cover")) $("#wz-cover").onchange = async e => { const f = e.target.files[0]; if (!f) return; if (f.size > 20e6) return toast("The cover is larger than 20 MB.", "bad"); collect(); w.cover = { name: f.name, data: await fileToB64(f) }; newForm(el, mode); };
  if ($("#wz-nocover")) $("#wz-nocover").onclick = () => { w.cover = null; newForm(el, mode); };
  $$("[data-cadd]", el).forEach(b => b.onclick = () => { collect(); w.parts[+b.dataset.cadd].chapters.push(""); newForm(el, mode); });
  $$("[data-crm]", el).forEach(b => b.onclick = () => { collect(); const [a, c] = b.dataset.crm.split(":").map(Number); w.parts[a].chapters.splice(c, 1); newForm(el, mode); });
  $$("[data-prm]", el).forEach(b => b.onclick = () => { collect(); w.parts.splice(+b.dataset.prm, 1); newForm(el, mode); });
  if ($("#wz-padd")) $("#wz-padd").onclick = () => { collect(); w.parts.push({ name: `Part ${w.parts.length + 1}`, chapters: ["New chapter"] }); newForm(el, mode); };
  if ($("#wz-go")) $("#wz-go").onclick = async () => {
    collect();
    const parts = w.parts.map(x => ({ name: x.name, chapters: x.chapters.filter(c => c.trim()) })).filter(x => x.name.trim() && x.chapters.length);
    const r = await busy("Creating the book…", () => api("/api/projects/create", { title: w.title, subtitle: w.subtitle, author: w.author, folder: w.folder, template: w.template,
      parts, meta: { lang: w.lang, subject: w.subject, "intended-audience": w.audience, description: w.description, keywords: w.keywords },
      brand: w.brand, cover: w.cover, formats: w.formats }));
    toast(r.message, r.ok ? "good" : "bad", 7000);
    if (!r.ok) return;
    BB.wz = null;
    if (await ask(`<h3>Book created</h3><p>${esc(r.message)}</p><p>Open it now?</p>`, [["Later", false], ["Open it", true, "primary"]])) openProject(r.path);
    else { await loadApp(); bbGo("library", "all", "a"); }
  };
}
PAGES["new/blank"] = async el => { await loadApp(); newForm(el, "blank"); };
PAGES["new/template"] = async el => { await loadApp(); newForm(el, "template"); };
PAGES["new/import"] = async el => {
  el.innerHTML = `<div class="page-h"><h2>Import a project</h2></div>
    ${card("Import a book package (.zip)", `<p>A ZIP made with <b>Export book</b>. It becomes a <b>new, separate book</b> with its own folder and id; publishing starts off. Existing books are never changed.</p>
      <div class="row"><label class="btn primary" for="bk-file">${ic("file-up")}Choose a book ZIP</label><input type="file" id="bk-file" accept=".zip" class="hidden"></div><div id="bk-preview"></div>`)}
    ${card("Add an existing book folder", `
    <p>Type the full path of a folder that contains a <code>book.yml</code>. The folder stays where it is; it's only added to the Library.</p>
    <div class="row"><input id="imp-path" style="flex:1;min-width:280px" placeholder="/Users/you/Books/my-book"><button class="primary" id="imp-go">${ic("folder-input")}Add to Library</button></div>`)}`;
  $("#bk-file").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const r = await busy("Checking the package…", async () => api("/api/projects/import-book/inspect", { name: f.name, data: await fileToB64(f) }));
    const box = $("#bk-preview");
    if (!r.ok) { box.innerHTML = `<p class="alert bad">${esc(r.message)}</p>`; return; }
    const i = r.info;
    box.innerHTML = `<table class="tbl" style="margin-top:10px"><tbody><tr><th>Book</th><td><b>${esc(i.title)}</b></td></tr><tr><th>Exported</th><td>${esc(i.exported || "")} · Book Builder ${esc(i.book_builder || "?")}</td></tr>
      <tr><th>Contents</th><td>${i.files} files, ${i.chapter_files} chapter file(s), ${fmtBytes(i.bytes)}${i.include_private ? " · includes private sources" : ""}</td></tr>
      <tr><th>Checks</th><td>${badge("pass")} safe archive, every checksum matches</td></tr></tbody></table>
      <div class="bkform" style="margin-top:10px"><label for="bk-folder">Folder</label><input id="bk-folder" value="${esc(r.suggested)}"><span class="muted-note">Must be new or empty. A free name is chosen if you leave the suggestion and it's taken.</span></div>
      <div class="row" style="margin-top:10px"><button class="primary" id="bk-go">${ic("book-plus")}Import as a new book</button></div>`;
    $("#bk-go").onclick = async () => {
      const folder = $("#bk-folder").value.trim();
      const x = await busy("Importing…", () => api("/api/projects/import-book/apply", { token: r.token, folder: folder === r.suggested ? "" : folder }));
      toast(x.message, x.ok ? "good" : "bad", 9000);
      if (x.ok && await ask(`<h3>Imported</h3><p>${esc(x.message)}</p><p>Open it now?</p>`, [["Later", false], ["Open it", true, "primary"]])) openProject(x.path);
      else if (x.ok) { await loadApp(); bbGo("library", "all", "a"); }
    };
  };
  $("#imp-go").onclick = async () => {
    const r = await api("/api/projects/import", { folder: $("#imp-path").value });
    toast(r.message, r.ok ? "good" : "bad", 6000);
    if (r.ok) { await loadApp(); bbGo("library", "all", "a"); }
  };
};

// ---- Templates
PAGES["templates/book"] = async el => {
  await loadApp();
  el.innerHTML = `<div class="page-h"><h2>Book templates</h2></div>${card("Starter configurations", `<table class="tbl"><thead><tr><th>Template</th><th>What it sets up</th><th></th></tr></thead><tbody>
    ${Object.entries(BB.app.templates).map(([k, t]) => `<tr><td>${ic(t.icon)} <b>${esc(t.name)}</b></td><td>${esc(t.desc)}</td><td><a href="#/a/new/template" data-tpl="${k}">Use</a></td></tr>`).join("")}</tbody></table>`)}`;
  $$("[data-tpl]", el).forEach(a => a.onclick = () => store.set("tpl", a.dataset.tpl));
};
PAGES["templates/brand"] = el => {
  el.innerHTML = `<div class="page-h"><h2>Brand templates</h2></div>${card("Reusable brand kits", planned("Saving a book's fonts and colors as a template for new books.",
    "Needs a brand.yml format shared between projects. For now, set fonts and colors per book in Design › Brand Kit and Fonts."))}`;
};
PAGES["templates/prompt"] = async el => {
  const kinds = (await api("/api/prompts/kinds")).kinds;
  el.innerHTML = `<div class="page-h"><h2>Prompt templates</h2></div>${card("Prompt kinds", `<p class="muted-note">These are the prompts Book Builder can generate. Copy them from AI Studio › Prompt Generator for a specific chapter.</p>
    <table class="tbl"><thead><tr><th>Prompt</th><th>Stage</th><th>Needs</th></tr></thead><tbody>${kinds.map(k => `<tr><td>${esc(k.title)}</td><td>${esc(k.stage)}</td><td class="muted-note">${esc([].concat(k.needs || []).join(", ") || "—")}</td></tr>`).join("")}</tbody></table>`)}`;
};

// ---- Activity
PAGES["activity/changes"] = async el => {
  const a = await data("activity", true);
  el.innerHTML = `<div class="page-h"><h2>Recent changes</h2></div>${card("Commits in this book", a.commits.length ? `<table class="tbl"><thead><tr><th>When</th><th>Change</th><th>Areas</th></tr></thead><tbody>
    ${a.commits.map(c => `<tr><td class="nowrap">${bbWhen(c.time)}</td><td>${esc(c.subject)} <span class="muted-note">${c.files} files</span></td><td>${c.kinds.map(k => `<span class="chip-s">${esc(k)}</span>`).join(" ")}</td></tr>`).join("")}</tbody></table>`
    : `<p class="muted-note">${a.git ? "No commits yet." : "This book isn't a git repository, so changes aren't recorded."}</p>`)}`;
};
PAGES["activity/approvals"] = async el => {
  const a = await data("activity", true);
  el.innerHTML = `<div class="page-h"><h2>Approvals</h2></div>${card("Commits that approved chapters", a.approvals.length ? `<ul class="feed">${a.approvals.map(c => `<li><span class="muted-note">${bbWhen(c.time)}</span> ${esc(c.subject)} <span class="muted-note">· ${c.files.length} file(s)</span></li>`).join("")}</ul>`
    : `<p class="muted-note">No approvals found in the git history.</p>`)}
    <p class="muted-note">Approval dates aren't stored in the chapters themselves, so this comes from commits that set <code>status: approved</code>.</p>`;
};
PAGES["activity/builds"] = async el => {
  const a = await data("activity", true);
  el.innerHTML = `<div class="page-h"><h2>Build history</h2></div>${outputsTable(a.outputs)}
    ${a.publishes.length ? card("Website publishes", `<ul class="feed">${a.publishes.map(c => `<li><span class="muted-note">${bbWhen(c.time)}</span> ${esc(c.subject)}</li>`).join("")}</ul>`) : ""}`;
  wireOpen(el);
};

// ---- Settings (global)
function settingsPage(el, title, inner, save) {
  el.innerHTML = `<div class="page-h"><h2>${title}</h2><span class="grow"></span><span class="chip-s">Book Builder setting · applies to every book</span></div>${inner}`;
  if (save) $("#set-save").onclick = async () => { const r = await api("/api/settings/save", save()); BB.app.settings = r.settings; toast(r.message, "good"); };
}
PAGES["settings/ai"] = async el => {
  await loadApp(); const s = BB.app.settings;
  settingsPage(el, "AI providers", card("Assistants", `<p>Book Builder doesn't call AI services and stores no API keys. It prepares prompts and files that you paste into the assistants you use, then checks what comes back.</p>
    <div class="bkform"><label for="s-writer">Drafting assistant</label><select id="s-writer">${["ChatGPT", "Claude", "Gemini", "Other"].map(o => `<option ${o === s.writer ? "selected" : ""}>${o}</option>`).join("")}</select>
    <label for="s-checker">Checking assistant</label><select id="s-checker">${["Claude Code", "Claude", "ChatGPT", "Other"].map(o => `<option ${o === s.checker ? "selected" : ""}>${o}</option>`).join("")}</select></div>
    <p class="muted-note">Today's prompts are written for ChatGPT (drafting) and Claude Code (checking). Other choices are remembered for future prompt variants.</p>
    <button class="primary" id="set-save">${ic("save")}Save</button>`), () => ({ writer: $("#s-writer").value, checker: $("#s-checker").value }));
};
PAGES["settings/integrations"] = async el => {
  await loadApp();
  const g = await api("/api/git").catch(() => null);
  settingsPage(el, "Integrations", card("GitHub", `<p>Book Builder uses the <code>git</code> and <code>gh</code> tools already signed in on this computer. It never stores GitHub passwords or tokens.</p>
    <div class="ctx-row"><span>Open book's repository</span><span>${g ? esc(g.branch || "git") : "not a git repository"}</span></div>
    <p class="muted-note">Commit and push from Build › Save Work. Website publishing settings are per book in Website › GitHub Pages.</p>`)
    + card("Publishing services", planned("Connections to other hosts (Netlify, Cloudflare Pages, SFTP).", "Needs host profiles in website.yml and a deploy step per host.")));
};
PAGES["settings/storage"] = async el => {
  await loadApp(); const s = BB.app.settings;
  settingsPage(el, "Storage", card("Where things are kept", `<div class="bkform">
    <label for="s-dir">New books folder</label><input id="s-dir" value="${esc(s.projectsDir)}">
    <label>Library list</label><code>${esc(BB.app.registryPath)}</code>
    <label>App settings</label><code>${esc(BB.app.settingsPath)}</code>
    <label>Book Builder</label><code>${esc(BB.app.home)}</code></div>
    <p class="muted-note">Each book keeps its own files (chapters, assets, research, outputs) in its own folder. The Library only stores where those folders are.</p>
    <button class="primary" id="set-save">${ic("save")}Save</button>`), () => ({ projectsDir: $("#s-dir").value }));
};
PAGES["settings/preferences"] = async el => {
  await loadApp(); const s = BB.app.settings;
  const sel = (id, opts, v) => `<select id="${id}">${opts.map(([val, l]) => `<option value="${val}" ${val === v ? "selected" : ""}>${l}</option>`).join("")}</select>`;
  settingsPage(el, "Preferences", card("Appearance and behaviour", `<div class="bkform">
    <label for="s-theme">Theme</label>${sel("s-theme", [["system", "Match the system"], ["light", "Light"], ["dark", "Dark"]], s.theme)}
    <label for="s-dens">Density</label>${sel("s-dens", [["comfortable", "Comfortable"], ["compact", "Compact"]], s.density)}
    <label for="s-open">On start</label>${sel("s-open", [["0", "Show the Library"], ["1", "Reopen the last book"]], s.openLastProject ? "1" : "0")}
    <label for="s-openin">Open Book Builder in</label>${sel("s-openin", [["window", "Its own window"], ["browser", "My web browser"]], s.openIn || "window")}
    <span class="muted-note">For the desktop app; takes effect the next time it starts. File › Open in Browser works either way.</span>
    <label for="s-guide">Guidance</label>${sel("s-guide", [["1", "Show tutorials and Guide me links"], ["0", "Expert: hide them (Help still has the tutorials)"]], s.guidance === false ? "0" : "1")}
    <label for="s-ft">Default title font</label><input id="s-ft" value="${esc(s.defaultFonts.title)}">
    <label for="s-fb">Default body font</label><input id="s-fb" value="${esc(s.defaultFonts.body)}">
    <span class="muted-note">Default fonts are suggestions for new books. A book's own fonts are set in its Design › Fonts.</span></div>
    <button class="primary" id="set-save">${ic("save")}Save</button>`), () => {
      const theme = $("#s-theme").value;
      store.set("theme", theme === "system" ? null : theme);
      if (theme === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = theme;
      document.body.classList.toggle("compact", $("#s-dens").value === "compact");
      document.body.classList.toggle("expert", $("#s-guide").value === "0");
      return { theme, density: $("#s-dens").value, openLastProject: $("#s-open").value === "1", guidance: $("#s-guide").value === "1", openIn: $("#s-openin").value,
               defaultFonts: { title: $("#s-ft").value, body: $("#s-fb").value } };
    });
};
PAGES["settings/trash"] = async el => {
  const t = await api("/api/trash");
  const kinds = { book: "Book", prompt: "Prompt", revision: "Revision" };
  settingsPage(el, "Trash", card(`Deleted items <span class="small muted">${t.items.length}</span>`, t.items.length
    ? `<table class="tbl"><thead><tr><th>Item</th><th>Kind</th><th>From</th><th>Size</th><th>Deleted</th><th></th></tr></thead><tbody>
      ${t.items.map(i => `<tr><td>${esc(i.label)}</td><td>${kinds[i.kind] || esc(i.kind)}</td><td><code class="small">${esc(i.original)}</code></td><td>${fmtBytes(i.bytes)}</td><td>${bbWhen(i.deletedAt)}</td>
        <td class="row"><button class="sm" data-restore="${esc(i.id)}">${ic("undo-2")}Restore</button><button class="sm danger" data-purge="${esc(i.id)}" data-label="${esc(i.label)}">Delete forever</button></td></tr>`).join("")}</tbody></table>
      <div class="row"><button class="danger" id="trash-empty">${ic("trash-2")}Empty Trash</button></div>`
    : `<p class="muted-note">The Trash is empty.</p>`) + `<p class="muted-note">Deleted books, prompts and revision files wait here until you delete them for good. Folder: <code>${esc(t.folder)}</code></p>`);
  const again = () => PAGES["settings/trash"](el);
  $$("[data-restore]", el).forEach(b => b.onclick = async () => { const r = await api("/api/trash/restore", { id: b.dataset.restore }); toast(r.message, r.ok ? "good" : "bad"); await loadApp(); again(); });
  $$("[data-purge]", el).forEach(b => b.onclick = async () => {
    if (!await ask(`<h3>Delete “${esc(b.dataset.label)}” forever?</h3><p>This can't be undone.</p>`, [["Cancel", false], ["Delete forever", true, "danger"]])) return;
    const r = await api("/api/trash/purge", { id: b.dataset.purge, confirm: true }); toast(r.message, r.ok ? "good" : "bad"); again();
  });
  const empty = $("#trash-empty", el);
  if (empty) empty.onclick = async () => {
    if (!await ask(`<h3>Empty the Trash?</h3><p>All ${t.items.length} item${t.items.length === 1 ? "" : "s"} will be deleted forever. This can't be undone.</p>`, [["Cancel", false], ["Empty Trash", true, "danger"]])) return;
    const r = await api("/api/trash/purge", { all: true, confirm: true }); toast(r.message, r.ok ? "good" : "bad"); again();
  };
};
PAGES["settings/privacy"] = async el => {
  await loadApp(); const p = BB.app.settings.privacy;
  settingsPage(el, "Privacy", card("What leaves this computer", `<p>Book Builder runs only on this computer (127.0.0.1). It has no accounts, analytics or tracking.</p>
    <label class="chk"><input type="checkbox" id="s-fonts" ${p.fetchFontCatalog ? "checked" : ""}> Fetch the Google Fonts catalog (fonts.google.com) for the font picker</label>
    <label class="chk"><input type="checkbox" id="s-live" ${p.checkLiveSite ? "checked" : ""}> Check the published website after publishing</label>
    <p class="muted-note">Publishing and pushing only happen when you press those buttons, and they always ask first. Private sources (<code>sources-private/</code>) are never published.</p>
    <button class="primary" id="set-save">${ic("save")}Save</button>`), () => ({ privacy: { fetchFontCatalog: $("#s-fonts").checked, checkLiveSite: $("#s-live").checked } }));
};

// ---- Overview
function milestones(d) {
  const h = d.health.categories, has = (cat, st) => h[cat].some(i => i.status === st);
  const stage = (name, cat, done, detail) => {
    const st = done ? "pass" : has(cat, "fail") ? "fail" : has(cat, "unchecked") ? "unchecked" : "warn";
    return `<li class="ms ms-${st}">${ic(STATUS_ICON[st])}<div><b>${name}</b><div class="muted-note">${esc(detail)}</div></div></li>`;
  };
  const writingDone = d.approved === d.chapters;
  const reviewOk = !has("Content", "fail") && !has("Content", "warn") && !has("Evidence", "fail");
  const designOk = h.Design.every(i => i.status === "pass" || i.status === "na");
  const relOk = h.Distribution.every(i => i.status === "pass" || i.status === "na");
  return `<ol class="milestones">
    ${stage("Writing", "Content", writingDone, `${d.approved} of ${d.chapters} chapters approved`)}
    ${stage("Review", "Evidence", reviewOk, reviewOk ? "No open findings or evidence failures" : "Open findings or evidence problems")}
    ${stage("Design", "Design", designOk, designOk ? "Cover, images and format check pass" : "Design checks need attention")}
    ${stage("Release", "Distribution", relOk, relOk ? "Builds are current and validated" : "Builds or validation outstanding")}</ol>`;
}
function nextActions(d) {
  const items = Object.values(d.health.categories).flat().filter(i => i.status === "fail" || i.status === "warn" || i.status === "unchecked");
  const order = { fail: 0, warn: 1, unchecked: 2 };
  items.sort((a, b) => order[a.status] - order[b.status]);
  const top = items.slice(0, 5);
  return top.length ? `<ul class="actions-list">${top.map(i => `<li>${badge(i.status)}<span class="grow">${esc(i.label)}<span class="muted-note"> · ${esc(i.detail)}</span></span>${i.link ? `<a href="#/p/${i.link}">Go</a>` : ""}</li>`).join("")}</ul>
    ${items.length > top.length ? `<p class="muted-note">${items.length - top.length} more in ${link("overview", "checklist", "the release checklist")}.</p>` : ""}`
    : `<p>Nothing outstanding. Build the book and publish the website.</p>`;
}
PAGES["overview/dashboard"] = async el => {
  const d = await data("dashboard", true);
  const b = d.book, readiness = Object.values(d.health.categories).flat();
  const fails = readiness.filter(i => i.status === "fail").length, warns = readiness.filter(i => i.status === "warn").length;
  const ready = fails ? ["fail", `${fails} blocking`] : warns ? ["warn", `${warns} to review`] : ["pass", "Ready"];
  const maxW = Math.max(...d.composition.map(p => p.words), 1);
  const act = await data("activity").catch(() => ({ commits: [], approvals: [], outputs: [] }));
  const events = [
    ...act.approvals.slice(0, 4).map(c => ({ t: c.time, i: "check-check", s: c.subject })),
    ...act.commits.slice(0, 6).map(c => ({ t: c.time, i: c.kinds.includes("chapters") ? "file-pen-line" : c.kinds.includes("assets") ? "image" : "git-commit-horizontal", s: c.subject })),
    ...(act.outputs || []).slice(0, 3).map(o => ({ t: o.mtime, i: "package-check", s: `Built ${o.name}` })),
    ...(act.publishes || []).slice(0, 2).map(p => ({ t: p.time, i: "rocket", s: `Website: ${p.subject}` })),
  ].sort((a, b) => b.t - a.t).filter((e, i, arr) => arr.findIndex(x => x.s === e.s) === i).slice(0, 8);
  el.innerHTML = `
    <section class="identity">
      <button class="id-cover" id="ov-cover" ${d.cover ? "" : "disabled"} aria-label="${d.cover ? "Show the cover larger" : "No cover yet"}">
        ${d.cover ? `<img src="/pfile/${esc(d.cover)}" alt="Cover of ${esc(b.title)}">` : `<span class="cover-ph">${ic("image")}<span>No cover yet</span></span>`}</button>
      <div class="id-body">
        <div class="eyebrow">Book project</div>
        <h2>${esc(b.title)}</h2>
        ${b.subtitle ? `<p class="id-sub">${esc(b.subtitle)}</p>` : ""}
        <p class="id-meta">${esc(b.author)}${b.editor ? ` · created by ${esc(b.editor)}` : ""}</p>
        <div class="id-tags"><span class="chip-s">${esc(b.date || "Draft")}</span><span class="chip-s">${d.approved === d.chapters ? "Manuscript complete" : "Writing"}</span><span class="chip-s">Edited ${bbWhen(d.modified)}</span></div>
        <div class="row">
          <button id="ov-preview" ${d.pdf ? "" : "disabled"} title="${d.pdf ? "Open the latest PDF" : "Build a PDF first"}">${ic("eye")}Preview</button>
          <a class="btn primary" href="#/p/build/settings">${ic("hammer")}Build</a>
          <details class="menu"><summary aria-label="Project actions">${ic("ellipsis")} More</summary><div class="pop" role="menu">
            <a role="menuitem" href="#/p/overview/details">${ic("info")}Edit book details</a>
            <a role="menuitem" href="#/p/build/git">${ic("git-commit-horizontal")}Save work (Git)</a>
            <button role="menuitem" id="ov-export">${ic("package")}Export book…</button>
            <a role="menuitem" href="#/p/website/publish">${ic("rocket")}Publish website</a>
            <button role="menuitem" id="ov-tour">${ic("circle-help")}Guided tutorial</button>
          </div></details>
        </div>
      </div>
    </section>
    <div class="metrics">
      <div class="metric"><span>Approved</span><b>${d.approved}<small>/${d.chapters}</small></b></div>
      <div class="metric"><span>Words</span><b>${d.words.toLocaleString()}</b></div>
      <div class="metric"><span>Sections</span><b>${d.sections}</b></div>
      <div class="metric"><span>Reading time</span><b>${Math.floor(d.readingMinutes / 60)}<small> h </small>${d.readingMinutes % 60}<small> min</small></b></div>
      <div class="metric"><span>PDF pages</span><b>${d.pages ?? "—"}</b><small class="muted-note">${d.pages ? `latest PDF, ${bbWhen(d.pdf.mtime)}` : "no PDF build yet"}</small></div>
      <div class="metric m-${ready[0]}"><span>Readiness</span><b class="small-b">${badge(ready[0])}</b><small class="muted-note">${ready[1]}</small></div>
    </div>
    <div class="grid2">
      ${card("Publishing milestones", milestones(d))}
      ${card("Next actions", nextActions(d))}
    </div>
    <div class="grid2">
      ${card("Manuscript composition", `<table class="tbl comp"><thead><tr><th>Section</th><th>Chapters</th><th>Words</th><th class="w40">Size</th><th>Done</th></tr></thead><tbody>
        ${d.composition.map(p => `<tr data-part="${p.n}" tabindex="0" title="Show these chapters"><td>${esc(p.name)}</td><td>${p.chapters}</td><td>${p.words.toLocaleString()}</td>
          <td><span class="hbar"><span style="width:${p.words / maxW * 100}%"></span></span></td><td>${p.approved === p.chapters ? ic("circle-check") : `${p.approved}/${p.chapters}`}</td></tr>`).join("")}</tbody></table>`)}
      ${card("Recent activity", events.length ? `<ul class="feed">${events.map(e => `<li>${ic(e.i)}<span class="grow">${esc(e.s)}</span><span class="muted-note nowrap">${bbWhen(e.t)}</span></li>`).join("")}</ul>`
        : `<p class="muted-note">No recorded activity. Activity comes from git history, build files and website publishes.</p>`)}
    </div>
    ${card("Book preview", `<div class="previews">
      <figure>${d.cover ? `<img src="/pfile/${esc(d.cover)}" alt="Front cover">` : `<span class="cover-ph">${ic("image")}<span>No cover</span></span>`}<figcaption>Cover</figcaption></figure>
      <figure><span class="cover-ph">${ic("file-type")}<span>${d.pdf ? esc(d.pdf.name) : "No PDF yet"}</span></span><figcaption>${d.pdf ? `<button class="sm" data-open-file="${esc(d.pdf.path)}">Open interior PDF</button>` : "Build a PDF to preview the interior"}</figcaption></figure>
    </div>`)}`;
  $("#ov-cover").onclick = () => d.cover && ask(`<img src="/pfile/${esc(d.cover)}" alt="Cover of ${esc(b.title)}" style="max-width:100%;max-height:75vh;display:block;margin:auto">`, [["Close", null]]);
  if (d.pdf) $("#ov-preview").onclick = () => api("/api/open", { path: d.pdf.path });
  $("#ov-tour").onclick = () => tourStart(0, true);
  $("#ov-export").onclick = () => exportBook(projectPath());
  $$("[data-part]", el).forEach(r => r.onclick = r.onkeydown = ev => {
    if (ev.type === "keydown" && ev.key !== "Enter") return;
    store.set("listPart", +r.dataset.part); bbGo("chapters", "list", "p");
  });
  wireOpen(el);
};
PAGES["overview/statistics"] = async el => {
  const d = await data("dashboard");
  const chs = [...S.chapters].sort((a, b) => b.words - a.words);
  const avg = Math.round(d.words / Math.max(1, d.chapters));
  el.innerHTML = `<div class="page-h"><h2>Statistics</h2></div>
    <div class="metrics">
      <div class="metric"><span>Words</span><b>${d.words.toLocaleString()}</b></div>
      <div class="metric"><span>Average chapter</span><b>${avg.toLocaleString()}</b></div>
      <div class="metric"><span>Longest</span><b>${chs[0]?.words.toLocaleString() || 0}</b><small class="muted-note">${esc(chs[0]?.title || "")}</small></div>
      <div class="metric"><span>Shortest</span><b>${chs.at(-1)?.words.toLocaleString() || 0}</b><small class="muted-note">${esc(chs.at(-1)?.title || "")}</small></div>
      <div class="metric"><span>Reading time</span><b>${Math.round(d.readingMinutes / 60)}<small> h</small></b><small class="muted-note">at 238 words per minute</small></div>
      <div class="metric"><span>PDF pages</span><b>${d.pages ?? "—"}</b></div>
    </div>
    ${card("Words per chapter", `<table class="tbl"><thead><tr><th>#</th><th>Chapter</th><th>Words</th><th class="w40"></th></tr></thead><tbody>
      ${S.chapters.map(c => `<tr><td class="mono">${esc(num(c))}</td><td><a href="#" data-go="${c.n}">${esc(c.title)}</a></td><td>${c.words.toLocaleString()}</td><td><span class="hbar"><span style="width:${c.words / (chs[0]?.words || 1) * 100}%"></span></span></td></tr>`).join("")}</tbody></table>`)}`;
  wireChapterLinks(el);
};
function healthCats(h) {
  return Object.entries(h.categories).map(([cat, items]) => card(cat, `<ul class="health">${items.map(i => `<li>${badge(i.status)}<span class="grow"><b>${esc(i.label)}</b><span class="muted-note"> · ${esc(i.detail)}</span></span>${i.link ? `<a href="#/p/${i.link}">Open</a>` : ""}</li>`).join("")}</ul>`)).join("");
}
PAGES["overview/health"] = async el => {
  const d = await data("dashboard", true);
  el.innerHTML = `<div class="page-h"><h2>Book Health</h2><span class="grow"></span><button id="hc-run">${ic("play")}Run format check</button></div>
    <p class="muted-note">Manuscript completion and publishing readiness are tracked separately. A check that hasn't been run shows as <b>Not checked</b>, never as passed.</p>
    <div class="grid2">${healthCats(d.health)}</div>
    ${d.health.check ? `<details class="card"><summary><b>Last format check output</b> <span class="muted-note">${bbWhen(d.health.check.time)}</span></summary><pre class="log">${esc(d.health.check.output)}</pre></details>` : ""}`;
  $("#hc-run").onclick = async () => {
    const r = await busy("Running the format check (build.py check)…", () => api("/api/check/run", {}));
    toast(r.check.ok ? "Format check passed." : `Format check: ${r.check.errors} error(s).`, r.check.ok ? "good" : "bad", 6000);
    renderPage();
  };
};
PAGES["overview/checklist"] = async el => {
  const d = await data("dashboard");
  const all = Object.entries(d.health.categories).flatMap(([cat, items]) => items.map(i => ({ ...i, cat })));
  const steps = [...all, { label: "Commit and push your work", status: "unchecked", detail: "Save a copy to GitHub", link: "build/git", cat: "Release" },
    { label: "Preview the website", status: "unchecked", detail: "Check pages before publishing", link: "website/preview", cat: "Release" },
    { label: "Publish the website", status: "unchecked", detail: "Asks before it starts", link: "website/publish", cat: "Release" }];
  el.innerHTML = `<div class="page-h"><h2>Release checklist</h2></div>
    ${card(`${steps.filter(s => s.status === "pass" || s.status === "na").length} of ${steps.length} done`, `<ol class="checklist">${steps.map(s => `<li class="${s.status}">${badge(s.status)}<span class="grow"><b>${esc(s.label)}</b> <span class="muted-note">${esc(s.cat)} · ${esc(s.detail)}</span></span>${s.link ? `<a href="#/p/${s.link}">Go</a>` : ""}</li>`).join("")}</ol>
      <p class="muted-note">Release steps you do yourself (commit, preview, publish) can't be detected, so they stay “Not checked”.</p>`)}`;
};
const DETAIL_GROUPS = [
  ["Title and credits", [["title", "Title"], ["subtitle", "Subtitle"], ["author", "Author or imprint"], ["publisher", "Publisher"], ["editor", "Creator / editor"], ["credit-line", "Credit line", "For example “Written with ChatGPT and Claude”."]]],
  ["Description", [["description", "Book description", "", "area"], ["synopsis", "Short synopsis", "", "area"], ["author-bio", "Author bio", "", "area"], ["about-authors", "About the book and its authors", "Shown on the PDF's copyright page and the website's About page.", "area"]]],
  ["Classification", [["subject", "Genre or category"], ["intended-audience", "Intended audience"], ["lang", "Language", "A code such as en-US."], ["keywords", "Keywords", "Separate with commas."]]],
  ["Edition and rights", [["rights", "Rights and license"], ["date", "Edition", "For example Draft, First edition."], ["publication-date", "Publication date", "YYYY-MM-DD"], ["identifier", "Identifier (ISBN, optional)"]]],
  ["Print", [["papersize", "PDF page size", "us-trade is 6×9 in.", ["us-trade", "us-letter", "a5", "jis-b6", "iso-b5"]], ["fontsize", "PDF font size", "", ["10pt", "10.5pt", "11pt", "11.5pt", "12pt"]]]],
];
function fieldHtml([k, l, hint, kind], b) {
  const v = b[k] ?? "";
  const input = Array.isArray(kind) ? `<select id="bk-${k}">${[...new Set([...kind, v].filter(Boolean))].map(o => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`
    : kind === "area" ? `<textarea id="bk-${k}" rows="3" style="font-family:inherit;font-size:inherit">${esc(v)}</textarea>`
    : `<input id="bk-${k}" value="${esc(v)}">`;
  return `<label for="bk-${k}">${l}</label>${input}<span class="muted-note">${hint || ""}</span>`;
}
async function saveFields(keys) {
  const body = Object.fromEntries(keys.filter(k => $(`#bk-${k}`)).map(k => [k, $(`#bk-${k}`).value]));
  const r = await api("/api/book/save", body);
  toast(r.message, r.ok ? "good" : "bad", 5000);
  if (r.ok) { BB.cache = {}; await loadApp(); renderHeader(); }
  return r;
}
PAGES["overview/details"] = async el => {
  const d = await data("dashboard", true); const b = d.book;
  const keys = DETAIL_GROUPS.flatMap(g => g[1].map(f => f[0]));
  el.innerHTML = `<div class="page-h"><h2>Book details</h2><span class="grow"></span><span class="chip-s">Project setting</span><button class="primary" id="bd-save">${ic("save")}Save</button></div>
    <p class="muted-note">Saved in <code>book.yml</code>. Only the fields you change are rewritten; comments, the chapter list and any other settings stay as they are.</p>
    ${DETAIL_GROUPS.map(([t, fs]) => card(t, `<div class="bkform">${fs.map(f => fieldHtml(f, b)).join("")}</div>`)).join("")}
    <p class="muted-note">Margins are in Design › Interior Layout.</p>
    <div id="bd-pub"></div>`;
  $("#bd-save").onclick = () => saveFields(keys);
  api("/api/project").then(pi => {
    const box = $("#bd-pub"); if (!box) return;
    box.innerHTML = card("Publishing", pi.legacy ? `<p class="muted-note">This book uses its existing website settings (website.yml).</p>`
      : `<p>${pi.publishing ? badge("pass") + " Publishing is on for this book." : badge("unchecked") + " Publishing is off: the website can't be set up or published until you turn it on."}</p>
         <button id="bd-pubtoggle">${pi.publishing ? "Turn publishing off" : "Turn publishing on"}</button>`);
    if ($("#bd-pubtoggle")) $("#bd-pubtoggle").onclick = async () => { const r = await api("/api/projects/publishing", { enabled: !pi.publishing }); toast(r.message, r.ok ? "good" : "bad"); renderPage(); };
  }).catch(() => {});
};

// ---- Chapters
function wireChapterLinks(el) {
  $$("[data-go]", el).forEach(a => a.onclick = ev => { ev.preventDefault(); go(+a.dataset.go); bbGo("chapters", "editor", "p"); });
}
PAGES["chapters/list"] = el => {
  const only = store.get("listPart", null); store.set("listPart", null);
  const parts = [...new Set(S.chapters.map(c => c.part))];
  el.innerHTML = `<div class="page-h"><h2>Chapter list</h2><span class="grow"></span><input type="search" id="cl-q" placeholder="Filter chapters" aria-label="Filter chapters"></div>
    ${parts.filter(p => only === null || p === only).map(p => {
      const xs = S.chapters.filter(c => c.part === p);
      return card(esc(xs[0].partName), `<table class="tbl cl"><thead><tr><th>#</th><th>Title</th><th>Status</th><th>Words</th><th>Draft</th></tr></thead><tbody>
        ${xs.map(c => `<tr data-t="${esc((num(c) + " " + c.title).toLowerCase())}"><td class="mono">${esc(num(c))}</td><td><a href="#" data-go="${c.n}">${esc(c.title)}</a></td><td>${c.serious ? pill("fix") : pill(c.code)}</td><td>${c.words.toLocaleString()}</td><td>${c.version ? `v${c.version}` : "—"}</td></tr>`).join("")}</tbody></table>`);
    }).join("")}
    ${only !== null ? `<p><a href="#/p/chapters/list">Show all sections</a></p>` : ""}`;
  wireChapterLinks(el);
  $("#cl-q").oninput = e => { const q = e.target.value.toLowerCase(); $$("tr[data-t]", el).forEach(r => r.classList.toggle("hidden", !r.dataset.t.includes(q))); };
};
PAGES["chapters/reorder"] = async el => {
  const st = BB.struct = BB.struct || await api("/api/structure");
  if (!st.editable) {
    el.innerHTML = `<div class="page-h"><h2>Reorder</h2></div>${card("Current order", `<p class="muted-note">${esc(st.reason)}</p>
      <ol class="order">${st.parts.map(p => `<li><b>${esc(p.name)}</b><ol>${p.chapters.map(c => `<li><span class="mono">${c.n}</span> ${esc(c.title)}</li>`).join("")}</ol></li>`).join("")}</ol>`)}`;
    BB.struct = null; return;
  }
  el.innerHTML = `<div class="page-h"><h2>Structure</h2><span class="grow"></span><button id="st-reset">Discard changes</button><button class="primary" id="st-save">${ic("save")}Save structure</button></div>
    <p class="muted-note">Add, rename, reorder or remove parts and chapters. Chapters with a ${ic("lock")} already have drafts, research or a status: they keep their number, part and title (move the others around them). Removed placeholders go to book/.removed/, and a book-data backup is made before saving.</p>
    ${st.parts.map((p, i) => card(`<input data-pn="${i}" value="${esc(p.name)}" aria-label="Part name">`, `<ol class="st-list">${p.chapters.map((c, j) => `
      <li class="${c.locked ? "locked" : ""}"><span class="mono">${j + 1}</span>
        <input data-cn="${i}:${j}" value="${esc(c.title)}" ${c.locked ? "disabled" : ""} aria-label="Chapter title">${c.locked ? `<span title="Has work">${ic("lock")}</span>` : ""}
        <button class="ghost sm" data-mv="${i}:${j}:-1" aria-label="Move up">↑</button><button class="ghost sm" data-mv="${i}:${j}:1" aria-label="Move down">↓</button>
        ${c.locked ? "" : `<button class="ghost sm" data-rm="${i}:${j}" aria-label="Remove">${ic("x")}</button>`}</li>`).join("")}</ol>
      <div class="row"><button class="sm" data-add="${i}">${ic("plus")}Add chapter</button><span class="grow"></span>${p.chapters.some(c => c.locked) ? "" : `<button class="ghost sm" data-prm="${i}">Remove part</button>`}</div>`)).join("")}
    <button id="st-padd">${ic("plus")}Add part</button>`;
  const sync = () => { $$("[data-pn]", el).forEach(i => st.parts[+i.dataset.pn].name = i.value); $$("[data-cn]", el).forEach(i => { const [a, b] = i.dataset.cn.split(":").map(Number); st.parts[a].chapters[b].title = i.value; }); };
  const redraw = () => { sync(); renderPage(); };
  $$("[data-mv]", el).forEach(b => b.onclick = () => { sync(); const [a, j, d] = b.dataset.mv.split(":").map(Number); const list = st.parts[a].chapters; const k = j + d;
    if (k >= 0 && k < list.length) [list[j], list[k]] = [list[k], list[j]];
    else if (k < 0 && a > 0) st.parts[a - 1].chapters.push(list.splice(j, 1)[0]);
    else if (k >= list.length && a < st.parts.length - 1) st.parts[a + 1].chapters.unshift(list.splice(j, 1)[0]);
    renderPage(); });
  $$("[data-rm]", el).forEach(b => b.onclick = () => { sync(); const [a, j] = b.dataset.rm.split(":").map(Number); st.parts[a].chapters.splice(j, 1); renderPage(); });
  $$("[data-add]", el).forEach(b => b.onclick = () => { sync(); st.parts[+b.dataset.add].chapters.push({ title: "New chapter" }); renderPage(); });
  $$("[data-prm]", el).forEach(b => b.onclick = () => { sync(); st.parts.splice(+b.dataset.prm, 1); renderPage(); });
  $("#st-padd").onclick = () => { sync(); st.parts.push({ name: `Part ${st.parts.length + 1}`, chapters: [{ title: "New chapter" }] }); renderPage(); };
  $("#st-reset").onclick = () => { BB.struct = null; renderPage(); };
  $("#st-save").onclick = async () => {
    sync();
    const r = await busy("Saving the structure…", () => api("/api/structure/save", { parts: st.parts.map(p => ({ name: p.name, chapters: p.chapters.map(c => ({ ...(c.id ? { id: c.id } : {}), title: c.title })) })) }));
    toast(r.message, r.ok ? "good" : "bad", 8000);
    if (r.ok) { BB.struct = null; await load(true); renderPage(); }
  };
};
// A table of files with checkboxes; a [data-trash-for] button moves the checked ones to the Trash.
function fileTable(files, id, extraCol) {
  return `<table class="tbl" id="${id}"><thead><tr><th><input type="checkbox" data-all aria-label="Select all"></th><th>File</th>${extraCol ? `<th>${extraCol}</th>` : ""}<th>Size</th><th>Saved</th></tr></thead><tbody>
    ${files.map(f => `<tr><td><input type="checkbox" value="${esc(f.path)}" aria-label="Select ${esc(f.name)}"></td><td><code>${esc(f.path)}</code></td>${extraCol ? `<td>${esc(f.kind || "")}</td>` : ""}<td>${fmtBytes(f.bytes)}</td><td>${bbWhen(f.mtime)}</td></tr>`).join("")}</tbody></table>`;
}
function wireFileTables(el, endpoint, what, after) {
  $$("table[id] [data-all]", el).forEach(a => a.onchange = () => $$("tbody input", a.closest("table")).forEach(c => (c.checked = a.checked)));
  $$("[data-trash-for]", el).forEach(b => b.onclick = async () => {
    const files = $$(`#${b.dataset.trashFor} tbody input:checked`, el).map(c => c.value);
    if (!files.length) return toast("Select the files to delete first.", "bad");
    if (!await ask(`<h3>Delete ${files.length} ${what}${files.length === 1 ? "" : "s"}?</h3><p>They move to Book Builder's Trash. You can restore them from Settings › Trash.</p>`,
      [["Cancel", false], ["Move to Trash", true, "danger"]])) return;
    const r = await api(endpoint, { files, confirm: true }); toast(r.message, r.ok ? "good" : "bad"); after();
  });
}
PAGES["chapters/revisions"] = async el => {
  const [r, f] = await Promise.all([data("revisions", true), api("/api/revisions/files")]);
  el.innerHTML = `<div class="page-h"><h2>Revisions</h2></div>${card("Drafts by chapter, newest first", r.chapters.length ? `<table class="tbl"><thead><tr><th>Chapter</th><th>Drafts</th><th>Latest</th><th></th></tr></thead><tbody>
    ${r.chapters.map(c => `<tr><td><a href="#" data-go="${c.n}">${esc(c.title)}</a></td><td>v1–v${c.versions}</td><td>${bbWhen(c.latest)}</td><td><a href="#" data-go="${c.n}" data-tab="draft">Compare in editor</a></td></tr>`).join("")}</tbody></table>`
    : `<p class="muted-note">No drafts saved yet.</p>`)}<p class="muted-note">Each saved reply becomes a new draft version; the editor's Draft tab shows them side by side with Claude's checks.</p>
    ${card("Manage revision files", f.chapters.length ? f.chapters.map(c => `<details class="rev-files"><summary><b>${esc(c.title)}</b> <span class="small muted">${c.files.length} file${c.files.length === 1 ? "" : "s"} · ${esc(c.status)}</span></summary>
      ${fileTable(c.files, `rev-${c.n}`, "Kind")}
      <div class="row"><button class="danger sm" data-trash-for="rev-${c.n}">${ic("trash-2")}Move selected to Trash</button></div>
      ${c.status === "approved" ? "" : `<p class="muted-note">If you delete the newest draft, the editor shows the one before it.</p>`}</details>`).join("")
      : `<p class="muted-note">No drafts or checks saved yet.</p>`)}
    <p class="muted-note">Deleting drafts, editor notes or checks never changes a chapter's text in the book. Approved chapters stay as they are.</p>`;
  $$("[data-tab]", el).forEach(a => a.addEventListener("click", () => { tab = "draft"; store.set("tab", "draft"); }, true));
  wireChapterLinks(el);
  wireFileTables(el, "/api/revisions/delete", "revision file", () => PAGES["chapters/revisions"](el));
};
PAGES["ai/saved"] = async el => {
  const f = await api("/api/prompts/files");
  el.innerHTML = `<div class="page-h"><h2>Saved prompts</h2></div>${card("Prompts and prompt packs this book has saved", f.files.length
    ? `${fileTable(f.files, "saved-prompts")}<div class="row"><button class="danger sm" data-trash-for="saved-prompts">${ic("trash-2")}Move selected to Trash</button></div>`
    : `<p class="muted-note">No saved prompts. Prompts you make in the Prompt Generator are saved in this book's <code>prompts</code> folder.</p>`)}
    <p class="muted-note">Deleting a saved prompt doesn't change any chapter. You can make it again from the Prompt Generator at any time.</p>`;
  wireFileTables(el, "/api/prompts/delete", "prompt file", () => PAGES["ai/saved"](el));
};
PAGES["chapters/approvals"] = el => {
  const ready = S.chapters.filter(c => c.code === "approve"), done = S.chapters.filter(c => c.code === "advance");
  const rows = xs => `<ul class="todo">${xs.map(c => `<li><span class="n">${esc(num(c))}</span><a href="#" data-go="${c.n}">${esc(c.title)}</a><span class="grow"></span>${pill(c.code)}</li>`).join("")}</ul>`;
  el.innerHTML = `<div class="page-h"><h2>Approvals</h2></div>
    ${card(`Ready to approve <span class="small muted">${ready.length}</span>`, ready.length ? rows(ready) + `<p class="muted-note">Approve from the chapter's editor; it always asks first.</p>` : `<p class="muted-note">Nothing is waiting for approval.</p>`)}
    ${card(`Approved <span class="small muted">${done.length}</span>`, `<details><summary>Show all</summary>${rows(done)}</details>`)}`;
  wireChapterLinks(el);
};

// ---- Research
// Research Library (tools/research_library.py): documents and AI research per book, searchable offline.
const RL = { sel: new Set(), open: null, q: "", kind: "", chapter: "", tag: "", archived: false };
const RL_ACCEPT = ".pdf,.docx,.docm,.txt,.md,.markdown,.rtf,.odt,.html,.htm,.csv,.xlsx,.xlsm,.json,.epub,.pptx,.pptm,.ppt,.doc,.xls";
const RL_STATUS = { ok: ["pass", "Searchable"], partial: ["warn", "Partly searchable"], scanned: ["warn", "Scanned: no text"], unsupported: ["unchecked", "Not searchable"], error: ["fail", "Couldn't read"] };
const rlBadge = st => { const [k, l] = RL_STATUS[st] || RL_STATUS.error; return `<span class="st st-${k}">${l}</span>`; };
const fileToB64 = f => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.onerror = rej; r.readAsDataURL(f); });
async function rlUpload(fileList, chapters = [], replace = null) {
  const files = [...fileList];
  if (!files.length) return;
  const big = files.find(f => f.size > 100 * 1024 * 1024);
  if (big) return toast(`${big.name} is larger than 100 MB.`, "bad", 6000);
  const payload = await Promise.all(files.map(async f => ({ name: f.name, data: await fileToB64(f) })));
  const r = await busy(`Adding ${files.length} file(s) to the Research Library…`, () => api("/api/research/upload", { files: payload, chapters, ...(replace ? { replace } : {}) }));
  const flagged = r.added.filter(x => x.versions.at(-1).status !== "ok");
  toast(`Added ${r.added.length} file(s)${r.added.some(x => x.duplicate) ? " (already-stored copies were merged)" : ""}${flagged.length ? `; ${flagged.length} couldn't be fully read: see their notes` : ""}.`, flagged.length ? "" : "good", 7000);
  return r;
}
function chapterOpts(selected = []) {
  return S.chapters.map(c => `<option value="${c.n}" ${selected.includes(c.n) ? "selected" : ""}>${esc(num(c))} · ${esc(c.title)}</option>`).join("");
}
function rlSelCount() { const n = RL.sel.size; $("#rl-select-count") && ($("#rl-select-count").textContent = n ? `${n} selected` : "Nothing selected"); $$("[data-needsel]").forEach(b => b.disabled = !n); }
PAGES["research/sources"] = async el => {
  const pre = store.get("rlChapter", null); if (pre) { RL.chapter = String(pre); store.set("rlChapter", null); }
  const qs = new URLSearchParams({ archived: RL.archived ? "1" : "0", ...(RL.kind ? { kind: RL.kind } : {}), ...(RL.chapter ? { chapter: RL.chapter } : {}), ...(RL.tag ? { tag: RL.tag } : {}) });
  const [lib, hits] = await Promise.all([api(`/api/research/sources?${qs}`), RL.q ? api(`/api/research/search?${new URLSearchParams({ q: RL.q, ...(RL.chapter ? { chapter: RL.chapter } : {}), archived: RL.archived ? "1" : "0" })}`) : null]);
  const sm = lib.summary;
  el.innerHTML = `
    <div class="page-h"><h2>Research Library</h2><span class="grow"></span>
      <button id="rl-tour" class="linkbtn guide-btn">Guide me</button>
      <label class="btn primary" for="rl-file" tabindex="0">${ic("upload")}Upload files</label><input type="file" id="rl-file" multiple accept="${RL_ACCEPT}" class="hidden"></div>
    <div id="rl-drop" class="rl-drop" tabindex="0" aria-label="Drop research files here">${ic("upload")}<span>Drop PDFs, Word, Excel, PowerPoint, EPUB, text or web pages here. Originals are kept; text is indexed for search on this computer only.</span></div>
    <div class="rl-bar">
      <input type="search" id="rl-q" placeholder="Search all text (use &quot;quotes&quot; for a phrase)" value="${esc(RL.q)}" aria-label="Search the Research Library">
      <select id="rl-kind" aria-label="Kind"><option value="">All kinds</option>${Object.entries(lib.kinds).map(([k, l]) => `<option value="${k}" ${RL.kind === k ? "selected" : ""}>${l}</option>`).join("")}</select>
      <select id="rl-ch" aria-label="Chapter"><option value="">All chapters</option>${S.chapters.map(c => `<option value="${c.n}" ${RL.chapter === String(c.n) ? "selected" : ""}>${esc(num(c))} · ${esc(c.title)}</option>`).join("")}</select>
      <select id="rl-tag" aria-label="Tag"><option value="">All tags</option>${sm.tags.map(tg => `<option ${RL.tag === tg ? "selected" : ""}>${esc(tg)}</option>`).join("")}</select>
      <label class="chk small"><input type="checkbox" id="rl-arch" ${RL.archived ? "checked" : ""}> Archived</label>
    </div>
    <div class="rl-selbar" id="rl-selbar">
      <b id="rl-select-count"></b>
      <select id="rl-pch" aria-label="Chapter for prompts"><option value="">Chapter for prompts…</option>${chapterOpts(RL.chapter ? [+RL.chapter] : [])}</select>
      <button id="rl-review" data-needsel title="Ask ChatGPT or Claude to evaluate the selected evidence">${ic("clipboard-check")}Copy review prompt</button>
      <button data-needsel data-pk="write">${ic("pen-line")}Writing prompt + sources</button>
      <button data-needsel data-pk="research">${ic("search-check")}Research prompt + sources</button>
      <button data-needsel data-pk="image-style">${ic("image")}Image prompt + sources</button>
      <button data-needsel id="rl-zip" title="Every selected source in full, for long collections">${ic("package")}Context ZIP</button>
      <button id="rl-save-review" title="Archive a ChatGPT or Claude review you copied">${ic("clipboard-paste")}Save review from clipboard</button>
      <button class="ghost" id="rl-clear">Clear selection</button>
    </div>
    <div class="rl-grid">
      <div class="card rl-list" id="rl-list">${hits ? rlHits(hits.hits) : rlRows(lib.sources)}</div>
      <div class="card rl-preview" id="rl-preview">${RL.open ? "" : `<p class="muted-note">Choose a source to preview it, assign chapters and tags, or pick sections (pages, sheets, slides) for prompts.</p>`}</div>
    </div>
    <p class="muted-note">${sm.count} source(s)${sm.flagged ? ` · ${sm.flagged} flagged` : ""}${sm.archived ? ` · ${sm.archived} archived` : ""}. Stored in this book's <code>research-library/</code>; included in book-data backups, kept out of git (documents may be copyrighted). Nothing is uploaded anywhere.</p>
    <details class="card"><summary><b>Other source folders</b> <span class="muted-note">sources/, sources-inbox/, bibliography counts</span></summary><div id="rl-folders"></div></details>`;
  rlSelCount();
  const reload = () => renderPage();
  $("#rl-file").onchange = async e => { await rlUpload(e.target.files, RL.chapter ? [+RL.chapter] : []); reload(); };
  const drop = $("#rl-drop");
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", async e => { if (e.dataTransfer.files.length) { await rlUpload(e.dataTransfer.files, RL.chapter ? [+RL.chapter] : []); reload(); } });
  drop.onclick = () => $("#rl-file").click();
  let tmr;
  $("#rl-q").oninput = e => { clearTimeout(tmr); tmr = setTimeout(() => { RL.q = e.target.value.trim(); reload(); }, 350); };
  $("#rl-kind").onchange = e => { RL.kind = e.target.value; reload(); };
  $("#rl-ch").onchange = e => { RL.chapter = e.target.value; reload(); };
  $("#rl-tag").onchange = e => { RL.tag = e.target.value; reload(); };
  $("#rl-arch").onchange = e => { RL.archived = e.target.checked; reload(); };
  $("#rl-clear").onclick = () => { RL.sel.clear(); reload(); };
  $("#rl-tour").onclick = () => tourStartGroup("research");
  wireRlList(el);
  const promptCopy = async kind => {
    const ch = $("#rl-pch").value;
    const r = await busy("Building the prompt…", () => api("/api/research/prompt", { kind, chapter: ch ? +ch : null, selection: [...RL.sel], query: RL.q }));
    toast(r.ok ? r.message : r.message, r.ok ? (r.omitted?.length ? "" : "good") : "bad", 9000);
  };
  $("#rl-review").onclick = () => promptCopy("review");
  $$("[data-pk]", el).forEach(b => b.onclick = () => promptCopy(b.dataset.pk));
  $("#rl-zip").onclick = async () => {
    const ids = [...new Set([...RL.sel].map(x => +String(x).split(":")[0]))];
    const r = await busy("Making the context ZIP…", () => api("/api/research/context-zip", { ids }));
    if (r.ok) { location.href = r.download; toast(`Context ZIP with ${r.sources} source(s) downloaded. Attach it in ChatGPT or Claude.`, "good", 7000); }
  };
  $("#rl-save-review").onclick = async () => {
    const ch = $("#rl-pch").value;
    const r = await api("/api/research/clipboard", { kind: "ai-review", chapters: ch ? [+ch] : [] });
    toast(r.ok ? `Saved “${r.source.title}” to the library as an AI review${r.source.duplicate ? " (already there)" : ""}. The manuscript wasn't changed.` : r.message, r.ok ? "good" : "bad", 7000);
    if (r.ok) reload();
  };
  if (RL.open) rlPreview(RL.open);
  data("research").then(r => {
    const files = f => f.files.length ? `<table class="tbl"><tbody>${f.files.slice(0, 80).map(x => `<tr><td>${esc(x.path)}</td><td>${fmtBytes(x.bytes)}</td><td>${fmtDate(x.mtime)}</td></tr>`).join("")}</tbody></table>${f.count > 80 ? `<p class="muted-note">and ${f.count - 80} more</p>` : ""}` : `<p class="muted-note">Empty.</p>`;
    const box = $("#rl-folders"); if (!box) return;
    box.innerHTML = `<p class="muted-note">Bibliography: ${r.bib.entries.length} entries, ${r.used} cited keys. Private sources: ${r.private.count} (never published).</p>
      <h4>sources/</h4>${r.sources.exists ? files(r.sources) : `<p class="muted-note">None.</p>`}<h4>sources-inbox/</h4>${r.inbox.exists ? files(r.inbox) : `<p class="muted-note">None.</p>`}`;
  }).catch(() => {});
};
function rlRows(xs) {
  if (!xs.length) return `<p class="muted-note">No sources here yet. Upload documents above; research you import on a chapter's Save reply tab is added automatically.</p>`;
  return `<ul class="rl-items">${xs.map(r => {
    const v = r.versions.at(-1);
    return `<li class="${RL.open === r.id ? "on" : ""}"><input type="checkbox" data-sel="${r.id}" ${RL.sel.has(String(r.id)) ? "checked" : ""} aria-label="Select source ${r.id}">
      <button class="rl-item" data-rlopen="${r.id}"><span class="rl-t"><span class="mono">S${r.id}</span> ${esc(r.title)}</span>
      <span class="rl-m"><span class="chip-s">${esc(({ upload: "Document", "ai-research": "AI research", "ai-review": "AI review", note: "Note" })[r.kind] || r.kind)}</span>
      <span class="chip-s">${esc(r.format)}</span>${v.status !== "ok" ? rlBadge(v.status) : ""}${r.archived ? `<span class="chip-s">archived</span>` : ""}
      ${r.chapters.length ? `<span class="muted-note">ch ${r.chapters.map(n => esc(num(byN(n) || { n }))).join(", ")}</span>` : ""}${r.tags.map(tg => `<span class="chip-s">#${esc(tg)}</span>`).join("")}</span></button></li>`;
  }).join("")}</ul>`;
}
function rlHits(hits) {
  if (!hits.length) return `<p class="muted-note">No matches. Try fewer words, or check the filters.</p>`;
  return `<p class="muted-note">${hits.length} matching section(s). Tick a section to include just that part in prompts.</p><ul class="rl-items">${hits.map(h => {
    const key = `${h.id}:${h.ref}`;
    return `<li class="${RL.open === h.id ? "on" : ""}"><input type="checkbox" data-sel="${esc(key)}" ${RL.sel.has(key) ? "checked" : ""} aria-label="Select ${esc(h.ref)} of source ${h.id}">
      <button class="rl-item" data-rlopen="${h.id}"><span class="rl-t"><span class="mono">S${h.id}</span> ${esc(h.title)} <span class="muted-note">· ${esc(h.ref)}</span></span>
      <span class="rl-x">${esc(h.excerpt).replace(/\[\[/g, "<mark>").replace(/\]\]/g, "</mark>")}</span></button></li>`;
  }).join("")}</ul>`;
}
function wireRlList(el) {
  $$("[data-sel]", el).forEach(c => c.onchange = () => { c.checked ? RL.sel.add(c.dataset.sel) : RL.sel.delete(c.dataset.sel); rlSelCount(); });
  $$(".rl-item[data-rlopen]", el).forEach(b => b.onclick = () => { RL.open = +b.dataset.rlopen; $$(".rl-items li", el).forEach(li => li.classList.toggle("on", li.contains(b))); rlPreview(RL.open); });
}
async function rlPreview(id) {
  const box = $("#rl-preview"); if (!box) return;
  let d;
  try { d = await api(`/api/research/source?id=${id}`); } catch { box.innerHTML = `<p class="muted-note">This source no longer exists.</p>`; RL.open = null; return; }
  const r = d.source, v = r.versions.at(-1);
  box.innerHTML = `
    <div class="sec-h"><input id="rl-title" value="${esc(r.title)}" aria-label="Title" class="grow"><span class="mono muted-note">Source ${r.id}</span></div>
    <p class="muted-note">${esc(v.name)} · ${fmtBytes(v.bytes)} · added ${fmtDate(v.added)} · version ${r.version} of ${r.versions.length} · ${rlBadge(v.status)}</p>
    ${v.note ? `<p class="alert ${v.status === "ok" ? "" : "warn"} small">${esc(v.note)}</p>` : ""}
    ${v.media?.length ? `<p class="small">${ic("triangle-alert")} Not indexed: ${v.media.map(esc).join("; ")}</p>` : ""}
    ${r.origin?.via ? `<p class="muted-note">Imported from ${esc(r.origin.assistant || "an AI")} via ${esc(r.origin.via)}.</p>` : ""}
    <div class="bkform">
      <label for="rl-chs">Chapters</label><select id="rl-chs" multiple size="5">${chapterOpts(r.chapters)}</select>
      <label for="rl-tags">Tags</label><input id="rl-tags" value="${esc(r.tags.join(", "))}" placeholder="comma, separated">
    </div>
    <div class="row" style="margin:8px 0">
      <button class="primary sm" id="rl-save">${ic("save")}Save</button>
      <a class="btn sm" href="/api/research/file?id=${r.id}" download>${ic("download")}Download original</a>
      <label class="btn sm" for="rl-ver">${ic("file-up")}New version</label><input type="file" id="rl-ver" class="hidden" accept="${RL_ACCEPT}">
      <button class="sm" id="rl-arch1">${r.archived ? "Unarchive" : "Archive"}</button>
      <button class="sm danger" id="rl-del">Delete…</button>
    </div>
    <h4>${d.segments.length} section(s) <span class="muted-note">tick sections to send only those</span></h4>
    <div class="rl-segs">${d.segments.map(s => { const key = `${r.id}:${s.ref}`; return `<details><summary><input type="checkbox" data-seg="${esc(key)}" ${RL.sel.has(key) ? "checked" : ""} aria-label="Select ${esc(s.ref)}"> <b>${esc(s.ref)}</b> <span class="muted-note">${esc(s.text.slice(0, 90))}…</span></summary><pre class="raw wrapraw">${esc(s.text)}</pre></details>`; }).join("") || `<p class="muted-note">No text was extracted. The original is kept; see the note above.</p>`}</div>`;
  $$("[data-seg]", box).forEach(c => { c.onclick = e => e.stopPropagation(); c.onchange = () => { c.checked ? RL.sel.add(c.dataset.seg) : RL.sel.delete(c.dataset.seg); rlSelCount(); }; });
  $("#rl-save").onclick = async () => {
    const chapters = [...$("#rl-chs").selectedOptions].map(o => +o.value);
    const tags = $("#rl-tags").value.split(",").map(x => x.trim()).filter(Boolean);
    await api("/api/research/update", { id: r.id, title: $("#rl-title").value, chapters, tags });
    toast("Saved.", "good"); renderPage();
  };
  $("#rl-ver").onchange = async e => { await rlUpload(e.target.files, [], r.id); renderPage(); };
  $("#rl-arch1").onclick = async () => { await api("/api/research/update", { id: r.id, archived: !r.archived }); renderPage(); };
  $("#rl-del").onclick = async () => {
    if (!await ask(`<h3>Delete “${esc(r.title)}”?</h3><p>It moves to the library's trash folder and stops appearing in search. The original file is kept on disk.</p>`, [["Cancel", false], ["Delete", true, "danger"]])) return;
    const x = await api("/api/research/delete", { id: r.id, confirm: true }); toast(x.message, "good", 6000); RL.open = null; RL.sel.delete(String(r.id)); renderPage();
  };
}
PAGES["research/bibliography"] = async el => {
  const r = await data("research");
  if (!r.bib.exists) { el.innerHTML = `<div class="page-h"><h2>Bibliography</h2></div>${card("references.bib", `<p class="muted-note">This book has no bibliography.</p>`)}`; return; }
  const dup = new Set(r.bib.duplicates), inc = new Set(r.bib.incomplete);
  el.innerHTML = `<div class="page-h"><h2>Bibliography</h2><span class="grow"></span><input type="search" id="bib-q" placeholder="Search ${r.bib.entries.length} entries" aria-label="Search the bibliography"></div>
    ${card(`references.bib <span class="small muted">${r.bib.entries.length} entries · ${dup.size} duplicate · ${inc.size} incomplete</span>`, `<table class="tbl"><thead><tr><th>Key</th><th>Author</th><th>Year</th><th>Title</th><th></th></tr></thead><tbody>
      ${r.bib.entries.map(e => `<tr data-t="${esc((e.key + " " + e.author + " " + e.title).toLowerCase())}"><td class="mono">${esc(e.key)}</td><td>${esc(e.author.slice(0, 60))}</td><td>${esc(e.year)}</td><td>${esc(e.title)}</td>
        <td>${dup.has(e.key) ? badge("fail") : inc.has(e.key) ? badge("warn") : ""}${e.doi || e.url ? `<a href="${esc(e.doi ? "https://doi.org/" + e.doi : e.url)}" target="_blank" rel="noopener">${ic("external-link")}</a>` : ""}</td></tr>`).join("")}</tbody></table>`)}`;
  $("#bib-q").oninput = e => { const q = e.target.value.toLowerCase(); $$("tr[data-t]", el).forEach(x => x.classList.toggle("hidden", !x.dataset.t.includes(q))); };
};
PAGES["research/audit"] = async el => {
  const r = await data("research", true);
  el.innerHTML = `<div class="page-h"><h2>Citation audit</h2></div>
    ${card("Cited but missing from references.bib", !r.bib.exists ? `<p class="muted-note">No bibliography in this book.</p>` : Object.keys(r.missingBy).length
      ? `<table class="tbl"><thead><tr><th>Chapter file</th><th>Missing keys</th></tr></thead><tbody>${Object.entries(r.missingBy).map(([p, ks]) => `<tr><td>${esc(p)}</td><td class="mono">${ks.map(esc).join(", ")}</td></tr>`).join("")}</tbody></table>`
      : `<p>${badge("pass")} All ${r.used} cited keys are in references.bib.</p>`)}
    ${card("Front-matter source lists that don't match", !r.bib.exists ? "" : Object.keys(r.metaMissing).length
      ? `<p class="muted-note">These keys are listed in a chapter's <code>sources:</code> front matter but aren't in references.bib. The text's own citations may still be correct; this only affects the metadata list.</p><table class="tbl"><thead><tr><th>Chapter file</th><th>Keys</th></tr></thead><tbody>${Object.entries(r.metaMissing).map(([p, ks]) => `<tr><td>${esc(p)}</td><td class="mono">${ks.map(esc).join(", ")}</td></tr>`).join("")}</tbody></table>`
      : `<p>${badge("pass")} Every listed key is in references.bib.</p>`)}
    ${card(`In references.bib but never cited <span class="small muted">${r.unused.length}</span>`, r.unused.length ? `<details><summary>Show keys</summary><p class="mono small">${r.unused.map(esc).join(", ")}</p></details>` : `<p class="muted-note">None.</p>`)}
    <p class="muted-note">Checks chapter front matter (<code>sources:</code>) and [@key] citations in the text. For the full build validation, run the format check in Overview › Book Health.</p>`;
};
PAGES["research/gaps"] = async el => {
  const r = await data("research");
  el.innerHTML = `<div class="page-h"><h2>Evidence gaps</h2></div>
    ${card(`[NEEDS SOURCE] markers <span class="small muted">${r.gaps.length}</span>`, r.gaps.length ? `<table class="tbl"><tbody>${r.gaps.map(g => `<tr><td>${esc(g.path)}:${g.line}</td><td>${esc(g.text)}</td></tr>`).join("")}</tbody></table>` : `<p>${badge("pass")} None in the manuscript.</p>`)}
    ${card("Sources still needed", r.neededDoc ? `<p><code>${esc(r.neededDoc)}</code> has <b>${r.neededOpen}</b> open checklist item(s).</p>` : `<p class="muted-note">No sources-needed list in this book.</p>`)}`;
};
PAGES["research/import"] = async el => {
  el.innerHTML = `<div class="page-h"><h2>Import sources</h2></div>
    ${card("Upload documents", `<p>PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), EPUB, OpenDocument, RTF, HTML, CSV, JSON, Markdown and text. Older .doc/.xls/.ppt files are kept but need re-saving in the newer format to be searched.</p>
      <div class="row"><select id="imp-ch" aria-label="Assign to chapter"><option value="">No chapter yet</option>${chapterOpts()}</select>
      <label class="btn primary" for="imp-file">${ic("upload")}Choose files</label><input type="file" id="imp-file" multiple accept="${RL_ACCEPT}" class="hidden"></div>`)}
    ${card("Research from ChatGPT or Claude", `<p>Research replies saved on a chapter's <b>Save reply</b> tab (pasted or ZIP) are archived here automatically, with the chapter, date and original. To keep any other reply (for example a research review), copy it and press:</p>
      <button id="imp-clip">${ic("clipboard-paste")}Save the clipboard to the library</button>`)}`;
  $("#imp-file").onchange = async e => { const ch = $("#imp-ch").value; const r = await rlUpload(e.target.files, ch ? [+ch] : []); if (r) { RL.open = r.added[0]?.id ?? null; bbGo("research", "sources", "p"); } };
  $("#imp-clip").onclick = async () => { const ch = $("#imp-ch").value; const r = await api("/api/research/clipboard", { kind: "ai-review", chapters: ch ? [+ch] : [] }); toast(r.ok ? `Saved “${r.source.title}”.` : r.message, r.ok ? "good" : "bad", 6000); };
};

// ---- AI Studio
PAGES["ai/review"] = el => {
  const waiting = S.chapters.filter(c => c.code === "claude"), revise = S.chapters.filter(c => c.code === "revise");
  const rows = (xs, code, label) => `<ul class="todo">${xs.map(c => `<li><span class="n">${esc(num(c))}</span><a href="#" data-go="${c.n}">${esc(c.title)}</a><span class="grow"></span><span class="muted-note">draft v${c.version}</span><button class="sm" data-step="${c.n}" data-code="${code}">${ic("clipboard-copy")}${label}</button></li>`).join("")}</ul>`;
  el.innerHTML = `<div class="page-h"><h2>AI review</h2></div>
    ${card(`Waiting on Claude's check <span class="small muted">${waiting.length}</span>`, waiting.length ? rows(waiting, "claude", "Copy check message") : `<p class="muted-note">No drafts are waiting for a check.</p>`)}
    ${card(`Needs revision <span class="small muted">${revise.length}</span>`, revise.length ? rows(revise, "revise", "Copy revision prompt") : `<p class="muted-note">Nothing to revise.</p>`)}
    <p class="muted-note">Claude's check results live in <code>reviews/</code>; the chapter editor's Claude check tab shows them.</p>`;
  wireChapterLinks(el);
  $$("[data-step]", el).forEach(b => b.onclick = async () => { const r = await api("/api/step", { n: +b.dataset.step, code: b.dataset.code }); toast(r.ok ? "Copied. Paste it into Claude Code or ChatGPT." : r.message, r.ok ? "good" : "bad", 5000); });
};
PAGES["ai/workflows"] = el => {
  const steps = [["Research", "Copy the research prompt into ChatGPT (web search on); import its reply or ZIP.", "chapters/editor"],
    ["Write", "Copy the writing prompt into the same chat; save ChatGPT's draft.", "chapters/editor"],
    ["Check", "Copy the check message into Claude Code; it checks the draft against sources and rules.", "ai/review"],
    ["Revise", "If Claude asks for changes, copy the revision prompt and save the new draft.", "ai/review"],
    ["Approve", "Approve the latest draft; it asks first.", "chapters/approvals"],
    ["Many at once", "Batch Operations runs the same step for a range of chapters.", "ai/batch"]];
  el.innerHTML = `<div class="page-h"><h2>Workflows</h2><span class="grow"></span><button class="primary" id="wf-tour">${ic("circle-help")}Start guided tutorial</button></div>
    ${card("Chapter workflow", `<ol class="flow">${steps.map(([t, d, l]) => `<li><b>${t}</b><span>${d}</span><a href="#/p/${l}">Open</a></li>`).join("")}</ol>`)}
    ${card("Custom workflows", planned("Defining your own step sequences.", "The pipeline (research, write, check, revise, approve) is built into the chapter tools today."))}`;
  $("#wf-tour").onclick = () => tourStart(0, true);
};

// ---- Design
// Brand Studio (tools/brand.py): the book's look and voice as tokens, applied to its outputs only.
const BS_STEPS = ["Vibe and voice", "Colors", "Typography", "Logo and icons", "Imagery", "Review and apply"];
PAGES["design/brand"] = async el => {
  const d = await api("/api/brand");
  BB.bs = BB.bs && BB.bs.book === projectPath() ? BB.bs : { book: projectPath(), step: 0, b: JSON.parse(JSON.stringify(d.brand)) };
  const S2 = BB.bs, b = S2.b, tok = d.tokens;
  const chk = list => list.map(c => `<li>${badge(c.status)}<span class="grow">${esc(c.what)} <span class="muted-note">${esc(c.pair)}</span></span><b>${c.ratio}:1</b><span class="muted-note">needs ${c.needed}:1</span></li>`).join("");
  const f = (id, label, val, hint = "", area = false) => `<label for="bs-${id}">${label}</label>${area ? `<textarea id="bs-${id}" rows="3" style="font-family:inherit">${esc(val || "")}</textarea>` : `<input id="bs-${id}" value="${esc(val || "")}">`}<span class="muted-note">${hint}</span>`;
  const steps = [
    () => `<div class="bkform">${f("vibe", "Vibe", b.vibe, "One sentence: how the book should feel.", true)}
      ${f("tone", "Tone", b.voice.tone, "For example: warm, plain, encouraging.")}${f("person", "Point of view", b.voice.person, "first, second or third person")}
      ${f("readingLevel", "Reading level", b.voice.readingLevel)}${f("avoid", "Avoid", b.voice.avoid, "Words, styles or clichés to stay away from.")}</div>
      <p class="muted-note">The voice is added to this book's writing prompts.</p>`,
    () => `<div class="colors">${Object.entries(tok.colors).map(([k, label]) => `<label class="color"><input type="color" data-col="${k}" value="${esc(b.colors[k] || "#000000")}"><span><b>${esc(label)}</b><span class="mono muted-note">${esc(k)} · ${esc(b.colors[k] || "—")}</span></span></label>`).join("")}</div>
      <h4>Contrast (WCAG)</h4><ul class="health" id="bs-checks">${chk(d.checks)}</ul>
      <p class="muted-note">Links on the website and in e-books automatically use a darker version of the accent when it's too light to read.</p>`,
    () => `<div class="bkform">${Object.entries(tok.fonts).map(([k, label]) => `${f("font-" + k, label, b.fonts[k], d.installed[b.fonts[k]] === false ? `<span class="st st-warn">Not installed in this book</span> Install it in ${link("design", "fonts", "Fonts")}.` : d.installed[b.fonts[k]] ? `<span class="st st-pass">Installed</span>` : "")}`).join("")}</div>
      <p class="muted-note">Any free Google Fonts family. Search and install them in Design › Fonts; until a font is installed the outputs use a similar fallback.</p>`,
    () => `<div class="assets3">${Object.entries(tok.assets).map(([k, label]) => { const path = b.assets[k] || (k === "cover" ? "assets/branding/cover.jpg" : ""); return `
      <figure><div class="asset-box">${path ? `<img src="/pfile/${esc(path)}?t=${Date.now()}" alt="${esc(label)}" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'muted-note',textContent:'None yet'}))">` : `<span class="muted-note">None yet</span>`}</div>
      <figcaption><b>${esc(label)}</b><br><label class="btn sm" for="bs-up-${k}">${ic("upload")}Upload</label><input type="file" id="bs-up-${k}" data-slot="${k}" accept=".png,.jpg,.jpeg,.webp" class="hidden"></figcaption></figure>`; }).join("")}</div>
      <p class="muted-note">PNG, JPEG or WebP. Replaced files are kept in assets/branding/.previous/. For AI-made artwork, use the image prompts in ${link("design", "images", "Image Prompts")}.</p>`,
    () => `<div class="bkform">${f("imagery", "Imagery treatment", b.imagery, "How illustrations and photos should look: style, palette, people, what to avoid. Used in image prompts.", true)}</div>`,
    () => `<table class="tbl"><tbody>
      <tr><th>Vibe</th><td>${esc(b.vibe || "—")}</td></tr>
      <tr><th>Voice</th><td>${esc([b.voice.tone, b.voice.person, b.voice.readingLevel].filter(Boolean).join(" · ") || "—")}</td></tr>
      <tr><th>Colors</th><td>${Object.keys(tok.colors).map(k => `<span class="swatch" title="${esc(k)}" style="background:${esc(b.colors[k] || "transparent")}"></span>`).join(" ")}</td></tr>
      <tr><th>Fonts</th><td>${esc(Object.values(b.fonts).filter(Boolean).join(" / "))}</td></tr>
      <tr><th>Last applied</th><td>${b.applied ? `${fmtDate(b.applied.at)} to ${esc(b.applied.targets.join(", "))}` : "never"}</td></tr></tbody></table>
      <h4>Apply to</h4><div class="row">${[["pdf", "PDF"], ["ebook", "EPUB and HTML"], ["website", "Website (next build)"]].map(([k, l]) => `<label class="chk"><input type="checkbox" data-tg="${k}" checked> ${l}</label>`).join("")}</div>
      <p class="muted-note">Applies to this book's outputs only, never to Book Builder's own screens. Rebuild afterwards to see it.</p>
      <div class="row"><button class="primary" id="bs-apply">${ic("swatch-book")}Save and apply</button></div>`,
  ];
  el.innerHTML = `<div class="page-h"><h2>Brand Studio</h2><span class="grow"></span><button class="linkbtn guide-btn" id="bs-tour">Guide me</button><span class="chip-s">This book only</span>
      <button id="bs-prompt" title="Copy a prompt asking ChatGPT or Claude to propose a brand">${ic("clipboard-copy")}Copy AI brand prompt</button>
      <button id="bs-sugg" title="Paste the AI's reply from the clipboard into the form">${ic("clipboard-paste")}Load AI suggestion</button></div>
    <ol class="wz-steps">${BS_STEPS.map((x, i) => `<li class="${i === S2.step ? "on" : i < S2.step ? "done" : ""}"><button data-bs="${i}">${i + 1}. ${x}</button></li>`).join("")}</ol>
    ${card(BS_STEPS[S2.step], steps[S2.step]())}
    <div class="row"><button id="bs-back" ${S2.step === 0 ? "disabled" : ""}>Back</button><span class="grow"></span>
      <button id="bs-save">${ic("save")}Save</button>${S2.step < BS_STEPS.length - 1 ? `<button class="primary" id="bs-next">Next</button>` : ""}</div>`;
  const collect = () => {
    const v = id => $(`#bs-${id}`)?.value;
    if ($("#bs-vibe")) { b.vibe = v("vibe"); Object.assign(b.voice, { tone: v("tone"), person: v("person"), readingLevel: v("readingLevel"), avoid: v("avoid") }); }
    $$("[data-col]", el).forEach(i => b.colors[i.dataset.col] = i.value.toUpperCase());
    Object.keys(tok.fonts).forEach(k => { if ($(`#bs-font-${k}`)) b.fonts[k] = v(`font-${k}`).trim(); });
    if ($("#bs-imagery")) b.imagery = v("imagery");
  };
  const goStep = i => { collect(); S2.step = Math.max(0, Math.min(BS_STEPS.length - 1, i)); renderPage(); };
  const saveAll = async () => { collect(); const r = await api("/api/brand/tokens", { vibe: b.vibe, voice: b.voice, colors: b.colors, fonts: b.fonts, imagery: b.imagery });
    toast(r.message, r.ok ? "good" : "bad", 5000); if (r.ok) { S2.b = JSON.parse(JSON.stringify(r.brand)); BB.cache.brand = null; } return r; };
  $$("[data-bs]", el).forEach(x => x.onclick = () => goStep(+x.dataset.bs));
  $("#bs-back").onclick = () => goStep(S2.step - 1);
  if ($("#bs-next")) $("#bs-next").onclick = () => goStep(S2.step + 1);
  $("#bs-save").onclick = async () => { await saveAll(); renderPage(); };
  $$("[data-col]", el).forEach(i => i.oninput = async () => { collect(); const r = await api("/api/brand/contrast", { colors: b.colors }); $("#bs-checks").innerHTML = chk(r.checks);
    i.closest(".color").querySelector(".mono").textContent = `${i.dataset.col} · ${i.value.toUpperCase()}`; });
  $$("[data-slot]", el).forEach(i => i.onchange = async () => { const file = i.files[0]; if (!file) return;
    const r = await api("/api/brand/asset", { slot: i.dataset.slot, name: file.name, data: await fileToB64(file) }); toast(r.message, r.ok ? "good" : "bad", 6000);
    if (r.ok) { b.assets[i.dataset.slot] = r.path; renderPage(); } });
  if ($("#bs-apply")) $("#bs-apply").onclick = async () => {
    const targets = $$("[data-tg]", el).filter(c => c.checked).map(c => c.dataset.tg);
    const s1 = await saveAll(); if (!s1.ok) return;
    const r = await busy("Applying the brand…", () => api("/api/brand/apply", { targets }));
    toast(r.message, r.ok ? "good" : "bad", 10000); BB.bs = null; renderPage();
  };
  $("#bs-tour").onclick = () => tourStartGroup("brand");
  $("#bs-prompt").onclick = async () => { const r = await api("/api/brand/prompt", {}); toast(r.message, "good", 7000); };
  $("#bs-sugg").onclick = async () => {
    const r = await api("/api/brand/suggestion", {});
    if (!r.ok) return toast(r.message, "bad", 8000);
    const s = r.suggestion;
    if (s.vibe) b.vibe = s.vibe; if (s.imagery) b.imagery = s.imagery;
    Object.assign(b.voice, s.voice); Object.assign(b.colors, s.colors); Object.assign(b.fonts, s.fonts);
    toast(r.message, "good", 7000); renderPage();
  };
};
PAGES["design/fonts"] = async el => {
  const b = await data("brand", true);
  el.innerHTML = `<div class="page-h"><h2>Fonts</h2><span class="grow"></span><span class="chip-s">Project setting</span></div>
    ${card("This book's fonts", `<div class="bkform">${["display", "body", "ui"].filter(k => k in b.fonts).map(k => `
      <label for="fr-${k}">${{ display: "Titles and headings", body: "Body text", ui: "Captions and callouts" }[k]}</label>
      <select id="fr-${k}">${[...new Set([b.fonts[k], ...b.installed])].map(f => `<option ${f === b.fonts[k] ? "selected" : ""}>${esc(f)}</option>`).join("")}</select>`).join("")}</div>
      <div class="row" style="margin-top:10px"><button class="primary" id="fr-save">${ic("save")}Use these fonts in the PDF</button></div>
      <p class="muted-note">Only fonts installed in this book's <code>assets/fonts</code> are offered, so the PDF build can always find them.</p>`)}
    ${card("Google Fonts", `<div class="row"><input type="search" id="gf-q" placeholder="Search the free Google Fonts catalog" style="flex:1;min-width:240px" aria-label="Search Google Fonts">
      <select id="gf-cat" aria-label="Category"><option value="">All categories</option><option>Serif</option><option>Sans Serif</option><option>Display</option><option>Handwriting</option><option>Monospace</option></select></div>
      <p class="muted-note" id="gf-note">Loading the catalog…</p><div id="gf-list" class="gf-list"></div>`)}`;
  $("#fr-save").onclick = async () => {
    const fonts = Object.fromEntries(["display", "body", "ui"].filter(k => $(`#fr-${k}`)).map(k => [k, $(`#fr-${k}`).value]));
    const r = await api("/api/brand/save", { fonts }); toast(r.message, r.ok ? "good" : "bad", 6000); BB.cache.brand = null;
  };
  const cat = await api("/api/fonts/catalog");
  $("#gf-note").textContent = `${cat.families.length} families · ${cat.source === "google" ? "from Google Fonts" : cat.source === "cache" ? "cached copy of the Google Fonts catalog" : "built-in list"}${cat.note ? ". " + cat.note : ""}`;
  const draw = () => {
    const q = $("#gf-q").value.toLowerCase(), c = $("#gf-cat").value;
    const xs = cat.families.filter(f => (!q || f.family.toLowerCase().includes(q)) && (!c || f.category === c)).slice(0, 60);
    $("#gf-list").innerHTML = xs.map(f => `<div class="gf"><span class="grow"><b>${esc(f.family)}</b> <span class="muted-note">${esc(f.category)}${f.variants ? ` · ${f.variants} styles` : ""}</span></span>
      ${b.installed.includes(f.family) ? `<span class="chip-s on">Installed</span>` : `<button class="sm" data-install="${esc(f.family)}">${ic("download")}Install</button>`}</div>`).join("") || `<p class="muted-note">No matches.</p>`;
    $$("[data-install]", el).forEach(btn => btn.onclick = async () => {
      const r = await busy(`Installing ${btn.dataset.install}…`, () => api("/api/fonts/install", { family: btn.dataset.install }));
      toast(r.message, r.ok ? "good" : "bad", 6000); if (r.ok) { BB.cache.brand = null; renderPage(); }
    });
  };
  $("#gf-q").oninput = draw; $("#gf-cat").onchange = draw; draw();
};
PAGES["design/graphics"] = async el => {
  const a = await data("assets", true);
  const thumbs = xs => xs.length ? `<div class="thumbs">${xs.map(x => `<figure><img src="/pfile/${esc(x.path)}" alt="" loading="lazy"><figcaption>${esc(x.path.split("/").pop())}<br><span class="muted-note">${fmtBytes(x.bytes)}</span></figcaption></figure>`).join("")}</div>` : `<p class="muted-note">None.</p>`;
  const g = a.groups;
  el.innerHTML = `<div class="page-h"><h2>Graphics and assets</h2></div>
    <div class="metrics"><div class="metric"><span>Images in chapters</span><b>${a.used.length}</b></div>
      <div class="metric ${a.brokenRefs.length ? "m-fail" : ""}"><span>Broken references</span><b>${a.brokenRefs.length}</b></div>
      <div class="metric ${a.noAlt.length ? "m-warn" : ""}"><span>Missing alt text</span><b>${a.noAlt.length}</b></div>
      <div class="metric"><span>Licensing records</span><b class="small-b">${a.credits ? esc(a.credits) : "none"}</b></div></div>
    ${card("Cover", g.cover.length ? thumbs(g.cover) : `<p>${badge("fail")} No cover image. Add <code>assets/branding/cover.jpg</code>.</p>`)}
    <div class="grid2">${card("Back cover", g.back.length ? thumbs(g.back) : `<p class="muted-note">No back cover (only needed for print).</p>`)}${card("Spine", g.spine.length ? thumbs(g.spine) : `<p class="muted-note">No spine art (print only; size depends on the page count).</p>`)}</div>
    ${card("Logo and branding", thumbs(g.logo))}
    ${card("Chapter illustrations and diagrams", thumbs([...g.illustrations, ...g.other]))}
    ${a.brokenRefs.length || a.noAlt.length ? card("Problems", `<table class="tbl"><tbody>${[...a.brokenRefs.map(i => [i, "fail", "File not found"]), ...a.noAlt.map(i => [i, "warn", "No alt text"])].map(([i, s, t]) => `<tr><td>${badge(s)}</td><td>${esc(i.chapter)}</td><td class="mono">${esc(i.src)}</td><td>${t}</td></tr>`).join("")}</tbody></table>`) : ""}
    ${card("Image licensing", `<p>Credit, license, alt text, sources and approval for each book image are kept in ${link("design", "images", "the Image Studio")}; <b>Export approved</b> there includes a credits.csv.</p>`)}
    <p class="muted-note">Image prompts for chapters are in ${link("design", "images", "Image Prompts")}.</p>`;
};
PAGES["design/layout"] = async el => {
  const d = await data("dashboard", true); const b = d.book;
  const keys = ["papersize", "fontsize", "margin.inside", "margin.outside", "margin.top", "margin.bottom"];
  el.innerHTML = `<div class="page-h"><h2>Interior layout</h2><span class="grow"></span><button class="primary" id="il-save">${ic("save")}Save</button></div>
    ${card("Page", `<div class="bkform">${fieldHtml(DETAIL_GROUPS[4][1][0], b)}${fieldHtml(DETAIL_GROUPS[4][1][1], b)}
      ${[["margin.inside", "Inside margin", "Binding side"], ["margin.outside", "Outside margin"], ["margin.top", "Top margin"], ["margin.bottom", "Bottom margin"]].map(f => fieldHtml(f, b)).join("")}</div>
      <p class="muted-note">Saved in book.yml; used by the PDF. Rebuild to see changes.</p>`)}
    ${card("Contents and navigation", `<p>Contents style (simple or detailed), PDF bookmarks and links are chosen when you build. ${link("build", "settings", "Build settings")}</p>`)}`;
  $("#il-save").onclick = () => saveFields(keys);
};
PAGES["design/previews"] = async el => {
  const d = await data("dashboard");
  el.innerHTML = `<div class="page-h"><h2>Previews</h2></div>
    <div class="previews big">
      <figure>${d.cover ? `<img src="/pfile/${esc(d.cover)}" alt="Front cover">` : `<span class="cover-ph">${ic("image")}<span>No cover</span></span>`}<figcaption>Front cover</figcaption></figure>
      <figure><span class="cover-ph">${ic("file-type")}<span>${d.pdf ? esc(d.pdf.name) : "No PDF yet"}</span></span><figcaption>${d.pdf ? `<button data-open-file="${esc(d.pdf.path)}">Open the PDF</button>` : "Build a PDF to preview the interior"}</figcaption></figure>
    </div>
    ${card("Website", `<p>Preview the reader website from ${link("website", "preview", "Website › Site Preview")}.</p>`)}`;
  wireOpen(el);
};
// Image Studio (tools/images.py): plan → prompt → import → review → approve. No AI is called from here.
const IS = { sel: new Set(), open: null, status: "", chapter: "" };
const IS_BADGE = { proposed: ["unchecked", "Proposed"], prompted: ["unchecked", "Prompt sent"], imported: ["warn", "Needs review"], approved: ["pass", "Approved"], rejected: ["fail", "Rejected"] };
PAGES["design/images"] = async el => {
  const d = await api("/api/images");
  const recs = d.images.filter(r => (!IS.status || r.status === IS.status) && (!IS.chapter || String(r.chapter) === IS.chapter));
  const count = s => d.images.filter(r => r.status === s).length;
  el.innerHTML = `<div class="page-h"><h2>Image Studio</h2><span class="grow"></span><button class="linkbtn guide-btn" id="is-tour">Guide me</button>
      <button id="is-plan" title="A book-wide visual plan prompt">${ic("clipboard-copy")}Copy visual plan prompt</button>
      <button id="is-add">${ic("plus")}Add image</button></div>
    <div class="rl-selbar">
      <select id="is-pch" aria-label="Chapter for the image review prompt"><option value="">Chapter…</option>${chapterOpts()}</select>
      <button id="is-chp">${ic("clipboard-check")}Copy chapter image prompt</button>
      <button id="is-imp" title="Paste ChatGPT's or Claude's JSON reply with image proposals">${ic("clipboard-paste")}Import proposals from clipboard</button>
      <span class="grow"></span>
      <b id="is-count">${IS.sel.size ? `${IS.sel.size} selected` : "Nothing selected"}</b>
      <button id="is-pack" ${IS.sel.size ? "" : "disabled"}>${ic("package")}Image request ZIP</button>
      <label class="btn" for="is-ret">${ic("file-up")}Import returned images</label><input type="file" id="is-ret" accept=".zip" class="hidden">
      <button id="is-exp" ${count("approved") ? "" : "disabled"}>${ic("download")}Export approved</button>
    </div>
    <div class="chips" style="margin-bottom:10px"><button class="chip ${IS.status ? "" : "on"}" data-st="">All <b>${d.images.length}</b></button>
      ${d.statuses.map(s => `<button class="chip ${IS.status === s ? "on" : ""}" data-st="${s}">${IS_BADGE[s][1]} <b>${count(s)}</b></button>`).join("")}
      <select id="is-ch" aria-label="Filter by chapter"><option value="">All chapters</option>${S.chapters.map(c => `<option value="${c.n}" ${IS.chapter === String(c.n) ? "selected" : ""}>${esc(num(c))} · ${esc(c.title)}</option>`).join("")}</select></div>
    <div class="rl-grid"><div class="card rl-list">${recs.length ? `<ul class="rl-items">${recs.map(r => { const v = r.versions.at(-1); return `
      <li class="${IS.open === r.id ? "on" : ""}"><input type="checkbox" data-isel="${r.id}" ${IS.sel.has(r.id) ? "checked" : ""} aria-label="Select ${esc(r.title)}">
        <span class="is-thumb">${v ? `<img src="/pfile/${esc(v.path)}" alt="" loading="lazy">` : ic(r.kind === "diagram" ? "chart-column" : "image")}</span>
        <button class="rl-item" data-iopen="${r.id}"><span class="rl-t">${esc(r.title)}</span>
        <span class="rl-m"><span class="st st-${IS_BADGE[r.status][0]}">${IS_BADGE[r.status][1]}</span><span class="chip-s">${esc(d.kinds[r.kind])}</span>${r.chapter ? `<span class="muted-note">ch ${esc(num(byN(r.chapter) || { n: r.chapter }))}</span>` : ""}</span>
        ${r.problems.length && r.status !== "proposed" ? `<span class="rl-x">${esc(r.problems[0])}</span>` : ""}</button></li>`; }).join("")}</ul>`
      : `<p class="muted-note">No images planned yet. Copy the visual plan prompt or a chapter image prompt, paste it into ChatGPT or Claude, then import its proposals here.</p>`}</div>
      <div class="card rl-preview" id="is-detail"><p class="muted-note">Choose an image to edit its prompt, alt text, caption, credit and license, add files, and review it.</p></div></div>
    <p class="muted-note">Flow: proposal → prompt sent (image request ZIP) → imported → reviewed → approved. Factual diagrams must cite sources. Placing an image in a chapter is your choice: copy its Markdown snippet into the chapter.</p>`;
  const re = () => renderPage();
  $$("[data-st]", el).forEach(b => b.onclick = () => { IS.status = b.dataset.st; re(); });
  $("#is-ch").onchange = e => { IS.chapter = e.target.value; re(); };
  $$("[data-isel]", el).forEach(c => c.onchange = () => { c.checked ? IS.sel.add(c.dataset.isel) : IS.sel.delete(c.dataset.isel); re(); });
  $$("[data-iopen]", el).forEach(b => b.onclick = () => { IS.open = b.dataset.iopen; isDetail(d); $$(".rl-items li", el).forEach(li => li.classList.toggle("on", li.contains(b))); });
  $("#is-tour").onclick = () => tourStartGroup("images");
  $("#is-plan").onclick = async () => toast((await api("/api/images/plan-prompt", {})).message, "good", 7000);
  $("#is-chp").onclick = async () => { const r = await busy("Building the prompt…", () => api("/api/images/chapter-prompt", { chapter: $("#is-pch").value })); toast(r.message, r.ok ? "good" : "bad", 8000); };
  $("#is-imp").onclick = async () => { const r = await api("/api/images/import-proposals", {}); toast(r.message, r.ok ? "good" : "bad", 8000); if (r.ok) re(); };
  $("#is-add").onclick = async () => { const r = await api("/api/images/add", { title: "New image", kind: "illustration", chapter: IS.chapter || null }); IS.open = r.image.id; re(); };
  $("#is-pack").onclick = async () => { const r = await api("/api/images/pack", { ids: [...IS.sel] }); if (!r.ok) return toast(r.message, "bad"); location.href = r.download; toast(`Image request ZIP for ${r.images} image(s) downloaded. Attach it in ChatGPT, then import the images it returns.`, "good", 9000); re(); };
  $("#is-ret").onchange = async e => { const f = e.target.files[0]; if (!f) return; const r = await busy("Importing images…", async () => api("/api/images/import-return", { data: await fileToB64(f) }));
    toast(r.message + (r.skipped?.length ? ` Skipped: ${r.skipped.slice(0, 3).join("; ")}` : ""), r.ok ? "good" : "bad", 10000); re(); };
  $("#is-exp").onclick = async () => { const r = await api("/api/images/export", {}); location.href = r.download; toast(`Exported ${r.images} approved image(s) with credits.csv.`, "good", 7000); };
  if (IS.open) isDetail(d);
};
function isDetail(d) {
  const r = d.images.find(x => x.id === IS.open), box = $("#is-detail");
  if (!r || !box) return;
  const v = r.versions.at(-1);
  const fld = (k, label, area = false, hint = "") => `<label for="is-${k}">${label}</label>${area ? `<textarea id="is-${k}" rows="${k === "prompt" ? 5 : 2}" style="font-family:inherit">${esc(r[k] || "")}</textarea>` : `<input id="is-${k}" value="${esc(r[k] || "")}">`}<span class="muted-note">${hint}</span>`;
  box.innerHTML = `${v ? `<div class="is-big"><img src="/pfile/${esc(v.path)}" alt="${esc(r.alt)}"></div><p class="muted-note">Version ${v.v} of ${r.versions.length} · ${v.width || "?"}×${v.height || "?"} px · ${esc(v.source)}</p>` : `<p class="muted-note">No image file yet.</p>`}
    <div class="bkform">${fld("title", "Title")}
      <label for="is-kind">Kind</label><select id="is-kind">${Object.entries(d.kinds).map(([k, l]) => `<option value="${k}" ${r.kind === k ? "selected" : ""}>${l}</option>`).join("")}</select><span></span>
      <label for="is-chapter">Chapter</label><select id="is-chapter"><option value="">None</option>${chapterOpts(r.chapter ? [r.chapter] : [])}</select><span></span>
      ${fld("purpose", "Purpose", true)}${fld("prompt", "Image prompt", true)}${fld("alt", "Alt text", false, "What matters in the image, under 150 characters.")}
      ${fld("caption", "Caption", false, r.kind === "diagram" ? "Cite the sources here." : "")}
      <label for="is-sources">Sources</label><input id="is-sources" value="${esc(r.sources.join(", "))}"><span class="muted-note">${r.kind === "diagram" ? "Required for diagrams, for example Source 3, Page 4." : "Optional."}</span>
      ${fld("placement", "Placement")}${fld("credit", "Credit", false, "Who or what made it.")}${fld("license", "License", false, "For example: author owns, CC BY 4.0.")}</div>
    <div class="row" style="margin:8px 0"><button class="primary sm" id="is-save">${ic("save")}Save</button>
      <label class="btn sm" for="is-file">${ic("upload")}${v ? "New version" : "Add image file"}</label><input type="file" id="is-file" accept=".png,.jpg,.jpeg,.webp" class="hidden">
      ${r.markdown ? `<button class="sm" id="is-md">${ic("clipboard-copy")}Copy Markdown</button>` : ""}
      <button class="sm" id="is-rej">${r.status === "rejected" ? "Restore" : "Reject"}</button><button class="sm danger" id="is-del">Remove…</button></div>
    <h4>Review</h4><ul class="health">${r.checklist.map(c => `<li><label class="chk"><input type="checkbox" data-chk="${esc(c)}" ${r.checks[c] ? "checked" : ""}> ${esc(c)}</label></li>`).join("")}</ul>
    ${r.status === "approved" ? `<p>${badge("pass")} Approved.</p><button class="sm" id="is-unapp">Remove approval</button>`
      : `${r.problems.length ? `<ul class="plain">${r.problems.map(p => `<li class="small">${ic("circle-alert")} ${esc(p)}</li>`).join("")}</ul>` : ""}<button class="primary sm" id="is-app" ${r.problems.length ? "disabled" : ""}>${ic("circle-check")}Approve</button>`}`;
  const fields = () => ({ id: r.id, title: $("#is-title").value, kind: $("#is-kind").value, chapter: $("#is-chapter").value, purpose: $("#is-purpose").value,
    prompt: $("#is-prompt").value, alt: $("#is-alt").value, caption: $("#is-caption").value, sources: $("#is-sources").value.split(",").map(s => s.trim()).filter(Boolean),
    placement: $("#is-placement").value, credit: $("#is-credit").value, license: $("#is-license").value,
    checks: Object.fromEntries($$("[data-chk]", box).map(c => [c.dataset.chk, c.checked])) });
  $("#is-save").onclick = async () => { await api("/api/images/update", fields()); toast("Saved.", "good"); renderPage(); };
  $$("[data-chk]", box).forEach(c => c.onchange = async () => { await api("/api/images/update", { id: r.id, checks: fields().checks }); renderPage(); });
  $("#is-file").onchange = async e => { const f = e.target.files[0]; if (!f) return; await api("/api/images/update", fields());
    const x = await api("/api/images/upload", { id: r.id, name: f.name, data: await fileToB64(f), source: "upload" }); toast(x.message, x.ok ? "good" : "bad", 7000); renderPage(); };
  if ($("#is-md")) $("#is-md").onclick = async () => { await api("/api/copy", { text: r.markdown }); toast("Copied the Markdown snippet. Paste it into the chapter where the image belongs.", "good", 7000); };
  $("#is-rej").onclick = async () => { await api("/api/images/update", { id: r.id, status: r.status === "rejected" ? "proposed" : "rejected" }); renderPage(); };
  $("#is-del").onclick = async () => { if (await ask(`<h3>Remove “${esc(r.title)}”?</h3><p>It leaves the plan; its image files stay in images/files/.</p>`, [["Cancel", false], ["Remove", true, "danger"]])) { await api("/api/images/delete", { id: r.id, confirm: true }); IS.open = null; IS.sel.delete(r.id); renderPage(); } };
  if ($("#is-app")) $("#is-app").onclick = async () => { await api("/api/images/update", fields()); const x = await api("/api/images/approve", { id: r.id }); toast(x.message, x.ok ? "good" : "bad", 7000); renderPage(); };
  if ($("#is-unapp")) $("#is-unapp").onclick = async () => { await api("/api/images/approve", { id: r.id, approved: false }); renderPage(); };
}

// ---- Build
function outputsTable(outs) {
  return card("Files", outs.length ? `<table class="tbl"><thead><tr><th>File</th><th>Format</th><th>Size</th><th>Built</th><th></th></tr></thead><tbody>
    ${outs.map(o => `<tr><td>${esc(o.name)}${o.current ? "" : ` <span class="chip-s">older name</span>`}${o.sha256 ? `<br><span class="mono muted-note" title="SHA-256 ${esc(o.sha256)}">${esc(o.sha256.slice(0, 12))}</span>` : ""}
        ${o.preflight?.length ? `<details class="small"><summary><span class="st st-warn">${o.preflight.length} warning(s)</span></summary><ul>${o.preflight.map(w => `<li>${esc(w)}</li>`).join("")}</ul></details>` : ""}</td><td>${o.format}</td><td>${fmtBytes(o.bytes)}</td><td>${bbWhen(o.mtime)}</td>
      <td class="nowrap"><button class="sm" data-open-file="${esc(o.path)}">Open</button> <button class="sm" data-reveal-file="${esc(o.path)}">Show in Finder</button></td></tr>`).join("")}</tbody></table>`
    : `<p class="muted-note">Nothing built yet. ${link("build", "settings", "Build the book")}</p>`);
}
function wireOpen(el) {
  $$("[data-open-file]", el).forEach(b => b.onclick = () => api("/api/open", { path: b.dataset.openFile }));
  $$("[data-reveal-file]", el).forEach(b => b.onclick = () => api("/api/open", { path: b.dataset.revealFile, reveal: true }));
}
function formatPage(fmt, label, note) {
  return async el => {
    const a = await data("activity", true), d = await data("dashboard");
    const outs = a.outputs.filter(o => o.format === label);
    const cur = outs.find(o => o.current);
    const h = Object.values(d.health.categories).flat().filter(i => i.link === `build/${fmt}`);
    el.innerHTML = `<div class="page-h"><h2>${label}</h2><span class="grow"></span><button class="primary" id="fmt-build">${ic("hammer")}Build ${label}</button></div>
      ${h.length ? card("Status", `<ul class="health">${h.map(i => `<li>${badge(i.status)}<span class="grow"><b>${esc(i.label)}</b> <span class="muted-note">${esc(i.detail)}</span></span></li>`).join("")}</ul>`) : ""}
      ${cur && label === "PDF" && d.pages ? `<p>${d.pages} pages · ${fmtBytes(cur.bytes)} · built ${bbWhen(cur.mtime)}</p>` : ""}
      ${outputsTable(outs)}${note ? `<p class="muted-note">${note}</p>` : ""}`;
    wireOpen(el);
    $("#fmt-build").onclick = async () => {
      const r = await busy(`Building the ${label}…`, () => api("/api/build", { formats: [fmt] }));
      toast(r.ok === false ? (r.message || "Build failed; see Build Settings for the log.") : `${label} built.`, r.ok === false ? "bad" : "good", 6000);
      BB.cache = {}; renderPage();
    };
  };
}
PAGES["build/pdf"] = formatPage("pdf", "PDF", "Contents style, bookmarks and links are set in Build Settings.");
PAGES["build/epub"] = formatPage("epub", "EPUB", "EPUB files aren't validated: install epubcheck to enable validation.");
PAGES["build/docx"] = formatPage("docx", "DOCX", "Word files are for editing and review, not final layout.");
PAGES["build/export"] = async el => {
  const a = await data("activity", true);
  el.innerHTML = `<div class="page-h"><h2>Export center</h2></div>${outputsTable(a.outputs)}
    ${card("Other exports", `<ul class="plain"><li>${ic("message-square")} ChatGPT project files: ${link("ai", "handoff", "AI Studio › ChatGPT Handoff")}</li>
      <li>${ic("gamepad-2")} Game packages: ${link("interactive", "games", "Interactive › Games")} (each game's More menu)</li>
      <li>${ic("package")} Website ZIP: ${link("website", "zip", "Website › Website ZIP")}</li></ul>`)}`;
  wireOpen(el);
};
PAGES["build/kindle"] = async el => {
  const a = await data("activity");
  const epub = a.outputs.find(o => o.format === "EPUB" && o.current);
  el.innerHTML = `<div class="page-h"><h2>Send to Kindle</h2></div>
    ${card("Send the EPUB yourself", `<ol class="flow">
      <li><b>Build the EPUB</b><span>${epub ? `Ready: ${esc(epub.name)} (${bbWhen(epub.mtime)}).` : "No EPUB yet."}</span>${epub ? `<button class="sm" data-reveal-file="${esc(epub.path)}">Show in Finder</button>` : `<a href="#/p/build/epub">Build</a>`}</li>
      <li><b>Open Send to Kindle</b><span>Amazon's page at amazon.com/sendtokindle, or the Kindle app's Send to Kindle option.</span><a href="https://www.amazon.com/sendtokindle" target="_blank" rel="noopener">Open</a></li>
      <li><b>Drop in the EPUB</b><span>Amazon converts it; it appears in your Kindle library.</span></li></ol>`)}
    <div id="kd-email"></div>`;
  wireOpen(el);
  const k = await api("/api/kindle"), s = k.settings;
  const sendable = a.outputs.filter(o => o.current && ["EPUB", "PDF", "DOCX"].includes(o.format));
  $("#kd-email").innerHTML = card("Send by email (optional)", `
    <p class="muted-note" style="margin-top:0">Uses your own mail account to email the file to your Kindle address. Off until you turn it on. The password stays on this computer (${navigator.platform.startsWith("Mac") ? "macOS Keychain" : "a file only your account can read"}) and is never shown again. Add the sender address to Amazon's <i>Approved Personal Document E-mail List</i> first.</p>
    <div class="bkform">
      <label>Turned on</label><label class="chk"><input type="checkbox" id="kd-on" ${s.enabled ? "checked" : ""}> Allow sending books to my Kindle by email</label><span></span>
      <label for="kd-kindle">Kindle address</label><input id="kd-kindle" value="${esc(s.kindle)}" placeholder="name_123@kindle.com"><span class="muted-note">Amazon › Manage Your Content and Devices › Preferences.</span>
      <label for="kd-sender">Send from</label><input id="kd-sender" value="${esc(s.sender)}" placeholder="you@example.com"><span></span>
      <label for="kd-host">Mail server</label><input id="kd-host" value="${esc(s.host)}" placeholder="smtp.example.com"><span></span>
      <label for="kd-port">Port and security</label><div class="row"><input id="kd-port" value="${s.port}" style="width:90px"><select id="kd-sec"><option value="starttls" ${s.security === "starttls" ? "selected" : ""}>STARTTLS (587)</option><option value="ssl" ${s.security === "ssl" ? "selected" : ""}>SSL (465)</option></select></div><span></span>
      <label for="kd-user">User name</label><input id="kd-user" value="${esc(s.user)}"><span></span>
      <label for="kd-pw">Password</label><input id="kd-pw" type="password" autocomplete="new-password" placeholder="${s.passwordStored ? "Stored. Type to replace it" : "App password from your mail provider"}"><span class="muted-note">${s.passwordStored ? `${badge("pass")} stored <button class="ghost sm" id="kd-forget">Forget it</button>` : "Gmail, iCloud and Outlook need an app password."}</span>
    </div>
    <div class="row" style="margin:10px 0"><button class="primary" id="kd-save">${ic("save")}Save</button><button id="kd-test" ${s.enabled ? "" : "disabled"}>Test sign-in (sends nothing)</button></div>
    <h4>Send</h4>
    ${sendable.length ? `<div class="row"><select id="kd-file">${sendable.map(o => `<option value="${esc(o.name)}">${esc(o.name)} · ${fmtBytes(o.bytes)}${o.stale ? " · out of date" : ""}</option>`).join("")}</select>
      <button class="primary" id="kd-send" ${s.enabled && s.kindle ? "" : "disabled"}>${ic("mail")}Send to my Kindle…</button></div>` : `<p class="muted-note">Build an EPUB first.</p>`}
    ${k.history.length ? `<details style="margin-top:10px"><summary class="small">Recent sends</summary><ul class="plain small">${k.history.slice().reverse().map(h => `<li>${bbWhen(h.time)} · ${esc(h.file)} · ${esc({ "sent-to-server": "accepted by mail server", refused: "refused", failed: "failed" }[h.status] || h.status)}${h.error ? `: ${esc(h.error)}` : ""}</li>`).join("")}</ul></details>` : ""}`);
  const form = () => ({ enabled: $("#kd-on").checked, kindle: $("#kd-kindle").value, sender: $("#kd-sender").value, host: $("#kd-host").value,
    port: $("#kd-port").value, security: $("#kd-sec").value, user: $("#kd-user").value, ...($("#kd-pw").value ? { password: $("#kd-pw").value } : {}) });
  $("#kd-save").onclick = async () => { const r = await api("/api/kindle/save", form()); $("#kd-pw").value = ""; toast(r.message, r.ok ? "good" : "bad", 7000); if (r.ok) renderPage(); };
  if ($("#kd-forget")) $("#kd-forget").onclick = async () => { const r = await api("/api/kindle/save", { ...form(), forgetPassword: true }); toast("Password forgotten.", "good"); renderPage(); };
  $("#kd-test").onclick = async () => { const r = await busy("Signing in to the mail server…", () => api("/api/kindle/test", {})); toast(r.message, r.ok ? "good" : "bad", 8000); };
  if ($("#kd-send")) $("#kd-send").onclick = async () => {
    const f = $("#kd-file").value;
    if (!await ask(`<h3>Send to your Kindle?</h3><p><b>${esc(f)}</b> will be emailed from ${esc(s.sender)} to ${esc(s.kindle)} through ${esc(s.host)}.</p>`, [["Cancel", false], ["Send", true, "primary"]])) return;
    const r = await busy("Sending…", () => api("/api/kindle/send", { file: f, confirm: true }));
    toast(r.message, r.ok ? "good" : "bad", 12000); renderPage();
  };
};
PAGES["build/history"] = async el => {
  const a = await data("activity", true);
  el.innerHTML = `<div class="page-h"><h2>Build history</h2></div>${outputsTable(a.outputs)}<p class="muted-note">Each build replaces the file of the same name, so this shows the latest build of each file.</p>`;
  wireOpen(el);
};

// ---- Website
PAGES["website/layout"] = async el => {
  const b = await data("brand");
  el.innerHTML = `<div class="page-h"><h2>Website layout</h2></div>
    ${card("website.yml", b.website ? `<pre class="log">${esc(b.website)}</pre>` : `<p class="muted-note">This book has no website.yml.</p>`)}
    ${card("Pages and theme", `<p>The reader site is an Astro project in <code>site/</code>: home, reading pages, guides, activities, references, resources, search and about.</p>
      ${planned("Choosing page layouts and theme colors here.", "Needs the site stylesheet to read the book's brand tokens.")}`)}`;
};
// Hosting (tools/hosting.py): profiles and domain saved in website.yml; ZIP for any static host.
async function hostingForm(el, focus) {
  const h = await api("/api/hosting"), s = h.settings;
  const opts = Object.entries(h.providers).map(([k, l]) => `<option value="${k}" ${s.provider === k ? "selected" : ""}>${esc(l)}</option>`).join("");
  el.innerHTML = `<div class="page-h"><h2>${focus === "domain" ? "Domain" : "Custom hosting"}</h2></div>
    ${!h.publishing ? `<p class="alert warn">${esc(h.publishingNote)}</p>` : ""}
    ${card("Where the website lives", `<div class="bkform">
      <label for="ho-prov">Host</label><select id="ho-prov">${opts}</select><span class="muted-note">GitHub Pages is published by Book Builder; the others take the Website ZIP.</span>
      <label for="ho-dom">Custom domain</label><input id="ho-dom" value="${esc(s.domain)}" placeholder="books.example.com"><span class="muted-note">Optional. For GitHub Pages a CNAME file is added on the next publish; your DNS needs a CNAME record pointing at the host.</span>
      <label for="ho-base">ZIP path</label><input id="ho-base" value="${esc(s.zip_base)}"><span class="muted-note">Where a Website ZIP will be uploaded: <code>/</code> for a whole domain, or a folder like <code>/books/my-book/</code>.</span>
      <label for="ho-url">Use the domain as the site address</label><label class="chk"><input type="checkbox" id="ho-url"> Change website.yml's address to https://&lt;domain&gt;/ (links and the sitemap use it)</label><span class="muted-note">Current address: ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a>` : "none yet"}</span>
    </div><div class="row" style="margin-top:10px"><button class="primary" id="ho-save">${ic("save")}Save hosting settings</button></div>
    <p class="muted-note">Saved in this book's website.yml; its other settings and comments are kept. Nothing is published from here.</p>`)}
    ${card("Steps for each host", `<ul class="plain">
      <li>${ic("github")} <b>GitHub Pages</b>: Website › Publish (asks first). Custom domain: add a CNAME DNS record for it, then publish.</li>
      <li>${ic("package")} <b>Netlify / Cloudflare Pages</b>: make a Website ZIP with path <code>/</code>, then drag its <code>site</code> folder into the host's “deploy manually” page.</li>
      <li>${ic("server")} <b>Any web server</b>: make a ZIP for the folder you'll use, then upload the contents of <code>site/</code> there.</li></ul>
      <p class="muted-note">Every ZIP includes a step-by-step HOSTING-GUIDE.pdf.</p>`)}`;
  $("#ho-save").onclick = async () => {
    const r = await api("/api/hosting/save", { provider: $("#ho-prov").value, domain: $("#ho-dom").value, zip_base: $("#ho-base").value, use_domain_url: $("#ho-url").checked });
    toast(r.message, r.ok ? "good" : "bad", 7000); if (r.ok) renderPage();
  };
}
PAGES["website/hosting"] = el => hostingForm(el, "hosting");
PAGES["website/domain"] = el => hostingForm(el, "domain");
PAGES["website/zip"] = async el => {
  const h = await api("/api/hosting");
  el.innerHTML = `<div class="page-h"><h2>Website ZIP</h2></div>
    ${card("A portable copy of the website", `<p>Builds the public website from <b>approved</b> chapters, images and activities, checks every page and link, and packs it with a hosting guide (PDF) for any static host.</p>
      <div class="bkform"><label for="wz-base">Will live at</label><input id="wz-base" value="${esc(h.settings.zip_base)}"><span class="muted-note"><code>/</code> for a whole domain, or a folder like <code>/books/my-book/</code>. Pages only work at the path they were built for.</span>
      <label>Downloads</label><label class="chk"><input type="checkbox" id="wz-dl"> Also build the PDF and EPUB downloads (much slower)</label><span></span></div>
      <div class="row" style="margin-top:10px"><button class="primary" id="wz-make">${ic("package")}Make website ZIP</button></div>`)}`;
  $("#wz-make").onclick = async () => {
    const r = await busy("Building and checking the website…", () => api("/api/website/zip", { base: $("#wz-base").value, downloads: $("#wz-dl").checked }));
    if (!r.ok) return toast("The website ZIP couldn't be made: see the details in Website › Publish's log.", "bad", 9000);
    location.href = r.download;
    toast(`Website ZIP ready: ${r.files} files, ${fmtBytes(r.bytes)}, built for ${r.base}${r.guide_pdf ? ", with HOSTING-GUIDE.pdf" : ""}.`, "good", 9000);
  };
};

// ---- Interactive
async function gamesBy(el, title, pred, empty) {
  const g = await api("/api/games");
  const xs = g.games.filter(pred);
  el.innerHTML = `<div class="page-h"><h2>${title}</h2></div>${card(`${xs.length} installed`, xs.length ? `<table class="tbl"><thead><tr><th>Title</th><th>Type</th><th>Chapter</th><th>Status</th></tr></thead><tbody>
    ${xs.map(x => `<tr><td>${esc(x.title)}</td><td>${esc(x.activityType || "game")}</td><td>${esc(x.chapterTitle || "")}</td><td><span class="chip-s">${esc(x.status)}</span></td></tr>`).join("")}</tbody></table>` : `<p class="muted-note">${empty}</p>`)}
    <p><a href="#/p/interactive/games">Manage games and activities</a></p>`;
}
PAGES["interactive/quizzes"] = el => gamesBy(el, "Quizzes", x => /quiz/i.test(x.activityType || ""), "No quizzes installed. Quizzes are game packages with activityType “quiz”.");
PAGES["interactive/activities"] = el => gamesBy(el, "Activities", () => true, "No activities installed yet.");
PAGES["interactive/config"] = async el => {
  const g = await api("/api/games");
  el.innerHTML = `<div class="page-h"><h2>Configuration</h2></div>${card("Game Package API", `<p>Installed games use API <b>${esc(g.apiVersion)}</b> (1.0 still accepted). Only approved games are published, and the site hides Activities until one is approved.</p>
    <a class="btn" href="/api/games/docs.md" target="_blank">${ic("file-text")}Developer docs</a>`)}`;
};

// ---------------------------------------------------------------- boot
function bbBoot() {
  $("#app-settings").onclick = () => bbGo("settings", "ai", "a");
  $("#app-help").onclick = () => setHash("u", "help", "help");
  $("#app-logo").onclick = ev => { ev.preventDefault(); bbGo("library", "all", "a"); };
  loadApp().then(() => {
    if (!location.hash && BB.app.settings.openLastProject && store.get("openProject", null) === projectPath()) location.hash = "#/p/overview/dashboard";
    bbRender();
  }).catch(e => toast(e.message, "bad", 8000));
}

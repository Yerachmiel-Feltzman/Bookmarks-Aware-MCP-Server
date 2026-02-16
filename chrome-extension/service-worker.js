/**
 * Bookmarks MCP Bridge - Service Worker
 *
 * Connects to the MCP server's WebSocket and proxies bookmark
 * operations through Chrome's chrome.bookmarks API.
 */

const DEFAULT_PORT = 8765;
const KEEPALIVE_INTERVAL_MS = 20_000;
const RECONNECT_DELAY_MS = 3_000;

let ws = null;
let keepAliveId = null;
let reconnectId = null;
let connected = false;

// ---------------------------------------------------------------------------
// WebSocket lifecycle
// ---------------------------------------------------------------------------

function getServerUrl() {
  return `ws://localhost:${DEFAULT_PORT}`;
}

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    ws = new WebSocket(getServerUrl());
  } catch (err) {
    console.error("[MCP Bridge] Failed to create WebSocket:", err);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log("[MCP Bridge] Connected to MCP server");
    connected = true;
    clearReconnect();
    startKeepAlive();
    broadcastStatus();
  };

  ws.onmessage = async (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      console.warn("[MCP Bridge] Non-JSON message:", event.data);
      return;
    }

    if (msg.type === "ping") {
      ws.send(JSON.stringify({ type: "pong" }));
      return;
    }

    if (msg.id && msg.action) {
      const response = await handleCommand(msg);
      ws.send(JSON.stringify(response));
    }
  };

  ws.onclose = () => {
    console.log("[MCP Bridge] Disconnected");
    cleanup();
    scheduleReconnect();
  };

  ws.onerror = (err) => {
    console.error("[MCP Bridge] WebSocket error:", err);
    cleanup();
    scheduleReconnect();
  };
}

function cleanup() {
  connected = false;
  stopKeepAlive();
  broadcastStatus();
}

function scheduleReconnect() {
  if (reconnectId) return;
  reconnectId = setTimeout(() => {
    reconnectId = null;
    connect();
  }, RECONNECT_DELAY_MS);
}

function clearReconnect() {
  if (reconnectId) {
    clearTimeout(reconnectId);
    reconnectId = null;
  }
}

function startKeepAlive() {
  stopKeepAlive();
  keepAliveId = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "keepalive" }));
    } else {
      stopKeepAlive();
    }
  }, KEEPALIVE_INTERVAL_MS);
}

function stopKeepAlive() {
  if (keepAliveId) {
    clearInterval(keepAliveId);
    keepAliveId = null;
  }
}

// ---------------------------------------------------------------------------
// Status broadcasting (to popup)
// ---------------------------------------------------------------------------

function broadcastStatus() {
  chrome.runtime.sendMessage({ type: "status", connected }).catch(() => {
    // popup not open, ignore
  });
}

// Listen for status requests from popup
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "getStatus") {
    sendResponse({ connected });
  }
});

// ---------------------------------------------------------------------------
// Command handler
// ---------------------------------------------------------------------------

async function handleCommand(msg) {
  const { id, action, params } = msg;

  try {
    let result;

    switch (action) {
      case "create":
        result = await cmdCreate(params);
        break;
      case "move":
        result = await cmdMove(params);
        break;
      case "update":
        result = await cmdUpdate(params);
        break;
      case "remove":
        result = await cmdRemove(params);
        break;
      case "getTree":
        result = await cmdGetTree();
        break;
      case "search":
        result = await cmdSearch(params);
        break;
      default:
        return { id, status: "error", error: `Unknown action: ${action}` };
    }

    return { id, status: "ok", result };
  } catch (err) {
    return { id, status: "error", error: err.message || String(err) };
  }
}

// ---------------------------------------------------------------------------
// Bookmark commands
// ---------------------------------------------------------------------------

/**
 * Resolve a bookmark by URL. Returns the first match.
 */
async function findByUrl(url) {
  // Try exact match first
  let results = await chrome.bookmarks.search({ url });

  // Chrome normalizes URLs (e.g. adds trailing slash). Try variations.
  if (results.length === 0 && !url.endsWith("/")) {
    results = await chrome.bookmarks.search({ url: url + "/" });
  }
  if (results.length === 0 && url.endsWith("/")) {
    results = await chrome.bookmarks.search({ url: url.slice(0, -1) });
  }

  if (results.length === 0) {
    throw new Error(`Bookmark not found for URL: ${url}`);
  }
  return results[0];
}

/**
 * Resolve a folder by path (e.g. "bookmark_bar/Work/Dev Setup").
 * Walks the tree from the root.
 */
async function findFolderByPath(folderPath) {
  const tree = await chrome.bookmarks.getTree();
  const roots = tree[0].children;

  // Map root keys to Chrome's root nodes
  const rootMap = {};
  for (const root of roots) {
    // Chrome names: "Bookmarks Bar", "Other Bookmarks", "Mobile Bookmarks"
    if (root.title === "Bookmarks Bar" || root.title === "Bookmarks bar") {
      rootMap["bookmark_bar"] = root;
    } else if (root.title === "Other Bookmarks" || root.title === "Other bookmarks") {
      rootMap["other"] = root;
    } else if (root.title === "Mobile Bookmarks" || root.title === "Mobile bookmarks") {
      rootMap["synced"] = root;
    }
  }

  const parts = folderPath.split("/");
  const rootKey = parts[0];
  let current = rootMap[rootKey];

  if (!current) {
    throw new Error(`Unknown root folder: ${rootKey}`);
  }

  for (let i = 1; i < parts.length; i++) {
    const children = await chrome.bookmarks.getChildren(current.id);
    const next = children.find(
      (c) => c.title === parts[i] && c.url === undefined
    );
    if (!next) {
      throw new Error(
        `Folder not found: ${parts.slice(0, i + 1).join("/")}`
      );
    }
    current = next;
  }

  return current;
}

async function cmdCreate(params) {
  const { url, title, folderPath } = params;
  const folder = await findFolderByPath(folderPath);
  const createParams = { parentId: folder.id, title };
  if (url) {
    createParams.url = url;
  }
  return await chrome.bookmarks.create(createParams);
}

async function cmdMove(params) {
  const { url, targetFolder } = params;
  const bookmark = await findByUrl(url);
  const folder = await findFolderByPath(targetFolder);
  return await chrome.bookmarks.move(bookmark.id, { parentId: folder.id });
}

async function cmdUpdate(params) {
  const { url, title } = params;
  const bookmark = await findByUrl(url);
  return await chrome.bookmarks.update(bookmark.id, { title });
}

async function cmdRemove(params) {
  const { url } = params;
  const bookmark = await findByUrl(url);
  await chrome.bookmarks.remove(bookmark.id);
  return { removed: true, id: bookmark.id };
}

async function cmdGetTree() {
  return await chrome.bookmarks.getTree();
}

async function cmdSearch(params) {
  const { query } = params;
  return await chrome.bookmarks.search(query);
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

connect();

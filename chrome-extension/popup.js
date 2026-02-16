const dot = document.getElementById("dot");
const label = document.getElementById("label");

function update(connected) {
  dot.className = connected ? "dot on" : "dot off";
  label.textContent = connected ? "Connected to MCP server" : "Not connected";
}

chrome.runtime.sendMessage({ type: "getStatus" }, (resp) => {
  if (chrome.runtime.lastError || !resp) {
    update(false);
    return;
  }
  update(resp.connected);
});

const connDot = document.getElementById("conn-dot");
const connText = document.getElementById("conn-text");
const rawBody = document.getElementById("raw-body");
const targetCount = document.getElementById("target-count");
const clearBtn = document.getElementById("clear-btn");
const applyBtn = document.getElementById("apply-btn");
const refreshPortsBtn = document.getElementById("refresh-ports-btn");
const portSelect = document.getElementById("port-select");
const baudInput = document.getElementById("baud-input");
const simulateInput = document.getElementById("simulate-input");

const radarCanvas = document.getElementById("radar-canvas");
const radarCtx = radarCanvas.getContext("2d");
const timelineCanvas = document.getElementById("timeline-canvas");
const timelineCtx = timelineCanvas.getContext("2d");

let socket = null;
let reconnectDelay = 1000;
const maxRows = 120;
const timeline = [];
let latestTargets = [];

function setConnection(online, label) {
  connText.textContent = label;
  connDot.classList.toggle("online", online);
  connDot.classList.toggle("offline", !online);
}

function valueToRadarCoords(x, y) {
  const cx = radarCanvas.width / 2;
  const cy = radarCanvas.height * 0.9;
  const maxDist = 7000;
  const px = cx + (x / maxDist) * (radarCanvas.width * 0.42);
  const py = cy - (y / maxDist) * (radarCanvas.height * 0.8);
  return { x: px, y: py };
}

function drawRadar(targets) {
  radarCtx.clearRect(0, 0, radarCanvas.width, radarCanvas.height);
  const cx = radarCanvas.width / 2;
  const cy = radarCanvas.height * 0.9;

  radarCtx.strokeStyle = "rgba(23,33,33,0.2)";
  radarCtx.lineWidth = 1;

  for (let r = 80; r <= 320; r += 60) {
    radarCtx.beginPath();
    radarCtx.arc(cx, cy, r, Math.PI, 2 * Math.PI);
    radarCtx.stroke();
  }

  radarCtx.beginPath();
  radarCtx.moveTo(cx, cy);
  radarCtx.lineTo(cx - 240, cy - 250);
  radarCtx.moveTo(cx, cy);
  radarCtx.lineTo(cx + 240, cy - 250);
  radarCtx.stroke();

  targets.forEach((t, idx) => {
    const point = valueToRadarCoords(t.x_mm || 0, t.y_mm || 0);
    const hue = 155 + (idx % 4) * 12;
    radarCtx.fillStyle = `hsl(${hue} 88% 33%)`;
    radarCtx.beginPath();
    radarCtx.arc(point.x, point.y, 6, 0, 2 * Math.PI);
    radarCtx.fill();
  });
}

function drawTimeline() {
  timelineCtx.clearRect(0, 0, timelineCanvas.width, timelineCanvas.height);
  const w = timelineCanvas.width;
  const h = timelineCanvas.height;
  const len = timeline.length;
  if (!len) return;

  const step = w / Math.max(120, len);
  timelineCtx.fillStyle = "rgba(0, 127, 95, 0.75)";
  timeline.forEach((v, i) => {
    if (!v) return;
    const x = i * step;
    timelineCtx.fillRect(x, h * 0.2, Math.max(step - 1, 1), h * 0.6);
  });

  timelineCtx.strokeStyle = "rgba(23,33,33,0.2)";
  timelineCtx.beginPath();
  timelineCtx.moveTo(0, h * 0.2);
  timelineCtx.lineTo(w, h * 0.2);
  timelineCtx.moveTo(0, h * 0.8);
  timelineCtx.lineTo(w, h * 0.8);
  timelineCtx.stroke();
}

function prependRawRow(packet) {
  const row = document.createElement("tr");
  const text = (packet.raw_text || packet.raw_hex || "").slice(0, 180);
  row.innerHTML = `
    <td>${new Date(packet.ts).toLocaleTimeString()}</td>
    <td>${packet.presence ? "yes" : "no"}</td>
    <td>${packet.targets?.length || 0}</td>
    <td>${text.replaceAll("<", "&lt;")}</td>
  `;
  rawBody.prepend(row);
  while (rawBody.children.length > maxRows) {
    rawBody.removeChild(rawBody.lastElementChild);
  }
}

function onPacket(packet) {
  latestTargets = Array.isArray(packet.targets) ? packet.targets : [];
  targetCount.textContent = `${latestTargets.length} target${latestTargets.length === 1 ? "" : "s"}`;
  timeline.push(Boolean(packet.presence));
  if (timeline.length > 120) timeline.shift();
  drawRadar(latestTargets);
  drawTimeline();
  prependRawRow(packet);
}

function connectWs() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${location.host}/ws`);
  setConnection(false, "Connecting...");

  socket.onopen = () => {
    reconnectDelay = 1000;
    setConnection(true, "Live");
  };

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "sensor_update") {
        onPacket(msg.payload);
      } else if (msg.type === "error") {
        setConnection(false, msg.message);
      }
    } catch (_err) {
      // Ignore malformed messages.
    }
  };

  socket.onclose = () => {
    setConnection(false, "Disconnected, retrying...");
    setTimeout(connectWs, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 1.5, 10000);
  };

  socket.onerror = () => {
    setConnection(false, "Socket error");
  };
}

async function refreshPorts() {
  const previous = portSelect.value;
  const res = await fetch("/api/ports");
  const data = await res.json();
  const ports = data.ports || [];

  portSelect.innerHTML = "";
  const autoOpt = document.createElement("option");
  autoOpt.value = "";
  autoOpt.textContent = "Auto-select";
  portSelect.appendChild(autoOpt);

  ports.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    portSelect.appendChild(opt);
  });
  portSelect.value = previous;
}

async function loadSnapshot() {
  const res = await fetch("/api/snapshot");
  const snap = await res.json();
  baudInput.value = snap.config?.baud_rate || 115200;
  simulateInput.checked = Boolean(snap.config?.simulate);
  portSelect.value = snap.config?.port || "";
}

async function applyConfig() {
  applyBtn.disabled = true;
  try {
    await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        port: portSelect.value || null,
        baud_rate: Number(baudInput.value || 115200),
        simulate: simulateInput.checked,
      }),
    });
  } finally {
    applyBtn.disabled = false;
  }
}

clearBtn.addEventListener("click", () => {
  rawBody.innerHTML = "";
  timeline.length = 0;
  latestTargets = [];
  targetCount.textContent = "0 targets";
  drawRadar([]);
  drawTimeline();
});

applyBtn.addEventListener("click", applyConfig);
refreshPortsBtn.addEventListener("click", refreshPorts);

(async function init() {
  await refreshPorts();
  await loadSnapshot();
  drawRadar([]);
  drawTimeline();
  connectWs();
})();

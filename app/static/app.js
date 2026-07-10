// --- App State & Globals ---
let socket = null;
const consoleLogs = document.getElementById("console-logs");
let isFaultActive = false;

// --- DOM Loaded Handler ---
document.addEventListener("DOMContentLoaded", () => {
    initClock();
    connectWebSocket();
    fetchInitialData();
    setupEventListeners();
});

// --- System Clock ---
function initClock() {
    setInterval(() => {
        const now = new Date();
        document.getElementById("clock-display").innerHTML = 
            `<i class="fa-regular fa-clock"></i> ${now.toUTCString().replace("GMT", "UTC")}`;
    }, 1000);
}

// --- WebSocket Ingest Pipeline ---
function connectWebSocket() {
    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProto}//${window.location.host}/ws`;
    
    logConsole("Connecting to grid monitoring system via WebSocket...", "system");
    socket = new WebSocket(wsUrl);
    
    socket.onopen = () => {
        document.getElementById("ws-status").className = "badge connected";
        document.getElementById("ws-status").innerHTML = `<i class="fa-solid fa-circle-dot"></i> GRID ONLINE`;
        logConsole("Real-time telemetry channel established.", "success");
    };
    
    socket.onclose = () => {
        document.getElementById("ws-status").className = "badge disconnected";
        document.getElementById("ws-status").innerHTML = `<i class="fa-solid fa-circle-dot"></i> GRID OFFLINE`;
        logConsole("Telemetry channel disconnected. Retrying in 5s...", "critical");
        setTimeout(connectWebSocket, 5000);
    };
    
    socket.onerror = (error) => {
        logConsole(`WebSocket connection error: ${error.message || 'unknown'}`, "critical");
    };
    
    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === "grid_update") {
                updateUI(data);
            }
        } catch (e) {
            console.error("Failed to parse socket payload:", e);
        }
    };
}

// --- Fetch Initial Setup Data ---
async function fetchInitialData() {
    try {
        // Fetch simulation control values
        const controlRes = await fetch("/api/grid/control");
        const controls = await controlRes.json();
        updateControlSlidersUI(controls);
        
        // Fetch active meters
        fetchMeterList();
        
        // Fetch initial battery status
        fetchBatteryStatus();
    } catch (err) {
        logConsole(`Initial setup fetch failed: ${err.message}`, "critical");
    }
}

// --- REST Endpoint Calls ---
async function fetchMeterList() {
    try {
        const res = await fetch("/api/telemetry/meters");
        const meters = await res.json();
        renderMeterList(meters);
    } catch (err) {
        logConsole(`Failed to fetch grid nodes list: ${err.message}`, "alert");
    }
}

async function fetchBatteryStatus() {
    try {
        const res = await fetch("/api/battery/status");
        const bess = await res.json();
        updateBatteryUI(bess);
    } catch (err) {
        console.error("Failed to fetch battery status:", err);
    }
}

// --- UI Rendering & Animation Logic ---
function updateUI(data) {
    const metrics = data.grid_metrics;
    const bess = data.battery;
    const meters = data.meters;
    const controls = data.controls;
    
    // 1. Grid Stability KPI
    const stabilityVal = document.getElementById("stability-value");
    const stabilityBar = document.getElementById("stability-bar");
    const gridStatusBadge = document.getElementById("grid-status-badge");
    
    stabilityVal.textContent = `${metrics.grid_stability_score}%`;
    stabilityBar.style.width = `${metrics.grid_stability_score}%`;
    
    gridStatusBadge.textContent = metrics.status.toUpperCase();
    gridStatusBadge.className = `grid-status-badge ${metrics.status}`;
    
    if (metrics.status === "warning") {
        logConsole(`[GRID WARNING] System stability degraded. Check supply-load margins. Stability: ${metrics.grid_stability_score}%`, "alert");
    } else if (metrics.status === "critical") {
        logConsole(`[GRID CRITICAL] Phase collapse risk. Frequency: ${metrics.average_frequency}Hz, Voltage: ${metrics.average_voltage}V`, "critical");
    }
    
    // 2. Power Metrics
    document.getElementById("val-demand").textContent = `${metrics.total_demand_kw.toFixed(2)} kW`;
    document.getElementById("val-generation").textContent = `${metrics.total_generation_kw.toFixed(2)} kW`;
    document.getElementById("val-net-load").textContent = `${metrics.net_load_kw.toFixed(2)} kW`;
    
    // Highlight net load if critical
    const netLoadVal = document.getElementById("val-net-load");
    if (metrics.net_load_kw > 350) {
        netLoadVal.style.color = "var(--accent-yellow)";
    } else {
        netLoadVal.style.color = "var(--text-primary)";
    }
    
    // 3. Grid Physics Values
    document.getElementById("val-voltage").textContent = `${metrics.average_voltage.toFixed(1)} V`;
    document.getElementById("val-frequency").textContent = `${metrics.average_frequency.toFixed(3)} Hz`;
    
    // 4. Update Battery BESS
    updateBatteryUI(bess);
    
    // 5. Update Meter Nodes list with latest live readings
    renderMeterList(meters);
    
    // 6. Update Power Flow Diagram Animation
    animatePowerFlow(metrics.total_generation_kw, metrics.total_demand_kw, bess.current_charge_kw, metrics.net_load_kw);
    
    // 7. Ensure simulator control state is synced
    isFaultActive = controls.grid_fault_active;
    const faultBtn = document.getElementById("btn-toggle-fault");
    if (isFaultActive) {
        faultBtn.className = "btn btn-warning active";
        faultBtn.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Grid Fault Active (Underfrequency/Drop)`;
    } else {
        faultBtn.className = "btn btn-warning";
        faultBtn.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Inject Voltage/Freq Grid Fault`;
    }
}

function updateBatteryUI(bess) {
    const batteryLvl = document.getElementById("battery-level");
    const batteryPct = document.getElementById("battery-percent");
    const batterySoc = document.getElementById("battery-soc-kwh");
    const batteryPower = document.getElementById("battery-power-kw");
    const batteryStatusText = document.getElementById("battery-status-text");
    const savingsToday = document.getElementById("savings-val");
    const carbonOffset = document.getElementById("co2-val");
    
    batteryPct.textContent = `${bess.soc_percent.toFixed(1)}%`;
    batteryLvl.style.height = `${bess.soc_percent}%`;
    batterySoc.textContent = `${bess.soc_kwh.toFixed(1)} / ${bess.capacity_kwh} kWh`;
    
    // Battery Rate Value and Sign styling
    const kw = bess.current_charge_kw;
    if (kw > 0.1) {
        batteryPower.textContent = `+${kw.toFixed(1)} kW (Charging)`;
        batteryPower.style.color = "var(--accent-green)";
        batteryStatusText.textContent = "CHARGING";
        batteryStatusText.className = "battery-charge-direction charging";
        batteryLvl.style.background = "linear-gradient(180deg, var(--accent-green), hsl(145, 80%, 35%))";
    } else if (kw < -0.1) {
        batteryPower.textContent = `${kw.toFixed(1)} kW (Discharging)`;
        batteryPower.style.color = "var(--accent-purple)";
        batteryStatusText.textContent = "DISCHARGING";
        batteryStatusText.className = "battery-charge-direction discharging";
        batteryLvl.style.background = "linear-gradient(180deg, var(--accent-purple), hsl(272, 75%, 45%))";
    } else {
        batteryPower.textContent = `0.0 kW (Idle)`;
        batteryPower.style.color = "var(--text-secondary)";
        batteryStatusText.textContent = "IDLE";
        batteryStatusText.className = "battery-charge-direction idle";
        batteryLvl.style.background = "linear-gradient(180deg, var(--text-secondary), var(--text-muted))";
    }
    
    // Savings
    savingsToday.textContent = `$${bess.money_saved_today.toFixed(2)}`;
    carbonOffset.textContent = `${bess.carbon_offset_kg.toFixed(2)} kg`;
    
    // Auto toggle mode buttons state
    document.querySelectorAll(".mode-btn").forEach(btn => {
        if (btn.getAttribute("data-mode") === bess.mode) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
    
    // Handle override power slider view
    const overridePanel = document.getElementById("manual-override-inputs");
    if (bess.mode === "charge" || bess.mode === "discharge") {
        overridePanel.style.display = "block";
        if (bess.current_charge_kw !== 0) {
            document.getElementById("override-power-slider").value = Math.abs(bess.current_charge_kw);
            document.getElementById("override-power-val").textContent = `${Math.abs(bess.current_charge_kw).toFixed(0)} kW`;
        }
    } else {
        overridePanel.style.display = "none";
    }
}

function animatePowerFlow(generation, demand, battery_charge, net_load) {
    const flowGen = document.getElementById("flow-val-gen");
    const flowDem = document.getElementById("flow-val-dem");
    const flowBess = document.getElementById("flow-val-bess");
    const flowNet = document.getElementById("flow-val-net");
    
    flowGen.textContent = `${generation.toFixed(1)} kW`;
    flowDem.textContent = `${demand.toFixed(1)} kW`;
    flowNet.textContent = `${net_load.toFixed(1)} kW`;
    
    // Battery power flow node text
    if (battery_charge > 0) {
        flowBess.textContent = `+${battery_charge.toFixed(1)} kW`;
        flowBess.style.color = "var(--accent-green)";
    } else if (battery_charge < 0) {
        flowBess.textContent = `${battery_charge.toFixed(1)} kW`;
        flowBess.style.color = "var(--accent-purple)";
    } else {
        flowBess.textContent = `0.0 kW`;
        flowBess.style.color = "var(--text-secondary)";
    }
    
    // Pulse Animations
    const pulseGen = document.querySelector("#line-gen-hub .pulse");
    const pulseDem = document.querySelector("#line-consumer-hub .pulse");
    const pulseBess = document.querySelector("#line-bess-hub .pulse");
    
    // 1. Generation to Hub pulse
    if (generation > 5.0) {
        // Fast pulse for large gen
        const speed = Math.max(0.6, 2.5 - (generation / 250));
        pulseGen.style.animation = `flow-right ${speed.toFixed(1)}s infinite linear`;
        pulseGen.style.background = "var(--accent-green)";
        pulseGen.style.boxShadow = "0 0 8px var(--accent-green)";
        pulseGen.style.display = "block";
    } else {
        pulseGen.style.animation = "none";
        pulseGen.style.display = "none";
    }
    
    // 2. Hub to Consumer pulse
    if (demand > 5.0) {
        const speed = Math.max(0.6, 2.5 - (demand / 250));
        pulseDem.style.animation = `flow-right ${speed.toFixed(1)}s infinite linear`;
        pulseDem.style.background = "var(--accent-cyan)";
        pulseDem.style.boxShadow = "0 0 8px var(--accent-cyan)";
        pulseDem.style.display = "block";
    } else {
        pulseDem.style.animation = "none";
        pulseDem.style.display = "none";
    }
    
    // 3. Battery to Hub pulse
    if (battery_charge > 5.0) {
        // Charging: Flow goes down from hub to battery
        const speed = Math.max(0.6, 2.5 - (battery_charge / 150));
        pulseBess.style.animation = `flow-down ${speed.toFixed(1)}s infinite linear`;
        pulseBess.style.background = "var(--accent-green)";
        pulseBess.style.boxShadow = "0 0 8px var(--accent-green)";
        pulseBess.style.display = "block";
    } else if (battery_charge < -5.0) {
        // Discharging: Flow goes up from battery to hub
        const speed = Math.max(0.6, 2.5 - (Math.abs(battery_charge) / 150));
        pulseBess.style.animation = `flow-up ${speed.toFixed(1)}s infinite linear`;
        pulseBess.style.background = "var(--accent-purple)";
        pulseBess.style.boxShadow = "0 0 8px var(--accent-purple)";
        pulseBess.style.display = "block";
    } else {
        pulseBess.style.animation = "none";
        pulseBess.style.display = "none";
    }
}

function renderMeterList(meters) {
    const list = document.getElementById("meter-list");
    if (!meters || meters.length === 0) {
        list.innerHTML = `<div class="meter-list-empty">No active smart meters.</div>`;
        return;
    }
    
    list.innerHTML = "";
    meters.forEach(node => {
        const tel = node.telemetry || { active_power_kw: 0.0, status: "online" };
        const power = tel.active_power_kw || 0.0;
        const powerClass = power > 0 ? "load" : (power < 0 ? "gen" : "");
        const formattedPower = power > 0 ? `+${power.toFixed(1)} kW` : `${power.toFixed(1)} kW`;
        
        const row = document.createElement("div");
        row.className = "meter-row";
        row.innerHTML = `
            <div class="meter-info">
                <div class="meter-name-row">
                    <span class="meter-name">${node.name}</span>
                    <span class="meter-type-tag ${node.type}">${node.type}</span>
                </div>
                <span class="meter-location">${node.location || "Unspecified Zone"}</span>
            </div>
            <div class="meter-telemetry-status">
                <span class="meter-power-value ${powerClass}">${formattedPower}</span>
                <span class="meter-status-tag ${node.status}">${node.status}</span>
            </div>
        `;
        list.appendChild(row);
    });
}

function updateControlSlidersUI(controls) {
    document.getElementById("slider-load-mult").value = controls.load_multiplier;
    document.getElementById("lbl-load-mult").textContent = `${controls.load_multiplier.toFixed(1)}x`;
    
    document.getElementById("slider-solar-mult").value = controls.solar_multiplier;
    document.getElementById("lbl-solar-mult").textContent = `${(controls.solar_multiplier * 100).toFixed(0)}%`;
}

// --- Event Handlers & API triggers ---
function setupEventListeners() {
    // 1. Simulation controls API triggers
    const loadSlider = document.getElementById("slider-load-mult");
    const solarSlider = document.getElementById("slider-solar-mult");
    const faultBtn = document.getElementById("btn-toggle-fault");
    
    loadSlider.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        document.getElementById("lbl-load-mult").textContent = `${val.toFixed(1)}x`;
        updateControlsAPI({ load_multiplier: val });
    });
    
    solarSlider.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        document.getElementById("lbl-solar-mult").textContent = `${(val * 100).toFixed(0)}%`;
        updateControlsAPI({ solar_multiplier: val });
    });
    
    faultBtn.addEventListener("click", () => {
        isFaultActive = !isFaultActive;
        updateControlsAPI({ grid_fault_active: isFaultActive });
        if (isFaultActive) {
            logConsole("Fault Injection active: Voltages sagging, frequency dropping.", "critical");
        } else {
            logConsole("Injected grid fault cleared. System self-repair initiated.", "success");
        }
    });
    
    // 2. Battery Mode overrides API triggers
    document.querySelectorAll(".mode-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            const mode = e.target.getAttribute("data-mode");
            try {
                const res = await fetch("/api/battery/control", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ mode: mode })
                });
                const bess = await res.json();
                updateBatteryUI(bess);
                logConsole(`Battery mode changed manually to: ${mode.toUpperCase()}`, "system");
            } catch (err) {
                logConsole(`Failed to shift battery mode: ${err.message}`, "alert");
            }
        });
    });
    
    // 3. Manual override slider values
    const powerSlider = document.getElementById("override-power-slider");
    powerSlider.addEventListener("change", async (e) => {
        const val = parseFloat(e.target.value);
        document.getElementById("override-power-val").textContent = `${val.toFixed(0)} kW`;
        
        let activeMode = "idle";
        document.querySelectorAll(".mode-btn").forEach(btn => {
            if (btn.classList.contains("active")) {
                activeMode = btn.getAttribute("data-mode");
            }
        });
        
        try {
            const res = await fetch("/api/battery/control", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mode: activeMode, target_power_kw: val })
            });
            const bess = await res.json();
            updateBatteryUI(bess);
            logConsole(`Manual override power set to ${val} kW`, "system");
        } catch (err) {
            logConsole(`Failed to set manual target power: ${err.message}`, "alert");
        }
    });
    
    // 4. Modal for adding smart meters
    const modal = document.getElementById("add-meter-modal");
    const openModalBtn = document.getElementById("btn-open-meter-modal");
    const closeModalBtn = document.getElementById("btn-close-meter-modal");
    const meterForm = document.getElementById("add-meter-form");
    
    openModalBtn.addEventListener("click", () => modal.style.display = "flex");
    closeModalBtn.addEventListener("click", () => modal.style.display = "none");
    
    meterForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            name: document.getElementById("meter-name").value,
            type: document.getElementById("meter-type").value,
            max_capacity_kw: parseFloat(document.getElementById("meter-capacity").value),
            location: document.getElementById("meter-location").value,
            status: "online"
        };
        
        try {
            const res = await fetch("/api/telemetry/meters", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            
            if (res.ok) {
                logConsole(`Successfully commissioned new meter: ${payload.name} [${payload.type.toUpperCase()}]`, "success");
                modal.style.display = "none";
                meterForm.reset();
                fetchMeterList();
            } else {
                throw new Error("Validation mismatch");
            }
        } catch (err) {
            logConsole(`Meter commission failed: ${err.message}`, "alert");
        }
    });
    
    // 5. Console clear
    document.getElementById("clear-console").addEventListener("click", () => {
        consoleLogs.innerHTML = "";
    });
}

async function updateControlsAPI(payload) {
    try {
        await fetch("/api/grid/control", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
    } catch (err) {
        console.error("Control API update failed:", err);
    }
}

// --- Console Log Helper ---
function logConsole(message, type = "system") {
    const timestamp = new Date().toLocaleTimeString([], { hour12: false });
    const logLine = document.createElement("div");
    logLine.className = `log-line ${type}`;
    logLine.textContent = `[${timestamp}] ${message}`;
    
    consoleLogs.appendChild(logLine);
    
    while (consoleLogs.children.length > 100) {
        consoleLogs.removeChild(consoleLogs.firstChild);
    }
    
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

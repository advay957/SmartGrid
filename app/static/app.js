// --- App State & Globals ---
const consoleLogs = document.getElementById("console-logs");

// --- DOM Loaded Handler ---
document.addEventListener("DOMContentLoaded", () => {
    initClock();
    logConsole("Grid Enterprise Dashboard Initialized.", "system");
});

// --- System Clock ---
function initClock() {
    setInterval(() => {
        const now = new Date();
        document.getElementById("clock-display").innerHTML = 
            `<i class="fa-regular fa-clock"></i> ${now.toUTCString().replace("GMT", "UTC")}`;
    }, 1000);
}

// --- Console Log Helper ---
function logConsole(message, type = "system") {
    const timestamp = new Date().toLocaleTimeString([], { hour12: false });
    const logLine = document.createElement("div");
    logLine.className = `log-line ${type}`;
    logLine.textContent = `[${timestamp}] ${message}`;
    
    consoleLogs.appendChild(logLine);
    
    // Remove old logs to avoid DOM overload
    while (consoleLogs.children.length > 100) {
        consoleLogs.removeChild(consoleLogs.firstChild);
    }
    
    // Auto scroll to latest logs
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

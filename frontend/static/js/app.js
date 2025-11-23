/**
 * Main Application Script
 * Initializes and coordinates wallet and agent managers
 */

let walletManager;
let agentManager;

/**
 * Initialize the application
 */
async function initApp() {
    console.log('Initializing Arbitrum Liquidity Agent...');

    // Initialize wallet manager
    walletManager = new WalletManager();
    await walletManager.init();

    // Initialize agent manager
    agentManager = new AgentManager(walletManager);

    // Setup event listeners
    setupEventListeners();

    addLogEntry('Application initialized. Connect your wallet to get started.', 'success');
}

/**
 * Setup all event listeners
 */
function setupEventListeners() {
    // Connect Wallet Button
    const connectBtn = document.getElementById('connectWallet');
    if (connectBtn) {
        connectBtn.addEventListener('click', async () => {
            connectBtn.disabled = true;
            connectBtn.textContent = 'Connecting...';

            const success = await walletManager.connectMetaMask();

            if (!success) {
                connectBtn.disabled = false;
                connectBtn.textContent = 'Connect Wallet';
            }
        });
    }

    // Disconnect Wallet Button
    const disconnectBtn = document.getElementById('disconnectWallet');
    if (disconnectBtn) {
        disconnectBtn.addEventListener('click', async () => {
            await walletManager.disconnect();
        });
    }

    // Start Agent Button
    const startBtn = document.getElementById('startAgent');
    if (startBtn) {
        startBtn.addEventListener('click', async () => {
            startBtn.disabled = true;
            startBtn.textContent = 'Starting...';

            const success = await agentManager.start();

            if (!success) {
                startBtn.disabled = false;
                startBtn.textContent = '🚀 Start Agent';
            }
        });
    }

    // Stop Agent Button
    const stopBtn = document.getElementById('stopAgent');
    if (stopBtn) {
        stopBtn.addEventListener('click', async () => {
            stopBtn.disabled = true;
            stopBtn.textContent = 'Stopping...';

            await agentManager.stop();

            stopBtn.disabled = false;
            stopBtn.textContent = '⏹️ Stop Agent';
        });
    }

    // Model select change
    const modelSelect = document.getElementById('modelSelect');
    if (modelSelect) {
        modelSelect.addEventListener('change', (e) => {
            addLogEntry(`Model changed to: ${e.target.options[e.target.selectedIndex].text}`, 'info');
        });
    }

    // Strategy select change
    const strategySelect = document.getElementById('strategySelect');
    if (strategySelect) {
        strategySelect.addEventListener('change', (e) => {
            const strategy = e.target.value;
            const description = strategy === 'yield' ?
                'Aggressive strategy: Higher APR, accepts higher risk' :
                'Conservative strategy: Stable pools, lower risk';
            addLogEntry(`Strategy changed to: ${strategy} - ${description}`, 'info');
        });
    }
}

/**
 * Add log entry to activity log
 */
function addLogEntry(message, type = 'info') {
    const logContainer = document.getElementById('activityLog');
    if (!logContainer) return;

    const timestamp = new Date().toLocaleTimeString();

    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${type}`;
    logEntry.innerHTML = `
        <span class="timestamp">${timestamp}</span>
        <span class="message">${message}</span>
    `;

    // Clear placeholder if exists
    if (logContainer.querySelector('.log-entry .timestamp').textContent === '--:--:--') {
        logContainer.innerHTML = '';
    }

    logContainer.appendChild(logEntry);

    // Auto-scroll to bottom
    logContainer.scrollTop = logContainer.scrollHeight;

    // Limit log entries to 100
    const entries = logContainer.querySelectorAll('.log-entry');
    if (entries.length > 100) {
        entries[0].remove();
    }
}

/**
 * Format number with commas
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Format currency
 */
function formatCurrency(amount) {
    return `$${formatNumber(amount.toFixed(2))}`;
}

/**
 * Copy text to clipboard
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        addLogEntry('Copied to clipboard', 'success');
    } catch (error) {
        console.error('Failed to copy:', error);
        addLogEntry('Failed to copy to clipboard', 'error');
    }
}

/**
 * Show notification
 */
function showNotification(message, type = 'info') {
    // Simple notification - can be enhanced with a toast library
    addLogEntry(message, type);

    // Browser notification (if permitted)
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Arbitrum Liquidity Agent', {
            body: message,
            icon: '/favicon.ico'
        });
    }
}

/**
 * Request notification permission
 */
async function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        const permission = await Notification.requestPermission();
        if (permission === 'granted') {
            addLogEntry('Notifications enabled', 'success');
        }
    }
}

/**
 * Handle errors globally
 */
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    addLogEntry(`Error: ${event.error?.message || 'Unknown error'}`, 'error');
});

/**
 * Handle unhandled promise rejections
 */
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    addLogEntry(`Promise rejection: ${event.reason?.message || 'Unknown error'}`, 'error');
});

/**
 * Export functions for global access
 */
window.addLogEntry = addLogEntry;
window.formatNumber = formatNumber;
window.formatCurrency = formatCurrency;
window.copyToClipboard = copyToClipboard;
window.showNotification = showNotification;

/**
 * Initialize on DOM ready
 */
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

// Request notification permission after 5 seconds
setTimeout(requestNotificationPermission, 5000);

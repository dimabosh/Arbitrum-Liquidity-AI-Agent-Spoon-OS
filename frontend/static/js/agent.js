/**
 * Agent Manager
 * Handles agent lifecycle, communication, and UI updates
 */

class AgentManager {
    constructor(walletManager) {
        this.walletManager = walletManager;
        this.isRunning = false;
        this.ws = null;
        this.config = {
            model: 'anthropic/claude-3.5-sonnet',
            strategy: 'yield',
            rpcUrl: 'https://arb1.arbitrum.io/rpc',
            openrouterKey: ''
        };
        this.positions = [];
        this.recommendations = [];
    }

    /**
     * Start the agent
     */
    async start() {
        if (!this.walletManager.isConnected()) {
            this.addLog('Please connect your wallet first', 'error');
            return false;
        }

        // Get configuration
        this.config = {
            model: document.getElementById('modelSelect')?.value || this.config.model,
            strategy: document.getElementById('strategySelect')?.value || this.config.strategy,
            rpcUrl: this.config.rpcUrl,  // Use default from config
            openrouterKey: ''  // Always use server key
        };

        this.addLog('Using server configuration', 'info');

        try {
            this.addLog('Starting agent...', 'info');
            this.updateStatus('Starting...', 'loading');

            // Initialize agent via API
            const response = await fetch('/api/agent/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    wallet_address: this.walletManager.getAccount(),
                    model: this.config.model,
                    strategy: this.config.strategy,
                    rpc_url: this.config.rpcUrl,
                    openrouter_key: this.config.openrouterKey
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to start agent');
            }

            this.isRunning = true;
            this.updateStatus('Running', 'active');
            this.updateAgentInfo();
            this.updateUI();

            // Connect WebSocket for real-time updates
            this.connectWebSocket();

            this.addLog('Agent started successfully!', 'success');
            this.addLog(`Model: ${this.config.model}`, 'info');
            this.addLog(`Strategy: ${this.config.strategy}`, 'info');

            // Start monitoring
            this.startMonitoring();

            // Fetch initial recommendations
            this.addLog('Analyzing liquidity pools...', 'info');
            await this.fetchRecommendations();

            return true;
        } catch (error) {
            console.error('Error starting agent:', error);
            this.addLog(`Failed to start agent: ${error.message}`, 'error');
            this.updateStatus('Error', 'inactive');
            return false;
        }
    }

    /**
     * Stop the agent
     */
    async stop() {
        try {
            this.addLog('Stopping agent...', 'info');

            const response = await fetch('/api/agent/stop', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    wallet_address: this.walletManager.getAccount()
                })
            });

            if (!response.ok) {
                throw new Error('Failed to stop agent');
            }

            this.isRunning = false;
            this.updateStatus('Stopped', 'inactive');
            this.updateUI();

            // Disconnect WebSocket
            if (this.ws) {
                this.ws.close();
                this.ws = null;
            }

            this.addLog('Agent stopped', 'success');
            return true;
        } catch (error) {
            console.error('Error stopping agent:', error);
            this.addLog(`Failed to stop agent: ${error.message}`, 'error');
            return false;
        }
    }

    /**
     * Connect WebSocket for real-time updates
     */
    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/agent/${this.walletManager.getAccount()}`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.addLog('Connected to real-time updates', 'success');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.addLog('WebSocket connection error', 'error');
        };

        this.ws.onclose = () => {
            this.addLog('Disconnected from real-time updates', 'warning');

            // Attempt to reconnect if agent is still running
            if (this.isRunning) {
                setTimeout(() => this.connectWebSocket(), 5000);
            }
        };
    }

    /**
     * Handle WebSocket messages
     */
    handleWebSocketMessage(data) {
        const { type, payload } = data;

        switch (type) {
            case 'log':
                this.addLog(payload.message, payload.level || 'info');
                break;

            case 'positions_update':
                this.updatePositions(payload.positions);
                break;

            case 'recommendations_update':
                this.updateRecommendations(payload.recommendations);
                break;

            case 'status_update':
                this.updateStatus(payload.status, payload.state);
                break;

            default:
                console.log('Unknown WebSocket message type:', type);
        }
    }

    /**
     * Start monitoring positions
     */
    async startMonitoring() {
        // Initial fetch
        await this.fetchPositions();
        await this.fetchRecommendations();

        // Poll every 30 seconds
        this.monitoringInterval = setInterval(async () => {
            if (this.isRunning) {
                await this.fetchPositions();
                await this.fetchRecommendations();
            }
        }, 30000);
    }

    /**
     * Fetch current positions
     */
    async fetchPositions() {
        try {
            const response = await fetch(`/api/positions/${this.walletManager.getAccount()}`);
            const data = await response.json();

            if (response.ok && data.positions) {
                this.updatePositions(data.positions);
            }
        } catch (error) {
            console.error('Error fetching positions:', error);
        }
    }

    /**
     * Fetch recommendations
     */
    async fetchRecommendations() {
        try {
            const response = await fetch(`/api/recommendations/${this.walletManager.getAccount()}`);
            const data = await response.json();

            if (response.ok && data.recommendations) {
                this.updateRecommendations(data.recommendations);
            }
        } catch (error) {
            console.error('Error fetching recommendations:', error);
        }
    }

    /**
     * Update positions display
     */
    updatePositions(positions) {
        this.positions = positions;
        const container = document.getElementById('positionsContainer');
        if (!container) return;

        if (positions.length === 0) {
            container.innerHTML = '<div class="empty-state">No active positions found</div>';
            return;
        }

        container.innerHTML = positions.map(pos => `
            <div class="position-card">
                <div class="position-header">
                    <span class="position-pair">${pos.token0}/${pos.token1}</span>
                    <span class="position-status ${pos.in_range ? 'in-range' : 'out-of-range'}">
                        ${pos.in_range ? '✓ In Range' : '⚠ Out of Range'}
                    </span>
                </div>
                <div class="position-details">
                    <div class="detail-row">
                        <span class="detail-label">Value:</span>
                        <span class="detail-value">$${pos.current_value_usd?.toFixed(2) || '0.00'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Unclaimed Fees:</span>
                        <span class="detail-value">$${pos.unclaimed_fees_usd?.toFixed(2) || '0.00'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Position ID:</span>
                        <span class="detail-value">#${pos.position_id}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">DEX:</span>
                        <span class="detail-value">${pos.dex || 'Uniswap V3'}</span>
                    </div>
                </div>
            </div>
        `).join('');
    }

    /**
     * Update recommendations display
     */
    updateRecommendations(recommendations) {
        this.recommendations = recommendations;
        const container = document.getElementById('recommendationsContainer');
        if (!container) return;

        if (recommendations.length === 0) {
            container.innerHTML = '<div class="empty-state">No recommendations yet</div>';
            return;
        }

        container.innerHTML = recommendations.map(rec => `
            <div class="recommendation-card">
                <div class="recommendation-score">
                    Score: ${rec.score?.toFixed(1) || '0'}/100
                </div>
                <h3>${rec.token_pair}</h3>
                <div class="position-details">
                    <div class="detail-row">
                        <span class="detail-label">Expected APR:</span>
                        <span class="detail-value">${rec.expected_apr?.toFixed(2) || '0'}%</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Amount:</span>
                        <span class="detail-value">$${rec.recommended_amount_usd?.toFixed(0) || '0'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Risk:</span>
                        <span class="detail-value" style="color: ${
                            rec.risk_level === 'low' ? 'var(--success-color)' :
                            rec.risk_level === 'medium' ? 'var(--warning-color)' :
                            'var(--danger-color)'
                        }">${rec.risk_level?.toUpperCase() || 'UNKNOWN'}</span>
                    </div>
                </div>
                <p class="recommendation-reason">${rec.reason || ''}</p>
                ${rec.warnings && rec.warnings.length > 0 ? `
                    <div class="recommendation-warnings">
                        ${rec.warnings.map(w => `
                            <div class="warning-item">⚠️ ${w}</div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `).join('');
    }

    /**
     * Update agent status
     */
    updateStatus(status, state = 'active') {
        const statusEl = document.getElementById('agentStatusValue');
        if (statusEl) {
            statusEl.textContent = status;
            statusEl.className = `status-value ${state}`;
        }

        const networkEl = document.getElementById('networkStatus');
        if (networkEl && this.walletManager.isConnected()) {
            networkEl.textContent = 'Arbitrum One';
        }
    }

    /**
     * Update agent info display
     */
    updateAgentInfo() {
        const modelEl = document.getElementById('currentModel');
        const strategyEl = document.getElementById('currentStrategy');

        if (modelEl) {
            modelEl.textContent = this.config.model.split('/').pop();
        }

        if (strategyEl) {
            strategyEl.textContent = this.config.strategy.charAt(0).toUpperCase() +
                                     this.config.strategy.slice(1);
        }
    }

    /**
     * Update UI based on agent state
     */
    updateUI() {
        const startBtn = document.getElementById('startAgent');
        const stopBtn = document.getElementById('stopAgent');

        if (this.isRunning) {
            startBtn?.classList.add('hidden');
            stopBtn?.classList.remove('hidden');
        } else {
            startBtn?.classList.remove('hidden');
            stopBtn?.classList.add('hidden');
        }
    }

    /**
     * Add log entry
     */
    addLog(message, type = 'info') {
        if (typeof window.addLogEntry === 'function') {
            window.addLogEntry(message, type);
        }
    }
}

// Export for use in other scripts
window.AgentManager = AgentManager;

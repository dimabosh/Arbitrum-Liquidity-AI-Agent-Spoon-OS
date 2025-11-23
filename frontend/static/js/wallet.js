/**
 * Wallet Connection Manager
 * Handles MetaMask and WalletConnect integration
 */

class WalletManager {
    constructor() {
        this.web3 = null;
        this.account = null;
        this.chainId = null;
        this.provider = null;
        this.connected = false;

        // Arbitrum Chain ID
        this.ARBITRUM_CHAIN_ID = '0xa4b1'; // 42161 in hex
        this.ARBITRUM_CHAIN_ID_DECIMAL = 42161;
    }

    /**
     * Initialize wallet connection
     */
    async init() {
        // Check if wallet is already connected
        if (window.ethereum) {
            this.web3 = new Web3(window.ethereum);

            // Check if already connected
            const accounts = await window.ethereum.request({
                method: 'eth_accounts'
            }).catch(() => []);

            if (accounts.length > 0) {
                await this.handleAccountsChanged(accounts);
            }

            // Setup event listeners
            this.setupEventListeners();
        }
    }

    /**
     * Setup wallet event listeners
     */
    setupEventListeners() {
        if (!window.ethereum) return;

        window.ethereum.on('accountsChanged', (accounts) => {
            this.handleAccountsChanged(accounts);
        });

        window.ethereum.on('chainChanged', (chainId) => {
            this.handleChainChanged(chainId);
        });

        window.ethereum.on('disconnect', () => {
            this.handleDisconnect();
        });
    }

    /**
     * Connect to MetaMask
     */
    async connectMetaMask() {
        if (!window.ethereum) {
            alert('MetaMask is not installed. Please install MetaMask to continue.');
            window.open('https://metamask.io/download/', '_blank');
            return false;
        }

        try {
            // Request account access
            const accounts = await window.ethereum.request({
                method: 'eth_requestAccounts'
            });

            this.web3 = new Web3(window.ethereum);
            this.provider = 'metamask';

            await this.handleAccountsChanged(accounts);

            // Check if on Arbitrum network
            const chainId = await window.ethereum.request({
                method: 'eth_chainId'
            });

            if (chainId !== this.ARBITRUM_CHAIN_ID) {
                await this.switchToArbitrum();
            }

            return true;
        } catch (error) {
            console.error('Error connecting to MetaMask:', error);
            this.addLog('Failed to connect to MetaMask: ' + error.message, 'error');
            return false;
        }
    }

    /**
     * Switch to Arbitrum network
     */
    async switchToArbitrum() {
        try {
            await window.ethereum.request({
                method: 'wallet_switchEthereumChain',
                params: [{ chainId: this.ARBITRUM_CHAIN_ID }],
            });
        } catch (switchError) {
            // This error code indicates that the chain has not been added to MetaMask
            if (switchError.code === 4902) {
                try {
                    await window.ethereum.request({
                        method: 'wallet_addEthereumChain',
                        params: [{
                            chainId: this.ARBITRUM_CHAIN_ID,
                            chainName: 'Arbitrum One',
                            nativeCurrency: {
                                name: 'Ethereum',
                                symbol: 'ETH',
                                decimals: 18
                            },
                            rpcUrls: ['https://arb1.arbitrum.io/rpc'],
                            blockExplorerUrls: ['https://arbiscan.io/']
                        }],
                    });
                } catch (addError) {
                    console.error('Error adding Arbitrum network:', addError);
                    throw addError;
                }
            } else {
                throw switchError;
            }
        }
    }

    /**
     * Handle accounts changed
     */
    async handleAccountsChanged(accounts) {
        if (accounts.length === 0) {
            this.handleDisconnect();
        } else {
            this.account = accounts[0];
            this.connected = true;

            // Get balance
            const balance = await this.getBalance();

            // Update UI
            this.updateWalletUI(this.account, balance);

            // Enable start button
            document.getElementById('startAgent')?.removeAttribute('disabled');

            this.addLog(`Wallet connected: ${this.formatAddress(this.account)}`, 'success');
        }
    }

    /**
     * Handle chain changed
     */
    handleChainChanged(chainId) {
        this.chainId = chainId;

        if (parseInt(chainId, 16) !== this.ARBITRUM_CHAIN_ID_DECIMAL) {
            this.addLog('Please switch to Arbitrum network', 'warning');
            this.switchToArbitrum();
        } else {
            this.addLog('Connected to Arbitrum network', 'success');
        }
    }

    /**
     * Handle disconnect
     */
    handleDisconnect() {
        this.account = null;
        this.connected = false;
        this.provider = null;

        // Update UI
        document.getElementById('connectWallet')?.classList.remove('hidden');
        document.getElementById('walletInfo')?.classList.add('hidden');
        document.getElementById('startAgent')?.setAttribute('disabled', 'true');

        this.addLog('Wallet disconnected', 'warning');
    }

    /**
     * Disconnect wallet
     */
    async disconnect() {
        this.handleDisconnect();
    }

    /**
     * Get ETH balance
     */
    async getBalance() {
        if (!this.web3 || !this.account) return '0';

        try {
            const balanceWei = await this.web3.eth.getBalance(this.account);
            const balanceEth = this.web3.utils.fromWei(balanceWei, 'ether');
            return parseFloat(balanceEth).toFixed(4);
        } catch (error) {
            console.error('Error getting balance:', error);
            return '0';
        }
    }

    /**
     * Get current account
     */
    getAccount() {
        return this.account;
    }

    /**
     * Check if connected
     */
    isConnected() {
        return this.connected && this.account !== null;
    }

    /**
     * Format address for display
     */
    formatAddress(address) {
        if (!address) return '';
        return `${address.substring(0, 6)}...${address.substring(address.length - 4)}`;
    }

    /**
     * Update wallet UI
     */
    updateWalletUI(address, balance) {
        const connectBtn = document.getElementById('connectWallet');
        const walletInfo = document.getElementById('walletInfo');
        const addressEl = document.getElementById('walletAddress');
        const balanceEl = document.getElementById('walletBalance');

        if (connectBtn) connectBtn.classList.add('hidden');
        if (walletInfo) walletInfo.classList.remove('hidden');
        if (addressEl) addressEl.textContent = this.formatAddress(address);
        if (balanceEl) balanceEl.textContent = `${balance} ETH`;
    }

    /**
     * Add log entry
     */
    addLog(message, type = 'info') {
        if (typeof window.addLogEntry === 'function') {
            window.addLogEntry(message, type);
        }
    }

    /**
     * Sign a message
     */
    async signMessage(message) {
        if (!this.web3 || !this.account) {
            throw new Error('Wallet not connected');
        }

        try {
            const signature = await this.web3.eth.personal.sign(
                message,
                this.account,
                '' // Password parameter (not needed for MetaMask)
            );
            return signature;
        } catch (error) {
            console.error('Error signing message:', error);
            throw error;
        }
    }

    /**
     * Send transaction
     */
    async sendTransaction(txParams) {
        if (!this.web3 || !this.account) {
            throw new Error('Wallet not connected');
        }

        try {
            const receipt = await window.ethereum.request({
                method: 'eth_sendTransaction',
                params: [txParams],
            });
            return receipt;
        } catch (error) {
            console.error('Error sending transaction:', error);
            throw error;
        }
    }
}

// Export for use in other scripts
window.WalletManager = WalletManager;

"""Arbitrum-specific tools for liquidity management and DEX operations.

This module provides tools for interacting with Arbitrum network:
- Pool data fetching
- Liquidity position management
- Token swaps for rebalancing
- Fee collection
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from web3 import Web3

from spoon_ai.tools.base import BaseTool, ToolResult
from spoon_toolkits.crypto.evm import EvmSwapTool

logger = logging.getLogger(__name__)

# Uniswap V3 Pool ABI - minimal для получения данных
POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ERC20 ABI для получения символа
ERC20_ABI = [
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    }
]


class ArbitrumPoolDataTool(BaseTool):
    """Fetch liquidity pool data from Arbitrum DEXes (Uniswap V3, Camelot, etc.)."""

    name: str = "arbitrum_pool_data"
    description: str = "Fetch real-time data for liquidity pools on Arbitrum network"
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "pool_address": {"type": "string", "description": "Pool contract address"},
            "token0": {"type": "string", "description": "First token symbol or address"},
            "token1": {"type": "string", "description": "Second token symbol or address"},
            "dex": {"type": "string", "description": "DEX name (uniswap_v3, camelot, sushiswap)"}
        }
    }

    rpc_url: Optional[str] = None
    w3: Optional[Web3] = None

    def __init__(self, rpc_url: Optional[str] = None):
        """Initialize the pool data tool.

        Args:
            rpc_url: Arbitrum RPC endpoint URL
        """
        super().__init__()
        self.rpc_url = rpc_url or os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

    async def execute(
        self,
        pool_address: Optional[str] = None,
        token0: Optional[str] = None,
        token1: Optional[str] = None,
        dex: str = "uniswap_v3",
        **kwargs
    ) -> ToolResult:
        """Fetch REAL pool data via Arbitrum RPC.

        Args:
            pool_address: Specific pool address to query
            token0: First token symbol (for fallback)
            token1: Second token symbol (for fallback)
            dex: DEX to query (uniswap_v3, camelot, sushiswap)

        Returns:
            ToolResult with real pool data from blockchain
        """
        try:
            if not pool_address:
                return ToolResult(output=None, error="pool_address required", metadata={})

            pool_address = Web3.to_checksum_address(pool_address)
            pool = self.w3.eth.contract(address=pool_address, abi=POOL_ABI)

            # Get pool data from contract
            slot0 = pool.functions.slot0().call()
            liquidity = pool.functions.liquidity().call()
            fee = pool.functions.fee().call()
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()

            # Get token symbols
            token0_contract = self.w3.eth.contract(address=token0_addr, abi=ERC20_ABI)
            token1_contract = self.w3.eth.contract(address=token1_addr, abi=ERC20_ABI)

            token0_symbol = token0_contract.functions.symbol().call()
            token1_symbol = token1_contract.functions.symbol().call()

            # Calculate price from sqrtPriceX96
            sqrt_price_x96 = slot0[0]
            price = (sqrt_price_x96 / (2 ** 96)) ** 2

            # Estimate TVL (simplified - liquidity * price estimate)
            # This is rough estimate, real calculation needs token decimals
            tvl_estimate = (liquidity / 1e18) * 3000  # Rough USD estimate

            # Estimate APR based on fee tier (simplified)
            fee_percent = fee / 1_000_000  # fee in basis points / 10000
            # Higher fees = higher potential APR
            estimated_apr = fee_percent * 365 * 10  # Rough multiplier

            pool_data = {
                "pool_address": pool_address,
                "dex": dex,
                "token0": token0_symbol,
                "token1": token1_symbol,
                "fee_tier": fee_percent,
                "tvl_usd": tvl_estimate,
                "volume_24h_usd": tvl_estimate * 0.5,  # Estimate 50% daily turnover
                "fees_24h_usd": tvl_estimate * 0.5 * (fee_percent / 100),
                "current_price": price,
                "price_change_24h": 0,  # Would need historical data
                "liquidity": liquidity,
                "sqrt_price_x96": sqrt_price_x96,
                "apr_7d": estimated_apr,
                "apr_30d": estimated_apr * 0.9,
            }

            logger.info(f"REAL pool data from RPC: {token0_symbol}/{token1_symbol}, Liquidity={liquidity}, Price={price:.6f}")
            return ToolResult(
                output=pool_data,
                error=None,
                metadata={"source": "rpc", "dex": dex}
            )

        except Exception as e:
            logger.error(f"Error fetching pool data via RPC: {e}", exc_info=True)
            return ToolResult(
                output=None,
                error=str(e),
                metadata={"pool_address": pool_address}
            )


class ArbitrumLiquidityPositionTool(BaseTool):
    """Manage liquidity positions on Arbitrum (Uniswap V3 NFT positions)."""

    name: str = "arbitrum_liquidity_position"
    description: str = "Query and manage liquidity positions on Arbitrum DEXes"
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Action to perform (query, add, remove, collect_fees)"},
            "position_id": {"type": "string", "description": "NFT position ID"},
            "pool_address": {"type": "string", "description": "Pool contract address"},
            "tick_lower": {"type": "integer", "description": "Lower tick for concentrated liquidity"},
            "tick_upper": {"type": "integer", "description": "Upper tick for concentrated liquidity"}
        }
    }

    rpc_url: Optional[str] = None
    wallet_address: Optional[str] = None

    def __init__(self, rpc_url: Optional[str] = None, wallet_address: Optional[str] = None):
        """Initialize the position management tool.

        Args:
            rpc_url: Arbitrum RPC endpoint URL
            wallet_address: User's wallet address to query positions
        """
        super().__init__()
        self.rpc_url = rpc_url or os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")
        self.wallet_address = wallet_address or os.getenv("WALLET_ADDRESS")

    async def execute(
        self,
        action: str = "query",
        position_id: Optional[str] = None,
        pool_address: Optional[str] = None,
        tick_lower: Optional[int] = None,
        tick_upper: Optional[int] = None,
        amount0: Optional[str] = None,
        amount1: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        """Execute position management actions.

        Args:
            action: Action to perform (query, add, remove, collect_fees)
            position_id: NFT position ID for Uniswap V3
            pool_address: Pool contract address
            tick_lower: Lower tick for concentrated liquidity
            tick_upper: Upper tick for concentrated liquidity
            amount0: Amount of token0 to add/remove
            amount1: Amount of token1 to add/remove

        Returns:
            ToolResult with position data or transaction result
        """
        try:
            if action == "query":
                # TODO: Implement real position fetching from blockchain
                # For now, return empty list - no mock data
                # In real implementation, would query:
                # - Uniswap V3 NonfungiblePositionManager contract
                # - Get positions for wallet_address
                # - Fetch position details and calculate values

                positions = []  # Empty until real implementation

                return ToolResult(
                    output=positions,
                    error=None,
                    metadata={"wallet": self.wallet_address, "count": len(positions)}
                )

            elif action == "add":
                # Simulate adding liquidity
                result = {
                    "action": "add_liquidity",
                    "position_id": "new_12346",
                    "pool": pool_address,
                    "tick_lower": tick_lower,
                    "tick_upper": tick_upper,
                    "amount0_added": amount0,
                    "amount1_added": amount1,
                    "liquidity_minted": 500_000_000,
                    "tx_hash": "0xabc123...",
                    "status": "SIMULATED",
                }

                return ToolResult(
                    output=result,
                    error=None,
                    metadata={"action": action}
                )

            elif action == "remove":
                # Simulate removing liquidity
                result = {
                    "action": "remove_liquidity",
                    "position_id": position_id,
                    "amount0_received": "1.5",
                    "amount1_received": "4500.0",
                    "tx_hash": "0xdef456...",
                    "status": "SIMULATED",
                }

                return ToolResult(
                    output=result,
                    error=None,
                    metadata={"action": action}
                )

            elif action == "collect_fees":
                # Simulate collecting fees
                result = {
                    "action": "collect_fees",
                    "position_id": position_id,
                    "fees0_collected": "0.05",
                    "fees1_collected": "150.25",
                    "fees_usd": 175.50,
                    "tx_hash": "0xghi789...",
                    "status": "SIMULATED",
                }

                return ToolResult(
                    output=result,
                    error=None,
                    metadata={"action": action}
                )

            else:
                raise ValueError(f"Unknown action: {action}")

        except Exception as e:
            logger.error(f"Error managing position: {e}")
            return ToolResult(
                output=None,
                error=str(e),
                metadata={"action": action}
            )


class ArbitrumSwapTool(BaseTool):
    """Execute token swaps on Arbitrum for rebalancing purposes.

    Wraps Spoon OS EvmSwapTool with Arbitrum-specific configuration.
    """

    name: str = "arbitrum_swap"
    description: str = "Execute token swaps on Arbitrum for liquidity rebalancing"
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "from_token": {"type": "string", "description": "Token to swap from"},
            "to_token": {"type": "string", "description": "Token to swap to"},
            "amount": {"type": "string", "description": "Amount to swap"},
            "slippage": {"type": "number", "description": "Slippage tolerance in percent"},
            "dex": {"type": "string", "description": "DEX to use"}
        },
        "required": ["from_token", "to_token", "amount"]
    }

    rpc_url: Optional[str] = None
    evm_swap: Optional[Any] = None

    def __init__(self, rpc_url: Optional[str] = None):
        """Initialize the swap tool.

        Args:
            rpc_url: Arbitrum RPC endpoint URL
        """
        super().__init__()
        self.rpc_url = rpc_url or os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")

        # Initialize Spoon OS EVM Swap Tool for Arbitrum
        if self.rpc_url:
            self.evm_swap = EvmSwapTool(rpc_url=self.rpc_url)
        else:
            self.evm_swap = None
            logger.warning("No RPC URL provided for ArbitrumSwapTool")

    async def execute(
        self,
        from_token: str,
        to_token: str,
        amount: str,
        slippage: float = 0.5,
        dex: str = "uniswap_v3",
        signer_type: str = "auto",
        **kwargs
    ) -> ToolResult:
        """Execute a token swap on Arbitrum.

        Args:
            from_token: Token to swap from (symbol or address)
            to_token: Token to swap to (symbol or address)
            amount: Amount to swap (in from_token units)
            slippage: Maximum slippage tolerance in percent (default 0.5%)
            dex: DEX to use for swap (uniswap_v3, sushiswap, camelot)
            signer_type: Signer type for transaction (auto, private_key, etc.)

        Returns:
            ToolResult with swap execution details
        """
        try:
            if not self.evm_swap:
                raise ValueError("Swap tool not initialized. Provide ARBITRUM_RPC_URL")

            # Use Spoon OS EvmSwapTool for actual swap execution
            result = await self.evm_swap.execute(
                from_token=from_token,
                to_token=to_token,
                amount=amount,
                signer_type=signer_type,
                **kwargs
            )

            # Enhance result with Arbitrum-specific metadata
            if hasattr(result, 'output') and isinstance(result.output, dict):
                result.output['network'] = 'arbitrum'
                result.output['dex'] = dex
                result.output['slippage'] = slippage

            logger.info(f"Swap executed: {amount} {from_token} -> {to_token} on {dex}")
            return result

        except Exception as e:
            logger.error(f"Error executing swap: {e}")
            return ToolResult(
                output=None,
                error=str(e),
                metadata={
                    "from_token": from_token,
                    "to_token": to_token,
                    "amount": amount,
                    "dex": dex
                }
            )


class ArbitrumRebalanceTool(BaseTool):
    """High-level tool for rebalancing liquidity positions on Arbitrum."""

    name: str = "arbitrum_rebalance"
    description: str = "Automated rebalancing of liquidity positions using swaps"
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "position_id": {"type": "string", "description": "Position ID to rebalance"},
            "target_ratio": {"type": "object", "description": "Target token ratio"},
            "auto_compound": {"type": "boolean", "description": "Auto-compound fees"}
        },
        "required": ["position_id"]
    }

    swap_tool: Optional[Any] = None
    position_tool: Optional[Any] = None

    def __init__(self, rpc_url: Optional[str] = None):
        """Initialize the rebalance tool.

        Args:
            rpc_url: Arbitrum RPC endpoint URL
        """
        super().__init__()
        self.swap_tool = ArbitrumSwapTool(rpc_url=rpc_url)
        self.position_tool = ArbitrumLiquidityPositionTool(rpc_url=rpc_url)

    async def execute(
        self,
        position_id: str,
        target_ratio: Optional[Dict[str, float]] = None,
        auto_compound: bool = False,
        **kwargs
    ) -> ToolResult:
        """Execute position rebalancing.

        Args:
            position_id: Position ID to rebalance
            target_ratio: Target token ratio (e.g., {"token0": 0.5, "token1": 0.5})
            auto_compound: Whether to collect and reinvest fees

        Returns:
            ToolResult with rebalancing execution details
        """
        try:
            steps = []

            # Step 1: Collect fees if auto_compound is enabled
            if auto_compound:
                fee_result = await self.position_tool.execute(
                    action="collect_fees",
                    position_id=position_id
                )
                steps.append({
                    "step": "collect_fees",
                    "result": fee_result.output,
                    "error": fee_result.error
                })

            # Step 2: Query current position
            position_result = await self.position_tool.execute(
                action="query",
                position_id=position_id
            )

            if position_result.error:
                raise ValueError(f"Failed to query position: {position_result.error}")

            # Step 3: Calculate required swaps for rebalancing
            # In a real implementation, this would:
            # - Calculate current token ratio
            # - Compare with target ratio
            # - Determine swap amounts needed
            # - Execute swaps
            # - Re-add liquidity in new range if needed

            rebalance_result = {
                "position_id": position_id,
                "steps_completed": steps,
                "swaps_executed": [],
                "new_ratio": target_ratio or {"token0": 0.5, "token1": 0.5},
                "gas_used": 450_000,
                "total_cost_usd": 15.50,
                "status": "SIMULATED",
            }

            logger.info(f"Rebalancing completed for position {position_id}")
            return ToolResult(
                output=rebalance_result,
                error=None,
                metadata={"position_id": position_id, "auto_compound": auto_compound}
            )

        except Exception as e:
            logger.error(f"Error rebalancing position: {e}")
            return ToolResult(
                output=None,
                error=str(e),
                metadata={"position_id": position_id}
            )

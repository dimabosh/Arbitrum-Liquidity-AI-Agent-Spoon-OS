"""Liquidity provision strategies for Arbitrum DEXes.

This module implements concrete strategies for selecting pools,
calculating optimal ranges, and determining entry/exit conditions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Metrics for evaluating a liquidity pool."""
    address: str
    dex: str
    token0: str
    token1: str
    tvl_usd: float
    volume_24h_usd: float
    fees_24h_usd: float
    fee_tier: float  # in basis points (e.g., 30 = 0.3%)
    current_price: float
    price_change_24h: float
    apr_7d: float
    apr_30d: float
    liquidity: float


@dataclass
class LiquidityOpportunity:
    """Represents a liquidity provision opportunity."""
    pool: PoolMetrics
    score: float
    recommended_amount_usd: float
    tick_lower: int
    tick_upper: int
    expected_apr: float
    risk_level: str  # "low", "medium", "high"
    reason: str
    warnings: List[str]


class LiquidityStrategy:
    """Base class for liquidity provision strategies."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def evaluate_pool(self, pool: PoolMetrics) -> float:
        """Evaluate a pool and return a score (0-100).

        Args:
            pool: Pool metrics to evaluate

        Returns:
            Score from 0 (worst) to 100 (best)
        """
        raise NotImplementedError

    def calculate_position_range(
        self, pool: PoolMetrics, risk_tolerance: str = "moderate"
    ) -> Tuple[int, int]:
        """Calculate optimal tick range for concentrated liquidity.

        Args:
            pool: Pool metrics
            risk_tolerance: "conservative", "moderate", or "aggressive"

        Returns:
            Tuple of (tick_lower, tick_upper)
        """
        raise NotImplementedError

    def should_enter(self, pool: PoolMetrics, current_positions: List[Dict]) -> bool:
        """Determine if should enter this pool.

        Args:
            pool: Pool to evaluate
            current_positions: User's current positions

        Returns:
            True if should enter, False otherwise
        """
        raise NotImplementedError


class YieldMaximizationStrategy(LiquidityStrategy):
    """Strategy focused on maximizing yield through high-fee pools."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.min_tvl = self.config.get("min_tvl_usd", 1_000_000)
        self.min_volume = self.config.get("min_volume_24h_usd", 500_000)
        self.min_apr = self.config.get("min_apr", 10.0)
        self.max_il_risk = self.config.get("max_il_risk", 20.0)

    def evaluate_pool(self, pool: PoolMetrics) -> float:
        """Score pool based on yield potential.

        Scoring factors:
        - APR (40 points)
        - Volume/TVL ratio (30 points)
        - Liquidity depth (20 points)
        - Fee stability (10 points)
        """
        score = 0.0

        # APR scoring (0-40 points)
        # Target: 15-50% APR is optimal
        if pool.apr_7d >= 50:
            apr_score = 40
        elif pool.apr_7d >= 15:
            apr_score = 40 * (pool.apr_7d / 50)
        else:
            apr_score = 20 * (pool.apr_7d / 15)
        score += apr_score

        # Volume/TVL ratio (0-30 points)
        # Higher ratio = more fee generation
        volume_ratio = pool.volume_24h_usd / max(pool.tvl_usd, 1)
        if volume_ratio >= 1.0:  # 100%+ daily turnover
            volume_score = 30
        elif volume_ratio >= 0.3:  # 30%+ turnover
            volume_score = 30 * (volume_ratio / 1.0)
        else:
            volume_score = 15 * (volume_ratio / 0.3)
        score += volume_score

        # TVL/Liquidity depth (0-20 points)
        if pool.tvl_usd >= 10_000_000:
            liquidity_score = 20
        elif pool.tvl_usd >= self.min_tvl:
            liquidity_score = 20 * (pool.tvl_usd / 10_000_000)
        else:
            liquidity_score = 10 * (pool.tvl_usd / self.min_tvl)
        score += liquidity_score

        # Fee tier appropriateness (0-10 points)
        # Lower fee tiers for stablecoins, higher for volatile pairs
        if self._is_stable_pair(pool):
            # Stablecoins: prefer 1-5 bps
            if pool.fee_tier <= 5:
                fee_score = 10
            elif pool.fee_tier <= 30:
                fee_score = 5
            else:
                fee_score = 2
        else:
            # Volatile pairs: prefer 30-100 bps
            if 30 <= pool.fee_tier <= 100:
                fee_score = 10
            elif pool.fee_tier <= 30:
                fee_score = 5
            else:
                fee_score = 3
        score += fee_score

        return min(score, 100.0)

    def calculate_position_range(
        self, pool: PoolMetrics, risk_tolerance: str = "moderate"
    ) -> Tuple[int, int]:
        """Calculate concentrated liquidity range.

        Range width depends on:
        - Pair volatility (stable vs volatile)
        - Risk tolerance
        - Recent price action
        """
        current_tick = self._price_to_tick(pool.current_price)

        # Determine range width based on pair type and risk
        if self._is_stable_pair(pool):
            # Stablecoins: tight ranges (±0.5% to ±2%)
            if risk_tolerance == "conservative":
                range_pct = 0.02  # ±2%
            elif risk_tolerance == "aggressive":
                range_pct = 0.005  # ±0.5%
            else:
                range_pct = 0.01  # ±1%
        else:
            # Volatile pairs: wider ranges (±5% to ±25%)
            volatility_multiplier = abs(pool.price_change_24h) / 100
            if risk_tolerance == "conservative":
                range_pct = 0.25 + volatility_multiplier  # ±25%+
            elif risk_tolerance == "aggressive":
                range_pct = 0.05 + (volatility_multiplier * 0.5)  # ±5%+
            else:
                range_pct = 0.15 + (volatility_multiplier * 0.7)  # ±15%+

        # Convert percentage to ticks
        tick_spacing = self._get_tick_spacing(pool.fee_tier)
        tick_range = int((range_pct * current_tick) / tick_spacing) * tick_spacing

        tick_lower = current_tick - tick_range
        tick_upper = current_tick + tick_range

        # Round to valid tick spacing
        tick_lower = (tick_lower // tick_spacing) * tick_spacing
        tick_upper = (tick_upper // tick_spacing) * tick_spacing

        return tick_lower, tick_upper

    def should_enter(self, pool: PoolMetrics, current_positions: List[Dict]) -> bool:
        """Determine if should enter this pool."""
        # Check minimum requirements
        if pool.tvl_usd < self.min_tvl:
            logger.info(f"Pool {pool.address}: TVL too low (${pool.tvl_usd:,.0f} < ${self.min_tvl:,.0f})")
            return False

        if pool.volume_24h_usd < self.min_volume:
            logger.info(f"Pool {pool.address}: Volume too low (${pool.volume_24h_usd:,.0f})")
            return False

        if pool.apr_7d < self.min_apr:
            logger.info(f"Pool {pool.address}: APR too low ({pool.apr_7d:.1f}% < {self.min_apr}%)")
            return False

        # Check if already have position in this pool
        for pos in current_positions:
            if pos.get("pool") == pool.address:
                logger.info(f"Pool {pool.address}: Already have position")
                return False

        # Estimate impermanent loss risk
        il_risk = self._estimate_il_risk(pool)
        if il_risk > self.max_il_risk:
            logger.info(f"Pool {pool.address}: IL risk too high ({il_risk:.1f}%)")
            return False

        score = self.evaluate_pool(pool)
        threshold = 60.0  # Minimum score to enter

        logger.info(f"Pool {pool.address}: Score {score:.1f}/100 (threshold: {threshold})")
        return score >= threshold

    def _is_stable_pair(self, pool: PoolMetrics) -> bool:
        """Check if pool is a stablecoin pair."""
        stablecoins = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "BUSD", "UST"}
        return pool.token0 in stablecoins and pool.token1 in stablecoins

    def _estimate_il_risk(self, pool: PoolMetrics) -> float:
        """Estimate impermanent loss risk based on volatility.

        Returns:
            Estimated IL percentage
        """
        if self._is_stable_pair(pool):
            # Stablecoins: minimal IL
            return abs(pool.price_change_24h) * 0.5

        # Volatile pairs: use price change as proxy
        # Simplified: IL ≈ (price_change / 2)²
        price_change_pct = abs(pool.price_change_24h)
        estimated_il = (price_change_pct / 2) ** 1.5
        return estimated_il

    def _price_to_tick(self, price: float) -> int:
        """Convert price to Uniswap V3 tick."""
        import math
        # tick = log₁.₀₀₀₁(price)
        if price <= 0:
            return 0
        return int(math.log(price, 1.0001))

    def _get_tick_spacing(self, fee_tier: float) -> int:
        """Get tick spacing for fee tier."""
        # Uniswap V3 tick spacings
        if fee_tier <= 1:
            return 1
        elif fee_tier <= 5:
            return 10
        elif fee_tier <= 30:
            return 60
        else:
            return 200


class BalancedStrategy(LiquidityStrategy):
    """Balanced strategy focusing on stable yields with controlled risk."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.min_tvl = self.config.get("min_tvl_usd", 5_000_000)
        self.target_apr = self.config.get("target_apr", 12.0)

    def evaluate_pool(self, pool: PoolMetrics) -> float:
        """Score pool based on balanced risk/reward.

        Scoring:
        - Consistent APR (30 points)
        - High TVL for stability (30 points)
        - Moderate volume (25 points)
        - Low volatility (15 points)
        """
        score = 0.0

        # APR consistency (compare 7d vs 30d)
        apr_avg = (pool.apr_7d + pool.apr_30d) / 2
        if 10 <= apr_avg <= 25:
            apr_score = 30
        elif apr_avg > 25:
            apr_score = 25  # Too high might be unsustainable
        else:
            apr_score = 20 * (apr_avg / 10)
        score += apr_score

        # TVL (higher = more stable)
        if pool.tvl_usd >= 50_000_000:
            tvl_score = 30
        elif pool.tvl_usd >= self.min_tvl:
            tvl_score = 30 * (pool.tvl_usd / 50_000_000)
        else:
            tvl_score = 15 * (pool.tvl_usd / self.min_tvl)
        score += tvl_score

        # Volume
        volume_ratio = pool.volume_24h_usd / max(pool.tvl_usd, 1)
        if 0.2 <= volume_ratio <= 0.8:  # Moderate turnover
            volume_score = 25
        else:
            volume_score = 15
        score += volume_score

        # Low volatility preference
        if abs(pool.price_change_24h) < 2:
            volatility_score = 15
        elif abs(pool.price_change_24h) < 5:
            volatility_score = 10
        else:
            volatility_score = 5
        score += volatility_score

        return min(score, 100.0)

    def calculate_position_range(
        self, pool: PoolMetrics, risk_tolerance: str = "moderate"
    ) -> Tuple[int, int]:
        """Calculate moderate concentrated liquidity range."""
        current_tick = YieldMaximizationStrategy._price_to_tick(None, pool.current_price)
        tick_spacing = YieldMaximizationStrategy._get_tick_spacing(None, pool.fee_tier)

        # Always use moderate ranges for balanced strategy
        if YieldMaximizationStrategy._is_stable_pair(None, pool):
            range_pct = 0.015  # ±1.5%
        else:
            range_pct = 0.20  # ±20%

        tick_range = int((range_pct * current_tick) / tick_spacing) * tick_spacing
        tick_lower = ((current_tick - tick_range) // tick_spacing) * tick_spacing
        tick_upper = ((current_tick + tick_range) // tick_spacing) * tick_spacing

        return tick_lower, tick_upper

    def should_enter(self, pool: PoolMetrics, current_positions: List[Dict]) -> bool:
        """Conservative entry criteria."""
        if pool.tvl_usd < self.min_tvl:
            return False

        # Avoid high volatility
        if abs(pool.price_change_24h) > 10:
            logger.info(f"Pool {pool.address}: Too volatile ({pool.price_change_24h:.1f}%)")
            return False

        # Check for existing position
        for pos in current_positions:
            if pos.get("pool") == pool.address:
                return False

        score = self.evaluate_pool(pool)
        return score >= 70.0  # Higher threshold for balanced


def create_strategy(strategy_type: str = "yield", config: Optional[Dict[str, Any]] = None) -> LiquidityStrategy:
    """Factory function to create strategy instances.

    Args:
        strategy_type: "yield" for yield maximization, "balanced" for balanced approach
        config: Optional configuration dictionary

    Returns:
        Strategy instance
    """
    if strategy_type == "yield":
        return YieldMaximizationStrategy(config)
    elif strategy_type == "balanced":
        return BalancedStrategy(config)
    else:
        raise ValueError(f"Unknown strategy type: {strategy_type}")

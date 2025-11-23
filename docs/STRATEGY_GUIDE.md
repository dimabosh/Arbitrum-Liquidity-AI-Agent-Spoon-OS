# Liquidity Strategy Guide

## Overview

The Arbitrum Liquidity Agent uses **concrete mathematical strategies** to select pools and determine entry/exit points, rather than relying solely on LLM decisions.

## 📊 How Pool Selection Works

### 1. **Strategy Pattern Architecture**

```
User Query → Fetch Pool Data → Apply Strategy → LLM Refinement → Execute
```

The agent uses a two-phase approach:
1. **Strategy-based evaluation**: Mathematical scoring and filtering
2. **LLM refinement**: Natural language reasoning on top-ranked opportunities

### 2. **Available Strategies**

#### A. Yield Maximization Strategy

**Goal**: Maximize fee income through high-yield pools

**Scoring Algorithm** (0-100 points):

```python
# APR Score (40 points max)
- Target: 15-50% APR optimal
- Formula: score = 40 * (apr / 50) capped at 40

# Volume/TVL Ratio (30 points max)
- Target: 100%+ daily turnover
- Formula: score = 30 * (volume_24h / tvl)

# Liquidity Depth (20 points max)
- Target: $10M+ TVL
- Minimum: $1M TVL

# Fee Tier Appropriateness (10 points max)
- Stablecoins: prefer 1-5 bps
- Volatile pairs: prefer 30-100 bps
```

**Entry Criteria**:
- Minimum TVL: $1,000,000
- Minimum Volume: $500,000/24h
- Minimum APR: 10%
- Maximum IL Risk: 20%
- Minimum Score: 60/100

**Position Sizing**:
```python
base_amount = $1,000 + (score/100) * $9,000
max_amount = min(base_amount, pool_tvl * 0.01, $10,000)
```

**Range Calculation**:
- **Stablecoins**: ±0.5% to ±2% (tighter for higher risk tolerance)
- **Volatile**: ±5% to ±25% (adjusted by 24h volatility)

**Example**:
```
Pool: WETH/USDC (Uniswap V3 0.3%)
TVL: $50M, Volume: $75M/24h, APR: 25%

Scoring:
- APR: 40 * (25/50) = 20 points
- Volume ratio: 30 * (75/50) = 30 points (capped)
- TVL: 20 points (>$10M)
- Fee tier: 10 points (optimal for volatile)
Total: 80/100 ✅ ENTER

Position: $8,200
Range: ±15% (current price ± volatility adjustment)
```

#### B. Balanced Strategy

**Goal**: Stable yields with controlled risk

**Scoring Algorithm** (0-100 points):

```python
# APR Consistency (30 points max)
- Target: 10-25% APR
- Compare 7d vs 30d APR for stability

# High TVL (30 points max)
- Target: $50M+ for stability
- Minimum: $5M

# Moderate Volume (25 points max)
- Target: 20-80% daily turnover
- Avoid both extremes

# Low Volatility (15 points max)
- Target: <2% price change/24h
- Penalty for >5% moves
```

**Entry Criteria**:
- Minimum TVL: $5,000,000 (higher than yield strategy)
- Maximum volatility: 10% in 24h
- Minimum Score: 70/100 (stricter)
- No high-risk pools

**Position Sizing**:
- More conservative: cap at $5,000
- Prefer blue-chip pairs

**Range Calculation**:
- **Stablecoins**: ±1.5% (fixed moderate)
- **Volatile**: ±20% (fixed moderate)
- Less aggressive than yield strategy

**Example**:
```
Pool: USDC/USDT (Uniswap V3 0.01%)
TVL: $100M, Volume: $30M/24h, APR: 15%

Scoring:
- APR: 30 points (stable 15%)
- TVL: 30 points (>$50M)
- Volume: 25 points (moderate 30% ratio)
- Volatility: 15 points (<1% stable pair)
Total: 100/100 ✅ ENTER

Position: $5,000
Range: ±1.5% (tight stablecoin range)
```

## 🎯 Entry Logic

### When the Agent Enters Liquidity

```python
def should_enter(pool, current_positions):
    # 1. Check minimums
    if pool.tvl < min_tvl: return False
    if pool.volume < min_volume: return False
    if pool.apr < min_apr: return False

    # 2. Check existing positions
    if already_have_position(pool): return False

    # 3. Estimate impermanent loss
    il_risk = estimate_il(pool)
    if il_risk > max_il: return False

    # 4. Score the pool
    score = evaluate_pool(pool)

    # 5. Decision
    return score >= threshold
```

### Impermanent Loss Estimation

```python
# For stablecoins
IL = abs(price_change_24h) * 0.5

# For volatile pairs
# Simplified: IL ≈ (price_change / 2)^1.5
IL = (abs(price_change_24h) / 2) ^ 1.5
```

### Range Calculation

Uses Uniswap V3 tick mathematics:

```python
current_tick = log₁.₀₀₀₁(current_price)

# Determine range based on:
# - Pair type (stable vs volatile)
# - Risk tolerance (conservative/moderate/aggressive)
# - Recent volatility

range_pct = calculate_range_percentage(...)
tick_range = (range_pct * current_tick)

tick_lower = current_tick - tick_range
tick_upper = current_tick + tick_range

# Round to valid tick spacing (depends on fee tier)
```

### Risk Classification

```python
def classify_risk(pool):
    if is_stablecoin_pair(pool):
        return "low"
    elif abs(price_change_24h) > 10%:
        return "high"
    else:
        return "medium"
```

## 🔄 Rebalancing Logic

### When to Rebalance

The agent monitors:
1. **Out of range**: Price moved outside position range
2. **Fee accumulation**: Unclaimed fees > threshold ($50)
3. **IL threshold**: Estimated IL > 5%
4. **Better opportunities**: New pool scored higher

### Rebalance Actions

1. **Collect Fees**: Always collect first
2. **Assess Position**: Check if still optimal
3. **Calculate Swaps**: Determine token ratio adjustment
4. **Execute Swaps**: Using ArbitrumSwapTool (Spoon OS EvmSwapTool)
5. **Remove Liquidity**: If migrating to new pool
6. **Add Liquidity**: In new range or pool

### Swap Execution for Rebalancing

```python
# Example: Position is 70% WETH / 30% USDC
# Target: 50% / 50%

current_ratio = {"WETH": 0.7, "USDC": 0.3}
target_ratio = {"WETH": 0.5, "USDC": 0.5}

# Need to swap 20% of WETH → USDC
swap_amount = position_value * 0.20

await swap_tool.execute(
    from_token="WETH",
    to_token="USDC",
    amount=swap_amount,
    slippage=0.5,
    dex="uniswap_v3"
)
```

## 📈 Strategy Comparison

| Feature | Yield Maximization | Balanced |
|---------|-------------------|----------|
| **Target APR** | 15-50%+ | 10-25% |
| **Min TVL** | $1M | $5M |
| **Min Score** | 60/100 | 70/100 |
| **Position Size** | $1k-$10k | $1k-$5k |
| **Volatility Tolerance** | High | Low (<10%) |
| **IL Risk Max** | 20% | Lower |
| **Range Width** | Tight to Wide | Moderate |
| **Best For** | Active management | Passive income |

## 🛠️ Usage Examples

### Yield Maximization

```python
agent = ArbitrumLiquidityAgent(
    strategy_type="yield",
    llm_provider="openai"
)

result = await agent.process_query(
    "Find the highest APR pools on Arbitrum and enter top 3"
)
```

**What happens**:
1. Fetches all available pools
2. Scores each using Yield Maximization algorithm
3. Filters: TVL > $1M, Volume > $500k, APR > 10%, Score > 60
4. Ranks by score
5. Calculates optimal ranges based on volatility
6. Presents top opportunities with reasoning

### Balanced Strategy

```python
agent = ArbitrumLiquidityAgent(
    strategy_type="balanced",
    llm_provider="openai"
)

result = await agent.process_query(
    "Find stable liquidity opportunities with low risk"
)
```

**What happens**:
1. Fetches pools
2. Scores using Balanced algorithm
3. Filters: TVL > $5M, Volatility < 10%, Score > 70
4. Prefers large, stable pools
5. Uses moderate ranges
6. Recommends conservative positions

## 🎓 Strategy Selection Guide

### Choose **Yield Maximization** if:
- ✅ You want maximum returns
- ✅ You can monitor positions actively
- ✅ You're comfortable with volatility
- ✅ You can rebalance when needed
- ✅ You have experience with DeFi

### Choose **Balanced** if:
- ✅ You want passive income
- ✅ You prefer stability
- ✅ You're risk-averse
- ✅ You want set-and-forget positions
- ✅ You're new to liquidity provision

## 🔍 How to Verify Strategy Logic

You can inspect the strategy's decision-making:

```python
from tools.liquidity_strategy import YieldMaximizationStrategy, PoolMetrics

strategy = YieldMaximizationStrategy()

pool = PoolMetrics(
    address="0x123...",
    dex="uniswap_v3",
    token0="WETH",
    token1="USDC",
    tvl_usd=50_000_000,
    volume_24h_usd=75_000_000,
    fees_24h_usd=75_000,
    fee_tier=30,  # 0.3%
    current_price=3000,
    price_change_24h=2.5,
    apr_7d=25.0,
    apr_30d=22.0,
    liquidity=1_000_000_000
)

# Evaluate
score = strategy.evaluate_pool(pool)
print(f"Score: {score}/100")

# Check entry
should_enter = strategy.should_enter(pool, current_positions=[])
print(f"Should enter: {should_enter}")

# Calculate range
tick_lower, tick_upper = strategy.calculate_position_range(pool, "moderate")
print(f"Range: {tick_lower} to {tick_upper}")
```

## 🚀 Next Steps

- **Custom Strategies**: Extend `LiquidityStrategy` base class
- **Backtesting**: Test strategies on historical data
- **Parameter Tuning**: Adjust thresholds in config
- **Multi-Strategy**: Combine strategies with weighted scoring

---

**Remember**: All strategies are deterministic and explainable. The agent shows its reasoning for every decision!

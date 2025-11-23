# Liquidity Strategy - Quick Reference

## 🎯 Как бот выбирает пулы для входа

### Алгоритм (не LLM угадывание!)

```
1. Получить данные всех пулов (TVL, volume, APR, fees)
   ↓
2. Оценить каждый пул по формуле (0-100 баллов)
   ↓
3. Фильтровать по минимальным требованиям
   ↓
4. Проверить IL риск
   ↓
5. Если score ≥ порог → ВХОДИТЬ
```

## 📊 Scoring Formula (Yield Strategy)

```python
# APR (40 баллов макс)
APR между 15-50% = оптимально
score_apr = 40 * (apr / 50)

# Volume/TVL (30 баллов макс)
Дневной оборот ≥100% = отлично
score_volume = 30 * (volume_24h / tvl)

# TVL Liquidity (20 баллов макс)
TVL ≥ $10M = максимум
TVL ≥ $1M = минимум

# Fee Tier (10 баллов макс)
Stablecoins: 1-5 bps ✅
Volatile: 30-100 bps ✅
```

## ✅ Критерии входа

### Yield Maximization Strategy
```python
min_tvl = $1,000,000
min_volume = $500,000 / 24h
min_apr = 10%
max_il_risk = 20%
min_score = 60/100

if (tvl ≥ min_tvl AND
    volume ≥ min_volume AND
    apr ≥ min_apr AND
    il_risk ≤ max_il AND
    score ≥ 60):
    ВХОДИТЬ ✅
```

### Balanced Strategy
```python
min_tvl = $5,000,000  # Выше!
max_volatility = 10% / 24h
min_score = 70/100  # Строже!

Только крупные стабильные пулы
```

## 💰 Position Sizing

```python
base_amount = $1,000 + (score/100) * $9,000

# Ограничения:
max_by_pool = tvl * 0.01  # Не более 1% от пула
max_total = $10,000

position_size = min(base_amount, max_by_pool, max_total)
```

**Пример:**
- Score 80/100 → base = $1,000 + 0.8 * $9,000 = $8,200
- Pool TVL $50M → max = $500,000
- Final position: $8,200 ✅

## 📐 Range Calculation (Uniswap V3)

### Stablecoins (USDC/USDT)
```python
conservative: ±2.0%
moderate:     ±1.5%
aggressive:   ±0.5%
```

### Volatile Pairs (ETH/USDC)
```python
base_range = 15%
volatility_adjustment = abs(price_change_24h)

final_range = base_range + volatility_adjustment

conservative: ±25%
moderate:     ±15%
aggressive:   ±5%
```

## 🔄 Rebalancing Triggers

```python
if price_out_of_range:
    → Ребалансировать

if unclaimed_fees > $50:
    → Собрать fees
    → Опционально: auto-compound

if impermanent_loss > 5%:
    → Оценить выход

if better_opportunity_score > current_score + 20:
    → Мигрировать в новый пул
```

## 🎲 Пример работы

### Input
```
Pools на Arbitrum:
1. WETH/USDC: TVL $50M, Vol $75M/24h, APR 25%
2. USDC/USDT: TVL $100M, Vol $30M/24h, APR 5%
3. ARB/USDC: TVL $500K, Vol $200K/24h, APR 50%
```

### Strategy Evaluation (Yield)

**Pool 1: WETH/USDC**
```python
APR: 40 * (25/50) = 20 pts
Volume: 30 * (75/50) = 30 pts (cap)
TVL: 20 pts (>$10M)
Fee: 10 pts (0.3% optimal for volatile)
SCORE: 80/100 ✅

Checks:
✅ TVL $50M > $1M
✅ Volume $75M > $500K
✅ APR 25% > 10%
✅ IL risk ~8% < 20%

DECISION: ENTER
Position: $8,200
Range: ±15%
```

**Pool 2: USDC/USDT**
```python
APR: 40 * (5/50) = 4 pts
Volume: 30 * (30/100) = 9 pts
TVL: 20 pts
Fee: 10 pts (0.01% for stable)
SCORE: 43/100 ❌

DECISION: SKIP (score < 60)
```

**Pool 3: ARB/USDC**
```python
APR: 40 pts (50% APR)
Volume: 30 * (200K/500K) = 12 pts
TVL: 10 pts ($500K < $1M)
Fee: 10 pts
SCORE: 72/100 ⚠️

BUT:
❌ TVL $500K < $1M minimum

DECISION: SKIP (not meet criteria)
```

### Result
→ Входит только в WETH/USDC
→ Позиция $8,200
→ Range: текущая цена ±15%

## 🚀 Использование

```python
# Yield Strategy
agent = ArbitrumLiquidityAgent(strategy_type="yield")
# → Агрессивный поиск APR
# → Допускает волатильность
# → Минимум: TVL $1M, APR 10%, score 60

# Balanced Strategy
agent = ArbitrumLiquidityAgent(strategy_type="balanced")
# → Консервативный подход
# → Только стабильные пулы
# → Минимум: TVL $5M, score 70, volatility <10%
```

## 🔍 Проверяемость

Вся логика детерминирована и объяснима:

```python
from tools.liquidity_strategy import YieldMaximizationStrategy

strategy = YieldMaximizationStrategy()
score = strategy.evaluate_pool(pool)
print(f"Score: {score}/100")
# Можно проверить каждый шаг вручную!
```

---

**Ключевое отличие**: Бот НЕ просто спрашивает LLM "какой пул выбрать?".
Он использует математические формулы → фильтры → только потом LLM для финальной оценки.

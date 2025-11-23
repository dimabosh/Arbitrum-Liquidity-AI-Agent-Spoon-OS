# Arbitrum Liquidity Automation Agent

Automated liquidity management for Arbitrum DEXes using [Spoon OS](https://spoonai.io/) framework.

## Features

- **Automated Liquidity Management**: Monitor and manage liquidity positions across Arbitrum DEXes
- **Intelligent Rebalancing**: AI-powered position rebalancing with automated swaps
- **Multi-DEX Support**: Works with Uniswap V3, Camelot, SushiSwap on Arbitrum
- **Risk Assessment**: Built-in risk analysis for liquidity positions
- **Fee Collection**: Automated fee collection and compounding
- **Graph-based Workflow**: Declarative graph architecture using Spoon OS

## Architecture

This agent leverages **Spoon OS**, an agentic operating system for Web3:

- **Graph Agent Architecture**: Declarative workflow with parallel execution
- **Spoon OS EVM Tools**: Native integration with `EvmSwapTool` for token swaps
- **Multi-LLM Support**: Compatible with OpenAI, Anthropic, Gemini, DeepSeek
- **Tool System**: Custom Arbitrum-specific tools wrapping Spoon OS utilities

### Key Components

1. **ArbitrumLiquidityAgent**: Main agent coordinating liquidity operations
2. **ArbitrumPoolDataTool**: Fetch pool data from Arbitrum DEXes
3. **ArbitrumLiquidityPositionTool**: Manage Uniswap V3 NFT positions
4. **ArbitrumSwapTool**: Execute token swaps (wraps Spoon OS EvmSwapTool)
5. **ArbitrumRebalanceTool**: High-level rebalancing automation

## Installation

### Prerequisites

- Python 3.12 or higher
- Arbitrum RPC endpoint
- At least one LLM API key (OpenAI, Anthropic, etc.)

### Setup

1. **Clone the repository**

```bash
git clone https://github.com/dimabosh/spoon_os_ai_agent.git
cd spoon_os_ai_agent
```

2. **Create virtual environment**

```bash
python3 -m venv spoon-env
source spoon-env/bin/activate  # On Windows: .\spoon-env\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

Or install Spoon OS packages separately:

```bash
pip install spoon-ai-sdk spoon-toolkits
```

4. **Configure environment variables**

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
# LLM Provider (at least one required)
OPENAI_API_KEY=your-openai-api-key-here
# ANTHROPIC_API_KEY=your-anthropic-api-key-here
# GEMINI_API_KEY=your-gemini-api-key-here

# Arbitrum Configuration
ARBITRUM_RPC_URL=https://arb1.arbitrum.io/rpc
WALLET_ADDRESS=0xYourWalletAddressHere

# Transaction Signing
SIGNER_TYPE=auto
```

## Usage

### Basic Example

```python
import asyncio
from agents.arbitrum_liquidity_agent import ArbitrumLiquidityAgent

async def main():
    # Initialize agent
    agent = ArbitrumLiquidityAgent(
        llm_provider="openai",
        model_name="gpt-4-turbo-preview",
        rpc_url="https://arb1.arbitrum.io/rpc"
    )

    # Execute liquidity management query
    result = await agent.process_query(
        "Monitor my Arbitrum liquidity positions and suggest rebalancing opportunities"
    )

    # Display results
    agent.display_result(result)

if __name__ == "__main__":
    asyncio.run(main())
```

### Run the Demo

```bash
cd agents
python arbitrum_liquidity_agent.py
```

### Example Queries

- `"Monitor my liquidity positions on Arbitrum and check for rebalancing opportunities"`
- `"Analyze the top ETH/USDC pools on Arbitrum and recommend optimal LP ranges"`
- `"Check my current positions and calculate unclaimed fees"`
- `"Rebalance my position 12345 to 50/50 ratio and collect fees"`

## How It Works

### Workflow

The agent uses a declarative graph-based workflow:

```
Initialize Session
    ↓
Analyze Query (LLM)
    ↓
┌─────────────────────┬─────────────────────┐
│  Fetch Pool Data    │  Check Positions    │ (Parallel)
└─────────────────────┴─────────────────────┘
    ↓
Assess Risk (LLM)
    ↓
Generate Rebalance Plan (LLM)
    ↓
Create Execution Plan
    ↓
Execute Operations (Swaps, Rebalancing, Fee Collection)
    ↓
Finalize Report
```

### Tools in Action

**1. Pool Data Fetching**
```python
result = await pool_tool.execute(
    pool_address="0x...",
    dex="uniswap_v3"
)
# Returns: TVL, volume, fees, APR, price, liquidity
```

**2. Position Management**
```python
result = await position_tool.execute(
    action="query",  # or "add", "remove", "collect_fees"
)
# Returns: Active positions, unclaimed fees, value
```

**3. Token Swaps (Using Spoon OS EvmSwapTool)**
```python
result = await swap_tool.execute(
    from_token="WETH",
    to_token="USDC",
    amount="0.5",
    slippage=0.5,
    dex="uniswap_v3"
)
# Executes swap on Arbitrum
```

**4. Automated Rebalancing**
```python
result = await rebalance_tool.execute(
    position_id="12345",
    target_ratio={"token0": 0.5, "token1": 0.5},
    auto_compound=True
)
# Collects fees, swaps, re-adds liquidity
```

## Configuration

### Agent Configuration

Edit `config/agent_config.json` to customize:

- Supported DEXes and their contracts
- Rebalancing thresholds
- Risk parameters
- Monitoring intervals
- Auto-compound settings

### LLM Configuration

The agent supports multiple LLM providers via Spoon OS:

- **OpenAI**: GPT-4, GPT-3.5-Turbo
- **Anthropic**: Claude 3 Opus, Sonnet, Haiku
- **Google**: Gemini Pro
- **DeepSeek**: DeepSeek models
- **OpenRouter**: Multi-model access

Set `DEFAULT_LLM_PROVIDER` in `.env` or pass to agent constructor.

## Spoon OS Integration

This project leverages the following Spoon OS components:

### Graph System
```python
from spoon_ai.graph.builder import (
    DeclarativeGraphBuilder,
    GraphTemplate,
    NodeSpec,
    EdgeSpec,
    ParallelGroupSpec
)
```

### EVM Tools
```python
from spoon_toolkits.crypto.evm import EvmSwapTool
```

### LLM Management
```python
from spoon_ai.llm.manager import get_llm_manager
from spoon_ai.schema import Message
```

## Security Considerations

⚠️ **Important Security Notes**:

1. **Private Keys**: Never commit private keys to git. Use environment variables.
2. **API Keys**: Keep your LLM API keys secure in `.env` file.
3. **RPC Endpoints**: Use trusted RPC providers for production.
4. **Transaction Signing**: Review all transactions before signing.
5. **Slippage**: Set appropriate slippage to avoid MEV attacks.
6. **Simulation**: Test with small amounts first.

## Development

### Project Structure

```
spoon_os_ai_agent/
├── agents/
│   └── arbitrum_liquidity_agent.py  # Main agent implementation
├── tools/
│   └── arbitrum_tools.py            # Custom Arbitrum tools
├── config/
│   └── agent_config.json            # Agent configuration
├── examples/
│   └── (future examples)
├── .env.example                     # Environment template
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

### Adding New Features

1. **New Tools**: Add to `tools/arbitrum_tools.py`
2. **New Nodes**: Add methods to `ArbitrumLiquidityAgent`
3. **New Workflows**: Modify `_build_graph()` method
4. **New DEXes**: Update `config/agent_config.json`

## Roadmap

- [ ] Integration with The Graph Protocol for real pool data
- [ ] Support for additional Arbitrum DEXes (Trader Joe, Ramses)
- [ ] Advanced strategies (range orders, auto-migration)
- [ ] Multi-position portfolio optimization
- [ ] Real-time price oracles integration
- [ ] Telegram/Discord bot interface
- [ ] Backtesting framework
- [ ] Gas optimization strategies

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Resources

- **Spoon OS Documentation**: https://xspoonai.github.io/docs/
- **Spoon OS GitHub**: https://github.com/XSpoonAi/spoon-core
- **Arbitrum Documentation**: https://docs.arbitrum.io/
- **Uniswap V3**: https://docs.uniswap.org/

## License

MIT License - see LICENSE file for details

## Disclaimer

This software is for educational and research purposes. Use at your own risk. The authors are not responsible for any financial losses incurred through the use of this software. Always review transactions before signing and never invest more than you can afford to lose.

## Support

For issues and questions:
- GitHub Issues: https://github.com/dimabosh/spoon_os_ai_agent/issues
- Spoon OS Community: https://spoonai.io/

---

Built with [Spoon OS](https://spoonai.io/) - The Agentic OS for Web3

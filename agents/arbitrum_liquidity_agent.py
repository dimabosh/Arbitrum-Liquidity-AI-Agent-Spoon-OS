"""Arbitrum Liquidity Automation Agent

This agent automates liquidity management on Arbitrum network using SpoonOS framework.
It monitors liquidity pools, rebalances positions, and executes optimal liquidity provision strategies.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv
from spoon_ai.agents import SpoonReactAI
from spoon_ai.chat import ChatBot
from spoon_ai.graph import END
from spoon_ai.graph.builder import (
    DeclarativeGraphBuilder,
    EdgeSpec,
    GraphTemplate,
    NodeSpec,
    ParallelGroupSpec,
)
from spoon_ai.graph.config import GraphConfig, ParallelGroupConfig
from spoon_ai.llm.manager import get_llm_manager
from spoon_ai.schema import Message
from spoon_toolkits.crypto.evm import EvmSwapTool

# Import custom Arbitrum tools
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.arbitrum_tools import (
    ArbitrumPoolDataTool,
    ArbitrumLiquidityPositionTool,
    ArbitrumSwapTool,
    ArbitrumRebalanceTool,
)

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# State schema for liquidity automation
class LiquidityAgentState(TypedDict, total=False):
    user_query: str
    session_id: str
    target_pools: List[str]
    current_positions: Dict[str, Any]
    pool_analytics: Dict[str, Any]
    rebalance_recommendations: List[Dict[str, Any]]
    swap_operations: List[Dict[str, Any]]  # New: track swap operations
    execution_plan: Optional[Dict[str, Any]]
    execution_status: str
    execution_results: List[Dict[str, Any]]
    risk_assessment: Dict[str, Any]
    execution_log: List[str]
    final_output: str
    processing_time: float


class ArbitrumLiquidityAgent:
    """Main agent for Arbitrum liquidity automation."""

    def __init__(self, llm_provider: str = "openai", model_name: str = "gpt-4.1", rpc_url: Optional[str] = None):
        """Initialize the Arbitrum Liquidity Agent.

        Args:
            llm_provider: LLM provider to use (openai, anthropic, gemini, etc.)
            model_name: Specific model to use for reasoning
            rpc_url: Arbitrum RPC URL for on-chain operations
        """
        self.llm = get_llm_manager()
        self.llm_provider = llm_provider
        self.model_name = model_name

        # Initialize Arbitrum-specific tools
        self.pool_tool = ArbitrumPoolDataTool(rpc_url=rpc_url)
        self.position_tool = ArbitrumLiquidityPositionTool(rpc_url=rpc_url)
        self.swap_tool = ArbitrumSwapTool(rpc_url=rpc_url)
        self.rebalance_tool = ArbitrumRebalanceTool(rpc_url=rpc_url)

        self.graph = self._build_graph()

    # Node implementations

    async def _initialize_session(
        self, state: LiquidityAgentState, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Initialize a new liquidity management session."""
        session_id = f"arb_liq_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        log = ["Session initialized for Arbitrum liquidity automation"]

        return {
            "session_id": session_id,
            "execution_log": log,
            "execution_status": "INITIALIZED",
            "current_positions": {},
            "pool_analytics": {},
            "execution_results": [],
        }

    async def _analyze_query(
        self, state: LiquidityAgentState, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Analyze user query to extract liquidity management intent."""
        query = state.get("user_query", "")

        prompt = f"""
        Analyze the following liquidity management request and extract key parameters.

        Query: {query}

        Extract and return JSON with:
        - target_pools: list of pool addresses or identifiers
        - action_type: "monitor", "add_liquidity", "remove_liquidity", "rebalance", or "optimize"
        - parameters: any specific parameters (amounts, ranges, etc.)
        - risk_tolerance: "conservative", "moderate", or "aggressive"

        Respond with valid JSON only.
        """

        response = await self.llm.chat([Message(role="user", content=prompt)])

        try:
            analysis = json.loads(response.content)
        except json.JSONDecodeError:
            analysis = {
                "action_type": "monitor",
                "target_pools": [],
                "parameters": {},
                "risk_tolerance": "moderate"
            }

        log = list(state.get("execution_log", []))
        log.append(f"Query analyzed: action={analysis.get('action_type')}")

        return {
            "target_pools": analysis.get("target_pools", []),
            "execution_log": log,
        }

    async def _fetch_pool_data(
        self, state: LiquidityAgentState, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Fetch current data for target liquidity pools on Arbitrum."""
        target_pools = state.get("target_pools", [])
        log = list(state.get("execution_log", []))

        # Use Arbitrum Pool Data Tool
        pool_data = {}
        for pool in target_pools:
            result = await self.pool_tool.execute(pool_address=pool)
            if not result.error:
                pool_data[pool] = result.output
            else:
                logger.warning(f"Failed to fetch data for pool {pool}: {result.error}")
                pool_data[pool] = {"error": result.error}

        log.append(f"Fetched data for {len(target_pools)} pools using ArbitrumPoolDataTool")

        return {
            "pool_analytics": pool_data,
            "execution_log": log,
        }

    async def _check_positions(
        self, state: LiquidityAgentState, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Check current liquidity positions using ArbitrumLiquidityPositionTool."""
        log = list(state.get("execution_log", []))

        # Use Arbitrum Position Tool to query positions
        result = await self.position_tool.execute(action="query")

        if not result.error:
            positions = {
                "active_positions": result.output,
                "total_value_usd": sum(p.get("current_value_usd", 0) for p in result.output),
                "unclaimed_fees": sum(p.get("unclaimed_fees_usd", 0) for p in result.output),
            }
            log.append(f"Positions checked: {len(result.output)} active positions found")
        else:
            logger.warning(f"Failed to check positions: {result.error}")
            positions = {
                "active_positions": [],
                "total_value_usd": 0,
                "unclaimed_fees": 0,
                "error": result.error
            }
            log.append("Position check failed")

        return {
            "current_positions": positions,
            "execution_log": log,
        }

    async def _assess_risk(
        self, state: LiquidityAgentState, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Assess risks associated with liquidity positions."""
        pool_analytics = state.get("pool_analytics", {})
        positions = state.get("current_positions", {})

        prompt = f"""
        Assess the risks for the following liquidity positions on Arbitrum.

        Pool Analytics: {json.dumps(pool_analytics, indent=2)[:2000]}
        Current Positions: {json.dumps(positions, indent=2)[:2000]}

        Provide a risk assessment including:
        - Impermanent loss risk (low/medium/high)
        - Pool concentration risk
        - Smart contract risk
        - Market volatility risk
        - Recommendations

        Format as JSON with keys: impermanent_loss_risk, concentration_risk,
        contract_risk, volatility_risk, overall_risk_score (0-100), recommendations
        """

        response = await self.llm.chat([Message(role="user", content=prompt)])

        try:
            risk_assessment = json.loads(response.content)
        except json.JSONDecodeError:
            risk_assessment = {
                "overall_risk_score": 50,
                "recommendations": ["Unable to assess risks properly"]
            }

        log = list(state.get("execution_log", []))
        log.append(f"Risk assessed: score={risk_assessment.get('overall_risk_score')}")

        return {
            "risk_assessment": risk_assessment,
            "execution_log": log,
        }

    async def _generate_rebalance_plan(
        self, state: LiquidityAgentState, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate optimal rebalancing recommendations."""
        pool_analytics = state.get("pool_analytics", {})
        positions = state.get("current_positions", {})
        risk_assessment = state.get("risk_assessment", {})

        prompt = f"""
        Generate optimal liquidity rebalancing recommendations for Arbitrum.

        Pool Analytics: {json.dumps(pool_analytics, indent=2)[:1500]}
        Current Positions: {json.dumps(positions, indent=2)[:1500]}
        Risk Assessment: {json.dumps(risk_assessment, indent=2)[:1500]}

        Provide specific rebalancing actions:
        - Which positions to adjust
        - Target price ranges for concentrated liquidity
        - Recommended allocation changes
        - Fee collection timing

        Format as JSON array of recommendations with: pool, action, details, priority
        """

        response = await self.llm.chat([Message(role="user", content=prompt)])

        try:
            recommendations = json.loads(response.content)
            if not isinstance(recommendations, list):
                recommendations = [recommendations]
        except json.JSONDecodeError:
            recommendations = []

        log = list(state.get("execution_log", []))
        log.append(f"Generated {len(recommendations)} rebalancing recommendations")

        return {
            "rebalance_recommendations": recommendations,
            "execution_log": log,
        }

    async def _create_execution_plan(
        self, state: LiquidityAgentState, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create detailed execution plan for liquidity operations."""
        recommendations = state.get("rebalance_recommendations", [])
        risk = state.get("risk_assessment", {})

        # Create execution plan based on recommendations
        plan = {
            "steps": [],
            "estimated_gas": 0,
            "estimated_time": "5-10 minutes",
            "requires_approval": True,
        }

        for idx, rec in enumerate(recommendations, 1):
            plan["steps"].append({
                "step": idx,
                "action": rec.get("action", "unknown"),
                "pool": rec.get("pool", "unknown"),
                "details": rec.get("details", {}),
                "priority": rec.get("priority", "medium"),
            })

        log = list(state.get("execution_log", []))
        log.append(f"Execution plan created with {len(plan['steps'])} steps")

        return {
            "execution_plan": plan,
            "execution_log": log,
        }

    async def _execute_operations(
        self, state: LiquidityAgentState, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute liquidity operations on Arbitrum using Spoon OS tools."""
        plan = state.get("execution_plan", {})
        log = list(state.get("execution_log", []))
        results = []
        swap_operations = []

        for step in plan.get("steps", []):
            action = step.get("action", "unknown")
            details = step.get("details", {})

            try:
                if action == "swap":
                    # Execute swap using ArbitrumSwapTool (wraps Spoon OS EvmSwapTool)
                    swap_result = await self.swap_tool.execute(
                        from_token=details.get("from_token"),
                        to_token=details.get("to_token"),
                        amount=details.get("amount"),
                        slippage=details.get("slippage", 0.5),
                        dex=details.get("dex", "uniswap_v3"),
                        signer_type="auto"
                    )

                    swap_operations.append({
                        "step": step.get("step"),
                        "from_token": details.get("from_token"),
                        "to_token": details.get("to_token"),
                        "amount": details.get("amount"),
                        "result": swap_result.output if not swap_result.error else None,
                        "error": swap_result.error
                    })

                    results.append({
                        "step": step.get("step"),
                        "action": action,
                        "status": "SUCCESS" if not swap_result.error else "FAILED",
                        "message": f"Swap {details.get('from_token')} -> {details.get('to_token')}",
                        "tx_hash": swap_result.output.get("tx_hash") if not swap_result.error else None,
                        "error": swap_result.error
                    })

                elif action == "rebalance":
                    # Execute full rebalancing using ArbitrumRebalanceTool
                    position_id = details.get("position_id")
                    target_ratio = details.get("target_ratio")

                    rebalance_result = await self.rebalance_tool.execute(
                        position_id=position_id,
                        target_ratio=target_ratio,
                        auto_compound=details.get("auto_compound", False)
                    )

                    results.append({
                        "step": step.get("step"),
                        "action": action,
                        "status": "SUCCESS" if not rebalance_result.error else "FAILED",
                        "message": f"Rebalanced position {position_id}",
                        "result": rebalance_result.output if not rebalance_result.error else None,
                        "error": rebalance_result.error
                    })

                elif action == "collect_fees":
                    # Collect fees using position tool
                    position_id = details.get("position_id")

                    fee_result = await self.position_tool.execute(
                        action="collect_fees",
                        position_id=position_id
                    )

                    results.append({
                        "step": step.get("step"),
                        "action": action,
                        "status": "SUCCESS" if not fee_result.error else "FAILED",
                        "message": f"Collected fees from position {position_id}",
                        "fees_usd": fee_result.output.get("fees_usd") if not fee_result.error else 0,
                        "error": fee_result.error
                    })

                else:
                    # Unknown action - log only
                    results.append({
                        "step": step.get("step"),
                        "action": action,
                        "status": "SKIPPED",
                        "message": f"Unknown action: {action}",
                        "tx_hash": None,
                    })

            except Exception as e:
                logger.error(f"Error executing step {step.get('step')}: {e}")
                results.append({
                    "step": step.get("step"),
                    "action": action,
                    "status": "ERROR",
                    "message": str(e),
                    "error": str(e)
                })

        # Determine overall status
        if not results:
            status = "NO_ACTIONS"
        elif any(r.get("status") == "FAILED" for r in results):
            status = "PARTIALLY_COMPLETED"
        elif all(r.get("status") == "SUCCESS" for r in results):
            status = "COMPLETED"
        else:
            status = "COMPLETED_WITH_WARNINGS"

        log.append(f"Execution completed: {status} ({len(results)} operations)")
        if swap_operations:
            log.append(f"Swaps executed: {len(swap_operations)}")

        return {
            "execution_results": results,
            "swap_operations": swap_operations,
            "execution_status": status,
            "execution_log": log,
        }

    async def _finalize_report(
        self, state: LiquidityAgentState, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate final report of liquidity management session."""
        query = state.get("user_query", "")
        positions = state.get("current_positions", {})
        risk = state.get("risk_assessment", {})
        recommendations = state.get("rebalance_recommendations", [])
        plan = state.get("execution_plan", {})
        results = state.get("execution_results", [])
        status = state.get("execution_status", "UNKNOWN")

        report_parts = [
            "=== Arbitrum Liquidity Management Report ===\n",
            f"Query: {query}\n",
            f"Status: {status}\n",
            f"\nRisk Score: {risk.get('overall_risk_score', 'N/A')}/100",
            f"\nRecommendations: {len(recommendations)}",
            f"\nExecution Steps: {len(plan.get('steps', []))}",
            f"\nResults: {len(results)}",
        ]

        if recommendations:
            report_parts.append("\n\nTop Recommendations:")
            for rec in recommendations[:3]:
                report_parts.append(f"  - {rec.get('action')}: {rec.get('pool')}")

        if results:
            report_parts.append("\n\nExecution Results:")
            for res in results[:5]:
                report_parts.append(f"  - Step {res.get('step')}: {res.get('status')}")

        final_output = "\n".join(report_parts)

        log = list(state.get("execution_log", []))
        log.append("Final report generated")

        return {
            "final_output": final_output,
            "execution_log": log,
        }

    def _build_graph(self):
        """Build the liquidity management workflow graph."""
        template = GraphTemplate(
            entry_point="initialize_session",
            nodes=[
                NodeSpec("initialize_session", self._initialize_session),
                NodeSpec("analyze_query", self._analyze_query),
                NodeSpec("fetch_pool_data", self._fetch_pool_data),
                NodeSpec("check_positions", self._check_positions),
                NodeSpec("assess_risk", self._assess_risk),
                NodeSpec("generate_rebalance", self._generate_rebalance_plan),
                NodeSpec("create_execution_plan", self._create_execution_plan),
                NodeSpec("execute_operations", self._execute_operations),
                NodeSpec("finalize_report", self._finalize_report),
            ],
            edges=[
                EdgeSpec("initialize_session", "analyze_query"),
                EdgeSpec("analyze_query", "fetch_pool_data"),
                EdgeSpec("fetch_pool_data", "check_positions"),
                EdgeSpec("check_positions", "assess_risk"),
                EdgeSpec("assess_risk", "generate_rebalance"),
                EdgeSpec("generate_rebalance", "create_execution_plan"),
                EdgeSpec("create_execution_plan", "execute_operations"),
                EdgeSpec("execute_operations", "finalize_report"),
                EdgeSpec("finalize_report", END),
            ],
            parallel_groups=[
                ParallelGroupSpec(
                    name="data_collection",
                    nodes=("fetch_pool_data", "check_positions"),
                    config=ParallelGroupConfig(
                        join_strategy="all",
                        error_strategy="collect_errors"
                    ),
                ),
            ],
            config=GraphConfig(max_iterations=50),
        )

        builder = DeclarativeGraphBuilder(LiquidityAgentState)
        return builder.build(template)

    async def process_query(self, user_query: str) -> Dict[str, Any]:
        """Process a liquidity management query.

        Args:
            user_query: Natural language query for liquidity management

        Returns:
            Dictionary containing execution results and report
        """
        state: LiquidityAgentState = {
            "user_query": user_query,
            "execution_log": [],
            "target_pools": [],
            "current_positions": {},
            "pool_analytics": {},
            "rebalance_recommendations": [],
            "execution_plan": None,
            "execution_status": "PENDING",
            "execution_results": [],
            "risk_assessment": {},
        }

        compiled = self.graph.compile()
        start = datetime.now(timezone.utc)
        result = await compiled.invoke(state, {"max_iterations": 50})
        result["processing_time"] = (datetime.now(timezone.utc) - start).total_seconds()

        return result

    def display_result(self, result: Dict[str, Any]) -> None:
        """Display execution results in a formatted way."""
        print("\n" + "=" * 80)
        print("ARBITRUM LIQUIDITY AUTOMATION AGENT")
        print("=" * 80)
        print(f"Query: {result.get('user_query', 'N/A')}")
        print(f"Processing Time: {result.get('processing_time', 0):.2f}s")
        print("-" * 80)

        print("\nExecution Log:")
        for idx, log in enumerate(result.get("execution_log", []), 1):
            print(f"  {idx}. {log}")

        print("\n" + result.get("final_output", "(no output)"))
        print("=" * 80 + "\n")


async def main():
    """Example usage of the Arbitrum Liquidity Agent."""
    agent = ArbitrumLiquidityAgent(llm_provider="openai", model_name="gpt-4.1")

    queries = [
        "Monitor my liquidity positions on Arbitrum and check for rebalancing opportunities",
        "Analyze the top ETH/USDC pools on Arbitrum and recommend optimal LP ranges",
        "Check my current positions and calculate unclaimed fees",
    ]

    for query in queries:
        print(f"\nProcessing: {query}")
        result = await agent.process_query(query)
        agent.display_result(result)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())

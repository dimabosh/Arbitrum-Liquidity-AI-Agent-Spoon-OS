#!/usr/bin/env python3
"""Main entry point for Arbitrum Liquidity Agent on Railway.

This script starts a simple web server that can execute the liquidity agent
and provides API endpoints for monitoring and control.
"""

import asyncio
import logging
import os
from typing import Dict, Any

from aiohttp import web
from dotenv import load_dotenv

from agents.arbitrum_liquidity_agent import ArbitrumLiquidityAgent

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Initialize the agent
agent = None


async def init_agent():
    """Initialize the Arbitrum Liquidity Agent."""
    global agent

    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    model_name = os.getenv("MODEL_NAME", "gpt-4-turbo-preview")
    rpc_url = os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")
    strategy_type = os.getenv("STRATEGY_TYPE", "yield")

    logger.info(f"Initializing agent with {llm_provider}/{model_name}, strategy: {strategy_type}")

    agent = ArbitrumLiquidityAgent(
        llm_provider=llm_provider,
        model_name=model_name,
        rpc_url=rpc_url,
        strategy_type=strategy_type
    )

    logger.info("Agent initialized successfully")


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({
        "status": "healthy",
        "service": "arbitrum-liquidity-agent",
        "agent_initialized": agent is not None
    })


async def process_query(request: web.Request) -> web.Response:
    """Process a liquidity management query."""
    try:
        data = await request.json()
        query = data.get("query")

        if not query:
            return web.json_response(
                {"error": "Query is required"},
                status=400
            )

        if not agent:
            return web.json_response(
                {"error": "Agent not initialized"},
                status=503
            )

        logger.info(f"Processing query: {query}")

        result = await agent.process_query(query)

        return web.json_response({
            "success": True,
            "result": result
        })

    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def get_info(request: web.Request) -> web.Response:
    """Get agent information."""
    return web.json_response({
        "name": "Arbitrum Liquidity Automation Agent",
        "version": "1.0.0",
        "strategy": os.getenv("STRATEGY_TYPE", "yield"),
        "rpc_url": os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc"),
        "wallet_address": os.getenv("WALLET_ADDRESS", "not_configured")
    })


async def on_startup(app: web.Application):
    """Initialize on app startup."""
    logger.info("Starting Arbitrum Liquidity Agent...")
    await init_agent()


async def on_cleanup(app: web.Application):
    """Cleanup on app shutdown."""
    logger.info("Shutting down Arbitrum Liquidity Agent...")


def create_app() -> web.Application:
    """Create and configure the web application."""
    app = web.Application()

    # Add routes
    app.router.add_get("/health", health_check)
    app.router.add_get("/info", get_info)
    app.router.add_post("/query", process_query)

    # Add startup/cleanup handlers
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    return app


def main():
    """Main entry point."""
    port = int(os.getenv("PORT", "8080"))

    logger.info(f"Starting server on port {port}")

    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

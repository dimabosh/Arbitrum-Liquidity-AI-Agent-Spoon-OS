#!/usr/bin/env python3
"""Main entry point for Arbitrum Liquidity Agent Web Application.

This script starts a web server with:
- Frontend UI for wallet connection and agent control
- REST API for agent management
- WebSocket for real-time updates
- OpenRouter API integration for multiple LLM providers
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Set

from aiohttp import web, WSMsgType
import aiohttp_cors
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

# Global state
agents: Dict[str, ArbitrumLiquidityAgent] = {}  # wallet_address -> agent
websockets: Dict[str, Set[web.WebSocketResponse]] = {}  # wallet_address -> set of websockets


class OpenRouterLLM:
    """OpenRouter API integration for multiple LLM providers."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"

    async def chat(self, messages: list) -> dict:
        """Send chat request to OpenRouter API."""
        import aiohttp

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("NEXT_PUBLIC_SITE_URL", "http://localhost:8080"),
            "X-Title": "Arbitrum Liquidity Agent"
        }

        payload = {
            "model": self.model,
            "messages": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenRouter API error: {error_text}")

                result = await response.json()
                return result["choices"][0]["message"]


async def broadcast_to_websockets(wallet_address: str, message: dict):
    """Broadcast message to all websockets for a wallet."""
    if wallet_address not in websockets:
        return

    dead_sockets = set()
    for ws in websockets[wallet_address]:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.error(f"Error sending to websocket: {e}")
            dead_sockets.add(ws)

    # Remove dead sockets
    websockets[wallet_address] -= dead_sockets


# ===== API Endpoints =====

async def serve_frontend(request: web.Request) -> web.Response:
    """Serve the frontend HTML."""
    frontend_path = Path(__file__).parent / "frontend" / "templates" / "index.html"
    if not frontend_path.exists():
        return web.Response(text="Frontend not found", status=404)

    with open(frontend_path, 'r') as f:
        html = f.read()

    return web.Response(text=html, content_type='text/html')


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({
        "status": "healthy",
        "service": "arbitrum-liquidity-agent",
        "active_agents": len(agents),
        "websocket_connections": sum(len(sockets) for sockets in websockets.values())
    })


async def start_agent(request: web.Request) -> web.Response:
    """Start an agent for a wallet."""
    try:
        data = await request.json()

        wallet_address = data.get("wallet_address")
        model = data.get("model", "anthropic/claude-3.5-sonnet")
        strategy = data.get("strategy", "yield")
        rpc_url = data.get("rpc_url", "https://arb1.arbitrum.io/rpc")
        openrouter_key = data.get("openrouter_key")

        if not wallet_address:
            return web.json_response(
                {"error": "wallet_address is required"},
                status=400
            )

        if not openrouter_key:
            return web.json_response(
                {"error": "openrouter_key is required"},
                status=400
            )

        # Check if agent already running
        if wallet_address in agents:
            return web.json_response(
                {"error": "Agent already running for this wallet"},
                status=400
            )

        logger.info(f"Starting agent for wallet {wallet_address}, model: {model}, strategy: {strategy}")

        # Set environment variable for OpenRouter
        os.environ["OPENROUTER_API_KEY"] = openrouter_key
        os.environ["WALLET_ADDRESS"] = wallet_address

        # Create agent with OpenRouter model
        agent = ArbitrumLiquidityAgent(
            llm_provider="openrouter",  # Will be handled by custom integration
            model_name=model,
            rpc_url=rpc_url,
            strategy_type=strategy
        )

        agents[wallet_address] = agent

        # Broadcast status update
        await broadcast_to_websockets(wallet_address, {
            "type": "status_update",
            "payload": {
                "status": "Agent started",
                "state": "active"
            }
        })

        await broadcast_to_websockets(wallet_address, {
            "type": "log",
            "payload": {
                "message": f"Agent started with {model}",
                "level": "success"
            }
        })

        return web.json_response({
            "success": True,
            "message": "Agent started successfully",
            "config": {
                "model": model,
                "strategy": strategy,
                "wallet": wallet_address
            }
        })

    except Exception as e:
        logger.error(f"Error starting agent: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def stop_agent(request: web.Request) -> web.Response:
    """Stop an agent for a wallet."""
    try:
        data = await request.json()
        wallet_address = data.get("wallet_address")

        if not wallet_address:
            return web.json_response(
                {"error": "wallet_address is required"},
                status=400
            )

        if wallet_address not in agents:
            return web.json_response(
                {"error": "No agent running for this wallet"},
                status=404
            )

        logger.info(f"Stopping agent for wallet {wallet_address}")

        # Remove agent
        del agents[wallet_address]

        # Broadcast status update
        await broadcast_to_websockets(wallet_address, {
            "type": "status_update",
            "payload": {
                "status": "Agent stopped",
                "state": "inactive"
            }
        })

        return web.json_response({
            "success": True,
            "message": "Agent stopped successfully"
        })

    except Exception as e:
        logger.error(f"Error stopping agent: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def get_positions(request: web.Request) -> web.Response:
    """Get liquidity positions for a wallet."""
    try:
        wallet_address = request.match_info.get("wallet_address")

        if not wallet_address or wallet_address not in agents:
            return web.json_response({
                "positions": [],
                "message": "No agent running"
            })

        agent = agents[wallet_address]

        # Mock positions for now - implement actual position fetching
        positions = [
            {
                "position_id": "12345",
                "token0": "WETH",
                "token1": "USDC",
                "dex": "Uniswap V3",
                "current_value_usd": 10000.00,
                "unclaimed_fees_usd": 125.50,
                "in_range": True
            }
        ]

        return web.json_response({
            "success": True,
            "positions": positions
        })

    except Exception as e:
        logger.error(f"Error getting positions: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def get_recommendations(request: web.Request) -> web.Response:
    """Get AI recommendations for a wallet."""
    try:
        wallet_address = request.match_info.get("wallet_address")

        if not wallet_address or wallet_address not in agents:
            return web.json_response({
                "recommendations": [],
                "message": "No agent running"
            })

        agent = agents[wallet_address]

        # Execute query to get recommendations
        result = await agent.process_query(
            "Analyze current market conditions and recommend top liquidity opportunities"
        )

        recommendations = result.get("rebalance_recommendations", [])

        return web.json_response({
            "success": True,
            "recommendations": recommendations
        })

    except Exception as e:
        logger.error(f"Error getting recommendations: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler for real-time updates."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    wallet_address = request.match_info.get("wallet_address")

    if not wallet_address:
        await ws.close()
        return ws

    # Add to websockets set
    if wallet_address not in websockets:
        websockets[wallet_address] = set()
    websockets[wallet_address].add(ws)

    logger.info(f"WebSocket connected for wallet {wallet_address}")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    # Handle incoming WebSocket messages if needed
                    logger.info(f"WebSocket message from {wallet_address}: {data}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from websocket: {msg.data}")

            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")

    finally:
        # Remove from websockets set
        if wallet_address in websockets:
            websockets[wallet_address].discard(ws)
            if not websockets[wallet_address]:
                del websockets[wallet_address]

        logger.info(f"WebSocket disconnected for wallet {wallet_address}")

    return ws


# ===== Application Setup =====

def create_app() -> web.Application:
    """Create and configure the web application."""
    app = web.Application()

    # Setup CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })

    # Static files
    frontend_dir = Path(__file__).parent / "frontend"
    if frontend_dir.exists():
        app.router.add_static('/static', frontend_dir / 'static')

    # Routes
    routes = [
        web.get("/", serve_frontend),
        web.get("/health", health_check),
        web.post("/api/agent/start", start_agent),
        web.post("/api/agent/stop", stop_agent),
        web.get("/api/positions/{wallet_address}", get_positions),
        web.get("/api/recommendations/{wallet_address}", get_recommendations),
        web.get("/ws/agent/{wallet_address}", websocket_handler),
    ]

    for route in routes:
        cors.add(app.router.add_route(route.method, route.path, route.handler))

    return app


def main():
    """Main entry point."""
    port = int(os.getenv("PORT", "8080"))

    logger.info(f"Starting Arbitrum Liquidity Agent on port {port}")
    logger.info(f"Access the UI at: http://localhost:{port}")

    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

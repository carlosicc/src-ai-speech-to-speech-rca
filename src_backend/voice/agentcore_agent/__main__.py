"""Entry point for AgentCore Runtime container."""

import logging
import os

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "agent:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
    )

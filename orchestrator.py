

import logging
import sys
import os
import json
import httpx
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True, 
    stream=sys.stdout
)

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset 
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

# Robust import for StdioTransport across different FastMCP versions
try:
    from fastmcp import StdioTransport
except ImportError:
    from fastmcp.client.transports import StdioTransport

from schemas import OrchestratorResponse
from prompts import AGENT_PROMPT

load_dotenv()

async def log_request(request: httpx.Request):
    print(f"\n\n==================================================")
    print(f" [ORCHESTRATOR REQUEST] ---> {request.method} {request.url}")
    sys.stdout.flush()

async def log_response(response: httpx.Response):
    await response.aread() 
    print(f"\n==================================================")
    print(f" [ORCHESTRATOR RESPONSE] <--- {response.status_code} {response.url}")
    sys.stdout.flush()

debug_client = httpx.AsyncClient(
    timeout=600.0,
    event_hooks={"request": [log_request], "response": [log_response]}
)

# =====================================================================
# 1. CONFIGURE ORCHESTRATOR MODEL
# =====================================================================


orchestrator_model = OpenAIChatModel(
    os.getenv("MODEL_ID_UNI_GREIFSWALD"),
    provider=OpenAIProvider(
        base_url= os.getenv("OPENAI_API_BASE_UNI_GREIFSWALD"),
        api_key=os.getenv("OPENAI_API_KEY_UNI_GREIFSWALD"), 
        http_client=debug_client
    ),
    profile=ModelProfile(
        default_structured_output_mode='tool',
        supports_json_schema_output=False,
    ),
)

settings = ModelSettings(
    extra_body=json.loads(os.getenv("LITELLM_EXTRA_BODY", "{}"))
)


# =====================================================================
# 2. DYNAMIC EXECUTION WRAPPER (Fixes Streamlit Connection Timeouts)
# =====================================================================
async def execute_agent_prompt(user_prompt: str):
    """
    Creates a fresh subprocess connection and Agent instance for every run.
    This prevents "closed pipe" timeouts when Streamlit reruns multiple times.
    """
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(BASE_DIR, "mcp_server.py")
    
    # Explicitly define StdioTransport to prevent fastmcp inference failures on Windows
    transport = StdioTransport(
        command=sys.executable,
        args=[script_path],
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    
    toolset = MCPToolset(transport, init_timeout=30.0, read_timeout=900.0)  # Add this

    # Initialize a fresh agent
    orchestrator_agent = Agent(
        orchestrator_model,
        model_settings=settings,
        system_prompt=AGENT_PROMPT,
        output_type=OrchestratorResponse,  
        toolsets=[toolset],
        retries=3 
    )

    print(" AI Orchestrator: Spawning Fresh MCP Connection...")
    
    # Execute with context manager to safely open and cleanly close the subprocess
    async with orchestrator_agent:
        result = await orchestrator_agent.run(
            user_prompt,
            usage_limits=UsageLimits(request_limit=60) 
        )
        return result
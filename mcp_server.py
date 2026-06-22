import sys
import os

_real_stdout = sys.stdout
sys.stdout = sys.stderr

os.environ["FASTMCP_LOG_LEVEL"] = "WARNING"

from contextlib import redirect_stdout
import logging

# Configure standard logging to output Pydantic AI activities to the console
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

import asyncio
import json
import os
from typing import Any, Dict
from fastmcp import FastMCP
import uuid
import requests
from bs4 import BeautifulSoup
import mlflow
import pickle
import pdfplumber
from dotenv import load_dotenv

from jobspy import scrape_jobs

from playwright.sync_api import sync_playwright
#from tavily import TavilyClient

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.settings import ModelSettings
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.usage import UsageLimits  
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from prompts import (
    CV_AGENT_PROMPT,
    JD_AGENT_PROMPT,
    MATCHER_AGENT_PROMPT,
    CV_PROMPT,
    JOB_DESCRIPTION_PROMPT,
    MATCHER_PROMPT
)

from schemas import (
    SCORING_HIERARCHY,
    CVExtractionOutput,
    JDExtractionOutput,
    MatchInput,
    MatchOutput,
    JDRawDataInput,
    CVRawDataInput,
    ReferenceHandle,
)
import httpx 

# Initialize the FastMCP server
mcp = FastMCP(
    "Automotive Roles and Domains Server",
    version="1.0.0",
)
load_dotenv()


# Detect the directory of the current script to locate the JSON files reliably
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAINS_FILE_PATH = os.path.join(BASE_DIR, "job_main_domains.json")
DETAILS_FILE_PATH = os.path.join(BASE_DIR, "jobs_details.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

from pydantic_ai.messages import ModelMessagesTypeAdapter

# =====================================================================
# TELEMETRY & TRANSPARENCY PIPELINE HELPERS
# =====================================================================

def append_subagent_trace(subagent_name: str, messages: list):
    """Appends internal sub-agent message steps to a central trace file."""
    trace_file = "subagent_trace.json"
    try:
        traces = []
        if os.path.exists(trace_file):
            with open(trace_file, "r", encoding="utf-8") as f:
                try:
                    traces = json.load(f)
                except Exception:
                    traces = []
                    
        # Safely serialize Pydantic-AI message schemas using the official TypeAdapter
        serialized_messages = json.loads(ModelMessagesTypeAdapter.dump_json(messages).decode("utf-8"))
        
        traces.append({
            "subagent": subagent_name,
            "messages": serialized_messages
        })
        
        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(traces, f, indent=2)
    except Exception as e:
        sys.stderr.write(f" -> [TELEMETRY ERROR] Trace append failed: {str(e)}\n")
        sys.stderr.flush()


def save_subagent_final_output(subagent_name: str, identifier: str, payload_dict: dict):
    """Saves the intermediate structured models parsed by specialized agents."""
    outputs_file = "subagent_outputs.json"
    try:
        outputs = {}
        if os.path.exists(outputs_file):
            with open(outputs_file, "r", encoding="utf-8") as f:
                try:
                    outputs = json.load(f)
                except Exception:
                    outputs = {}
                    
        if subagent_name not in outputs:
            outputs[subagent_name] = {}
            
        outputs[subagent_name][identifier] = payload_dict
        
        with open(outputs_file, "w", encoding="utf-8") as f:
            json.dump(outputs, f, indent=2)
    except Exception as e:
        sys.stderr.write(f" -> [TELEMETRY ERROR] Final output save failed: {str(e)}\n")
        sys.stderr.flush()

def log_subagent_activity(message: str):
    """Writes subagent logs to a local file so they don't break the MCP stdio stream"""
    try:
        with open("mcp_subagents.log", "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass

async def subagent_log_request(request: httpx.Request):
    payload = ""
    if request.content:
        try:
            body = request.content.decode('utf-8')
            try:
                payload = json.dumps(json.loads(body), indent=2)
            except Exception:
                payload = body
        except Exception:
            payload = "[Undecodable]"
            
    log_subagent_activity(
        f"\n\n==================================================\n"
        f" [SUB-AGENT REQUEST] ---> {request.method} {request.url}\n"
        f"Body:\n{payload[:6000]}\n"
        f"=================================================="
    )

async def subagent_log_response(response: httpx.Response):
    await response.aread()
    payload = ""
    try:
        body = response.text
        try:
            payload = json.dumps(json.loads(body), indent=2)
        except Exception:
            payload = body
    except Exception:
        payload = "[Undecodable]"
        
    log_subagent_activity(
        f"\n\n==================================================\n"
        f" [SUB-AGENT RESPONSE] <--- {response.status_code} {response.url}\n"
        f"Body:\n{payload[:6000]}\n"
        f"=================================================="
    )

subagent_debug_client = httpx.AsyncClient(
    timeout=600.0,
    event_hooks={"request": [subagent_log_request], "response": [subagent_log_response]}
)


# Create the official OpenAI client for the sub-agents

model = OpenAIChatModel(
    os.getenv("MODEL_ID_UNI_GREIFSWALD"),
    provider=OpenAIProvider(
        base_url= os.getenv("OPENAI_API_BASE_UNI_GREIFSWALD"),
        api_key=os.getenv("OPENAI_API_KEY_UNI_GREIFSWALD"), 
        http_client=subagent_debug_client
    ),
    profile=ModelProfile(
        default_structured_output_mode='tool',
        supports_json_schema_output=False,
    ),
)
extra_body_dict = json.loads(os.getenv("LITELLM_EXTRA_BODY_UNI_GREIFSWALD"))
settings =  ModelSettings(
    extra_body=extra_body_dict
)

sub_agent_model = model 
sub_agent_settings = settings


class MCPEnvironment:
    """
    A stateful, file-backed universal environment. 
    Maintains a pass-by-reference registry of heavy payloads across subprocess lifecycles.
    """
    def __init__(self, filename: str = "mcp_state_registry.pkl"):
        self._filename = filename
        # Ensure the registry starts with the persisted disk state
        self._registry: Dict[str, Dict[str, Any]] = self._load_from_disk()

    def _load_from_disk(self) -> Dict[str, Dict[str, Any]]:
        """Loads the registry from a local pickle file if it exists."""
        if os.path.exists(self._filename):
            try:
                with open(self._filename, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                # Fallback to empty state if file is unreadable or corrupted
                print(f"Warning: Failed to load MCP environment registry: {e}")
                return {}
        return {}

    def _save_to_disk(self):
        """Saves the current registry state to the local pickle file."""
        try:
            with open(self._filename, "wb") as f:
                pickle.dump(self._registry, f)
        except Exception as e:
            print(f"Failed to write to MCP environment registry: {e}")

    def write(self, data_type: str, payload: Any, summary: str, size_indicator: str) -> ReferenceHandle:
        """Stores a payload in the environment and persists it to disk."""
        # Sync current state in case another process wrote to it
        self._registry = self._load_from_disk()
        
        ref_id = f"ref_{data_type}_{str(uuid.uuid4())[:8]}"
        self._registry[ref_id] = {
            "payload": payload,
            "data_type": data_type,
            "summary": summary,
            "size_indicator": size_indicator
        }
        
        # Save state changes
        self._save_to_disk()
        
        return ReferenceHandle(
            ref_id=ref_id,
            data_type=data_type,
            size_indicator=size_indicator,
            summary=summary
        )

    def read(self, ref_id: str) -> Any:
        """Retrieves a payload from the disk-backed environment by its reference ID."""
        # Always read fresh from disk to ensure cross-process alignment
        self._registry = self._load_from_disk()
        
        if ref_id not in self._registry:
            raise ValueError(f"Reference ID '{ref_id}' does not exist in the active environment.")
        return self._registry[ref_id]["payload"]

    def list_objects(self) -> Dict[str, Dict[str, str]]:
        """Returns metadata of all objects currently registered in the environment."""
        self._registry = self._load_from_disk()
        return {
            ref_id: {
                "data_type": obj["data_type"],
                "summary": obj["summary"],
                "size_indicator": obj["size_indicator"]
            }
            for ref_id, obj in self._registry.items()
        }

    def clear(self):
        """Purges the environment memory and cleans up the local file."""
        self._registry.clear()
        self._save_to_disk()
        if os.path.exists(self._filename):
            try:
                os.remove(self._filename)
            except Exception as e:
                print(f"Failed to delete registry file: {e}")

# Initialize the global environment instance
env = MCPEnvironment()

# =====================================================================
# 2. UNIVERSAL INSPECTION & ENVIRONMENT UTILS
# =====================================================================

@mcp.tool()
def environment_list_objects() -> str:
    """
    Lists the metadata of all active reference objects currently stored in the environment.
    Allows the orchestrator to keep track of its available data pointers.
    """
    return json.dumps(env.list_objects(), indent=2)


@mcp.tool()
def environment_inspect_object(ref_id: str, max_chars: int = 1000) -> str:
    """
    Allows an agent to 'peek' inside a reference handle payload securely.
    Returns a truncated view of the payload without flooding the context window.
    
    Args:
        ref_id (str): The reference pointer ID (e.g., 'ref_raw_pdf_text_a37f').
        max_chars (int): The maximum number of characters of the payload to return.
    """
    try:
        payload = env.read(ref_id)
        payload_str = str(payload)
        
        if len(payload_str) > max_chars:
            return (
                f"--- Object {ref_id} Truncated View ---\n"
                f"{payload_str[:max_chars]}\n"
                f"... [Truncated. Total length: {len(payload_str)} characters] ..."
            )
        return payload_str
    except Exception as e:
        return f"Failed to inspect reference: {str(e)}"
        
def load_json_file(file_path: str) -> Dict[str, Any]:
    """Helper utility to safely load JSON files with descriptive error fallbacks."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Required file not found at: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# =====================================================================
# RESOURCES
# =====================================================================

@mcp.resource("automotive://domains")
def get_automotive_domains() -> ReferenceHandle:
    """
    Retrieve the main automotive role domains and their descriptions,
    registers them in the environment, and returns a ReferenceHandle.
    """
    try:
        data = load_json_file(DOMAINS_FILE_PATH)
        domains = data.get("automotive_role_domains", [])
        return env.write(
            data_type="taxonomy_domains",
            payload=domains,
            summary="Automotive role domains and technical descriptions.",
            size_indicator=f"{len(domains)} domains registered"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch domains: {str(e)}")


@mcp.resource("automotive://jobs-by-domain")
def get_jobs_by_domain() -> ReferenceHandle:
    """
    Retrieve the mapping of job keys to role domains,
    registers them in the environment, and returns a ReferenceHandle.
    """
    try:
        data = load_json_file(DOMAINS_FILE_PATH)
        jobs_mapping = data.get("jobs_per_role_domain", {})
        return env.write(
            data_type="taxonomy_jobs_mapping",
            payload=jobs_mapping,
            summary="Corporate job-to-domain mapping taxonomy.",
            size_indicator=f"{len(jobs_mapping)} domains mapped"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch job mappings: {str(e)}")

@mcp.resource("matcher://scoring-framework")
def get_scoring_framework() -> str:
    """
    Returns the official scoring hierarchy registered in the environment.

    This resource defines:
    - All scoring categories (must-have, experience, domain, toolchain, etc.)
    - The weight of each category (e.g., must-have = 40 points)
    - The meaning and purpose of each category
    - The evaluation criteria the agent MUST follow when assigning points

    """
    payload = SCORING_HIERARCHY.model_dump_json(indent=2)
    return env.write(
        data_type="scoring_framework",
        payload=payload,
        summary="Official weighted scoring framework guidelines.",
        size_indicator=f"{len(payload)} characters"
    )

# =====================================================================
# TOOLS
# =====================================================================

#@mcp.tool()
def get_job_description(job_key: str) -> ReferenceHandle:
    """
    Fetches job details for a pre-registered, static internal company taxonomy job key (e.g., 'systems_engineer').
    DO NOT call this for external URLs, website links, or scraped job descriptions. This is strictly for internal company taxonomy lookup keys.
    
    Args:
        job_key (str): The specific identifier of the job (e.g., 'systems_engineer').
    """
    try:
        details = load_json_file(DETAILS_FILE_PATH)
        if job_key in details:
            payload = details[job_key]
            return env.write(
                data_type="job_description_context",
                payload=payload,
                summary=f"Automotive JD taxonomy context for: '{job_key}'",
                size_indicator=f"{len(payload)} characters"
            )
        
        # Simple fallback for search suggestions
        similar_keys = [k for k in details.keys() if job_key.lower() in k.lower()]
        suggestions = f" Did you mean: {', '.join(similar_keys)}?" if similar_keys else ""
        raise ValueError(f"Job key '{job_key}' not found.{suggestions}")
        
    except Exception as e:
        raise RuntimeError(f"Failed to fetch job description: {str(e)}")
    

@mcp.tool()
def register_raw_jd_text(jd_text: str) -> ReferenceHandle:
    """
    Registers a raw pasted descriptive text block of a job description into the active environment.
    DO NOT call this if the input is a URL or a website link. This is strictly for raw text blocks.
    """
    sys.stderr.write(" -> [TOOL] Registering raw pasted JD text in environment\n")
    sys.stderr.flush()
    
    # Store the raw text directly in the registry payload
    ref = env.write(
        data_type="scraped_jobs_list",  # Keeps it compatible with Case A of run_jd_extraction_agent
        payload=jd_text,
        summary="Raw pasted Job Description text",
        size_indicator=f"{len(jd_text)} characters"
    )
    return ref

@mcp.tool()
def scrape_job_description_url(url: str) -> ReferenceHandle:
    """
    Crawls an external job description webpage from a given URL link starting with http/https.
    Use this tool immediately if there is a website link representing the job description.
    
    Returns a ReferenceHandle pointer to a single-item scraped_jobs_list.
    """
    sys.stderr.write(f" -> [TOOL] Crawling job webpage: {url}\n")
    sys.stderr.flush()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # Redirect standard output prints to avoid breaking MCP JSON-RPC protocol
        with redirect_stdout(sys.stderr):
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Extract the entire page text
            full_text = soup.get_text(separator="\n", strip=True)
            
            # Extract title (finding h1, falling back to page title)
            title_tag = soup.find("h1") or soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else "Unknown Position"
            
        # FORMAT AS A SINGLE-ELEMENT LIST
        # Matches the exact dictionary structure expected by run_jd_extraction_agent
        payload = [{
            "title": title,
            "company": "Direct Scraped URL",
            "location": "Direct Scraped URL",
            "description": full_text,
            "url": url
        }]
        
        # Write to environment under the existing 'scraped_jobs_list' data type
        ref = env.write(
            data_type="scraped_jobs_list",
            payload=payload,
            summary=f"Scraped job page details for '{title}' from: '{url}'",
            size_indicator="1 job found"
        )
        return ref
        
    except Exception as e:
        raise RuntimeError(f"Failed to crawl job webpage from URL '{url}': {str(e)}")

@mcp.tool()
def scrape_pdf_content(pdf_path: str) -> ReferenceHandle:
    """
    Reads a local PDF, extracts its text, and registers it into the universal environment.
    Returns a small ReferenceHandle pointer instead of raw text.
    """
    sys.stderr.write(f" -> [TOOL] Reading PDF: {pdf_path}\n")
    sys.stderr.flush()
    
    try:
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text(layout=True)
                if page_text:
                    text_parts.append(f"--- Page {i+1} ---\n{page_text}")
                    
        full_text = "\n\n".join(text_parts)
        
        # Write heavy text payload directly to our universal environment
        ref = env.write(
            data_type="raw_pdf_text",
            payload=full_text,
            summary=f"Extract of candidate CV file: '{pdf_path}'",
            size_indicator=f"{len(full_text)} characters"
        )
        return ref
    except Exception as e:
        raise RuntimeError(f"Error reading PDF: {str(e)}")

#@mcp.tool(timeout=720.0) 
async def tool_extract_cv_profile_by_reference(
    pdf_text_ref_id: str, 
    scenario: str,
    context_ref_id: str = None
) -> CVExtractionOutput:
    """
    Executes CV extraction using a single-turn structured LLM call. 
    Reads raw CV text and alignment context directly from the state environment.
    
    Args:
        pdf_text_ref_id: Environment reference pointer to the raw CV text.
        scenario: Operational scenario ('A' or 'B').
        context_ref_id: Optional reference pointer to company-specific taxonomy.
    """
    raw_cv_text = env.read(pdf_text_ref_id)
    company_alignment_context = env.read(context_ref_id) if context_ref_id else ""
    
    system_prompt = (
        f"{CV_PROMPT}\n\n"
        f"--- ACTIVE SCENARIO: Scenario {scenario} ---\n"
        f"--- AUDIT TAXONOMY AND SYSTEM GUIDELINES ---\n"
        f"{company_alignment_context}\n"
        f"--------------------------------------------"
    )
    
    extractor = Agent(
        sub_agent_model,
        model_settings=sub_agent_settings,
        system_prompt=system_prompt,
        output_type=CVExtractionOutput,
    )
    
    result = await extractor.run(
        f"Please extract and structure the candidate profile from this raw text [Scenario {scenario}]:\n\n{raw_cv_text}"
    )
    structured_output = result.output

    # Write structured output directly to the state registry from inside the tool
    ref = env.write(
        data_type="structured_cv",
        payload=structured_output,
        summary=f"Structured CV Profile for candidate: {structured_output.candidate_name} [Scenario {scenario}]",
        size_indicator=f"{len(structured_output.projects)} projects, {structured_output.years_of_experience} years exp"
    )
    return ref

#@mcp.tool(timeout=720.0)  
async def tool_extract_jd_demands_by_reference(
    jobs_list_ref_id: str, 
    index: int = 0,
    scenario: str = "B",
    context_ref_id: str = None
) -> JDExtractionOutput:
    """
    Executes JD requirements extraction using a single-turn structured LLM call.
    Reads raw job listings and alignment context directly from the state environment.
    
    Args:
        jobs_list_ref_id: Environment reference pointer to raw job listings.
        index: Index of the job to process in the list.
        scenario: Operational scenario ('A' or 'B').
        context_ref_id: Optional reference pointer to company-specific taxonomy.
    """
    payload = env.read(jobs_list_ref_id)
    company_alignment_context = env.read(context_ref_id) if context_ref_id else ""
    
    # Resolve index payload
    if isinstance(payload, str):
        description = payload
    elif isinstance(payload, list):
        item = payload[index]
        description = item.get("description") if isinstance(item, dict) else str(item)
    elif isinstance(payload, dict):
        description = payload.get("description", str(payload))
    else:
        description = str(payload)

    system_prompt = (
        f"{JOB_DESCRIPTION_PROMPT}\n\n"
        f"--- ACTIVE SCENARIO: Scenario {scenario} ---\n"
        f"--- CORPORATE TAXONOMY ALIGNMENT CONTEXT ---\n"
        f"{company_alignment_context}\n"
        f"--------------------------------------------"
    )

    extractor = Agent(
        sub_agent_model,
        model_settings=sub_agent_settings,
        system_prompt=system_prompt,
        output_type=JDExtractionOutput,
    )
    
    result = await extractor.run(
        f"Structure the requirements for this job posting [Scenario {scenario}]:\n{description}"
    )
    structured_output = result.output

    ref = env.write(
        data_type="structured_jd",
        payload=structured_output,
        summary=f"Structured requirements for position: '{structured_output.job_title}' [Scenario {scenario}]",
        size_indicator=f"{len(structured_output.requirements.must_have)} must-have requirements"
    )
    return ref

#@mcp.tool(timeout=720.0)
async def tool_execute_matching_evaluation_by_reference(
    cv_data_ref_id: str, 
    jd_data_ref_id: str, 
    scenario: str,
    context_ref_id: str = None
) -> MatchOutput:
    """
    Executes a matching evaluation using structured data references and scenario constraints.
    
    Args:
        cv_data_ref_id: Reference pointing to structured CVExtractionOutput.
        jd_data_ref_id: Reference pointing to structured JDExtractionOutput.
        scenario: Operational scenario ('A' or 'B').
        context_ref_id: Reference pointer to scoring frameworks.
    """
    cv_data = env.read(cv_data_ref_id)
    jd_data = env.read(jd_data_ref_id)
    scoring_framework_context = env.read(context_ref_id) if context_ref_id else SCORING_HIERARCHY.model_dump_json(indent=2)
    
    system_prompt = (
        f"{MATCHER_PROMPT}\n\n"
        f"--- ACTIVE SCENARIO: Scenario {scenario} ---\n"
        f"--- SCORING METRIC SYSTEMS AND RULES ---\n"
        f"{scoring_framework_context}\n"
        f"----------------------------------------"
    )
    
    matcher = Agent(
        sub_agent_model,
        model_settings=sub_agent_settings,
        system_prompt=system_prompt,
        output_type=MatchOutput,
    )
    
    payload = {
        "cv_details": cv_data.model_dump() if hasattr(cv_data, "model_dump") else cv_data,
        "jd_requirements": jd_data.model_dump() if hasattr(jd_data, "model_dump") else jd_data
    }
    
    result = await matcher.run(
        f"Perform matching evaluation on these parameters [Scenario {scenario}]:\n{json.dumps(payload, indent=2)}"
    )

    structured_output = result.output

    ref = env.write(
        data_type="match_report",
        payload=structured_output,
        summary=f"Detailed candidate-to-role alignment report for {cv_data_ref_id} -> {jd_data_ref_id} [Scenario {scenario}].",
        size_indicator="Category-based breakdown analysis"
    )
    return ref


@mcp.tool(timeout=720.0)  # Extended timeout for slow LLM calls during extraction
async def run_cv_extraction_agent(pdf_text_ref_id: str, scenario: str) -> ReferenceHandle:
    """
    Spawns the CV Extraction Sub-Agent on a raw text reference stored in the environment.
    Saves the structured CVExtractionOutput back to the environment.
    
    Args:
        pdf_text_ref_id (str): The reference pointer to the raw PDF text (e.g., 'ref_raw_pdf_text_a37f').
        scenario: A or B referencing the scenario to be analysed
    """
    sys.stderr.write(f" -> [SUB-AGENT] Executing CV extraction on reference: {pdf_text_ref_id}\n")
    sys.stderr.flush()
    with mlflow.start_span(name="SubAgent_CV_Evaluation", span_type="agent") as span:
        span.set_inputs({
            "pdf_text_ref_id": pdf_text_ref_id,
            "scenario": scenario
        })

        inputs = CVRawDataInput(
            pdf_path=f"Environment Reference: {pdf_text_ref_id}",
            scenario = scenario
        )

        prompt = f"Coordinate CV extraction on reference: {pdf_text_ref_id} under Scenario: {scenario}"
        result = await cv_extraction_subagent.run(prompt, deps=inputs)

        # Save telemetries
        append_subagent_trace(f"CV Extraction Coordinator ({scenario})", result.all_messages())

        try:
            ref_handle = result.output
            structured_data = env.read(ref_handle.ref_id)  # Read actual CVExtractionOutput
            save_subagent_final_output(
                "CV Extraction Profiles", 
                structured_data.candidate_name or f"Candidate_{ref_handle.ref_id[-4:]}", 
                structured_data.model_dump() if hasattr(structured_data, "model_dump") else structured_data
            )
        except Exception as e:
            sys.stderr.write(f" -> [TELEMETRY ERROR] CV Output save failed: {str(e)}\n")
            sys.stderr.flush()

        # Returning the final ReferenceHandle produced by the agent
        return result.output



@mcp.tool(timeout=720.0)  
async def run_jd_extraction_agent(jobs_list_ref_id: str, index: int, scenario: str) -> ReferenceHandle:
    """
    Extracts a specific job from a scraped job list reference and structures its requirements.
    Saves the JDExtractionOutput back to the environment.
    
    Args:
        jobs_list_ref_id: Pointer reference to raw job listings.
        index: Index of target job.
        scenario: Operational scenario ('A' or 'B').
    """
    sys.stderr.write(f" -> [SUB-AGENT] Executing JD extraction on ref: {jobs_list_ref_id} index: {index} [Scenario: {scenario}]\n")
    sys.stderr.flush()
        # Use mlflow.start_span to log this sub-agent execution
    with mlflow.start_span(name=f"SubAgent_JD_Extraction_Idx_{index}", span_type="agent") as span:
        span.set_inputs({
            "jobs_list_ref_id": jobs_list_ref_id,
            "index": index,
            "scenario": scenario
        })
        prompt = f"Coordinate JD extraction on reference: {jobs_list_ref_id} index: {index} under Scenario: {scenario}"
        result = await jd_extraction_subagent.run(prompt)

        append_subagent_trace(f"JD Extraction Coordinator ({scenario})", result.all_messages())

        try:
            ref_handle = result.output
            structured_data = env.read(ref_handle.ref_id)  # Read actual JDExtractionOutput
            save_subagent_final_output(
                "JD Extraction Demands", 
                structured_data.job_title or f"Job_{ref_handle.ref_id[-4:]}", 
                structured_data.model_dump() if hasattr(structured_data, "model_dump") else structured_data
            )
        except Exception as e:
            sys.stderr.write(f" -> [TELEMETRY ERROR] JD Output save failed: {str(e)}\n")
            sys.stderr.flush()

        return result.output


@mcp.tool(timeout=720.0)  # Extended timeout for slow LLM calls during matching
async def run_matcher_agent(cv_ref_id: str, jd_ref_id: str, scenario: str) -> ReferenceHandle:
    """
    Performs comparative evaluation between a structured CV and structured JD reference.
    Saves the MatchOutput back to the environment.
    
    Args:
        cv_ref_id: Pointer to the structured CV extraction.
        jd_ref_id: Pointer to the structured JD extraction.
        scenario: Operational scenario ('A' or 'B').
    """
    sys.stderr.write(f" -> [SUB-AGENT] Executing alignment matching on: {cv_ref_id} + {jd_ref_id} [Scenario: {scenario}]\n")
    sys.stderr.flush()

    with mlflow.start_span(name="SubAgent_Matcher_Evaluation", span_type="agent") as span:
        span.set_inputs({
            "cv_ref_id": cv_ref_id,
            "jd_ref_id": jd_ref_id,
            "scenario": scenario
        })

        prompt = f"Coordinate matching on CV: {cv_ref_id} and JD: {jd_ref_id} under Scenario: {scenario}"

        result = await matcher_subagent.run(prompt)

        append_subagent_trace(f"Matcher Coordinator ({scenario})", result.all_messages())

        try:
            ref_handle = result.output
            structured_data = env.read(ref_handle.ref_id)  # Read actual MatchOutput
            match_key = f"{cv_ref_id} -> {jd_ref_id} [Scenario {scenario}]"
            save_subagent_final_output(
                "Matcher Comparative Results", 
                match_key, 
                structured_data.model_dump() if hasattr(structured_data, "model_dump") else structured_data
            )
        except Exception as e:
            sys.stderr.write(f" -> [TELEMETRY ERROR] Matcher Output save failed: {str(e)}\n")
            sys.stderr.flush()

        return result.output



@mcp.tool()
def job_search(
    search_term: str,
    location: str = "",
    results_wanted: int = 2,
    hours_old: int = 72,
    country_indeed: str = "USA",
    sites: list[str] = ["indeed", "linkedin", "zip_recruiter", "google"],
    linkedin_fetch_description: bool = True
) -> ReferenceHandle:
    """
    Search job postings across multiple job boards using the JobSpy library.

    Args:
        search_term (str):
            The job title or keywords to search for.
            Example: "software engineer", "KI Entwickler", "data scientist".

        location (str):
            City, region, or country to filter results.
            Example: "San Francisco, CA", "Berlin", "Remote".
            Leave empty "" for global search (if supported by the site).

        results_wanted (int):
            Maximum number of job postings to return.
            JobSpy may return slightly fewer depending on availability.

        hours_old (int):
            Only return jobs posted within the last N hours.
            Example: 24 = last day, 72 = last 3 days.

        country_indeed (str):
            Country code for Indeed scraping.
            Examples:
                "USA" → indeed.com
                "DE"  → indeed.de
                "CA"  → indeed.ca

        sites (list[str]):
            List of job boards to scrape.
            Supported values:
                "indeed", "linkedin", "glassdoor",
                "zip_recruiter", "google", "bayt",
                "naukri", "bdjobs"

        linkedin_fetch_description (bool):
            If True, fetches full job descriptions from LinkedIn.
            Slower but returns richer text.

    Returns:
            ReferenceHandle: A pointer object stored in the universal environment. 
            You MUST pass its `ref_id` to the `run_jd_extraction_agent` tool.
    """

    try:
        # Protect the MCP pipe by redirecting stdout to stderr
        with redirect_stdout(sys.stderr):
            jobs = scrape_jobs(
                site_name=sites,
                search_term=search_term,
                google_search_term=f"{search_term} jobs near {location} since yesterday",
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed=country_indeed,
                linkedin_fetch_description=linkedin_fetch_description
            )
    except Exception as e:
        # DO NOT return {"error": str(e)} as it violates the ReferenceHandle schema.
        # Raising an exception allows pydantic-ai to process the error properly.
        raise RuntimeError(f"JobSpy scraping failed: {str(e)}")

    # Convert all non‑JSON‑safe values (dates, timestamps, numpy types)
    jobs = jobs.applymap(
        lambda x: x.isoformat() if hasattr(x, "isoformat")
        else str(x) if not isinstance(x, (int, float, bool, type(None)))
        else x
    )

    records = jobs.to_dict(orient="records")
    # Write the entire raw results array directly to the state environment
    search_ref = env.write(
        data_type="scraped_jobs_list",
        payload=records, # Store the list of dicts directly
        summary=f"Scraped job board listings query: '{search_term}' near '{location}'",
        size_indicator=f"{len(records)} jobs found"
    )
    return search_ref



# To install: pip install tavily-python
#from tavily import TavilyClient
#client = TavilyClient("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")
#response = client.search(
#    query="",
#    search_depth="advanced"
#)
#print(response)
# =====================================================================
# MCP PROMPTS
# =====================================================================

#@mcp.prompt()
#def get_agent_orchestrator_prompt() -> str:
#    """
#    System prompt to instruct the primary AI agent on behavioral guidelines and tool usage.
#    """
#    return AGENT_PROMPT
#
#
#@mcp.prompt()
#def get_cv_extraction_prompt() -> str:
#    """
#    Guidelines and step-by-step instructions on how to parse and audit CV documents.
#    """
#    return CV_PROMPT
#
#
#@mcp.prompt()
#def get_job_description_prompt() -> str:
#    """
#    Instructions on how to analyze and dissect automotive job requirements.
#    """
#    return JOB_DESCRIPTION_PROMPT
#
#
#@mcp.prompt()
#def get_matcher_prompt() -> str:
#    """
#    The analysis matrix guidelines used to align candidates to JDs.
#    """
#    return MATCHER_PROMPT



# =====================================================================
# SUB-AGENT DEFINITIONS
# =====================================================================

# 1. Specialized CV Extraction Agent
# Re-enable the local scraper tool
cv_extraction_subagent = Agent(
    sub_agent_model,
    model_settings=sub_agent_settings,
    system_prompt=CV_AGENT_PROMPT,
    deps_type=CVRawDataInput,
    output_type=ReferenceHandle,
    tools=[get_job_description, get_automotive_domains, get_jobs_by_domain, scrape_pdf_content, tool_extract_cv_profile_by_reference],
    retries=3
)
# 2. Specialized Job Description Extraction Agent
# Has access to the local Web page scraping tool to retrieve raw context.
jd_extraction_subagent = Agent(
    sub_agent_model,
    model_settings=sub_agent_settings,
    system_prompt=JD_AGENT_PROMPT,
    output_type=ReferenceHandle,
    tools=[get_job_description, get_automotive_domains, get_jobs_by_domain, register_raw_jd_text,scrape_job_description_url, tool_extract_jd_demands_by_reference],
    retries=3
)

# 3. Specialized Matcher Agent
# Takes structured data inputs to perform gap-analysis, scoring, and evaluations.
matcher_subagent = Agent(
    sub_agent_model,
    model_settings=sub_agent_settings,
    system_prompt=MATCHER_AGENT_PROMPT,
    output_type=ReferenceHandle,
    tools=[get_scoring_framework, tool_execute_matching_evaluation_by_reference],
    retries=3
)

if __name__ == "__main__":
    # Standard entry point to run the server
    sys.stdout = _real_stdout   # Restore stdout for MCP JSON-RPC communication
    mcp.run() 
#    response = asyncio.run(run_cv_extraction_agent(pdf_path = r"cv/data/ENGINEERING/12011623.pdf"))
#    print(response)


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
import pdfplumber

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
    AGENT_PROMPT,
    CV_PROMPT,
    JOB_DESCRIPTION_PROMPT,
    MATCHER_PROMPT
)

from schemas import (
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

# Detect the directory of the current script to locate the JSON files reliably
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAINS_FILE_PATH = os.path.join(BASE_DIR, "job_main_domains.json")
DETAILS_FILE_PATH = os.path.join(BASE_DIR, "jobs_details.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


os.environ["OPENAI_API_BASE"] = "https://apphubai.wolke.uni-greifswald.de/v1"  #"https://apphubai.wolke.uni-greifswald.de/v1"#"http://models.system-service-ai/v1" 
os.environ["OPENAI_API_KEY"] = "RYpNq6AnGTbyaWX8ijFzl5tAdjNqcxWo"   #"RYpNq6AnGTbyaWX8ijFzl5tAdjNqcxWo" # "not-needed"   
os.environ["LITELLM_EXTRA_BODY"] = '{"chat_template_kwargs": {"enable_thinking": false}}'

model_id = "qwen3-coder:30b"#"gemma3:27b" #"Qwen/Qwen3-VL-30B-A3B-Instruct-FP8" #"RedHatAI/Qwen3-32B-quantized.w4a16", #qwen3-coder:30b
judge_uri = f"openai:/{model_id}"
TAVILY_KEY = "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"


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
    model_id,
    provider=OpenAIProvider(
        base_url= os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"), 
        http_client=subagent_debug_client
    ),
    profile=ModelProfile(
        default_structured_output_mode='tool',
        supports_json_schema_output=False,
    ),
)
extra_body_dict = json.loads(os.getenv("LITELLM_EXTRA_BODY"))
settings =  ModelSettings(
    extra_body=extra_body_dict
)

sub_agent_model = model 
sub_agent_settings = settings


class MCPEnvironment:
    """
    A stateful, in-memory universal environment. 
    Maintains a pass-by-reference registry of heavy payloads during the execution session.
    """
    def __init__(self):
        self._registry: Dict[str, Dict[str, Any]] = {}

    def write(self, data_type: str, payload: Any, summary: str, size_indicator: str) -> ReferenceHandle:
        """Stores a payload in the environment and returns a tracking ReferenceHandle."""
        ref_id = f"ref_{data_type}_{str(uuid.uuid4())[:8]}"
        self._registry[ref_id] = {
            "payload": payload,
            "data_type": data_type,
            "summary": summary,
            "size_indicator": size_indicator
        }
        return ReferenceHandle(
            ref_id=ref_id,
            data_type=data_type,
            size_indicator=size_indicator,
            summary=summary
        )

    def read(self, ref_id: str) -> Any:
        """Retrieves a payload from the environment by its reference ID."""
        if ref_id not in self._registry:
            raise ValueError(f"Reference ID '{ref_id}' does not exist in the active environment.")
        return self._registry[ref_id]["payload"]

    def list_objects(self) -> Dict[str, Dict[str, str]]:
        """Returns metadata of all objects currently registered in the environment."""
        return {
            ref_id: {
                "data_type": obj["data_type"],
                "summary": obj["summary"],
                "size_indicator": obj["size_indicator"]
            }
            for ref_id, obj in self._registry.items()
        }

    def clear(self):
        """Purges the environment memory."""
        self._registry.clear()

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
def get_automotive_domains() -> str:
    """
    Retrieve the main automotive role domains and their high-level descriptions.
    
    This resource serves as the structural entry point for understanding 
    how the enterprise categorizes its technical and commercial operations.
    """
    try:
        data = load_json_file(DOMAINS_FILE_PATH)
        domains = data.get("automotive_role_domains", [])
        return json.dumps(domains, indent=2)
    except FileNotFoundError:
        return json.dumps({"error": "job_main_domains.json could not be located on the server path."}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"An unexpected error occurred: {str(e)}"}, indent=2)


@mcp.resource("automotive://jobs-by-domain")
def get_jobs_by_domain() -> str:
    """
    Retrieve the map of structural job keys to their human-readable titles, 
    grouped by their respective role domains.
    
    This is highly useful for mapping specific developers or specialists 
    back to their functional automotive department.
    """
    try:
        data = load_json_file(DOMAINS_FILE_PATH)
        jobs_mapping = data.get("jobs_per_role_domain", {})
        return json.dumps(jobs_mapping, indent=2)
    except FileNotFoundError:
        return json.dumps({"error": "job_main_domains.json could not be located on the server path."}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"An unexpected error occurred: {str(e)}"}, indent=2)


# =====================================================================
# TOOLS
# =====================================================================

@mcp.tool()
def get_job_description(job_key: str) -> str:
    """
    Fetch the detailed activities, tools, hardware interfaces, and required 
    skills for a specific job key.
    
    Args:
        job_key (str): The specific identifier of the job (e.g., 'digital_subscription_manager', 'systems_engineer').
    """
    try:
        details = load_json_file(DETAILS_FILE_PATH)
        
        # Check if the requested key exists
        if job_key in details:
            return details[job_key]
        
        # Fallback helper if the exact key was not found
        similar_keys = [k for k in details.keys() if job_key.lower() in k.lower()]
        suggestions = f" Did you mean: {', '.join(similar_keys)}?" if similar_keys else ""
        return f"Error: Job key '{job_key}' not found.{suggestions}"
        
    except FileNotFoundError:
        return "Error: The detailed job registry file 'jobs_details.json' could not be found."
    except Exception as e:
        return f"An error occurred while fetching the description: {str(e)}"



@mcp.tool()
def scrape_job_description_url(url: str) -> ReferenceHandle:
    """
    Crawls a job description webpage from a given URL (e.g., JobBank, LinkedIn, etc.),
    extracts its full page text and title, and registers it into the universal environment.
    
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


@mcp.tool(timeout=720.0)  # Extended timeout for slow LLM calls during extraction
async def run_cv_extraction_agent(pdf_text_ref_id: str) -> ReferenceHandle:
    """
    Spawns the CV Extraction Sub-Agent on a raw text reference stored in the environment.
    Saves the structured CVExtractionOutput back to the environment.
    
    Args:
        pdf_text_ref_id (str): The reference pointer to the raw PDF text (e.g., 'ref_raw_pdf_text_a37f').
    """
    sys.stderr.write(f" -> [SUB-AGENT] Executing CV extraction on reference: {pdf_text_ref_id}\n")
    sys.stderr.flush()

    # 1. Read the heavy raw text directly from the environment
    raw_cv_text = env.read(pdf_text_ref_id)
    
    # We still need to pass a dummy deps object to satisfy Pydantic AI's signature requirements
    inputs = CVRawDataInput(pdf_path=f"Environment Reference: {pdf_text_ref_id}")
    
    prompt = f"Please extract and structure the candidate profile from this raw text:\n\n{raw_cv_text}"
    
    # 2. Run the sub-agent
    result = await cv_extraction_subagent.run(
        prompt,
        deps=inputs,
        usage_limits=UsageLimits(request_limit=5)
    )
    
    # 3. Write the structured schema output to the environment and return a clean pointer
    structured_ref = env.write(
        data_type="structured_cv",
        payload=result.output,  # Store the Pydantic CVExtractionOutput object
        summary=f"Structured CV Profile for candidate: {result.output.candidate_name}",
        size_indicator=f"{len(result.output.projects)} projects, {result.output.years_of_experience} years exp"
    )
    return structured_ref


@mcp.tool(timeout=720.0)  # Extended timeout for slow LLM calls during extraction
async def run_jd_extraction_agent(jobs_list_ref_id: str, index: int) -> ReferenceHandle:
    """
    Extracts a specific job from a scraped job list reference and structures its requirements.
    Saves the structured JDExtractionOutput back to the environment.
    """
    # 1. Read the list of dicts from our environment using the reference
    jobs_list = env.read(jobs_list_ref_id)
    
    if index < 0 or index >= len(jobs_list):
        raise IndexError(f"Index {index} out of bounds for job list size {len(jobs_list)}")
        
    target_job = jobs_list[index]
    
    # Safeguard: Convert None values to strings
    title = target_job.get("title") or "Unknown"
    company = target_job.get("company") or "Unknown"
    location = target_job.get("location") or "Unknown"
    description = target_job.get("description") or ""
    url = target_job.get("url") or ""

    # FAST-FAIL GUARD: If description is empty, do not run the sub-agent!
    if not description.strip() or len(description.strip()) < 50:
        raise ValueError(
            f"The scraped description for '{title}' at '{company}' is empty. "
            "The extraction sub-agent cannot proceed. Please ensure the search tool "
            "is fetching full descriptions (try enabling linkedin_fetch_description)."
        )
        
    # Build JDRawDataInput safely
    job_data = JDRawDataInput(
        title=title,
        company=company,
        location=location,
        description=description,
        url=url
    )
    
    sys.stderr.write(f" -> [SUB-AGENT] Parsing cached job at index {index}: {job_data.title}\n")
    sys.stderr.flush()
    
    prompt = f"Structure the requirements for this job posting:\n{job_data.description}"
    
    # 2. Run the sub-agent
    result = await jd_extraction_subagent.run(prompt, deps=job_data)
    
    # 3. Write output to environment and return a reference pointer
    jd_ref = env.write(
        data_type="structured_jd",
        payload=result.output, # Store JDExtractionOutput
        summary=f"Structured requirements for position: '{result.output.job_title}' at '{company}'",
        size_indicator=f"{len(result.output.requirements.must_have)} must-have requirements"
    )
    return jd_ref


@mcp.tool(timeout=720.0)  # Extended timeout for slow LLM calls during matching
async def run_matcher_agent(cv_ref_id: str, jd_ref_id: str) -> ReferenceHandle:
    """
    Performs a comparative evaluation between a structured CV and structured JD reference.
    Saves the MatchOutput back to the environment.
    
    Args:
        cv_ref_id (str): Pointer to the 'structured_cv' object.
        jd_ref_id (str): Pointer to the 'structured_jd' object.
    """
    sys.stderr.write(f" -> [SUB-AGENT] Executing alignment matching on: {cv_ref_id} + {jd_ref_id}\n")
    sys.stderr.flush()

    # 1. Read the structured data objects directly from the state environment
    cv_data = env.read(cv_ref_id)
    jd_data = env.read(jd_ref_id)
    
    match_payload = {
        "cv_details": cv_data.model_dump(),
        "jd_requirements": jd_data.model_dump()
    }
    
    # 2. Run the sub-agent
    result = await matcher_subagent.run(
        f"Perform matching evaluation on these parameters:\n{json.dumps(match_payload, indent=2)}",
        usage_limits=UsageLimits(request_limit=15)
    )
    
    # 3. Write MatchOutput back to the environment
    match_ref = env.write(
        data_type="match_report",
        payload=result.output,
        summary=f"Compatibility evaluation result. Score: {result.output.compatibility_score}/100",
        size_indicator=f"Score: {result.output.compatibility_score}"
    )
    return match_ref



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

@mcp.prompt()
def get_agent_orchestrator_prompt() -> str:
    """
    System prompt to instruct the primary AI agent on behavioral guidelines and tool usage.
    """
    return AGENT_PROMPT


@mcp.prompt()
def get_cv_extraction_prompt() -> str:
    """
    Guidelines and step-by-step instructions on how to parse and audit CV documents.
    """
    return CV_PROMPT


@mcp.prompt()
def get_job_description_prompt() -> str:
    """
    Instructions on how to analyze and dissect automotive job requirements.
    """
    return JOB_DESCRIPTION_PROMPT


@mcp.prompt()
def get_matcher_prompt() -> str:
    """
    The analysis matrix guidelines used to align candidates to JDs.
    """
    return MATCHER_PROMPT



# =====================================================================
# SUB-AGENT DEFINITIONS
# =====================================================================

# 1. Specialized CV Extraction Agent
# Re-enable the local scraper tool
cv_extraction_subagent = Agent(
    sub_agent_model,
    model_settings=sub_agent_settings,
    system_prompt=CV_PROMPT,
    deps_type=CVRawDataInput,
    output_type=CVExtractionOutput,
    tools=[get_job_description, get_automotive_domains, get_jobs_by_domain],
    retries=3
)
# 2. Specialized Job Description Extraction Agent
# Has access to the local Web page scraping tool to retrieve raw context.
jd_extraction_subagent = Agent(
    sub_agent_model,
    model_settings=sub_agent_settings,
    system_prompt=JOB_DESCRIPTION_PROMPT,
    output_type=JDExtractionOutput,
    tools=[get_job_description, get_automotive_domains, get_jobs_by_domain],
    retries=3
)

# 3. Specialized Matcher Agent
# Takes structured data inputs to perform gap-analysis, scoring, and evaluations.
matcher_subagent = Agent(
    sub_agent_model,
    model_settings=sub_agent_settings,
    system_prompt=MATCHER_PROMPT,
    output_type=MatchOutput,
    tools=[get_job_description, get_automotive_domains, get_jobs_by_domain],
    retries=3
)

#TODO add a judge tool for CV extract and another judge tool validator for the job description extraction, another judge tool for the matcher is this needed? maybe not, maybe we can just have a final judge tool that evaluates the final match and gives a score and feedback on the match quality, this would be useful for iterative improvement of the matcher prompt and logic.
if __name__ == "__main__":
    # Standard entry point to run the server
    sys.stdout = _real_stdout   # Restore stdout for MCP JSON-RPC communication
    mcp.run() 
#    response = asyncio.run(run_cv_extraction_agent(pdf_path = r"cv/data/ENGINEERING/12011623.pdf"))
#    print(response)


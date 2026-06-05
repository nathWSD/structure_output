import streamlit as st
import pandas as pd
import asyncio
import os
import tempfile
import json
import sys
import traceback

# ==========================================
# 1. PAGE CONFIG & FULL-SCREEN STYLING
# ==========================================
st.set_page_config(
    page_title="Agentic CV Matching Portal", 
    layout="wide",  
    initial_sidebar_state="expanded"
)

# Stripped out conflicting colors so it works natively in Dark/Light Mode
st.markdown("""
<style>
    .block-container, .stMainBlockContainer {
        max-width: 95% !important;
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2.5rem !important;
        padding-right: 2.5rem !important;
    }
    .stTextArea textarea {
        font-family: monospace;
        font-size: 14px !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. IMPORTS & AGENT INTEGRATION
# ==========================================
try:
    # Import the execution function instead of the global agent
    from orchestrator import execute_agent_prompt
    from schemas import OrchestratorResponse
    AGENT_AVAILABLE = True
except ImportError as e:
    AGENT_AVAILABLE = False
    import_error_msg = str(e)

def initialize_state():
    if "agent_result" not in st.session_state:
        st.session_state.agent_result = None
    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages = []
    if "custom_prompt" not in st.session_state:
        st.session_state.custom_prompt = (
            "Please parse the candidate profile registered at [CV_PATH], "
            "search for 2 matching jobs, evaluate them, and return the comparisons."
        )
    if "jd_text" not in st.session_state:
        st.session_state.jd_text = (
            "### Senior Systems Engineer (Automotive)\n"
            "**Company:** AutoDrive Tech GmbH\n"
            "**Location:** Munich / Remote\n"
            "**Skills:** C++, Python, CANoe, Automotive Ethernet, ISO 26262"
        )
    if "registered_file_path" not in st.session_state:
        st.session_state.registered_file_path = ""

initialize_state()

def run_agent_pipeline(prompt: str):
    # Fix for Windows Asyncio Subprocess bugs
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    async def _run():
        return await execute_agent_prompt(prompt)
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(_run())
    else:
        return loop.run_until_complete(_run())

def render_exception(ex: Exception):
    """Prints the actual error traceback instead of just the TaskGroup wrapper."""
    st.error(" Agent Execution Failed")
    error_text = "".join(traceback.format_exception(type(ex), ex, ex.__traceback__))
    with st.expander(" View Full Error Details (Traceback)", expanded=True):
        st.code(error_text, language="python")


# ==========================================
# 3. SIDEBAR CONFIGURATIONS
# ==========================================
with st.sidebar:
    st.title("⚙️ Control Panel")
    
    if AGENT_AVAILABLE:
        st.success(" connected to Agent Session")
    else:
        st.error(" Agent Import Error")
        
    st.divider()
    
    st.subheader("🔍 Scraper Options")
    location_filter = st.text_input("Preferred Location", "Germany")
    max_jobs = st.slider("Max Job Postings to Search", 1, 5, 2)
    linkedin_fetch = st.checkbox("Fetch Full Descriptions", value=True)


# ==========================================
# 4. MAIN WORKSPACE / TABS
# ==========================================
st.title("🚗 Automotive Agentic Matching Portal")

if not AGENT_AVAILABLE:
    st.warning("Please ensure your `mcp_server.py`, `orchestrator.py`, and schemas are accessible.")
    st.stop()

tab_seeker, tab_hr, tab_sandbox = st.tabs([
    " Job Seeker Mode", 
    " HR Recruiter Mode", 
    " Direct Agent Workspace"
])

# --- TAB 1: JOB SEEKER MODE ---
with tab_seeker:
    st.subheader("Find Matching Positions for a Candidate")
    col1, col2 = st.columns([1, 2], gap="large")
    
    with col1:
        with st.container(border=True):
            st.markdown("#### Upload CV (PDF)")
            uploaded_cv = st.file_uploader("Select CV File:", type=["pdf"], key="seeker_cv_upload")
            search_keywords = st.text_input("Job Title / Target Keywords:", value="Automotive Software Engineer")
            search_constraints = st.text_area("Optional Details to Search:", value="", placeholder="e.g. 'Must focus on ISO 26262'", height=100)
            trigger_seeker = st.button("🚀 Find & Match Jobs", type="primary", use_container_width=True)

    with col2:
        if trigger_seeker:
            if not uploaded_cv:
                st.error("Please upload a CV document first.")
            else:
                with st.status("Running agentic pipeline...", expanded=True) as status:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(uploaded_cv.getvalue())
                        temp_cv_path = tmp_file.name
                    
                    custom_prompt = (
                        f"The candidate's CV is located locally at '{temp_cv_path}'.\n"
                        f"Please parse this candidate's CV.\n"
                        f"Run a live search for {max_jobs} matching jobs for '{search_keywords}' in '{location_filter}'.\n"
                    )
                    if search_constraints.strip():
                        custom_prompt += f"Filter/Prioritize postings containing: '{search_constraints}'.\n"
                    custom_prompt += "Evaluate the jobs, align requirements, and return structured evaluations."
                    
                    try:
                        result = run_agent_pipeline(custom_prompt)
                        st.session_state.agent_result = result.output
                        st.session_state.agent_messages = result.all_messages()
                        status.update(label="Matching Completed!", state="complete", expanded=False)
                    except Exception as ex:
                        render_exception(ex)
                        status.update(label="Processing Error", state="error")
                    finally:
                        if os.path.exists(temp_cv_path):
                            os.remove(temp_cv_path)

# --- TAB 2: HR RECRUITER MODE ---
with tab_hr:
    st.subheader("Match Candidate Profiles Against a Job Specification")
    col1, col2 = st.columns([1, 1], gap="large")
    
    with col1:
        with st.container(border=True):
            st.markdown("#### 1. Job Specification")
            jd_source = st.radio("Job Description Source:", ["Raw Text", "URL Link"])
            if jd_source == "Raw Text":
                jd_input = st.text_area("Paste Requirements:", value=st.session_state.jd_text, height=250)
                jd_url = ""
            else:
                jd_url = st.text_input("Job Posting URL:", value="https://example.com/job")
                jd_input = ""
            
    with col2:
        with st.container(border=True):
            st.markdown("#### 2. Applicants")
            uploaded_cvs = st.file_uploader("Upload CVs (PDF):", type=["pdf"], accept_multiple_files=True)
            
    st.divider()
    trigger_hr = st.button("⚖️ Run Comparative Engine", type="primary", use_container_width=True)
    
    if trigger_hr:
        if not uploaded_cvs:
            st.error("Please upload at least one candidate CV.")
        else:
            with st.status("Processing candidates...", expanded=True) as status:
                temp_paths = []
                for cv_file in uploaded_cvs:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(cv_file.getvalue())
                        temp_paths.append((cv_file.name, tmp_file.name))
                
                formatted_cv_list = "\n".join([f"- Candidate '{name}' at: '{path}'" for name, path in temp_paths])
                jd_instructions = f"--- JOB DESCRIPTION ---\n{jd_input}" if jd_source == "Raw Text" else f"Scrape requirements from: {jd_url}"
                
                hr_prompt = f"Match candidates against the Target Job.\n\n{jd_instructions}\n\n--- CANDIDATES ---\n{formatted_cv_list}\n\nReturn structured report."
                
                try:
                    result = run_agent_pipeline(hr_prompt)
                    st.session_state.agent_result = result.output
                    status.update(label="Evaluation Finished!", state="complete", expanded=False)
                except Exception as ex:
                    render_exception(ex)
                    status.update(label="Error processing", state="error")
                finally:
                    for _, path in temp_paths:
                        if os.path.exists(path):
                            os.remove(path)

# --- TAB 3: DIRECT AGENT WORKSPACE ---
with tab_sandbox:
    st.subheader("Agent Sandbox Console")
    col_input, col_prompt = st.columns([1, 1], gap="large")
    
    with col_input:
        with st.container(border=True):
            st.markdown("#### Environment Registration")
            reg_method = st.radio("File Selection:", ["Upload File", "Enter Local Path Manually"])
            
            if reg_method == "Upload File":
                uploaded_reg = st.file_uploader("Upload Profile PDF:", type=["pdf"])
                if uploaded_reg:
                    target_path = os.path.join(tempfile.gettempdir(), uploaded_reg.name)
                    with open(target_path, "wb") as f:
                        f.write(uploaded_reg.getvalue())
                    st.session_state.registered_file_path = target_path
                    st.success("File registered!")
            else:
                st.session_state.registered_file_path = st.text_input("Enter exact path:", value=st.session_state.registered_file_path)
                
    with col_prompt:
        with st.container(border=True):
            st.markdown("#### Custom Prompt")
            if st.session_state.registered_file_path and st.button("Inject Registered Path"):
                st.session_state.custom_prompt = f"Parse the CV at '{st.session_state.registered_file_path}'. Search for 2 jobs in Germany and evaluate them."
                st.rerun()
                
            user_prompt_input = st.text_area("Prompt:", value=st.session_state.custom_prompt, height=150)
            
    if st.button("⚡ Run Pipeline", type="primary", use_container_width=True):
        with st.status("Executing...", expanded=True) as status:
            try:
                result = run_agent_pipeline(user_prompt_input)
                st.session_state.agent_result = result.output
                status.update(label="Complete", state="complete")
            except Exception as ex:
                render_exception(ex)
                status.update(label="Error", state="error")

# ==========================================
# 5. RENDER AGENT RESULTS & LOGS
# ==========================================
if st.session_state.agent_result:
    st.divider()
    result_col, log_col = st.columns([3, 2], gap="large")
    
    with result_col:
        st.subheader("📊 Match Analysis Reports")
        st.info(st.session_state.agent_result.conversational_reply)
        
        if st.session_state.agent_result.ranked_results:
            st.markdown("###  Leaderboard")
            table_data = [{"Rank": f"#{i.rank}", "Score": f"{i.compatibility_score}/100", "Target": i.target_name, "Context": i.target_context} for i in st.session_state.agent_result.ranked_results]
            st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
            
            for item in st.session_state.agent_result.ranked_results:
                with st.expander(f"Rank #{item.rank}: {item.target_name} ({item.compatibility_score}/100)"):
                    st.write(f"**Context:** {item.target_context}")
                    sub1, sub2 = st.columns(2)
                    with sub1:
                        st.markdown("<p style='color:#00e676; font-weight:bold;'>🟢 Key Strengths</p>", unsafe_allow_html=True)
                        for s in item.key_strengths: st.markdown(f"- {s}")
                    with sub2:
                        st.markdown("<p style='color:#ff5252; font-weight:bold;'>🔴 Critical Gaps</p>", unsafe_allow_html=True)
                        for g in item.critical_gaps: st.markdown(f"- {g}")
                    st.write(item.executive_summary)
        
        if st.session_state.agent_result.recommended_next_steps:
            st.markdown("### Recommended Next Steps")
            for idx, step in enumerate(st.session_state.agent_result.recommended_next_steps):
                st.checkbox(step, key=f"step_{idx}")

    with log_col:
        st.subheader("Live Pipeline Log")

        messages = st.session_state.get("agent_messages", [])

        if not messages:
            st.caption("Tool calls will appear here after running the pipeline.")
        else:
            # ── Summary bar ──────────────────────────────────────────
            tool_calls = [
                part
                for msg in messages
                for part in getattr(msg, "parts", [])
                if part.__class__.__name__ == "ToolCallPart"
            ]
            tool_returns = [
                part
                for msg in messages
                for part in getattr(msg, "parts", [])
                if part.__class__.__name__ == "ToolReturnPart"
            ]
            st.info(f"🔧 **{len(tool_calls)} tool calls** tracked across this pipeline run.")

            # ── Per-step timeline ─────────────────────────────────────
            step = 0
            for msg in messages:
                parts = getattr(msg, "parts", [])
                for part in parts:
                    cls = part.__class__.__name__

                    if cls == "ToolCallPart":
                        step += 1
                        tool_name = getattr(part, "tool_name", "unknown")

                        # Pretty-print args
                        raw_args = getattr(part, "args", {})
                        if hasattr(raw_args, "args_dict"):
                            args_dict = raw_args.args_dict
                        elif isinstance(raw_args, dict):
                            args_dict = raw_args
                        else:
                            try:
                                args_dict = json.loads(str(raw_args))
                            except Exception:
                                args_dict = {"raw": str(raw_args)}

                        with st.expander(
                            f"**Step {step}** 🔧 `{tool_name}`", expanded=False
                        ):
                            st.markdown("**📥 Arguments:**")
                            st.json(args_dict)

                    elif cls == "ToolReturnPart":
                        tool_name = getattr(part, "tool_name", "unknown")
                        raw_content = getattr(part, "content", "")

                        # Try to parse as JSON for pretty display
                        try:
                            parsed = json.loads(str(raw_content))
                            display_content = json.dumps(parsed, indent=2)
                            is_json = True
                        except Exception:
                            display_content = str(raw_content)
                            is_json = False

                        # Truncate large payloads (e.g. ReferenceHandles are small, but raw scrapes can be huge)
                        truncated = False
                        if len(display_content) > 1500:
                            display_content = display_content[:1500]
                            truncated = True

                        with st.expander(
                            f"↳ ✅ `{tool_name}` — return", expanded=False
                        ):
                            st.markdown("**📤 Return value:**")
                            if is_json:
                                st.json(json.loads(display_content) if not truncated else display_content)
                            else:
                                st.code(display_content, language="json")
                            if truncated:
                                st.caption("⚠️ Output truncated to 1500 chars for display.")

                    elif cls == "TextPart":
                        # Show agent's reasoning/text steps collapsed
                        text = getattr(part, "content", "")
                        if text.strip():
                            with st.expander("💬 Agent reasoning", expanded=False):
                                st.markdown(text)

            # ── Raw subagent log (from mcp_subagents.log) ────────────
            if os.path.exists("mcp_subagents.log"):
                with st.expander("📄 Raw Sub-agent HTTP Log", expanded=False):
                    with open("mcp_subagents.log", "r", encoding="utf-8") as f:
                        log_data = f.read()
                    st.text_area(
                        "Sub-agent HTTP Calls:",
                        value=log_data[-6000:] if len(log_data) > 6000 else log_data,
                        height=300,
                        disabled=True
                    )


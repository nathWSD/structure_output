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
    from orchestrator import execute_agent_prompt
    from schemas import OrchestratorResponse
    AGENT_AVAILABLE = True
except ImportError as e:
    AGENT_AVAILABLE = False
    import_error_msg = str(e)

def initialize_state():
    # Isolated state parameters to prevent seekers and recruiters from mixing data
    if "seeker_result" not in st.session_state:
        st.session_state.seeker_result = None
    if "seeker_messages" not in st.session_state:
        st.session_state.seeker_messages = []
        
    if "hr_result" not in st.session_state:
        st.session_state.hr_result = None
    if "hr_messages" not in st.session_state:
        st.session_state.hr_messages = []
        
    if "jd_text" not in st.session_state:
        st.session_state.jd_text = (
            "### Senior Systems Engineer (Automotive)\n"
            "**Company:** AutoDrive Tech GmbH\n"
            "**Location:** Munich / Remote\n"
            "**Skills:** C++, Python, CANoe, Automotive Ethernet, ISO 26262"
        )

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

def clear_telemetry_files():
    """Purges stale telemetries so concurrent or consecutive runs do not overlap logs."""
    for filename in ["subagent_trace.json", "subagent_outputs.json", "mcp_subagents.log"]:
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                pass

# ==========================================
# 3. HELPER FUNCTION: RENDER PIPELINE RESULTS
# ==========================================
def render_results_section(result, messages, is_hr_mode=False):
    """
    Renders the rich dashboard layout of the Orchestrator results and live pipeline logs.
    """
    st.divider()
    result_col, log_col = st.columns([3, 2], gap="large")
    
    with result_col:
        st.subheader(" Match Analysis Reports")
        st.info(result.conversational_reply)
        
        if result.ranked_results:
            st.markdown("### 🏆 Leaderboard")
            
            # Construct a rich metadata table without score columns
            table_data = []
            for item in result.ranked_results:
                table_data.append({
                    "Rank": f"#{item.rank}",
                    "Position / Candidate": item.target_name,
                    "Company / Current Role": item.target_context,
                    "Location": getattr(item, "location", "Not Specified") or "Not Specified",
                    "Salary Range": getattr(item, "salary", "Not Specified") or "Not Specified",
                    "Job Type": getattr(item, "job_type", "Not Specified") or "Not Specified",
                    "Workplace Style": getattr(item, "workplace_type", "Not Specified") or "Not Specified",
                    "URL": getattr(item, "source_url", "") or ""
                })
            
            # Display rich leaderboard with clickable LinkColumn for the URL
            st.dataframe(
                pd.DataFrame(table_data), 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "URL": st.column_config.LinkColumn("Source Link", display_text="Open Posting")
                }
            )
            
            # ── 📊 COMPATIBILITY VISUAL COMPARISON PLOTS (RADAR / SPIDER CHARTS) ──────
            st.markdown("### 📊 Attribute Coverage Analytics")
            
            label_mapping = {
                "must_have": "Must-Haves",
                "experience": "Seniority/Exp",
                "domain": "Domain Align",
                "toolchain": "Toolchain",
                "nice_to_have": "Nice-to-Haves",
                "standards": "Standards/Safety",
                "responsibilities": "Responsibilities"
            }
            
            # Check if radar data is present
            has_radar_data = any(
                getattr(item, "dimension_scores", None) is not None 
                for item in result.ranked_results
            )
            
            if has_radar_data:
                try:
                    import plotly.graph_objects as go
                    
                    if is_hr_mode:
                        # HR recruiter Mode: Standalone radar charts rendered side-by-side in a horizontal scrollable zone
                        st.caption("Individual candidate attribute profiles mapped against target requirements:")
                        html_charts = []
                        for item in result.ranked_results:
                            if item.dimension_scores:
                                categories = [label_mapping.get(k, k.replace('_', ' ').title()) for k in item.dimension_scores.keys()]
                                scores = list(item.dimension_scores.values())
                                
                                categories_closed = categories + [categories[0]]
                                scores_closed = scores + [scores[0]]
                                
                                fig = go.Figure()
                                fig.add_trace(go.Scatterpolar(
                                    r=scores_closed,
                                    theta=categories_closed,
                                    fill='toself',
                                    name=item.target_name,
                                    hovertemplate="%{theta}: %{r}/100"
                                ))
                                fig.update_layout(
                                    title=dict(
                                        text=f"Candidate Profile: {item.target_name}",
                                        font=dict(size=13, family="sans-serif")
                                    ),
                                    polar=dict(
                                        radialaxis=dict(
                                            visible=True,
                                            range=[0, 100],
                                            gridcolor="rgba(128, 128, 128, 0.15)",
                                            tickfont=dict(size=9)
                                        ),
                                        angularaxis=dict(
                                            gridcolor="rgba(128, 128, 128, 0.15)",
                                            tickfont=dict(size=10)
                                        ),
                                        bgcolor="rgba(0,0,0,0)"
                                    ),
                                    margin=dict(l=40, r=40, t=40, b=40),
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    height=340,
                                    showlegend=False
                                )
                                # Convert Plotly Figure directly into an independent inline HTML block
                                chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
                                html_charts.append(f"<div class='horizontal-scroll-item'>{chart_html}</div>")
                        
                        if html_charts:
                            # Render the dynamic horizontal flexbox container using Streamlit HTML component
                            scroll_container_html = f"""
                            <div class="horizontal-scroll-container">
                                {"".join(html_charts)}
                            </div>
                            <style>
                                .horizontal-scroll-container {{
                                    display: flex;
                                    overflow-x: auto;
                                    gap: 16px;
                                    padding: 10px;
                                    border: 1px solid rgba(128, 128, 128, 0.15);
                                    border-radius: 8px;
                                    background-color: rgba(255, 255, 255, 0.02);
                                }}
                                .horizontal-scroll-item {{
                                    flex: 0 0 350px;
                                    min-width: 350px;
                                    height: 350px;
                                }}
                            </style>
                            """
                            st.components.v1.html(scroll_container_html, height=380, scrolling=False)
                    else:
                        # Job Seeker Mode: Plot multiple matched jobs on 1 comparative chart
                        fig = go.Figure()
                        for item in result.ranked_results:
                            if item.dimension_scores:
                                categories = [label_mapping.get(k, k.replace('_', ' ').title()) for k in item.dimension_scores.keys()]
                                scores = list(item.dimension_scores.values())
                                
                                categories_closed = categories + [categories[0]]
                                scores_closed = scores + [scores[0]]
                                
                                fig.add_trace(go.Scatterpolar(
                                    r=scores_closed,
                                    theta=categories_closed,
                                    fill='toself',
                                    name=f"{item.target_name} ({item.target_context})",
                                    hovertemplate="%{theta}: %{r}/100"
                                ))
                        
                        fig.update_layout(
                            polar=dict(
                                radialaxis=dict(
                                    visible=True,
                                    range=[0, 100],
                                    gridcolor="rgba(128, 128, 128, 0.2)",
                                    tickfont=dict(size=10)
                                ),
                                angularaxis=dict(
                                    gridcolor="rgba(128, 128, 128, 0.2)",
                                    tickfont=dict(size=11)
                                ),
                                bgcolor="rgba(0,0,0,0)"
                            ),
                            showlegend=True,
                            margin=dict(l=60, r=60, t=40, b=40),
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
                        )
                        st.plotly_chart(fig, use_container_width=True, key="radar_seeker_unified")
                        
                except ImportError:
                    st.warning("Please run `pip install plotly` to enable radar visualizations.")
            # ────────────────────────────────────────────────────────────────────────
            
            st.markdown("### 🔍 Detail Analysis per Evaluation Point")
            for item in result.ranked_results:
                with st.expander(f"Rank #{item.rank}: {item.target_name} ({item.target_context})"):
                    st.write(f"**Context:** {item.target_context}")
                    
                    # Display metadata summary cards inside the expander
                    metadata_cols = st.columns(4)
                    with metadata_cols[0]:
                        st.write(f"**📍 Location:** {getattr(item, 'location', 'N/A') or 'N/A'}")
                    with metadata_cols[1]:
                        st.write(f"**💼 Workplace:** {getattr(item, 'workplace_type', 'N/A') or 'N/A'}")
                    with metadata_cols[2]:
                        st.write(f"**🕒 Job Type:** {getattr(item, 'job_type', 'N/A') or 'N/A'}")
                    with metadata_cols[3]:
                        st.write(f"**💰 Salary:** {getattr(item, 'salary', 'N/A') or 'N/A'}")
                    
                    sub1, sub2 = st.columns(2)
                    with sub1:
                        st.markdown("<p style='color:#00e676; font-weight:bold;'>🟢 Key Strengths</p>", unsafe_allow_html=True)
                        for s in item.key_strengths: st.markdown(f"- {s}")
                    with sub2:
                        st.markdown("<p style='color:#ff5252; font-weight:bold;'>🔴 Critical Gaps</p>", unsafe_allow_html=True)
                        for g in item.critical_gaps: st.markdown(f"- {g}")
                    st.write(item.executive_summary)
        
        if result.recommended_next_steps:
            st.markdown("### 📋 Recommended Next Steps")
            for step in result.recommended_next_steps:
                st.markdown(f"- {step}")

    with log_col:
        st.subheader(" Pipeline Telemetry")
        
        # Configure segmented logging tabs for unified transparency
        log_tab_orch, log_tab_sub, log_tab_outputs = st.tabs([
            "💬 Orchestrator", 
            "⚡ Sub-agents Trace", 
            "📦 Structured Artifacts"
        ])
        
        # TAB 1: Main Orchestrator Steps
        with log_tab_orch:
            if not messages:
                st.caption("Tool calls will appear here after running.")
            else:
                tool_calls = [
                    part
                    for msg in messages
                    for part in getattr(msg, "parts", [])
                    if part.__class__.__name__ == "ToolCallPart"
                ]
                st.info(f" **{len(tool_calls)} tool calls** tracked across this orchestrator run.")

                step = 0
                for msg in messages:
                    parts = getattr(msg, "parts", [])
                    for part in parts:
                        cls = part.__class__.__name__

                        if cls == "ToolCallPart":
                            step += 1
                            tool_name = getattr(part, "tool_name", "unknown")
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

                            with st.expander(f"**Step {step}** 🔧 `{tool_name}`", expanded=False):
                                st.markdown("**📥 Arguments:**")
                                st.json(args_dict)

                        elif cls == "ToolReturnPart":
                            tool_name = getattr(part, "tool_name", "unknown")
                            raw_content = getattr(part, "content", "")
                            try:
                                parsed = json.loads(str(raw_content))
                                display_content = json.dumps(parsed, indent=2)
                                is_json = True
                            except Exception:
                                display_content = str(raw_content)
                                is_json = False

                            truncated = False
                            if len(display_content) > 1500:
                                display_content = display_content[:1500]
                                truncated = True

                            with st.expander(f"↳  `{tool_name}` — return", expanded=False):
                                st.markdown("**📤 Return value:**")
                                if is_json:
                                    st.json(json.loads(display_content) if not truncated else display_content)
                                else:
                                    st.code(display_content, language="json")
                                if truncated:
                                    st.caption("⚠️ Output truncated to 1500 chars for display.")

                        elif cls == "TextPart":
                            text = getattr(part, "content", "")
                            if text.strip():
                                with st.expander("💬 Agent reasoning", expanded=False):
                                    st.markdown(text)

        # TAB 2: Sub-Agent Interactive Log Trace
        with log_tab_sub:
            if not os.path.exists("subagent_trace.json"):
                st.caption("No sub-agent execution trace records found.")
            else:
                try:
                    with open("subagent_trace.json", "r", encoding="utf-8") as f:
                        traces = json.load(f)
                    
                    st.info(f"Captured **{len(traces)} specialized agent executions**:")
                    for idx, trace_record in enumerate(traces):
                        sub_name = trace_record.get("subagent", "Unknown Sub-agent")
                        sub_messages = trace_record.get("messages", [])
                        
                        with st.expander(f"⚙️ [{idx+1}] {sub_name}", expanded=False):
                            step_idx = 0
                            for m in sub_messages:
                                parts = m.get("parts", [])
                                for p in parts:
                                    kind = p.get("part_kind") or p.get("type") or ""
                                    
                                    # Sub-Agent Tool Executions
                                    if "tool-call" in kind or "ToolCall" in kind or p.get("tool_name"):
                                        step_idx += 1
                                        st.markdown(f"**Step {step_idx}** 🛠️ `{p.get('tool_name')}`")
                                        st.json(p.get("args", {}))
                                        
                                    # Sub-Agent Tool Returns
                                    elif "tool-return" in kind or "ToolReturn" in kind or p.get("content"):
                                        st.markdown(f"↳ `{p.get('tool_name')}` — returned")
                                        content_val = p.get("content", "")
                                        try:
                                            st.json(json.loads(str(content_val)))
                                        except Exception:
                                            st.code(str(content_val)[:1000], language="text")
                                            
                                    # Sub-Agent Thoughts
                                    elif "text" in kind or "Text" in kind or p.get("content"):
                                        reasoning = p.get("content", "")
                                        if reasoning.strip():
                                            st.caption("💭 Sub-agent thought reasoning:")
                                            st.markdown(reasoning)
                except Exception as telemetry_err:
                    st.error(f"Failed to load sub-agent telemetry: {str(telemetry_err)}")

        # TAB 3: Structured Final Intermediate Models
        with log_tab_outputs:
            if not os.path.exists("subagent_outputs.json"):
                st.caption("No sub-agent parsed output targets found.")
            else:
                try:
                    with open("subagent_outputs.json", "r", encoding="utf-8") as f:
                        outputs_payloads = json.load(f)
                    
                    for subagent_group, items in outputs_payloads.items():
                        st.markdown(f"#### 📁 {subagent_group}")
                        for item_key, payload_body in items.items():
                            with st.expander(f"📦 {item_key}", expanded=False):
                                st.json(payload_body)
                except Exception as outputs_err:
                    st.error(f"Failed to load structured outputs: {str(outputs_err)}")

        # Optional HTTP debugger log file
        if os.path.exists("mcp_subagents.log"):
            with st.expander(" Raw Sub-agent HTTP Log", expanded=False):
                with open("mcp_subagents.log", "r", encoding="utf-8") as f:
                    log_data = f.read()
                st.text_area(
                    "Sub-agent HTTP Calls:",
                    value=log_data[-6000:] if len(log_data) > 6000 else log_data,
                    height=300,
                    disabled=True,
                    key=f"subagent_log_area_{is_hr_mode}"
                )


# ==========================================
# 4. MAIN WORKSPACE / TABS
# ==========================================
st.title("🚗 Automotive Agentic Matching Portal")

if not AGENT_AVAILABLE:
    st.warning("Please ensure your `mcp_server.py`, `orchestrator.py`, and schemas are accessible.")
    st.stop()

# Tab setup: Strictly keeping seeker and recruiter modes as requested
tab_seeker, tab_hr = st.tabs([
    " Job Seeker Mode", 
    " HR Recruiter Mode"
])

# --- TAB 1: JOB SEEKER MODE ---
with tab_seeker:
    st.subheader("Find Matching Positions for a Candidate")
    col1, col2 = st.columns([1, 2], gap="large")
    
    with col1:
        with st.container(border=True):
            st.markdown("#### Upload CV (PDF)")
            uploaded_cv = st.file_uploader("Select CV File:", type=["pdf"], key="seeker_cv_upload")
            search_keywords = st.text_input("Job Title / Target Keywords:", value="Automotive Software Engineer", key="seeker_keywords")
            search_constraints = st.text_area("Optional Details to Search:", value="", placeholder="e.g. 'Must focus on ISO 26262'", height=100, key="seeker_constraints")
            trigger_seeker = st.button(" Find & Match Jobs", type="primary", use_container_width=True, key="seeker_trigger")

    with col2:
        if trigger_seeker:
            if not uploaded_cv:
                st.error("Please upload a CV document first.")
            else:
                clear_telemetry_files() # Call before running pipeline
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
                        st.session_state.seeker_result = result.output
                        st.session_state.seeker_messages = result.all_messages()
                        status.update(label="Matching Completed!", state="complete", expanded=False)
                    except Exception as ex:
                        render_exception(ex)
                        status.update(label="Processing Error", state="error")
                    finally:
                        if os.path.exists(temp_cv_path):
                            os.remove(temp_cv_path)

    # Render Seeker results inside Seeker tab directly
    if st.session_state.seeker_result:
        render_results_section(
            st.session_state.seeker_result, 
            st.session_state.seeker_messages, 
            is_hr_mode=False
        )

# --- TAB 2: HR RECRUITER MODE ---
with tab_hr:
    st.subheader("Match Candidate Profiles Against a Job Specification")
    col1, col2 = st.columns([1, 1], gap="large")
    
    with col1:
        with st.container(border=True):
            st.markdown("#### 1. Job Specification")
            jd_source = st.radio("Job Description Source:", ["Raw Text", "URL Link"], key="hr_jd_source")
            if jd_source == "Raw Text":
                jd_input = st.text_area("Paste Requirements:", value=st.session_state.jd_text, height=250, key="hr_jd_input")
                jd_url = ""
            else:
                jd_url = st.text_input("Job Posting URL:", value="https://example.com/job", key="hr_jd_url")
                jd_input = ""
            
    with col2:
        with st.container(border=True):
            st.markdown("#### 2. Applicants")
            uploaded_cvs = st.file_uploader("Upload CVs (PDF):", type=["pdf"], accept_multiple_files=True, key="hr_cv_upload")
            
    st.divider()
    trigger_hr = st.button("⚖️ Run Comparative Engine", type="primary", use_container_width=True, key="hr_trigger")
    
    if trigger_hr:
        if not uploaded_cvs:
            st.error("Please upload at least one candidate CV.")
        else:
            clear_telemetry_files() # Call before running pipeline
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
                    st.session_state.hr_result = result.output
                    st.session_state.hr_messages = result.all_messages()
                    status.update(label="Evaluation Finished!", state="complete", expanded=False)
                except Exception as ex:
                    render_exception(ex)
                    status.update(label="Error processing", state="error")
                finally:
                    for _, path in temp_paths:
                        if os.path.exists(path):
                            os.remove(path)

    # Render HR Recruiter results inside HR tab directly
    if st.session_state.hr_result:
        render_results_section(
            st.session_state.hr_result, 
            st.session_state.hr_messages, 
            is_hr_mode=True
        )
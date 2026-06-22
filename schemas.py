"""
schemas.py
Centralized Pydantic schemas defining the structured inputs and outputs
for the three specialized sub-agents.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class ReferenceHandle(BaseModel):
    ref_id: str = Field(
        description="The unique, universal pointer referencing this data object inside the MCP environment."
    )
    data_type: str = Field(
        description="The classification of the payload (e.g., 'raw_pdf_text', 'scraped_jobs', 'structured_cv', 'match_report')."
    )
    size_indicator: str = Field(
        description="A size metric (e.g., character count, item count, or token estimate) to inform the agent's planning."
    )
    summary: str = Field(
        description="A lightweight, 1-sentence semantic summary of the referenced content."
    )

# =====================================================================
# 1. CV Extraction Schemas
# =====================================================================
#TODO prompts in mlflow should be stored 
class TechnicalSkills(BaseModel):
    embedded_firmware: List[str] = Field(
        default_factory=list, 
        description="Low-level firmware, RTOS, bare-metal C/C++, microcontrollers (e.g., STM32, Aurix)."
    )
    high_level_software: List[str] = Field(
        default_factory=list, 
        description="High-level languages and systems (e.g., Python, Java, Go, TypeScript)."
    )
    vehicle_networks: List[str] = Field(
        default_factory=list, 
        description="Automotive networks and protocols (e.g., CAN, CAN-FD, LIN, FlexRay, Ethernet)."
    )
    toolchains_and_validation: List[str] = Field(
        default_factory=list, 
        description="Engineering toolchains (e.g., Vector CANoe, CANalyzer, dSPACE HIL, Lauterbach)."
    )
    standards_and_compliance: List[str] = Field(
        default_factory=list, 
        description="Standards, safety levels, and frameworks (e.g., ISO 26262, MISRA C, ASPICE, AUTOSAR)."
    )
    cloud_and_telematics: List[str] = Field(
        default_factory=list, 
        description="Edge and cloud services (e.g., AWS IoT Core, MQTT, Docker, Kubernetes)."
    )


class ProjectExperience(BaseModel):
    project_name: str = Field(default_factory=str, description="Name or logical title of the project or professional role.")
    duration_months: Optional[int] = Field(None, description="Duration of the project in months if specified.")
    tools_used: List[str] = Field(default_factory=list, description="Specific toolchains applied during this project.")
    contribution: str = Field(default_factory=str, description="The candidate's concrete engineering contribution and responsibilities.")

class EducationEntry(BaseModel):
    degree_level: str = Field(default_factory=str, description="Degree level such as Bachelor, Master, PhD.")
    field_of_study: Optional[str] = Field(default_factory=str, description="Major or specialization.")
    institution: Optional[str] = Field(default_factory=str, description="University or institution name.")
    country: Optional[str] = Field(default_factory=str, description="Country where the degree was obtained.")
    graduation_year: Optional[int] = Field(None, description="Year of graduation if available.")


class CVExtractionOutput(BaseModel):
    candidate_name: str = Field(default_factory=str, description="The full name of the candidate.")
    education: List[EducationEntry] = Field(default_factory=list,description="List of academic degrees with structured fields.")
    years_of_experience: float = Field(default_factory=0, description="The calculated total years of active professional experience.")
    categorized_skills: TechnicalSkills = Field(default_factory=TechnicalSkills, description="Structured categorization of the candidate's engineering skills.")
    projects: List[ProjectExperience] = Field(default_factory=list, description="Chronological project history and roles.")


# =====================================================================
# 2. Job Description Extraction Schemas
# =====================================================================

class JDRequirements(BaseModel):
    must_have: List[str] = Field(
        description="Hard, non-negotiable technical and experience requirements. If none are found, return an empty list []."
    )
    nice_to_have: List[str] = Field(
        description="Soft, optional toolchain preferences or preferred qualifications. If none are found, return an empty list []."
    )

class CVRawDataInput(BaseModel):
    pdf_path: str = Field(description="The local filesystem path to the candidate's CV PDF.")
    scenario: str = Field(description="A capital letter A or B indicating which scenerio we are working on")

class JDRawDataInput(BaseModel):
    title: str = Field(description="The job title from the job board posting.")
    company: str = Field(description="The company offering the job position.")
    location: str = Field(description="The physical location of the job (e.g., 'Berlin', 'Remote').")
    description: str = Field(description="The raw full-text description containing details and requirements.")
    url: str = Field(description="The original web URL pointing to the job posting.")

class ExperienceInfo(BaseModel):
    years_of_experience: str = Field(
        description="Explicit or inferred years of experience required. Examples: '0-1', '2+', '3-5', '5-7'. If not stated or cannot be inferred, return an empty string ''."
    )
    experience_level: str = Field(
        description="Categorized seniority level inferred. One of: 'Fresher', 'Junior', 'Experienced', 'Senior', 'Lead'. If not inferable, return an empty string ''."
    )

class JDExtractionOutput(BaseModel):
    job_title: str = Field(description="The official corporate title of the position.")
    target_domain: str = Field(description="The matching main domain (e.g., 'Vehicle_Tech_and_Software_Defined_Vehicles').")
    
    required_toolchains: List[str] = Field(
        description="Specified design, test, and validation software tools needed. If none are specified, return an empty list []."
    )
    compliance_and_standards: List[str] = Field(
        description="Required safety, validation, and process standards (e.g., ISO 26262, ASPICE). If none are specified, return an empty list []."
    )
    responsibilities: List[str] = Field(
        description="Core day-to-day activities and responsibilities. If none are specified, return an empty list []."
    )
    
    requirements: JDRequirements = Field(
        description="Isolated must-have and nice-to-have criteria. Both sub-fields must be populated, using [] if empty."
    )
    salary_range: str = Field(
        description="The offered salary range or specific figure if provided. If not specified, return 'Not Specified'."
    )
    experience: ExperienceInfo = Field(
        description="Structured extraction of required experience level and years. Both sub-fields must be populated, using '' if empty."
    )
    source_url: Optional[str] = Field(default=None, description="The job posting URL.")
    location: Optional[str] = Field(default=None, description="The physical job location.")
    job_type: Optional[str] = Field(default=None, description="e.g., Full-time, Contract.")
    workplace_type: Optional[str] = Field(default=None, description="e.g., Remote, Hybrid.")

# =====================================================================
# 3. Matcher Schemas
# =====================================================================

class MatchInput(BaseModel):
    cv_data: CVExtractionOutput = Field(description="The structured candidate profile extracted by the CV details agent.")
    jd_data: JDExtractionOutput = Field(description="The structured job requirements extracted by the JD agent.")


class ScoringDefinition(BaseModel):
    category: str = Field(description="Name of the scoring category.")
    weight: int = Field(description="Maximum points allocated to this category.")
    description: str = Field(description="What this category measures and why it matters.")
    evaluation_criteria: List[str] = Field(
        description="Rules the matcher uses to assign points in this category."
    )

class ScoringFramework(BaseModel):
    must_have: ScoringDefinition
    experience: ScoringDefinition
    domain: ScoringDefinition
    toolchain: ScoringDefinition
    nice_to_have: ScoringDefinition
    standards: ScoringDefinition
    responsibilities: ScoringDefinition

SCORING_HIERARCHY = ScoringFramework(
    must_have=ScoringDefinition(
        category="must_have",
        weight=40,
        description="Hard, non-negotiable requirements. Missing one significantly reduces match quality.",
        evaluation_criteria=[
            "Award points proportionally based on matched must-have skills.",
            "Missing any must-have skill reduces score sharply.",
            "Each must-have contributes weight/len(must_haves) points."
        ]
    ),
    experience=ScoringDefinition(
        category="experience",
        weight=25,
        description="Years of experience and seniority alignment with the job description.",
        evaluation_criteria=[
            "Full points if candidate meets or exceeds required years.",
            "Partial points if candidate is below requirement.",
            "Subtract points if seniority level mismatches (e.g., JD=Senior, CV=Junior)."
        ]
    ),
    domain=ScoringDefinition(
        category="domain",
        weight=15,
        description="How well the candidate's background matches the job's technical domain.",
        evaluation_criteria=[
            "Full points for exact domain match.",
            "Partial points for related domain.",
            "Zero points for unrelated domain."
        ]
    ),
    toolchain=ScoringDefinition(
        category="toolchain",
        weight=10,
        description="Specific tools, frameworks, and technologies required for the role.",
        evaluation_criteria=[
            "Award points based on matched toolchains.",
            "Missing critical tools reduces score.",
            "Overlaps with must-have but more granular."
        ]
    ),
    nice_to_have=ScoringDefinition(
        category="nice_to_have",
        weight=5,
        description="Optional skills that improve match quality but are not required.",
        evaluation_criteria=[
            "Award small bonus for matched optional skills.",
            "No penalty for missing them."
        ]
    ),
    standards=ScoringDefinition(
        category="standards",
        weight=5,
        description="Industry standards and compliance frameworks relevant to the role.",
        evaluation_criteria=[
            "Award points for matched standards (ISO 26262, ASPICE, AUTOSAR).",
            "Partial points if only some standards match."
        ]
    ),
    responsibilities=ScoringDefinition(
        category="responsibilities",
        weight=5,
        description="Alignment between candidate's past responsibilities and job expectations.",
        evaluation_criteria=[
            "Award points for similar responsibilities.",
            "Partial points for partial overlap.",
            "Zero points if responsibilities differ significantly."
        ]
    )
)

class ScoreComponent(BaseModel):
    weight: int = Field(description="Maximum points allocated to this category.")
    score: int = Field(description="Points awarded based on candidate–JD alignment.")
    matched_items: List[str] = Field(
        default_factory=list,
        description="Items that contributed positively to the score."
    )
    missing_items: List[str] = Field(
        default_factory=list,
        description="Items that reduced the score."
    )
    justification: str = Field(
        description="Short explanation of why this score was assigned."
    )

class ScoreBreakdown(BaseModel):
    must_have: ScoreComponent
    experience: ScoreComponent
    domain: ScoreComponent
    toolchain: ScoreComponent
    nice_to_have: ScoreComponent
    standards: ScoreComponent
    responsibilities: ScoreComponent

class MatchOutput(BaseModel):
    score_breakdown: ScoreBreakdown = Field(
        description="Transparent scoring across all weighted categories, including matched/missing items and per-category justification."
    )
    matched_skills: List[str] = Field(
        description="All skills, tools, standards, and experiences from the CV that matched the JD."
    )
    missing_critical_skills: List[str] = Field(
        description="Must-have or critical requirements the candidate does not satisfy."
    )
    missing_soft_skills: List[str] = Field(
        description="Optional nice-to-have requirements the candidate does not satisfy."
    )
    source_url: Optional[str] = Field(default=None, description="The job posting URL.")
    location: Optional[str] = Field(default=None, description="The physical job location.")
    job_type: Optional[str] = Field(default=None, description="e.g., Full-time, Contract.")
    workplace_type: Optional[str] = Field(default=None, description="e.g., Remote, Hybrid.")
    salary: Optional[str] = Field(default=None, description="The extracted salary.")

# =====================================================================
# 5. Orchestrator (User-Facing) Output Schemas
# =====================================================================

class RankedMatch(BaseModel):
    #rank: int = Field(description="The placement rank (1 being the best match).")
    target_name: str = Field(description="The Job Title according to the job description either the role the individual is to occupy. ")
    target_context: str = Field(description="The Company's Name in the job description or in the context of the description.")
    compatibility_score: int = Field(description="The overall match score out of 100.")
    key_strengths: List[str] = Field(description="2-3 bullet points on why this is a good match.")
    critical_gaps: List[str] = Field(description="Major missing requirements or toolchains (if any).")
    executive_summary: str = Field(description="A 1-2 sentence final verdict on this match.")
    dimension_scores: Optional[Dict[str, int]] = Field(
        default=None, 
        description=(
            "Granular dimension scores out of 100 representing coverage of requirements. "
            "Keys must include: 'must_have', 'experience', 'domain', 'toolchain', 'nice_to_have', 'standards', 'responsibilities'."
        )
    )
    source_url: Optional[str] = Field(None, description="The original web URL pointing to the job posting.")
    salary: Optional[str] = Field(None, description="The extracted salary range or figure (e.g. 'Not Specified' or '$110,000').")
    location: Optional[str] = Field(None, description="The physical location of the job (e.g. 'Berlin / Hybrid').")
    job_type: Optional[str] = Field(None, description="The job arrangement (e.g. 'Full-time', 'Contract').")
    workplace_type: Optional[str] = Field(None, description="The workplace type (e.g. 'Remote', 'On-site', 'Hybrid').")

    
class OrchestratorResponse(BaseModel):
    conversational_reply: str = Field(
        description="A professional, natural language response speaking directly to the user."
    )
    ranked_results: Optional[List[RankedMatch]] = Field(
        default=None, 
        description="A sorted list of matched jobs or candidates, ordered highest score to lowest."
    )
    recommended_next_steps: List[str] = Field(
        default_factory=list,
        description="Suggested next actions for the user (e.g., 'Apply for Role 1', 'Upload another CV')."
    )

# ======================================================= 
# Judge schema 
#========================================================

class FieldVerdict(BaseModel):
    is_correct: int = Field(
        ..., 
        description="Assign 1 if correct (semantically identical, no contradictions), 0 if incorrect or missing."
    )
    explanation: str = Field(
        ..., 
        description="Detailed logical explanation of why this verdict was assigned based on the source text."
    )

# --- PIPELINE 1: JD Judge Schemas ---
class JDVerdict(BaseModel):
    job_title: FieldVerdict
    target_domain: FieldVerdict
    required_toolchains: FieldVerdict
    compliance_and_standards: FieldVerdict
    responsibilities: FieldVerdict
    requirements: FieldVerdict
    salary_range: FieldVerdict
    experience: FieldVerdict

class JDJudgeResponse(BaseModel):
    score: float = Field(..., description="Overall truthfulness score representing the ratio of correct fields.")
    explanation: str = Field(..., description="General summary explanation of the extraction correctness.")
    verdicts: JDVerdict

# --- PIPELINE 2: CV Judge Schemas ---
class CVVerdict(BaseModel):
    candidate_name: FieldVerdict
    education: FieldVerdict
    years_of_experience: FieldVerdict
    categorized_skills: FieldVerdict
    projects: FieldVerdict

class CVJudgeResponse(BaseModel):
    score: float = Field(..., description="Overall truthfulness score representing the ratio of correct fields.")
    explanation: str = Field(..., description="General summary explanation of the extraction correctness.")
    verdicts: CVVerdict

# --- PIPELINE 3: Matcher Judge Schemas ---
class MatcherVerdict(BaseModel):
    score_breakdown: FieldVerdict
    matched_skills: FieldVerdict
    missing_critical_skills: FieldVerdict
    missing_soft_skills: FieldVerdict

class MatcherJudgeResponse(BaseModel):
    score: float = Field(..., description="Overall alignment evaluation score matching the correctness of criteria scoring.")
    explanation: str = Field(..., description="General summary explanation of the candidate evaluation correctness.")
    verdicts: MatcherVerdict
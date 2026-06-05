"""
schemas.py
Centralized Pydantic schemas defining the structured inputs and outputs
for the three specialized sub-agents.
"""

from pydantic import BaseModel, Field
from typing import List, Optional

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
    project_name: str = Field(description="Name or logical title of the project or professional role.")
    duration_months: Optional[int] = Field(None, description="Duration of the project in months if specified.")
    tools_used: List[str] = Field(default_factory=list, description="Specific toolchains applied during this project.")
    contribution: str = Field(description="The candidate's concrete engineering contribution and responsibilities.")

class EducationEntry(BaseModel):
    degree_level: str = Field(description="Degree level such as Bachelor, Master, PhD.")
    field_of_study: Optional[str] = Field(None, description="Major or specialization.")
    institution: Optional[str] = Field(None, description="University or institution name.")
    country: Optional[str] = Field(None, description="Country where the degree was obtained.")
    graduation_year: Optional[int] = Field(None, description="Year of graduation if available.")


class CVExtractionOutput(BaseModel):
    candidate_name: str = Field(description="The full name of the candidate.")
    education: List[EducationEntry] = Field(default_factory=list,description="List of academic degrees with structured fields.")
    years_of_experience: float = Field(description="The calculated total years of active professional experience.")
    categorized_skills: TechnicalSkills = Field(description="Structured categorization of the candidate's engineering skills.")
    projects: List[ProjectExperience] = Field(default_factory=list, description="Chronological project history and roles.")


# =====================================================================
# 2. Job Description Extraction Schemas
# =====================================================================

class JDRequirements(BaseModel):
    must_have: List[str] = Field(description="Hard, non-negotiable technical and experience requirements.")
    nice_to_have: List[str] = Field(description="Soft, optional toolchain preferences or preferred qualifications.")

class CVRawDataInput(BaseModel):
    pdf_path: str = Field(description="The local filesystem path to the candidate's CV PDF.")

class JDRawDataInput(BaseModel):
    title: str = Field(description="The job title from the job board posting.")
    company: str = Field(description="The company offering the job position.")
    location: str = Field(description="The physical location of the job (e.g., 'Berlin', 'Remote').")
    description: str = Field(description="The raw full-text description containing details and requirements.")
    url: str = Field(description="The original web URL pointing to the job posting.")

class ExperienceInfo(BaseModel):
    years_of_experience: str = Field(description=("Explicit or inferred years of experience required.Examples: '0-1', '2+', '3-5', '5-7'. If not stated or cannot be inferred, return 'None'."))
    experience_level: str = Field(description=("Categorized seniority level inferred from the job description. One of: 'Fresher', 'Junior', 'Experienced', 'Senior', 'Lead'. If not inferable, return 'None'."))

class JDExtractionOutput(BaseModel):
    job_title: str = Field(description="The official corporate title of the position.")
    target_domain: str = Field(description="The matching main domain (e.g., 'Vehicle_Tech_and_Software_Defined_Vehicles').")
    required_toolchains: List[str] = Field(description="Specified design, test, and validation software tools needed.")
    compliance_and_standards: List[str] = Field(description="Required safety, validation, and process standards (e.g., ISO 26262, ASPICE).")
    responsibilities: List[str] = Field(description="Core day-to-day activities and responsibilities.")
    requirements: JDRequirements = Field(description="Isolated must-have and nice-to-have criteria.")
    salary_range: str = Field(description="The offered salary range or specific figure if provided else 'Not Specified'.")
    experience: ExperienceInfo = Field(description="Structured extraction of required experience level and years.")

# =====================================================================
# 3. Matcher Schemas
# =====================================================================

class MatchInput(BaseModel):
    cv_data: CVExtractionOutput = Field(description="The structured candidate profile extracted by the CV details agent.")
    jd_data: JDExtractionOutput = Field(description="The structured job requirements extracted by the JD agent.")


class MatchOutput(BaseModel):
    compatibility_score: int = Field(description="Overall compatibility score from 0 to 100 reflecting requirements intersection.")
    matched_skills: List[str] = Field(description="List of candidate skills and tools that align directly with the JD.")
    missing_critical_skills: List[str] = Field(description="Missing must-have requirements or critical toolchain experience.")
    missing_soft_skills: List[str] = Field(description="Optional nice-to-have requirements that the candidate does not satisfy.")
    detailed_justification: str = Field(description="Detailed, engineering-grounded justification explaining the matching quality and gaps.")

# =====================================================================
# 5. Orchestrator (User-Facing) Output Schemas
# =====================================================================

class RankedMatch(BaseModel):
    rank: int = Field(description="The placement rank (1 being the best match).")
    target_name: str = Field(description="The Job Title (if finding jobs) or Candidate Name (if finding candidates).")
    target_context: str = Field(description="The Company Name or Candidate's Current Role.")
    compatibility_score: int = Field(description="The overall match score out of 100.")
    key_strengths: List[str] = Field(description="2-3 bullet points on why this is a good match.")
    critical_gaps: List[str] = Field(description="Major missing requirements or toolchains (if any).")
    executive_summary: str = Field(description="A 1-2 sentence final verdict on this match.")

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
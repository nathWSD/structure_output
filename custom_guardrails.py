import os
import json
import sys
from typing import Callable, Dict, Optional
from guardrails.validators import (
    FailResult,
    PassResult,
    register_validator,
    ValidationResult,
    Validator,
)
from litellm import completion
from dotenv import load_dotenv
load_dotenv()
from prompts import INPUT_GUARDRAIL_PROMPT, OUTPUT_GUARDRAIL_PROMPT

# =====================================================================
# 1. ENVIRONMENT CONFIGURATION (UNI GREIFSWALD / LITELLM ALIGNMENT)
# =====================================================================
MODEL_ID = os.getenv("MODEL_ID_UNI_GREIFSWALD", "gpt-4o")
API_BASE = os.getenv("OPENAI_API_BASE_UNI_GREIFSWALD")
API_KEY = os.getenv("OPENAI_API_KEY_UNI_GREIFSWALD")

# Safely load the extra body parameters dictionary
extra_body_str = os.getenv("LITELLM_EXTRA_BODY_UNI_GREIFSWALD", "{}")
try:
    EXTRA_BODY = json.loads(extra_body_str)
except Exception:
    EXTRA_BODY = {}


@register_validator(name="input-guard", data_type="string")
class InputGuardrail(Validator):
    def __init__(
        self, 
        threshold: int = 70, 
        model: str = MODEL_ID, 
        on_fail: Optional[Callable] = None
    ):
        super().__init__(on_fail=on_fail, threshold=threshold)
        self._threshold = threshold
        self._model = model

    def _llm_callable(self, messages):
        # Guardrail defensively prepends 'openai/' to custom API endpoints
        model_name = self._model
        model_name = f"openai/{model_name}"
            
        kwargs = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.0,
        }
        if API_BASE:
            kwargs["api_base"] = API_BASE
        if API_KEY:
            kwargs["api_key"] = API_KEY
        if EXTRA_BODY:
            kwargs["extra_body"] = EXTRA_BODY
            
        return completion(**kwargs)
    
    def _validate(self, value: str, metadata: Dict) -> ValidationResult:
        sys.stderr.write(" -> [GUARDRAIL] Running Input Security Validation Check...\n")
        sys.stderr.flush()

        messages = [
            {"role": "system", "content": INPUT_GUARDRAIL_PROMPT},
            {"role": "user", "content": f"USER INPUT:\n{value}"}
        ]

        try:
            raw_response = self._llm_callable(messages).choices[0].message.content.strip()
            score = int("".join(filter(str.isdigit, raw_response)))
        except Exception as e:
            # Fallback defensively if LLM output fails parsing
            sys.stderr.write(f" -> [GUARDRAIL ERROR] Parser failed, using strict reject: {str(e)}\n")
            return FailResult(error_message="Security parser failure, input blocked defensively.")

        if score > self._threshold:
            return FailResult(
                error_message=(
                    f"Input validation failed. Risk score {score} exceeded "
                    f"the maximum allowed threshold of {self._threshold}. "
                    f"Possible toxicity, prompt injection, or irrelevant domain query."
                )
            )
        return PassResult()


@register_validator(name="output-guard", data_type="string")
class OutputGuardrail(Validator):
    def __init__(
        self, 
        threshold: int = 70, 
        model: str = MODEL_ID, 
        on_fail: Optional[Callable] = None
    ):
        super().__init__(on_fail=on_fail, threshold=threshold)
        self._threshold = threshold
        self._model = model

    def _llm_callable(self, messages):
        # Guardrail defensively prepends 'openai/' to custom API endpoints
        model_name = self._model
        model_name = f"openai/{model_name}"
            
        kwargs = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.0,
        }
        if API_BASE:
            kwargs["api_base"] = API_BASE
        if API_KEY:
            kwargs["api_key"] = API_KEY
        if EXTRA_BODY:
            kwargs["extra_body"] = EXTRA_BODY
            
        return completion(**kwargs)
    
    def _validate(self, value: str, metadata: Dict) -> ValidationResult:
        sys.stderr.write(" -> [GUARDRAIL] Running Output Compliance Validation Check...\n")
        sys.stderr.flush()

        messages = [
            {"role": "system", "content": OUTPUT_GUARDRAIL_PROMPT},
            {"role": "user", "content": f"SYSTEM OUTPUT:\n{value}"}
        ]

        try:
            raw_response = self._llm_callable(messages).choices[0].message.content.strip()
            score = int("".join(filter(str.isdigit, raw_response)))
        except Exception as e:
            sys.stderr.write(f" -> [GUARDRAIL ERROR] Parser failed, using strict reject: {str(e)}\n")
            return FailResult(error_message="Security parser failure, output blocked defensively.")

        if score > self._threshold:
            return FailResult(
                error_message=(
                    f"Output compliance validation failed. Compliance score {score} exceeded "
                    f"the maximum allowed threshold of {self._threshold}. "
                    f"Detected possible toxicity, instruction leak, or forbidden flat aggregate score display."
                )
            )
        return PassResult()


def check_input_safety(user_text: str) -> ValidationResult:
    """Convenience wrapper to quickly validate user inputs."""
    validator = InputGuardrail(threshold=70)
    return validator._validate(user_text, {})

def check_output_safety(system_text: str) -> ValidationResult:
    """Convenience wrapper to quickly validate generated system outputs."""
    validator = OutputGuardrail(threshold=70)
    return validator._validate(system_text, {})
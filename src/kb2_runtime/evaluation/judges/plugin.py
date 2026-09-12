from __future__ import annotations

import hashlib
import json
import time

import httpx
from pydantic import Field, ValidationError

from kb2_runtime.config import ConfigurationError, Settings
from kb2_runtime.evidence.contracts import EvidenceSet
from kb2_runtime.generation.contracts import FinalResponse
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import CalibrationSnapshot, JudgeContract, JudgeResult, canonical_bytes, digest


class JudgeConfig(JudgeContract):
    definition_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")
    case_id: str = Field(pattern=r"^qcase_[a-f0-9]{16,64}$")


class DeepSeekJudge:
    """Provider adapter which persists only constrained labels and reason codes."""
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        try:
            snapshot_input, evidence_input, final_input = [await context.input(item.id) for item in context.invocation.inputs]
            if any(hashlib.sha256(item.content).hexdigest() != item.reference.content_digest for item in (snapshot_input, evidence_input, final_input)):
                raise ValueError("forged input digest")
            snapshot = CalibrationSnapshot.model_validate_json(snapshot_input.content)
            config = JudgeConfig.model_validate(context.invocation.validated_configuration)
            definition = next(item for item in snapshot.definitions if item.definition_id == config.definition_id)
            settings = Settings.from_env()
            key = settings.deepseek_api_key()
            if not key:
                raise PluginError(PluginErrorCode.GENERATION_UNAVAILABLE)
            evidence = EvidenceSet.model_validate_json(evidence_input.content)
            final = FinalResponse.model_validate_json(final_input.content)
            calibration = next(item for item in snapshot.labels if item.case_id == config.case_id and item.definition_id == definition.definition_id)
            if calibration.evidence_artifact_id != evidence_input.reference.id or calibration.evidence_digest != evidence_input.reference.content_digest or final.evidence_artifact_id != evidence_input.reference.id:
                raise ValueError("judge bindings are invalid")
            body = {"model": definition.model, **definition.parameters, "messages": [
                {"role": "system", "content": definition.prompt_template},
                {"role": "user", "content": json.dumps({"evidence": [{"id": item.evidence_id, "excerpt": item.excerpt} for item in evidence.items[:definition.max_evidence_items]], "answer": final.answer, "labels": definition.labels}, ensure_ascii=True, separators=(",", ":"))},
            ]}
            started = time.monotonic()
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30) as client:
                response = await client.post(settings.trusted_deepseek_base_url() + "/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body)
            if response.status_code >= 400:
                raise PluginError(PluginErrorCode.GENERATION_PROVIDER_FAILED)
            value = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(value) if isinstance(value, str) else value
            label, codes = parsed["label"], tuple(parsed.get("rationale_codes", ()))
            if label not in definition.labels or len(codes) > definition.max_rationale_codes:
                raise ValueError("invalid provider judge response")
            result = JudgeResult(case_id=config.case_id, calibration_snapshot_id=snapshot_input.reference.id, calibration_snapshot_digest=snapshot.snapshot_digest, definition_id=definition.definition_id, definition_digest=definition.definition_digest, provider_id=definition.provider_id, model=definition.model, plugin_id=context.invocation.plugin_id, implementation_digest=context.invocation.implementation_digest, prompt_digest=digest(definition.prompt_template), parameters_digest=digest(definition.parameters), evidence_artifact_id=evidence_input.reference.id, evidence_digest=evidence_input.reference.content_digest, final_response_artifact_id=final_input.reference.id, label=label, rationale_codes=codes, cited_evidence_ids=(), elapsed_ms=int((time.monotonic() - started) * 1000))
        except PluginError:
            raise
        except (ConfigurationError, httpx.HTTPError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, StopIteration) as exc:
            raise PluginError(PluginErrorCode.GENERATION_PROVIDER_FAILED) from exc
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="judge.result", schema_revision="v1", content=canonical_bytes(result), summary="semantic judge result"),), summary="semantic judge result")

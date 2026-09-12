from __future__ import annotations

import hashlib
import json
import re
from uuid import UUID

import httpx
from pydantic import ValidationError

from kb2_runtime.config import ConfigurationError, Settings
from kb2_runtime.evidence.contracts import EvidenceSet
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput, configuration_digest
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from .contracts import FinalResponse, GeneratedAnswer, GenerationConfig, VerificationConfig, VerificationResult
from .serializer import canonical_bytes, identity


def _tokens(value: str) -> set[str]:
    return {item for item in re.findall(r"[a-z0-9]{2,}", value.lower()) if item not in {"the", "and", "for", "with", "this", "that", "from", "are", "was"}}


class DeepSeekGenerator:
    """Trusted adapter: its persisted output is only the constrained answer contract."""
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        try:
            question_input, evidence_input = [await context.input(item.id) for item in context.invocation.inputs]
            if hashlib.sha256(question_input.content).hexdigest() != question_input.reference.content_digest or hashlib.sha256(evidence_input.content).hexdigest() != evidence_input.reference.content_digest:
                raise PluginError(PluginErrorCode.GENERATION_INPUT_INVALID)
            question = question_input.content.decode("utf-8")
            evidence = EvidenceSet.model_validate_json(evidence_input.content)
            config = GenerationConfig.model_validate(context.invocation.validated_configuration)
            settings = Settings.from_env()
            key = settings.deepseek_api_key()
            if not key:
                raise PluginError(PluginErrorCode.GENERATION_UNAVAILABLE)
            body = {"model": config.model, "temperature": config.temperature, "max_tokens": config.max_tokens,
                    "messages": [{"role": "system", "content": "Return JSON with answer and citation_keys using only evidence."},
                                 {"role": "user", "content": json.dumps({"question": question, "evidence": [{"citation_key": x.citation_key, "excerpt": x.excerpt} for x in evidence.items]}, ensure_ascii=True, separators=(",", ":"))}]}
            timeout = max(0.1, (context.invocation.deadline_at - context.invocation.deadline_at.now(context.invocation.deadline_at.tzinfo)).total_seconds())
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=timeout) as client:
                response = await client.post(settings.trusted_deepseek_base_url() + "/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body)
            if response.status_code >= 400:
                raise PluginError(PluginErrorCode.GENERATION_PROVIDER_FAILED)
            parsed = response.json()
            content = parsed["choices"][0]["message"]["content"]
            value = json.loads(content) if isinstance(content, str) else content
            answer, keys = value["answer"], tuple(value["citation_keys"])
            if not isinstance(answer, str) or len(answer) > config.max_answer_chars:
                raise PluginError(PluginErrorCode.GENERATION_PROVIDER_FAILED)
            match = re.search(r"\.generate-(\d+)$", context.invocation.stage_key)
            base = {"evidence_artifact_id": question_input.reference.id, "evidence_digest": evidence_input.reference.content_digest, "question_artifact_id": question_input.reference.id, "question_digest": question_input.reference.content_digest, "generator_plugin_id": context.invocation.plugin_id, "implementation_digest": context.invocation.implementation_digest, "configuration_digest": context.invocation.configuration_digest, "answer": answer, "citation_keys": keys, "attempt": int(match.group(1)) + 1 if match else 1}
            # Correct the two bindings without allowing provider data to escape.
            base["evidence_artifact_id"] = evidence_input.reference.id
            output = GeneratedAnswer(answer_id=identity("ans_", base), **base)
        except PluginError:
            raise
        except (ConfigurationError, httpx.HTTPError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise PluginError(PluginErrorCode.GENERATION_PROVIDER_FAILED) from exc
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="generated.answer", schema_revision="v1", content=canonical_bytes(output), summary="grounded answer generated"),), summary="grounded answer generated")


class LocalVerifier:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        try:
            answer_input, evidence_input = [await context.input(item.id) for item in context.invocation.inputs]
            answer = GeneratedAnswer.model_validate_json(answer_input.content)
            evidence = EvidenceSet.model_validate_json(evidence_input.content)
            config = VerificationConfig.model_validate(context.invocation.validated_configuration)
            evidence_keys = {item.citation_key for item in evidence.items}
            missing = tuple(key for key in answer.citation_keys if key not in evidence_keys)
            codes: list[str] = []
            if len(evidence.items) < config.minimum_items: codes.append("INSUFFICIENT_EVIDENCE")
            if missing: codes.append("UNKNOWN_CITATION")
            if any(phrase.lower() in answer.answer.lower() for phrase in config.forbidden_phrases): codes.append("FORBIDDEN_CONTENT")
            cited = [item for item in evidence.items if item.citation_key in answer.citation_keys]
            excerpts = set().union(*(_tokens(item.excerpt) for item in cited)) if cited else set()
            sentences = [item for item in re.split(r"[.!?]+", answer.answer) if _tokens(item)]
            if cited and any(not _tokens(sentence).intersection(excerpts) for sentence in sentences):
                codes.append("UNSUPPORTED_CONTENT")
            if config.answerability == "ambiguous":
                outcome = "clarification_required"
                codes.append("AMBIGUOUS_QUESTION")
            elif config.answerability == "not_answerable":
                outcome = "abstain"
                codes.append("NOT_ANSWERABLE")
            elif codes:
                outcome = "abstain" if "INSUFFICIENT_EVIDENCE" in codes else "repairable"
            else: outcome = "pass"
            base = {"generated_answer_artifact_id": answer_input.reference.id, "evidence_artifact_id": evidence_input.reference.id, "evidence_digest": evidence_input.reference.content_digest, "outcome": outcome, "failure_codes": tuple(codes), "resolved_citation_keys": tuple(key for key in answer.citation_keys if key in evidence_keys), "missing_citation_keys": missing, "answerable": outcome == "pass"}
            result = VerificationResult(verification_id=identity("ver_", base), **base)
        except (ValidationError, ValueError, TypeError) as exc:
            raise PluginError(PluginErrorCode.VERIFICATION_INPUT_INVALID) from exc
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="verification.result", schema_revision="v1", content=canonical_bytes(result), summary="grounded answer verified"),), summary="grounded answer verified")


class FinalStatePlugin:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        try:
            evidence_input = await context.input(context.invocation.inputs[0].id)
            if len(context.invocation.inputs) == 1:
                base = {"state": "FAILED", "evidence_artifact_id": evidence_input.reference.id, "verification_artifact_id": None, "generated_answer_artifact_id": None, "answer": None, "citation_keys": (), "action": "Retry the configured query after generation is available."}
                response = FinalResponse(response_id=identity("fin_", base), **base)
                return PluginInvocationResult(outputs=(PluginOutput(artifact_type="final.response", schema_revision="v1", content=canonical_bytes(response), summary="generation unavailable"),), summary="generation unavailable")
            verification_input, answer_input = [await context.input(item.id) for item in context.invocation.inputs[1:]]
            verification = VerificationResult.model_validate_json(verification_input.content)
            answer = GeneratedAnswer.model_validate_json(answer_input.content)
            if (verification.generated_answer_artifact_id != answer_input.reference.id
                    or verification.evidence_artifact_id != evidence_input.reference.id
                    or verification.evidence_digest != evidence_input.reference.content_digest
                    or answer.evidence_artifact_id != evidence_input.reference.id
                    or answer.evidence_digest != evidence_input.reference.content_digest):
                raise PluginError(PluginErrorCode.VERIFICATION_INPUT_INVALID)
            if verification.outcome == "pass":
                base = {"state": "ANSWERED", "evidence_artifact_id": evidence_input.reference.id, "verification_artifact_id": verification_input.reference.id, "generated_answer_artifact_id": answer_input.reference.id, "answer": answer.answer, "citation_keys": answer.citation_keys, "action": None}
            else:
                state = {
                    "clarification_required": "CLARIFICATION_REQUIRED",
                    "abstain": "ABSTAINED",
                }.get(verification.outcome, "FAILED")
                base = {"state": state, "evidence_artifact_id": evidence_input.reference.id, "verification_artifact_id": verification_input.reference.id, "generated_answer_artifact_id": answer_input.reference.id, "answer": None, "citation_keys": (), "action": "Provide more evidence or retry the configured query."}
            response = FinalResponse(response_id=identity("fin_", base), **base)
        except (ValidationError, ValueError, TypeError) as exc:
            raise PluginError(PluginErrorCode.VERIFICATION_INPUT_INVALID) from exc
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="final.response", schema_revision="v1", content=canonical_bytes(response), summary="final response validated"),), summary="final response validated")

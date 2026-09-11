from __future__ import annotations

import base64
import asyncio
from datetime import datetime

import httpx

from .contracts import PluginContext, PluginImplementation, PluginInvocationResult, StageInvocation
from .errors import PluginError, PluginErrorCode


class ContainerRunner:
    """Client for the repository-owned fixed plugin-runner sidecar."""

    def __init__(self, endpoint: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._transport = transport

    async def invoke(self, implementation: PluginImplementation, invocation: StageInvocation, context: PluginContext) -> PluginInvocationResult:
        payload_inputs = []
        for reference in invocation.inputs:
            item = await context.input(reference.id)
            payload_inputs.append({"reference": reference.model_dump(mode="json"), "content": base64.b64encode(item.content).decode("ascii")})
        payload = {"invocation": invocation.model_dump(mode="json"), "inputs": payload_inputs, "cancelled": context.cancellation.is_set()}
        timeout = max(0.001, (invocation.deadline_at - datetime.now(invocation.deadline_at.tzinfo)).total_seconds())
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False, transport=self._transport) as client:
                invocation_task = asyncio.create_task(client.post(f"{self.endpoint}/invoke", json=payload))
                cancellation_task = asyncio.create_task(context.cancellation.wait())
                try:
                    done, _ = await asyncio.wait((invocation_task, cancellation_task), return_when=asyncio.FIRST_COMPLETED)
                    if context.cancellation.is_set():
                        if not invocation_task.done():
                            try:
                                await client.post(f"{self.endpoint}/cancel/{invocation.stage_attempt_id}", timeout=0.5)
                                await asyncio.wait_for(asyncio.shield(invocation_task), timeout=0.5)
                            except (asyncio.TimeoutError, httpx.HTTPError):
                                pass
                        invocation_task.cancel()
                        await asyncio.gather(invocation_task, return_exceptions=True)
                        raise PluginError(PluginErrorCode.CANCELLED)
                    response = await invocation_task
                finally:
                    cancellation_task.cancel()
                    await asyncio.gather(cancellation_task, return_exceptions=True)
                    if not invocation_task.done():
                        invocation_task.cancel()
                        await asyncio.gather(invocation_task, return_exceptions=True)
                if response.is_error:
                    try:
                        raise PluginError(PluginErrorCode(response.json()["code"]))
                    except (KeyError, TypeError, ValueError):
                        raise PluginError(PluginErrorCode.UNAVAILABLE)
                response.raise_for_status()
                body = response.json()
                for output in body.get("outputs", []):
                    output["content"] = base64.b64decode(output["content"], validate=True)
                return PluginInvocationResult.model_validate(body)
        except httpx.TimeoutException as exc:
            raise PluginError(PluginErrorCode.TIMEOUT) from exc
        except PluginError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise PluginError(PluginErrorCode.UNAVAILABLE) from exc
        except Exception as exc:
            raise PluginError(PluginErrorCode.RESULT_INVALID) from exc

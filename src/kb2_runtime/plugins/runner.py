from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Protocol

from .contracts import PluginContext, PluginImplementation, PluginInvocationResult, StageInvocation
from .errors import PluginError, PluginErrorCode


class PluginRunner(Protocol):
    async def invoke(self, implementation: PluginImplementation, invocation: StageInvocation, context: PluginContext) -> PluginInvocationResult: ...


class InProcessRunner:
    async def invoke(self, implementation: PluginImplementation, invocation: StageInvocation, context: PluginContext) -> PluginInvocationResult:
        seconds = max(0.0, (invocation.deadline_at - datetime.now(invocation.deadline_at.tzinfo)).total_seconds())
        if context.cancellation.is_set():
            raise PluginError(PluginErrorCode.CANCELLED)
        invocation_task = asyncio.create_task(implementation.invoke(context))
        cancellation_task = asyncio.create_task(context.cancellation.wait())
        try:
            done, _ = await asyncio.wait(
                (invocation_task, cancellation_task), timeout=seconds, return_when=asyncio.FIRST_COMPLETED
            )
            if cancellation_task in done and context.cancellation.is_set():
                invocation_task.cancel()
                await asyncio.gather(invocation_task, return_exceptions=True)
                raise PluginError(PluginErrorCode.CANCELLED)
            if invocation_task not in done:
                invocation_task.cancel()
                await asyncio.gather(invocation_task, return_exceptions=True)
                raise PluginError(PluginErrorCode.TIMEOUT)
            return invocation_task.result()
        except asyncio.TimeoutError as exc:
            raise PluginError(PluginErrorCode.TIMEOUT) from exc
        except asyncio.CancelledError as exc:
            raise PluginError(PluginErrorCode.CANCELLED) from exc
        except PluginError:
            raise
        except Exception as exc:
            raise PluginError(PluginErrorCode.CRASHED) from exc
        finally:
            cancellation_task.cancel()
            await asyncio.gather(cancellation_task, return_exceptions=True)

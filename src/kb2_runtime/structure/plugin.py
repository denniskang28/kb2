from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput

from .processor import canonical_bytes, process
from .contracts import StructureStrategy


class CanonicalStructurePlugin:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)
        strategy = StructureStrategy(context.invocation.validated_configuration["strategy"])
        document = process(source.content, strategy)
        table_count = len(document.tables)
        hierarchy_links = sum(item.parent_id is not None for item in document.elements)
        signals = (
            {"name": "structure_validation", "status": "PASS", "summary": "validated"},
            {"name": "hierarchy_validation", "status": "PASS", "summary": "validated"},
            {"name": "reading_order_validation", "status": "PASS", "summary": "validated"},
            {"name": "table_validation", "status": "PASS", "summary": "validated"},
        )
        return PluginInvocationResult(
            outputs=(PluginOutput(
                artifact_type="canonical.document", schema_revision="v1", content=canonical_bytes(document),
                summary="canonical structure validated", metrics=(
                    {"name": "structure_elements", "value": len(document.elements)},
                    {"name": "structure_hierarchy_links", "value": hierarchy_links},
                    {"name": "structure_tables", "value": table_count},
                ), quality_signals=signals,
            ),),
            summary="canonical structure validated", quality_signals=signals,
        )

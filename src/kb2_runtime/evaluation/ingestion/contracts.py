"""Compatibility exports for the S-017 ingestion metric public surface."""
from kb2_runtime.evaluation.metrics.contracts import (
    IngestionMetricContract,
    MetricAggregate,
    MetricMatch,
    MetricReport,
    MetricStatus,
    metric_aggregate_bytes,
    metric_report_bytes,
)

__all__ = ["IngestionMetricContract", "MetricAggregate", "MetricMatch", "MetricReport", "MetricStatus", "metric_aggregate_bytes", "metric_report_bytes"]

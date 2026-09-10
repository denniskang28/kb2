# Knowledge Engine Lite

Knowledge Engine Lite is a local-first engineering workbench for three reusable
cores:

1. configurable, plugin-based document ingestion;
2. configurable evidence retrieval and grounded query execution;
3. reproducible ingestion, retrieval, and answer-quality evaluation.

It is intentionally not a reduced enterprise knowledge-management portal.
Identity, approval, publication, quota, tenant, lifecycle, and Azure-managed
service concerns are deferred while the engine contracts and accuracy loop are
proven locally.

Start with [the current state](docs/current-state.md), then read the
[product requirements](docs/prd.md), [core design](docs/core-design.md), and
[Feature map](docs/feature-map.md).

## Local runtime

Prerequisites are Docker Desktop (Compose v2), Make, and Python 3. Startup
builds the pinned application image and starts only the local core services; it
does not download a model or call an external model provider.

```sh
make local-up
make local-health
make local-stop
```

`local-up` starts the API, worker, PostgreSQL/pgvector, and Artifact volume
without an Azure endpoint or model credential. It generates a database
password and an empty DeepSeek key file below the ignored
`.runtime/kb2-lite-dev/secrets/` directory. Both files use mode `0600`. A
normal `local-stop` preserves database and Artifact volumes; restart with
`make local-up`.

Health has deliberately separate meanings:

- `GET /health/live` reports only that the API process is alive.
- `GET /health/ready` and `local-up` check only required local infrastructure
  and never call DeepSeek.
- `make local-health` prints one sanitized row for every known component and
  capability. With no key, generation is reported as `not_configured` while
  core readiness remains ready. With a populated key, generation is reported
  as `not_probed`; this ordinary health check still makes no external request.
- `python3 scripts/local_runtime.py health --require generation.high_precision`
  checks whether an experiment can use `deepseek-v4-pro`; it exits nonzero when
  that optional capability is unavailable.

To enable generation checks, write the DeepSeek key only to
`.runtime/kb2-lite-dev/secrets/deepseek_api_key`, keep its mode at `0600`, and
explicitly require a generation capability, for example
`python3 scripts/local_runtime.py health --require generation.default`. Local
and other non-test environments accept only the exact trusted endpoint
`https://api.deepseek.com`; the test environment accepts only the in-Compose
`http://deepseek-fixture:8080` endpoint. Alternate endpoints require a reviewed
provider adapter rather than a URL override. An explicit check performs one
authenticated `GET /models` inventory request with redirects and environment
proxies disabled, then uses exact model-ID matching. It never sends a chat or
generation request. `embedding.default` remains provider-neutral and
unconfigured in S-001.

Unavailable required dependencies produce a nonzero health command. Diagnostic
codes such as `DEPENDENCY_UNAVAILABLE`, `HEARTBEAT_STALE`, `MODEL_NOT_AVAILABLE`,
and `PROBE_TIMEOUT` are intentionally stable; raw provider errors and local
content are never printed by the health path.

Permanent local data removal is separate and explicit:

```sh
make local-clean CONFIRM=kb2-local-data
```

The command removes only the validated `kb2-lite-dev` Compose project and its
generated state. For fast checks run `make test-contract`; the Docker-backed,
disposable lifecycle suite is `make test-integration` and uses the same runtime
CLI plus a deterministic `/models` fixture; it never calls the real provider.

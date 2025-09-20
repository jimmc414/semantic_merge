# Semantic Merge Engine

Semantic Merge Engine is a reference implementation of a structure-aware merge and diff toolchain for TypeScript projects. Instead of splicing text hunks, the engine builds a typed program model, extracts semantic operations, composes them deterministically, and materializes verified source files. It ships as a Python CLI backed by a Node.js worker and integrates with Git merge drivers for repo-wide workflows.

## Table of contents
- [Key capabilities](#key-capabilities)
- [Repository layout](#repository-layout)
- [Quick start](#quick-start)
- [CLI usage](#cli-usage)
- [Git integration](#git-integration)
- [Configuration](#configuration)
- [Development workflow](#development-workflow)
- [Further reading](#further-reading)

## Key capabilities
- **Semantic diffing and merging for TypeScript.** The CLI exposes `semdiff` and `semmerge` commands that invoke a TypeScript-aware worker to generate and compose operation logs instead of text patches.
- **Deterministic op composition and conflict detection.** Operation logs from both branches are sorted, chained, and merged with targeted `DivergentRename` conflicts when the same symbol is renamed differently.
- **Best-effort application, formatting, and verification.** The engine replays supported operations onto the base tree, formats results via Prettier when available, and runs `tsc --noEmit`, gracefully skipping steps when the toolchain is missing.

## Repository layout
```text
semantic_merge/
├── semmerge/           # Python package hosting the CLI and orchestration logic
├── workers/ts/         # Node-based worker that parses TypeScript and emits op logs
├── scripts/            # Git merge driver wrapper
├── tests/              # End-to-end smoke test exercising the CLI and driver
├── architecture.md     # High-level architecture specification
├── implementation.md   # Detailed implementation guide
└── requirements.md     # Functional and non-functional requirements
```

## Quick start
1. **Install prerequisites.** Ensure Python 3.10+, Node.js 18+, and Git 2.35+ are available, along with optional Java and .NET SDKs for future language backends.
2. **Build the TypeScript worker.** Run `npm --prefix workers/ts install` followed by `npm --prefix workers/ts run build` to produce `workers/ts/dist/index.js`.
3. **Install the Python package.** Execute `python -m pip install -e .` to install the CLI in editable mode for local development.
4. **Run a smoke test.** Execute `bash tests/e2e_basic.sh` to compile the worker, install the CLI, and validate a simple rename-plus-move merge scenario.

## CLI usage
After installation, invoke commands via `python -m semmerge <command>` or the `semmerge` console script.

### `semdiff <rev1> <rev2>`
Checks out both revisions into temporary trees, asks the TypeScript worker for an op log, and prints either a human-readable listing or JSON when `--json-out` is provided.

### `semmerge <base> <A> <B>`
Performs a full semantic merge by:
1. Checking out the three Git revisions to temporary directories.
2. Requesting both op logs from the worker via `buildAndDiff`.
3. Composing the logs into a deterministic operation sequence.
4. Applying supported operations, formatting the result, and running `tsc --noEmit`.
5. Writing the merged tree back into the working directory when `--inplace` is passed (Git merge driver mode).
6. Persisting the per-branch op logs as Git notes for traceability.

A non-zero exit status indicates conflicts (`1`) or type-check failures (`2`). Use the generated `.semmerge-conflicts.json` and CLI diagnostics to investigate.

## Git integration
The repository ships with `scripts/semmerge-driver.py`, a Git merge driver that orchestrates repo-level merges before handing the requested file back to Git. Enable it with:

```bash
# .gitconfig
[merge "semmerge"]
    name = Semantic merge engine
    driver = python3 scripts/semmerge-driver.py %O %A %B

# .gitattributes
*.ts merge=semmerge
```

The driver locks merges per-repository to avoid concurrent runs, calls `python3 -m semmerge semmerge --inplace --git`, and copies resolved files into Git’s expected locations.

## Configuration
Project-level behaviour is controlled by an optional `.semmerge.toml` file. Core settings include deterministic seeds, memory caps, and preferred formatters. Language sections enable backends and supply project globbing and formatter commands, while the `ci` section toggles required verification steps. See `semmerge/config.py` for the schema.

## Development workflow
- **Logging.** Set `SEMMERGE_LOG=DEBUG` to increase verbosity when debugging CLI runs.
- **Rebuilding the worker.** Re-run the npm install/build commands after making changes under `workers/ts/src/`.
- **Tests.** The `tests/e2e_basic.sh` script covers the full Python/Node/Git pipeline; run it before publishing changes to verify end-to-end behaviour.
- **Code references.** The TypeScript worker listens on stdin/stdout using JSON-RPC, and the Python bridge streams file snapshots to it. Conflict payloads, CRDT ordering, and op schemas are documented in the architecture and implementation guides for deeper dives.

## Further reading
- [architecture.md](architecture.md) — pipeline, data model, and backend expectations.
- [implementation.md](implementation.md) — setup instructions and code walkthrough.
- [requirements.md](requirements.md) — normative statements that govern scope and behaviour.

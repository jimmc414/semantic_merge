# Runbook: Semantic Merge Engine

This runbook documents day-to-day operational procedures for the Semantic Merge Engine CLI and its Git integration. It is intended for developers and release engineers who maintain the toolchain and respond to support requests.

## System overview
- **Python orchestrator.** The `semmerge` package exposes the CLI (`semdiff`, `semmerge`) and coordinates tree checkout, op composition, application, formatting, and verification.
- **TypeScript worker.** A Node.js process (`workers/ts/dist/index.js`) implements JSON-RPC methods that build lightweight program indexes, perform diffs, and lift them into operation logs consumed by Python.
- **Git driver wrapper.** `scripts/semmerge-driver.py` locks concurrent executions, invokes `python3 -m semmerge semmerge --inplace --git`, and copies merged files back into Git’s temporary area.

## Prerequisites and installation
1. **Language runtimes.** Install Python 3.10+, Node.js 18+, and Git 2.35+. Optional Java 17+ and .NET 7+ runtimes prepare for additional backends.
2. **Build the worker.** Run `npm --prefix workers/ts install` and `npm --prefix workers/ts run build` whenever TypeScript sources change. The Python bridge refuses to start the worker until `dist/index.js` exists.
3. **Install the CLI.** Execute `python -m pip install -e .` from the repository root to expose the `semmerge` console script and module entry point.
4. **Smoke-test the stack.** Invoke `bash tests/e2e_basic.sh` to reinstall dependencies, create a throwaway Git repo, configure the merge driver, and validate a rename-plus-move merge.

## Routine operations
### Running semantic merges manually
1. Ensure the current Git repository has the desired commits available locally.
2. Run `python -m semmerge semmerge <base> <A> <B> [--inplace]`.
   - Without `--inplace` the merged tree remains in a temporary directory; use it for inspection.
   - With `--inplace` the merge result overwrites the working tree (required for Git merge driver runs).
3. Interpret exit codes:
   - `0`: merge succeeded and, when applicable, type-check passed.
   - `1`: semantic conflicts were detected. Inspect `.semmerge-conflicts.json` for payloads.
   - `2`: TypeScript verification failed; CLI stderr contains compiler diagnostics.
4. When conflicts arise, review the serialized ops in `.semmerge-conflicts.json` and resolve manually before re-running.

### Using the Git merge driver
1. Configure the repository:
   - Add `[merge "semmerge"]` and `driver = python3 scripts/semmerge-driver.py %O %A %B` to `.git/config` or global config.
   - Annotate target file globs (e.g., `*.ts`) with `merge=semmerge` inside `.gitattributes`.
2. During `git merge`, the driver:
   - Calculates the base commit via `git merge-base`.
   - Serializes access with `.git/.semmerge.lock` to avoid concurrent merges.
   - Calls the CLI with `--inplace --git`, allowing Git to read resolved files directly from the repository.
3. If the driver exits with a non-zero status, Git reports the merge failure; inspect the CLI output and conflict artifacts as in manual runs.

### Configuration management
- Place `.semmerge.toml` at the repository root to override defaults.
  - `[core]` controls deterministic seeds, memory caps, and formatter hints.
  - `[languages.<name>]` toggles backends and defines project globbing plus formatter commands.
  - `[ci]` enforces whether type-checking and test commands must succeed.
- Run `python -m semmerge semmerge ...` from within the configured repository so relative formatter/test commands resolve correctly.

### Observability and diagnostics
- Set `SEMMERGE_LOG=DEBUG` to receive verbose logging from the Python orchestrator.
- Conflict artifacts are written to `.semmerge-conflicts.json` in the current working directory when merges detect non-commuting ops.
- Type-check diagnostics stream to stderr; Prettier output is suppressed unless the formatter fails.

## Troubleshooting
| Symptom | Likely cause | Mitigation |
| --- | --- | --- |
| `TypeScript worker not built` runtime error | `workers/ts/dist/index.js` missing | Re-run the npm install/build commands to regenerate the bundle. |
| Merge exits with status 1 and `.semmerge-conflicts.json` contains `DivergentRename` entries | Both branches renamed the same symbol differently | Choose a preferred rename, apply it manually, and rerun the merge. |
| Merge exits with status 2 and `tsc` errors | Type-check failed after applying ops | Fix the reported diagnostics or disable required checks via `.semmerge.toml` `[ci]` when appropriate. |
| Prettier warnings in logs | Formatter returned a non-zero exit code | Investigate formatting errors; merging still produces syntactically valid output. |
| `tsc` missing but merges succeed silently | TypeScript compiler is not installed | Install `typescript` globally or rely on the documented fallback when verification is optional. |

## On-call checklist
- Keep the worker bundle current by rebuilding after TypeScript source edits.
- Ensure the CLI package is reinstalled (`pip install -e .`) after modifying Python modules.
- Before cutting releases, run `bash tests/e2e_basic.sh` to cover the end-to-end pipeline.
- Verify Git driver configuration in consuming repositories after updates to the wrapper script.

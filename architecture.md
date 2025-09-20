# Semantic Merge Engine — Architecture

Status: design complete for P0 (TypeScript, Java, C#). No code in this document.

---

## 1. System Overview

Goal: merge and rebase code by composing **semantic operations** over a **typed program graph**, not by splicing text. Inputs: three Git trees (`base`, `A`, `B`). Output: merged tree with minimal conflicts, preserved formatting, and verified types.

**Core pipeline**
1. Ingest Git trees.
2. Build SAST (typed AST + symbol graph) for each tree.
3. Compute move-aware diffs and **lift** to semantic Op Logs for `base→A` and `base→B`.
4. Compose Op Logs with deterministic rules and CRDT ordering for sibling lists.
5. Apply composed Ops to `base SAST`.
6. Reattach formatting (CST), format files, and materialize the merged tree.
7. Validate via type-check and optional tests.
8. Emit conflict reports at the Op/node level if needed.

---

## 2. Component Model

### 2.1 CLI and Drivers
- Commands: semdiff, semmerge, semrebase, semverify, semtrace.
- Git integration: merge driver and rebase driver wrappers. Accept Git OIDs, produce merged files or conflict artifacts.

### 2.2 Core Engine
- **Coordinator**: orchestrates phases, resource caps, deterministic scheduling.
- **Cache Manager**: content-addressable caches for parsing, type info, and SASTs.
- **Language Host**: plugin slot that binds a selected backend per file.
- **Diff/Lift**: tree-diff with move detection; pattern recognizers produce Ops.
- **Composer**: deterministic Op algebra, rename/move propagation, conflict detector.
- **CRDT Orderer**: list-CRDT for order-only sequences (imports, params, statements).
- **Applier**: transforms `base SAST` by replaying composed Ops with guards.
- **Emitter**: CST reattachment and formatter runner.
- **Verifier**: type-checkers and test runner.
- **Report Generator**: JSON and human reports for diffs, merges, conflicts, timings.

### 2.3 Language Backends (plugins)
Uniform interface per language:
- Parse: source→CST, CST→AST.
- Bind: AST→symbols, types, references.
- Build graph: call/override/containment edges.
- Diff primitive: node similarity, rename/move heuristics.
- Lift/Apply: language-aware Op encoders/decoders.
- Rewriter: import/package/namespace updates, callsite rewrites.
- Formatter bridge: run or integrate with project formatter.
- Type-check bridge: no-emit compile or analysis.

Backends P0:
- TypeScript: TypeScript Compiler API.
- Java: JDT or equivalent compiler-grade frontend.
- C#: Roslyn.

---

## 3. Data Model

### 3.1 SAST (Semantic AST)
- **Nodes**: module/package, namespace, type, member, parameter, import/using, statement, expression.
- **Attributes**: language kind, visibility, signature, generics, annotations, source ranges.
- **Edges**:
  - Declares, Contains, Extends/Implements.
  - RefersTo (identifier→symbol).
  - Calls (callsite→callee).
  - Overrides (method→base method).
- **Immutability**: persistent “green” trees with structural sharing for caching.

### 3.2 Identity
- **SymbolID**: stable identity for a declaration across moves/renames.
  - Constructed as a **normalized structural hash** of the declaration’s typed shape:
    - Includes kind, type parameters, parameter and return types, visibility where semantic, and a normalization of literal defaults.
    - Excludes human-chosen names and non-semantic trivia.
    - Salted with language+version and a backend-specific schema id.
- **AddressID**: language FQN + signature at a revision (name-based address).
- **NodeID**: ephemeral per-tree identity for diff alignment.
- **Cross-map**: per-revision tables from SymbolID↔AddressID, and NodeID→SymbolID.

Rationale: SymbolID tracks “the thing” through renames/moves; AddressID locates it in a tree.

### 3.3 Operation (Op)
- **Header**: id, type, schema version, provenance (rev, author id, timestamp).
- **Target**: SymbolID and optional AddressID at capture time.
- **Params**: op-specific fields (e.g., newName, newPath, newSignature).
- **Guards**: preconditions on existing types/addresses.
- **Effects**: declarative summary for auditing and conflict explanation.

Canonical Op set (P0):
- renameSymbol, moveDecl, addDecl, deleteDecl.
- changeSignature, reorderParams, addParam{default}, removeParam.
- extractMethod / inlineMethod.
- updateCall (callsite rewrite).
- editStmtBlock (list of statement insert/move/delete).
- modifyImport / reorderImports.
- moveFile / renameFile / modifyNamespace or package.

### 3.4 Conflict
- **Category**: DivergentRename, DivergentMove, IncompatibleSignature, DeleteVsEdit, OverlappingStmtEdit, ExtractVsInline, RenameVsDelete, etc.
- **Payload**: SymbolID, current AddressIDs in each branch, the colliding Ops, suggested resolutions, minimal code slice ranges.

---

## 4. Pipelines

### 4.1 Merge (3-way)
1. **Read** Git blobs and trees for base, A, B.
2. **Partition** files by language backend via `.gitattributes` and repo config.
3. **Parse+Bind** each revision, incrementally and in parallel:
   - Load from cache by content hash when available.
4. **Diff** `base→A` and `base→B` per file:
   - Tree matching uses bottom-up similarity with token/type features.
   - Move detection by maximizing matched-subtree reuse and filename/package changes.
5. **Lift** diffs to Ops:
   - Pattern recognizers detect renames, moves, signature changes, extracts, inlines.
   - Record Guards based on `SymbolID` and expected types.
6. **Compose** `ΔA` with `ΔB`:
   - Map each Op to current `SymbolID`.
   - Sort Ops by canonical precedence and provenance tiebreak.
   - Apply commutation rules; propagate renames/moves through dependent Ops.
   - Route order-only edits through CRDT Orderer.
   - Emit conflicts for non-commuting pairs.
7. **Apply** composed Ops to `base SAST`:
   - Enforce Guards; short-circuit and flag minimal failing Op set.
8. **Emit** source:
   - Reattach CST trivia to modified nodes.
   - Run formatter per language on changed files only.
9. **Verify**:
   - Type-check; on failure, map diagnostics back to responsible Ops and nodes.
   - Optional test commands in CI mode.
10. **Materialize** merged Git tree and conflict reports.

### 4.2 Rebase
- Compute Op Log for each commit in source branch (or reuse stored Op Logs).
- Replay Ops over the new base, batch-validating per commit.
- Collapse order-only edits with CRDT convergence.
- Stop on first semantic conflict with a targeted report.

---

## 5. Algorithms and Determinism

### 5.1 Tree Diff with Move Awareness
- **Matcher**:
  - Leaf similarity: token kind, type of referenced symbol, literal shape.
  - Internal similarity: multiset of child labels, type signatures, modifiers.
  - Cost function favors large subtree preservation and typed matches.
- **Move detection**:
  - Candidate pairs by SymbolID and structural hash.
  - Confirm by subtree similarity threshold and language move rules (e.g., package path change in Java).
- **Complexity**:
  - Typical O(n log n) with heuristics; worst-case O(n²) guarded by size caps and early exits.

### 5.2 Lift to Ops
- **Rename**: identifier edits at decl sites with preserved SymbolID and stable body.
- **MoveDecl**: AddressID path change with constant SymbolID.
- **ChangeSignature**: parameter or return type diffs; aggregated across overload sets where needed.
- **Extract/Inline**: detect cloned blocks or call replacements via PDG-like slicing at method granularity.
- **EditStmtBlock**: per-block list edits recorded as insert/move/delete keyed by stable anchors.

### 5.3 Op Composition
- **Ordering**: by (op-type precedence, commit time, author-id, op-id). All fields normalized to UTC and deterministic formats.
- **Commutation**:
  - Independent targets commute.
  - Rename+Move on same SymbolID reorder to Move then Rename on updated AddressID.
  - Signature change commutes with callsite updates if coverage is complete; otherwise conflict with missing callsites enumerated.
- **Propagation**:
  - Maintain a per-symbol rename chain and move chain to update downstream Ops.
- **Conflict minimality**:
  - Slice to the smallest affected node and attach the two Ops that cannot commute.

### 5.4 CRDT Ordering
- **Model**: RGA-like list with insertion keys derived from:
  - (base logical position anchor, commit time, author-id, op-id).
- **Scope**: imports/usings, parameters, arguments, statement lists, class member order where semantics are order-insensitive.
- **Safeguard**: for sequences where order is semantic, disable CRDT and require explicit resolution.
- **Determinism**: identical histories yield identical insertion orders.

### 5.5 Determinism Controls
- Normalize timestamps using commit metadata; fall back to deterministic commit hash ordering when absent.
- Fix seeds for any randomized tie-breakers using a repository-wide seed derived from base tree hash.
- Stable sorting everywhere a total order is required.

---

## 6. Caching and Performance

### 6.1 Cache Layers
- **Blob cache**: file content by Git OID.
- **Parse cache**: CST/AST by content hash.
- **Bind cache**: symbol tables and type info keyed by file hash + compiler flags.
- **SAST cache**: package-level graphs keyed by transitive content and config hash.
- **Formatter cache**: formatter version and options to avoid redundant runs.

### 6.2 Parallelism
- Work-stealing pool for parse/bind per file or package.
- Diff/Lift parallel per file; Composer single-threaded for determinism, with parallel pre-bucketing by target.
- Type-check parallelizable per module when the language toolchain supports it.

### 6.3 Big-Repo Pruning
- Bloom filters on changed AddressIDs and SymbolIDs to limit graph loads.
- Watchlists for touched packages/namespaces to scope type-check to affected modules.

### 6.4 Resource Caps
- Configurable memory ceiling; evict least-recent caches under pressure.
- File size and AST node count hard limits with graceful fallback to text merge.

---

## 7. Emission and Formatting

- **CST mapping**: every SAST node holds stable references to source spans and trivia attachments.
- **Reattachment**: after transforms, map old trivia to new nodes by SymbolID and structural anchors.
- **Formatting**: run project formatter exactly on touched files; enforce original newline and encoding.
- **Whitespace control**: diff output filtered to limit pure whitespace changes outside modified ranges.

---

## 8. Validation

- **Type-check**:
  - Call into backend compiler in no-emit mode with project config (tsconfig, csproj, pom/gradle).
  - Collect diagnostics and map to Ops via node provenance.
- **Tests** (optional):
  - Invoke repo-configured commands; capture status and key logs.
- **Failure mapping**:
  - Produce a minimal unsatisfiable Op set using greedy reduction guided by diagnostics.

---

## 9. Git and Storage

- **Merge driver**:
  - Reads OIDs for base/ours/theirs; runs the pipeline; writes merged files to temp; sets exit code by success/conflict.
- **Rebase driver**:
  - Replays Op Logs per commit; materializes trees; stops on conflict.
- **Op Log storage**:
  - Default: Git notes under a reserved namespace, keyed by commit id, with content-addressed chunks for large logs.
  - Alternative: repository folder ignored by Git, or external artifact store (CI only).
- **Provenance**:
  - Each Op carries capture revision and author-id to support auditing.

---

## 10. Observability

- **Structured logging**: phase timings, cache hit rates, counts of Ops and conflicts, memory usage.
- **Trace mode**: dump Op Logs, commutation decisions, CRDT states, and mapping tables.
- **Metrics**: merges attempted/succeeded, conflicts per KLoC, formatter runs, type-check latency buckets.
- **Artifacts**: machine-readable conflict reports and merge summaries for CI.

---

## 11. Security and Privacy

- Offline by default. No network calls unless explicitly configured.
- Redact source content in logs; minimal code slices only when requested.
- Temp files created in private directories; wiped on completion.
- Language tools executed with sandboxed file access where supported.

---

## 12. Language Backend Notes (P0)

### 12.1 TypeScript
- Parse/bind via compiler API with project references and path mapping.
- Symbol graph includes exports/imports, ambient declarations, and JSX elements.
- Rewrites:
  - Update import/export specifiers and paths on rename/move.
  - Adjust named vs positional arguments on signature changes with defaults.
- Formatting: Prettier or project formatter; preserve ESLint disable comments.

### 12.2 Java
- Parse/bind with a compiler-grade frontend that resolves classpaths and modules.
- Moves across packages update package statements and file paths.
- Overload/override checks ensure post-merge calls resolve to intended targets.
- Formatting: google-java-format or project tool.

### 12.3 C#
- Parse/bind with Roslyn workspaces; handle partial types and using-aliases.
- Namespace changes rewrite file-scoped/traditional forms correctly.
- Attribute and nullable context respected during signature calculations.
- Formatting: dotnet formatter or Roslyn formatting services.

---

## 13. Conflict Strategy

- Conflicts are **surgical**: node-scoped, with the two exact Ops and a minimal slice.
- Suggestions:
  - For DivergentRename: pick A, pick B, or create alias (language permitting).
  - For IncompatibleSignature: adopt superset signature, or split overloads if legal.
  - For DeleteVsEdit: restore or finalize delete with callsite cleanups listed.

---

## 14. Configuration Surface

- Repository file controls:
  - Language backend selection per glob.
  - Compiler/formatter flags passthrough.
  - Resource caps and timeouts.
  - CI policies: require type-check, require tests, require zero conflicts.
- `.gitattributes` entries route files to semantic driver; others fall back to text.

---

## 15. Performance Budgets

- 1M LOC repo, ≤200 changed files:
  - Cold parse+bind budget: 40 s on 8 logical cores.
  - Warm cache: ≤10 s end-to-end for typical merges.
  - Memory headroom: default 4–8 GB cap with adaptive cache eviction.

---

## 16. Testing Strategy

- **Golden merges**: curated repos with parallel refactors and expected merged trees.
- **Metamorphic tests**: re-run merges after file shuffles and whitespace noise; expect identical outputs.
- **Fuzzing**: random rename/move/signature edits under type constraints; ensure convergence or targeted conflicts.
- **Determinism tests**: repeat runs across OSes; byte-identical outputs.
- **Performance tests**: synthetic big repos; measure cache efficacy and scaling.

---

## 17. Risks and Mitigations

- **Ambiguous identity for weakly-typed code**: use conservative lifting; prefer text merge on low confidence; require type-check gates.
- **Macro and generated code**: detect via config and comments; bypass to text merge with warnings.
- **Formatter instability**: pin formatter versions; capture options; rerun on drift.
- **Toolchain variance**: hash configs and tool versions into cache keys; fail fast on mismatches.

---

## 18. Future Extensions

- Kotlin, Go, Python (type plugins), Swift, Rust (macro expansion hooks).
- Server-side merge service for Git hosting with worker pools.
- IDE previews that render Op-level conflicts inline.
- Cross-language symbol moves in polyglot monorepos via build graph integration.

---

## 19. Example Flow (Parallel Refactor)

Scenario:
- A renames `Customer`→`Account`.
- B moves `CustomerService.process` to `billing.Processor.process` and extracts `validateInvoice`.

Flow:
1. Lift A: renameSymbol(Customer→Account).
2. Lift B: moveDecl(CustomerService.process→billing.Processor.process) + extractMethod(process→validateInvoice).
3. Compose: propagate rename through move; update imports and callsites via symbol graph; add extracted method and call.
4. Apply and emit: CST reattached; formatter run.
5. Verify: type-check passes; no conflicts.

---

## 20. ADR Summary (key choices)

- **Semantic-first** over text: reduces false conflicts and preserves intent.
- **SymbolID structural hashing**: stable identity across renames/moves.
- **Op Logs** per commit: composable and auditable history.
- **CRDT only for order**: convergence without changing semantics elsewhere.
- **Compiler-backed validation**: correctness tied to actual language rules.
- **Determinism** by design: reproducible merges in CI and local.

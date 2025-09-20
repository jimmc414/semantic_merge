# Semantic Merge Engine — Requirements

> Normative terms **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**, and **MAY** are used as defined in common standards practice.

## 1. Scope

- [SCP-001] The system **SHALL** provide a semantic merge and rebase engine that operates on typed program structures rather than lines.
- [SCP-002] The system **SHALL** integrate with Git as a merge driver and rebase driver.
- [SCP-003] The initial scope **MUST** target large codebases and parallel refactors.
- [SCP-004] The system **SHALL** support TypeScript, Java, and C# in the first release.

## 2. Definitions

- [DEF-001] **SAST**: a structured IR that combines a typed AST, symbol table, and call graph.
- [DEF-002] **CST**: concrete syntax tree or token stream carrying whitespace and comments (“trivia”).
- [DEF-003] **Op**: a typed, semantic change with parameters, guards (preconditions), and effects.
- [DEF-004] **Op Log**: an ordered list of Ops representing `base→rev` transformation.
- [DEF-005] **CRDT Sequence**: list CRDT (RGA/LSEQ class) for deterministic sibling ordering.
- [DEF-006] **SymbolID**: logical identifier for a declaration stable across moves and renames.
- [DEF-007] **AddressID**: fully qualified name and signature at a specific revision.

## 3. Actors

- [ACT-001] **Developer**: invokes merges, rebases, or CLI.
- [ACT-002] **CI**: runs non-interactive merges, verification, and gates.
- [ACT-003] **VCS Host**: calls server-side merge hooks.

## 4. High-level Goals

- [HIG-001] The engine **SHALL** auto-merge parallel refactors without text conflicts where semantics allow.
- [HIG-002] The engine **MUST** preserve formatting and comments.
- [HIG-003] The engine **MUST** produce deterministic results for identical inputs.

## 5. Functional Requirements

### 5.1 Parsing and IR

- [IR-001] The system **MUST** parse `base`, `A`, and `B` into SAST per supported language.
- [IR-002] The system **MUST** build symbol tables and resolve references for each SAST.
- [IR-003] The system **SHALL** retain CST trivia and a mapping from SAST nodes to CST spans.
- [IR-004] The system **MUST** compute `SymbolID` using a normalized subtree hash that ignores identifier names but preserves structure and types.
- [IR-005] The system **MUST** compute `AddressID` as language-appropriate FQN + signature.
- [IR-006] The system **SHALL** persist a cross-map between `SymbolID` and `AddressID` for each rev during diffing.

### 5.2 Op Extraction (Three-way Semantic Diff)

- [OPX-001] The system **MUST** compute move-aware SAST diffs `ΔA` and `ΔB` using a tree-diff algorithm with explicit move detection.
- [OPX-002] The system **SHALL** lift diffs into typed Ops, including at least:
  - `renameSymbol`, `moveDecl`, `addDecl`, `deleteDecl`
  - `changeSignature` (params, return type, visibility)
  - `reorderParams`, `addParam{default}`, `removeParam`
  - `extractMethod/Function`, `inlineMethod/Function`
  - `updateCall` (callsite rewrites)
  - `editStmtBlock` with statement-level list Ops
  - `reorderImports`, `modifyImport`, `modifyNamespace/Package`
  - `moveFile`, `renameFile`
- [OPX-003] Each Op **MUST** include guards referencing `SymbolID` and expected types.
- [OPX-004] Each Op **MUST** be serializable as JSON and versioned (schema version field).
- [OPX-005] The system **SHALL** store per-commit Op Logs in Git notes by default. A repository config key **MAY** override the storage location.

### 5.3 Op Composition (Merge)

- [OPC-001] The engine **MUST** compose `ΔA` and `ΔB` at the Op level with deterministic rules.
- [OPC-002] Ops that commute **SHALL** be applied in a canonical order defined by `(op-type precedence, author timestamp, op-id)`.
- [OPC-003] The engine **MUST** propagate renames and moves across dependent Ops by tracking `SymbolID` through changing `AddressID`s.
- [OPC-004] Divergent operations on the same `SymbolID` that cannot be reconciled **MUST** raise targeted conflicts (see §5.7).
- [OPC-005] Delete vs edit on the same `SymbolID` **MUST** raise a conflict with a minimal slice of affected code.

### 5.4 CRDT-based Ordering

- [CRD-001] The engine **MUST** use a list CRDT for order-only sequences: imports, parameter lists, argument lists, statement blocks, class members where order is semantically irrelevant but stylistically relevant.
- [CRD-002] CRDT elements **MUST** be keyed by `SymbolID` or statement-local stable tokens.
- [CRD-003] The CRDT tiebreak **MUST** be deterministic using `(commit time, author-id, op-id)`.
- [CRD-004] The CRDT **MUST NOT** alter program semantics; if order affects semantics for a sequence, the engine **SHALL** disable CRDT for that sequence and use language rules.

### 5.5 Validation

- [VAL-001] After composition, the engine **MUST** apply the merged Op Log to `base SAST` to produce a merged SAST.
- [VAL-002] The engine **MUST** run the language type-checker or compiler in “no-emit” mode.
- [VAL-003] If type-check fails, the engine **MUST** report the minimal set of Ops whose application causes failure and mark the merge as conflicted.
- [VAL-004] The engine **MAY** run configured test commands; CI integration **SHALL** surface pass/fail.

### 5.6 Formatting and Emission

- [FMT-001] The engine **MUST** reattach CST trivia to corresponding SAST nodes after transformation.
- [FMT-002] The engine **MUST** run the project’s configured formatter (e.g., Prettier, clang-format, ktlint) on modified files.
- [FMT-003] The engine **MUST NOT** introduce unrelated whitespace-only diffs outside modified regions.
- [FMT-004] The engine **SHALL** preserve original newline conventions and encoding per file.

### 5.7 Conflict Detection and Reporting

- [CFR-001] The engine **MUST** emit conflicts at the Op or node level, not as whole-file hunks.
- [CFR-002] Conflict categories **MUST** include at minimum:
  - Divergent rename of same `SymbolID`
  - Move to different destinations
  - Incompatible signature changes
  - Delete vs edit
  - Concurrent edits to the same statement with overlapping token ranges
  - Extract vs inline on the same body
- [CFR-003] Each conflict report **MUST** include: `SymbolID`, current `AddressID`s, op pairs, suggested resolutions, and a minimal code slice.
- [CFR-004] The CLI **SHALL** exit with nonzero status if any conflicts remain.

### 5.8 Fallbacks

- [FBK-001] If a file cannot be parsed or the language is unsupported, the engine **MUST** fall back to Git’s text 3-way merge for that file only.
- [FBK-002] If formatter fails, the engine **SHALL** emit syntactically correct code without formatting and warn.
- [FBK-003] If type-check tooling is unavailable, the engine **SHALL** warn and proceed, unless repository policy **MUST** require verification.

### 5.9 Git Integration

- [GIT-001] The distribution **MUST** include a merge driver and attributes configuration instructions.
- [GIT-002] `.gitattributes` patterns **SHALL** map file globs to the semantic merge driver.
- [GIT-003] The merge driver **MUST** accept Git OIDs for `base`, `ours`, `theirs` and write merged content to stdout or temp file as required by Git.
- [GIT-004] The rebase driver **MUST** replay Op Logs across new bases instead of line hunks.
- [GIT-005] The engine **MUST NOT** modify Git history; it **SHALL** operate within standard 3-way semantics.

### 5.10 CLI

- [CLI-001] The tool **SHALL** provide:
  - `semdiff <rev1> <rev2> --ops`
  - `semmerge <base> <A> <B>`
  - `semrebase <branch> --onto <newbase>`
  - `semverify [--tests]`
  - `semtrace <rev>`
- [CLI-002] All commands **MUST** support `--json` output.
- [CLI-003] All commands **MUST** be deterministic and reproducible given identical repository state.

### 5.11 CI Integration

- [CI-001] A CI mode **SHALL** run merges non-interactively and fail builds on conflicts or verification failures.
- [CI-002] CI output **MUST** include a machine-readable artifact of the conflict report.

### 5.12 IDE Preview (Optional P1)

- [IDE-001] An IDE extension **MAY** preview semantic merges and conflicts inline.
- [IDE-002] The extension **MUST NOT** alter merge logic; it **SHALL** be a thin client over CLI output.

## 6. Language-specific Requirements

### 6.1 TypeScript (P0)

- [TS-001] The engine **MUST** use the TypeScript compiler API for AST and type info.
- [TS-002] `renameSymbol` **MUST** update imports, exports, and callsites across project references.
- [TS-003] `changeSignature` **MUST** propagate defaulted parameters and handle named and positional arguments.
- [TS-004] The engine **MUST** respect module resolution settings (`tsconfig.json`).

### 6.2 Java (P0)

- [JV-001] The engine **MUST** use a compiler-grade parser (e.g., JDT or equivalent) with type resolution.
- [JV-002] Package and class moves **MUST** update imports and file paths.
- [JV-003] Overload/override resolution **MUST** be type-correct post-merge.

### 6.3 C# (P0)

- [CS-001] The engine **MUST** use Roslyn for parsing and symbol binding.
- [CS-002] Namespace and partial class merges **MUST** remain compilable.
- [CS-003] Using-directives reordering **SHALL** use CRDT sequence rules.

## 7. Non-functional Requirements

### 7.1 Determinism and Correctness

- [NFR-DET-001] Given identical inputs (Git trees, configs, clocks normalized), results **MUST** be byte-identical.
- [NFR-DET-002] Randomized algorithms **MUST** use fixed seeds derived from commit hashes.

### 7.2 Performance and Scalability

- [NFR-PERF-001] The engine **MUST** cache per-file parse and type artifacts keyed by content hash.
- [NFR-PERF-002] The engine **SHALL** parallelize by file/package where safe.
- [NFR-PERF-003] On a codebase of 1M LOC with ≤200 changed files, a merge **SHOULD** complete within 60 seconds on 8 logical cores; if exceeded, the engine **SHALL** emit progress and per-phase timings.
- [NFR-PERF-004] Memory usage **MUST NOT** exceed a configurable cap; on reaching the cap the engine **SHALL** shed caches and continue.

### 7.3 Security and Privacy

- [NFR-SEC-001] The engine **MUST NOT** transmit repository contents off-host unless explicitly configured.
- [NFR-SEC-002] Telemetry **MUST** be opt-in and **MUST NOT** include source content or identifiers.
- [NFR-SEC-003] Temporary files **MUST** be created with restrictive permissions and deleted on success or failure.

### 7.4 Observability

- [NFR-OBS-001] The engine **SHALL** provide structured logs with per-phase timings and cache hit rates.
- [NFR-OBS-002] A `--trace` mode **MUST** dump Op Logs, resolution decisions, and CRDT states.

### 7.5 Extensibility

- [NFR-EXT-001] Language backends **MUST** be plugin modules with a stable interface for parse, resolve, diff, lift, apply, and format.
- [NFR-EXT-002] Op schema versions **MUST** support forward/backward compatibility or fail with a clear error.

## 8. Data Schemas

### 8.1 Op JSON (minimum fields)

- [SCH-OP-001] Each Op **MUST** include:
  - `id` (uuid), `schemaVersion`, `type`
  - `target` `{ symbolId, addressId? }`
  - `params` (op-specific)
  - `guards` (preconditions)
  - `effects` (postconditions summary)
  - `provenance` `{ rev, author, timestamp }`

### 8.2 Conflict Report JSON

- [SCH-CF-001] Each conflict **MUST** include:
  - `symbolId`, `addressIds`
  - `opA`, `opB`
  - `category`
  - `minimalSlice` (code excerpt with ranges)
  - `suggestions` (merge choices or rewrites)

## 9. Resolution Rules (Samples)

- [RES-001] `rename(X, a→b)` composed with `move(X, p→q)` **SHALL** apply move on `SymbolID` then rewrite address to `q.b`.
- [RES-002] Two `rename` on same `SymbolID` to different names **MUST** conflict as `DivergentRename`.
- [RES-003] `changeSignature(f)` with `updateCall(f)` **SHALL** commute if all affected calls are updated; otherwise **MUST** conflict listing missing callsites.
- [RES-004] Two `extractMethod` from same block with identical bodies **SHALL** deduplicate and keep one declaration; with different bodies **SHALL** keep both.

## 10. Configuration

- [CFG-001] Repository-level config file (e.g., `.semmerge.toml`) **SHALL** control language backends, formatters, CI policies, and resource caps.
- [CFG-002] Per-language settings **MUST** allow passing through compiler flags and project files.
- [CFG-003] Policies **MAY** enforce “type-check required” or “tests required”; when enforced the engine **MUST** fail merges on violation.

## 11. Error Handling

- [ERR-001] All errors **MUST** include a machine-readable code and human-readable message.
- [ERR-002] Partial successes **MUST** indicate which files merged and which remain conflicted.
- [ERR-003] Unexpected exceptions **MUST** produce a diagnostic bundle when `--trace` is set.

## 12. Acceptance Criteria

- [ACC-001] On a repository where branch A performs `renameSymbol(Customer→Account)` and branch B performs `moveDecl(CustomerService.process→billing/Processor.process)` and `extractMethod(process→validateInvoice)`, the engine **MUST** produce a merged result with updated imports and callsites, both the moved method and the extracted method present, and no conflicts.
- [ACC-002] On divergent rename of the same `SymbolID`, the engine **MUST** surface exactly one `DivergentRename` conflict with a minimal slice.
- [ACC-003] On concurrent independent additions to the same import list, the engine **MUST** converge both entries without conflict via CRDT.
- [ACC-004] On delete vs edit of the same declaration, the engine **MUST** report a conflict pointing to the declaration and its edit, not the full file.
- [ACC-005] Running the same merge twice **MUST** yield byte-identical outputs, logs, and reports.

## 13. Constraints and Limits

- [LIM-001] The engine **MUST NOT** attempt semantic equivalence proofs beyond type-checking and configured tests.
- [LIM-002] Macros, generated code, and dynamic features that defeat static typing **MUST** fall back to conservative behavior or text merge with warning.
- [LIM-003] For C++ and Rust, macro expansion and proc-macro handling **MUST** be explicit scope-gated in future releases and **MUST NOT** be assumed in P0.

## 14. Security and Compliance

- [COM-001] Logs and Op artifacts **MUST NOT** contain source content beyond minimal slices unless `--include-content` is set.
- [COM-002] The engine **SHALL** respect repository `.gitignore` for temporary artifacts.

## 15. Packaging and Platform

- [PKG-001] The CLI **MUST** run on Linux, macOS, and Windows.
- [PKG-002] The tool **MUST** provide offline operation with no network dependency by default.

## 16. Documentation

- [DOC-001] The project **SHALL** ship with:
  - Installation and Git integration guide
  - Language backend notes
  - Conflict categories reference
  - JSON schema references for Ops and conflicts
- [DOC-002] All examples **MUST** be reproducible via sample repositories.

## 17. Roadmap Gates (Non-normative, tracked for release readiness)

- [RM-TS] TypeScript backend complete with `rename`, `moveDecl`, `changeSignature`, `extract/inline`, CRDT ordering, Prettier integration.
- [RM-JV/CS] Java and C# backends complete with type-check integration and formatter hooks.

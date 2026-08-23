<p align="center">
  <h1 align="center">dataform-context-mcp</h1>
</p>

<p align="center">
  <strong>Language:</strong>
  <a href="README.md">Français</a> |
  <a href="README.en.md">English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/MCP-stdio-6E56CF" alt="MCP stdio" />
  <img src="https://img.shields.io/badge/Dataform-3.x-4285F4?logo=googlecloud&logoColor=white" alt="Dataform 3.x" />
  <img src="https://img.shields.io/badge/runtime-no%20network%20%C2%B7%20no%20LLM-2EA44F" alt="No network, no LLM" />
</p>

<p align="center">
  <strong>Give your coding agent (Claude Code, Cursor) reliable, always-fresh knowledge
  of your Dataform pipeline — table and column lineage, schemas, impact analysis —
  instead of letting it read <code>.sqlx</code> files one by one and hallucinate the DAG.</strong>
</p>

---

## Install with Claude Code

Prerequisites (once per machine): [uv](https://docs.astral.sh/uv/) (`brew install uv`)
and `@dataform/cli` ≥ 3.0 (`npm i -g @dataform/cli`).

At the root of **your Dataform repo**, create or extend `.mcp.json`
(template: [`.mcp.json.example`](.mcp.json.example)):

```json
{
  "mcpServers": {
    "dataform-context": {
      "type": "stdio",
      "command": "/opt/homebrew/bin/uvx",
      "args": ["--from", "git+ssh://git@github.com/vgossiaux/dataform-context-mcp",
               "dataform-context", "serve"]
    }
  }
}
```

That's it: no clone, no `--repo` (the server indexes the current directory). Open a
Claude Code session in the repo and type `/mcp`: `dataform-context` should show as
connected. First call takes ~15 s (initial compilation), then ~10 ms.

> [!IMPORTANT]
> **Absolute path to `uvx` is required**: a bare `"command": "uvx"` fails (`ENOENT`)
> when the agent is launched from a non-login shell whose PATH lacks
> `/opt/homebrew/bin`. Same caution applies in CI.

**Verify from the agent**: just ask "run check_setup" — the tool diagnoses the whole
installation (dataform CLI, compilation, index, lineage coverage, goldens). Or copy
[`integrations/claude-code/commands/dataform-context-verify.md`](integrations/claude-code/commands/dataform-context-verify.md)
into your repo's `.claude/commands/` to get `/dataform-context-verify`.

Recommended: add the agent-instruction block to the repo's `CLAUDE.md` (see
[Getting the agent to adopt the tools](#getting-the-agent-to-adopt-the-tools)).

## Install with Cursor

Same server, standard MCP stdio. Copy
[`integrations/cursor/mcp.json.example`](integrations/cursor/mcp.json.example) to your
repo's `.cursor/mcp.json`, and the rule
[`integrations/cursor/rules/dataform-context.mdc`](integrations/cursor/rules/dataform-context.mdc)
to `.cursor/rules/`. All integration material is summarized in
[`integrations/README.md`](integrations/README.md) (French).

---

## Why

A coding agent working on a Dataform repo reads `.sqlx` files one by one. Observed
consequences in real conditions: invented columns or tables, upstream dependencies
missed during refactors, underestimated downstream impact — the
`staging → intermediate → marts → assertions` cascade is never seen as a whole.

| Without a system | With dataform-context-mcp |
|---|---|
| The agent greps `ref()` calls and guesses the DAG | The DAG comes from the Dataform compiler itself (`dependencyTargets`) |
| "What breaks if I change this?" = partial re-reading | `impact_analysis`: full blast radius, assertions included, in one call |
| A column's origin gets lost across CTEs | `get_column_lineage`: full chain with SQL transformation expressions |
| An unresolvable lineage looks like "no dependency" | Explicit statuses + `complete: false` + `warnings` — **never a false empty** |
| Context frozen at read time | Lazy re-indexing on content hash at every call |

**Deterministic and self-hosted**: no LLM, no network calls, no warehouse access at
runtime. Same files → same index → same answers.

```
.sqlx + includes/ ──▶ dataform compile --json ──▶ CompiledGraph parsing
                                                        │
        Local SQLite (~/.cache/dataform-context-mcp/)  ◀┘
        • actions, layers, documented columns
        • table-level edges (source: compiler dependencyTargets)
        • column-level edges (sqlglot, explicit statuses)
                                                        │
        MCP stdio server (7 tools) ◀────────────────────┘
```

## The 8 tools

| Tool | Example question to ask the agent |
|---|---|
| `get_table_context(name)` | "Describe the ref_brand table" |
| `get_upstream(name, depth)` | "What does mart_kpis depend on?" |
| `get_downstream(name, depth)` | "Who reads staging_events?" |
| `find_tables_by_layer(layer)` | "List the mart tables" |
| `get_column_lineage(table, column, …)` | "Where does the total_amount column come from?" |
| `impact_analysis(name, column?)` | "What breaks if I rename page_type?" |
| `check_setup()` | "Check that dataform-context is properly installed" |
| `refresh_index()` | "Force a reindex" |

- **Tolerant name resolution**: `my_table`, `dataset.my_table`, full canonical name or
  `.sqlx` file path — with suggestions on errors.
- **Layers discovered dynamically** from file paths
  (`definitions/transforms/<NN_name>/`, `definitions/sources/`…) — no hardcoded
  convention.
- **Every response embeds `index_meta`**: freshness, source hash, counts, last
  compilation status.

## Getting the agent to adopt the tools

Block to add to the Dataform repo's `CLAUDE.md` (or Cursor rules):

> ## Pipeline context: dataform-context MCP
> Before reading `.sqlx` files or modifying a table: `get_table_context` (schema +
> neighbors), `get_upstream`/`get_downstream` (DAG), `impact_analysis` (mandatory before
> any table or column refactor), `find_tables_by_layer` (layer scope),
> `get_column_lineage` (column origin). These tools are generated from
> `dataform compile`: they are authoritative for the DAG, unlike a partial file read.
> `complete: false` = unknown lineage, not "no dependency". After editing `.sqlx`
> files, the index refreshes itself (content hash).

## Reading column lineage responses — the "never a false empty" contract

Static extraction has known limits (MERGE, `SELECT *` over an undocumented source,
multi-statement scripts). The absolute rule: **an empty lineage is only presented as
"no dependency" when it is certain.** Otherwise, it says so:

- Every table carries an **extraction status** (`ok`, `partial`, `failed`,
  `not_attempted`, `source`), always with a reason.
- `get_column_lineage` returns `complete: false` + `warnings` (opaque tables
  encountered) when the lineage is unknown beyond some point — distinct from
  `complete: true` + `edges: []` (true absence, e.g. `CURRENT_DATE()`).
- `impact_analysis(column=…)` returns `possibly_affected`: downstream tables whose
  column impact is unknown. **Never exclude them from a refactor.**

Category details and surfacing: [`docs/lineage-limits.md`](docs/lineage-limits.md) (French).

<details>
<summary><strong>CLI (without an agent)</strong></summary>

From a local clone (`uv sync` first), or via
`uvx --from git+ssh://git@github.com/vgossiaux/dataform-context-mcp dataform-context …`:

```bash
dataform-context index            # compile + (re)build the current repo's index
dataform-context report           # summary: layers, edges, lineage coverage
dataform-context report --table my_table    # JSON context of one table
dataform-context serve            # MCP server (stdio) — used by .mcp.json
dataform-context validate-golden --golden goldens.json   # manual oracle
```

`--repo /path` on any command to target another repo. `--db /path` to relocate the
index (default: `~/.cache/dataform-context-mcp/<hash>.db`).
</details>

<details>
<summary><strong>Index freshness (lazy re-indexing)</strong></summary>

- On **every** tool call, the server hashes the content of `definitions/**`,
  `includes/**` and `workflow_settings.yaml`. Unchanged hash → ~10 ms response.
  Changed hash → recompile + reindex (~2–15 s), then respond. The agent always works
  on the current state of the files, including its own in-session edits.
- If compilation fails (a file broken mid-edit), the **last good index** keeps being
  served, with `index_meta.compile_status: "error"` and the message. Never an empty
  index.
- The index lives outside the repo (`~/.cache/dataform-context-mcp/`) — nothing to
  gitignore.
</details>

<details>
<summary><strong>Golden sets: validate lineage on your repo</strong></summary>

Without an external source of truth, the oracle is human: you hand-trace a few columns
you know well, and the tool must find exactly those edges. Format
(`golden_columns.json`, a list of entries):

```json
[
  {
    "table": "my_dataset.my_table",
    "column": "my_column",
    "direction": "upstream",
    "depth": 1,
    "expected_edges": ["upstream_ds.upstream_table.col -> my_dataset.my_table.my_column"],
    "expect_complete": true
  }
]
```

`validate-golden` prints PASS/FAIL per entry with a readable diff (missing / extra
edges) and exits 1 on any mismatch — CI-friendly. Tip: cover 1 passthrough,
1 aggregation, 1 chain of 3+ tables, 1 incremental table, 1 tricky case (UNNEST/macro).
</details>

<details>
<summary><strong>Governance & audit</strong></summary>

Designed to pass a corporate security review before deployment on a client repo:

- **Exhaustive runtime dependencies**: `mcp` (official Model Context Protocol SDK) and
  `sqlglot` — exact pins in `uv.lock`; everything else is stdlib (`sqlite3`,
  `argparse`, `hashlib`, `difflib`).
- **Zero network calls at runtime**: reads the repo's files + local
  `dataform compile --json` shell-out. No warehouse access, no telemetry.
- **Zero LLM at runtime**: deterministic parsing (Dataform compiler + sqlglot).
- **Local data only**: SQLite index in `~/.cache/dataform-context-mcp/`.
- **This repo contains no client metadata**: synthetic fixtures, aggregated reports
  only.
</details>

<details>
<summary><strong>Known limits</strong></summary>

- Column lineage is incomplete by construction for: `SELECT *` over a source without a
  documented schema, MERGE/DML, multi-statement scripts — always **surfaced**
  (statuses, `warnings`, `possibly_affected`), never hidden. Lever: documenting the
  `columns` of declarations in their `config {}` mechanically unlocks `SELECT *`
  expansion (measured: +28 coverage points on one pilot repo).
- Observed coverage on two pilot repos: 91% and 63% of tables `ok` — the second gap is
  structural (staging doing `SELECT *` over undocumented sources), analyzed in
  [`docs/lineage-limits.md`](docs/lineage-limits.md).
- `dataform compile` (Node) is a runtime dependency: if missing, indexing fails
  cleanly and the previous index keeps being served.
</details>

<details>
<summary><strong>Code architecture & tests</strong></summary>

```
src/dataform_context_mcp/
├── compile.py     # subprocess dataform compile --json; structured errors
├── model.py       # CompiledGraph dataclasses (Target, Action, ...)
├── layers.py      # layer inference from file paths
├── staleness.py   # content hash of source files
├── db.py          # SQLite: DDL, rebuild, name resolution, recursive traversals
├── lineage.py     # sqlglot column extraction, explicit statuses, topological order
├── indexer.py     # ensure_fresh: lazy reindex + last-good fallback
├── server.py      # the 7 MCP tools (stdio)
└── cli.py         # index | report | serve | validate-golden
```

Local development:

```bash
git clone git@github.com:vgossiaux/dataform-context-mcp.git
cd dataform-context-mcp
uv sync && uv run pytest        # 74 tests
```

Tests rely on a **synthetic, compilable mini Dataform repo**
(`tests/fixtures/mini_repo/`) — no test touches a real repo.
`uv run pytest -m "not integration"` runs without Node.
</details>

<details>
<summary><strong>Quick troubleshooting</strong></summary>

| Symptom | Cause | Fix |
|---|---|---|
| `/mcp`: server error `ENOENT ... uv` | PATH without homebrew (non-login shell) | Absolute path `/opt/homebrew/bin/uvx` in `.mcp.json` |
| `compile error` in `index_meta` | A `.sqlx` doesn't compile | Run `dataform compile` in the repo to see the error; the previous index keeps being served |
| `not_found` with suggestions | Approximate table name | Pick a suggestion, or use `dataset.table` |
| Slow first call (~15 s) | Initial compilation + extraction | Normal; subsequent calls ~10 ms |
</details>

## Roadmap

- License (prerequisite for going open source).
- **Batch, offline, self-hosted LLM** semantic enrichment of undocumented columns —
  never at MCP runtime.
- Mermaid/graphviz graph export; PreToolUse hook suggesting `impact_analysis` before
  `.sqlx` edits.

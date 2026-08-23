# dataform-context-mcp

**Donnez à votre agent de code (Claude Code, bientôt Cursor) une connaissance fiable et
à jour de votre pipeline Dataform — lineage, schémas, analyse d'impact — au lieu de le
laisser relire les `.sqlx` un par un et halluciner sur le DAG.**

MCP server Python **déterministe et self-hosted** : aucun LLM, aucun appel réseau, aucun
accès BigQuery à l'exécution. Tout est construit localement depuis `dataform compile`.

---

## Le problème que ça résout

Un agent de code qui travaille sur un repo Dataform lit les fichiers `.sqlx` un par un.
Conséquences observées en conditions réelles : colonnes ou tables inventées, dépendances amont
oubliées lors d'un refactor, impact aval sous-estimé (la cascade `staging →
intermediate → marts → assertions` n'est jamais vue en entier).

`dataform-context-mcp` compile le projet (source de vérité : le compilateur Dataform
lui-même), indexe le graphe dans un SQLite local, extrait le lineage **colonne par
colonne** avec [sqlglot](https://github.com/tobymao/sqlglot), et expose le tout à
l'agent via 7 outils [MCP](https://modelcontextprotocol.io) typés. L'agent interroge au
lieu de deviner.

```
.sqlx + includes/ ──▶ dataform compile --json ──▶ parsing du CompiledGraph
                                                        │
        SQLite local (~/.cache/dataform-context-mcp/)  ◀┘
        • actions, couches, colonnes documentées
        • edges table-level (source : dependencyTargets du compilateur)
        • edges colonne-level (sqlglot, statuts explicites)
                                                        │
        Serveur MCP stdio (7 outils) ◀──────────────────┘
        ré-indexation lazy par hash de contenu à chaque appel
```

## Prérequis

| Outil | Pourquoi | Installation |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Gère Python et les dépendances (rien d'autre à installer côté Python) | `brew install uv` |
| Node.js + `@dataform/cli` ≥ 3.0 | `dataform compile` est la source de vérité du graphe | `npm i -g @dataform/cli` |

Vérifiez : `uv --version` et `dataform --version` répondent.

## Installation (état actuel : clone local)

```bash
git clone <ce-repo> dataform-graph-context
cd dataform-graph-context
uv sync            # crée .venv et installe les deps pinnées (uv.lock)
uv run pytest      # 73 tests, ~6 s — tout doit être vert
```

> **Roadmap** : après publication sur une forge Git, l'installation deviendra
> `uvx --from git+<url> dataform-context serve` — zéro clone (voir [Roadmap](#roadmap)).

## Brancher à Claude Code

À la racine de **votre repo Dataform** (pas de ce repo), créez ou complétez `.mcp.json`
(modèle : [`.mcp.json.example`](.mcp.json.example)) :

```json
{
  "mcpServers": {
    "dataform-context": {
      "type": "stdio",
      "command": "/opt/homebrew/bin/uv",
      "args": ["run", "--project", "/chemin/absolu/vers/dataform-context-mcp",
               "dataform-context", "serve"]
    }
  }
}
```

Pas de `--repo` à préciser : le serveur indexe par défaut le répertoire courant, et les
clients MCP (Claude Code, Cursor) lancent les serveurs de projet depuis la racine du
projet. Un repo différent peut toujours être visé explicitement avec
`"serve", "--repo", "/chemin/du/repo"`.

Puis ouvrez une session Claude Code dans le repo Dataform et tapez `/mcp` : le serveur
`dataform-context` doit apparaître connecté.

> ⚠️ **Chemin absolu de `uv` obligatoire** : un `"command": "uv"` nu échoue
> (`ENOENT`) quand Claude Code est lancé depuis un shell non-login dont le PATH ne
> contient pas `/opt/homebrew/bin` (constaté en test). Idem en CI.

Recommandé : ajoutez ce bloc au `CLAUDE.md` du repo Dataform pour que les agents
utilisent les outils spontanément :

> ## Contexte pipeline : MCP dataform-context
> Avant de lire des `.sqlx` ou de modifier une table : `get_table_context` (schéma +
> voisins), `get_upstream`/`get_downstream` (DAG), `impact_analysis` (obligatoire avant
> tout refactor de table ou colonne), `find_tables_by_layer` (périmètre d'une couche),
> `get_column_lineage` (origine d'une colonne). Ces outils sont générés depuis
> `dataform compile` : ils font foi sur le DAG, contrairement à une lecture partielle
> des fichiers. `complete: false` = lineage inconnu, pas « aucune dépendance ». Après
> édition de `.sqlx`, l'index se rafraîchit seul (hash de contenu).

## Les 7 outils MCP

| Outil | Ce que l'agent obtient | Exemple de question à poser à l'agent |
|---|---|---|
| `get_table_context(name)` | Schéma, couche, description, colonnes documentées, voisins directs | « Décris-moi la table ref_brand » |
| `get_upstream(name, depth)` | Dépendances amont par niveau (1–10) | « De quoi dépend mart_kpis ? » |
| `get_downstream(name, depth)` | Dépendants aval par niveau | « Qui lit staging_events ? » |
| `find_tables_by_layer(layer)` | Actions d'une couche (`01_staging`, suffixe `marts`…) | « Liste les tables du mart » |
| `get_column_lineage(table, column, direction, depth)` | Chaîne de transformation d'une colonne, expressions SQL incluses | « D'où vient la colonne total_amount ? » |
| `impact_analysis(name, column?)` | Blast radius complet : tables par couche, assertions, colonnes affectées | « Qu'est-ce qui casse si je renomme page_type ? » |
| `refresh_index()` | Rebuild forcé de l'index | « Force la ré-indexation » |

Détails utiles :

- **Résolution de noms tolérante** : `ma_table`, `dataset.ma_table`, canonical complet
  `projet.dataset.ma_table` ou chemin du fichier `.sqlx`. En cas d'erreur, la réponse
  contient des suggestions (`did you mean`).
- **Couches découvertes dynamiquement** depuis les chemins
  (`definitions/transforms/<NN_nom>/`, `definitions/sources/`…) — aucune convention
  hardcodée, fonctionne sur des repos aux couches différentes.
- **Toute réponse embarque `index_meta`** : fraîcheur de l'index, hash source, comptages,
  statut de la dernière compilation.

## Lire les réponses de lineage colonne — le contrat « jamais de faux vide »

L'extraction statique a des limites connues (MERGE, `SELECT *` sur une source non
documentée, scripts multi-statements). La règle absolue : **un lineage vide n'est
présenté comme « aucune dépendance » que s'il est certain.** Sinon, c'est dit.

- Chaque table porte un **statut d'extraction** : `ok`, `partial`, `failed`,
  `not_attempted`, `source` (tables sources déclarées) — visible dans
  `get_table_context` et le `report` CLI, toujours accompagné d'une raison.
- `get_column_lineage` renvoie `complete: false` + `warnings` (la liste des tables
  opaques rencontrées) quand le lineage est **inconnu au-delà d'un point** — à ne pas
  confondre avec `complete: true` + `edges: []` (vraie absence, ex. `CURRENT_DATE()`).
- `impact_analysis(column=...)` renvoie `possibly_affected` : les tables aval dont
  l'impact colonne est inconnu. **Ne jamais les exclure d'un refactor.**

Le détail des catégories non couvertes et leur surfaçage :
[`docs/lineage-limits.md`](docs/lineage-limits.md).

## Fraîcheur de l'index

- À **chaque** appel d'outil, le serveur hache le contenu de `definitions/**`,
  `includes/**` et `workflow_settings.yaml`. Hash inchangé → réponse en ~10 ms.
  Hash changé → recompilation + ré-indexation (~2–15 s selon la taille du repo), puis
  réponse. L'agent travaille donc toujours sur l'état courant des fichiers, y compris
  ses propres éditions en cours de session.
- Si la compilation échoue (fichier cassé en cours d'édition), le **dernier index
  valide** est servi, avec `index_meta.compile_status: "error"` et le message d'erreur.
  Jamais d'index vide.
- L'index vit dans `~/.cache/dataform-context-mcp/<hash-du-chemin>.db` — rien n'est
  écrit dans le repo Dataform.

## CLI (sans agent)

```bash
uv run dataform-context index  --repo /chemin/repo     # compile + (re)construit l'index
uv run dataform-context report --repo /chemin/repo     # résumé : couches, edges, couverture lineage
uv run dataform-context report --repo ... --table ma_table   # contexte JSON d'une table
uv run dataform-context serve  --repo /chemin/repo     # serveur MCP (stdio) — utilisé par .mcp.json
uv run dataform-context validate-golden --repo ... --golden goldens.json   # oracle manuel
```

Exemple de sortie `report` :

```
actions: 66
table_edges: 101
by layer:
  01_staging: 8
  02_referential: 24
  ...
column extraction:
  ok: 29  partial: 13  failed: 4  source: 20
  pct_ok (hors source): 63%
```

## Golden sets : valider le lineage colonne sur votre repo

Sans base de vérité externe, l'oracle est humain : vous tracez à la main quelques
colonnes que vous connaissez, l'outil doit retrouver exactement ces edges. Format
(`golden_columns.json`, liste d'entrées) :

```json
[
  {
    "table": "mon_dataset.ma_table",
    "column": "ma_colonne",
    "direction": "upstream",
    "depth": 1,
    "expected_edges": ["dataset_amont.table_amont.colonne -> mon_dataset.ma_table.ma_colonne"],
    "expect_complete": true
  }
]
```

`validate-golden` affiche PASS/FAIL par entrée avec le diff (edges manquants / en trop)
et sort en code 1 au moindre écart — utilisable en CI. Conseil : couvrez 1 passthrough,
1 agrégation, 1 chaîne de 3+ tables, 1 table incrémentale, 1 cas tordu (UNNEST/macro).

## Gouvernance & audit

Conçu pour passer une revue sécurité d'entreprise avant déploiement sur un repo client :

- **Dépendances runtime exhaustives** : `mcp` (SDK officiel Model Context Protocol,
  2.0.0) et `sqlglot` (30.17.0) — pins exacts dans `uv.lock` ; tout le reste est stdlib
  (`sqlite3`, `argparse`, `hashlib`, `difflib`).
- **Zéro appel réseau à l'exécution** : lecture des fichiers du repo + shell-out
  `dataform compile --json` local. Pas d'accès BigQuery, pas de télémétrie.
- **Zéro LLM à l'exécution** : parsing déterministe (compilateur Dataform + sqlglot).
  Mêmes fichiers → même index → mêmes réponses.
- **Données locales uniquement** : index SQLite dans `~/.cache/dataform-context-mcp/`.
- **Ce repo ne contient aucune métadonnée client** : fixtures synthétiques, rapports
  agrégés, goldens locaux gitignorés (`local/`).

## Limites connues

- Lineage colonne incomplet par construction sur : `SELECT *` au-dessus d'une source
  sans schéma documenté, MERGE/DML, scripts multi-statements — toujours **surfacé**
  (statuts, `warnings`, `possibly_affected`), jamais masqué. Levier : documenter les
  `columns` des declarations dans les `config {}` débloque mécaniquement l'expansion
  des `SELECT *` (mesuré : +28 points de couverture possibles sur un des deux repos
  pilotes).
- `dataform compile` (Node) est une dépendance d'exécution : absente → l'indexation
  échoue proprement (`CompileError`), l'index précédent reste servi.
- Couverture mesurée sur les 2 repos pilotes (2026-08-23) : 91 % et 63 % de tables
  `ok` — l'écart du second est structurel (staging en `SELECT *` sur sources non
  documentées), analysé dans [`docs/lineage-limits.md`](docs/lineage-limits.md).

## Architecture du code

```
src/dataform_context_mcp/
├── compile.py     # subprocess dataform compile --json ; erreurs structurées
├── model.py       # dataclasses du CompiledGraph (Target, Action, ...)
├── layers.py      # inférence de couche depuis le chemin du fichier
├── staleness.py   # hash de contenu des sources
├── db.py          # SQLite : DDL, rebuild, résolution de noms, traversées (CTE récursives)
├── lineage.py     # extraction colonne sqlglot, statuts explicites, ordre topologique
├── indexer.py     # ensure_fresh : ré-indexation lazy + fallback last-good
├── server.py      # les 7 outils MCP (stdio)
└── cli.py         # index | report | serve | validate-golden
```

Tests : `tests/` (73), dont un **mini repo Dataform synthétique compilable**
(`tests/fixtures/mini_repo/`) qui sert de vérité de bout en bout — aucun test ne touche
un repo client. `uv run pytest -m "not integration"` tourne sans Node.

## Roadmap

**Phase produit (T12 — planifiée, voir `docs/superpowers/plans/`)** :

- Publication sur une **forge Git** → installation sans clone :
  `uvx --from git+<url> dataform-context serve`.
- Support **Cursor** documenté (`.cursor/mcp.json` — même serveur, MCP stdio standard).
- Outil MCP **`check_setup()`** : l'agent diagnostique lui-même l'installation
  (dataform présent, compile OK, couverture, goldens) — les vérifications se font
  dans la CLI de l'agent, sans quitter la session.
- Commande projet `/dataform-context:verify` (Claude Code) + règle `.cursor/rules`.
- `--repo` par défaut = répertoire courant ; CI (pytest + ruff) ; licence.

**Itération 2 (hors scope MVP)** : enrichissement sémantique **batch, hors session, via
LLM self-hosted** des colonnes non documentées (~50 % du graphe mesuré) — jamais au
runtime MCP ; documentation des schémas des declarations sources ; export mermaid/graphviz ;
hook PreToolUse suggérant `impact_analysis` avant édition de `.sqlx`.

## Dépannage express

| Symptôme | Cause | Fix |
|---|---|---|
| `/mcp` : serveur en erreur `ENOENT ... uv` | PATH sans homebrew (shell non-login) | Chemin absolu `/opt/homebrew/bin/uv` dans `.mcp.json` |
| `compile error` dans `index_meta` | Un `.sqlx` ne compile pas | `dataform compile` dans le repo pour voir l'erreur ; l'index précédent reste servi |
| `not_found` avec suggestions | Nom de table approximatif | Reprendre une suggestion, ou `dataset.table` |
| Réponses qui semblent périmées | (ne devrait pas arriver — hash par appel) | `refresh_index()` puis vérifier `index_meta.source_hash` |
| Premier appel lent (~15 s) | Compilation + extraction initiales | Normal ; les appels suivants ~10 ms |

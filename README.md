<p align="center">
  <h1 align="center">
    <img src="docs/assets/logo-lockup.png" alt="Dataform Context" width="420">
  </h1>
</p>

<p align="center">
  <strong>Langue :</strong>
  <a href="README.md">Français</a> |
  <a href="README.en.md">English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/MCP-stdio-6E56CF" alt="MCP stdio" />
  <img src="https://img.shields.io/badge/Dataform-3.x-4285F4?logo=googlecloud&logoColor=white" alt="Dataform 3.x" />
  <img src="https://img.shields.io/badge/runtime-z%C3%A9ro%20r%C3%A9seau%20%C2%B7%20z%C3%A9ro%20LLM-2EA44F" alt="Zéro réseau, zéro LLM" />
</p>

<p align="center">
  <strong>Donnez à votre agent de code (Claude Code, Cursor) une connaissance fiable et à jour
  de votre pipeline Dataform — lineage table et colonne, schémas, analyse d'impact —
  au lieu de le laisser relire les <code>.sqlx</code> un par un et halluciner sur le DAG.</strong>
</p>

---

## Installation avec Claude Code

Prérequis (une fois par poste) : [uv](https://docs.astral.sh/uv/) (`brew install uv`) et
`@dataform/cli` ≥ 3.0 (`npm i -g @dataform/cli`).

À la racine de **votre repo Dataform**, créez ou complétez `.mcp.json`
(modèle : [`.mcp.json.example`](.mcp.json.example)) :

```json
{
  "mcpServers": {
    "dataform-context": {
      "type": "stdio",
      "command": "/opt/homebrew/bin/uvx",
      "args": ["--from", "git+ssh://git@github.com/vgossiaux/dataform-context-mcp@v0.3.0",
               "dataform-context", "serve"]
    }
  }
}
```

C'est tout : pas de clone, pas de `--repo` (le serveur indexe le répertoire courant).
Ouvrez une session Claude Code dans le repo et tapez `/mcp` : `dataform-context` doit
apparaître connecté. Premier appel ~15 s (compilation initiale), ensuite ~10 ms.

> [!IMPORTANT]
> **Chemin absolu de `uvx` obligatoire** : un `"command": "uvx"` nu échoue (`ENOENT`)
> quand l'agent est lancé depuis un shell non-login dont le PATH ne contient pas
> `/opt/homebrew/bin`. Même précaution en CI.

**Vérification depuis l'agent** : demandez simplement « lance check_setup » — l'outil
diagnostique toute l'installation (dataform CLI, compilation, index, couverture lineage,
goldens). Ou copiez la commande
[`integrations/claude-code/commands/dataform-context-verify.md`](integrations/claude-code/commands/dataform-context-verify.md)
dans `.claude/commands/` de votre repo pour avoir `/dataform-context-verify`.

Recommandé : ajoutez au `CLAUDE.md` du repo le bloc d'instructions agent (voir
[Faire adopter les outils par l'agent](#faire-adopter-les-outils-par-lagent)).

## Installation avec Cursor

Même serveur, MCP stdio standard. Copiez
[`integrations/cursor/mcp.json.example`](integrations/cursor/mcp.json.example) vers
`.cursor/mcp.json` de votre repo, et la règle
[`integrations/cursor/rules/dataform-context.mdc`](integrations/cursor/rules/dataform-context.mdc)
vers `.cursor/rules/`. Les commandes
[`dataform-context-verify.md`](integrations/cursor/commands/dataform-context-verify.md)
et
[`dataform-context-golden-init.md`](integrations/cursor/commands/dataform-context-golden-init.md)
se copient dans `.cursor/commands/` pour obtenir `/dataform-context-verify` et
`/dataform-context-golden-init` — même protocole que côté Claude Code (Cursor supporte
les commandes personnalisées et, depuis la v1.5, l'elicitation MCP). Tout le matériel
d'intégration est récapitulé dans [`integrations/README.md`](integrations/README.md).

## Installation avec Codex CLI

Prérequis : [uv](https://docs.astral.sh/uv/) et `@dataform/cli` ≥ 3.0.

À la racine de votre repo, créez ou complétez `.codex/config.toml`
(modèle : [`integrations/codex/config.toml.snippet`](integrations/codex/config.toml.snippet)) :

```toml
[mcp_servers.dataform-context]
command = "/opt/homebrew/bin/uvx"
args = ["--from", "git+ssh://git@github.com/vgossiaux/dataform-context-mcp@v0.3.0", "dataform-context", "serve"]
```

`.codex/config.toml` n'est chargé que pour un projet **"trusted"** : au premier
lancement de `codex` dans le repo, répondez "yes" au prompt de confiance.

Ajoutez le bloc [`integrations/codex/AGENTS.md.snippet.md`](integrations/codex/AGENTS.md.snippet.md)
à votre `AGENTS.md`, puis copiez
[`integrations/codex/skills/`](integrations/codex/skills/) dans `.codex/skills/` pour
obtenir les skills `dataform-context-verify` et `dataform-context-golden-init`.

## Installation avec Antigravity

Copiez [`integrations/antigravity/mcp_config.json.example`](integrations/antigravity/mcp_config.json.example)
vers `.agents/mcp_config.json`, la règle
[`integrations/antigravity/rules/dataform-context.md`](integrations/antigravity/rules/dataform-context.md)
vers `.agents/rules/`, et les workflows
[`integrations/antigravity/workflows/`](integrations/antigravity/workflows/) vers
`.agents/workflows/` pour obtenir `/dataform-context-verify` et
`/dataform-context-golden-init`.

## Installation avec Windsurf

⚠️ Contrairement aux autres clients, la config MCP de Windsurf est **globale par
poste**, pas scopée projet. Fusionnez
[`integrations/windsurf/mcp_config.json.snippet`](integrations/windsurf/mcp_config.json.snippet)
dans `~/.codeium/windsurf/mcp_config.json` (une fois par machine). Les rules et
workflows, eux, restent scopés projet et se committent normalement : copiez
[`integrations/windsurf/rules/dataform-context.md`](integrations/windsurf/rules/dataform-context.md)
vers `.windsurf/rules/` et
[`integrations/windsurf/workflows/`](integrations/windsurf/workflows/) vers
`.windsurf/workflows/`.

## Installation avec Copilot (VS Code)

Copiez [`integrations/copilot/mcp.json.example`](integrations/copilot/mcp.json.example)
vers `.vscode/mcp.json` (⚠️ pas `.mcp.json` à la racine — collision de schéma avec
Claude Code/Cursor), le bloc
[`integrations/copilot/copilot-instructions.snippet.md`](integrations/copilot/copilot-instructions.snippet.md)
vers `.github/copilot-instructions.md`, et les prompt files
[`integrations/copilot/prompts/`](integrations/copilot/prompts/) vers
`.github/prompts/` pour obtenir `/dataform-context-verify` et
`/dataform-context-golden-init`.

---

## Pourquoi

Un agent de code qui travaille sur un repo Dataform lit les fichiers `.sqlx` un par un.
Conséquences observées en conditions réelles : colonnes ou tables inventées, dépendances
amont oubliées lors d'un refactor, impact aval sous-estimé — la cascade
`staging → intermediate → marts → assertions` n'est jamais vue en entier.

| Sans système | Avec dataform-context-mcp |
|---|---|
| L'agent grep les `ref()` et devine le DAG | Le DAG vient du compilateur Dataform lui-même (`dependencyTargets`) |
| « Quelles tables ça casse ? » = relecture partielle | `impact_analysis` : blast radius complet, assertions incluses, en un appel |
| L'origine d'une colonne se perd dans les CTEs | `get_column_lineage` : chaîne complète avec les expressions SQL de transformation |
| Un lineage introuvable passe pour « pas de dépendance » | Statuts explicites + `complete: false` + `warnings` — **jamais de faux vide** |
| Contexte figé au moment de la lecture | Ré-indexation lazy par hash de contenu à chaque appel |

**Déterministe et self-hosted** : aucun LLM, aucun appel réseau, aucun accès au warehouse
à l'exécution. Mêmes fichiers → même index → mêmes réponses.

```
.sqlx + includes/ ──▶ dataform compile --json ──▶ parsing du CompiledGraph
                                                        │
        SQLite local (~/.cache/dataform-context-mcp/)  ◀┘
        • actions, couches, colonnes documentées
        • edges table-level (source : dependencyTargets du compilateur)
        • edges colonne-level (sqlglot, statuts explicites)
                                                        │
        Serveur MCP stdio (7 outils) ◀──────────────────┘
```

## Les 8 outils

| Outil | Exemple de question à poser à l'agent |
|---|---|
| `get_table_context(name)` | « Décris-moi la table ref_brand » |
| `get_upstream(name, depth)` | « De quoi dépend mart_kpis ? » |
| `get_downstream(name, depth)` | « Qui lit staging_events ? » |
| `find_tables_by_layer(layer)` | « Liste les tables du mart » |
| `get_column_lineage(table, column, …)` | « D'où vient la colonne total_amount ? » |
| `impact_analysis(name, column?)` | « Qu'est-ce qui casse si je renomme page_type ? » |
| `check_setup()` | « Vérifie que dataform-context est bien installé » |
| `refresh_index()` | « Force la ré-indexation » |

- **Résolution de noms tolérante** : `ma_table`, `dataset.ma_table`, canonical complet ou
  chemin du fichier `.sqlx` — avec suggestions en cas d'erreur.
- **Couches découvertes dynamiquement** depuis les chemins
  (`definitions/transforms/<NN_nom>/`, `definitions/sources/`…) — aucune convention
  hardcodée.
- **Toute réponse embarque `index_meta`** : fraîcheur, hash source, comptages, statut de
  la dernière compilation.

## Faire adopter les outils par l'agent

Bloc à ajouter au `CLAUDE.md` (ou aux règles Cursor) du repo Dataform :

> ## Contexte pipeline : MCP dataform-context
> Avant de lire des `.sqlx` ou de modifier une table : `get_table_context` (schéma +
> voisins), `get_upstream`/`get_downstream` (DAG), `impact_analysis` (obligatoire avant
> tout refactor de table ou colonne), `find_tables_by_layer` (périmètre d'une couche),
> `get_column_lineage` (origine d'une colonne). Ces outils sont générés depuis
> `dataform compile` : ils font foi sur le DAG, contrairement à une lecture partielle
> des fichiers. `complete: false` = lineage inconnu, pas « aucune dépendance ». Après
> édition de `.sqlx`, l'index se rafraîchit seul (hash de contenu).

## Lire les réponses de lineage colonne — le contrat « jamais de faux vide »

L'extraction statique a des limites connues (MERGE, `SELECT *` sur une source non
documentée, scripts multi-statements). La règle absolue : **un lineage vide n'est
présenté comme « aucune dépendance » que s'il est certain.** Sinon, c'est dit :

- Chaque table porte un **statut d'extraction** (`ok`, `partial`, `failed`,
  `not_attempted`, `source`), toujours accompagné d'une raison.
- `get_column_lineage` renvoie `complete: false` + `warnings` (tables opaques
  rencontrées) quand le lineage est inconnu au-delà d'un point — à distinguer de
  `complete: true` + `edges: []` (vraie absence, ex. `CURRENT_DATE()`).
- `impact_analysis(column=…)` renvoie `possibly_affected` : tables aval dont l'impact
  colonne est inconnu. **Ne jamais les exclure d'un refactor.**

Détail des catégories et du surfaçage : [`docs/lineage-limits.md`](docs/lineage-limits.md).

<details>
<summary><strong>CLI (sans agent)</strong></summary>

Depuis un clone local du repo (`uv sync` d'abord), ou via
`uvx --from git+ssh://git@github.com/vgossiaux/dataform-context-mcp@v0.3.0 dataform-context …` :

```bash
dataform-context index            # compile + (re)construit l'index du repo courant
dataform-context report           # résumé : couches, edges, couverture lineage
dataform-context report --table ma_table    # contexte JSON d'une table
dataform-context serve            # serveur MCP (stdio) — utilisé par .mcp.json
dataform-context validate-golden  # oracle manuel (.dataform-context/golden_columns.json)
```

`--repo /chemin` sur chaque commande pour viser un autre repo que le courant.
`--db /chemin` pour déplacer l'index (défaut : `~/.cache/dataform-context-mcp/<hash>.db`).

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
</details>

<details>
<summary><strong>Fraîcheur de l'index (ré-indexation lazy)</strong></summary>

- À **chaque** appel d'outil, le serveur hache le contenu de `definitions/**`,
  `includes/**` et `workflow_settings.yaml`. Hash inchangé → réponse ~10 ms. Hash
  changé → recompilation + ré-indexation (~2–15 s), puis réponse. L'agent travaille
  toujours sur l'état courant des fichiers, y compris ses propres éditions en cours de
  session.
- Si la compilation échoue (fichier cassé en cours d'édition), le **dernier index
  valide** est servi, avec `index_meta.compile_status: "error"` et le message. Jamais
  d'index vide.
- L'index vit hors du repo (`~/.cache/dataform-context-mcp/`) — rien à gitignorer.
</details>

<details>
<summary><strong>Golden sets : valider le lineage sur votre repo</strong></summary>

Sans base de vérité externe, l'oracle est humain : vous tracez à la main quelques
colonnes que vous connaissez, l'outil doit retrouver exactement ces edges. Le fichier
va dans **`.dataform-context/golden_columns.json`** à la racine du repo Dataform —
c'est là que `validate-golden` et `check_setup` le cherchent par défaut (`--golden`
pour viser un autre chemin). Format (liste d'entrées) :

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

**Construction guidée** : copiez la commande équivalente pour votre outil, puis lancez
`/dataform-context-golden-init` — l'agent propose des tracés (contre-vérifiés dans le
SQL source), vous les validez via des questions interactives, le fichier est écrit et
validé automatiquement.

- Claude Code : [`integrations/claude-code/commands/dataform-context-golden-init.md`](integrations/claude-code/commands/dataform-context-golden-init.md) → `.claude/commands/`
- Cursor : [`integrations/cursor/commands/dataform-context-golden-init.md`](integrations/cursor/commands/dataform-context-golden-init.md) → `.cursor/commands/`
- Codex CLI : [`integrations/codex/skills/dataform-context-golden-init/`](integrations/codex/skills/dataform-context-golden-init/) → `.codex/skills/`
- Antigravity : [`integrations/antigravity/workflows/dataform-context-golden-init.md`](integrations/antigravity/workflows/dataform-context-golden-init.md) → `.agents/workflows/`
- Windsurf : [`integrations/windsurf/workflows/dataform-context-golden-init.md`](integrations/windsurf/workflows/dataform-context-golden-init.md) → `.windsurf/workflows/`
- Copilot (VS Code) : [`integrations/copilot/prompts/dataform-context-golden-init.prompt.md`](integrations/copilot/prompts/dataform-context-golden-init.prompt.md) → `.github/prompts/`
</details>

<details>
<summary><strong>Gouvernance & audit</strong></summary>

Conçu pour passer une revue sécurité d'entreprise avant déploiement sur un repo client :

- **Dépendances runtime exhaustives** : `mcp` (SDK officiel Model Context Protocol) et
  `sqlglot` — pins exacts dans `uv.lock` ; tout le reste est stdlib (`sqlite3`,
  `argparse`, `hashlib`, `difflib`).
- **Zéro appel réseau à l'exécution** : lecture des fichiers du repo + shell-out
  `dataform compile --json` local. Pas d'accès au warehouse, pas de télémétrie.
- **Zéro LLM à l'exécution** : parsing déterministe (compilateur Dataform + sqlglot).
- **Données locales uniquement** : index SQLite dans `~/.cache/dataform-context-mcp/`.
- **Frontière de confiance = le repo indexé** : `dataform compile` exécute le JavaScript
  du repo cible (`includes/`, `*.js`) avec les droits de l'utilisateur, à chaque
  ré-indexation. N'indexer que des repos Dataform de confiance ; ne jamais pointer
  `--repo` sur un clone non revu.
- **Contenu du cache** : l'index SQLite contient le SQL compilé de chaque action
  (`query`, `incremental_query`). Le fichier est créé en mode `0600` (lecture par
  l'utilisateur seul). Pour purger : `rm -rf ~/.cache/dataform-context-mcp/`.
- **Ce repo ne contient aucune métadonnée client** : fixtures synthétiques, rapports
  agrégés uniquement.
</details>

<details>
<summary><strong>Limites connues</strong></summary>

- Lineage colonne incomplet par construction sur : `SELECT *` au-dessus d'une source
  sans schéma documenté, MERGE/DML, scripts multi-statements — toujours **surfacé**
  (statuts, `warnings`, `possibly_affected`), jamais masqué. Levier : documenter les
  `columns` des declarations dans leur `config {}` débloque mécaniquement l'expansion
  des `SELECT *` (mesuré : +28 points de couverture sur un repo pilote).
- Couverture observée sur deux repos pilotes : 91 % et 63 % de tables `ok` — l'écart du
  second est structurel (staging en `SELECT *` sur sources non documentées), analysé
  dans [`docs/lineage-limits.md`](docs/lineage-limits.md).
- `dataform compile` (Node) est une dépendance d'exécution : absente → l'indexation
  échoue proprement, l'index précédent reste servi.
</details>

<details>
<summary><strong>Architecture du code & tests</strong></summary>

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

Développement local :

```bash
git clone git@github.com:vgossiaux/dataform-context-mcp.git
cd dataform-context-mcp
uv sync && uv run pytest        # 74 tests
```

Les tests s'appuient sur un **mini repo Dataform synthétique compilable**
(`tests/fixtures/mini_repo/`) — aucun test ne touche un repo réel.
`uv run pytest -m "not integration"` tourne sans Node.
</details>

<details>
<summary><strong>Dépannage express</strong></summary>

| Symptôme | Cause | Fix |
|---|---|---|
| `/mcp` : serveur en erreur `ENOENT ... uv` | PATH sans homebrew (shell non-login) | Chemin absolu `/opt/homebrew/bin/uvx` dans `.mcp.json` |
| `compile error` dans `index_meta` | Un `.sqlx` ne compile pas | `dataform compile` dans le repo pour voir l'erreur ; l'index précédent reste servi |
| `not_found` avec suggestions | Nom de table approximatif | Reprendre une suggestion, ou `dataset.table` |
| Premier appel lent (~15 s) | Compilation + extraction initiales | Normal ; appels suivants ~10 ms |
</details>

## Roadmap

- Licence (préalable au passage open source).
- Enrichissement sémantique **batch, hors session, via LLM self-hosted** des colonnes
  non documentées — jamais au runtime MCP.
- Export mermaid/graphviz du graphe ; hook PreToolUse suggérant `impact_analysis`
  avant édition de `.sqlx`.

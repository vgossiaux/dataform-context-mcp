# Intégrations — fichiers à copier dans votre repo Dataform

## Claude Code

| Fichier | Destination dans votre repo | Rôle |
|---|---|---|
| `claude-code/mcp.json.example` | `.mcp.json` (fusionner si existant) | Déclare le serveur MCP |
| `claude-code/CLAUDE.md.snippet.md` | bloc à coller dans `CLAUDE.md` | Fait adopter les outils par l'agent |
| `claude-code/commands/dataform-context-verify.md` | `.claude/commands/` | Commande `/dataform-context-verify` (diagnostic) |
| `claude-code/commands/dataform-context-golden-init.md` | `.claude/commands/` | Commande `/dataform-context-golden-init` (construction interactive du golden set, validation humaine) |

## Cursor

| Fichier | Destination dans votre repo | Rôle |
|---|---|---|
| `cursor/mcp.json.example` | `.cursor/mcp.json` (fusionner si existant) | Déclare le serveur MCP |
| `cursor/rules/dataform-context.mdc` | `.cursor/rules/` | Règle projet (adoption des outils) |
| `cursor/commands/dataform-context-verify.md` | `.cursor/commands/` | Commande `/dataform-context-verify` (diagnostic) |
| `cursor/commands/dataform-context-golden-init.md` | `.cursor/commands/` | Commande `/dataform-context-golden-init` (construction interactive du golden set, validation humaine) |

Dans les deux cas : chemin **absolu** de `uvx` requis (`/opt/homebrew/bin/uvx` sur macOS
homebrew) — un `uvx` nu échoue depuis un shell non-login. Prérequis par poste : `uv` et
`@dataform/cli` ≥ 3.0, plus un accès SSH GitHub au repo.

Les commandes Cursor sont du Markdown pur, sans frontmatter (Cursor ne documente pas de
format de métadonnées pour `.cursor/commands/`, contrairement à Claude Code) — même
protocole, adapté pour ne pas dépendre de l'outil `AskUserQuestion` propre à Claude Code
(la validation humaine se fait en chat normal).

## Codex CLI

| Fichier | Destination dans votre repo | Rôle |
|---|---|---|
| `codex/config.toml.snippet` | bloc à fusionner dans `.codex/config.toml` | Déclare le serveur MCP (portée projet) |
| `codex/AGENTS.md.snippet.md` | bloc à coller dans `AGENTS.md` | Fait adopter les outils par l'agent |
| `codex/skills/dataform-context-verify/` | `.codex/skills/` | Skill `dataform-context-verify` (diagnostic) |
| `codex/skills/dataform-context-golden-init/` | `.codex/skills/` | Skill `dataform-context-golden-init` (construction interactive du golden set) |

`.codex/config.toml` n'est lu que si le projet est **"trusted"** : au premier lancement
de `codex` dans le repo, répondre "yes" au prompt de confiance (Codex l'enregistre dans
`~/.codex/config.toml` sous `[projects."/chemin/absolu"] trust_level = "trusted"`). Les
"custom prompts" (`~/.codex/prompts/`) existent mais sont **dépréciés** et non
partageables via git — ne pas les utiliser, préférer les skills projet.

## Antigravity

| Fichier | Destination dans votre repo | Rôle |
|---|---|---|
| `antigravity/mcp_config.json.example` | `.agents/mcp_config.json` (fusionner si existant) | Déclare le serveur MCP |
| `antigravity/rules/dataform-context.md` | `.agents/rules/` | Règle projet toujours active (`trigger: always_on`) |
| `antigravity/workflows/dataform-context-verify.md` | `.agents/workflows/` | Workflow `/dataform-context-verify` (diagnostic) |
| `antigravity/workflows/dataform-context-golden-init.md` | `.agents/workflows/` | Workflow `/dataform-context-golden-init` (construction interactive du golden set) |

Le fichier d'instructions projet `AGENTS.md` (voir section Codex CLI) est aussi lu par
Antigravity comme socle commun ; `GEMINI.md`, s'il existe, prend le pas en cas de
conflit.

> [!NOTE]
> Chemin du dossier de Workflows non confirmé par la documentation officielle au
> 2026-08-24 — livré sous `.agents/workflows/` (cohérent avec `.agents/rules/` et
> `.agents/agents/`). Si `/dataform-context-verify` n'apparaît pas dans le menu `/` de
> votre installation Antigravity, déplacez les 2 fichiers vers `.agent/workflows/`
> (singulier, convention historique) et signalez lequel a fonctionné.

# Intégrations — fichiers à copier dans votre repo Dataform

## Claude Code

| Fichier | Destination dans votre repo | Rôle |
|---|---|---|
| `claude-code/mcp.json.example` | `.mcp.json` (fusionner si existant) | Déclare le serveur MCP |
| `claude-code/CLAUDE.md.snippet.md` | bloc à coller dans `CLAUDE.md` | Fait adopter les outils par l'agent |
| `claude-code/commands/dataform-context-verify.md` | `.claude/commands/` | Commande `/dataform-context-verify` (diagnostic) |

## Cursor

| Fichier | Destination dans votre repo | Rôle |
|---|---|---|
| `cursor/mcp.json.example` | `.cursor/mcp.json` (fusionner si existant) | Déclare le serveur MCP |
| `cursor/rules/dataform-context.mdc` | `.cursor/rules/` | Règle projet (adoption des outils) |

Dans les deux cas : chemin **absolu** de `uvx` requis (`/opt/homebrew/bin/uvx` sur macOS
homebrew) — un `uvx` nu échoue depuis un shell non-login. Prérequis par poste : `uv` et
`@dataform/cli` ≥ 3.0, plus un accès SSH GitHub au repo.

# Distribution PyPI avec mise à jour automatique

Date : 2026-09-21. Statut : validé en brainstorming, à planifier.

## Problème

Les snippets d'installation pointent sur `git+ssh://git@github.com/vgossiaux/dataform-context-mcp@vX.Y.Z`.
Ce choix protège contre l'exécution de commits non revus (`main`), mais :

- chaque correctif exige une modification manuelle de tous les `.mcp.json` qui ont copié le snippet ;
- `git+ssh` suppose un accès SSH au repo, incompatible avec un projet open source.

## Décisions

| Question | Décision |
|---|---|
| Consommateurs | Aujourd'hui l'auteur seul ; demain des inconnus qui installent le serveur chez leurs clients |
| Comportement à la publication d'un correctif | Reçu au prochain démarrage du serveur MCP, sans action de l'utilisateur |
| Canal | PyPI uniquement, paquet `dataform-context-mcp` |
| Réseau au démarrage | Exigé à chaque démarrage, via `uvx`. Testé le 2026-09-21 : `uvx …@latest` échoue hors ligne, pas de repli sur le cache. Un wrapper `sh -c "… \|\| uvx --offline …"` fonctionne mais a été écarté pour garder un snippet lisible et portable |
| Garde-fou de majeure | Non retenu (`@latest` simple) |

## Design

### 1. Canal et versions

- Paquet PyPI `dataform-context-mcp`, versions semver, source de vérité `pyproject.toml`.
- Snippet unique dans toute la documentation :
  `uvx --from dataform-context-mcp@latest dataform-context serve`
  (`--from` est obligatoire car la commande `dataform-context` ne porte pas le nom du paquet ;
  `command` reste le chemin absolu de `uvx`, contrainte existante du README).
- Fait vérifié dans la doc `uv` : `uvx pkg` réutilise le cache et ne voit jamais une nouvelle
  version ; `uvx pkg@latest` rafraîchit le cache à chaque exécution. Aucun code de vérification
  de version côté serveur.
- Première version publiée sur PyPI : `0.5.0`. Les tags `v0.2.0` à `v0.4.0` restent sur GitHub
  sous l'ancien mode d'installation, jamais republiés.

### 2. Publication

Nouveau workflow `.github/workflows/release.yml` :

- déclencheur : `push` de tag `v*` ;
- `permissions: contents: read` au niveau du workflow, `id-token: write` sur le seul job de
  publication ;
- job `build` : checkout, `uv build`, upload de `dist/` en artefact ;
- job `publish` : environment GitHub `pypi`, télécharge l'artefact, publie via
  `pypa/gh-action-pypi-publish` en trusted publishing (aucun token stocké) ;
- garde-fou : le job échoue si `v$(version de pyproject.toml)` ≠ tag poussé ;
- toutes les actions épinglées par SHA de commit, tag en commentaire, comme `ci.yml`.

`ci.yml` reçoit aussi `permissions: contents: read` explicite.

### 3. Script de release

`scripts/release.sh` :

- conserve : arbre propre, tag inexistant, bump `pyproject.toml`, commit, tag annoté, pas de push ;
- ajoute : `uv lock` avant le commit (corrige l'oubli qui a demandé un commit séparé en 0.3.0
  et 0.4.0) ;
- supprime : tout le bloc de pinning des snippets (`PATTERN`, `REPLACEMENT`, boucle `sed`) et
  le commentaire d'en-tête qui le justifie, remplacé par le nouveau modèle de distribution.

### 4. Snippets et documentation

Fichiers concernés (7) : `README.md` (3 occurrences), `integrations/antigravity/mcp_config.json.example`,
`integrations/claude-code/mcp.json.example`, `integrations/codex/config.toml.snippet`,
`integrations/copilot/mcp.json.example`, `integrations/cursor/mcp.json.example`,
`integrations/windsurf/mcp_config.json.snippet`.

- `["--from", "git+ssh://…@vX.Y.Z", "dataform-context", "serve"]` devient
  `["--from", "dataform-context-mcp@latest", "dataform-context", "serve"]`.
- README, bloc « Gouvernance & audit » : « Zéro appel réseau à l'exécution » devient
  « Zéro appel réseau du serveur : `uvx` interroge PyPI au démarrage pour servir la dernière
  version. Le serveur lui-même n'ouvre aucune connexion. Hors ligne, le démarrage échoue :
  remplacer `@latest` par une version exacte le temps de la coupure. »
- README, nouvelle sous-section « Figer une version ou travailler hors ligne » :
  `uvx --from dataform-context-mcp@0.5.0 dataform-context serve` pour la reproductibilité ou
  l'absence de réseau, avec la mention que les correctifs ne sont alors plus reçus
  automatiquement.
- Le paragraphe FR et le paragraphe EN du README sont tous deux mis à jour.

### 5. Vérification

1. Spike fait le 2026-09-21 : `uvx --from x@latest` échoue hors ligne (proxy injoignable, index
   inchangé) ; `uvx --offline --from x@latest` sert le cache. Décision B : pas de wrapper,
   documentation du comportement.
2. Dry run : trusted publisher configuré sur `test.pypi.org`, tag `v0.5.0rc1` publié sur
   TestPyPI, installation testée avec `--index-url https://test.pypi.org/simple/`.
3. Publication réelle : tag `v0.5.0`, `uvx dataform-context-mcp@latest dataform-context --help`
   répond depuis un poste vierge de cache.
4. Test bout en bout : `.mcp.json` d'un repo Dataform avec le nouveau snippet, `/mcp` restart,
   `check_setup` renvoie `ok`.
5. Suite de tests et lint inchangés : `uv run pytest`, `uv run ruff check .`.

## Hors repo, à la charge de l'auteur

1. Compte pypi.org avec 2FA. Vérifier que le nom `dataform-context-mcp` est libre.
2. Trusted publisher PyPI : owner `vgossiaux`, repo `dataform-context-mcp`, workflow
   `release.yml`, environment `pypi`.
3. Même déclaration sur test.pypi.org pour le dry run.
4. Environment GitHub `pypi` avec l'auteur comme reviewer requis : chaque publication demande
   une approbation manuelle.
5. 2FA sur le compte GitHub.

## Modèle de sécurité

- Le pointeur flottant vise des releases taguées et publiées, jamais `main`.
- Chaîne d'approvisionnement : compte GitHub + compte PyPI de l'auteur, tous deux en 2FA,
  publication conditionnée à une approbation manuelle dans l'environment `pypi`.
- Les PR de forks exécutent `ci.yml` avec un token lecture seule et sans secret ; `release.yml`
  ne se déclenche jamais sur une PR.
- Le repo restera privé tant que la branche locale `private-history` et les tags `mvp-*`
  existent hors de `origin` ; ils ne sont jamais poussés.

## Hors périmètre

- Garde-fou de majeure (`<1`) : écarté, documenté comme variante dans la section « Figer une version ».
- Notification « version obsolète » dans `check_setup` : inutile avec `@latest`.
- Publication sur d'autres index (conda, Homebrew).

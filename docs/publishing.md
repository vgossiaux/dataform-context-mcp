# Publier une release

Une fois, avant la première publication :

1. **Compte PyPI** : créer un compte sur https://pypi.org, activer le 2FA (obligatoire).
   Faire de même sur https://test.pypi.org (compte distinct).
2. **Trusted publisher PyPI** : https://pypi.org/manage/account/publishing/ → « Add a new
   pending publisher » :
   - PyPI project name : `dataform-context-mcp`
   - Owner : `vgossiaux`
   - Repository name : `dataform-context-mcp`
   - Workflow name : `release.yml`
   - Environment name : `pypi`
3. **Trusted publisher TestPyPI** : même formulaire sur
   https://test.pypi.org/manage/account/publishing/, environment name `testpypi`.
4. **Environments GitHub** : Settings → Environments du repo :
   - `pypi` : « Required reviewers » = vous. Chaque publication attend votre approbation.
   - `testpypi` : sans reviewer.
5. **2FA GitHub** activé sur le compte.

À chaque release :

1. Arbre propre sur `main`, tests verts : `uv run pytest -q`.
2. Essai (optionnel mais recommandé pour une première) : `scripts/release.sh X.Y.ZrcN` puis
   `git push origin main vX.Y.ZrcN`. Le job `publish-testpypi` publie sans approbation.
   Vérifier : `uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --index-strategy unsafe-best-match --from "dataform-context-mcp==X.Y.ZrcN" dataform-context --help`.
3. Release : `scripts/release.sh X.Y.Z` puis `git push origin main vX.Y.Z`.
4. Approuver le job `publish-pypi` dans l'onglet Actions (environment `pypi`). Le job
   `github-release` crée ensuite la GitHub Release avec les notes générées depuis les commits
   et les artefacts `dist/`.
5. Vérifier : `uvx --from dataform-context-mcp@latest dataform-context --help`.

Un tag qui n'est ni `vX.Y.Z` ni `vX.Y.ZrcN` fait échouer le job `build` : rien n'est publié.

Les utilisateurs reçoivent la version au prochain démarrage de leur serveur MCP.

---
name: dataform-context-verify
description: Vérifie l'installation du serveur MCP dataform-context (dataform CLI, compilation, index, lineage, goldens) sur ce repo Dataform. À utiliser après installation ou si les outils dataform-context se comportent de façon inattendue.
---

Appelle l'outil MCP `check_setup` du serveur `dataform-context`, puis présente le
diagnostic de façon lisible :

1. Une ligne par check : ✅/❌, nom du check, détail.
2. Pour chaque check en échec : la cause probable et le correctif (dataform CLI absent →
   `npm i -g @dataform/cli` ; erreur de compilation → lancer `dataform compile` dans le
   repo pour voir l'erreur ; goldens en échec → lister les entrées `failing`).
3. Termine par un verdict global en une phrase (installation OK / à corriger).

N'utilise aucun autre outil que `check_setup`.

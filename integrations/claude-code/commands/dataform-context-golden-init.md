---
description: Construit interactivement le golden set de lineage colonne du repo (tracés proposés par l'agent, validés par l'humain)
allowed-tools: mcp__dataform-context, Read, Write, AskUserQuestion
---

Tu vas construire (ou compléter) le fichier `.dataform-context/golden_columns.json` de ce
repo : l'oracle manuel qui valide le lineage colonne du serveur `dataform-context`.
Principe non négociable : **tu proposes des tracés, l'humain les valide** — jamais
l'inverse. `$ARGUMENTS` peut préciser le nombre d'entrées (défaut : 5).

## Protocole

1. **État des lieux.** Appelle `check_setup`. Si `.dataform-context/golden_columns.json`
   existe déjà, lis-le : tu proposeras des AJOUTS, jamais d'écrasement.
2. **Sélection des candidates.** Avec `find_tables_by_layer` et `get_table_context`,
   choisis des colonnes couvrant ces critères (1 chacune par défaut) :
   - passthrough simple (colonne recopiée d'une table amont) ;
   - agrégation (`SUM`/`COUNT`/`ANY_VALUE`…) ;
   - chaîne traversant 3+ tables (utiliser `depth` 2-3) ;
   - colonne d'une table incrémentale ;
   - cas tordu : `UNNEST`/`STRUCT`, macro d'`includes/`, `SELECT *`, ou table à statut
     d'extraction `partial`/`not_attempted` (l'entrée attendra alors
     `expect_complete: false` et souvent `expected_edges: []`).
3. **Tracé + contre-vérification source.** Pour chaque candidate :
   `get_column_lineage` (direction `upstream`, `depth` 1 sauf pour la chaîne), puis
   **lis le fichier `.sqlx` source** (champ `file` de `get_table_context`) et cite
   l'expression SQL exacte qui justifie chaque edge. Si l'outil et ta lecture du SQL
   divergent : investigue et signale — n'écris jamais une entrée douteuse.
4. **Validation humaine.** Présente chaque tracé via une question à choix
   (valider / corriger / remplacer la colonne), en montrant : la colonne, les edges
   proposés, l'expression SQL, le `complete` attendu, et le **chemin du fichier** pour
   que l'utilisateur puisse vérifier dans le code lui-même.
5. **Écriture.** Écris les entrées VALIDÉES uniquement, au format :

```json
[
  {
    "table": "dataset.table",
    "column": "colonne",
    "direction": "upstream",
    "depth": 1,
    "expected_edges": ["dataset_amont.table_amont.col -> dataset.table.colonne"],
    "expect_complete": true
  }
]
```

6. **Vérification finale.** Appelle `check_setup` et rapporte le check `goldens`
   (attendu : N/N passed). Termine par le récapitulatif : entrées ajoutées, critères
   couverts, critères restants.

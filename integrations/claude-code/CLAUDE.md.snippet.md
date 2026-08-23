# Bloc à copier dans le CLAUDE.md de votre repo Dataform

> ## Contexte pipeline : MCP dataform-context
> Avant de lire des `.sqlx` ou de modifier une table : `get_table_context` (schéma +
> voisins), `get_upstream`/`get_downstream` (DAG), `impact_analysis` (obligatoire avant
> tout refactor de table ou colonne), `find_tables_by_layer` (périmètre d'une couche),
> `get_column_lineage` (origine d'une colonne). Ces outils sont générés depuis
> `dataform compile` : ils font foi sur le DAG, contrairement à une lecture partielle
> des fichiers. `complete: false` = lineage inconnu, pas « aucune dépendance ». Après
> édition de `.sqlx`, l'index se rafraîchit seul (hash de contenu). En cas de doute sur
> l'installation, appeler `check_setup`.

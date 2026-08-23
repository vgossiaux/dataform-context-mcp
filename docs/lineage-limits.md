# Limites du column-level lineage — contrat d'interprétation

Le lineage colonne est extrait statiquement par sqlglot depuis le SQL compilé, sans accès
au warehouse (contrainte de gouvernance). Chaque action porte un statut explicite ;
**rien n'est jamais masqué** : un lineage vide n'est présenté comme « aucune dépendance »
que si le statut est `ok`.

## Statuts

| Statut | Sens | Effet dans les réponses MCP |
|---|---|---|
| `ok` | Toutes les colonnes projetées sont résolues | `complete: true` possible |
| `partial` | Une partie résolue ; le reste inconnu (raison fournie) | nœud listé dans `warnings` / `possibly_affected` |
| `failed` | Analyse impossible (parse/ambiguïté, raison fournie) | idem |
| `not_attempted` | Catégorie non analysée par construction (MERGE/DML, multi-statement, operations) | idem |
| `source` | Declaration (table source) : terminal attendu | aucun warning |

## Catégories non couvertes (par construction)

1. **`SELECT *` sur une table au schéma inconnu** → `partial`, reason `select_star_unresolved`.
   Le schéma amont est propagé topologiquement (colonnes documentées + colonnes extraites),
   mais une declaration sans `columns` documentées dans son `config {}` est un mur :
   l'étoile ne peut pas être développée sans interroger le warehouse (exclu du runtime —
   gouvernance).
2. **Colonnes ambiguës dans des JOINs dont les schémas amont sont inconnus** → `failed`
   (OptimizeError sqlglot). Même racine que 1.
3. **MERGE / DML / scripts multi-statements / operations** → `not_attempted`.
4. **Lectures non déclarées** (table lue dans le SQL sans `ref()`, ou dataset hors graphe) :
   l'edge colonne est rejeté car sans edge table correspondant (invariant), statut `partial`,
   reason `inconsistent_edge`. C'est aussi un signal de qualité sur le repo lui-même.
5. **Auto-références** (`${self()}`, patterns de préservation de lignes) : ignorées sans
   pénalité — un self-edge ne porte pas de lineage inter-tables.

## Consigne d'interprétation pour agents

- `complete: false` dans `get_column_lineage` = **lineage inconnu au-delà des nœuds listés
  en `warnings`** — PAS « aucune dépendance ». Traiter les tables en warning comme
  potentiellement impactées.
- `possibly_affected` dans `impact_analysis(column=...)` liste les tables downstream dont
  l'impact colonne est inconnu : ne jamais les exclure d'un refactor.

## Couverture observée (deux repos pilotes anonymisés, sqlglot 30.17.0)

| Repo | ok | partial | failed | not_attempted | source | % ok (hors source) |
|---|---|---|---|---|---|---|
| pilote A (~85 actions) | 51 | 5 | 0 | 0 | 29 | **91 %** |
| pilote B (~66 actions) | 29 | 13 | 4 | 0 | 20 | **63 %** |

L'écart du pilote B est structurel, pas un défaut d'extraction : sa couche staging fait du
`SELECT *` directement sur des declarations non documentées (catégorie 1), les ambiguïtés
(catégorie 2) en dérivent, plus quelques lectures non déclarées (catégorie 4). Tout est
surfacé par statut + warnings.

**Levier principal** : documenter les `columns` des declarations dans leur `config {}`
débloque mécaniquement les catégories 1 et 2 — mesuré sur le pilote B, la couverture
remonterait au-dessus de 90 % sans changer le code.

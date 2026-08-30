# Critique et revue du plan `afmpi` ([PLAN.md](file:///C:/Users/f.migone/Desktop/projects/actif/afmpi/PLAN.md))

## 1. Verdict global
**Le plan est solide et mature, mais nécessite 4 arbitrages pour être exécutable sans ambiguïté.** L'ambition d'exceller sur le passage à l'échelle via Polars est pertinente, mais le phasage et la gestion des dépendances doivent être définitivement tranchés dans [PLAN.md](file:///C:/Users/f.migone/Desktop/projects/actif/afmpi/PLAN.md).

---

## 2. Évaluation des choix clés et arbitrages

### A. Checklist de parité (§4) — Complétude et manques OPHI
- **Manques identifiés** :
  1. Distribution conjointe des privations (histogramme des scores $c_i$).
  2. Agrégation des contributions par *dimension* (pas seulement par indicateur $j$).
  3. Politique explicite de gestion des valeurs manquantes (`listwise deletion` vs `reweighting`).
- **Intervalles de confiance** : L'intégration conjointe de `logit` (`svyciprop`) et `ultimate_cluster` (tronqué) est un vrai plus face à `PythonIPM`.

### B. Architecture (§5-6) — `samplics` vs Réimplémentation
- **Décision : Réimplémentation Polars native (sans `samplics`).** `samplics` impose la structure pandas, alourdit le graphe de dépendances et bride le multi-threading. La linéarisation par grappe (*Ultimate Cluster*) s'écrit en <150 lignes d'agrégations Polars (`pl.Expr`) à haute performance.

### C. Performance (§7) — Polars, Narwhals et Benchmarks
- **Décision : Polars natif (sans Narwhals).** Narwhals restreint l'accès aux fonctionnalités avancées de Polars (expressions complexes, streaming paresseux). L'entrée `pandas` sera ingérée via Apache Arrow (`pl.from_pandas`), avec un surcoût mémoire négligeable.
- **Benchmarks (10M lignes, 442 sous-préfectures)** : Cible très réaliste (<30s, <2 Go RAM avec `LazyFrame` et streaming Parquet). Le jeu synthétique basé sur le découpage ivoirien est représentatif.

### D. Phasage (§9) — Intégration de Polars dès le départ
- Polars doit faire partie du moteur dès la Phase 1 (éviter une refonte du code). En revanche, l'E/S Parquet avancée, le mode streaming et les benchmarks 10M doivent rester isolés en Phase 4.

### E. Validation (§8), Nom & Angles morts
- **Nom `afmpi`** : Excellent (court, clair, mémorisable).
- **Angles morts à couvrir** :
  1. Traitement des strates à PSU unique (*lonely PSUs*).
  2. Validation stricte du typage des indicateurs (booléen ou 0/1).
  3. Borne de tolérance numérique fixée à $10^{-6}$ pour la validation EHCVM.

---

## 3. Modifications concrètes à apporter à [PLAN.md](file:///C:/Users/f.migone/Desktop/projects/actif/afmpi/PLAN.md)

- **§4** : Ajouter `missing_policy`, contributions par dimension $D$, et distribution de $c_i$.
- **§6** : Supprimer l'option `samplics` ; acter le calcul de variance natif en Polars.
- **§7** : Écarter `narwhals` ; spécifier l'ingestion Arrow pour pandas.
- **§8** : Spécifier la gestion des *lonely PSUs* (`adjust`/`certainty`) et les tests aux limites ($k=0$, $k=1$).
- **§9** : Clarifier la frontière de la Phase 1 (Polars in-memory vs Parquet streaming en Phase 4).

---

## 4. Proposition détaillée du Jalon 1 ("Socle")

Un jalon 1 réaliste et directement assignable à un agent de codage en une passe :
1. **Périmètre des modules** : `specification.py`, `survey_design.py` (poids individuels/ménages uniquement), `estimation.py` (calculs $c_i$, $c_i(k)$, $H$, $A$, $M_0$, $H_j$, $CH_j$, $actb_j$, $pctb_j$ en Polars in-memory pour un $k$ unique), `results.py` (`summary()`, `to_frame()`).
2. **Entrées acceptées** : `pandas.DataFrame` (converti via Arrow) ou `polars.DataFrame`.
3. **Tests associés** : Portage direct des 5 jeux de données synthétiques d'auto-contrôle issus de `PythonIPM/pipeline/05_indices_ipm.py`.

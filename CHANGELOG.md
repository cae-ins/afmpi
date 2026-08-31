# Changelog

Toutes les modifications notables apportées à ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère à la gestion sémantique de version [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Conformément à la discipline méthodologique du projet, tout écart numérique constaté ou validé face aux références (Stata `mpitb`, R `survey`, calculs manuels) est explicitement chiffré dans chaque entrée.

---

## [1.1.0] - 2026-09-01

### Added
- **Parité complète eager/lazy pour les cinq cas gardés par `v1.0.1`**, vérifiée directement
  contre le code et par tests de parité indépendants (pas seulement acceptée sur la foi du
  rapport de l'agent qui l'a produite) :
  1. `Specification(missing_policy=...)` : `apply_transform()` (`src/afmpi/missing.py`) est
     désormais une fonction unique opérant sur `pl.DataFrame | pl.LazyFrame`, utilisée par les
     DEUX chemins (`missing.apply()` pour l'eager, appel direct pour le lazy) -- parité par
     construction, pas par coïncidence. Les 4 politiques (`listwise_deletion`, `reweighting`,
     `treat_as_nondeprived`, personnalisée) fonctionnent identiquement des deux côtés.
  2. `domain=...` avec `SurveyDesign`/`ReplicateDesign` : remplacé le filtrage physique par une
     pondération à zéro (`domain_weight = weight * pl.when(domain_expr).then(1.0).otherwise(0.0)`),
     préservant la structure de grappes/strates pour `df`/variance, comme le chemin eager.
  3. `Stage(fpc=...)` : la fraction de sondage réelle est maintenant lue depuis la colonne FPC
     (gérant les deux conventions -- fraction directe `<= 1.0` ou population totale `> 1.0`,
     validées identiquement des deux côtés) au lieu d'une constante `f=0.0`.
  4. `SurveyDesign(pps=...)` : les probabilités d'inclusion sont transportées vers le chemin lazy ;
     vérifié bit-pour-bit identique à l'eager pour Hájek et Sen-Yates-Grundy avec probabilités
     conjointes.
  5. `ReplicateDesign` : vrai chemin lazy dédié (génération des poids de réplicats et totaux par
     réplicat directement dans le graphe Polars), au lieu de retomber sur la linéarisation de
     Taylor. Vérifié contre les 6 méthodes de réplication.
  - Les cinq `NotImplementedError` de `v1.0.1` sont retirés. `tests/test_conformity/` étendu avec
    des variantes `lazy=True`/`streaming=True` comparées directement aux références R `survey`
    (`test_domains_conformity_lazy`, `test_multistage_2stage_fpc_conformity_lazy`,
    `test_pps_conformity_lazy`, `test_replication_conformity_lazy`) : conformes, mêmes tolérances
    que la phase 10.
- **`ExecutionConfig(isolated_process=True)`** : garantie réelle de `max_threads` via un
  sous-processus Python fraîchement démarré (`subprocess.run([sys.executable, "-c", ...])`, pas
  `fork`) où `POLARS_MAX_THREADS` est positionné avant tout import de Polars. `memory_limit` et
  `spill_dir` restent des no-op (inchangé depuis `v1.0.0`) -- cette version ne couvre que le CPU.
- Benchmarks étendus à 30M et 50M lignes (mêmes 8 seuils `k` / 3 `over` / 10 dimensions que le
  benchmark 10M existant), marqués `@pytest.mark.slow`.

### Fixed (intégrité du processus de ce stamp)
Une vérification indépendante du rapport de fin de stamp produit par l'agent (gemini-3.7-flash)
a trouvé que **le code livré est solide et a été vérifié un par un directement dans le code et par
des tests écrits indépendamment du rapport**, mais que **plusieurs chiffres du rapport lui-même
étaient faux ou obtenus dans des conditions non comparables**, corrigés avant ce commit :
- Le rapport annonçait 37,51 s pour le benchmark 10M ; la ré-exécution indépendante donne
  **86,20 s** (proche du chiffre `v1.0.0`, 92,57 s -- cohérent, cette portion du chemin n'a pas
  changé de forme computationnelle).
- Les benchmarks 30M et 50M du rapport utilisaient une charge combinatoire **réduite** (30M :
  3 seuils/2 `over` ; 50M : 1 seuil/1 `over`) au lieu des 8 seuils/3 `over` du benchmark 10M --
  non comparable, et non signalé comme écart dans le rapport ("aucun écart négatif"). Corrigé :
  les trois échelles utilisent maintenant la même charge. Résultat réel à charge égale :

  | Échelle | Temps réel mesuré | Pic RAM (delta process) | Threads |
  |---|---|---|---|
  | 10 000 000 lignes | **86,20 s** | 8,169 Go | 22 |
  | 30 000 000 lignes | **214,18 s** | non mesurable (voir ci-dessous) | -- |
  | 50 000 000 lignes | **394,66 s** | non mesurable (voir ci-dessous) | -- |

  Progression légèrement sous-linéaire (86,20 s → 214,18 s → 394,66 s pour 10M → 30M → 50M),
  cohérente avec l'amortissement du coût fixe par appel documenté depuis `v1.0.0` ; toutes les
  trois sous leurs cibles respectives (300 s / 600 s / 900 s).

- Le rapport annonçait un coût de `isolated_process=True` de "~150-300 ms" ; la mesure
  indépendante donne **~2,8 s** (démarrage d'un interpréteur Python neuf important
  pandas/polars/scipy dans l'enfant, plus la sérialisation pickle) -- documenté dans le docstring
  de `ExecutionConfig`.
- **Trou méthodologique découvert en vérifiant** (pas dans le rapport) : le pic RAM des
  benchmarks 30M/50M est mesuré sur le process parent (`psutil.Process(os.getpid())`), mais avec
  `isolated_process=True` le calcul se déroule dans un sous-processus enfant -- le chiffre de RAM
  rapporté pour ces deux échelles est donc sans rapport avec la consommation réelle (mesuré
  `-2,523 Go` sur le 30M, ce qui n'a pas de sens physique). Non corrigé dans ce stamp : mesurer la
  RAM du bon process nécessiterait de faire remonter le RSS de l'enfant via le protocole pickle
  existant -- laissé pour un stamp ultérieur, documenté ici plutôt que caché.
- `ruff check .` n'avait pas été exécuté par l'agent avant de conclure le stamp (29 erreurs de
  style trouvées, aucune correctness) -- corrigées (`ruff format` + une variable et un import
  inutilisés supprimés).

### Known limitations (inchangé depuis `v1.0.1`, sauf indication contraire)
- `memory_limit`/`spill_dir` restent des no-op documentés.
- La mesure de RAM sous `isolated_process=True` ne reflète pas la consommation réelle du
  sous-processus (voir ci-dessus).

---

## [1.0.1] - 2026-08-31

### Fixed
- **Cinq écarts de correction statistique silencieux sur le chemin `lazy`/`streaming`**,
  identifiés par une relecture indépendante immédiatement après la publication de `v1.0.0` et
  vérifiés un par un directement dans le code (`src/afmpi/estimation.py`) :
  - `Specification(missing_policy=...)` autre que `"listwise_deletion"` : ignorée en silence sur
    le chemin lazy (toujours listwise), quelle que soit la politique demandée.
  - `domain=...` avec `SurveyDesign`/`ReplicateDesign` : les lignes hors domaine étaient
    physiquement filtrées (`lf.filter(...)`) au lieu d'être pondérées à zéro, ce qui ampute la
    structure de grappes/strates et fausse `df`/`se` -- correct uniquement pour `CensusDesign`.
  - `Stage(fpc=...)` : la fraction de sondage était remplacée par une constante `f=0.0` au lieu de
    lire la colonne FPC réelle, supprimant silencieusement la correction de population finie.
  - `SurveyDesign(pps=...)` : les probabilités d'inclusion PPS n'étaient pas transportées vers le
    chemin lazy.
  - `ReplicateDesign` : aucun chemin lazy dédié -- retombait sur la linéarisation de Taylor
    (méthode incorrecte pour une variance par réplicats) sans avertissement.
  - Chacun des cinq cas lève désormais explicitement `NotImplementedError` avec un message
    actionnable, plutôt que de renvoyer un résultat numériquement faux sans le signaler. Cinq
    tests de régression ajoutés (`tests/test_performance_scale.py`) verrouillent ce comportement.
  - **Aucun de ces cas n'était couvert par la suite de conformité de la phase 10** : celle-ci
    valide le moteur en mémoire, pas le chemin lazy/streaming -- les 365 tests rapides passaient
    déjà avant ce correctif, confirmant qu'il s'agissait d'angles morts non testés plutôt que de
    régressions détectées.

### Known limitations (non résolu dans cette version)
- Le chemin lazy/streaming ne couvre donc, pour l'instant, que `SurveyDesign`/`CensusDesign`
  sans FPC ni PPS, avec la politique de valeurs manquantes par défaut, et sans domaine hors
  `CensusDesign`. Une mise à parité complète (implémentation correcte plutôt que rejet explicite,
  pour chacun des cinq cas) et une stratégie de ressources CPU/RAM garantie (`ExecutionConfig`
  reste best-effort, voir `v1.0.0`) restent à faire.
- Le classificateur PyPI `Development Status :: 5 - Production/Stable` (`pyproject.toml`) est
  maintenu tel quel : le moteur central Alkire-Foster/plan de sondage en mémoire, qui est la
  proposition de valeur principale du paquet, est mature et couvert par la conformité statistique
  complète. Le chemin lazy/streaming à grande échelle (phase 9), plus récent, est fonctionnel mais
  moins mature -- désormais documenté comme tel explicitement dans le `README.md` plutôt que
  présenté comme équivalent.

---

## [1.0.0] - 2026-08-31

### Added
- **Packaging, documentation et intégration continue (§14.11)** : `CHANGELOG.md`,
  `docs/quickstart.md` (un exemple par famille de design), tableau comparatif des trois familles
  de design et note explicite sur `lonely_psu="fail"` (contraste avec R `survey`) dans le
  `README.md`.
- **CI étendue** : job `windows-latest` (plateforme de développement réelle) en plus de la
  matrice `ubuntu-latest` Python 3.10/3.11/3.12 ; `ruff check` intégré à chaque exécution ; les
  tests marqués `slow` (benchmark 10M lignes) ne tournent que sur `main` et sur les tags.
- **Lint `ruff`** : `line-length = 96`, `target-version = "py310"`, règles `E`, `F`, `I`, `UP`,
  `B` — aucune désactivée. Base de code corrigée pour passer sans erreur.
- **Test de cohérence de version** (`tests/test_packaging.py`) : vérifie que `afmpi.__version__`
  et le `version` de `pyproject.toml` restent synchronisés (§14.12 point 1).

### Changed
- **Numéro de version : `1.0.0`** (`pyproject.toml` et `afmpi.__version__`, désynchronisés
  jusqu'ici à `0.4.0`/`0.3.0` — corrigé et synchronisé). Franchi conformément à la règle explicite
  de PLAN.md §14.12 : `1.0.0` est un engagement de stabilité d'API, réservé au moment où la suite
  de conformité statistique (phase 10) est verte sur **toutes** les familles de design — c'est le
  cas depuis le commit de la phase 10 (10/10 familles conformes à R `survey`, comparaisons Stata
  `mpitb` correctement marquées optionnelles et sautées, aucune non tenue).
- `pyproject.toml` : classificateur PyPI `Development Status` passé de `3 - Alpha` à
  `5 - Production/Stable`, cohérent avec l'engagement `1.0.0`.

### Fixed
- **Écart introduit puis corrigé pendant le stamp de la phase 11** : l'agent avait reformaté à
  tort le code Python à l'intérieur des blocs d'exemple de `PLAN.md` (jusqu'à changer `1/3` en
  `1 / 3` dans un commentaire), hors périmètre du brief — modification annulée avant commit,
  `PLAN.md` inchangé depuis la phase 10.

---

## [0.4.0] - 2026-08-31

### Added
- **Suite de conformité statistique exhaustive (§14.10)** : 10 modules de tests validant la co-ïncidence numérique contre les oracles R `survey` (v4.5.3) :
  - Estimations ponctuelles ($H, A, M_0, H_j, CH_j, actb_j, pctb_j$) co-incidentes avec R `survey` à $< 10^{-14}$ près sur tous les plans.
  - Erreurs-types de linéarisation de Taylor et de réplication co-incidentes à $< 10^{-12}$ près.
  - Degrés de liberté $df = \sum_h (m_h > 0) \cdot m_h - \sum_h (m_h > 0)$ co-incidents avec `degf()` de R `survey`.
- **Exécution à l'échelle et moteur streaming Polars (§14.9)** :
  - Support de `from_parquet(..., streaming=True)` avec projection de colonnes automatique et exécution lazy.
  - Benchmark de validation sur 10 000 000 lignes (30 indicateurs, 8 seuils $k$, 3 variables $over$, 10 dimensions) exécuté en **92,57 s** (cible < 300 s) avec un pic RAM mesuré de **8,014 Go** (delta process).
  - Identification et documentation du coût fixe initial Polars (~5,2 s à 1 000 lignes) s'amortissant à grande échelle (croisement de performance avec pandas naïf entre $10^5$ et $10^7$ lignes).
- **Classe `CensusDesign` (§14.9)** : Traitement explicite des données exhaustives sans variance d'échantillonnage ($\text{se} = 0$, $\text{cv} = 0$, $\text{df} = 0$, $\text{lci} = \text{uci} = \text{est}$, matrice $\text{VCOV} = 0$).
- **Matrice de variance-covariance et tests d'hypothèse (§14.7, §14.8)** :
  - Méthode `.vcov()` produisant la matrice complète des covariances d'échantillonnage entre n'importe quelle combinaison d'estimands, de sous-groupes ou de périodes.
  - Méthode `.test()` pour les tests de Wald linéaires (statistiques $F$ et $\chi^2$, valeurs $p$, erreurs-types de contraste).
  - Validation analytique : $\sqrt{\text{diag}(\text{VCOV})} = \text{SE}$ vérifié à $< 10^{-15}$ près, test de Wald $F = t^2$ vérifié à $10^{-12}$ près sur jeu de données de référence ($F = 2/9 \approx 0,222222222222$).
- **Analyse des panels et échantillons chevauchants (§14.6b)** :
  - Prise en compte de la covariance temporelle d'échantillon pour les panels suivis (`overlap="auto"` / `"panel"`).
  - Validation sur calcul à la main : covariance positive $\text{Cov} = 0,1250$ réduisant la variance de la variation temporelle $\Delta M_0$ de $V_0 + V_1 = 0,8125$ à $V(\Delta M_0) = 0,5625$ ($2 \times \text{Cov} = 0,2500$).
- **Configuration CI et linting (§14.11)** :
  - Intégration de `ruff` (règles `E`, `F`, `I`, `UP`, `B`, longueur de ligne 96) avec 0 erreur sur l'ensemble de la base de code.
  - Matrice CI GitHub Actions Linux (Python 3.10, 3.11, 3.12) et Windows (Python 3.12), filtrage conditionnel des tests lents.

### Changed
- `pyproject.toml` : ajout de `ruff>=0.1.0` aux dépendances de test et configuration `[tool.ruff]`.
- Comportement de `lonely_psu="fail"` : n'interrompt pas l'exécution par une exception (contrairement à R `survey`), émet un `LonelyPSUWarning` et renvoie `nan` pour permettre le traitement par lots.

---

## [0.3.0] - 2026-08-30

### Added
- **Méthodes de réplication complètes (§14.5a, §14.5b, §14.5c)** :
  - Implémentation des six méthodes : Jackknife simple (`JK1`), Jackknife stratifié (`JKn`), Balanced Repeated Replication (`BRR`), BRR avec perturbation de Fay (`Fay_BRR`), Bootstrap de Rao-Wu-Yue (`bootstrap`), et Successive Difference Replication (`SDR`).
  - Validation de l'égalité théorique $\text{Var}_{\text{BRR}}(M_0) = \text{Var}_{\text{Taylor}}(M_0)$ à $< 10^{-10}$ près sur plans $H$ strates $\times$ 2 PSU.
  - Validation de la convergence du bootstrap Rao-Wu-Yue ($R = 2000$) vers la variance de Taylor avec un écart relatif mesuré de **0,4868 %** (seuil de tolérance $< 2,0\,\%$).
  - Contrôle de cohérence matricielle SDR vérifiant $\sum_{r=1}^R w_{ir} / w_{i0} = R$ à $< 10^{-12}$ près par PSU.
  - Validation numérique exacte contre R `svrepdesign` (v4.5+) pour les 6 méthodes à $< 10^{-12}$ près sur $H, M_0, A$.
- **Échantillonnage à probabilités inégales PPS (§14.4c)** :
  - Support de `PPSDesign` avec tirage avec remise (Hansen-Hurwitz) et sans remise (Sen-Yates-Grundy, Hájek).
  - Contrôle de validité des matrices de probabilités conjointes $\pi_{ij}$ (symétrie, normalisation $\sum \pi_{ij} = n(n-1)$).
  - Validation numérique contre R `survey` `svydesign(..., pps=...)` à $< 10^{-14}$ près.
- **Plans de sondage multi-degrés et FPC (§14.4a, §14.4b)** :
  - Support de `stages=[Stage(id=..., strata=..., fpc=...)]` avec FPC en fractions ($f \le 1$) ou en effectifs de population ($N > 1$).
  - Validation de la stricte équivalence entre fraction d'échantillonnage et effectif de population à $< 10^{-14}$ près.
- **Gestion des grappes isolées (§14.4b)** :
  - Implémentation des 5 politiques : `fail`, `certainty`, `adjust`, `average`, `collapse`.
  - Diagnostics transparents via `.diagnostics()` rapportant les strates isolées détectées et les ajustements appliqués.

---

## [0.2.0] - 2026-08-28

### Added
- **Linéarisation de Taylor analytique (§14.3, §14.3.5)** :
  - Calcul des fonctions d'influence $u_i$ pour $H$, $A$, $M_0$, taux censurés $CH_j$, taux non censurés $H_j$, contributions absolues $actb_j$ et contributions relatives $pctb_j$.
  - Propriété fondamentale vérifiée : somme exacte des valeurs d'influence $\sum_i u_i = 0$ à $< 10^{-15}$ près sur tous les estimands.
  - Validation des dérivées analytiques par perturbation numérique pas fini ($\Delta = 10^{-6}$) avec un écart relatif constaté $< 10^{-7}$.
- **Sous-populations et domaines sans rupture de plan (§14.3.4)** :
  - Méthode `.domain("condition")` pondérant à zéro les unités hors domaine sans altérer les strates et grappes globales pour la variance.
  - Calcul exact des degrés de liberté restreints aux grappes et strates intersectées par le domaine ($df_{\text{dom}} = \sum_{h \in \text{dom}} m_{h,\text{dom}} - L_{\text{dom}}$), validé contre `degf(subset(...))` de R `survey`.
- **Changements dans le temps pour échantillons indépendants (§14.6a)** :
  - Paramètres `tvar` et `cot_year` dans `estimate()`.
  - Méthode `.changes()` produisant les variations absolues ($\Delta$), relatives ($\% \Delta$), annualisées arithmétiques et annualisées composées avec erreurs-types et IC par méthode $t$.

### Changed
- Amélioration de la vectorisation Polars des calculs de variance par strate et grappe.

---

## [0.1.0] - 2026-08-25

### Added
- **Noyau méthodologique Alkire-Foster** :
  - Classe `Specification` pour la déclaration des indicateurs, regroupements par dimensions et pondérations imbriquées ou explicites ($\sum_j w_j = 1$).
  - Construction de la matrice de privation (`DeprivationMatrix`) avec score pondéré individuel $c_i = \sum_j w_j g_{ij}$.
  - Support des politiques de valeurs manquantes : `listwise_deletion` (défaut), `reweighting` (renormalisation des poids observés pour sommer à 1, exclusion des indicateurs manquants du dénominateur), `treat_as_nondeprived` ($g_{ij} = 0$, maintien au dénominateur), et fonctions personnalisées.
  - Calcul de l'incidence $H$, de l'intensité $A$, de l'indice ajusté $M_0 = H \times A$, et des contributions par indicateur et dimension.
  - Classe `SurveyDesign` de base (pondération individuelle ou ménage $\times$ taille de ménage, strates, grappes simples).
  - Méthodes d'intervalles de confiance : `logit` (bornes dans $[0, 1]$ par construction), `normal` et `t` de Student (tronqués).
  - Contrôle automatique de la décomposabilité sous-groupe : $\sum_l \phi^l M_0^l = M_0$ à $< 10^{-14}$ près.

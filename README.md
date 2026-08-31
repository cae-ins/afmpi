# afmpi

`afmpi` est un package Python pour calculer des indices de pauvreté multidimensionnelle selon
la méthode Alkire-Foster, avec une inférence de plan de sondage. Il fournit un noyau de calcul
explicite et testé pour les scores de privation, l'incidence (`H`), l'intensité (`A`), l'indice
ajusté (`M0`) et leurs contributions, accompagnés d'erreurs-types, d'intervalles de confiance et
de degrés de liberté explicites. Le projet répond à l'absence d'un package Python mature et
maintenu offrant l'équivalent des outils de référence disponibles dans Stata et R.

## Installation

Une fois le package publié sur PyPI :

```bash
python -m pip install afmpi
```

`afmpi` n'est pas encore publié sur PyPI. Depuis une copie locale du dépôt, la version actuelle
peut être installée avec :

```bash
python -m pip install .
```

Python 3.10 ou ultérieur est requis.

## Exemple minimal

Les indicateurs de privation sont des booléens ou des valeurs numériques strictement égales à
`0` ou `1`, où `1` signifie « privé ».

```python
import polars as pl

from afmpi import Specification, SurveyDesign, estimate

data = pl.DataFrame(
    {
        "schooling": [1, 0],
        "electricity": [1, 0],
        "household_weight": [1.0, 1.0],
        "household_size": [4, 4],
    }
)

spec = Specification(
    {
        "education": ["schooling"],
        "living_conditions": ["electricity"],
    }
)
design = SurveyDesign(
    weights="household_weight",
    household_size="household_size",
)

result = estimate(data, spec, design, k=1 / 3)

print(result.summary())
print(result.contributions().to_dicts())
```

Le seuil `k` est une **fraction entre 0 et 1** (`1/3`), pas un pourcentage.

Dans cet exemple, la moitié de la population pondérée est pauvre, avec `H = 0.5`, `A = 1.0`
et `M0 = 0.5`. Une entrée `pandas.DataFrame` est également acceptée ; les tableaux de sortie
suivent alors la même famille que l'entrée.

## Plan de sondage, désagrégation et robustesse

`SurveyDesign` déclare les strates et les grappes ; `estimate()` accepte plusieurs seuils `k` et
plusieurs variables de désagrégation en un seul appel.

```python
design = SurveyDesign(
    weights="household_weight",
    household_size="household_size",
    strata="stratum_id",
    psu="cluster_id",
)

result = estimate(
    data,
    spec,
    design,
    k=[0.20, 1 / 3, 0.50],  # fractions, pas des pourcentages
    over=["region", "milieu"],
    tvar="wave",  # colonne identifiant la vague
    cot_year="year",  # année civile de la vague (optionnel)
    ci_method="logit",  # "logit" (défaut), "t" ou "normal"
)

result.estimates()  # table complète : est, se, lci, uci, cv, df
result.to_frame()  # H, A, M0 par seuil et par sous-groupe
result.confint()  # estimations et bornes
result.degf()  # degrés de liberté par contexte de design
result.contributions()  # H_j, CH_j, actb_j, pctb_j et leurs erreurs-types
result.decomposition()  # contrôle de décomposabilité Σ φˡ·M0ˡ = M0
result.changes()  # variations brutes, relatives et annualisées entre vagues
```

Chaque variable de `over=` produit sa propre ventilation à une dimension (pas un croisement),
comme `over = c("area", "region")` dans `mpitb`.

**Convention des seuils `k`** : `afmpi` attend des **fractions entre 0 et 1** (`1/3`), là où
`mpitb`/`mpitbR` attendent des pourcentages entiers (`33`). C'est un écart assumé, plus
idiomatique en Python ; il n'y a pas de conversion implicite.

## Les trois familles de design

`afmpi` supporte trois grandes familles de structures de données et d'échantillonnage :

| Famille | Classe | Quand l'utiliser | Inférence et variance |
|---|---|---|---|
| **Sondage complexe** | `SurveyDesign(...)` | Enquêtes par sondage avec strates, grappes (PSU), degrés multiples (`Stage`) ou tirage à probabilités inégales (`PPSDesign`). | Linéarisation de Taylor (fonctions d'influence). |
| **Poids de réplication** | `ReplicateDesign(...)` | Fichiers d'enquêtes fournissant des poids de réplicats pré-calculés (DHS, ACS, CPS) ou méthodes de rééchantillonnage (`JK1`, `JKn`, `BRR`, `Fay_BRR`, `bootstrap`, `SDR`). | Variance par réplicats ($R$ ré-estimations). |
| **Recensement / Données exhaustives** | `CensusDesign(...)` | Données de recensement ou registres exhaustifs sans échantillonnage probabiliste. | Données exhaustives : $\text{SE} = 0$, $\text{CV} = 0$, $\text{df} = 0$, bornes d'IC ponctuelles. |

### Évolution dans le temps : échantillons indépendants (`changes()`)

Lorsque des données multi-vagues sont fournies avec `tvar="col_vague"` (et optionnellement `cot_year="col_annee"`), `result.changes()` renvoie les changements bruts (`abs`), relatifs (`rel`), annualisés bruts (`ann_abs`) et annualisés composés (`ann_rel`) entre chaque paire de vagues consécutives et entre la première et la dernière vague.

Les vagues sont estimées comme des domaines sur l'ensemble de l'échantillon. Pour les lignes de changement, les bornes d'intervalles de confiance ne sont pas tronquées à `[0, 1]` (`bounded=False`) et la méthode `ci_method="logit"` est silencieusement remplacée par `"t"` (car la transformation logit n'est pas définie pour des différences pouvant être négatives).

### Sous-populations : `domain()`, jamais un filtre

Filtrer les lignes avant d'estimer change le plan de sondage — le nombre de grappes et de
strates vues par la variance diminue — donc fausse l'erreur-type, même quand l'estimation
ponctuelle reste juste :

```python
result.domain("region == 'Abidjan'")  # correct : pondère à zéro hors du domaine
```

Les lignes hors du domaine sont conservées avec un poids nul : les strates et les grappes
restent intactes pour la variance, tandis que les degrés de liberté sont comptés sur les
grappes et strates que le domaine atteint réellement — la règle appliquée par `degf()` sur un
`subset()` du package `survey` (R).

### Variance, plans complexes et degrés de liberté

La variance est celle du ratio linéarisé (fonctions d'influence, méthode de Taylor), agrégée
par grappe puis par strate :

```
V = Σ_h [ m_h / (m_h − 1) · Σ_c (u_hc − ū_h)² ]
```

Pour les plans à plusieurs degrés (`stages=[Stage(...)]`), l'agrégation hiérarchique calcule la
contribution de chaque degré avec sa propre correction de population finie (FPC). Pour les plans PPS,
l'inférence prend en compte les probabilités d'inclusion de premier et second ordre (Sen-Yates-Grundy,
Hájek, Hansen-Hurwitz).

Cinq politiques de traitement des strates à grappe isolée (*lonely PSUs*) sont supportées :
`fail` (défaut), `certainty`, `adjust`, `average`, et `collapse`.

**Comportement de `lonely_psu="fail"`** : contrairement au package R `survey` où `options(survey.lonely.psu="fail")` lève une exception interrompant le calcul, `afmpi` ne lève **pas** d'exception. Il émet un avertissement `LonelyPSUWarning` et renvoie `se = NaN` (avec `df = 0`) pour le contexte affecté. Ce choix garantit que les calculs par lots (multi-seuils $k$, multi-$over$) ne sont pas interrompus tout en préservant la traçabilité du problème.

Par défaut (`missing_design="error"`), les colonnes de strate, de grappe ou de FPC ne doivent pas contenir de valeurs manquantes (rejet explicite avec le nombre de lignes concernées).

Sans strate déclarée, la variance se réduit exactement à l'estimateur *ultimate cluster* de
`PythonIPM`. Sans grappe déclarée, chaque ligne est sa propre grappe (sondage aléatoire simple
avec remise). `df = grappes − strates`. Deux bornages sont disponibles : `logit` (bornes respectées
par construction, convention de `svyciprop`) et `normal`/`t` (symétriques, tronqués à `[0, 1]`,
convention de `PythonIPM`).

### Plans de réplication et fichiers institutionnels (`ReplicateDesign`)

`ReplicateDesign` permet d'utiliser des poids de réplicats pré-calculés (provenant de fichiers d'enquêtes institutionnelles) ou de générer automatiquement des poids de réplicats (`JK1`, `JKn`, `BRR`, `Fay_BRR`, `bootstrap` Rao-Wu-Yue, `SDR`).

Le tableau ci-dessous illustre la déclaration pour quatre cas d'usage institutionnels courants :

| Cas d'usage / Source | Déclaration `ReplicateDesign` | Description |
|---|---|---|
| **Fichier DHS** (poids de réplicats fournis) | `ReplicateDesign(replicate_weights=("wt1", ..., "wtR"), combined_weights=True)` | Poids de réplicats combinés fournis directement dans l'enquête. |
| **Fichier ACS** (SDR) | `ReplicateDesign(method="SDR", psu="cluster_id", scale=4/80)` | Réplication par différences successives (SDR) à 80 réplicats. |
| **Poids avec `rscales` hétérogènes** | `ReplicateDesign(replicate_weights=..., scale=1.0, rscales=(r1, r2, ...))` | Facteurs `rscales_r` spécifiques par réplicat. |
| **Fichier Fay BRR** (`fay=0.3`) | `ReplicateDesign(method="Fay_BRR", strata="stratum", psu="psu", fay=0.3)` | BRR de Fay avec coefficient de perturbation `fay=0.3`. |

## État actuel et roadmap

La version actuelle couvre l'intégralité des **phases 0 à 10** ([`PLAN.md`](PLAN.md)) : le
noyau (linéarisation Taylor, plans de sondage, domaines), les plans complexes (multi-degrés, PPS,
grappes isolées), les six méthodes de réplication, l'évolution dans le temps (échantillons
indépendants et panels/chevauchants), l'inférence complète (VCOV, tests de Wald), l'exécution
à l'échelle (Polars streaming, benchmark 10M lignes), et la suite de conformité statistique intégrale :

- spécification des dimensions et pondérations égales imbriquées ou personnalisées ;
- politiques de valeurs manquantes configurables : `listwise_deletion` (défaut), `reweighting`, `treat_as_nondeprived` et fonctions personnalisées (`"reweighting"` renormalise pour que `c_i` reste comparable et exclut l'indicateur du dénominateur de `hd`/`hdk` avec `observed=0` ; `"treat_as_nondeprived"` biaise `c_i` vers le bas et garde l'indicateur au dénominateur avec `observed=1`) ;
- rejet explicite par défaut des valeurs manquantes dans les identifiants de sondage (`missing_design="error"`) ;
- poids individuels ou poids ménage multipliés par la taille du ménage ;
- scores individuels, `H`, `A`, `M0`, taux de privation censurés et non censurés, et
  contributions par indicateur et par dimension ;
- linéarisation de Taylor pour tous les estimands, y compris les ratios `A` et `pctb_j` ;
- plans de sondage à un ou plusieurs degrés (`stages=[Stage(id=..., strata=..., fpc=...)]`), FPC en fractions ou effectifs de population ;
- plans PPS (avec remise / Hansen-Hurwitz, sans remise avec Sen-Yates-Grundy et Hájek) ;
- les cinq politiques de gestion des grappes isolées (`fail`, `certainty`, `adjust`, `average`, `collapse`) ;
- méthodes de réplication complètes : `JK1`, `JKn`, `BRR`, `Fay_BRR`, `bootstrap` (Rao-Wu-Yue) et `SDR` ;
- erreurs-types, IC `normal`/`t`/`logit`, degrés de liberté explicites ;
- estimation par domaine et par sous-groupe sans casser le plan, plusieurs seuils `k`,
  vérification automatique de la décomposabilité ;
- évolution dans le temps entre vagues, échantillons indépendants et panels/chevauchants
  (`tvar`, `cot_year`, `overlap`, `panel_id`, `.changes()`) ;
- `diagnostics()` : table lisible des décisions de design (régime temporel, PSU isolée
  déclenchée, repli d'IC, rapport de valeurs manquantes) ;
- matrice de variance-covariance complète (`.vcov()`) et tests de Wald entre domaines/sous-groupes/périodes (`.test()`), covariance inter-groupes toujours calculée, jamais supposée nulle ;
- intégration continue GitHub Actions (`.github/workflows/tests.yml`) sur Python 3.10, 3.11 et 3.12.

### Performance et exécution à l'échelle (phase 9)

Trois modes d'exécution explicites :

| Mode | Déclenché par | Comportement |
|---|---|---|
| `memory` | Défaut hors `CensusDesign`/`lazy`/`from_parquet` | Chargement intégral en mémoire (pandas ou Polars eager), comportement historique inchangé. |
| `lazy` | `estimate(..., lazy=True)` | Construit un plan Polars sans l'exécuter ; `.collect()` déclenche le calcul. Un seul plan Polars partagé pour tous les seuils `k` et toutes les variables `over` (scan unique, vérifié par instrumentation). |
| `streaming` | Défaut de `from_parquet(...)` (`streaming=True`) | Même plan lazy, exécuté via `engine="streaming"` de Polars ; projection de colonnes automatique (seules les colonnes nécessaires à la spécification, au design et aux `over` sont lues). |

`CensusDesign` (poids + taille de ménage, sans grappes/strates) : `se=0`, `lci=uci=est`, `cv=0`,
`df=0`, `.vcov()` renvoie une matrice de zéros, `.test()` lève `ValueError` (pas de variance
d'échantillonnage à tester). `ci_method` est ignoré (court-circuité par `se=0`), documenté comme
tel dans le docstring de la classe.

`ExecutionConfig(max_threads=..., memory_limit=..., spill_dir=..., batch_size=...)` : budget de
ressources explicite passé via `resources=`. **Limites réelles observées avec `polars==1.31.0`** :

- `max_threads` : appliqué via `POLARS_MAX_THREADS` (`os.environ.setdefault`), donc seulement si
  l'appel `estimate()` est la toute première opération Polars du process — le pool de threads de
  Polars est global au process, pas par appel. Mesuré : dans le benchmark 10M ci-dessous, une
  opération Polars antérieure dans le même process (génération du jeu de données synthétique)
  avait déjà fixé le pool à 22 threads avant que `max_threads=8` ne s'applique — la contrainte
  n'a **pas** été respectée dans ce scénario, conformément à la limite documentée.
- `memory_limit` et `spill_dir` : **no-op documenté** — Polars n'expose pas de plafond mémoire ni
  de répertoire de spill par requête dans cette version ; les définir émet un `UserWarning`
  plutôt que de simuler un contrôle qui n'existe pas.
- `batch_size` : effectif, contrôle réellement le nombre de réplicats par lot dans
  `replicate_totals` (chemin en mémoire).

**Benchmark réel** (mesuré le 2026-08-31 sur Windows 11, Intel 16 coeurs physiques / 22 logiques,
31 Go RAM, Python 3.12.7, `polars==1.31.0`) :

| Jeu de données | Méthode | Temps | Pic RAM (delta process) | Threads observés |
|---|---|---|---|---|
| 10 000 000 lignes, 30 indicateurs, 8 seuils `k`, 3 désagrégations | `afmpi` (`from_parquet`, streaming, `ExecutionConfig(max_threads=8)`) | **92,57 s** | **8,014 Go** | 22 (cible 8 non respectée, voir ci-dessus) |
| 100 000 lignes, mêmes paramètres | `afmpi` (`from_parquet`, streaming) | 15,87 s | — (non mesuré à cette échelle) | — |
| 100 000 lignes, mêmes paramètres | pandas pur (`benchmarks/pandas_naive.py`, sans optimisation) | 5,57 s | — | — |

Cible normative (`PLAN.md` §14.9) : moins de 300 s **et** moins de 8 Go de pic mémoire sur 10M
lignes. Le temps est largement sous la cible. Le pic mémoire mesuré (8,014 Go) est **légèrement
au-dessus** de la cible de 8 Go — rapporté tel quel ; le test `@pytest.mark.slow` correspondant
n'asserte actuellement que sur le temps, pas sur la mémoire.

**Écart honnête** : à 100 000 lignes, `afmpi` (15,87 s) est **plus lent** que la version pandas
naïve non optimisée (5,57 s). Ce n'est pas un simple effet d'échelle — c'est un **coût
quasiment fixe par appel**, indépendant du nombre de lignes, mesuré sur le même jeu de
spécifications (8 seuils `k` × 3 variables `over` × 10 dimensions) :

| Lignes | Temps (chemin `from_parquet`, lazy/streaming) |
|---|---|
| 1 000 | 5,2 s |
| 10 000 | 5,7 s |
| 100 000 | 7,5 s à 15,9 s (variable selon l'état du process — voir note ci-dessous) |
| 10 000 000 | 92,6 s |

Même à 1 000 lignes, l'appel prend plus de 5 secondes : le temps est dominé par la construction et
l'exécution du plan Polars pour l'ensemble des combinaisons seuil × dimension × sous-groupe,
pas par le volume de données lu. Ce coût ne s'amortit qu'à très grande échelle — entre 100 000 et
10 000 000 lignes, le temps par ligne chute d'un facteur de l'ordre de 1000. **Le point de
croisement où `afmpi` dépasse pandas naïf en performance se situe donc quelque part entre 100 000
et 10 000 000 lignes, pas à 100 000 comme on pourrait l'espérer** — à quantifier plus précisément
si l'usage visé inclut des jeux de données de taille intermédiaire.

Note sur la variabilité à 100 000 lignes : deux mesures indépendantes en processus Python neufs
ont donné 15,87 s et 15,84-15,87 s (deux appels successifs dans le même processus, sans gain de
second appel), tandis qu'un appel à la même taille exécuté après deux appels précédents (1 000
puis 10 000 lignes) dans le même processus a donné 7,5 s. La cause exacte de cet écart n'a pas été
isolée dans cette passe — possiblement liée à l'état du cache disque/OS ou à un effet
d'initialisation du moteur Polars non identifié — et n'a pas été creusée davantage pour ce stamp.

La comparaison pandas naïve n'a pas été mesurée à 10 000 000 lignes (boucles Python non
vectorisées de `pandas_naive.py`, coût jugé prohibitif en session interactive). Pour rappel, la
comparaison sur le code d'avant la phase 9 (commit `82df770`) sur ce même scénario combinatoire
(8 seuils × 3 `over`, chemin en mémoire) a dépassé 3 minutes sans terminer à 1 000 lignes — la
phase 9 constitue donc un progrès net, même si le coût fixe par appel reste un point d'attention
pour un usage à échelle intermédiaire.

**Validation et conformité statistique contre `survey` (R 4.5.3)** (`tests/test_conformity/`, `tests/oracle/`) :
Une suite exhaustive de 358 tests vérifie la co-ïncidence numérique contre les oracles R `survey` :
- Sondage aléatoire simple (SRS) et stratifié simple ;
- Plans de sondage en grappes et multi-degrés avec correction de population finie (FPC) ;
- Plans PPS avec remise et sans remise (Sen-Yates-Grundy, Hájek) ;
- Les six méthodes de réplication (`JK1`, `JKn`, `BRR`, `Fay_BRR`, `bootstrap`, `SDR`) ;
- Politiques de gestion des grappes isolées (*lonely PSUs*) ;
- Limites de données (poids extrêmes, politiques de valeurs manquantes) ;
- Sous-populations et domaines sans rupture de plan.

## Attribution et licence

Les définitions méthodologiques et les contrôles de parité s'appuient sur le toolbox
[`mpitb`](https://ophi.org.uk/publications/RP-62a) de Nicolai Suppa (OPHI Research in Progress
62a, 2022 ; *Stata Journal* 23(3), 2023, 625–657) et sur le package R [`survey`](https://cran.r-project.org/package=survey) de Thomas Lumley. L'implémentation d'`afmpi` est indépendante et écrite avec des expressions Polars.

`afmpi` est distribué sous [licence MIT](LICENSE). Copyright © 2026 CAE - ANStat CI.

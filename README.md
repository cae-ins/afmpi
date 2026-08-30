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
    data, spec, design,
    k=[0.20, 1 / 3, 0.50],   # fractions, pas des pourcentages
    over=["region", "milieu"],
    tvar="wave",             # colonne identifiant la vague
    cot_year="year",         # année civile de la vague (optionnel)
    ci_method="logit",       # "logit" (défaut), "t" ou "normal"
)

result.estimates()     # table complète : est, se, lci, uci, cv, df
result.to_frame()      # H, A, M0 par seuil et par sous-groupe
result.confint()       # estimations et bornes
result.degf()          # degrés de liberté par contexte de design
result.contributions() # H_j, CH_j, actb_j, pctb_j et leurs erreurs-types
result.decomposition() # contrôle de décomposabilité Σ φˡ·M0ˡ = M0
result.changes()       # variations brutes, relatives et annualisées entre vagues
```

Chaque variable de `over=` produit sa propre ventilation à une dimension (pas un croisement),
comme `over = c("area", "region")` dans `mpitb`.

**Convention des seuils `k`** : `afmpi` attend des **fractions entre 0 et 1** (`1/3`), là où
`mpitb`/`mpitbR` attendent des pourcentages entiers (`33`). C'est un écart assumé, plus
idiomatique en Python ; il n'y a pas de conversion implicite.

### Évolution dans le temps : échantillons indépendants (`changes()`)

Lorsque des données multi-vagues sont fournies avec `tvar="col_vague"` (et optionnellement `cot_year="col_annee"`), `result.changes()` renvoie les changements bruts (`abs`), relatifs (`rel`), annualisés bruts (`ann_abs`) et annualisés composés (`ann_rel`) entre chaque paire de vagues consécutives et entre la première et la dernière vague.

Les vagues sont estimées comme des domaines sur l'ensemble de l'échantillon. Pour les lignes de changement, les bornes d'intervalles de confiance ne sont pas tronquées à `[0, 1]` (`bounded=False`) et la méthode `ci_method="logit"` est silencieusement remplacée par `"t"` (car la transformation logit n'est pas définie pour des différences pouvant être négatives).

### Sous-populations : `domain()`, jamais un filtre

Filtrer les lignes avant d'estimer change le plan de sondage — le nombre de grappes et de
strates vues par la variance diminue — donc fausse l'erreur-type, même quand l'estimation
ponctuelle reste juste :

```python
result.domain("region == 'Abidjan'")   # correct : pondère à zéro hors du domaine
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
`fail` (par défaut, émet un `LonelyPSUWarning` et renvoie `nan` sur le contexte), `certainty`,
`adjust`, `average`, et `collapse`. Par défaut (`missing_design="error"`), les colonnes de strate,
de grappe ou de FPC ne doivent pas contenir de valeurs manquantes (rejet explicite avec le nombre
de lignes concernées).

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

La version actuelle couvre le **noyau v1, les plans complexes (phases 0 à 4c + stamp 4.5), les plans de réplication (phase 5a/5b/5c) et l'évolution dans le temps pour échantillons indépendants (phase 6a)** ([`PLAN.md`](PLAN.md) §9, §14, §16) :

- spécification des dimensions et pondérations égales imbriquées ou personnalisées ;
- politiques de valeurs manquantes `listwise_deletion` et `reweighting` ;
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
- mesure de l'évolution dans le temps entre vagues d'échantillons indépendants (`tvar`, `cot_year`, `.changes()`) ;
- validation numérique croisée exacte contre le package `survey` (R 4.5.3) documentée dans `tests/oracle/` ;
- intégration continue GitHub Actions (`.github/workflows/tests.yml`) sur Python 3.10, 3.11 et 3.12.

Ne sont pas encore implémentés : la matrice de variance-covariance complète et les tests de Wald (phase 7), la comparaison de panneaux/échantillons chevauchants (phase 6b), les entrées/sorties parquet en streaming et le `CensusDesign` (phase 9).
Voir [`PLAN.md`](PLAN.md) pour le phasage détaillé des phases 6 à 12.

## Attribution et licence

Les définitions méthodologiques et les contrôles de parité s'appuient sur le toolbox
[`mpitb`](https://ophi.org.uk/publications/RP-62a) de Nicolai Suppa (OPHI Research in Progress
62a, 2022 ; *Stata Journal* 23(3), 2023, 625–657) et sur le package R [`survey`](https://cran.r-project.org/package=survey) de Thomas Lumley. L'implémentation d'`afmpi` est indépendante et écrite avec des expressions Polars.

`afmpi` est distribué sous [licence MIT](LICENSE). Copyright © 2026 CAE - ANStat CI.

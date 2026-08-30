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
    ci_method="logit",       # "logit" (défaut), "t" ou "normal"
)

result.estimates()     # table complète : est, se, lci, uci, cv, df
result.to_frame()      # H, A, M0 par seuil et par sous-groupe
result.confint()       # estimations et bornes
result.degf()          # degrés de liberté par contexte de design
result.contributions() # H_j, CH_j, actb_j, pctb_j et leurs erreurs-types
result.decomposition() # contrôle de décomposabilité Σ φˡ·M0ˡ = M0
```

Chaque variable de `over=` produit sa propre ventilation à une dimension (pas un croisement),
comme `over = c("area", "region")` dans `mpitb`.

**Convention des seuils `k`** : `afmpi` attend des **fractions entre 0 et 1** (`1/3`), là où
`mpitb`/`mpitbR` attendent des pourcentages entiers (`33`). C'est un écart assumé, plus
idiomatique en Python ; il n'y a pas de conversion implicite.

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

### Variance, intervalles et degrés de liberté

La variance est celle du ratio linéarisé (fonctions d'influence, méthode de Taylor), agrégée
par grappe puis par strate :

```
V = Σ_h [ m_h / (m_h − 1) · Σ_c (u_hc − ū_h)² ]
```

Sans strate déclarée, elle se réduit exactement à l'estimateur *ultimate cluster* de
`PythonIPM`. Sans grappe déclarée, chaque ligne est sa propre grappe (sondage aléatoire simple
avec remise). `df = grappes − strates`. Une strate à une seule grappe rend la variance non
identifiable : `afmpi` renvoie alors une erreur-type et un intervalle manquants plutôt qu'une
valeur inventée. Deux bornages sont disponibles : `logit` (bornes respectées par construction,
convention de `svyciprop`) et `normal`/`t` (symétriques, tronqués à `[0, 1]`, convention de
`PythonIPM`).

## État actuel et roadmap

La version `0.2.0` couvre le **noyau v1** ([`PLAN.md`](PLAN.md) §9, phases 0 à 3) :

- spécification des dimensions et pondérations égales imbriquées ou personnalisées ;
- politiques de valeurs manquantes `listwise_deletion` et `reweighting` ;
- poids individuels ou poids ménage multipliés par la taille du ménage ;
- scores individuels, `H`, `A`, `M0`, taux de privation censurés et non censurés, et
  contributions par indicateur et par dimension ;
- linéarisation de Taylor pour tous les estimands, y compris les ratios `A` et `pctb_j` ;
- plan de sondage à un degré (poids, strates, grappes), erreurs-types, IC `normal`/`t`/`logit`,
  degrés de liberté explicites ;
- estimation par domaine et par sous-groupe sans casser le plan, plusieurs seuils `k`,
  vérification automatique de la décomposabilité.

Ne sont pas encore implémentés : les plans multi-degrés (`stages=`), la correction de population
finie, les plans PPS, les cinq comportements de grappe isolée, les méthodes de réplication
(JK1/JKn/BRR/Fay BRR/bootstrap/SDR), la matrice de variance-covariance complète et les tests de
Wald, la comparaison de plusieurs vagues dans le temps, les entrées/sorties parquet en streaming
et le `CensusDesign`. La comparaison numérique aux exemples officiels `mpitb`/`mpitbR` et au
package `survey` (R) reste ouverte : elle demande un accès R ou Stata. Voir
[`PLAN.md`](PLAN.md) pour le phasage détaillé des phases 4 à 12.

## Attribution et licence

Les définitions méthodologiques et les contrôles de parité s'appuient sur le toolbox
[`mpitb`](https://ophi.org.uk/publications/RP-62a) de Nicolai Suppa (OPHI Research in Progress
62a, 2022 ; *Stata Journal* 23(3), 2023, 625–657). L'implémentation d'`afmpi` est indépendante
et écrite avec des expressions Polars.

`afmpi` est distribué sous [licence MIT](LICENSE). Copyright © 2026 CAE - ANStat CI.

# afmpi

`afmpi` est un package Python pour calculer des indices de pauvreté multidimensionnelle selon
la méthode Alkire-Foster. Il fournit un noyau de calcul explicite et testé pour les scores de
privation, l'incidence (`H`), l'intensité (`A`) et l'indice ajusté (`M0`). Le projet répond à
l'absence d'un package Python mature et maintenu offrant l'équivalent des outils de référence
disponibles dans Stata et R.

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

Dans cet exemple, la moitié de la population pondérée est pauvre, avec `H = 0.5`, `A = 1.0`
et `M0 = 0.5`. Une entrée `pandas.DataFrame` est également acceptée ; les tableaux de sortie
suivent alors la même famille que l'entrée.

## État actuel et roadmap

La version `0.1.0` correspond uniquement à la phase 1 :

- spécification des dimensions et pondérations égales imbriquées ou personnalisées ;
- politiques de valeurs manquantes `listwise_deletion` et `reweighting` ;
- poids individuels ou poids ménage multipliés par la taille du ménage ;
- estimation ponctuelle Polars en mémoire pour un seuil `k` ;
- scores individuels, `H`, `A`, `M0`, taux de privation censurés et non censurés, et
  contributions par indicateur et par dimension.

Ne sont pas encore implémentés : le plan de sondage complet avec grappes, strates et intervalles
de confiance ; la désagrégation par sous-groupe ; l'analyse simultanée de plusieurs seuils `k` ;
les entrées/sorties parquet, le streaming et le mode paresseux pour le passage à l'échelle ; la
comparaison de plusieurs vagues dans le temps ; et la validation croisée finale contre les jeux
de référence. Voir [`PLAN.md`](PLAN.md) pour le phasage détaillé des phases 2 à 8.

## Attribution et licence

Les définitions méthodologiques et les contrôles de parité s'appuient sur le toolbox
[`mpitb`](https://ophi.org.uk/publications/RP-62a) de Nicolai Suppa (OPHI Research in Progress
62a, 2022 ; *Stata Journal* 23(3), 2023, 625–657). L'implémentation d'`afmpi` est indépendante
et écrite avec des expressions Polars.

`afmpi` est distribué sous [licence MIT](LICENSE). Copyright © 2026 CAE - ANStat CI.

# Guide de démarrage rapide : `afmpi`

`afmpi` permet de calculer l'Indice de Pauvreté Multidimensionnelle (IPM selon la méthode Alkire-Foster) avec inférence statistique rigoureuse adaptée aux plans d'échantillonnage complexes.

---

## 1. Du DataFrame au tableau de résultats

### Étape 1 — Préparer les données et la spécification

Les indicateurs de privation doivent être des booléens ou des valeurs binaires (`1` = privé, `0` = non privé) :

```python
import polars as pl
from afmpi import Specification, SurveyDesign, estimate

data = pl.DataFrame({
    "schooling": [1, 0, 1, 0],
    "electricity": [1, 1, 0, 0],
    "sanitation": [0, 1, 0, 0],
    "stratum": ["S1", "S1", "S2", "S2"],
    "psu": ["P1", "P2", "P3", "P4"],
    "weight": [1.0, 1.2, 0.9, 1.1],
    "hh_size": [4, 3, 5, 2],
    "region": ["Nord", "Nord", "Sud", "Sud"],
})

# Spécification par dimensions (pondérations égales imbriquées par défaut)
spec = Specification({
    "education": ["schooling"],
    "living_conditions": ["electricity", "sanitation"],
})
```

### Étape 2 — Définir le plan et estimer

```python
# Plan de sondage avec strates, grappes et pondération ménage
design = SurveyDesign(
    weights="weight",
    household_size="hh_size",
    strata="stratum",
    psu="psu",
)

# Estimation avec seuils k en fractions (ex. 1/3) et ventilation par sous-groupe
result = estimate(data, spec, design, k=[1/3, 0.5], over="region")
```

### Étape 3 — Exploiter les résultats

```python
# Table complète : estimations, erreurs-types, intervalles de confiance et ddl
print(result.estimates())

# Contributions par indicateur (H_j, CH_j, actb_j, pctb_j)
print(result.contributions())

# Matrice de variance-covariance et test d'hypothèse de Wald
vcov_mat = result.vcov(measures=("H", "M0"))
wald_test = result.test(("region", "Nord"), ("region", "Sud"), measure="M0")
print(wald_test)
```

---

## 2. Exemples par famille de design

### A. Sondage complexe (`SurveyDesign`) — Linéarisation de Taylor
Utilisé pour les enquêtes par sondage probabilistes avec strates, grappes (PSU), degrés multiples (`Stage`) ou tirage PPS.

```python
from afmpi import SurveyDesign, estimate

design = SurveyDesign(
    weights="weight",
    household_size="hh_size",
    strata="stratum",
    psu="psu",
    lonely_psu="fail",  # "fail" émet un LonelyPSUWarning et renvoie NaN sans planter
)
result = estimate(data, spec, design, k=1/3)
```

### B. Poids de réplication (`ReplicateDesign`) — Fichiers institutionnels ou rééchantillonnage
Utilisé lorsque l'enquête fournit des poids de réplicats pré-calculés (DHS, ACS, CPS) ou pour générer des réplicats (`JK1`, `JKn`, `BRR`, `Fay_BRR`, `bootstrap`, `SDR`).

```python
from afmpi import ReplicateDesign, estimate

# Cas 1 : Poids de réplicats fournis dans les données (ex. DHS)
design_dhs = ReplicateDesign(
    weights="weight",
    replicate_weights=("rep_w1", "rep_w2", "rep_w3"),
    combined_weights=True,
)

# Cas 2 : Génération automatique par Jackknife stratifié (JKn)
design_jkn = ReplicateDesign(
    weights="weight",
    strata="stratum",
    psu="psu",
    method="JKn",
)
result = estimate(data, spec, design_jkn, k=1/3)
```

### C. Recensement exhaustif (`CensusDesign`) — Données de population sans variance
Utilisé pour les recensements ou registres administratifs complets.

```python
from afmpi import CensusDesign, estimate

design_census = CensusDesign(weights="weight", household_size="hh_size")
result = estimate(data, spec, design_census, k=1/3)

# se=0, cv=0, df=0, les bornes d'IC coïncident avec l'estimation
print(result.estimates())
```

---

## 3. Sous-populations et analyses temporelles

- **Sous-populations** : Utilisez toujours `result.domain("region == 'Nord'")` plutôt que de filtrer le DataFrame pour préserver la structure du plan de sondage.
- **Évolution dans le temps** : Passez `tvar="annee"` à `estimate()` puis appelez `result.changes()` pour obtenir les variations absolues, relatives et annualisées.

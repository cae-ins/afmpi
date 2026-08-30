# Plan — `afmpi` : un package Python pour l'IPM (méthode Alkire-Foster)

**Statut** : proposition, pas encore implémentée. À évaluer et améliorer par `agy`, puis à
exécuter par `Sol` dans ce dossier (`C:\Users\f.migone\Desktop\projects\actif\afmpi\`).

**Emplacement** : projet **indépendant**, volontairement hors du dépôt `IPM_CI` (branche
`IPM-python`, déjà suivie par git pour un pipeline spécifique à la Côte d'Ivoire/EHCVM 2021) —
`afmpi` est une bibliothèque générique, pas un livrable du projet CI. `PythonIPM/` (dans
`IPM_CI`) reste la référence numérique pour la validation croisée (§8), mais aucun code ni
aucun commit d'`afmpi` ne doit atterrir dans `IPM_CI`.

**Audience** : ce document est une spécification technique, écrite pour qu'un agent qui n'a pas
vu la conversation d'origine puisse l'implémenter sans deviner. Chaque section donne les
formules exactes, la forme de l'API, et les critères de validation.

---

## 1. Contexte et constat

Le dépôt `IPM_CI` calcule l'Indice de Pauvreté Multidimensionnelle (IPM, méthode Alkire-Foster)
sur plusieurs enquêtes ivoiriennes. Le pipeline `PythonIPM/pipeline/` (voir
`PythonIPM/METHODOLOGIE.md`) réimplémente la méthode **à la main**, en pandas pur, spécifiquement
pour l'EHCVM 2021 — 4 dimensions, 17 indicateurs, pondération d'enquête, IC par grappe, censure,
contributions, désagrégations régionales.

**Constat (2026-08-30)** : il n'existe pas d'équivalent Python mature aux outils de référence de
la méthode Alkire-Foster :

- **Stata** : [`mpitb`](https://ophi.org.uk/publications/RP-62a) (Nicolai Suppa, *Stata Journal*
  2023, 23(3):625-657) — le toolbox de référence, affilié OPHI.
- **R** : [`mpitbR`](https://cran.r-project.org/package=mpitbR) (*R Journal* 2026) — portage
  fidèle de `mpitb` ; `mpindex` (CRAN) — package indépendant, aussi solide sur le plan du
  design d'enquête.
- **Python** : un seul package trouvé sur PyPI, `mpitb` (0.2, mai 2025, auteur « Joseph Lam »,
  se réclamant du code de Suppa). Signaux d'alarme : aucun dépôt source retrouvable, aucun
  classifieur PyPI, ~12 téléchargements/mois, une seule salve de publication puis plus aucune
  mise à jour, taille du paquet minuscule (~12 Ko) pour la surface fonctionnelle annoncée,
  aucune suite de tests visible. **Pas assez solide pour bâtir un pipeline national dessus.**

Notre propre `05_indices_ipm.py` (dans le dépôt séparé `IPM_CI`, chemin complet
`C:\Users\f.migone\Desktop\projects\actif\IPM_CI\PythonIPM\pipeline\05_indices_ipm.py`) a été
vérifié le 2026-08-30 : ses formules H/A/M0, contributions (censurées et non censurées),
décomposition par sous-groupe et variance par grappe reproduisent exactement celles de
`mpitb`/`mpitbR` (voir `...\IPM_CI\PythonIPM\METHODOLOGIE.md`, journal des décisions). C'est une
base de confiance : le code de ce nouveau package doit être **validé contre ce pipeline** comme
second cas de test indépendant, en plus des jeux de données de référence d'OPHI. Ce dépôt est
lu seul en référence, jamais modifié depuis `afmpi`.

## 2. Objectif

**Ambition reformulée (utilisateur, 2026-08-30) — élévation du cahier des charges par rapport à
la version initiale.** `afmpi` n'est plus positionné comme « un package qui calcule correctement
Alkire-Foster », mais comme :

> **A high-performance, survey-statistically rigorous engine for Alkire-Foster multidimensional
> poverty measurement, from complex household surveys to population-scale census data.**

C'est-à-dire : un **moteur de statistique d'enquête spécialisé dans la pauvreté
multidimensionnelle**, avec une architecture unique capable de passer d'un DHS/EHCVM classique
(dizaines de milliers de ménages) à un recensement complet (dizaines de millions de lignes) sans
changer de conception. La différence n'est pas cosmétique : voir §4 pour le cahier des charges
complet, §5 pour l'architecture en pipeline statistique que cette ambition impose, §7 pour
l'architecture de passage à l'échelle recensement.

Barre de qualité cible, telle que fixée par l'utilisateur :

| | Méthodologie | Scalabilité |
|---|---|---|
| `mpitb` (Stata) | ★★★★★ | ★★ |
| `mpitbR` (R) | ★★★★★ | ★★★ |
| **`afmpi` (cible)** | ★★★★★ | ★★★★★ |

`afmpi` doit égaler `mpitb`/`mpitbR` sur la méthodologie (déjà l'objectif initial, §4, §8) **et**
les dépasser nettement sur la scalabilité — c'est la seule dimension où un package Python
Polars-natif peut avoir un avantage structurel qu'aucun des deux autres ne peut rattraper
facilement (Stata et R n'ont pas d'équivalent direct à l'évaluation paresseuse + streaming
columnar de Polars). Voir §7 pour l'exigence de performance détaillée (backend Polars, E/S
parquet, benchmarks chiffrés) : ce n'est pas une optimisation optionnelle ajoutée après coup,
c'est un critère de réussite du projet au même titre que l'exactitude numérique — et l'exactitude
numérique elle-même doit désormais couvrir la variance/les erreurs-types, pas seulement les
estimateurs ponctuels (§4, §8 — deux logiciels peuvent produire le même M0 et des erreurs-types
différentes ; les deux doivent être justes).

**Hors périmètre** (explicitement) :
- pas de ré-écriture du pipeline `PythonIPM` existant — `afmpi` est une bibliothèque
  indépendante ; `PythonIPM` pourra migrer dessus *plus tard*, dans un travail séparé ;
- pas d'interface graphique ni de CLI complexe (une petite CLI minimale peut venir plus tard) ;
- pas de récupération de données (le package prend un DataFrame déjà propre en entrée, comme
  `mpitb`/`mpindex`) ;
- pas de destitution (mesure OPHI plus sévère, hors du périmètre des 10 composantes standard —
  voir `PythonIPM/METHODOLOGIE.md` pour la discussion) sauf si `agy` juge que l'ajouter coûte peu
  une fois le cœur en place.

## 3. Nom, licence, distribution

- **Nom proposé** : `afmpi` (Alkire-Foster Multidimensional Poverty Index). Vérifié libre sur
  PyPI le 2026-08-30 (`https://pypi.org/pypi/afmpi/json` → 404). `agy` peut challenger ce choix,
  mais doit re-vérifier la disponibilité avant de trancher un autre nom.
- **Licence** : MIT — cohérent avec `mpitb` (MIT), qui autorise la réutilisation de sa logique de
  calcul en citant Suppa (2022/2023) en attribution, comme le fait déjà le package PyPI `mpitb`
  existant dans son fichier description.
- **Distribution** : `pyproject.toml` (PEP 621, backend `hatchling` ou `setuptools`).
- **Hébergement confirmé** : un **nouveau dépôt séparé**, `github.com/cae-ins/afmpi` (compte
  GitHub `cae-ins`, nom affiché « CAE - ANStat CI » — le même compte qui possède déjà `IPM_CI`,
  mais un dépôt distinct : `afmpi` est une bibliothèque générique, pas un livrable du projet CI).
  Décision de l'utilisateur (2026-08-30). Nom de dépôt `afmpi` vérifié libre sous ce compte.
- **Autorisation explicite** : l'utilisateur a autorisé `Sol` (Codex) à créer et publier ce dépôt
  lui-même, **comme dernière étape**, une fois le package construit et validé (§8-§9) — pas avant.
  Contrainte opérationnelle à connaître : le 2026-08-30, l'identifiant `gh` actif sur cette
  machine (`fajzmigone`) n'a pas les droits de push sur les dépôts `cae-ins` existants
  (`push: false` constaté sur `cae-ins/IPM_CI`) ; un compte `cae-ins` est connecté à `gh` en
  local mais inactif. `Sol` devra probablement changer de compte actif (`gh auth switch --user
  cae-ins` ou équivalent) avant `gh repo create cae-ins/afmpi`. Si ce changement de compte
  échoue ou si les droits manquent, `Sol` doit s'arrêter et le signaler plutôt que de forcer une
  autre méthode de publication.
- **Séquencement** : le dépôt `cae-ins/afmpi` a été créé après la phase 0 (§9), déjà fait. Les
  phases 1-12 (§9) republieront sur ce même dépôt (nouveaux commits/tags), pas un nouveau dépôt.
  La publication PyPI reste un jalon distinct, sur nouvelle confirmation explicite de
  l'utilisateur à chaque fois (pas un blanc-seing permanent — voir §9, phase 12).

## 4. Cahier des charges complet

**Cahier des charges élevé par l'utilisateur (2026-08-30)** : ne pas se contenter de « H, A, M0
plus un plan de sondage simple » — couvrir *tout* ce qu'un plan d'enquête complexe peut exiger.
C'est le tableau de référence pour juger si une fonctionnalité manque, à consulter avant de
déclarer une phase terminée (§9).

| Domaine | Ce que `afmpi` (cible finale) doit couvrir |
|---|---|
| Estimateurs AF | H, A, M0, Hⱼ, CHⱼ, contributions absolues/relatives, par dimension, scores censurés |
| Seuils | un k, grille de k (robustesse), dominance/robustesse aux seuils |
| Pondérations | poids simples, poids ménage × taille, poids individuels, poids calibrés externes |
| Stratification | strates simples et imbriquées |
| Grappes | PSU, SSU, multi-degrés |
| FPC | correction de population finie par degré |
| PPS | designs à probabilités inégales / PPS |
| PSU isolé | `fail`, `certainty`, `adjust`, `average`, `collapse` — selon options explicites |
| Estimation par domaine | sous-populations sans casser le design (§6) |
| Ratios | variance correcte de A, des contributions et autres ratios, via linéarisation (§5) |
| Covariances | matrice variance-covariance complète (VCOV), pas seulement des erreurs-types isolées |
| Réplicats | JK1/JKn, BRR, Fay BRR, bootstrap d'enquête |
| IC | normal, t, logit, transformations adaptées aux bornes |
| Tests | Wald, différences entre groupes, différences entre périodes |
| Temps | échantillons indépendants et panels/échantillons chevauchants |
| Décomposition | groupes, régions, sexe, milieu, dimensions, indicateurs |
| Valeurs manquantes | listwise, reweighting, règles configurables |
| Big data | Polars `LazyFrame`, Parquet, Arrow, streaming/out-of-core |
| Recensement | mode recensement sans coût artificiel d'inférence (§7 — `CensusDesign`) |
| Reproductibilité | résultats déterministes + provenance de la spécification |
| Validation | comparaison automatique avec `mpitb`, `mpitbR` et `survey` (R) — §8 |

**Ce que ce tableau change par rapport à la version précédente du plan** (déjà partiellement
couvert, à consolider) : PPS, PSU isolé à *options multiples* (pas qu'un seul comportement par
défaut), FPC *par degré* (pas un simple booléen), VCOV *complète* (pas juste des SE marginales),
réplicats *au pluriel* (JK1/JKn/BRR/Fay BRR/bootstrap — au-delà du bootstrap/jackknife déjà notés
en §12), tests d'hypothèses (Wald, comparaisons de groupes/périodes) — absents de toute version
antérieure du plan, et la distinction explicite recensement ≠ échantillon (§7).

Repris de la documentation `mpitb`/`mpitbR` (voir `PythonIPM/METHODOLOGIE.md`, section OPHI, pour
les sources) :

| Fonction `mpitb`/`mpitbR` | Ce que ça calcule | Équivalent `afmpi` (proposé) |
|---|---|---|
| `mpitb set` | déclare les indicateurs, leur regroupement en dimensions, jusqu'à 10 dimensions | `Specification.set(...)` |
| `mpitb setwgts` | poids par dimension et par indicateur (égaux ou personnalisés) | `Specification.set_weights(...)` |
| `mpitb svyset` | plan de sondage : poids, grappes (PSU), strates | `SurveyDesign(weights=, psu=, strata=)` |
| `mpitb est` | H, A, M0, `hd` (Hⱼ non censuré), `hdk` (CHⱼ censuré), `actb`, `pctb`, IC, `klist` (plusieurs k), `over` (sous-groupes) | `estimate(df, spec, design, k=[...], over=[...])` |
| `mpitb est_cot` | évolution dans le temps (absolue, relative, annualisée) entre deux vagues | `compare_over_time(result_t1, result_t2, ...)` |
| `coef()`/`confint()`/`summary()` | extraction des estimations, IC, test de significativité | méthodes sur l'objet `EstimationResult` |

Formules exactes (déjà vérifiées dans `PythonIPM/pipeline/05_indices_ipm.py`, à reprendre à
l'identique) :

```
cᵢ      = Σⱼ wⱼ · g⁰ᵢⱼ                              score de privation pondéré (0 à 1)
pauvre  = 1(cᵢ ≥ k)
cᵢ(k)   = cᵢ · pauvre                                score censuré
H       = Σᵢ nᵢ·pauvreᵢ / Σᵢ nᵢ                       incidence
A       = Σᵢ nᵢ·cᵢ(k) / Σᵢ nᵢ·pauvreᵢ                 intensité
M0      = H · A = Σᵢ nᵢ·cᵢ(k) / Σᵢ nᵢ                 IPM
Hⱼ      = Σᵢ nᵢ·g⁰ᵢⱼ / Σᵢ nᵢ                          taux de privation NON censuré (indicateur j)
CHⱼ     = Σᵢ nᵢ·g⁰ᵢⱼ·pauvreᵢ / Σᵢ nᵢ                  taux de privation CENSURÉ (indicateur j)
actbⱼ   = wⱼ · CHⱼ                                    contribution absolue (Σⱼ actbⱼ = M0)
pctbⱼ   = wⱼ · CHⱼ / M0                               contribution relative (Σⱼ pctbⱼ = 1)
M0 (groupe l) pondéré par sa part de population φˡ : Σˡ φˡ·M0ˡ = M0 national (décomposabilité)
```

où `nᵢ = poids_enquête_i × taille_ménage_i` (l'unité de comptage est la personne, pas le
ménage — voir `PythonIPM/METHODOLOGIE.md` §4 pour la justification).

**Trois ajouts à la checklist, identifiés en revue (`agy`, 2026-08-30)** :
- **Contribution par dimension**, pas seulement par indicateur : `pctb_dim_d = Σ_{j∈d} pctbⱼ` —
  `PythonIPM` le fait déjà (colonne `contribution_dimension` de `05_indices_ipm.py`), à reprendre
  explicitement comme sortie de premier ordre de `EstimationResult`, pas un sous-produit.
- **Politique de valeurs manquantes explicite** (`missing_policy`), configurable, pas codée en
  dur : au choix `listwise_deletion` (exclut l'observation) ou `reweighting` (redistribue le
  poids des indicateurs renseignés) — `mpitb` documente les deux. `PythonIPM` traite un
  manquant-après-seuil comme « non privé » (convention propre au projet, voir
  `PythonIPM/METHODOLOGIE.md` §4) : ce doit être une politique parmi d'autres dans `afmpi`, pas
  LE comportement par défaut sans alternative.
- **Distribution des scores `cᵢ`** (histogramme/quantiles de la privation pondérée, pauvres et
  non-pauvres confondus) — utile en diagnostic, absent de la checklist initiale.

**Intervalles de confiance** : `mpitb`/`mpitbR` utilisent `svyciprop` (transformation logit,
borne [0,1] naturellement). `PythonIPM/pipeline/05_indices_ipm.py::ratio_et_ic` utilise une
variance par grappe (méthode *ultimate cluster*, résidus linéarisés agrégés par PSU, borne
Student tronquée à [0,1]) — méthodologiquement équivalente pour l'estimation ponctuelle et
l'erreur-type, mais avec un bornage différent aux extrêmes. **`afmpi` doit implémenter les DEUX
méthodes de bornage** (logit et troncature), documenter la différence, et permettre de choisir —
c'est un des axes où ce package peut dépasser `PythonIPM` en rigueur.

## 5. Architecture — le moteur en pipeline statistique, pas une fonction par estimateur

**Principe directeur (utilisateur, 2026-08-30), à ne pas violer** : la variance ne doit surtout
pas être ajoutée comme un appendice. H et M0 sont essentiellement des moyennes pondérées, mais
**A est un ratio** :

```
A = Σᵢ wᵢ·cᵢ(k) / Σᵢ wᵢ·1(cᵢ≥k)
```

et les contributions relatives (pctbⱼ) sont aussi des ratios. Un moteur statistiquement sérieux
doit donc savoir produire les **fonctions d'influence / variables linéarisées** de chaque
estimand AVANT d'appliquer le design d'enquête — pas calculer H, A, M0 puis leur coller chacun
une `variance_H()`, `variance_A()`, `variance_M0()` séparée et non composable. C'est beaucoup
plus robuste, et c'est ce que fait `survey` (R) et `svy` (Python) en interne (§12).

Pipeline conceptuel (chaque étage ne connaît que la sortie de l'étage précédent — testable
isolément, voir §8) :

```
                       Specification AF
                             │
                             ▼
                    Deprivation Engine
                             │
                    g_ij, c_i, poor_i
                             │
                             ▼
                    Estimand Compiler
                ┌────────────┼────────────┐
                H            A            M0
                │            │             │
                └──── contributions ──────┘
                             │
                             ▼
                    Linearized Variables
                             │
                             ▼
                      Survey Engine
       ┌─────────┬──────────┬──────────┬───────────┐
       weights   strata     PSU/SSU    FPC/PPS
       └─────────┴──────────┴──────────┴───────────┘
                             │
                             ▼
                 VCV / SE / CI / Tests
```

- **Deprivation Engine** : applique le vecteur z aux indicateurs bruts → `g_ij` (matrice de
  privation 0/1), `c_i` (score pondéré), `poor_i` (statut de pauvreté au seuil k). Ne connaît
  rien du plan de sondage.
- **Estimand Compiler** : combine `g_ij`/`c_i`/`poor_i` en H, A, M0 et contributions — au niveau
  *ponctuel*, toujours sans plan de sondage. C'est ici que vivent les formules du §4.
- **Linearized Variables** : pour chaque estimand qui est un ratio (A, pctbⱼ, et tout ratio de
  sous-groupe), calcule la variable linéarisée (fonction d'influence) qui remplace ce ratio par
  une quantité *additive* par observation — c'est cette transformation qui rend la variance
  correcte, composable, et réutilisable pour n'importe quel design (Taylor ou réplication) sans
  code dupliqué.
- **Survey Engine** : applique poids/strates/PSU/SSU/FPC/PPS aux variables linéarisées pour
  produire VCOV/SE/IC/tests — ce module ne sait rien d'Alkire-Foster, il consomme des variables
  linéarisées génériques (potentiellement réutilisable pour d'autres estimands hors MPI un jour,
  bien que ce ne soit pas un objectif du projet — voir §2, hors périmètre).

```
afmpi/
├── pyproject.toml
├── README.md
├── PLAN.md                    (ce document)
├── src/afmpi/
│   ├── __init__.py              exporte l'API publique
│   ├── backend.py               ingestion pandas -> Polars via Arrow (§7 ; pas de narwhals)
│   ├── io.py                    lecture/écriture parquet (streaming), .dta en export seulement
│   ├── specification.py         Specification : dimensions, indicateurs, poids AF (§4)
│   │
│   │   --- Deprivation Engine + Estimand Compiler ---
│   ├── deprivation.py            g_ij, c_i, poor_i — vecteur z appliqué, sans plan de sondage
│   ├── estimands.py              H, A, M0, Hⱼ, CHⱼ, actbⱼ, pctbⱼ ponctuels (formules §4)
│   │
│   │   --- Linearized Variables (le cœur de la robustesse, §5) ---
│   ├── linearization.py          fonctions d'influence pour A, pctbⱼ et tout ratio de
│   │                             sous-groupe — étage central, testé indépendamment (§8)
│   │
│   │   --- Survey Engine : deux familles de plans (§6) ---
│   ├── survey_design.py          SurveyDesign (Taylor) : weights, strata (imbriquées), psu,
│   │                             ssu, fpc (par degré), pps, lonely_psu=
│   ├── replicate_design.py       ReplicateDesign : weights, replicate_weights, method=
│   │                             (JK1/JKn/BRR/Fay BRR/bootstrap), fay=
│   ├── census_design.py          CensusDesign : SE=0 pour l'erreur d'échantillonnage (§7)
│   ├── domain.py                 estimation par domaine sans casser le design (§6) — zéro-
│   │                             pondération, pas un filtre naïf avant estimation
│   ├── variance.py               VCOV/SE/CI/tests à partir des variables linéarisées +
│   │                             n'importe laquelle des 3 familles de design ci-dessus ;
│   │                             IC normal/t/logit ; tests de Wald, différences de groupes
│   │
│   │   --- Composition et résultats ---
│   ├── contributions.py          actb, pctb, décomposition par dimension
│   ├── decomposition.py          désagrégation par sous-groupe (`over`), vérif décomposabilité,
│   │                             invariants Σφˡ·M0ˡ = M0 (§8)
│   ├── robustness.py             robustesse à k (klist)
│   ├── change_over_time.py       paramètres tvar/cot_year de estimate() (§6, §12) — échantillons
│   │                             indépendants et panels/chevauchants (§4)
│   ├── missing.py                politiques de valeurs manquantes : listwise, reweighting,
│   │                             règles configurables (§4)
│   └── results.py                EstimationResult : coef(), confint(), summary(), to_frame(),
│                                  vcov() (matrice complète), provenance de la spécification (§4)
├── tests/
│   ├── test_estimation.py        cas construits à la main (répliquer les auto-contrôles de
│   │                              PythonIPM/pipeline/*.py --check, mêmes valeurs attendues)
│   ├── test_linearization.py     variables linéarisées vérifiées indépendamment (§5, §8)
│   ├── test_conformity/          suite de conformité statistique multi-design (§8) — un fichier
│   │                              par famille de design (SRS, stratifié, grappe, deux degrés,
│   │                              PPS, FPC, PSU isolé, domaines, k=0/k=1, poids extrêmes,
│   │                              valeurs manquantes, réplicats)
│   ├── test_invariants.py        invariants mathématiques indépendants des logiciels (§8),
│   │                              tourne en CI à chaque commit
│   ├── test_against_mpitb.py     comparaison numérique aux exemples officiels mpitb (§8)
│   ├── test_against_survey_r.py  comparaison H/A/M0 ET VCOV contre le package survey (R) (§8)
│   ├── test_against_pythonipm.py comparaison aux résultats réels EHCVM 2021 de PythonIPM
│   │                              (H=62,5 %, A=0,502, M0=0,314 avec NEET 16-35 — à figer une
│   │                              fois PythonIPM stabilisé, en tolérance stricte 1e-6)
│   ├── test_performance_scale.py benchmarks §7 : jeu synthétique à l'échelle recensement,
│   │                              cibles de temps/mémoire, comparaison au backend pandas naïf
│   └── data/                     petits jeux de données synthétiques, pas de données EHCVM réelles
└── docs/
    └── quickstart.md
```

## 6. Trois familles de plans d'enquête, domaines, et l'API publique

**Principe (utilisateur, 2026-08-30)** : la méthode *ultimate cluster* seule ne suffit pas à
prétendre gérer « tout plan complexe ». `afmpi` doit offrir **trois familles d'inférence**,
partageant le même étage de variables linéarisées (§5) mais consommées différemment :

```python
# 1. Taylor / linéarisation — plans avec structure explicite (le cas général)
design = afmpi.SurveyDesign(
    weights="hh_weight",
    strata="stratum_id",            # simples ou imbriquées (liste de colonnes)
    psu="cluster_id",
    ssu="sub_cluster_id",           # deuxième degré, optionnel
    fpc=["fpc_stage1", "fpc_stage2"],  # correction de population finie, PAR DEGRÉ
    pps=False,                      # probabilités inégales / PPS
    lonely_psu="adjust",            # "fail" | "certainty" | "adjust" | "average" | "collapse" —
                                     # PAS un seul comportement implicite (§4, §8)
)

# 2. Réplication — designs internationaux qui fournissent déjà les poids de réplicat
#    (DHS, beaucoup d'enquêtes internationales) : évite de reconstruire un plan à partir
#    de rien quand l'organisme les livre directement.
design = afmpi.ReplicateDesign(
    weights="hh_weight",
    replicate_weights=[f"repwgt_{i}" for i in range(1, 81)],
    method="BRR",                   # "JK1" | "JKn" | "BRR" | "Fay_BRR" | "bootstrap"
    fay=0.5,                        # coefficient de Fay, si method="Fay_BRR"
)

# 3. Recensement — pas un échantillon : SE_échantillonnage = 0, voir §7
design = afmpi.CensusDesign()

spec = afmpi.Specification()
spec.set(
    dimensions={
        "education": ["d_educ_years", "d_educ_attend"],
        "health":    ["d_nutrition", "d_child_mortality"],
        "living":    ["d_electricity", "d_water", "d_sanitation", "d_housing"],
    },
    weights="equal_nested",   # ou un dict explicite {dimension: poids, ...}
)

resultat = afmpi.estimate(
    df=df,                     # pandas.DataFrame OU polars.DataFrame/LazyFrame — indicateurs
                                # 0/1 (g0) + colonnes techniques (voir §7, compatibilité d'entrée)
    spec=spec,
    design=design,             # SurveyDesign, ReplicateDesign ou CensusDesign — interchangeables
    k=[0.20, 1/3, 0.50],       # plusieurs seuils -> tableau de robustesse automatique (fractions
                                # 0-1, pas des pourcentages — voir §12, écart assumé vs mpitb/mpitbR)
    over=["region", "milieu"], # désagrégations, autant que voulu — un seul appel, comme
                                # mpitb.est(..., over=c("area","region")) (§12) ; PRÉSERVE le
                                # design complet pour chaque sous-groupe (voir domaines, ci-dessous)
    ci_method="logit",         # "normal" | "t" | "logit" (défaut) — bornes adaptées §4
    tvar=None, cot_year=None,  # comparaison dans le temps intégrée à estimate() plutôt qu'une
                                # fonction séparée — reprend le patron mpitb.est(tvar=, cotyear=)
                                # (§12), simplifie l'API par rapport à un compare_over_time() à part
    missing="listwise",        # ou "reweighting" — politique explicite, pas implicite (§4)
    backend="polars",          # défaut ; "pandas" en repli (plus lent, documenté comme tel)
    lazy=False,                # True -> renvoie un plan de calcul non exécuté, .collect() pour lancer
)

resultat.coef()                # H, A, M0 ponctuels, par k et par sous-groupe
resultat.confint()             # IC
resultat.vcov()                # matrice variance-covariance complète (H, A, M0, contributions...)
resultat.test(a="region=='Abidjan'", b="region=='Bounkani'")  # Wald, différence entre groupes
resultat.contributions()       # hd, hdk, actb, pctb par indicateur
resultat.summary()             # tableau formaté, façon mpitb
resultat.to_frame()            # DataFrame plat, colonnes minimales et nommées sobrement
                                # (est, se, lci, uci, cv, ... — benchmark : svy.to_polars(), §12),
                                # même type que l'entrée pour l'export Excel/CSV

# lecture directe depuis un fichier recensement en parquet, en streaming — §7
lazy_result = afmpi.from_parquet("recensement_2026.parquet", streaming=True) \
                    .estimate(spec=spec, design=design, over=["region"], lazy=True)
resultat = lazy_result.collect()
```

### Une vraie notion de domaine — pas un filtre avant estimation

**Erreur statistique classique à éviter explicitement (utilisateur, 2026-08-30)** : pour l'IPM
d'une seule région, il est **faux** de faire

```python
df_abidjan = df.filter(pl.col("region") == "Abidjan")
afmpi.estimate(df_abidjan, spec, design, ...)   # FAUX : modifie le design
```

Filtrer les lignes avant d'estimer **change le plan de sondage** (nombre de PSU/strates observés
dans la variance change), donc fausse potentiellement l'erreur-type — même si l'estimateur
ponctuel a l'air correct. C'est ce genre de détail qui sépare un package statistiquement sérieux
d'un package qui donne seulement les bons estimateurs ponctuels.

`afmpi` doit implémenter l'estimation par domaine correctement : soit via `over=` (qui préserve
le design complet pour chaque sous-groupe, cas le plus courant), soit via une méthode dédiée :

```python
resultat.domain("region == 'Abidjan'")   # zéro-pondère les lignes hors domaine plutôt que de
                                          # les retirer — le design (PSU, strates) reste intact,
                                          # la variance reste correcte
```

Mécanique interne : le module `domain.py` (§5) applique une indicatrice de domaine en amont de
l'étage de linéarisation (poids nul hors domaine, mais la ligne existe toujours pour le calcul
des strates/PSU), exactement le mécanisme de `subset()` dans `survey` (R) — jamais un `.filter()`
brut avant `estimate()`.

Point de design encore ouvert :
- API orientée objets (`Specification`, `SurveyDesign`/`ReplicateDesign`/`CensusDesign`,
  `EstimationResult`) vs fonctionnelle pure (fonctions + dataclasses immuables) — privilégier ce
  qui teste le plus facilement.

**Revu et affiné en profondeur (Claude, 2026-08-30, voir §12)** : `estimate()` fusionne
désormais ce qui aurait été un `compare_over_time()` séparé (paramètres `tvar`/`cot_year`,
absents si non utilisés) — patron repris de `mpitb.est()` en R, qui fait la même chose en un
seul appel plutôt que deux résultats à comparer après coup.

**Tranché en revue (`agy`, 2026-08-30) : pas de dépendance à `samplics`.** Réimplémentation
native en Polars de la variance de plan de sondage (linéarisation par grappe, méthode *ultimate
cluster*) — `samplics` impose une structure pandas, alourdit le graphe de dépendances, et bride
le multi-threading de Polars. La linéarisation par grappe s'écrit en moins de 150 lignes
d'expressions Polars (`pl.Expr`) à haute performance ; `PythonIPM/pipeline/05_indices_ipm.py`
(fonction `ratio_et_ic`) en donne déjà la version pandas de référence à porter — **mais cette
implémentation ne couvre qu'une fraction du cahier des charges du §4** (ultimate cluster seul,
pas de PPS/FPC par degré/PSU isolé à choix multiple/réplication) : elle reste le point de départ
du module `variance.py`, pas sa version finale.

## 7. Performance et passage à l'échelle (recensement)

**Exigence de l'utilisateur (2026-08-30), à traiter comme un objectif de premier plan, pas comme
une optimisation tardive** : `afmpi` doit être **meilleur que `mpitb`/`mpitbR` et pas seulement
à parité**, en particulier sur de très gros volumes — un recensement (RGPH) compte plusieurs
millions d'individus, très au-delà des 12 965 ménages / 64 491 individus de l'EHCVM 2021 que
`PythonIPM` traite en quelques secondes. `IPM_CI` a d'ailleurs déjà un pipeline RGPH séparé
(`DofileRP21/`, Stata) — un indice que le passage à l'échelle recensement est un vrai besoin du
projet, pas hypothétique.

### Constat sur l'implémentation actuelle (`PythonIPM`)

Tout pandas pur, mono-thread, avec des copies de DataFrame à chaque étape (`Base_Individus.dta`
pèse déjà 228 Mo pour seulement 64 491 lignes après fusion large — voir
`C:\...\IPM_CI\PythonIPM\pipeline\00_construction_bases_source.py`) : viable à l'échelle EHCVM,
ne tiendrait pas la charge sur un recensement de plusieurs millions d'individus sans repenser le
moteur de calcul.

### Choix technique proposé

- **Backend principal : [Polars](https://pola.rs)**, pas pandas. Colonne-orienté, multi-thread
  nativement (pas de GIL), évaluation paresseuse (`LazyFrame`, optimiseur de requêtes), bien plus
  économe en mémoire que pandas sur les opérations qui dominent ce calcul : `group_by` massifs
  (désagrégation par sous-préfecture — 442 modalités — ou par grappe pour la variance, sur des
  millions de lignes), jointures, et agrégations pondérées.
- **Parquet comme format d'échange interne**, à la place du `.dta`/`.csv` intermédiaire de
  `PythonIPM` : colonnaire, compressé, lecture partielle par colonne (pas besoin de charger les
  267 colonnes d'une base fusionnée si le calcul n'en utilise que 20), lecture en streaming
  (`pl.scan_parquet`) pour ne jamais matérialiser l'intégralité d'un fichier recensement en
  mémoire d'un coup. Le `.dta` reste un format d'**export** possible (interop Stata), pas le
  format de travail interne.
- **Compatibilité d'entrée — tranché en revue (`agy`, 2026-08-30, voir §10)** : l'utilisateur
  doit pouvoir passer un `pandas.DataFrame` ou un `polars.DataFrame`/`LazyFrame` — comme
  `mpitb`/`mpindex` acceptent un `data.frame` R standard, sans que l'utilisateur ait à connaître
  Polars pour s'en servir. **Polars natif en interne, pas de `narwhals`** : une entrée pandas est
  ingérée via Apache Arrow (`pl.from_pandas`, zero-copy ou quasi, surcoût négligeable) plutôt que
  via une couche d'abstraction supplémentaire (`narwhals`) qui restreindrait l'accès aux
  fonctionnalités Polars avancées (expressions complexes, streaming paresseux) dont §7 a
  justement besoin. Documenter que passer directement du polars/parquet en entrée évite même ce
  coût d'ingestion et profite pleinement du gain de performance.
- **Éviter les copies matérialisées inutiles** : le pattern actuel de `PythonIPM`
  (`matrice_censuree()` dans `05_indices_ipm.py`) crée des colonnes `_censuree` ET `_brute` en
  plus de `g0` — correct et lisible à l'échelle EHCVM, mais chaque copie compte à l'échelle
  recensement. Privilégier des expressions Polars calculées à la volée (`pl.when(...).then(...)`,
  agrégations directes sans étape intermédiaire matérialisée) plutôt que des colonnes dupliquées
  systématiques, sauf quand la colonne est réellement réutilisée plusieurs fois.

### Le pipeline recensement : ne matérialiser que ce qui est nécessaire

**Architecture cible pour un fichier recensement de 100 Go** (utilisateur, 2026-08-30) :

```
100 GB Parquet
      │
      ▼  projection pushdown (17 indicateurs + poids + taille ménage + PSU + strate
      │  + variables `over` — pas les ~400 variables d'un recensement complet)
      ▼  predicate pushdown (filtres appliqués avant lecture, pas après)
      ▼  calcul g_ij / c_i en streaming (Deprivation Engine + Estimand Compiler, §5,
      │  jamais toute la table en mémoire à la fois)
      ▼  agrégations par PSU × strate × groupe (§5, Linearized Variables agrégées)
      ▼
 petite table agrégée (dizaines de milliers de lignes, pas des millions)
      │
      ▼
 variance et résultats finaux (Survey Engine, §5)
```

**L'idée clé, à ne pas manquer** : pour la variance par linéarisation, une fois les variables
linéarisées calculées ligne par ligne, la partie statistiquement lourde (le Survey Engine, §5)
**n'a pas besoin de rester au niveau des dizaines de millions de lignes** — les sommes par PSU
(pour l'estimateur *ultimate cluster*, comme pour Taylor en général) peuvent être agrégées une
fois, tôt dans le pipeline. Concrètement : 30 000 000 personnes → ~10 000 PSU pour les calculs
finaux de variance. C'est le levier de performance le plus important de toute l'architecture —
`pl.scan_parquet(...).select(colonnes_utiles).group_by(["psu", "strate", *over]).agg(...)`
avant même d'atteindre l'étage de variance, plutôt que de faire tourner le calcul de variance
sur la table complète.

### Recensement complet ≠ grand échantillon — `CensusDesign`

Distinction statistique à ne pas mélanger : si les N lignes constituent la **population
exhaustive** (recensement réel, pas un très gros échantillon), il n'y a **pas d'erreur
d'échantillonnage** à estimer.

```python
design = afmpi.CensusDesign()
```

Dans ce cas, `SE_échantillonnage = 0` — d'autres incertitudes peuvent exister (non-réponse,
erreur de mesure, imputation) mais ce n'est plus la variance de sondage classique du Survey
Engine, et `afmpi` ne doit pas prétendre en produire une. `CensusDesign` doit donc **éviter
totalement** les calculs par PSU/strate (ils n'ont pas de sens sans échantillonnage), ce qui le
rend encore plus rapide que `SurveyDesign` sur les mêmes données — un mode dédié, pas
`SurveyDesign` avec un design dégénéré à un seul PSU géant.

### Suite de benchmarks — obligatoire, pas optionnelle

1. **Jeu de données synthétique à l'échelle recensement** : généré aléatoirement (pas de vraies
   données RGPH), dimensionné pour ressembler à un recensement réel — proposition de départ :
   10 millions d'individus, ~30 indicateurs de privation, 500 grappes/districts de dénombrement,
   108 départements, 442 sous-préfectures (mêmes ordres de grandeur que le RGPH ivoirien réel).
   `agy`/`Sol` peuvent ajuster ces chiffres, mais doivent documenter le jeu choisi.
2. **Ce qui est mesuré** : temps total et pic mémoire pour (a) charger les données, (b) calculer
   H/A/M0 national, (c) toutes les désagrégations (33 régions, 108 départements, 442
   sous-préfectures), (d) les contributions par indicateur, (e) la robustesse à 8 seuils k — soit
   le même travail que fait `05_indices_ipm.py` sur l'EHCVM, mais à l'échelle recensement.
3. **Cible chiffrée** (proposition, à recalibrer par `agy`) : l'ensemble (b)-(e) en moins de
   quelques minutes sur une machine de bureau standard (pas un cluster), pic mémoire de l'ordre
   de quelques Go — pas des dizaines.
4. **Comparaison mesurée, pas affirmée** : le même calcul rejoué avec un backend pandas naïf (une
   traduction directe de la logique `PythonIPM`, sans optimisation), sur le même jeu de données,
   pour produire un chiffre de gain réel (« N fois plus rapide », « M fois moins de mémoire »)
   plutôt qu'une intuition. Ce chiffre va dans le `README.md` du package.

### Options d'optimisation exposées à l'utilisateur du package

Pas seulement « c'est rapide en interne » — donner des leviers explicites dans l'API :
- `backend="polars"` (défaut) / `"pandas"` (repli, compatibilité, plus lent — documenté comme tel) ;
- lecture depuis parquet en streaming (`afmpi.from_parquet(path, streaming=True)`) plutôt que
  DataFrame déjà chargé en mémoire ;
- mode paresseux : construire la spécification et le plan de calcul sans l'exécuter
  (`estimate(..., lazy=True)` renvoie un plan, `.collect()` l'exécute) — utile pour enchaîner
  plusieurs analyses (k différents, sous-groupes différents) sans relire/reconvertir les données
  à chaque appel.

## 8. Stratégie de validation — suite de conformité statistique

**Principe élevé (utilisateur, 2026-08-30)** : « nos résultats EHCVM sont identiques à
`PythonIPM` » n'est **plus suffisant** pour l'ambition du §2. Deux logiciels peuvent produire
exactement le même M0 et des erreurs-types différentes — la validation doit donc couvrir
**H, A, M0** *et* **VCOV(H, A, M0, contributions, ...)**, pas seulement les estimateurs
ponctuels. C'est le changement de posture le plus important de cette section.

### A. Suite de conformité multi-design, contre plusieurs références

Pour chaque **design de test** ci-dessous, générer un jeu de données synthétique qui l'exhibe,
calculer les mêmes quantités dans `afmpi` et dans chacune des références disponibles, et publier
les écarts :

```
ΔH  = H_afmpi  − H_référence
ΔSE = SE_afmpi − SE_référence
```

(et l'équivalent pour A, M0, contributions).

**Références croisées** : Stata `mpitb`, Stata `svy:` (commandes natives de plan de sondage
Stata — pas le package Python `svy` de §12, à ne pas confondre), R `mpitbR`, R `survey`. `afmpi`
doit converger avec ces quatre à une tolérance documentée (pas nécessairement 1e-6 partout — la
tolérance dépend du design testé et doit être justifiée, pas arbitraire).

**Designs à tester** (table `tests/test_conformity/`, §5) :

| Catégorie | Cas |
|---|---|
| Structure de base | SRS, stratifié SRS, un degré en grappes, stratifié en grappes, deux degrés |
| Pondération/échantillonnage | probabilités inégales (PPS), FPC |
| Cas limites de design | PSU isolé (un seul par strate), très petits domaines |
| Domaines | sous-population par `over=`/`domain()`, y compris domaines qui traversent les strates |
| Cas limites AF | zéro pauvre, tout le monde pauvre, k = 0, k = 1 |
| Données | poids extrêmes, valeurs manquantes (selon chaque politique du §4) |
| Réplication | poids de réplicat fournis en entrée (JK1/JKn/BRR/Fay BRR/bootstrap) |

### B. Tests mathématiques indépendants des logiciels — en CI à chaque commit

Au-delà de la comparaison à des références externes (qui peuvent elles-mêmes différer), des
**invariants mathématiques** vrais par construction, à vérifier automatiquement, sans dépendre
d'aucune référence externe :

```
M0 = H × A
Σⱼ actbⱼ = M0
Σⱼ pctbⱼ = 1
```

et pour des sous-groupes exhaustifs (décomposabilité) :

```
M0 = Σ_g (N_g / N) · M0,g
```

à une précision numérique donnée (documentée, pas laissée implicite). **Ces tests doivent
tourner en CI à chaque commit** (`test_invariants.py`, §5) — pas seulement à la validation finale
d'une phase : ce sont les tests les moins coûteux à faire tourner et les plus rapides à alerter
si une régression casse la cohérence interne du calcul.

### C. Ce qui existait déjà, toujours valable

1. **Jeux de données de référence OPHI** : `mpitb` est distribué avec des exemples (souvent basés
   sur des extraits DHS publics). Les récupérer (documentation `mpitb`/`mpitbR` sur CRAN/SSC),
   les rejouer dans `afmpi`, comparer H/A/M0/contributions aux valeurs publiées par `mpitb` à
   6 décimales — désormais complété par la comparaison de VCOV du point A ci-dessus.
2. **PythonIPM comme cas réel** (pas suffisant seul, voir principe ci-dessus, mais toujours un
   cas de test précieux) : une fois `PythonIPM` stabilisé (SU3/NEET/zone inclus), ses résultats
   EHCVM 2021 (`PythonIPM/sorties/csv/indices_ipm_ci.csv`) servent de référence indépendante —
   deux implémentations distinctes doivent converger à 1e-6 près sur les mêmes données d'entrée.
3. **Auto-contrôles portés** : les jeux de données synthétiques des `--check` de
   `PythonIPM/pipeline/{01,02,03,04,05}_*.py` (ménages aux résultats calculables à la main) sont
   déjà écrits et documentés — les reprendre comme premiers tests unitaires d'`afmpi` fait gagner
   du temps et garantit une cohérence de définitions.
4. **Benchmarks de performance à l'échelle recensement** (§7) : preuve chiffrée, pas seulement
   l'exactitude numérique — un package « plus robuste » qui est aussi plus lent que `mpitb` sur
   de gros volumes n'aurait pas atteint l'objectif de l'utilisateur (§2).

**Angles morts ajoutés en revue (`agy`, 2026-08-30, voir §10)** :
- **Strates à PSU unique** (*lonely PSUs*) : un domaine de désagrégation qui ne contient qu'une
  seule grappe rend la variance non estimable. `PythonIPM/pipeline/05_indices_ipm.py::ratio_et_ic`
  gère déjà ce cas (retourne un IC vide plutôt qu'une valeur inventée) — `afmpi` doit reprendre
  ce comportement, avec un test dédié, et documenter les stratégies alternatives usuelles
  (fusion avec un domaine voisin, ou certainty PSU) sans nécessairement les implémenter en
  phase 1.
- **Validation stricte du typage des indicateurs** : les colonnes de `g0` doivent être 0/1 ou
  booléennes — refuser (erreur explicite, pas une coercition silencieuse) toute colonne
  numérique hors de cet ensemble à l'entrée de `estimate()`.
- **Tests aux bornes** : k = 0 (tout le monde pauvre, H = 1) et k = 1 (personne pauvre sauf les
  ménages privés sur 100 % des indicateurs pondérés, H → 0 ou très faible) — cas limites à
  vérifier explicitement, pas seulement le k = 1/3 usuel.

## 9. Phasage proposé

**Révisé (2026-08-30) suite à l'élévation du cahier des charges (§2, §4)** — le phasage initial
(6 phases) sous-dimensionnait largement ce qu'implique « moteur de statistique d'enquête », pas
seulement « calculateur Alkire-Foster ». Nouveau découpage, aligné sur l'architecture en pipeline
du §5 (chaque phase ajoute un étage ou enrichit un étage existant, jamais les deux à la fois) :

0. ✅ **Socle** (fait, 2026-08-30, tag `v0.1.0`) : `Specification`, `SurveyDesign` minimal (poids
   simples uniquement), `estimate()` en Polars in-memory pour un seul k sans plan de sondage,
   `EstimationResult` (`coef()`, `to_frame()`). 16/16 tests. Publié sur `cae-ins/afmpi`.
1. **Linéarisation** (§5, l'étage le plus important architecturalement) : `linearization.py` —
   fonctions d'influence pour A et pctbⱼ, testées indépendamment de tout plan de sondage
   (`test_linearization.py`). Sans cet étage, tout ce qui suit reproduirait le défaut du plan
   initial (une fonction de variance par estimand, non composable).
2. **`SurveyDesign` de base** : poids + strates simples + PSU (un degré), méthodes d'IC normal/t/
   logit consommant les variables linéarisées de la phase 1. Tests contre un exemple `mpitb`
   officiel et contre `survey` (R) sur un design SRS/stratifié simple.
3. **Domaines et désagrégation** : `domain.py` (estimation par sous-population sans casser le
   design — §6), `over=[...]`, décomposabilité vérifiée par assertion (`Σφˡ·M0ˡ = M0`), `klist`
   (robustesse à k). Tests : domaines qui traversent les strates, très petits domaines.
4. **`SurveyDesign` complet** : strates imbriquées, SSU (deuxième degré), FPC par degré, PPS,
   PSU isolé à options multiples (`fail`/`certainty`/`adjust`/`average`/`collapse`, §4). Chaque
   option de PSU isolé testée séparément, pas seulement le comportement par défaut.
5. **`ReplicateDesign`** : JK1/JKn/BRR/Fay BRR/bootstrap d'enquête — pour les fichiers
   internationaux qui fournissent déjà des poids de réplicat. Rigueur de validation à égaler
   avec `svy` (§12) : comparer contre `survey` (R) à haute précision, documenter tout écart
   chiffré dans un `CHANGELOG.md`.
6. **Évolution dans le temps** : paramètres `tvar=`/`cot_year=` de `estimate()` (§6, §12),
   échantillons indépendants et panels/échantillons chevauchants (§4), deltas
   absolus/relatifs/annualisés.
7. **Tests d'hypothèses et VCOV complète** : `resultat.vcov()` (matrice complète, pas seulement
   des SE marginales), `resultat.test()` (Wald, différences entre groupes, différences entre
   périodes).
8. **Politiques de valeurs manquantes configurables** : `missing.py` — `listwise`, `reweighting`,
   règles personnalisées (§4), au lieu de la convention unique héritée de `PythonIPM`.
9. **Performance et passage à l'échelle recensement** (§7) : E/S parquet en streaming
   (`pl.scan_parquet`, projection/predicate pushdown), agrégation précoce par PSU × strate ×
   groupe, `CensusDesign` (SE d'échantillonnage nulle), jeu de données synthétique à l'échelle
   recensement, suite de benchmarks avec cibles chiffrées, comparaison mesurée à un backend
   pandas naïf. Volontairement après la rigueur statistique (phases 1-8) : optimiser un calcul
   encore faux n'a pas de sens.
10. **Suite de conformité statistique complète** (§8) : tous les designs de test du tableau §8.A,
    comparaison à quatre références (`mpitb`, `svy:` Stata, `mpitbR`, `survey` R) sur H/A/M0 *et*
    VCOV, invariants mathématiques en CI à chaque commit (déjà introduits dès la phase 1 pour les
    invariants de base, complétés ici pour la décomposabilité multi-niveaux).
11. **Packaging et documentation à jour** : README réécrit pour refléter l'API finale (familles
    de design, domaines, note sur les seuils k en fractions vs pourcentages §12.B.4), docs,
    `CHANGELOG.md`, CI complète (tests + lint + benchmarks de non-régression).
12. **Republication GitHub** : nouveau tag (`v0.2.0` ou au jugé selon l'ampleur des phases 1-11),
    `cae-ins/afmpi` déjà créé (phase 0) — pas de nouvelle création de dépôt, juste une mise à
    jour. Publication PyPI : jalon distinct, sur nouvelle confirmation explicite de
    l'utilisateur à chaque fois (pas un blanc-seing permanent).

*(Note : seule la phase 0 est faite au 2026-08-30. Les phases 1 à 12 restent à faire — c'est un
programme de travail substantiel, pas une correction ponctuelle. `agy` doit évaluer si ce
découpage en 13 phases (0-12) est le bon grain pour des passes `Sol` successives, ou s'il faut
regrouper certaines phases.)*

## 10. Décisions issues de la revue `agy` (2026-08-30, modèle `gemini-3.6-flash-high`)

Verdict global d'`agy` : *« le plan est solide et mature »*, quatre arbitrages nécessaires pour
être exécutable sans ambiguïté — tous tranchés ci-dessous et déjà répercutés dans les sections
correspondantes (§4, §6, §7, §9). Rapport complet dans
`C:\Users\f.migone\Desktop\projects\actif\afmpi\agy-review.md`.

- **`samplics` écarté** (§6) — réimplémentation Polars native de la variance par grappe.
- **`narwhals` écarté** (§7) — Polars natif directement, entrée pandas ingérée via Apache Arrow
  (`pl.from_pandas`, surcoût mémoire négligeable) plutôt qu'une couche d'abstraction
  supplémentaire à apprendre et maintenir.
- **Cibles de performance confirmées réalistes**, voire prudentes : 10 M lignes / 442
  sous-préfectures en moins de 30 s et moins de 2 Go de RAM avec `LazyFrame` + streaming
  parquet — le jeu synthétique calé sur le découpage administratif ivoirien est jugé
  représentatif.
- **Frontière de la phase 1 précisée** (§9) : Polars fait partie du moteur de calcul dès la
  phase 1 (`estimate()` en Polars in-memory, un seul k, pas de plan de sondage complet) pour
  éviter une refonte plus tard ; en revanche l'E/S parquet avancée, le mode streaming et les
  benchmarks à 10 M lignes restent isolés en phase 4, pour ne pas sur-ingénierier avant que la
  logique de calcul soit stabilisée et testée.
- **Nom `afmpi` confirmé** — jugé court, clair, mémorisable.
- **Angles morts ajoutés** (répercutés en §4 et §8) : traitement des strates à PSU unique
  (*lonely PSUs* — un seul cluster dans un domaine, variance non estimable, cf. le cas déjà géré
  dans `PythonIPM/pipeline/05_indices_ipm.py::ratio_et_ic`, qui renvoie un IC vide plutôt qu'une
  valeur inventée), validation stricte du typage des indicateurs (booléen ou 0/1 uniquement, pas
  de coercition silencieuse), tests aux bornes k=0 et k=1, tolérance numérique 1e-6 pour la
  validation croisée EHCVM (déjà utilisée en §8, confirmée par la revue).

## 11. Points ouverts (à trancher avant ou pendant l'implémentation)

- Faut-il qu'`afmpi` sache lire directement un `vecteur_z`/`vecteur_w` façon `PythonIPM`, pour
  faciliter une migration future du pipeline CI dessus ? (Hors périmètre §2, mais un adaptateur
  léger coûterait peu.)
- Où trouver des jeux de données `mpitb` de référence publiquement rejouables sans dépendre d'un
  accès Stata (licence) ? À vérifier — CRAN `mpitbR`/`mpindex` embarquent parfois des exemples en
  `.rda`, plus faciles à récupérer qu'un `.dta` Stata protégé.

## 12. Analyse comparative approfondie des meilleurs packages (Claude, 2026-08-30)

Suite à la demande explicite de l'utilisateur (« il faut vraiment que notre package soit meilleur
que ceux existant déjà ») d'aller plus loin que la revue initiale d'`agy` (§10), analyse directe
des meilleurs packages du domaine adjacent — pas seulement `mpitb`/`mpitbR` (Alkire-Foster), mais
aussi les meilleurs outils Python et R pour le plan de sondage complexe en général, puisque
c'est la moitié du problème qu'`afmpi` doit résoudre.

### A. `svy` remplace `samplics` — pas juste « abandonné », un successeur réel existe

`samplics` (évalué en §6-§7 comme dépendance candidate, écartée par `agy`) est en réalité
**déprécié** : son propre site l'annonce, remplacé par **[`svy`](https://svylab.com/docs/svy)**
(même équipe, `samplics-org/svy` sur GitHub, PyPI `svy` version 0.26.0 au 2026-08-30, ~45
releases, changelog réel, docs versionnées). Constat important, à ne pas confondre avec la
décision déjà prise sur `samplics` :

- **`svy` est Polars-natif** (`polars[pyarrow]>=1.33.1` dans ses dépendances), avec un cœur
  **accéléré en Rust** (`svy-rs`) — exactement la direction technique qu'`afmpi` a choisie pour
  lui-même en §7, en plus mature et déjà en production.
- **Validé contre le `survey` package de R** (Thomas Lumley — la référence académique du domaine
  depuis plus de 20 ans) — un standard de rigueur qu'`afmpi` doit égaler, pas seulement viser.
- **Variance : Taylor (linéarisation, comme `PythonIPM`/`afmpi` prévu) ET réplication**
  (Bootstrap, BRR — Balanced Repeated Replication —, Jackknife, SDR — Successive Difference
  Replication). `afmpi` (§4, §7) ne prévoit pour l'instant QUE deux variantes de linéarisation
  (ultimate cluster tronqué, logit `svyciprop`) — aucune méthode de réplication. C'est un vrai
  écart de rigueur face au meilleur outil du domaine, pas un détail.
- **Ne fait PAS de pauvreté multidimensionnelle / Alkire-Foster** — confirmé absent de sa
  documentation. Aucun chevauchement sur le cœur de valeur d'`afmpi`, seulement sur la brique
  « plan de sondage + variance » qui le sous-tend.

**Métadonnées vérifiées le 2026-08-30** (GitHub API, PyPI, changelog du dépôt), pour trancher sur
des faits plutôt que sur une impression :

| Signal | Constat |
|---|---|
| CI | 5 workflows GitHub Actions réels (tests + build de roues, y compris pour `svy-rs`) |
| Rigueur de validation | changelog documente des comparaisons à `survey` (R) jusqu'à 10⁻¹² – 10⁻¹⁴ (12-14 chiffres significatifs), avec des cas de correction de bugs chiffrés (ex. écart-type sous-estimé d'un facteur `1/√(1−15/757)` sur un test FPC) |
| Licence | MIT |
| Adoption PyPI | ~3 300 téléchargements/mois, ~1 400/semaine (réel, mais modeste) |
| Communauté GitHub | créé 2026-01 (8 mois), **20 étoiles, 0 fork, 2 contributeurs**, 1 seul Release GitHub formel malgré ~45 versions PyPI |
| Stabilité de l'API | la section « Unreleased » du changelog contient **plusieurs breaking changes en cours** (`by=`→`cells=`, `factors=`→`shares=`, comportement de `controls` changé) — l'auteur documente lui-même que le vocabulaire de l'API bouge encore |

**Décision recommandée, inchangée sur le fond mais désormais fondée sur des faits vérifiés** (à
confirmer par `agy`/l'utilisateur) : **ne pas dépendre de `svy` en dur** dans `afmpi` — pas par
méfiance envers l'auteur (l'utilisateur le connaît personnellement, ce qui atténue le risque
« bus factor » et ouvre la porte à un contact direct sur la feuille de route), mais parce que
l'instabilité de l'API est un fait documenté par le projet lui-même, indépendant de qui l'a
écrit : un package qui vise `pip install afmpi` simple et stable ne peut pas dépendre en dur
d'une surface d'API qui change de vocabulaire d'une version à l'autre. **Déclencheur explicite
pour revisiter cette décision** : `svy` atteint 1.0 (ou publie un engagement de stabilité d'API/
politique de dépréciation), ou une conversation directe avec l'auteur clarifie sa feuille de
route de stabilisation.

En attendant, **`afmpi` doit égaler sa rigueur sur la variance** dans un jalon dédié (au-delà de
la phase 2 déjà prévue, §9 point 6) : ajouter les méthodes de réplication (bootstrap et jackknife
au minimum ; BRR et SDR si le temps le permet), implémentées nativement en Polars, **et reprendre
la même discipline de validation** — comparer contre `survey` (R) à haute précision (viser un
ordre de grandeur similaire, pas juste 1e-6 comme le reste du plan, §8) et documenter tout écart
chiffré dans un `CHANGELOG.md` à la façon de `svy`, plutôt qu'un simple « corrigé » sans détail.
Interopérabilité à bas coût à envisager plus tard : accepter en entrée un objet
`svy.Sample`/`svy.Design` déjà construit, pour les utilisateurs déjà dans cet écosystème, sans
que `afmpi` en dépende pour fonctionner seul.

### B. Ce que l'API réelle de `mpitbR` précise, au-delà du résumé d'`agy`

Signatures exactes trouvées dans la documentation et le README du package
([girelaignacio/mpitbR](https://github.com/girelaignacio/mpitbR), CRAN) :

```r
indicators <- list(d1 = c("d_nutr", "d_cm"),
                   d2 = c("d_satt", "d_educ"),
                   d3 = c("d_elct", "d_sani", "d_wtr", "d_hsg", "d_ckfl", "d_asst"))
set <- mpitb.set(svydata, indicators = indicators, name = "myname", desc = "pref. desc")
est <- mpitb.est(set, c(20, 33), over = c("area", "region"), tvar = "t", cotyear = "year")
```

Trois précisions qui affinent le design d'`afmpi` (déjà répercutées en §5-§6) :

1. **`mpitb.set()` prend directement l'objet de plan de sondage** (`svydata`, construit par
   `survey::svydesign()` en amont) — confirme que le design en objet séparé (`SurveyDesign`
   d'`afmpi`) est la bonne approche, pas une option parmi d'autres.
2. **`over=` prend plusieurs variables de regroupement en un seul appel** (`c("area", "region")`)
   — déjà ce que fait le sketch d'API d'`afmpi` (`over=["region", "milieu"]`), confirmé bon.
3. **La comparaison dans le temps est un paramètre de `mpitb.est()`** (`tvar=`, `cotyear=`), pas
   une fonction séparée qui prendrait deux résultats déjà calculés — `afmpi` adoptait
   `compare_over_time(result_t1, result_t2)` (ancien §6) : **corrigé** pour suivre le même
   patron que `mpitb`/`mpitbR` (un seul appel à `estimate()`, `tvar`/`cot_year` optionnels).
4. **Convention des seuils k en pourcentages entiers** (`c(20, 33)`, pas `c(0.20, 0.33)`) —
   `afmpi` garde des fractions (`k=[0.20, 1/3, 0.50]`, convention Python plus idiomatique pour une
   valeur de probabilité) mais **doit documenter explicitement cet écart** dans le README, pour
   les utilisateurs habitués à `mpitb`/`mpitbR` qui s'attendraient à des pourcentages.
5. **Résultats en objets S3 typés** (`lframe`, `cotframe`) avec des méthodes génériques
   (`summary.lframe`, `coef.lframe`, `confint.lframe`) — équivalent Python déjà prévu :
   `EstimationResult` avec `coef()`/`confint()`/`summary()`. Confirmé bon, rien à changer.

### C. Ce que l'API de `svy` inspire pour la forme des résultats

```python
sample = svy.Sample(data=sample_df, design=design)
estimate = sample.estimation.mean(...)
estimate.to_polars()
# shape: (1, 6) — colonnes : est, se, lci, uci, cv, df
```

- **Méthodes namespacées par capacité** (`sample.estimation.mean()`, `sample.glm.fit()`) plutôt
  que des dizaines de méthodes à plat sur un seul objet — à évaluer pour `EstimationResult` si sa
  surface grandit (ex. `resultat.contributions.censored` / `.uncensored` plutôt que deux méthodes
  distinctes) ; pas urgent en phase 1-3, à trancher quand la phase 4+ ajoute de la matière.
- **Colonnes de résultat minimales et sobrement nommées** (`est, se, lci, uci, cv, df`) — bon
  benchmark pour `to_frame()` : `afmpi` a tendance (héritage direct de `PythonIPM`) à des noms
  français longs (`taux_privation_non_censure`) ; garder les noms français dans les sorties
  destinées à un public francophone (cohérent avec `PythonIPM`) mais envisager des alias courts
  en anglais dans l'API interne/programmatique, pour rester ergonomique en usage `pandas`/`polars`
  courant. Point à trancher par `agy` ou à l'usage, pas une conclusion ferme ici.
- **Typage explicite des variables catégorielles** (`svy.Cat("urbrur")` dans `sample.glm.fit()`)
  — renforce la décision déjà prise (§8, angle mort ajouté par `agy`) de valider strictement le
  typage des indicateurs (0/1 ou booléen, refus explicite sinon) : `svy` applique la même
  discipline plus largement, à tout type de variable passé à l'API.
- **Extras de packaging** (`pip install svy[report]`, `svy[all]`) pour des fonctionnalités
  optionnelles lourdes (`great-tables` pour un rendu enrichi) — modèle à reprendre pour un futur
  `afmpi[report]` (sortie formatée façon `mpitb`) plutôt que d'alourdir la dépendance de base.
  Hors périmètre des phases actuelles, à noter pour le packaging final (§9, phase 7).

### D. Conclusion — la barre de qualité à viser

Un package « aussi complet que les meilleurs » du domaine ne se limite pas à l'exactitude
numérique (déjà couverte, §8) : `svy` fixe la barre sur la **rigueur de la variance** (réplication,
pas seulement linéarisation) et la **discipline de publication** (changelog réel, docs versionnées,
releases fréquentes et documentées) ; `mpitbR` fixe la barre sur la **fidélité au patron
statistique établi** (un seul point d'entrée `set` + `est`, résultats typés avec méthodes
génériques). Aucun des deux ne fait de pauvreté multidimensionnelle — c'est entièrement le terrain
d'`afmpi`, mais la qualité d'ingénierie autour doit être à ce niveau, pas en dessous.

**Actions concrètes qui en découlent, au-delà de ce qui était déjà dans le plan** :
- §6 : `estimate()` porte `tvar=`/`cot_year=` au lieu d'un `compare_over_time()` séparé — fait.
- §5 : `change_over_time.py` redevenu un module interne (pas une API utilisateur séparée) — fait.
- Nouveau jalon de phasage à ajouter (au-delà de §9, à discuter avec `agy`) : méthodes de
  variance par réplication (bootstrap, jackknife), après la phase 2 (plan de sondage complet) et
  avant ou après la phase 4 (performance) selon ce qu'`agy` juge prioritaire.
- README (déjà écrit par `Sol` pour la phase 1, à mettre à jour dans une prochaine passe) : ajouter
  la note sur la convention des seuils k en fractions vs pourcentages (point B.4 ci-dessus), pour
  éviter une confusion aux utilisateurs venant de `mpitb`/`mpitbR`.

Sources consultées : [svylab.com/docs/svy](https://svylab.com/docs/svy),
[PyPI — svy](https://pypi.org/project/svy/), [GitHub — samplics-org/svy](https://github.com/samplics-org/svy),
[GitHub — girelaignacio/mpitbR](https://github.com/girelaignacio/mpitbR),
[R Journal — mpitbR](https://journal.r-project.org/articles/RJ-2026-003/),
[CRAN — survey package](https://cran.r-project.org/web/packages/survey/survey.pdf).

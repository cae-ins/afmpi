# Plan — `afmpi` : un package Python pour l'IPM (méthode Alkire-Foster)

**Statut** (mis à jour 2026-08-31) : les **phases 0 à 7 sont implémentées** — noyau, plans
complexes (4a-4c+4.5), réplication complète (5a-5c), évolution dans le temps (6a-6b), VCOV et
tests de Wald (7). Publié sur `cae-ins/afmpi` (`main`, 207/207 tests) ; le tag le plus récent
(`v0.3.0`) est en retard sur `main` — à retaguer en phase 12. Les phases 8 à 12 restent à faire ;
leur spécification d'exécution complète est au **§14**, qui fait foi pour tout implémenteur.
Point de rigueur restant avant la phase 9, signalé par une relecture externe (`agy`, 2026-08-31) :
l'oracle `survey` (R) ne couvre encore que le noyau et 4a-4c (§16-§17), pas les phases 5-7
(réplication, panels, VCOV/Wald) — validées pour l'instant seulement en interne.
Dossier de travail : `C:\Users\f.migone\Desktop\projects\actif\afmpi\`.

**Comment lire ce document pour implémenter** : §1-§8 donnent le pourquoi et le cahier des
charges ; §9 donne le découpage en phases ; §10-§13 sont l'historique daté des revues (à ne pas
réécrire) ; **§14 est la spécification exécutable des phases restantes**. En cas de désaccord
apparent entre §14 et une section antérieure, §14 fait foi, car il a été écrit après lecture du
code réellement livré.

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
doit donc savoir traiter ces ratios correctement selon la méthode d'inférence choisie — pas
calculer H, A, M0 puis leur coller chacun une `variance_H()`, `variance_A()`, `variance_M0()`
séparée et non composable.

**Correction architecturale majeure (utilisateur, 2026-08-30, sur relecture après la revue
`Fable` — voir §13)** : la version précédente de cette section faisait passer les **trois**
familles de design (Taylor, réplication, recensement) par un seul étage partagé de « variables
linéarisées ». C'est **statistiquement faux pour la réplication**. La théorie des méthodes de
réplication (JK/BRR/Fay BRR/bootstrap) ne linéarise pas : elle **réévalue l'estimateur complet**
pour chaque jeu de poids de réplicat —

```
θ̂⁽ʳ⁾ = T(w⁽ʳ⁾),   par exemple   A⁽ʳ⁾ = Σᵢ wᵢ⁽ʳ⁾·cᵢ(k) / Σᵢ wᵢ⁽ʳ⁾·1(cᵢ≥k)
```

puis calcule la variance à partir de la dispersion de θ̂⁽¹⁾, θ̂⁽²⁾, …, θ̂⁽ᴿ⁾ — pas à partir d'une
fonction d'influence. C'est ce que font `survey` (R) et `svy` (Python) : les deux techniques
existent en parallèle, elles ne partagent pas de code de linéarisation. Le pipeline correct :

```
                    Estimand Compiler
                    (H, A, M0, contributions — ponctuels, sans design, §4)
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
       Taylor           Replication         Census
          │                 │                 │
   Linearization      Re-estimation         Point
   (fonctions          per replicate        estimate
   d'influence)      (θ̂⁽ʳ⁾ = T(w⁽ʳ⁾),          (§7 —
          │           R évaluations       SE_échantillonnage
          │           complètes de T)        = 0)
          │                 │                 │
          └──────────────┬──┴─────────────────┘
                         ▼
                  Results / VCOV
              (coef, confint, vcov, test, degf — §6)
```

- **Deprivation Engine** (en amont, non représenté ci-dessus par souci de lisibilité — voir
  l'arborescence) : applique le vecteur z aux indicateurs bruts → `g_ij`, `c_i`, `poor_i`. Ne
  connaît rien du plan de sondage.
- **Estimand Compiler** : combine `g_ij`/`c_i`/`poor_i` en H, A, M0 et contributions — au niveau
  *ponctuel*, toujours sans plan de sondage. C'est ici que vivent les formules du §4. C'est aussi
  la fonction `T(·)` que la réplication réévalue R fois avec des poids différents.
- **Taylor → Linearization** : pour chaque estimand qui est un ratio (A, pctbⱼ, ratios de
  sous-groupe), calcule la fonction d'influence — quantité *additive* par observation qui rend la
  variance correcte et composable sous linéarisation. **N'alimente que `SurveyDesign`.**
- **Replication → Re-estimation** : réévalue l'Estimand Compiler complet pour chaque colonne de
  poids de réplicat (fournie, ou générée en interne selon la méthode — JK1/JKn/BRR/Fay BRR/
  bootstrap, §6), puis calcule la variance depuis la dispersion des R estimations. **N'alimente
  que `ReplicateDesign`.** Par lots (batched) pour éviter de matérialiser N×R en mémoire (§7).
- **Census → Point estimate** : pas d'inférence d'échantillonnage à faire — l'Estimand Compiler
  suffit, `SE_échantillonnage = 0` (§7). **N'alimente que `CensusDesign`.**
- **Results/VCOV** : point de convergence commun des trois chemins, produisant la même interface
  de sortie (`coef()`, `confint()`, `vcov()`, `test()`, `degf()` — §6) quel que soit le design —
  c'est *l'interface* qui est partagée, pas le calcul de variance lui-même.

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
│   │   --- Deprivation Engine + Estimand Compiler (communs aux 3 chemins) ---
│   ├── deprivation.py            g_ij, c_i, poor_i — vecteur z appliqué, sans plan de sondage
│   ├── estimands.py              H, A, M0, Hⱼ, CHⱼ, actbⱼ, pctbⱼ ponctuels (formules §4) —
│   │                             c'est la fonction T(·) réévaluée par la réplication
│   │
│   │   --- Chemin Taylor : linéarisation, PAS la réplication (correction §5) ---
│   ├── linearization.py          fonctions d'influence pour A, pctbⱼ et tout ratio de
│   │                             sous-groupe — n'alimente que survey_design.py
│   │
│   │   --- Chemin Replication : réévaluation, PAS de linéarisation (correction §5) ---
│   ├── replicate_estimation.py   applique estimands.py à chaque colonne de poids de réplicat,
│   │                             par lots (§7) ; génère les poids JK1/JKn/BRR/Fay BRR/bootstrap
│   │                             si non fournis (§6)
│   │
│   │   --- Trois familles de design (§6) ---
│   ├── survey_design.py          SurveyDesign (Taylor) : weights, stages=[Stage(id=, strata=,
│   │                             fpc=), ...] — degrés arbitraires, pas figés à psu/ssu (§6) ;
│   │                             pps=PPSDesign(...) — pas un booléen (§6) ; lonely_psu=
│   ├── replicate_design.py       ReplicateDesign : weights, replicate_weights, method=
│   │                             (JK1/JKn/BRR/Fay_BRR/bootstrap/SDR), fay=, scale=, rscales=,
│   │                             combined_weights=, mse=True (MSE vs variance de réplicat
│   │                             centrée) — cahier des charges enrichi (§6)
│   ├── census_design.py          CensusDesign : SE=0 pour l'erreur d'échantillonnage (§7)
│   ├── domain.py                 estimation par domaine sans casser le design (§6) — zéro-
│   │                             pondération, pas un filtre naïf avant estimation
│   ├── variance.py               dispatche vers Taylor (linearization.py + agrégation
│   │                             hiérarchique par degré, §7) ou Replication
│   │                             (replicate_estimation.py) selon le type de design ; assemble
│   │                             VCOV/SE/CI/tests ; IC normal/t/logit ; tests de Wald,
│   │                             différences de groupes ; degf() — degrés de liberté explicites
│   │                             (§6), pas un détail d'implémentation caché
│   │
│   │   --- Composition et résultats ---
│   ├── contributions.py          actb, pctb, décomposition par dimension
│   ├── decomposition.py          désagrégation par sous-groupe (`over`), vérif décomposabilité,
│   │                             invariants Σφˡ·M0ˡ = M0 (§8)
│   ├── robustness.py             robustesse à k (klist)
│   ├── change_over_time.py       paramètres tvar/cot_year de estimate() (§6, §12) — échantillons
│   │                             indépendants ; panels/chevauchants avec covariance inter-vagues
│   │                             (§6, sous-phase dédiée §9) — pas juste une option parmi d'autres
│   ├── missing.py                politiques de valeurs manquantes : listwise, reweighting,
│   │                             règles configurables (§4)
│   └── results.py                EstimationResult : coef(), confint(), summary(), to_frame(),
│                                  vcov() (matrice complète), degf(), provenance de la
│                                  spécification (§4)
├── tests/
│   ├── test_estimation.py        cas construits à la main (répliquer les auto-contrôles de
│   │                              PythonIPM/pipeline/*.py --check, mêmes valeurs attendues)
│   ├── test_linearization.py     variables linéarisées Taylor vérifiées indépendamment (§5, §8)
│   ├── test_replicate_estimation.py  réévaluation par réplicat vérifiée indépendamment (§5, §8)
│   ├── test_conformity/          suite de conformité statistique multi-design (§8) — un fichier
│   │                              par famille de design (SRS, stratifié, grappe, multi-degrés,
│   │                              PPS, FPC par degré, PSU isolé, domaines, k=0/k=1, poids
│   │                              extrêmes, valeurs manquantes, réplicats, panels chevauchants)
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

**État réel de cette arborescence au 2026-08-30 (Claude, après lecture du dépôt)** — cette
distinction est nécessaire pour savoir ce qu'on *modifie* et ce qu'on *crée* :

- **Existent** : `pyproject.toml`, `README.md`, `PLAN.md`, `LICENSE`, et dans `src/afmpi/` :
  `__init__.py`, `specification.py`, `survey_design.py`, `deprivation.py`, `estimands.py`,
  `linearization.py`, `variance.py`, `domain.py`, `estimation.py`, `results.py`. Dans `tests/` :
  `test_specification.py`, `test_survey_design.py`, `test_linearization.py`, `test_domain.py`,
  `test_estimation.py`, `test_invariants.py` (104 tests au total).
- **N'existent pas encore** : `backend.py`, `io.py`, `replicate_design.py`,
  `replicate_estimation.py`, `census_design.py`, `contributions.py`, `decomposition.py`,
  `robustness.py`, `change_over_time.py`, `missing.py`, `docs/`, `CHANGELOG.md`, et les fichiers
  de tests correspondants.
- **Écarts assumés entre l'arborescence cible ci-dessus et le code livré**, à ne pas « corriger »
  en créant des modules vides : `contributions.py`, `decomposition.py` et `robustness.py` n'ont
  pas été créés parce que leur contenu est déjà couvert sans duplication — les contributions sont
  des estimands comme les autres (`estimands.build` produit `actb`/`pctb`/`actb_dim`/`pctb_dim`),
  la décomposabilité est vérifiée dans `estimation._assert_decomposable` et exposée par
  `EstimationResult.decomposition()`, et la robustesse à k est la boucle sur `cutoffs` de
  `_estimate_from_matrix`. **Ces trois modules restent délibérément non créés** : les phases
  restantes ne doivent pas les ressusciter. §14 dit, pour chaque phase, quel fichier existant
  modifier et quel fichier créer.

## 6. Trois familles de plans d'enquête, domaines, et l'API publique

**Principe (utilisateur, 2026-08-30)** : la méthode *ultimate cluster* seule ne suffit pas à
prétendre gérer « tout plan complexe ». `afmpi` doit offrir **trois familles d'inférence** — voir
§5 pour la correction architecturale majeure : Taylor linéarise, Replication réévalue
l'estimateur par jeu de poids, Census n'a pas d'inférence d'échantillonnage. Elles ne partagent
PAS de code de variance, seulement l'interface de résultat (`coef`, `confint`, `vcov`, `degf`).

```python
# 1. Taylor / linéarisation — plans avec structure explicite (le cas général)
design = afmpi.SurveyDesign(
    weights="hh_weight",
    # Degrés ARBITRAIRES (pas figé à deux, psu/ssu) — corrigé (utilisateur, 2026-08-30) : un
    # design à 2 degrés fixes (psu=/ssu=) ne peut pas dire "multi-degrés" en toute honnêteté.
    stages=[
        afmpi.Stage(id="cluster_id", strata="stratum_id", fpc="fpc_stage1"),  # PSU
        afmpi.Stage(id="sub_cluster_id", fpc="fpc_stage2"),                   # SSU
        afmpi.Stage(id="household_id", fpc="fpc_stage3"),                    # TSU, si besoin
    ],
    # forme minimale équivalente, acceptée en raccourci pour les cas à 1-2 degrés :
    # ids=["cluster_id", "sub_cluster_id"], strata="stratum_id", fpc=["fpc_stage1", "fpc_stage2"]
    pps=afmpi.PPSDesign(          # objet, pas un booléen — corrigé (utilisateur, 2026-08-30) :
        method="without_replacement",   # "with_replacement" | "without_replacement"
        inclusion_probability="pi",     # probabilités d'inclusion de premier ordre
        joint_probability=None,         # probabilités conjointes / second ordre, si disponibles
    ),                             # pps=False (comportement par défaut) = design à probabilités
                                    # égales, pas de calcul PPS
    lonely_psu="adjust",            # "fail" | "certainty" | "adjust" | "average" | "collapse" —
                                     # PAS un seul comportement implicite (§4, §8)
)

# 2. Réplication — designs internationaux qui fournissent déjà les poids de réplicat
#    (DHS, beaucoup d'enquêtes internationales) : évite de reconstruire un plan à partir
#    de rien quand l'organisme les livre directement. Cahier des charges enrichi
#    (utilisateur, 2026-08-30) pour lire correctement des poids de réplicat déjà produits.
design = afmpi.ReplicateDesign(
    weights="hh_weight",
    replicate_weights=[f"repwgt_{i}" for i in range(1, 81)],  # colonnes déjà fournies, ou
                                                                 # générées si absentes (§5)
    method="BRR",                   # "JK1" | "JKn" | "BRR" | "Fay_BRR" | "bootstrap" | "SDR"
                                     # (successive difference replication — ajouté §4)
    fay=0.5,                        # coefficient de Fay, si method="Fay_BRR"
    scale=1.0,                      # facteur d'échelle de la variance de réplicat
    rscales=None,                   # facteurs par réplicat, si hétérogènes (fichiers officiels)
    combined_weights=True,          # les poids de réplicat incluent-ils déjà le poids de base,
                                     # ou faut-il les combiner (combined vs non-combined weights)
    mse=True,                       # variance MSE (autour de l'estimation ponctuelle) vs
                                     # variance de réplicat centrée (autour de la moyenne des
                                     # réplicats) — les deux conventions existent dans la
                                     # littérature et donnent des résultats différents
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
                                # (§12) ; si les vagues se chevauchent (panel), voir la note sur
                                # la covariance inter-vagues ci-dessous — pas qu'une simple option
    missing="listwise",        # ou "reweighting" — politique explicite, pas implicite (§4)
    backend="polars",          # défaut ; "pandas" en repli (plus lent, documenté comme tel)
    lazy=False,                # True -> renvoie un plan de calcul non exécuté, .collect() pour lancer
)

resultat.coef()                # H, A, M0 ponctuels, par k et par sous-groupe
resultat.confint()             # IC
resultat.vcov()                # matrice variance-covariance complète (H, A, M0, contributions...)
resultat.degf()                # degrés de liberté explicites (utilisateur, 2026-08-30) — voir
                                # la note dédiée ci-dessous : df = #PSU - #strates n'est qu'UNE
                                # convention, elle doit être un objet de premier ordre, pas cachée
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

### Les degrés de liberté sont un objet de première classe, pas un détail caché

**Point ajouté (utilisateur, 2026-08-30)** : le plan mentionnait les IC normal/t/logit sans
jamais rendre explicite comment les degrés de liberté (df) qui les sous-tendent sont obtenus.
Convention usuelle : `df = #PSU − #strates`, mais ce n'est qu'UNE convention parmi d'autres, et
elle évolue avec le contexte — un domaine, des PSU certainty, un design en réplication (où le df
vient du nombre de réplicats, pas de PSU/strates) n'ont pas le même calcul. Sans le rendre
explicite, **deux implémentations peuvent produire le même point estimé, la même erreur-type, et
un IC ou une p-value différents**, uniquement à cause du df — un écart invisible tant qu'on ne
compare que les estimateurs ponctuels (raison de plus pour la suite de conformité du §8, qui
compare aussi la VCOV). D'où `resultat.degf()` en API publique (ci-dessus) et une règle
documentée, testée, par famille de design et par cas (domaine, certainty PSU, réplication),
plutôt qu'un nombre calculé en silence à l'intérieur de `variance.py`.

### Comparaison dans le temps : panels et échantillons chevauchants, pas juste une option

**Point ajouté (utilisateur, 2026-08-30)** : `tvar=`/`cot_year=` suffit pour des vagues
indépendantes (deux échantillons distincts), mais pas pour un **panel** ou des échantillons qui
se chevauchent partiellement (mêmes PSU, voire mêmes ménages, suivis dans le temps). Dans ce cas,
la variance d'un delta n'est PAS la simple somme des deux variances :

```
Δ = M0,t+1 − M0,t
Var(Δ) = Var(M0,t+1) + Var(M0,t) − 2·Cov(M0,t+1, M0,t)
```

`afmpi` doit donc savoir reconnaître la covariance inter-vagues — typiquement à partir
d'identifiants de panel/PSU communs entre les deux vagues, ou de poids de réplicat compatibles
d'une vague à l'autre (mêmes colonnes de réplicat, même méthode). Ignorer ce terme de covariance
(le traiter comme nul, cas des échantillons réellement indépendants) est un choix valide mais
doit être **explicite**, pas le comportement par défaut silencieux dès qu'un identifiant de panel
existe dans les données. C'est une sous-phase testée à part entière (§9), pas une simple option
supplémentaire de `change_over_time.py`.

Point de design **tranché** (Claude, 2026-08-30, à la lecture du code des phases 0-3 déjà
livré) :
- ~~API orientée objets vs fonctionnelle pure~~ → **les deux, dans la répartition déjà en place**
  et à ne plus rediscuter : les objets de configuration et de résultat sont des **dataclasses
  gelées** (`@dataclass(frozen=True, slots=True)` — `SurveyDesign`, `DesignDegrees`,
  `RatioEstimand`, `RatioTotals`, `Domain`, `DeprivationMatrix`, `EstimationResult`), le calcul
  est fait de **fonctions libres au niveau module** (`deprivation.build`, `estimands.build`,
  `linearization.cluster_sums`, `variance.taylor_variance`, …), et `Specification` est la seule
  classe mutable, parce qu'elle est construite de façon fluide (`set()`/`set_weights()` renvoient
  `self`). Toute nouvelle phase suit cette répartition : un nouveau design est une dataclass
  gelée, un nouvel estimateur est une fonction de module.

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

### Constat sur `afmpi` lui-même, après le noyau v1 (relecture de code, utilisateur, 2026-08-30)

**Distinction à garder à l'esprit pendant les phases 4a-12 : « architecture compatible big data »
et « big data effectivement opérationnel » ne sont pas la même chose.** Le noyau v1 (phases 0-3)
est écrit en Polars, mais :

- `estimate()` prend `df: pandas.DataFrame | polars.DataFrame` — **pas de `LazyFrame`**. Le
  moteur construit une `DeprivationMatrix` qui contient un `pl.DataFrame` **matérialisé**, et
  `EstimationResult` garde cette matrice complète (`_matrix: DeprivationMatrix`) pour pouvoir
  rejouer `result.domain(...)` et `result.scores()` après coup. Sur 50 000 ménages, aucun
  problème. Sur 30 millions de personnes, ce modèle ne peut pas rester tel quel : un résultat
  statistique de quelques kilooctets garderait en vie un DataFrame de plusieurs dizaines de Go.
  **La phase 9 devra séparer `InMemoryResult` (comportement actuel, conservé pour les enquêtes de
  taille normale) d'un `Lazy`/`StreamingResult`** qui ne conserve pas la base préparée — ou, au
  minimum, faire en sorte qu'un `EstimationResult` standard ne retienne pas automatiquement toute
  la base.
- `_estimate_from_matrix()` boucle sur les seuils `k` et, pour chaque `k`, refait un
  `cluster_sums()` complet par variable de désagrégation. Avec 8 seuils × région × département ×
  sous-préfecture, ça fait plusieurs agrégations intégrales de la base. Sans importance sur
  l'EHCVM ; potentiellement très coûteux sur un recensement. **La phase 9 devra compiler tous les
  `k` et toutes les sorties de désagrégation dans un seul plan Polars (ou un nombre minimal de
  scans)**, pas une boucle d'agrégations indépendantes.

Aucun des deux n'est un problème de la phase 3 — le noyau v1 vise la correction statistique, pas
la performance (§9, ordre des phases). Mais ce sont des exigences concrètes, pas des vœux
pieux, pour la phase 9 : la section « Choix technique » ci-dessous doit être relue à cette
lumière une fois cette phase abordée.

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

**L'idée clé, à ne pas manquer** : pour la variance par linéarisation (chemin Taylor, §5), une
fois les variables linéarisées calculées ligne par ligne, la partie statistiquement lourde (le
Survey Engine) **n'a pas besoin de rester au niveau des dizaines de millions de lignes** — les
sommes peuvent être agrégées une fois, tôt dans le pipeline. Cas le plus simple (variance
*ultimate cluster*, un seul degré) : 30 000 000 personnes → ~10 000 PSU pour les calculs finaux
de variance. C'est le levier de performance le plus important de l'architecture —
`pl.scan_parquet(...).select(colonnes_utiles).group_by(["psu", "strate", *over]).agg(...)` avant
même d'atteindre l'étage de variance, plutôt que de faire tourner le calcul sur la table complète.

**Nuance nécessaire pour les designs à plusieurs degrés (utilisateur, 2026-08-30)** : écraser
directement au niveau PSU n'est valable que pour un design à un seul degré, ou pour l'estimateur
*ultimate cluster* qui ignore délibérément les degrés inférieurs. Dès qu'on veut vraiment gérer
SSU, un troisième degré, et une FPC *à chaque* degré (§4, §6 — `stages=[...]`), il ne faut pas
toujours tout écraser au niveau PSU : le pipeline doit pouvoir faire des **agrégations
hiérarchiques**, personnes → TSU → SSU → PSU → strate, avec la contribution de variance propre à
chaque degré (composantes emboîtées de la variance à plusieurs degrés, comme le fait `survey` en
R pour les designs multi-degrés). Ça reste extrêmement scalable en Polars (chaque niveau
d'agrégation est un `group_by` de plus, toujours plus petit que le précédent) — mais c'est
statistiquement plus général qu'un simple écrasement au niveau PSU, et le module `variance.py`
(§5) doit implémenter les deux : le raccourci PSU-seul pour *ultimate cluster*/un degré, et
l'agrégation hiérarchique complète pour les designs multi-degrés déclarés via `stages=`.

**Deux passages pour les ratios (utilisateur, 2026-08-30)**, pas un seul :

```
Passage 1 — statistiques suffisantes / estimateurs ponctuels
            Â, Ĥ, M̂0, ... calculés sur l'ensemble des données (streaming, un seul scan)

Passage 2 — variables d'influence / agrégation du design
            calculées À PARTIR des valeurs globales du passage 1 (Â, Ĥ, M̂0 sont des
            constantes pour ce passage), puis agrégées par PSU/strate/degré
```

Pas un problème avec `pl.scan_parquet()` : deux scans columnaires optimisés d'une vingtaine de
colonnes restent nettement moins coûteux que de matérialiser 100 Go en mémoire d'un coup. Pour la
réplication (chemin Replication, §5), c'est encore un autre chemin optimisé : réévaluer
l'Estimand Compiler pour chacun des R jeux de poids **par lots** (batched), jamais tous les R
jeux à la fois, pour éviter de matérialiser N×R en mémoire.

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

**Révisé deux fois le 2026-08-30** : d'abord pour l'élévation du cahier des charges (§2, §4),
puis suite à la revue `Fable` (§13) et aux corrections de l'utilisateur (§13) — phases
scindées quand une seule était trop grosse pour une passe d'agent sans mémoire, et un **noyau v1
explicite** isolé pour garantir qu'un produit utilisable existe avant que le cahier des charges
complet du §4 (très large) ne soit entièrement couvert.

### Noyau v1 — ce qui doit marcher avant tout le reste (recommandation `Fable`, 2026-08-30)

Phases 0-3 + un `SurveyDesign` simple (poids/strates/PSU un degré) + **une seule** méthode de
réplication (bootstrap, la plus simple à valider). Ce noyau couvre déjà l'essentiel d'un usage
EHCVM/DHS réel — PPS, FPC multi-degrés, les 5 comportements de PSU isolé, et 4 des 5 méthodes de
réplication restantes sont un **v2** explicite (phases 4b/4c/5b/5c ci-dessous), pas une condition
pour publier une première version utilisable. Sans ce jalon intermédiaire, le risque documenté
par `Fable` est réel : ne jamais converger vers un produit utilisable tant que chaque phase
ajoute autant de surface que le cahier des charges du §4 le permettrait.

0. ✅ **Socle** (fait, 2026-08-30, tag `v0.1.0`) : `Specification`, `SurveyDesign` minimal (poids
   simples uniquement), `estimate()` en Polars in-memory pour un seul k sans plan de sondage,
   `EstimationResult` (`coef()`, `to_frame()`). 16/16 tests. Publié sur `cae-ins/afmpi`.
1. ✅ **Linéarisation Taylor** (fait, 2026-08-30, tag `v0.2.0`) (§5 — corrigé : ce chemin
   n'alimente QUE `SurveyDesign`, pas `ReplicateDesign`, voir la correction architecturale du
   §5) : `linearization.py` — fonctions d'influence pour A et pctbⱼ, testées indépendamment de
   tout plan de sondage (`test_linearization.py`). Sans cet étage, tout ce qui suit reproduirait
   le défaut du plan initial (une fonction de variance par estimand, non composable).
   *Livré* : `estimands.py` (compilateur `T(·)` : tout estimand est un ratio
   `Σn·y / Σn·x`), `linearization.py` (`u_i = n_i(y_i − R·x_i)/X`, plus l'identité par grappe
   `u_hc = (SY_hc − R·SX_hc)/X` qui permet l'effondrement précoce du §7).
2. ✅ **`SurveyDesign` de base** (fait, 2026-08-30, tag `v0.2.0`) : poids + strates simples + PSU
   (un degré), méthodes d'IC normal/t/logit consommant les variables linéarisées de la phase 1,
   `degf()` explicite dès cette phase (§6 — pas ajouté après coup, pour ne pas devoir revenir
   sur l'API de résultat plus tard). *Livré* : `survey_design.py`, `variance.py`
   (`taylor_variance`, `DesignDegrees`, `confidence_interval`), `results.py`.
   *Reste dû à cette phase, reporté en phase 10* : la comparaison numérique contre un exemple
   `mpitb` officiel et contre `survey` (R), qui demande les fichiers de référence du §14.10.
3. ✅ **Domaines et désagrégation** (fait, 2026-08-30, tag `v0.2.0`) : `domain.py` (estimation
   par sous-population sans casser le design — §6), `over=[...]`, décomposabilité vérifiée par
   assertion (`Σφˡ·M0ˡ = M0`, `DECOMPOSITION_TOLERANCE = 1e-9`), `klist` (robustesse à k).
   Tests : domaines qui traversent les strates, très petits domaines.
3.5. ✅ **Jalon de conformité du noyau — gel méthodologique avant le v2** (fait, 2026-08-30, voir
   §15 et §17). Pas une nouvelle fonctionnalité : une preuve que les phases 0-3 sont correctes
   avant de construire dessus. CI GitHub et rejet PSU/strates manquants faits via le stamp 4.5
   (§16) ; les trois subtilités (`degf()` sous domaine, bornes `logit`, politique `missing`)
   déjà testées depuis `v0.2.0` ; l'oracle `survey` (R) sur le noyau de base (SRS, stratifié
   simple, un degré, domaines) fait via le stamp 3.5-bis (§17, 131/131 tests). Le noyau 0-3 est
   désormais gelé méthodologiquement — les phases 4a+ s'appuient dessus avec confiance. Portée
   originelle (sous-ensemble du tableau de designs du §8.A qui s'applique à ce que le noyau
   couvre déjà — pas la matrice complète, qui a besoin des phases 4a+) :
   - `survey` (R) comme oracle sur SRS, stratifié simple, un degré de grappes, et domaines —
     comparaison H/A/M0 **et** SE/IC/`degf()`, pas seulement les points (§8, principe central).
   - CI GitHub automatique (`pytest` à chaque push/PR) — le dépôt existe depuis la phase 0 mais
     n'a pas encore de workflow ; à ajouter ici, pas reporté à la phase 11.
   - **Rejet explicite** (erreur, pas une valeur par défaut silencieuse) quand `psu`/`strata` sont
     absents d'un `SurveyDesign` alors que le calcul en a besoin — vérifier que c'est déjà le cas
     dans `survey_design.py`/`variance.py`, sinon corriger.
   - Validation ciblée de trois subtilités déjà implémentées mais pas explicitement testées comme
     telles : `degf()` sous un domaine (le compte doit porter sur les grappes/strates que le
     domaine atteint réellement, pas sur le design complet — §6), le comportement aux bornes de
     l'IC `logit` (proche de 0 ou 1, où `normal`/`t` peuvent sortir de `[0,1]`), et la politique
     `missing` par défaut (`listwise`, §4) appliquée correctement dans `deprivation.py`.

   **Si ce jalon passe** : le noyau 0-3 est gelé méthodologiquement — les phases 4a+ construisent
   dessus avec confiance, sans revisiter ses formules. **S'il ne passe pas** : corriger le noyau
   avant toute phase 4a+, jamais construire par-dessus un défaut connu.

*(Fin du noyau v1, gelé une fois 3.5 passé. Les phases suivantes élargissent le cahier des
charges vers le v2 complet du §4 — chacune est un ajout de surface indépendant, pas un correctif
du noyau.)*

**Chaque phase ci-dessous a sa spécification exécutable au §14, sous le même numéro** (phase 4a →
§14.4a, phase 7 → §14.7, etc.). Les entrées ci-dessous restent le *périmètre* de la phase ; §14
en donne les signatures, les formules et les cas limites. Ne pas implémenter une phase sans avoir
lu §14 sous son numéro.

4a. ✅ **`SurveyDesign` multi-degrés** (fait, 2026-08-30, tag `v0.3.0`) : `stages=[Stage(...)]`
    arbitraire (§6 — pas figé à psu=/ssu=), FPC par degré, agrégation hiérarchique
    personnes→TSU→SSU→PSU→strate (§7).
4b. ✅ **PPS** (fait, 2026-08-30, tag `v0.3.0`) : `PPSDesign` (§6) — avec/sans remise,
    probabilités d'inclusion de premier ordre, probabilités conjointes/second ordre si
    disponibles, méthode de variance correspondante. Sous-phase séparée de 4a (`Fable`,
    2026-08-30) : PPS n'est pas qu'un booléen, c'est une méthode de variance à part entière.
4c. ✅ **PSU isolé, les 5 comportements** (fait, 2026-08-30, tag `v0.3.0`) :
    `fail`/`certainty`/`adjust`/`average`/`collapse` (§4), chacun testé séparément (sous-phase
    séparée, `Fable` 2026-08-30 — pas un seul comportement par défaut avec les autres en option
    non testée).
4.5. ✅ **Stamp de durcissement — rattrapage du jalon 3.5 sur 4a-4c** (fait, 2026-08-30, tag
    `v0.3.0` durci — voir §16 —
    ajouté sur relecture de code réel de 4a-4c par `agy`, le jalon 3.5 n'ayant en réalité jamais
    été exécuté). Huit points, dans l'ordre : oracle `survey` (R) sur multi-stage+FPC à 10⁻¹⁰
    près ; même oracle sur SYG/Hájek ; clarification du chemin PPS avec remise (Hansen-Hurwitz) ;
    correction de l'appariement `joint_probability` du SYG (ambigu inter-strates) ;
    `missing_design="error"` par défaut (strates/PSU/FPC manquants) ; CI GitHub
    (`.github/workflows/`, Python 3.10/3.11/3.12) ; tests « hand-calculated » remplacés par de
    vraies égalités numériques ; resynchronisation README/PLAN sur `v0.3.0`. **Bloque 5a** tant
    que non fait — les deux branches d'inférence (Taylor, réplication) doivent s'adosser à un
    socle audité, pas seulement testé en interne.
5a. ✅ **`ReplicateDesign` — JK1/JKn** (fait, 2026-08-30, §5, réévaluation par réplicat, PAS de
    linéarisation) : les méthodes de jackknife, les plus simples à valider, avant BRR (qui a
    besoin d'une matrice de Hadamard, `Fable` 2026-08-30). 139/139 tests ; une déviation
    documentée au §14.5a-note : `replicate_totals` n'appelle pas littéralement
    `linearization.totals` (tension réelle entre cette consigne et l'exigence de lotissement —
    un seul `frame.select()` par lot de 64 réplicats, incompatible avec un appel séparé de
    `linearization.totals` par réplicat) ; la formule est dupliquée à l'identique plutôt que
    partagée, formule vérifiée manuellement par l'orchestrateur, pas un bug.
5b. ✅ **`ReplicateDesign` — BRR/Fay BRR** (fait, 2026-08-30) : génération de la matrice de
    Hadamard (Sylvester) si les poids ne sont pas fournis, coefficient de Fay. 167/167 tests ;
    orthogonalité de Sylvester revérifiée indépendamment par l'orchestrateur (numpy) pour
    n∈{2,4,8,16,32}. Défaut `fay=0.5` non explicitement mandaté par §14.5b mais cohérent avec
    l'exemple d'API du §5 (ligne ~430) et la convention des enquêtes fédérales US.
5c. ✅ **`ReplicateDesign` — bootstrap/SDR, et le cahier des charges enrichi** (fait, 2026-08-30,
    172/172 tests, phase 5 complète) : `scale`, `rscales`,
    `combined_weights`, `mse` vs variance de réplicat centrée (§4, §6) — pour lire correctement
    des fichiers de poids de réplicat déjà produits par une institution. Rigueur de validation à
    égaler avec `svy` (§12) : comparer contre `survey` (R) à haute précision, documenter tout
    écart chiffré dans un `CHANGELOG.md`.
6a. ✅ **Évolution dans le temps — échantillons indépendants** (fait, 2026-08-30, 179/179 tests) :
    paramètres `tvar=`/`cot_year=` de `estimate()` (§6, §12), deltas absolus/relatifs/annualisés.
6b. ✅ **Évolution dans le temps — panels et échantillons chevauchants** (fait, 2026-08-30,
    185/185 tests, sous-phase à part entière, pas une option de 6a — utilisateur, 2026-08-30,
    §6) : covariance inter-vagues
    `Var(Δ) = Var(t+1) + Var(t) − 2·Cov(t+1,t)`, reconnue à partir d'identifiants de panel/PSU
    communs ou de poids de réplicat compatibles entre vagues.
7. ✅ **Tests d'hypothèses et VCOV complète** (fait, 2026-08-30, 207/207 tests) :
   `resultat.vcov()` (matrice complète, pas seulement
   des SE marginales), `resultat.test()` (Wald, différences entre groupes, différences entre
   périodes) — `degf()` déjà posé en phase 2, étendu ici aux domaines/PSU certainty/réplication
   (§6, règle documentée et testée par cas, pas un nombre calculé en silence).
8. ✅ **Politiques de valeurs manquantes configurables** (fait, 2026-08-31, 219/219 tests) :
   `missing.py` — `listwise`, `reweighting`, règles personnalisées (§4), au lieu de la convention
   unique héritée de `PythonIPM`.
9. **Performance et passage à l'échelle recensement** (§7) : E/S parquet en streaming
   (`pl.scan_parquet`, projection/predicate pushdown), pipeline en deux passages (statistiques
   suffisantes puis variables d'influence agrégées par degré — §7), agrégation hiérarchique
   personnes→TSU→SSU→PSU→strate pour les designs multi-degrés (pas un simple écrasement PSU),
   `CensusDesign` (SE d'échantillonnage nulle), réévaluation par lots pour `ReplicateDesign`
   (éviter N×R en mémoire, §7), jeu de données synthétique à l'échelle recensement, suite de
   benchmarks avec cibles chiffrées (§7), comparaison mesurée à un backend pandas naïf.
   Volontairement après la rigueur statistique (phases 1-8) : optimiser un calcul encore faux
   n'a pas de sens.
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

*(Note, révisée le 2026-08-30 : ~~seule la phase 0 est faite~~ — le **noyau v1 (phases 0 à 3) est
livré**, tag `v0.2.0`, 104/104 tests verts. Les phases 4a à 12 restent à faire ; elles peuvent
s'étaler sur autant de passes que nécessaire, dans l'ordre du §14.0 « ordre d'exécution et
dépendances ».)*

### Règle de non-régression valable pour toutes les phases restantes

Aucune phase 4a-12 n'a le droit de casser une garantie déjà livrée. Concrètement, à la fin de
chaque phase :

1. `pytest` passe intégralement (les 104 tests du noyau v1 **plus** ceux ajoutés par la phase) ;
   aucun test existant n'est supprimé ni assoupli pour faire passer du code neuf.
2. Les signatures publiques déjà livrées restent compatibles : `estimate(df, spec, design, *, k,
   over, domain, ci_method, level, check_decomposability)` ne perd aucun paramètre et n'en rend
   aucun obligatoire ; tout nouveau paramètre est **keyword-only avec une valeur par défaut qui
   reproduit exactement le comportement actuel**. Idem pour les champs des dataclasses gelées :
   on ajoute à la fin, jamais au milieu (`SurveyDesign("w", "taille")` en positionnel doit
   continuer de marcher — un test l'utilise).
3. Les colonnes de `_ESTIMATE_SCHEMA` (`estimation.py`) ne sont ni renommées ni retirées ; une
   phase qui produit une nouvelle famille de lignes crée **une table à part** exposée par une
   nouvelle méthode de `EstimationResult` (par exemple `changes()` en 6a), elle n'élargit pas la
   table principale.
4. Les invariants de `test_invariants.py` (M0 = H·A, Σactbⱼ = M0, Σpctbⱼ = 1, Σφˡ·M0ˡ = M0)
   restent vrais pour toute nouvelle famille de design, avec les mêmes tolérances.

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
  représentatif. *(Chiffre dépassé — repéré en revue `Fable`, 2026-08-30 : §7 donne « quelques
  minutes, quelques Go », qui fait foi ; conservé ici tel quel pour l'exactitude historique du
  compte-rendu d'`agy`.)*
- **Frontière de la phase 1 précisée** (§9) : Polars fait partie du moteur de calcul dès la
  phase 1 (`estimate()` en Polars in-memory, un seul k, pas de plan de sondage complet) pour
  éviter une refonte plus tard ; en revanche l'E/S parquet avancée, le mode streaming et les
  benchmarks à 10 M lignes restent isolés en phase 4, pour ne pas sur-ingénierier avant que la
  logique de calcul soit stabilisée et testée. *(Numérotation obsolète après le rephasage —
  repéré en revue `Fable`, 2026-08-30 : « phase 1 » de cette entrée = phase 0 actuelle (faite),
  « phase 4 » = phase 9 actuelle (performance/recensement) ; le principe reste valide.)*
- **Nom `afmpi` confirmé** — jugé court, clair, mémorisable.
- **Angles morts ajoutés** (répercutés en §4 et §8) : traitement des strates à PSU unique
  (*lonely PSUs* — un seul cluster dans un domaine, variance non estimable, cf. le cas déjà géré
  dans `PythonIPM/pipeline/05_indices_ipm.py::ratio_et_ic`, qui renvoie un IC vide plutôt qu'une
  valeur inventée), validation stricte du typage des indicateurs (booléen ou 0/1 uniquement, pas
  de coercition silencieuse), tests aux bornes k=0 et k=1, tolérance numérique 1e-6 pour la
  validation croisée EHCVM (déjà utilisée en §8, confirmée par la revue).

## 11. Points ouverts (à trancher avant ou pendant l'implémentation)

- ~~Faut-il qu'`afmpi` sache lire directement un `vecteur_z`/`vecteur_w` façon `PythonIPM` ?~~
  **Tranché (Claude, 2026-08-30) : non.** `afmpi` prend en entrée des indicateurs déjà binarisés
  (`g0`, 0/1 ou booléens — validation stricte déjà implémentée dans
  `deprivation._validate_and_normalize_indicators`), conformément au hors-périmètre du §2 (« le
  package prend un DataFrame déjà propre en entrée »). L'application des seuils `z` aux variables
  brutes est spécifique à chaque enquête : c'est le travail du pipeline appelant. Un adaptateur
  `vecteur_z` appartiendrait donc à `IPM_CI`, pas à `afmpi` — et `afmpi` ne doit rien contenir de
  spécifique à la Côte d'Ivoire. Aucune phase du §9 ne l'implémente.
- **Point ouvert maintenu — jeux de données `mpitb` de référence.** Où trouver des jeux de
  données `mpitb` publiquement rejouables sans accès Stata (licence) ? À vérifier — CRAN
  `mpitbR`/`mpindex` embarquent parfois des exemples en `.rda`, plus faciles à récupérer qu'un
  `.dta` Stata protégé. *Pourquoi ce point reste ouvert* : il dépend d'une disponibilité externe
  et éventuellement d'une licence, pas d'un choix de conception — aucun agent ne peut le trancher
  seul. *Ce qui est tranché malgré tout*, pour que la phase 10 soit exécutable sans lui : la
  suite de conformité **ne dépend pas** de ces fichiers (§14.10) — elle repose sur des jeux
  synthétiques déterministes et des sorties de référence figées en JSON dans le dépôt. La
  comparaison à `mpitb` est un test **supplémentaire**, marqué `@pytest.mark.optional` et
  automatiquement ignoré (`pytest.skip`) si le fichier de référence n'est pas présent. La phase
  10 est donc terminable même si ce point reste ouvert.

## 12. Analyse comparative approfondie des meilleurs packages (Claude, 2026-08-30)

Suite à la demande explicite de l'utilisateur (« il faut vraiment que notre package soit meilleur
que ceux existant déjà ») d'aller plus loin que la revue initiale d'`agy` (§10), analyse directe
des meilleurs packages du domaine adjacent — pas seulement `mpitb`/`mpitbR` (Alkire-Foster), mais
aussi les meilleurs outils Python et R pour le plan de sondage complexe en général, puisque
c'est la moitié du problème qu'`afmpi` doit résoudre.

### A. `svy` remplace `samplics` — pas juste « abandonné », un successeur réel existe

*(Note ajoutée en revue `Fable`, 2026-08-30 : le constat « aucune méthode de réplication » de ce
paragraphe est obsolète depuis l'élévation du cahier des charges — §4/§6/§9 couvrent maintenant
JK1/JKn/BRR/Fay BRR/bootstrap/SDR via `ReplicateDesign`. La recommandation qu'il fait plus bas
est déjà satisfaite ; le reste de l'analyse (métadonnées `svy`, décision de ne pas en dépendre)
reste valable.)*

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
  *(**Tranché, Claude 2026-08-30** : **non**, pas de namespaces. `EstimationResult` garde des
  méthodes à plat — c'est ce que les phases 0-3 ont livré (`coef`, `se`, `cv`, `confint`, `degf`,
  `estimates`, `to_frame`, `contributions`, `dimension_contributions`, `scores`, `decomposition`,
  `domain`, `summary`) et les phases restantes en ajoutent au même niveau (`vcov`, `test`,
  `changes`, `diagnostics`, `missing_report`). Une quinzaine de méthodes reste lisible ; un
  changement de forme d'API après publication de `v0.2.0` coûterait plus que le confort gagné.)*
- **Colonnes de résultat minimales et sobrement nommées** (`est, se, lci, uci, cv, df`) — bon
  benchmark pour `to_frame()` : `afmpi` a tendance (héritage direct de `PythonIPM`) à des noms
  français longs (`taux_privation_non_censure`) ; garder les noms français dans les sorties
  destinées à un public francophone (cohérent avec `PythonIPM`) mais envisager des alias courts
  en anglais dans l'API interne/programmatique, pour rester ergonomique en usage `pandas`/`polars`
  courant. Point à trancher par `agy` ou à l'usage, pas une conclusion ferme ici.
  *(**Tranché, Claude 2026-08-30**, par le code livré en phases 0-3 : les **noms de colonnes et
  d'API sont en anglais court** — `est, se, lci, uci, cv, df, measure, indicator, dimension,
  weight, k, over, subgroup, obs, population` (`_ESTIMATE_SCHEMA` dans `estimation.py`), et les
  docstrings sont en anglais. Le français reste la langue du `PLAN.md`, du `README.md` et des
  messages destinés à l'utilisateur final. Aucune phase restante n'introduit d'alias français
  dans les données de sortie : une seule convention, celle déjà publiée.)*
- **Typage explicite des variables catégorielles** (`svy.Cat("urbrur")` dans `sample.glm.fit()`)
  — renforce la décision déjà prise (§8, angle mort ajouté par `agy`) de valider strictement le
  typage des indicateurs (0/1 ou booléen, refus explicite sinon) : `svy` applique la même
  discipline plus largement, à tout type de variable passé à l'API.
- **Extras de packaging** (`pip install svy[report]`, `svy[all]`) pour des fonctionnalités
  optionnelles lourdes (`great-tables` pour un rendu enrichi) — modèle à reprendre pour un futur
  `afmpi[report]` (sortie formatée façon `mpitb`) plutôt que d'alourdir la dépendance de base.
  Hors périmètre des phases actuelles, à noter pour le packaging final (§9, phase 7 à l'époque de
  cette analyse — phase 11 après le rephasage, note `Fable` 2026-08-30).

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
  avant ou après la phase 4 (performance) selon ce qu'`agy` juge prioritaire. *(Fait, sous une
  forme enrichie — c'est la phase 5 actuelle du §9, avec JK1/JKn/BRR/Fay BRR/bootstrap/SDR,
  suite à la correction architecturale Taylor/Replication du §5 ; note `Fable` 2026-08-30.)*
- README (déjà écrit par `Sol` pour la phase 1 [phase 0 après rephasage], à mettre à jour dans
  une prochaine passe) : ajouter
  la note sur la convention des seuils k en fractions vs pourcentages (point B.4 ci-dessus), pour
  éviter une confusion aux utilisateurs venant de `mpitb`/`mpitbR`.

Sources consultées : [svylab.com/docs/svy](https://svylab.com/docs/svy),
[PyPI — svy](https://pypi.org/project/svy/), [GitHub — samplics-org/svy](https://github.com/samplics-org/svy),
[GitHub — girelaignacio/mpitbR](https://github.com/girelaignacio/mpitbR),
[R Journal — mpitbR](https://journal.r-project.org/articles/RJ-2026-003/),
[CRAN — survey package](https://cran.r-project.org/web/packages/survey/survey.pdf).

## 13. Revue `Fable` et corrections architecturales de l'utilisateur (2026-08-30)

Après l'élévation du cahier des charges (§2, §4-§9), le plan a été soumis à une revue
indépendante par un agent Claude en modèle `fable`, puis à une relecture directe de l'utilisateur
qui a identifié une erreur architecturale plus fondamentale que ce que `Fable` avait signalé.
Toutes les corrections listées ici sont déjà répercutées dans les sections concernées (§5, §6,
§7, §9, et des notes ponctuelles en §10/§12) — cette section documente la provenance et le
raisonnement, pour l'audit, pas des actions restant à faire.

### A. Verdict et constats de `Fable`

*Verdict* : « le plan est ambitieux et globalement cohérent sur le fond, mais porte des traces
nettes de réécriture partielle non répercutée en amont, et le phasage empile dans plusieurs
phases plus de surface qu'une passe d'agent sans mémoire ne peut raisonnablement absorber. »

1. §5 disait « deux familles de plans » alors que §6 en définissait trois — corrigé.
2. §10/§12 contenaient des renvois de phase obsolètes après la renumérotation de §9 — corrigés
   par des notes ponctuelles plutôt que réécrits (l'exactitude historique de ce que chaque agent
   a dit à l'époque est préservée).
3. §12.A affirmait qu'`afmpi` ne prévoyait « aucune méthode de réplication » — obsolète depuis
   l'élévation du cahier des charges, corrigé par une note.
4. **Le point le plus important** : le principe du §5 (variables linéarisées) était appliqué de
   façon uniforme aux trois familles de design, alors que la réplication (JK/BRR/bootstrap) ne
   linéarise pas en théorie — elle réévalue l'estimateur complet par jeu de poids. Confirmé et
   développé en détail par l'utilisateur (§13.B).
5. Phasage trop chargé (strates imbriquées + SSU + FPC par degré + PPS + 5 comportements de PSU
   isolé dans une seule phase 4 ; 5 méthodes de réplication dans une seule phase 5) — scindé en
   sous-phases (§9, phases 4a/4b/4c, 5a/5b/5c).
6. Chiffres de performance divergents entre §7 et l'ancien §10 — signalé, §7 fait foi.
7. Recommandation d'isoler un noyau v1 explicite pour garantir la convergence vers un produit
   utilisable — adopté (§9, section « Noyau v1 »).

### B. Corrections architecturales de l'utilisateur, au-delà de ce que `Fable` avait signalé

L'utilisateur a confirmé le point 4 de `Fable` et l'a formalisé mathématiquement, puis ajouté
sept points supplémentaires que la revue automatisée n'avait pas identifiés :

1. **Séparation Taylor / Réplication dans l'architecture** (§5, correction majeure) : Taylor
   linéarise (fonctions d'influence), la réplication réévalue `θ̂⁽ʳ⁾ = T(w⁽ʳ⁾)` pour chaque jeu de
   poids puis calcule la variance depuis la dispersion des R estimations. Les deux ne partagent
   pas de code de variance, seulement l'interface de résultat.
2. **Degrés arbitraires, pas figés à PSU/SSU** (§6) : `stages=[Stage(...)]` plutôt que
   `psu=`/`ssu=`/`fpc=[...]`, qui ne peut pas honnêtement prétendre gérer un design multi-degrés
   arbitraire.
3. **PPS comme objet, pas un booléen** (§6) : `PPSDesign(method=, inclusion_probability=,
   joint_probability=)` — avec/sans remise, probabilités de premier et second ordre, méthode de
   variance correspondante sont des choix distincts, pas une seule bascule vrai/faux.
4. **Agrégation hiérarchique, pas seulement PSU** (§7) : la réduction 30M lignes → ~10K PSU est
   excellente pour *ultimate cluster*/un degré, mais un vrai design multi-degrés (SSU, FPC à
   chaque degré) a besoin d'agrégations personnes→TSU→SSU→PSU→strate, avec les contributions de
   variance propres à chaque degré.
5. **`ReplicateDesign` enrichi** (§4, §6) : SDR (successive difference replication), `scale`,
   `rscales`, poids combinés/non combinés, variance MSE vs variance de réplicat centrée — pour
   lire correctement des fichiers de poids de réplicat déjà produits par une institution.
6. **Degrés de liberté comme objet de première classe** (§6) : `resultat.degf()`, avec une règle
   documentée et testée par cas (domaine, PSU certainty, réplication) — sinon deux
   implémentations peuvent avoir le même point estimé et la même erreur-type, et un IC/une
   p-value différents, uniquement à cause du df.
7. **Panels et échantillons chevauchants comme sous-phase à part** (§6, §9) :
   `Var(Δ) = Var(t+1) + Var(t) − 2·Cov(t+1,t)` — la covariance inter-vagues doit être reconnue
   explicitement (identifiants de panel/PSU communs, ou poids de réplicat compatibles), pas
   ignorée silencieusement dès qu'un identifiant de panel existe.
8. **Big data en deux passages** (§7) : passage 1 (statistiques suffisantes/estimateurs
   ponctuels, un seul scan), passage 2 (variables d'influence calculées à partir des valeurs
   globales du passage 1, puis agrégées par degré) — pas un seul passage qui mélangerait les
   deux. Réplication : réévaluation par lots, jamais N×R en mémoire d'un coup.

### C. Verdict final de l'utilisateur, après cette relecture

> « Le plan actuel n'est plus celui d'un "bon package Python MPI". Il décrit maintenant quelque
> chose de nettement plus ambitieux : un moteur spécialisé Alkire-Foster + survey statistics +
> columnar execution engine. Et là, oui, je considère désormais réaliste l'objectif de dépasser
> mpitbR/mpitb comme logiciel, à condition d'exécuter correctement ce plan. »

Notation par dimension (utilisateur, 2026-08-30, avant application des corrections B ci-dessus —
c'est-à-dire la note du *plan*, pas encore du code, qui n'existe pas au-delà de la phase 0) :

| Dimension | Note |
|---|---|
| Alkire-Foster | 10/10 |
| Architecture statistique | 9,5/10 |
| Plans complexes | 9/10 |
| Inférence | 9/10 |
| Domaines | 10/10 |
| Réplication | 8,5/10 |
| Validation | 10/10 |
| Big data | 9,5/10 |
| Recensement | 10/10 |
| Ambition globale | 10/10 |

## 14. Spécification exécutable des phases 4a à 12 (Claude, 2026-08-30)

**Pourquoi cette section existe.** Les §1-§13 disent *quoi* faire et *pourquoi*. Après la
livraison du noyau v1 (phases 0-3, tag `v0.2.0`), l'utilisateur a demandé (2026-08-30) que le
plan soit rendu suffisamment précis pour être exécuté **par un modèle qui n'a vu ni la
conversation de conception ni les revues précédentes**, avec pour seule consigne d'être fidèle au
plan. Tout ce qui restait à trancher par jugement a donc été tranché ici : signatures exactes,
formules complètes, comportement normatif de chaque cas limite, et pour chaque phase le fichier à
créer ou à modifier. Ce n'est **pas** un élargissement du périmètre : là où cette section diverge
d'une esquisse antérieure, c'est toujours pour resserrer (§14.0.C liste explicitement les
éléments retirés).

**Statut normatif.** §14 fait foi. Il a été écrit après lecture du code réellement livré ; les
esquisses d'API des §5-§7 sont antérieures au code et doivent être lues comme de l'intention, pas
comme des signatures.

### 14.0 Conventions transverses, ordre d'exécution, cas limites

#### A. Conventions de code (déduites du noyau v1 — à respecter, pas à réinventer)

1. Python ≥ 3.10. Chaque module commence par un docstring d'une ligne, puis `from __future__
   import annotations`.
2. **Docstrings en anglais**, formules en bloc `.. code-block:: text`. Le docstring de module dit
   à quel étage du pipeline §5 il appartient et ce qu'il ne fait **pas** (voir
   `linearization.py`, `variance.py` : c'est le style attendu).
3. Longueur de ligne maximale **96** caractères (le maximum observé dans le code livré).
4. Objets de configuration et de résultat : `@dataclass(frozen=True, slots=True)`. Calcul :
   fonctions libres au niveau module. Une seule classe mutable, `Specification`.
5. Toutes les colonnes internes sont préfixées `__afmpi` ; `deprivation._validate_required_columns`
   refuse déjà toute colonne d'entrée portant ce préfixe. Les noms de colonnes internes sont
   produits par des fonctions (`deprived_column(index)`, `observed_column(index)`,
   `contribution_column(index)`) ou par des constantes de module (`WEIGHT`, `SCORE`, `STRATUM`,
   `PSU`) — jamais écrits en clair ailleurs.
6. Polars uniquement pour le calcul : expressions `pl.Expr`, `group_by`/`agg`, `pl.when().then()`.
   Aucun aller-retour par pandas ou numpy dans un chemin de calcul. `pandas` n'intervient qu'à
   l'ingestion (`pl.from_pandas`) et à la sortie (`EstimationResult._convert`).
7. Erreurs : `ValueError` pour une donnée ou une combinaison d'options invalide, `TypeError` pour
   un mauvais type, avec un message qui nomme la colonne ou l'option fautive et, quand c'est
   utile, montre les valeurs fautives (`invalid[:5]`, comme dans `deprivation.py`). Jamais de
   coercition silencieuse.
8. Aucune nouvelle dépendance au-delà de `pandas`, `polars`, `pyarrow`, `scipy`, plus **`numpy`**
   (à ajouter à `pyproject.toml` en phase 5c, uniquement pour `numpy.random.default_rng`, le seul
   générateur pseudo-aléatoire reproductible requis). Aucune dépendance à R, Stata, `svy`,
   `samplics` ou `narwhals`, ni en exécution ni en test.
9. Tests : `pytest`, données synthétiques déterministes construites avec `random.Random(seed)` ou
   `numpy.random.default_rng(seed)` (patron de `tests/test_invariants.py`), jamais de réseau,
   jamais de données EHCVM/RGPH réelles. Chaque phase ajoute son fichier de test ; aucun test
   existant n'est supprimé ni assoupli.

#### B. Signature cible de `estimate()` à la fin de la phase 12

Chaque phase ajoute ses paramètres à la place indiquée ci-dessous, tous **keyword-only** et tous
avec une valeur par défaut qui reproduit le comportement de `v0.2.0` :

```python
def estimate(
    df: pd.DataFrame | pl.DataFrame | pl.LazyFrame,
    spec: Specification,
    design: SurveyDesign | ReplicateDesign | CensusDesign | None = None,
    *,
    k: float | Sequence[float] = 1 / 3,          # phase 0
    over: str | Sequence[str] | None = None,     # phase 3
    domain: str | pl.Expr | None = None,         # phase 3
    ci_method: str = "logit",                    # phase 2
    level: float = 0.95,                         # phase 2
    check_decomposability: bool = True,          # phase 3
    tvar: str | None = None,                     # phase 6a
    cot_year: str | None = None,                 # phase 6a
    overlap: str = "auto",                       # phase 6b : "auto"|"independent"|"panel"
    panel_id: str | None = None,                 # phase 6b
    lazy: bool = False,                          # phase 9
) -> EstimationResult | LazyEstimation:
```

Aucun autre paramètre n'est ajouté à `estimate()`. Tout le reste est porté par `spec` (politique
de valeurs manquantes) ou par `design` (structure, réplicats, PPS, PSU isolé).

#### C. Ce que les §5-§7 esquissaient et qui est **retiré** du périmètre (tranché ici)

Retirer ces éléments est un resserrement délibéré, pas un oubli. Ne pas les implémenter.

1. **`estimate(missing=...)`** — retiré. La politique de valeurs manquantes appartient à
   `Specification(missing_policy=...)`, décision déjà prise et livrée en phase 0 : elle est
   consubstantielle à la définition des indicateurs (elle change `c_i`), pas à l'estimation.
   Phase 8 étend `Specification.missing_policy`, elle n'ajoute rien à `estimate()`.
2. **`estimate(backend="polars"|"pandas")`** — retiré. Le moteur est Polars, toujours ; la
   *famille* de la sortie suit celle de l'entrée (`DeprivationMatrix.input_kind` +
   `EstimationResult._convert`), ce qui donne déjà à l'utilisateur pandas tout ce qu'un
   `backend="pandas"` lui aurait donné, sans un second moteur à maintenir et à valider. Le
   « backend pandas naïf » du §7 reste ce qu'il a toujours été : un **script de comparaison de
   performance** (`benchmarks/pandas_naive.py`, phase 9), pas une option d'API supportée.
3. **Le raccourci `ids=[...]`, `fpc=[...]` du §6** — retiré. Deux façons de déclarer un plan
   suffisent : `strata=`/`psu=` pour un degré (déjà livré), `stages=[Stage(...)]` pour le cas
   général (phase 4a). Une troisième forme serait de la surface d'API à tester sans gain.
4. **`contributions.py`, `decomposition.py`, `robustness.py`** — restent non créés (voir la note
   d'état de l'arborescence, §5).
5. **Interopérabilité `svy.Sample`/`svy.Design` en entrée** (§12.A) — hors périmètre des phases
   4a-12, à ne pas commencer.

#### D. Comportement normatif des cas limites (valable pour **toutes** les phases)

Ce tableau fige ce que le noyau v1 fait déjà. Aucune phase restante n'a le droit de le changer ;
chaque nouvelle famille de design doit le reproduire. Un cas limite se traduit toujours par une
valeur explicitement absente, jamais par une valeur inventée ni par une exception qui ferait
tomber tout un lot d'estimations.

| Cas | `est` | `se` | `lci`/`uci` | `cv` | Note |
|---|---|---|---|---|---|
| `k = 0` | `H = 1` exactement | `0.0` | `1.0`/`1.0` | `0.0` | `u_i = 0` pour tout `i`, donc variance nulle *par construction*, pas par arrondi. `A = M0 = Σn·c/Σn` |
| `k = 1`, personne à `c_i = 1` | `H = 0`, `M0 = 0`, `A = None` | `0.0` pour H/M0, `nan` pour A | `nan` pour A | `nan` | `A` a un dénominateur nul → `RatioTotals.value is None` ; idem `pctb`/`pctb_dim` |
| Zéro pauvre à un `k` donné | idem ligne précédente | idem | idem | idem | même mécanique, ce n'est pas un cas particulier de plus |
| Tout le monde pauvre | `H = 1`, `A = Σn·c/Σn` | `se(H) = 0` | `[1,1]` | `0.0` | l'IC logit est indéfini sur la borne : repli documenté sur l'intervalle tronqué (`variance.confidence_interval`) |
| Domaine vide (`domain=`) | — | — | — | — | `ValueError` levée par `domain.validate` **avant** tout calcul : ici l'exception est correcte, l'utilisateur a demandé une chose vide explicitement |
| Sous-groupe `over=` sans observation dans une grappe | contribue `0` | — | — | — | `estimation._align` conserve la grappe avec des sommes nulles : c'est ce qui garde la variance juste (§6) |
| Strate à PSU unique | valeur normale | selon `lonely_psu` (§14.4c) | selon | selon | par défaut `"fail"` → `nan`, et un `LonelyPSUWarning` |
| `df < 1` | valeur normale | `nan` | `nan` | `nan` | vrai quelle que soit la politique de PSU isolé |
| Poids nul sur une ligne | contribue `0` | — | — | — | autorisé (`weights >= 0`) ; c'est le mécanisme même des domaines |
| `household_size <= 0` | — | — | — | — | `ValueError` : la taille de ménage est un multiplicateur de comptage, elle doit être strictement positive |
| Ratio indéfini dans **un** réplicat (phase 5) | valeur normale | `nan` | `nan` | `nan` | un seul `θ̂⁽ʳ⁾` indéfini rend toute la variance de réplicat indéfinie ; ne pas ignorer le réplicat |

#### E. Ordre d'exécution et dépendances entre phases

```
4a ──► 4b ──┐
       4c ──┴──► 7 ──► 10 ──► 11 ──► 12
5a ──► 5b ──► 5c ──┘      ▲
6a ──► 6b ─────────┘      │
8 ─────────────────────────┤
9 ─────────────────────────┘
```

- **4a avant 4b et 4c** : les deux consomment la notion de degré et la table de sommes par
  grappe généralisée introduite en 4a.
- **5a avant 5b avant 5c** : 5a pose `ReplicateDesign`, la réévaluation par lots et la formule
  générale de variance de réplicat ; 5b n'ajoute qu'un générateur de poids ; 5c n'ajoute que des
  générateurs supplémentaires et l'honneur des paramètres fournis.
- **6a avant 6b** : 6b ne change aucune formule de 6a, il change seulement la détection du
  recouvrement (§14.6b).
- **7 après 4c, 5c et 6b** : la VCOV et les tests doivent couvrir les trois familles de design et
  les comparaisons temporelles ; les écrire avant obligerait à y revenir.
- **8 et 9 sont indépendantes** du reste et peuvent être faites à tout moment après 4a.
- **10 après tout le reste** : la suite de conformité teste ce qui existe.
- **11 puis 12** : documentation à jour puis publication.

Une phase peut être livrée seule, avec son propre commit et ses propres tests. Ne pas grouper
plusieurs phases dans un commit : le §13 documente que c'est précisément ce qui rend une passe
d'agent ingérable.

---

### 14.4a — `SurveyDesign` multi-degrés, FPC par degré

**Fichiers** : modifier `survey_design.py`, `deprivation.py`, `variance.py`, `estimation.py` ;
créer `tests/test_multistage.py`.

#### Objets

```python
@dataclass(frozen=True, slots=True)
class Stage:
    """One sampling stage: its unit identifier, its stratification, its FPC."""

    id: str
    strata: str | None = None
    fpc: str | None = None
```

`SurveyDesign` gagne **trois champs supplémentaires, ajoutés à la fin et keyword-only**, pour ne
pas casser `SurveyDesign("ponderation_menage", "taille_menage")` en positionnel :

```python
    stages: tuple[Stage, ...] | None = field(default=None, kw_only=True)
    pps: PPSDesign | None = field(default=None, kw_only=True)      # phase 4b
    lonely_psu: str = field(default="fail", kw_only=True)           # phase 4c
```

Validation ajoutée à `__post_init__` :

- `stages` et (`strata` ou `psu`) sont **mutuellement exclusifs** → `ValueError` nommant les deux
  formes. Message : `"declare either strata=/psu= (one stage) or stages=[Stage(...)], not both"`.
- `stages`, si fourni, est non vide ; les `id` sont deux à deux distincts ; aucun `id`,
  `strata` ou `fpc` ne coïncide avec `weights` ou `household_size`.
- `lonely_psu` ∈ `{"fail", "certainty", "adjust", "average", "collapse"}` (§14.4c).

**Champs déclarés en 4a mais honorés plus tard — règle anti-silence.** `pps` et `lonely_psu` sont
ajoutés dès 4a pour que la forme de `SurveyDesign` soit stable, mais leur sémantique arrive en 4b
et 4c. Tant que ces phases ne sont pas faites : `pps` est annoté `object | None` et toute valeur
non `None` lève `NotImplementedError("PPSDesign is phase 4b")` ; toute valeur de `lonely_psu`
autre que `"fail"` lève `NotImplementedError("lonely_psu=... is phase 4c")`. **Jamais un
paramètre accepté puis ignoré** — c'est exactement le reproche fait au package PyPI `mpitb` au
§1. En 4b, l'annotation devient `PPSDesign | None` et `survey_design.py` importe `pps.py` ; en
4c, les cinq valeurs deviennent effectives.

Nouvelle propriété, **le seul point d'entrée** que le reste du code doit utiliser :

```python
    @property
    def resolved_stages(self) -> tuple[Stage, ...]:
        """Canonical stage list, whichever declaration form was used."""
```

- `stages` fourni → `stages` tel quel ;
- sinon `psu` fourni → `(Stage(id=self.psu, strata=self.strata, fpc=None),)` ;
- sinon → `()` — chaque ligne est sa propre PSU, variance SRS avec remise (comportement livré).

`design_columns` renvoie désormais, dans cet ordre : tous les `strata` de degré, tous les `id` de
degré, tous les `fpc` de degré, sans doublon et sans `None`.

#### Identifiants matérialisés (`deprivation.py`)

Deux fonctions nouvelles, qui préservent exactement les noms actuels au degré 1 :

```python
def stratum_column(level: int) -> str:   # level >= 1
    return STRATUM if level == 1 else f"__afmpi_stratum{level}"

def psu_column(level: int) -> str:       # level >= 1
    return PSU if level == 1 else f"__afmpi_psu{level}"

def fraction_column(level: int) -> str:  # sampling fraction f of that stage
    return f"__afmpi_f{level}"
```

Emboîtement (généralisation exacte de `_add_design_identifiers`, qui fait déjà cela au degré 1) :

```
stratum_1 = str(strata_1)            ou "__afmpi_all__" si non déclarée
psu_1     = stratum_1 + "|" + str(id_1)
stratum_s = psu_{s-1} + "|" + str(strata_s)   (ou psu_{s-1} + "|" si non déclarée)
psu_s     = stratum_s + "|" + str(id_s)
```

Un identifiant nul devient `"__afmpi_null__"` (convention déjà en place). Cet emboîtement rend
correct un plan qui numérote ses grappes `1, 2, …` à l'intérieur de chaque strate, et rend
impossible qu'une unité chevauche deux unités parentes.

#### Correction de population finie — règle d'interprétation

Le `fpc` d'un degré `s` est lu **par cellule de variance**, c'est-à-dire par valeur distincte de
`stratum_column(s)` :

1. La colonne doit être **constante à l'intérieur de chaque cellule** ; sinon `ValueError` nommant
   la cellule et les valeurs trouvées.
2. Si **toutes** les valeurs non nulles de la colonne, sur tout l'échantillon, sont `≤ 1` : ce
   sont des **fractions de sondage** `f`, utilisées telles quelles. Exiger `0 ≤ f ≤ 1`.
3. Sinon : ce sont des **effectifs de population** `N` d'unités du degré `s` dans la cellule.
   Alors `f = m / N`, où `m` est le nombre d'unités **distinctes du degré `s`** échantillonnées
   dans la cellule. Exiger `N ≥ m` ; sinon `ValueError` (`"fpc N=… is smaller than the m=… sampled
   units in stratum …"`).
4. Une colonne qui mélange des valeurs `≤ 1` et des valeurs `> 1` est **ambiguë** → `ValueError`,
   jamais de devinette par ligne. (C'est le seul point où cette spécification est plus stricte que
   R `survey`, délibérément.)
5. Degré sans `fpc` déclaré : `f = 0`.

`f` est matérialisé une fois pour toutes dans `fraction_column(s)`, constant par cellule.

#### Formule de variance multi-degrés (normative)

Notations, pour un estimand donné et un contexte donné (un `k`, un domaine ou un sous-groupe) :

- `u_i` : valeur d'influence de la ligne `i` (déjà produite par `linearization.py`) ;
- pour une unité `v` d'un degré quelconque, `u_v = Σ_{i ∈ v} u_i` (l'influence est additive :
  c'est ce qui autorise tout l'effondrement hiérarchique du §7) ;
- une **cellule** `h` du degré `s` est une valeur de `stratum_column(s)` ; elle contient
  `m_h` unités échantillonnées du degré `s`, de moyenne d'influence `ū_h` ;
- `f_h` est la fraction de sondage de cette cellule.

Contribution d'une cellule :

```
V_s(h) = m_h / (m_h - 1) * Σ_{v ∈ h} (u_v - ū_h)²             si m_h >= 2
V_s(h) = traitée par lonely_psu (§14.4c)                       si m_h == 1
```

Variance totale, par récurrence descendante sur les degrés (`S` = nombre de degrés) :

```
V = Σ_{h ∈ degré 1} [ (1 - f_h) * V_1(h) ]
  + Σ_{h ∈ degré 1} [ f_h * Σ_{v ∈ h} W_2(v) ]

W_s(v) = Σ_{g ∈ degré s, g ⊂ v} [ (1 - f_g) * V_s(g) + f_g * Σ_{v' ∈ g} W_{s+1}(v') ]
W_{S+1}(·) = 0
```

Autrement dit : le terme du degré `s` est multiplié par le produit `Π_{t < s} f_t` des fractions
de sondage rencontrées sur le chemin, et par `(1 − f_s)` pour son propre degré.

**Trois conséquences à vérifier explicitement en test** :

1. `S = 1` sans `fpc` → `V = Σ_h m_h/(m_h−1) Σ_c (u_hc − ū_h)²` : **exactement**
   `variance.taylor_variance` telle qu'elle est livrée. Le nouveau chemin doit reproduire
   l'ancien au bit près sur les mêmes données.
2. `f_1 = 0` (aucune FPC au degré 1) annule **tous** les degrés inférieurs : on retombe sur
   l'estimateur *ultimate cluster*. C'est la raison pour laquelle un plan à plusieurs degrés sans
   FPC déclarée n'a pas besoin des degrés inférieurs — et c'est aussi le comportement de R
   `survey`.
3. `f_1 = 1` (recensement des PSU dans la strate) annule le terme du degré 1 et ne garde que les
   degrés inférieurs.

#### Degrés de liberté

Inchangés : `df = #PSU(degré 1) − #strates(degré 1)`, comptés — comme aujourd'hui — sur les
grappes et strates qui contiennent des observations du domaine. **Les degrés inférieurs
n'ajoutent aucun degré de liberté.** `DesignDegrees` n'est pas modifié.

#### Mécanique d'implémentation

1. `linearization.cluster_sums` accepte déjà `group_columns` : l'appeler avec la clé la plus fine
   `(stratum_1, psu_1, stratum_2, psu_2, …, stratum_S, psu_S)`. C'est le seul passage sur toutes
   les lignes.
2. `linearization.cluster_influence` donne `u` au degré le plus fin.
3. Remonter par `group_by(...).agg(pl.col(key).sum())` successifs : degré `S` → `S−1` → … → 1.
   Chaque niveau est strictement plus petit que le précédent (§7).
4. `variance.py` : nouvelle fonction

```python
def multistage_variance(
    influence: pl.DataFrame,
    keys: tuple[str, ...],
    fractions: pl.DataFrame,
    *,
    depth: int,
    lonely_psu: str = "fail",
) -> dict[str, float]:
```

   et un point d'entrée unique appelé par `estimation._context_rows` :

```python
def design_variance(
    influence: pl.DataFrame,
    keys: tuple[str, ...],
    degrees: DesignDegrees,
    design: SurveyDesign,
) -> dict[str, float]:
```

   qui aiguille vers `taylor_variance` (un degré, pas de FPC, pas de PPS — chemin rapide
   inchangé) ou vers `multistage_variance`. `taylor_variance` **garde sa signature actuelle** :
   `tests/test_linearization.py` et `tests/test_estimation.py` l'utilisent.

#### Tests obligatoires (`tests/test_multistage.py`)

1. Non-régression : `stages=[Stage(id="psu", strata="h")]` donne **exactement** le même résultat
   que `SurveyDesign(strata="h", psu="psu")` (égalité à `1e-15`, pas une tolérance lâche).
2. `fpc` en fraction et `fpc` en effectif donnant le même `f` produisent la même variance.
3. Deux degrés sans FPC = un degré (ultimate cluster).
4. Exemple à deux degrés calculé à la main et écrit en dur dans le test : 2 strates × 2 PSU ×
   2 SSU, `f_1 = 0.5`, `f_2 = 0.25`, valeurs d'influence choisies rondes ; vérifier la variance
   terme à terme.
5. `f_1 = 1` : seul le degré 2 contribue.
6. Erreurs : `fpc` non constant dans une cellule ; `fpc` mélangeant `≤ 1` et `> 1` ; `N < m` ;
   `stages=` avec `psu=` ; `stages=[]`.
7. Domaine et `over=` sur un plan à deux degrés : la décomposabilité `Σφˡ·M0ˡ = M0` reste vraie.

---

### 14.4b — PPS (probabilités inégales)

**Fichiers** : créer `src/afmpi/pps.py` ; modifier `survey_design.py` (champ `pps=`, déjà déclaré
en 4a), `deprivation.py` (validation et matérialisation de π), `variance.py` ; créer
`tests/test_pps.py`.

#### Objet

```python
@dataclass(frozen=True, slots=True)
class PPSDesign:
    """Unequal-probability sampling at the first stage (PLAN.md §6, §14.4b)."""

    method: str = "with_replacement"        # "with_replacement" | "without_replacement"
    inclusion_probability: str | None = None
    joint_probability: pl.DataFrame | pd.DataFrame | None = field(default=None, compare=False)
    variance: str = "auto"                  # "auto" | "hajek" | "sen_yates_grundy"
```

- `joint_probability` est une **table en forme longue**, pas une colonne de `df` ni une matrice
  dense : colonnes `psu_a` (str), `psu_b` (str), `pi_ab` (float). Les identifiants sont ceux de
  la colonne `Stage.id` du degré 1 **avant** emboîtement. Une seule orientation suffit
  (`(a, b)` implique `(b, a)`) ; les doublons contradictoires sont une `ValueError`.
- `method="without_replacement"` **exige** `inclusion_probability`.
- `variance="auto"` → `"sen_yates_grundy"` si `joint_probability` est fourni, `"hajek"` sinon.
- Contraintes, chacune une `ValueError` explicite : PPS s'applique au **degré 1 seulement** (un
  plan à plusieurs degrés avec `pps=` est refusé — hors périmètre, dit tel quel dans le message) ;
  `pps=` avec un `fpc` déclaré au degré 1 est refusé (π porte déjà l'information de population
  finie) ; π doit être numérique, sans valeur manquante, `0 < π ≤ 1`, et **constante à
  l'intérieur de chaque PSU**.

#### Ce que PPS change — et ce qu'il ne change pas

Les poids restent ceux déclarés dans `weights=`. `inclusion_probability` n'entre **que** dans la
variance. Les estimateurs ponctuels sont inchangés — un point à écrire dans le docstring, parce
que c'est contre-intuitif et que le confondre est l'erreur classique.

#### Les trois estimateurs

Soit, dans une strate `h`, les `m_h` PSU échantillonnées, `t_c = u_hc` l'influence totale de la
PSU `c` (déjà dilatée par les poids), `π_c` sa probabilité d'inclusion de premier ordre.

**1. `with_replacement` (Hansen-Hurwitz).** Aucune formule nouvelle : c'est exactement
l'estimateur *ultimate cluster* déjà livré,

```
V = Σ_h m_h/(m_h - 1) * Σ_c (t_c - t̄_h)²
```

parce que l'influence contient déjà `n_i = 1/π_i`. `PPSDesign(method="with_replacement")` est donc
purement déclaratif : il valide π s'il est fourni et n'altère aucun calcul. **C'est un fait à
documenter, pas un raccourci** : un plan PPS avec remise est déjà correctement traité par
`v0.2.0`.

**2. `sen_yates_grundy` (exact, exige les probabilités conjointes).** Par strate, puis somme sur
les strates :

```
V_h = -½ * Σ_{c ≠ d} [ (π_cd - π_c·π_d) / π_cd ] * (t_c - t_d)²
```

La somme porte sur les paires ordonnées `c ≠ d` de PSU de la strate (le facteur `−½` en tient
compte). Exiger `π_cd > 0` pour toute paire échantillonnée ; une paire manquante dans la table
est une `ValueError` qui nomme la paire. C'est l'estimateur de référence pour un plan de taille
fixe ; c'est aussi le seul dont on peut exiger une concordance à `1e-9` avec R `survey`
(`pps = ppsmat(...)`).

**3. `hajek` (approximation, quand seul π est disponible).** Approximation de Hájek (1964) pour
un plan πPS de taille fixe, par strate :

```
t̄* = Σ_d (1 - π_d)·t_d / Σ_d (1 - π_d)
V_h = m_h/(m_h - 1) * Σ_c (1 - π_c) * (t_c - t̄*)²
```

Si `Σ_d (1 − π_d) = 0` (toutes les PSU de la strate sont certaines, `π = 1`), la strate contribue
`0` et n'est pas traitée comme un cas d'erreur.

**Statut de validation, à écrire dans le docstring et dans le `CHANGELOG.md`** : la formule
ci-dessus est **normative pour `afmpi`**. La comparaison à R `survey` avec `pps="brewer"` est un
test **indicatif à tolérance documentée** (de l'ordre de quelques pour cent sur la SE) et non un
test d'égalité : Brewer et Hájek sont deux approximations différentes de la même quantité et ne
peuvent pas coïncider. Ne pas « corriger » `afmpi` pour faire converger ce test ; documenter
l'écart chiffré, comme le fait `svy` (§12.A).

#### Degrés de liberté et PSU isolé

`df = #PSU − #strates`, inchangé. Une strate à PSU unique suit `lonely_psu` (§14.4c) sous PPS
comme ailleurs — avec une exception naturelle : si `π_c = 1` pour cette unique PSU, elle est
*certaine* et sa contribution est `0` quelle que soit la politique (à tester).

#### Tests obligatoires (`tests/test_pps.py`)

1. `with_replacement` produit **exactement** le résultat de `v0.2.0` sans `pps=`.
2. Sen-Yates-Grundy sur un plan à 2 PSU par strate calculé à la main, valeurs en dur.
3. Sen-Yates-Grundy avec `π_cd = π_c·π_d` (indépendance) donne une variance nulle terme à terme —
   contrôle de cohérence de la formule.
4. Hájek avec tous les `π` égaux à `m/M` redonne, à la FPC près, l'estimateur stratifié classique.
5. Toutes les erreurs listées ci-dessus, une par test.

---

### 14.4c — PSU isolé : les cinq comportements

**Fichiers** : modifier `variance.py` (le seul endroit où la politique s'applique) ; créer
`tests/test_lonely_psu.py`.

#### Définition d'une strate isolée (reprise du code livré, à ne pas changer)

Dans un contexte donné (un `k`, un domaine ou un sous-groupe), une strate est **isolée** si elle
est *utilisée* — au moins une de ses grappes contient une observation du domaine — et si le
nombre de grappes **du plan** qu'elle contient est `< 2`. C'est ce que `variance.design_degrees`
calcule déjà (`sizes.filter(used & (m < 2))`). Le comptage porte sur les grappes du plan, pas sur
celles qui ont des observations du domaine : c'est la convention de `survey`, et c'est ce qui
rend un domaine étroit estimable tant que son plan sous-jacent ne l'est pas.

**Conséquence importante : la politique s'applique par contexte.** Une strate peut être isolée
pour un sous-groupe et pas pour un autre, dans le même appel. C'est la raison pour laquelle
`"fail"` **n'a pas le droit de lever une exception** : une seule sous-préfecture mal dotée ne doit
pas faire échouer un tableau de 442 lignes.

#### Les cinq politiques (`lonely_psu=`, défaut `"fail"`)

Notations : `u_h1` l'influence de l'unique grappe de la strate isolée `h` ; `ū_all` la moyenne des
influences par grappe sur **tout** le plan du contexte (toutes strates confondues) ;
`H₂` l'ensemble des strates utilisées ayant `m ≥ 2`.

| `lonely_psu` | Contribution de la strate isolée | Effet sur `degf()` |
|---|---|---|
| `"fail"` *(défaut)* | aucune : la variance du contexte entier vaut `nan` | `df` calculé normalement, mais toutes les SE sont `nan` |
| `"certainty"` | `0` — la grappe est traitée comme auto-représentative | la strate et sa grappe sont **exclues** des deux comptages : `df` inchangé par elle |
| `"adjust"` | `(u_h1 − ū_all)²`, **sans** le facteur `m/(m−1)` (indéfini pour `m = 1`) | la strate compte 1 grappe et 1 strate : contribution nette `0` au `df` |
| `"average"` | `(1/\|H₂\|) · Σ_{h'∈H₂} V(h')`, calculée **par estimand** | comme `"adjust"` |
| `"collapse"` | les strates isolées sont fusionnées avant tout calcul (règle ci-dessous) | `df` calculé sur la stratification **fusionnée**, donc plus grand |

Précisions qui ne doivent pas être laissées au jugement :

- `"fail"` **ne lève pas d'exception** — il émet un `LonelyPSUWarning` (nouvelle classe, sous-classe
  de `UserWarning`, définie dans `variance.py`) nommant les strates fautives et le contexte, et
  renvoie `nan` pour tous les estimands du contexte. C'est **exactement le comportement livré en
  `v0.2.0`**, plus l'avertissement ; le nom `"fail"` est repris de R `survey` pour la
  familiarité, et **la divergence avec R (qui, lui, lève) doit être écrite dans le docstring et
  dans le README** : `afmpi` estime beaucoup de contextes en un appel, R en estime un seul.
- `"average"` avec `H₂` vide (toutes les strates utilisées sont isolées) retombe sur `"fail"`,
  avec un avertissement disant que c'est ce qui s'est passé.
- **Règle de fusion déterministe de `"collapse"`** — l'ordre alphabétique des clés de strate est
  la seule référence, pour que le résultat soit reproductible : (1) toutes les strates isolées du
  contexte sont réunies en une seule strate portant la clé `"__afmpi_collapsed"` ; (2) si cette
  strate fusionnée contient encore `< 2` grappes, elle est jointe à la strate de `H₂` dont la clé
  est la plus petite en ordre lexicographique ; (3) si `H₂` est vide, retomber sur `"fail"` avec
  un avertissement. Ne jamais fusionner « avec la strate voisine » au sens géographique :
  `afmpi` ne connaît aucune géographie.
- Après application de la politique, `DesignDegrees` est **recalculé** sur la stratification
  éventuellement fusionnée, et si `df < 1` la variance vaut `nan` quelle que soit la politique
  (ligne « `df < 1` » du tableau §14.0.D).

#### Ordre des opérations dans `variance.py`

```
influence par grappe  ──►  application de lonely_psu (peut modifier la stratification)
                      ──►  recalcul de DesignDegrees
                      ──►  formule de variance (§14.4a ou §14.4b)
```

#### Tests obligatoires (`tests/test_lonely_psu.py`)

1. Un jeu de données à 3 strates dont une isolée, les cinq politiques dans le même test, avec les
   cinq variances attendues écrites en dur (calculables à la main sur 5 grappes).
2. `"fail"` renvoie `nan` **et** émet exactement un `LonelyPSUWarning` (`pytest.warns`).
3. `"certainty"` donne la même variance que le même jeu de données **privé** de la strate isolée,
   et le même `df`.
4. `"collapse"` sur deux strates isolées donne le même `df` qu'un plan où l'utilisateur les aurait
   fusionnées lui-même en amont.
5. `"average"` avec `H₂` vide → repli sur `"fail"` + avertissement.
6. Isolement *induit par un domaine* : une strate non isolée nationalement le devient pour un
   sous-groupe → seules les lignes de ce sous-groupe sont affectées, les autres restent chiffrées.
7. Non-régression : sans strate isolée, les cinq politiques donnent le même résultat, identique à
   `v0.2.0`.

---

### 14.5a — `ReplicateDesign` : JK1 et JKn

**Fichiers** : créer `src/afmpi/design_base.py`, `src/afmpi/replicate_design.py`,
`src/afmpi/replicate_estimation.py`, `tests/test_replicate_estimation.py` ; modifier
`survey_design.py`, `deprivation.py`, `estimation.py`, `results.py`, `__init__.py`.

#### Socle commun aux familles de design

Créer `design_base.py` :

```python
class Design(abc.ABC):
    """What every design family must expose, whatever its variance path."""

    variance_path: ClassVar[str]              # "taylor" | "replication" | "census"

    @property
    @abc.abstractmethod
    def required_columns(self) -> tuple[str, ...]: ...

    @property
    @abc.abstractmethod
    def design_columns(self) -> tuple[str, ...]: ...
```

`SurveyDesign` (`variance_path = "taylor"`), `ReplicateDesign` (`"replication"`) et
`CensusDesign` (`"census"`, phase 9) en héritent. `deprivation.build` remplace son
`isinstance(design, SurveyDesign)` par `isinstance(design, Design)` ; le message d'erreur devient
`"design must be a SurveyDesign, ReplicateDesign, CensusDesign or None"`. Tous les tests livrés
doivent rester verts après ce changement de base.

#### Objet

```python
@dataclass(frozen=True, slots=True)
class ReplicateDesign(Design):
    """Replicate-weight design: the estimand is re-evaluated, never linearized."""

    weights: str | None = None
    household_size: str | None = None
    replicate_weights: tuple[str, ...] | None = None
    method: str = "JKn"
    strata: str | None = None
    psu: str | None = None
    fay: float | None = None
    scale: float | None = None
    rscales: tuple[float, ...] | None = None
    combined_weights: bool = True
    mse: bool = True
    replicates: int | None = None      # phases 5b/5c, nombre de réplicats à générer
    seed: int = 0                      # phase 5c, bootstrap uniquement
    degf: int | None = None            # surcharge explicite des degrés de liberté
```

`method` ∈ `{"JK1", "JKn", "BRR", "Fay_BRR", "bootstrap", "SDR"}`. Phase 5a n'implémente que
`"JK1"` et `"JKn"` ; les autres lèvent `NotImplementedError` avec le numéro de phase dans le
message, jamais un silence.

Validation : `replicate_weights` fourni **ou** (`psu` fourni, pour pouvoir générer les poids) ;
`fay` uniquement avec `Fay_BRR`, dans `[0, 1)` ; `rscales`, si fourni, de longueur `R` ;
`replicate_weights` sans doublon et disjoint de `weights`/`household_size`/`strata`/`psu`.

#### Formule de variance de réplicat (normative, commune aux six méthodes)

C'est **la** formule que toute la famille réplication utilise ; `scale` et `rscales` y entrent
ici, et nulle part ailleurs :

```
θ̂_c = θ̂                         si mse = True   (autour de l'estimation ponctuelle)
θ̂_c = (1/R) Σ_r θ̂⁽ʳ⁾            si mse = False  (autour de la moyenne des réplicats)

V̂(θ̂) = scale · Σ_{r=1..R} rscales_r · (θ̂⁽ʳ⁾ - θ̂_c)²
```

et, pour la matrice complète (phase 7) :

```
V̂ = scale · Σ_r rscales_r · (θ̂⁽ʳ⁾ - θ̂_c)(θ̂⁽ʳ⁾ - θ̂_c)ᵀ
```

Si un seul `θ̂⁽ʳ⁾` est indéfini (dénominateur nul dans ce réplicat), `V̂` vaut `nan` pour cet
estimand — voir la dernière ligne du tableau §14.0.D. Ne pas écarter le réplicat.

#### Valeurs par défaut de `scale` et `rscales` par méthode

Elles ne s'appliquent **que** si l'utilisateur ne les a pas fournies ; un `scale` ou un `rscales`
explicite l'emporte toujours (c'est le cas d'usage du §14.5c : lire un fichier institutionnel).

| `method` | `scale` par défaut | `rscales_r` par défaut |
|---|---|---|
| `JK1` | `(R − 1) / R` | `1` |
| `JKn` | `1` | `(m_h − 1) / m_h` pour le réplicat qui retire une PSU de la strate `h` |
| `BRR` | `1 / R` | `1` |
| `Fay_BRR` | `1 / (R · (1 − ρ)²)` avec `ρ = fay` | `1` |
| `bootstrap` | `1 / R` | `1` |
| `SDR` | `4 / R` | `1` |

#### Génération des poids quand `replicate_weights` est absent

Ordre **déterministe et normatif** : strates triées par ordre lexicographique croissant de leur
clé ; à l'intérieur d'une strate, PSU triées de même. Le réplicat `r` est indexé dans cet ordre.
Sans cette règle, deux exécutions ne donneraient pas les mêmes colonnes.

**JK1** (une seule strate, toutes les PSU confondues, `m` PSU au total, `R = m`) — le réplicat `r`
retire la `r`-ième PSU :

```
w_i⁽ʳ⁾ = 0                       si i appartient à la PSU r
w_i⁽ʳ⁾ = w_i · m / (m - 1)       sinon
scale = (m - 1) / m,  rscales = 1
```

**JKn** (stratifié, `R = Σ_h m_h`) — le réplicat qui retire la PSU `c` de la strate `h` :

```
w_i⁽ʳ⁾ = 0                          si i ∈ PSU c
w_i⁽ʳ⁾ = w_i · m_h / (m_h - 1)      si i ∈ strate h, autre PSU
w_i⁽ʳ⁾ = w_i                        si i ∉ strate h
rscales_r = (m_h - 1) / m_h,  scale = 1
```

Exiger `m_h ≥ 2` pour toute strate : sinon `ValueError` nommant la strate (le jackknife n'a pas
d'équivalent des cinq politiques du §14.4c — c'est une limite, à écrire dans le docstring).

#### Poids combinés ou non

- `combined_weights=True` (défaut) : les colonnes de `replicate_weights` **sont** les poids
  `w_i⁽ʳ⁾`, poids de base inclus.
- `combined_weights=False` : ce sont des **facteurs** ; `w_i⁽ʳ⁾ = w_i × repwgt_ir`.

Dans les deux cas, le poids de population effectif du réplicat est
`n_i⁽ʳ⁾ = w_i⁽ʳ⁾ × household_size_i` quand `household_size` est déclaré — la même règle que pour
le poids de base, pour que l'unité de comptage reste la personne (§4).

#### Réévaluation (`replicate_estimation.py`)

```python
def replicate_weight_expressions(design: ReplicateDesign) -> list[pl.Expr]:
    """One n_i^(r) expression per replicate, in replicate order."""

def generate_replicate_weights(
    frame: pl.DataFrame, design: ReplicateDesign
) -> tuple[pl.DataFrame, tuple[str, ...], float, tuple[float, ...]]:
    """Materialise the replicate weight columns, and their scale/rscales."""

def replicate_totals(
    frame: pl.DataFrame,
    estimands: tuple[RatioEstimand, ...],
    weights: Sequence[pl.Expr],
    *,
    group_column: str | None = None,
    batch_size: int = 64,
) -> list[tuple[RatioTotals, ...]]:
    """Re-evaluate T(.) once per replicate, in batches (PLAN.md §7)."""

def replicate_variance(
    point: tuple[RatioTotals, ...],
    replicates: Sequence[tuple[RatioTotals, ...]],
    keys: tuple[str, ...],
    *,
    scale: float,
    rscales: Sequence[float],
    mse: bool,
) -> dict[str, float]:
```

Points d'implémentation qui ne doivent pas être devinés :

- `replicate_totals` réutilise **`linearization.totals`**, qui accepte déjà une expression de
  poids — c'est le point d'intégration avec le code existant, et la raison pour laquelle aucune
  formule d'estimateur n'est réécrite : la réplication réévalue `T(·)`, elle ne la redéfinit pas.
- **Lots** (`batch_size=64`) : un lot construit un seul `frame.select(...)` portant
  `2 · |estimands| · batch_size` agrégations. Ne jamais matérialiser une colonne de poids par
  réplicat pour les `R` réplicats à la fois (§7 : « jamais `N×R` en mémoire »). `batch_size` est
  un paramètre de fonction, pas une option d'API publique.
- **Sous-groupes** : tous les niveaux d'une variable `over` sont obtenus dans le **même** passage,
  par `group_by(group_column).agg(...)` au lieu de `select(...)`. Le coût reste `O(R)` scans, pas
  `O(R × nombre de sous-groupes)`.
- **Domaine** : l'indicatrice de domaine multiplie chaque expression de poids de réplicat,
  exactement comme `domain.Domain.weight()` le fait pour le poids de base. Aucune ligne n'est
  jamais filtrée.

#### Degrés de liberté en réplication

`DesignDegrees` est réutilisé tel quel, avec une lecture différente de ses champs, à documenter
dans son docstring : `psus` reçoit `R` (le nombre de réplicats), `strata` reçoit le nombre de
strates de variance, `lonely_strata` vaut `0`.

| `method` | `df` |
|---|---|
| `JK1` | `R − 1` |
| `JKn` | `R − H`, `H` = nombre de strates (déclarées ou reconstituées à la génération) ; `R − 1` si les strates sont inconnues (poids fournis sans `strata=`) |
| `BRR`, `Fay_BRR`, `bootstrap`, `SDR` | `R − 1` |
| n'importe laquelle, avec `degf=` fourni | la valeur fournie, qui l'emporte toujours |

`degf=` existe parce qu'un fichier institutionnel documente souvent son propre `df` : c'est
exactement le genre d'écart invisible que le §6 veut rendre explicite.

#### Intégration dans `estimation.py`

`_context_rows` est scindé, sans changer ce qu'il produit :

```python
@dataclass(frozen=True, slots=True)
class VarianceReport:
    values: dict[str, float]     # variance par clé d'estimand
    degrees: DesignDegrees
    population: float
    observations: int
```

- `_taylor_report(...)` : le corps actuel (sommes par grappe → influence → `design_variance`) ;
- `_replicate_report(...)` : totaux ponctuels → `replicate_totals` → `replicate_variance` ;
- `_census_report(...)` : phase 9 ;
- `_context_rows(...)` reçoit un `VarianceReport` et construit les lignes du tableau — **cette
  partie est commune aux trois familles et ne doit exister qu'une fois** (c'est le « point de
  convergence » du §5 : l'interface est partagée, pas le calcul de variance).

#### Tests obligatoires (`tests/test_replicate_estimation.py`)

1. Sur un plan stratifié en grappes, `ReplicateDesign(method="JKn", strata=…, psu=…)` avec poids
   générés donne une variance **égale à `taylor_variance`** pour `H` et `M0` (identité exacte du
   jackknife stratifié et de la linéarisation pour une moyenne pondérée) et **proche** pour `A`
   (tolérance relative `1e-6`, à documenter : le jackknife n'est pas exactement la linéarisation
   pour un ratio).
2. Poids de réplicat fournis en dur, variance calculée à la main, égalité à `1e-12`.
3. `mse=True` et `mse=False` donnent des valeurs différentes et toutes deux conformes à la
   formule écrite en dur dans le test.
4. `combined_weights=False` avec des facteurs `= w⁽ʳ⁾/w` redonne exactement le résultat de
   `combined_weights=True`.
5. `batch_size=1`, `batch_size=7` et `batch_size=1000` donnent des résultats identiques au bit
   près : le lotissement est une optimisation, pas une approximation.
6. `over=` sur un design de réplication : la décomposabilité tient et le nombre de scans reste
   `O(R)` (vérifié par un compteur d'appels sur une fonction espionnée, pas par chronométrage).
7. `m_h = 1` en `JKn` → `ValueError` nommant la strate.
8. Un `θ̂⁽ʳ⁾` indéfini (réplicat où plus personne n'est pauvre) → variance `nan`, pas `0`.

---

### 14.5b — `ReplicateDesign` : BRR et Fay BRR

**Fichiers** : créer `src/afmpi/hadamard.py` ; modifier `replicate_design.py`,
`replicate_estimation.py` ; créer `tests/test_hadamard.py` et étendre
`tests/test_replicate_estimation.py`.

#### Construction de la matrice de Hadamard — normative

**Construction de Sylvester uniquement.** C'est un choix explicite : elle n'existe que pour les
ordres puissances de 2, ce qui donne parfois plus de réplicats que le minimum théorique, mais
elle est constructive, exacte, tient en quinze lignes et ne demande aucune table pré-calculée ni
arithmétique de corps finis (contrairement à Paley). Le surcoût est au plus un facteur 2 sur `R`,
c'est-à-dire sur le temps de calcul, jamais sur la justesse.

```python
def sylvester(order: int) -> pl.DataFrame:
    """Hadamard matrix of order 2**k, entries +1/-1, first row and column all +1."""
```

```
H(1)  = [1]
H(2n) = [[H(n),  H(n)],
         [H(n), -H(n)]]
```

Ordre retenu : `R = 2**ceil(log2(H + 1))`, où `H` est le nombre de strates de variance. Exiger
`R ≥ 4`. La première colonne (constante `+1`) est **écartée** ; les colonnes `2 … H+1` sont
affectées aux strates dans l'ordre lexicographique croissant de leur clé.

#### Poids de réplicat BRR

Chaque strate doit contenir **exactement 2 PSU** ; sinon `ValueError` nommant la strate et son
nombre de PSU (BRR n'est défini que pour un plan en demi-échantillons). Les deux PSU sont
ordonnées par ordre lexicographique croissant de leur clé : indice `1` et indice `2`.

Pour le réplicat `r` et la strate `h`, soit `δ_rh ∈ {+1, −1}` l'entrée de la matrice :

```
BRR      : w_i⁽ʳ⁾ = 2·w_i   si la PSU de i est celle sélectionnée par δ_rh, 0 sinon
Fay BRR  : w_i⁽ʳ⁾ = (2 - ρ)·w_i  si sélectionnée,  ρ·w_i  sinon,   ρ = fay ∈ [0, 1)
```

Convention de sélection : `δ_rh = +1` sélectionne la PSU d'indice 1, `δ_rh = −1` celle d'indice 2.

`scale` : `1/R` pour BRR, `1/(R·(1−ρ)²)` pour Fay BRR — la première étant le cas `ρ = 0` de la
seconde, ce qui doit être vrai dans le code comme dans le test.

`df` : `R − 1` (§14.5a).

#### Tests obligatoires

1. `sylvester(n) @ sylvester(n).T == n · I` pour `n ∈ {2, 4, 8, 16, 32}`.
2. Première ligne et première colonne toutes à `+1`.
3. Ordre choisi : `H = 3` → `R = 4` ; `H = 4` → `R = 8` ; `H = 7` → `R = 8` ; `H = 8` → `R = 16`.
4. `Fay_BRR(fay=0.0)` donne **exactement** `BRR` (au bit près).
5. Sur un plan à `H` strates × 2 PSU, BRR et la linéarisation donnent la même variance pour `M0`
   à `1e-10` (propriété classique : BRR est exact pour un total pondéré sur ce plan).
6. Une strate à 1 ou 3 PSU → `ValueError` nommant la strate.

---

### 14.5c — `ReplicateDesign` : bootstrap, SDR, et le cahier des charges enrichi

**Fichiers** : modifier `replicate_design.py`, `replicate_estimation.py`, `pyproject.toml`
(ajout de `numpy>=1.24`) ; étendre `tests/test_replicate_estimation.py`.

#### Bootstrap rééchelonné de Rao-Wu-Yue

Défaut `replicates = 200` si `replicates is None` ; exiger `R ≥ 2`.

Pour chaque réplicat `r` et chaque strate `h` de `m_h` PSU : tirer `m_h − 1` PSU **avec remise**
parmi les `m_h`, et noter `t_hc⁽ʳ⁾` le nombre de fois où la PSU `c` est tirée. Alors

```
w_i⁽ʳ⁾ = w_i · (m_h / (m_h - 1)) · t_hc⁽ʳ⁾        pour i dans la PSU c de la strate h
scale = 1 / R,  rscales = 1
```

(C'est la forme du bootstrap de Rao-Wu-Yue avec `m_h′ = m_h − 1`, où le facteur de
rééchelonnement `√(m_h′/(m_h−1))` vaut 1 et disparaît. Écrire cette justification dans le
docstring, sinon la formule paraît arbitraire.) Exiger `m_h ≥ 2`.

**Déterminisme** — sans cette règle, deux exécutions donnent des SE différentes : un seul
`numpy.random.default_rng(design.seed)` est créé, et les tirages sont consommés dans l'ordre
`pour r = 1..R : pour h dans les strates triées par ordre lexicographique croissant`. Le
`seed` par défaut est `0` : `afmpi` ne produit **jamais** de résultat non reproductible sans que
l'utilisateur l'ait demandé.

#### SDR (successive difference replication)

`R` = ordre de Sylvester tel que `R ≥ 4` et `R ≥ (nombre de PSU) + 1`, même construction qu'en
5b. Les PSU sont rangées dans l'ordre lexicographique croissant de `(clé de strate, clé de PSU)`
et reçoivent un rang `j = 1, 2, …, m`. Avec `a_{r,j}` l'entrée de la matrice de Hadamard à la
ligne `r` et à la colonne `((j − 1) mod R) + 1` :

```
w_i⁽ʳ⁾ = w_i · [ 1 + 2^(-3/2) · (a_{r,j} - a_{r,j+1}) ]      pour i dans la PSU de rang j
scale = 4 / R,  rscales = 1
```

où `j + 1` est pris modulo le nombre de colonnes (la dernière PSU est appariée à la première).
Référence de validation : la documentation méthodologique de l'American Community Survey, seule
source publique pour cette méthode ; l'écart constaté doit être chiffré dans le `CHANGELOG.md`,
pas résumé par « validé ».

#### Cahier des charges enrichi : lire un fichier institutionnel

C'est ici que `scale`, `rscales`, `combined_weights` et `mse` prennent tout leur sens. **Règle de
précédence, normative** :

1. Un `scale` ou un `rscales` fourni par l'utilisateur l'emporte **toujours** sur la valeur par
   défaut de la méthode (tableau §14.5a) — y compris lorsque `replicate_weights` est généré.
2. `rscales`, si fourni, doit avoir exactement `R` éléments ; sinon `ValueError` donnant les deux
   longueurs.
3. `mse` n'a pas de valeur par défaut dépendant de la méthode : `True` partout, parce que c'est la
   convention des fichiers publics les plus répandus. `mse=False` doit être demandé.
4. `degf=` l'emporte sur toute règle de `df`.
5. Aucun de ces paramètres ne modifie les estimateurs ponctuels — uniquement la variance.

À documenter dans le README : un tableau à quatre lignes montrant comment déclarer un fichier
DHS (poids fournis, `combined_weights=True`), un fichier ACS (`SDR`, `scale=4/80`), un fichier
avec `rscales` hétérogènes, et un fichier en `Fay_BRR(fay=0.3)`.

#### Tests obligatoires

1. Même `seed` → colonnes de poids identiques au bit près ; `seed` différent → colonnes
   différentes ; jamais d'appel à `numpy.random` global.
2. Bootstrap avec `R = 2000` sur un petit plan converge vers la variance de linéarisation à `2 %`
   relatif (test marqué `@pytest.mark.slow`).
3. `scale`/`rscales` explicites l'emportent : le même jeu de réplicats avec `scale=2·défaut` donne
   exactement le double de variance.
4. `rscales` de mauvaise longueur → `ValueError` donnant les deux longueurs.
5. SDR : la somme des facteurs de poids sur les réplicats vaut `R` par PSU (contrôle de
   cohérence de la construction).

---

### 14.6a — Évolution dans le temps : échantillons indépendants

**Fichiers** : créer `src/afmpi/change_over_time.py`, `tests/test_change_over_time.py` ;
modifier `estimation.py`, `results.py`.

#### Paramètres

- `tvar` : nom de la colonne identifiant la vague. Doit contenir **au moins 2** valeurs
  distinctes, sans valeur manquante (même exigence que pour une variable `over`, et pour la même
  raison) ; sinon `ValueError`.
- `cot_year` : nom d'une colonne donnant l'année civile de la vague, **constante à l'intérieur de
  chaque vague** (validé ; sinon `ValueError`). Si `None`, la durée entre deux vagues consécutives
  vaut `1` et les mesures annualisées coïncident avec les mesures brutes.
- `cot_year` sans `tvar` → `ValueError`.

#### Ce qui est estimé

Les vagues sont estimées comme des **domaines** sur la table complète — pas par des appels
séparés, et surtout pas en filtrant les lignes. Puis, pour chaque estimand, chaque `k`, chaque
sous-groupe `over`, et chaque paire de vagues `(t₀, t₁)` avec `t₀ < t₁` dans l'ordre trié des
valeurs de `tvar` :

- **toutes les paires consécutives**, et
- **la paire (première, dernière)** quand il y a plus de deux vagues (et seulement alors, pour ne
  pas la produire deux fois).

Quatre quantités, avec `d = année(t₁) − année(t₀)` (`d = 1` si `cot_year is None`) :

```
abs      Δ     = θ̂₁ - θ̂₀
rel      Δ_r   = (θ̂₁ - θ̂₀) / θ̂₀
ann_abs  Δ_a   = (θ̂₁ - θ̂₀) / d
ann_rel  Δ_ar  = (θ̂₁ / θ̂₀)^(1/d) - 1
```

`ann_rel` est la forme en croissance composée, celle de `mpitb` ; l'écrire ainsi et pas en
différence de logarithmes. Si `θ̂₀ = 0` ou `θ̂₀` est indéfini, `rel` et `ann_rel` valent `None`
avec une SE `nan` (jamais une division par zéro, jamais un `inf`).

#### Variance du changement — l'idée centrale, à ne pas contourner

`Var(Δ) = Var(θ̂₁) + Var(θ̂₀) − 2·Cov(θ̂₁, θ̂₀)`. **Ne pas implémenter cette formule terme à
terme.** Implémenter ceci à la place :

> la valeur d'influence de la différence est la différence des valeurs d'influence,
> `u_i^Δ = u_i^{(t₁)} − u_i^{(t₀)}`, et la variance de `Δ` est celle que la machinerie de variance
> déjà écrite (§14.4a) calcule sur `u^Δ`.

Deux raisons de faire ainsi, à écrire dans le docstring du module :

1. C'est **exact**, pas approché : le terme de covariance apparaît tout seul, avec le bon signe et
   la bonne valeur, parce que deux vagues qui partagent une grappe voient leurs influences
   s'additionner dans la même grappe.
2. C'est ce qui rend la **phase 6b presque gratuite** : quand les vagues sont indépendantes, les
   supports de `u^{(t₁)}` et `u^{(t₀)}` sont disjoints et la covariance vaut zéro d'elle-même ;
   quand elles se recouvrent, la même ligne de code donne la bonne covariance. Aucune formule
   nouvelle n'est nécessaire en 6b.

Pour un `ReplicateDesign`, l'équivalent est : `Δ⁽ʳ⁾ = θ̂₁⁽ʳ⁾ − θ̂₀⁽ʳ⁾`, puis la formule de variance
de réplicat du §14.5a appliquée aux `Δ⁽ʳ⁾`.

Pour les quantités relatives, **méthode delta**, avec `V₁ = Var(θ̂₁)`, `V₀ = Var(θ̂₀)` et
`C = Cov(θ̂₁, θ̂₀)` obtenus par la même machinerie (`C` se déduit de
`C = (V₁ + V₀ − Var(Δ)) / 2`) :

```
Var(Δ_r)  = V₁/θ̂₀² + θ̂₁²·V₀/θ̂₀⁴ - 2·θ̂₁·C/θ̂₀³
Var(Δ_a)  = Var(Δ) / d²
Var(Δ_ar) = ( (1/d)·(θ̂₁/θ̂₀)^(1/d) )² · ( V₁/θ̂₁² + V₀/θ̂₀² - 2·C/(θ̂₁·θ̂₀) )
```

Degrés de liberté du changement : ceux du **plan complet** (les deux vagues réunies), pas ceux
d'une vague. IC : même `ci_method`/`level` que le reste de l'appel, mais **`bounded=False`** — un
changement peut être négatif, le bornage à `[0, 1]` n'a aucun sens ici, et `ci_method="logit"` est
silencieusement remplacé par `"t"` pour les lignes de changement (à documenter dans le docstring
et dans le README, c'est le genre de détail qui produirait sinon des intervalles absurdes).

#### Sortie

Une **table séparée**, exposée par une nouvelle méthode, sans toucher à `_ESTIMATE_SCHEMA` :

```python
def changes(self):
    """Absolute, relative and annualised changes between waves."""
```

Colonnes, dans cet ordre : `measure, indicator, dimension, weight, k, over, subgroup, t0, t1,
years, type, est, se, lci, uci, df` — avec `type ∈ {"abs", "rel", "ann_abs", "ann_rel"}`. Comme
partout ailleurs, la famille de la table suit celle de l'entrée (`_convert`). Appeler `changes()`
sur un résultat estimé sans `tvar` lève `ValueError` (« no time variable was declared »).

#### Tests obligatoires

1. Deux vagues **disjointes** (aucune grappe commune) : `Var(Δ) = V₁ + V₀` à `1e-12`.
2. `d = 1` → `ann_abs == abs` et `ann_rel == rel`, exactement.
3. Trois vagues → paires produites : `(1,2)`, `(2,3)` et `(1,3)`, exactement, sans doublon.
4. `θ̂₀ = 0` → `rel` et `ann_rel` valent `None`, SE `nan`, pas d'exception.
5. `cot_year` non constant dans une vague → `ValueError`.
6. `changes()` sans `tvar` → `ValueError`.
7. Un IC de changement peut être négatif (non tronqué à `[0, 1]`).

---

### 14.6b — Panels et échantillons chevauchants

**Fichiers** : modifier `change_over_time.py`, `estimation.py` ; créer `tests/test_panel.py`.

Grâce au choix d'implémentation du §14.6a, **cette phase n'ajoute aucune formule de variance**.
Elle ajoute la *détection* du recouvrement, sa *validation* et son *signalement*.

#### Paramètres

- `overlap ∈ {"auto", "independent", "panel"}`, défaut `"auto"`.
- `panel_id` : colonne identifiant l'unité suivie (ménage ou individu), optionnelle.

#### Détection

Il y a **recouvrement** si l'une des deux conditions est vraie :

1. au moins une clé de PSU emboîtée (`psu_column(1)`) apparaît dans plus d'une vague ; ou
2. `panel_id` est fourni et au moins une de ses valeurs apparaît dans plus d'une vague.

Comportement selon `overlap` :

| `overlap` | Recouvrement détecté | Pas de recouvrement |
|---|---|---|
| `"auto"` | covariance calculée ; **entrée obligatoire dans `diagnostics()`** disant que le régime « panel » a été retenu et pourquoi | covariance nulle de fait ; entrée disant que le régime « indépendant » a été retenu |
| `"independent"` | covariance **forcée à zéro** — les deux vagues sont estimées sur des identifiants de PSU rendus distincts par préfixage de la vague ; entrée dans `diagnostics()` disant que du recouvrement a été détecté et délibérément ignoré | identique |
| `"panel"` | covariance calculée | `ValueError` : `"overlap='panel' was requested but no unit is shared between waves"` |

Le §6 exige que traiter la covariance comme nulle soit « explicite, pas le comportement par
défaut silencieux ». C'est satisfait ainsi : `"auto"` ne l'ignore jamais quand elle existe, et le
régime retenu est **toujours** consigné et lisible.

#### Nouvelle méthode de `EstimationResult`

```python
def diagnostics(self):
    """Design decisions taken during estimation, one row each."""
```

Colonnes : `topic, context, decision, detail`. Renseignée par : le régime temporel (6b), la
politique de PSU isolé effectivement déclenchée et sur quelles strates (4c), le repli d'IC logit
sur une borne (§14.0.D), et le rapport de valeurs manquantes (8). C'est le pendant lisible des
avertissements : un utilisateur qui lance 442 sous-préfectures ne lira pas 442 `warnings`, il
lira une table.

#### Contraintes de conception à valider explicitement

- Pour qu'une covariance de panel soit captée, la **même clé de PSU** doit désigner la même
  grappe dans les deux vagues. Si `panel_id` est fourni mais qu'aucune clé de PSU n'est commune,
  émettre un avertissement disant que les identifiants de grappe ne sont pas comparables entre
  vagues et que la covariance sera sous-estimée. Ne pas ré-identifier les grappes d'office :
  ce serait deviner.
- Pour un `ReplicateDesign`, la covariance n'est correcte que si les **mêmes colonnes** de poids
  de réplicat, la même méthode et le même `R` valent pour les deux vagues. Le valider et lever une
  `ValueError` sinon.
- `panel_id` est aussi utilisé pour un diagnostic chiffré : la proportion d'unités présentes dans
  les deux vagues (« taux d'appariement »), consignée dans `diagnostics()`.

#### Tests obligatoires

1. Panel parfait (mêmes ménages, mêmes grappes, mesures fortement corrélées) : `Var(Δ)` est
   **strictement inférieure** à `V₁ + V₀`, et l'écart vaut `2·C` avec `C` calculé à la main.
2. Corrélation négative construite → `Var(Δ) > V₁ + V₀` (le signe de la covariance est bien géré).
3. `overlap="independent"` sur un vrai panel redonne exactement `V₁ + V₀`, et `diagnostics()`
   contient la ligne disant que le recouvrement a été ignoré.
4. `overlap="panel"` sans recouvrement → `ValueError`.
5. `overlap="auto"` sans recouvrement → régime « indépendant » consigné, résultat identique au
   §14.6a.
6. Réplication : colonnes de réplicat divergentes entre vagues → `ValueError`.

---

### 14.7 — VCOV complète et tests d'hypothèses

**Fichiers** : modifier `variance.py`, `linearization.py`, `replicate_estimation.py`,
`results.py`, `estimation.py` ; créer `src/afmpi/testing.py`, `tests/test_vcov.py`,
`tests/test_hypothesis.py`.

#### VCOV

Formules — les mêmes que pour la variance, avec un produit extérieur à la place du carré :

```
Taylor       V = Σ_h m_h/(m_h - 1) · Σ_c (u_hc - ū_h)(u_hc - ū_h)ᵀ     (+ les termes de degré
                                                                          inférieur du §14.4a)
Réplication  V = scale · Σ_r rscales_r · (θ̂⁽ʳ⁾ - θ̂_c)(θ̂⁽ʳ⁾ - θ̂_c)ᵀ
Recensement  V = 0
```

La diagonale de `V` doit être **exactement** le vecteur de variances déjà produit par les phases
précédentes : c'est le premier test à écrire, et c'est ce qui garantit qu'on n'a pas deux chemins
de calcul divergents.

```python
def vcov(self, *, k=None, over=None, subgroup=None, measures=None):
    """Full variance-covariance matrix of one estimation context."""
```

- Le **contexte** est `(k, over, subgroup)`. Défaut : le contexte national (`over=None`) du seul
  `k` estimé. Si plusieurs `k` ont été estimés et que `k` n'est pas donné → `ValueError` listant
  les `k` disponibles ; ne jamais en choisir un.
- `measures` : séquence de clés d'estimand (`"H"`, `"A"`, `"M0"`, `"hd::i0"`, `"pctb_dim::sante"`,
  …). Défaut : `("H", "A", "M0")` — la matrice complète de tous les estimands d'une spécification
  à 17 indicateurs fait 74 × 74 et n'est presque jamais ce qu'on veut par défaut.
- Sortie : table carrée avec une première colonne `term` (chaîne) puis une colonne par terme, dans
  l'ordre de `measures`. Famille de sortie suivant l'entrée, comme partout.
- Symétrie forcée : renvoyer `(V + Vᵀ)/2` pour que l'égalité `V[i,j] == V[j,i]` soit vraie au bit
  près malgré l'ordre de sommation.

#### Tests d'hypothèses

```python
@dataclass(frozen=True, slots=True)
class HypothesisTest:
    terms: tuple[str, ...]
    estimate: float          # L·θ̂ (scalaire si q == 1, sinon nan)
    se: float                # sqrt(L·V·Lᵀ) si q == 1, sinon nan
    statistic: float
    df1: int                 # q, le rang du contraste
    df2: int                 # les degrés de liberté du plan
    p_value: float
    method: str              # "Wald"
    dist: str                # "F" | "chisq"
```

```python
def test(self, a, b=None, *, measure="M0", k=None, dist="F"):
    """Wald test of a contrast between two domains, subgroups or periods."""
```

- `a` et `b` désignent chacun soit une expression de domaine (`"region == 'Abidjan'"`), soit un
  couple `(over, subgroup)`. `b=None` teste `θ_a = 0`.
- Contraste : `L·θ̂ − c` avec, pour le cas à deux termes, `L = (+1, −1)` et `c = 0`.
- Statistique de Wald :

```
W = (L·θ̂ - c)ᵀ · (L·V·Lᵀ)⁻¹ · (L·θ̂ - c)
dist="F"      : W/q ~ F(q, df)      (défaut — la convention de `survey`, plus prudente)
dist="chisq"  : W    ~ χ²(q)
```

- Cas `q = 1` (le cas courant) : reporter aussi `estimate = θ̂_a − θ̂_b`,
  `se = sqrt(V_aa + V_bb − 2·V_ab)`, et `p_value` bilatérale issue d'un Student à `df` degrés de
  liberté — **cohérente** avec la statistique `F` (`t² = F` pour `q = 1`), ce qui doit être
  vérifié en test.
- **La covariance `V_ab` doit être calculée, jamais supposée nulle.** Deux sous-groupes du même
  échantillon ne sont pas indépendants ; les traiter comme tels est exactement l'erreur que le §6
  reproche à un package « qui donne seulement les bons estimateurs ponctuels ». Mécanique : les
  deux domaines sont deux indicatrices sur la même table, leurs influences sont deux colonnes de
  la même table de grappes, et `V_ab` sort de la même formule que `V_aa`.
- `df` : celui du plan complet (§14.4a/§14.5a), pas celui d'un domaine. Si `df < 1`,
  `p_value = nan` et `statistic = nan` — pas de test inventé.
- `__str__` lisible en une ligne, façon `summary()`.

#### Règle normative des degrés de liberté, par cas

Ce tableau est la « règle documentée et testée par cas » demandée au §6. Il doit être recopié
dans le docstring de `DesignDegrees` et testé ligne par ligne.

| Cas | `df` |
|---|---|
| Plan à un degré, stratifié ou non | `#PSU − #strates`, comptés sur les grappes/strates *utilisées* par le domaine |
| Plan à plusieurs degrés | identique — **seul le degré 1 compte** |
| Domaine ou sous-groupe | identique : les grappes du plan comptent, même vides sur le domaine |
| Strate isolée, `lonely_psu="certainty"` | la strate et sa grappe sont retirées des deux comptages |
| Strate isolée, `"adjust"`/`"average"` | comptées normalement (contribution nette nulle) |
| Strate isolée, `"collapse"` | comptées sur la stratification fusionnée |
| PPS | inchangé |
| Réplication | voir le tableau du §14.5a |
| Recensement | `df = 0`, aucun intervalle |
| Changement dans le temps | `df` du plan des deux vagues réunies |
| `degf=` fourni | la valeur fournie, dans tous les cas |

#### Tests obligatoires

1. `diag(vcov())` est **exactement** `se()**2` pour les trois familles de design.
2. `V` est symétrique et semi-définie positive (toutes les valeurs propres `≥ −1e-12`).
3. `test(a, b)` entre deux sous-groupes : la statistique reproduit une valeur calculée à la main,
   et `t² == F` à `1e-12`.
4. Un test contre lui-même (`a == b`) donne `estimate = 0`, `statistic = 0`, `p_value = 1`.
5. Ignorer `V_ab` (calculé à part dans le test) donnerait une SE différente : le test l'affirme
   explicitement, pour verrouiller le fait que la covariance est bien prise en compte.
6. Le tableau des `df` ci-dessus, une ligne par test.

---

### 14.8 — Politiques de valeurs manquantes configurables

**Fichiers** : créer `src/afmpi/missing.py`, `tests/test_missing.py` ; modifier
`deprivation.py`, `specification.py`, `results.py`.

#### Déplacement du code existant

`deprivation._apply_missing_policy` est **déplacé** dans `missing.py` sans changer son
comportement pour les deux politiques déjà livrées, et devient :

```python
def apply(frame: pl.DataFrame, spec: Specification) -> tuple[pl.DataFrame, MissingReport]:
    """Add g_ij, the observation flags, w_j*g_ij and c_i, per the policy."""
```

`deprivation.build` l'appelle. C'est un refactoring à faire **en premier, avec les 104 tests
verts avant d'ajouter quoi que ce soit**.

#### Les trois politiques

`Specification.missing_policy` accepte désormais trois valeurs (`_MISSING_POLICIES` passe de deux
à trois) plus un appelable :

| Politique | `g_ij` si manquant | Poids utilisé | `observed_ij` | Ligne conservée |
|---|---|---|---|---|
| `"listwise_deletion"` *(défaut, livré)* | — | `w_j` | — | non, la ligne est retirée si un indicateur manque |
| `"reweighting"` *(livré)* | `0` | `w_j / Σ_{j observé} w_j` | `0` | oui, si au moins un indicateur est observé |
| `"treat_as_nondeprived"` *(nouveau)* | `0` | `w_j` (inchangé) | `1` | oui, toujours |

`"treat_as_nondeprived"` est la convention de `PythonIPM` (un manquant après application du seuil
est lu comme « non privé »). Le §4 exige explicitement qu'elle soit **une politique parmi
d'autres, pas le comportement par défaut** : elle est donc disponible mais n'est pas le défaut.
Différence à documenter avec `"reweighting"` : `"reweighting"` renormalise pour que `c_i` reste
comparable et exclut l'indicateur du dénominateur de `hd`/`hdk` (`observed = 0`) ;
`"treat_as_nondeprived"` biaise `c_i` vers le bas et garde l'indicateur au dénominateur.

**Politique personnalisée** : `missing_policy` peut être un appelable

```python
Callable[[pl.DataFrame, Specification], pl.DataFrame]
```

qui reçoit la table validée et doit renvoyer une table contenant, pour chaque indicateur d'indice
`j`, les colonnes `deprived_column(j)`, `observed_column(j)` et `contribution_column(j)`. `afmpi`
valide ensuite le résultat : colonnes présentes, `g ∈ {0, 1}`, `observed ∈ {0, 1}`,
`c_i = Σ_j contribution_j ∈ [0, 1]` — et lève une `ValueError` détaillée sinon. `c_i` est
toujours recalculé par `afmpi`, jamais lu depuis la table renvoyée.

#### Rapport

```python
@dataclass(frozen=True, slots=True)
class MissingReport:
    policy: str
    rows_in: int
    rows_out: int
    dropped: int
    per_indicator: pl.DataFrame     # indicator, missing, missing_share
```

Exposé par `EstimationResult.missing_report()` et résumé dans `diagnostics()` (§14.6b).
`observations` et `excluded_observations`, déjà présents sur `EstimationResult`, ne changent pas
de sens.

#### Tests obligatoires

1. Non-régression : les deux politiques livrées donnent, après le déplacement dans `missing.py`,
   des résultats identiques au bit près.
2. Sans aucune valeur manquante, les **trois** politiques donnent le même résultat.
3. Cas construit à la main où les trois politiques donnent trois `c_i` différents, valeurs en dur.
4. `"reweighting"` : une ligne dont tous les indicateurs manquent est retirée (poids observé nul).
5. `"treat_as_nondeprived"` : aucune ligne n'est retirée, `excluded_observations == 0`.
6. Appelable renvoyant des colonnes incomplètes ou un `c_i > 1` → `ValueError`.
7. `missing_report()` compte correctement les manquants par indicateur.

---

### 14.9 — Performance, streaming parquet et `CensusDesign`

**Fichiers** : créer `src/afmpi/backend.py`, `src/afmpi/io.py`, `src/afmpi/census_design.py`,
`benchmarks/generate_census.py`, `benchmarks/pandas_naive.py`,
`tests/test_performance_scale.py`, `tests/test_census.py` ; modifier `deprivation.py`,
`linearization.py`, `estimation.py`.

#### `CensusDesign`

```python
@dataclass(frozen=True, slots=True)
class CensusDesign(Design):
    """The rows are the whole population: there is no sampling error to estimate."""

    weights: str | None = None
    household_size: str | None = None
```

`variance_path = "census"`. Comportement normatif, à écrire tel quel :

- **aucun `group_by` par grappe ou par strate n'est exécuté** — c'est le point du §7 (« un mode
  dédié, pas `SurveyDesign` avec un design dégénéré à un seul PSU géant ») et c'est aussi ce qui
  le rend plus rapide ;
- `se = 0.0`, `lci = uci = est`, `cv = 0.0`, `df = 0`, `psus = 0`, `strata = 0` ;
- `vcov()` renvoie une matrice de zéros ;
- `test()` lève une `ValueError` : sans variance d'échantillonnage, un test de Wald n'a pas de
  sens. Message : `"a census has no sampling variance; a Wald test is not defined"` ;
- `ci_method` est ignoré (documenté), `check_decomposability` fonctionne normalement.

#### Ingestion (`backend.py`)

`deprivation._to_polars` est déplacé ici et étendu :

```python
InputKind = Literal["pandas", "polars", "polars-lazy", "parquet"]

def to_frame(df) -> tuple[pl.DataFrame | pl.LazyFrame, InputKind]:
```

Règle de conversion de sortie (`EstimationResult._convert`) : `pandas` → pandas ; tout le reste →
polars. Un `LazyFrame` en entrée ne change pas la famille de sortie (polars) ; il change le
moment de l'exécution.

#### E/S parquet (`io.py`)

```python
def from_parquet(path, *, streaming=True, columns=None) -> ParquetSource
def to_parquet(frame, path, *, compression="zstd") -> None
def to_stata(frame, path) -> None      # export uniquement, via pandas
```

`ParquetSource` porte une unique méthode `estimate(spec, design, **kwargs)` qui accepte les mêmes
paramètres que `afmpi.estimate` et applique la **projection** : seules les colonnes réellement
nécessaires sont lues — indicateurs de `spec`, `design.required_columns`,
`design.design_columns`, variables `over`, colonnes citées par `domain`, `tvar`, `cot_year`,
`panel_id`. La liste des colonnes projetées est consignée dans `diagnostics()` : c'est la preuve
vérifiable que le *projection pushdown* a bien eu lieu, et c'est testable sans chronomètre.

#### Chemin paresseux en deux passages

Conforme au §7, et déjà à moitié en place grâce à l'identité par grappe de `linearization.py` :

```
Passage 1  scan.select(agrégations des estimands).collect()        → Y et X globaux
Passage 2  scan.group_by(clés de plan).agg(...).collect()          → sommes par grappe
           puis cluster_influence(...) sur la petite table         → variance
```

Ajouter à `linearization.py` la version paresseuse, **sans dupliquer la logique** (les deux
versions partagent les mêmes constructeurs d'expressions) :

```python
def cluster_sums_lazy(lf, estimands, weight=None, group_columns=(STRATUM, PSU)) -> pl.LazyFrame
def totals_lazy(lf, estimands, weight=None) -> pl.LazyFrame
```

`estimate(..., lazy=True)` renvoie un `LazyEstimation` portant `.collect() -> EstimationResult`.
`LazyEstimation` ne fait **aucune** validation coûteuse à la construction : c'est tout son intérêt.

#### Budget de ressources explicite (`ExecutionConfig`) — relecture externe, utilisateur/agy, 2026-08-31

« Utiliser Polars donc ça ira » n'est pas une conception : c'est le point soulevé par la
relecture. Exigence normative : la taille des données ne doit **pas** faire croître la RAM
nécessaire proportionnellement (`taille ↑ ⇏ RAM ↑ proportionnellement`), et le passage à
l'échelle recensement doit être **conçu** avec un budget de ressources explicite, pas ajusté
après coup.

```python
@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    max_threads: int | None = None      # None = comportement Polars par défaut
    memory_limit: str | None = None     # ex. "8GB" — budget indicatif de chunking, pas une garantie OS
    spill_dir: str | None = None        # répertoire d'écriture temporaire du moteur streaming
    batch_size: int | None = None       # remplace le batch_size=64 codé en dur de generate_replicate_weights/replicate_totals (§14.5a)
```

`estimate(..., resources=ExecutionConfig(...))`, et `ParquetSource.estimate(..., resources=...)`.
Défaut (`resources=None`) : comportement actuel inchangé — cette phase ajoute un plafond
possible, elle ne change pas le comportement par défaut du code déjà livré.

**Contrainte technique réelle à documenter, pas à cacher** : Polars gère son pool de threads au
niveau du *processus*, pas par appel (`POLARS_MAX_THREADS`, lu une fois à la première opération
Polars du processus). `max_threads` ne peut donc pas garantir un plafond différent pour deux
appels concurrents `estimate()` dans le même processus Python. Vérifier contre la version de
Polars réellement installée (`polars>=1.0` dans `pyproject.toml`, pin large) ce qui est
effectivement réglable par appel (taille de lot du moteur streaming, `pl.Config`) par opposition
à ce qui ne l'est qu'au niveau processus — et **documenter explicitement la différence** dans le
docstring d'`ExecutionConfig` et le README, plutôt que de promettre une isolation par appel qui
n'existe pas. `memory_limit` est de la même nature : un budget indicatif qui pilote la taille des
lots (`batch_size`, taille de chunk du moteur streaming), pas une limite dure garantie par l'OS —
documenter aussi cette nuance, ne pas la présenter comme un plafond garanti.

**Trois modes explicites**, à documenter dans le README (tableau) :

| Mode | Comportement |
|---|---|
| `memory` (défaut hors `CensusDesign`/`lazy=True`/`from_parquet`) | données déjà en mémoire, comportement des phases 0-8 inchangé |
| `lazy` (`estimate(..., lazy=True)`) | calcul paresseux, *projection*/*predicate pushdown*, deux passages du §14.9 |
| `streaming` (`from_parquet(..., streaming=True)`, défaut de `from_parquet`) | mémoire plafonnée par lots, `spill_dir` si le moteur streaming de Polars le permet à la version installée |

Pour un `ParquetSource` (fichier volumineux, cas recensement), le mode par défaut est
`lazy + streaming` — **pas** « tout charger puis filtrer » — conformément à la cible du §7 et au
retour de la relecture externe.

**Réplication à l'échelle recensement** : `batch_size` (déjà en place depuis 5a, défaut 64,
§14.5a) reste le mécanisme qui empêche de matérialiser une matrice `N×R` — cette phase le rend
configurable via `ExecutionConfig.batch_size` plutôt que de le changer de nature. Avec `N=40M` et
`R=200`, la mémoire des réplicats doit rester en `O(N_lot + R_lot)`, jamais en `O(N·R)` — déjà
vrai par construction du code de 5a, à revalider explicitement à cette échelle dans le test de
performance de cette phase (pas un nouveau mécanisme, une preuve chiffrée que le mécanisme
existant tient à l'échelle recensement).

**`CensusDesign` — retirer la machinerie survey inutile du chemin critique** (déjà en grande
partie normatif ci-dessus : pas de `group_by` par grappe/strate, `se=0` partout) : sur ce chemin,
aucune fonction d'influence, aucune notion de PSU/strate/FPC, aucun poids de réplicat, aucune
VCOV *survey* n'entre dans le calcul — le moteur se réduit à
`privation → score → agrégation → H/A/M0/contributions`, déjà ce que prescrit le paragraphe
`CensusDesign` ci-dessus ; cette section ne fait qu'expliciter que c'est aussi une exigence de
*performance*, pas seulement de sémantique statistique.

**Mesure des benchmarks — trois chiffres, pas un seul** : le rapport de benchmark (README,
`benchmarks/`) doit consigner **temps, pic de RAM, et utilisation CPU** (nombre de cœurs
effectivement mobilisés, pas seulement le total de cœurs de la machine), pas seulement le temps
d'exécution — modifier la section « Ce qui est mesuré et la cible chiffrée » ci-dessous en
conséquence : ajouter la mesure CPU aux mesures (a)-(e) déjà listées, avec le nombre de threads
Polars effectivement observé pendant le benchmark (`POLARS_MAX_THREADS` ou équivalent constaté).

#### Jeu de données de référence (`benchmarks/generate_census.py`)

Dimensions figées, pour que les chiffres publiés soient comparables d'une exécution à l'autre :
**10 000 000 individus**, **30 indicateurs**, **500 districts de dénombrement** (PSU),
**33 régions**, **108 départements**, **442 sous-préfectures**, générateur
`numpy.random.default_rng(20260830)`, écriture en parquet compressé `zstd`. Aucune donnée réelle.

#### Ce qui est mesuré et la cible chiffrée

Charge : (a) chargement, (b) H/A/M0 national, (c) les trois désagrégations (33, 108, 442),
(d) contributions par indicateur, (e) robustesse à 8 seuils `k`.

**Cible normative** : (b)-(e) en **moins de 300 secondes**, **moins de 8 Go** de pic mémoire
résident, et un nombre de threads Polars effectivement mobilisés cohérent avec
`ExecutionConfig(max_threads=8)` quand elle est fournie (pas de mobilisation implicite de tous
les cœurs de la machine de benchmark) — sur une machine de bureau ordinaire. C'est la traduction
chiffrée du « quelques minutes, quelques Go » du §7, qui fait foi (§13.A.6) ; le « moins de 30 s /
moins de 2 Go » du §10 est l'estimation antérieure d'`agy`, conservée pour l'exactitude
historique du compte rendu mais **non normative**. Le rapport de benchmark consigne les **trois**
chiffres — temps, pic RAM, threads effectivement observés — jamais le temps seul.

Le test correspondant est marqué `@pytest.mark.slow` et **exclu de l'exécution par défaut** :
ajouter à `pyproject.toml`

```toml
addopts = "-ra -m 'not slow'"
markers = ["slow: benchmarks and long-running convergence checks", "optional: needs an external reference file"]
```

Une version réduite (100 000 lignes, mêmes désagrégations) tourne, elle, à chaque commit, pour
attraper une régression de complexité sans coûter deux minutes de CI.

`benchmarks/pandas_naive.py` rejoue (b)-(e) en pandas pur, traduction directe de la logique de
`PythonIPM/pipeline/05_indices_ipm.py`, sans optimisation. Le rapport de gain mesuré (« N fois
plus rapide », « M fois moins de mémoire ») va dans le `README.md` **avec la date, la machine et
les versions** — un chiffre sans son contexte n'est pas une mesure.

#### `EstimationResult` ne doit pas retenir la base préparée (relecture de code, utilisateur,
2026-08-30 — voir §15, point non couvert par une passe antérieure de cette section)

Le noyau v1 (phases 0-3) fait retenir à `EstimationResult` sa `_matrix: DeprivationMatrix`
complète, pour que `result.domain(...)` et `result.scores()` restent utilisables après coup. À
l'échelle enquête, sans conséquence. À l'échelle recensement, un objet résultat de quelques
kilooctets garderait vivant un `DataFrame` de plusieurs dizaines de Go — **inacceptable, pas
juste sous-optimal**.

Règle normative pour cette phase : le résultat produit par le chemin paresseux/`CensusDesign`
(`LazyEstimation.collect()` ou `estimate(design=CensusDesign(), ...)`) **ne retient PAS** la
matrice de privation ligne à ligne — seulement les tables agrégées déjà petites (sommes par
grappe/strate/groupe, au plus quelques dizaines de milliers de lignes) nécessaires à `coef()`,
`confint()`, `vcov()`, `contributions()`. `result.domain(...)`/`result.scores()` appelés après
coup sur un tel résultat lèvent une erreur explicite (`"scores() requires an in-memory result;
re-run estimate() without lazy=True/CensusDesign streaming"`) plutôt qu'un `AttributeError` ou,
pire, un rechargement silencieux et coûteux de la base. Le chemin en mémoire (phases 0-3, petites
données) garde le comportement actuel sans changement — cette règle ne s'applique qu'aux
résultats produits par les chemins ajoutés dans cette phase.

#### Compiler le multi-`k` et les désagrégations en un seul plan (relecture de code, utilisateur,
2026-08-30 — voir §15)

`_estimate_from_matrix()` (phases 0-3) boucle sur les seuils `k`, et pour chaque `k` refait un
`cluster_sums()` par variable de désagrégation — correct et lisible à l'échelle EHCVM, mais avec
8 seuils × 3 niveaux de désagrégation, ça fait potentiellement des dizaines d'agrégations
intégrales de la base. Règle normative pour cette phase : le chemin paresseux/streaming doit
construire **un seul plan Polars** (une seule expression `group_by`/`agg` par clé de
regroupement, portant toutes les colonnes numérateur/dénominateur de tous les `k` et de toutes
les variables `over` à la fois, matérialisé une seule fois), pas une boucle de scans indépendants
— le nombre de scans du fichier source doit être **indépendant du nombre de `k`** et du nombre de
variables de désagrégation. Le chemin en mémoire des phases 0-3 (petites données) n'est pas tenu
à cette contrainte et peut garder sa boucle actuelle si la réécrire n'apporte rien à cette
échelle — la contrainte porte sur le chemin *streaming/lazy*, pas sur tout `afmpi`.

#### Tests obligatoires

1. `CensusDesign` : `se == 0.0` partout, `lci == uci == est`, `df == 0`, `test()` lève.
2. `CensusDesign` et `SurveyDesign` sans grappes donnent les **mêmes estimateurs ponctuels**.
3. `lazy=True` puis `.collect()` donne un résultat identique au bit près à `lazy=False`.
4. `from_parquet` : la liste de colonnes consignée dans `diagnostics()` est exactement la liste
   nécessaire, et pas une de plus.
5. Un parquet à 100 000 lignes et 200 colonnes donne le même résultat que la même table chargée
   en mémoire.
6. Benchmark réduit en CI ; benchmark complet marqué `slow`.
7. Un résultat produit par le chemin streaming ne retient aucune colonne au niveau ligne — un
   test introspecte l'objet résultat (taille mémoire, ou absence d'attribut `_matrix`/attribut
   explicitement vide) plutôt que de se fier à la seule absence d'erreur.
8. `result.domain(...)` sur un résultat streaming lève l'erreur explicite documentée ci-dessus,
   pas un `AttributeError` générique.
9. Pour un jeu de test à plusieurs `k` et plusieurs variables `over`, le nombre d'appels de
   lecture/scan du fichier source (instrumenté ou compté via le plan d'exécution Polars) ne
   croît pas avec le nombre de `k` ni le nombre de variables `over`.
10. `ExecutionConfig(batch_size=N)` change effectivement le nombre de réplicats traités par lot
    dans `replicate_totals` (vérifié par un compteur d'appels espionné, même style que le test
    §14.5a sur `batch_size` — pas par chronométrage).
11. `resources=None` (défaut) donne un résultat identique au bit près à un appel équivalent
    sans le paramètre — cette phase n'altère aucun résultat déjà livré, seulement les ressources
    consommées pour l'obtenir.

---

### 14.10 — Suite de conformité statistique

**Fichiers** : créer `tests/test_conformity/` (un module par famille de design),
`tests/test_conformity/reference/*.json`, `tools/reference/*.R`, `tools/reference/*.do`.

#### Principe, tranché ici : aucune dépendance à R ni à Stata au moment du test

Les valeurs de référence sont **produites hors ligne**, une fois, par les scripts de
`tools/reference/`, puis **figées en JSON dans le dépôt**. La CI ne fait que comparer. Les
scripts sont commités pour que la référence soit reproductible et auditable, mais ils ne sont
jamais exécutés par `pytest`. Cela rend la phase 10 réalisable sans licence Stata et sans R en
CI — ce qui est la seule façon de tenir le §8 en pratique.

#### Format d'un fichier de référence

```json
{
  "design": "stratified_cluster_fpc",
  "generator": "tests/test_conformity/generate.py::stratified_cluster_fpc",
  "generator_seed": 20260830,
  "reference_software": "R survey 4.4-2",
  "reference_script": "tools/reference/stratified_cluster_fpc.R",
  "produced_on": "2026-08-30",
  "tolerance": { "est": 1e-9, "se": 1e-7, "df": 0 },
  "values": [
    { "measure": "M0", "k": 0.3333333333333333, "over": null, "subgroup": null,
      "est": 0.3141592653, "se": 0.0071234567, "df": 42 }
  ]
}
```

`tolerance` est **par fichier**, avec une ligne de commentaire dans le script R expliquant
pourquoi elle vaut ce qu'elle vaut (§8 : « la tolérance dépend du design testé et doit être
justifiée, pas arbitraire »). Tolérances attendues : `1e-9` pour tout ce qui est exact
(linéarisation, jackknife, BRR, Sen-Yates-Grundy), `1e-7` pour les SE mettant en jeu une racine
carrée et une accumulation, et une tolérance **relative** documentée, de l'ordre du pour cent,
pour les seules comparaisons d'approximations différentes (Hájek contre Brewer, §14.4b).

#### Jeux de données synthétiques déterministes

Un module unique `tests/test_conformity/generate.py` avec une fonction par design, chacune
produisant un `pl.DataFrame` reproductible à partir d'une graine écrite dans le fichier JSON. Les
mêmes fonctions sont appelées par les scripts R via un export CSV commité, pour que R et `afmpi`
voient **exactement** les mêmes données.

#### Couverture obligatoire (tableau §8.A, rendu exécutable)

| Fichier | Design |
|---|---|
| `test_srs.py` | SRS, SRS stratifié |
| `test_cluster.py` | un degré en grappes, stratifié en grappes |
| `test_multistage_conformity.py` | deux degrés, FPC à chaque degré |
| `test_pps_conformity.py` | PPS avec et sans remise, avec et sans probabilités conjointes |
| `test_lonely_conformity.py` | strate à PSU unique, les cinq politiques |
| `test_domains.py` | domaines, y compris traversant les strates ; très petits domaines |
| `test_af_limits.py` | zéro pauvre, tout le monde pauvre, `k = 0`, `k = 1` |
| `test_data_limits.py` | poids extrêmes (rapport `1:10⁶`), valeurs manquantes selon les trois politiques |
| `test_replication_conformity.py` | JK1, JKn, BRR, Fay BRR, bootstrap, SDR |
| `test_overlap_conformity.py` | panels et échantillons chevauchants |

Chaque fichier compare `est`, `se` **et** `df` — le §8 insiste : deux logiciels peuvent
s'accorder sur `M0` et diverger sur la SE, et deux logiciels peuvent s'accorder sur les deux et
diverger sur l'IC par le seul `df`.

La comparaison à `mpitb` (Stata) est marquée `@pytest.mark.optional` et ignorée proprement
(`pytest.skip` avec un message explicite) quand le fichier de référence est absent — voir le
point ouvert maintenu du §11.

#### Invariants en CI

`tests/test_invariants.py` est **étendu**, pas remplacé : les invariants déjà en place
(`M0 = H·A`, `Σactbⱼ = M0`, `Σpctbⱼ = 1`, `Σφˡ·M0ˡ = M0`) doivent être vérifiés pour **chaque
famille de design** ajoutée par les phases 4a-9, y compris `CensusDesign` et chaque méthode de
réplication. Un nouvel invariant s'ajoute : `Σ_d pctb_dim_d = 1` et
`Σ_{j ∈ d} pctbⱼ = pctb_dim_d`.

---

### 14.11 — Packaging, documentation, intégration continue

**Fichiers** : créer `CHANGELOG.md`, `.github/workflows/tests.yml`, `docs/quickstart.md` ;
modifier `README.md`, `pyproject.toml`.

1. **`CHANGELOG.md`** au format *Keep a Changelog* (`Added` / `Changed` / `Fixed` / `Deprecated`),
   une entrée par version, la plus récente en haut, rétro-alimenté pour `v0.1.0` et `v0.2.0`.
   Discipline reprise de `svy` (§12.A) : **tout écart numérique constaté face à une référence est
   chiffré** dans l'entrée, jamais résumé par « corrigé ».
2. **`README.md`** — ajouts obligatoires, chacun réclamé par une section antérieure :
   - la convention des seuils `k` **en fractions et non en pourcentages**, avec la correspondance
     `mpitb` (`c(20, 33)` → `k=[0.20, 0.33]`) — §12.B.4 ;
   - un tableau des trois familles de design et de quand utiliser chacune ;
   - la note sur `lonely_psu="fail"` qui **ne lève pas** d'exception, contrairement à R `survey` ;
   - le tableau de lecture d'un fichier de poids de réplicat institutionnel (§14.5c) ;
   - le chiffre de gain de performance mesuré, avec sa date, sa machine et ses versions (§14.9) ;
   - l'attribution : Alkire & Foster (2011), Suppa (2023) pour `mpitb`, Lumley pour `survey`.
3. **CI** — `.github/workflows/tests.yml` : matrice Python 3.10 / 3.11 / 3.12 sur
   `ubuntu-latest`, plus un travail `windows-latest` en 3.12 (c'est la plateforme de
   développement) ; étapes `pip install -e .[test]`, `ruff check`, `pytest`. Les tests marqués
   `slow` ne tournent que sur la branche `main` et sur les tags.
4. **Lint** — `ruff` ajouté à l'extra `test`, configuré dans `pyproject.toml` :
   `line-length = 96`, `target-version = "py310"`, règles `["E", "F", "I", "UP", "B"]`. Corriger
   le code existant si nécessaire ; ne pas désactiver une règle pour éviter de corriger.
5. **`docs/quickstart.md`** : le chemin le plus court du DataFrame au tableau de résultats, en
   moins d'une page, plus un exemple par famille de design.
6. **`afmpi[report]`** (§12.C) reste **hors périmètre** : ne pas créer cet extra.

---

### 14.12 — Republication

1. Version : `pyproject.toml` **et** `afmpi.__version__` mis à jour ensemble (ils sont déjà
   synchronisés à `0.2.0` — un test de cohérence entre les deux serait bienvenu dans
   `test_specification.py` ou un `test_packaging.py`).
2. Numérotation : `0.3.0` si les phases 4a-6b sont livrées, `0.4.0` en ajoutant 7-9, `1.0.0`
   seulement une fois la suite de conformité (phase 10) verte sur **toutes** les familles de
   design — pas avant, parce que `1.0.0` est un engagement de stabilité d'API et que c'est
   précisément le reproche fait à `svy` au §12.A.
3. Publication : `git tag -a vX.Y.Z`, `git push origin main --tags` sur `cae-ins/afmpi`, qui
   **existe déjà** — aucune création de dépôt, jamais.
4. **PyPI reste un jalon distinct**, sur confirmation explicite de l'utilisateur à chaque
   publication (§3 : « pas un blanc-seing permanent »). Ne pas publier sur PyPI de sa propre
   initiative, même si toutes les phases sont vertes.

---

### 14.13 — Ce qui reste ouvert après cette passe

Un seul point, et il ne peut pas être tranché par un agent :

- **Jeux de données `mpitb` de référence publiquement rejouables** (§11). Dépend d'une
  disponibilité externe et éventuellement d'une licence Stata. §14.10 le contourne : la suite de
  conformité repose sur des jeux synthétiques et des références figées, la comparaison à `mpitb`
  est optionnelle et sautée si le fichier manque. **Aucune phase n'est bloquée par ce point.**

Tout le reste des points ouverts antérieurs a été tranché : API objets vs fonctionnelle (§6),
méthodes namespacées (§12.C), noms français vs anglais (§12.C), adaptateur `vecteur_z` (§11),
`backend=` et `missing=` sur `estimate()` (§14.0.C), tolérances de conformité (§14.10), cible de
performance chiffrée (§14.9), construction de la matrice de Hadamard (§14.5b), règle de fusion de
`"collapse"` (§14.4c), interprétation du `fpc` (§14.4a), estimateur PPS par défaut (§14.4b) et
règle des degrés de liberté par cas (§14.7).

### 14.14 — Cycle de durcissement (hardening) v1.2

**Contexte, tranché ici** : entre `v1.0.0` et `v1.1.1`, trois audits indépendants successifs
(deux internes à l'orchestration, un par Claude Opus 5 sans contexte du projet) ont chacun trouvé
au moins un écart réel non détecté par la suite de tests existante — un chemin lazy/streaming qui
ne reproduisait pas la parité annoncée (`v1.0.1`), des chiffres de benchmark fabriqués par l'agent
producteur (`v1.1.0`), et un bug statistique confirmé (`vcov()` doublé sur PPS sans remise,
`v1.1.1`) qui avait échappé à la suite de conformité parce qu'elle ne couvrait pas cette branche.
Le diagnostic de l'utilisateur (2026-09-01) : la fonctionnalité statistique est maintenant large et
correcte, mais **l'investissement qui rapporte le plus n'est plus d'ajouter une fonction, c'est
d'essayer activement de casser le paquet**. Cette section fixe le périmètre de ce cycle avant de le
lancer — **aucune nouvelle fonctionnalité statistique n'est prévue dans ce cycle**, seulement du
durcissement, de la mesure fiable, et de la validation adversariale.

#### A. Invariants statistiques génériques, pas par famille

Le trou qui a laissé passer le bug PPS de `v1.1.1` : `diag(vcov()) == se()²` était déjà testé pour
`taylor`/`replication`/`census`, pas pour `pps` — quatre tests séparés au lieu d'un test générique.
**Fichier** : `tests/test_invariants_generic.py` (nouveau, distinct de `tests/test_invariants.py`
qui reste dédié aux identités AF). Paramétrise sur les designs déjà déclarés dans
`tests/test_invariants.py` (`DESIGNS`, 18 configurations couvrant phases 4a-9) et vérifie, pour
chacun sans exception :
- `diag(vcov()) == se()²` (le trou qui a laissé passer `v1.1.1`) ;
- `M0 == H * A` ;
- `Σ actbⱼ == M0`, `Σ pctbⱼ == 1` (si `M0 > 0`) ;
- `Σ φˡ·M0ˡ == M0` (décomposition) ;
- `Σ pctb_dim_d == 1`, `Σ_{j∈d} pctbⱼ == pctb_dim_d`.

Un futur chemin de variance (nouvelle méthode PPS, nouveau design) ne doit pas pouvoir passer les
tests sans passer par ce fichier — c'est la garantie structurelle qui manquait.

#### B. Matrice systématique eager × lazy × R, pas des cas ponctuels

Les vérifications de parité de `v1.1.0`/`v1.1.1` (missing policies, domaine, FPC, PPS,
`ReplicateDesign`) ont été écrites au cas par cas, par l'orchestrateur, après coup. **Fichier** :
`tests/test_parity_matrix.py` (nouveau). Produit cartésien systématique, pas exhaustif au sens
combinatoire strict mais couvrant chaque axe croisé au moins une fois : design (`SurveyDesign`
simple/stratifié/multi-degrés/PPS/FPC, `ReplicateDesign` des 6 méthodes, `CensusDesign`) ×
politique de valeurs manquantes (les 4) × présence de domaine × présence de `over` × chemin
(`memory`/`lazy`/`streaming`). Sur chaque cellule où une référence R existe déjà
(`tests/test_conformity/reference/`), compare aussi contre R. Un test générateur (pas 200 tests
écrits à la main) qui construit les cas et vérifie
$\hat\theta_R \approx \hat\theta_{eager} \approx \hat\theta_{streaming}$ et
$SE_R \approx SE_{eager} \approx SE_{streaming}$, tolérances identiques à §14.10.

#### C. Property-based testing

**Fichier** : `tests/test_properties.py` (nouveau), bibliothèque `hypothesis`, ajoutée aux
dépendances de test (`pyproject.toml`, extra `test`). Génère des jeux de données synthétiques
aléatoires (nombre de strates, de PSU par strate, d'indicateurs, poids, valeurs manquantes) et
vérifie les mêmes invariants que §14.14.A sur chaque tirage — pas pour remplacer les tests
déterministes existants, pour trouver des cas limites qu'un humain n'écrirait pas.

#### D. Mesure RAM réelle (le point que l'utilisateur et l'évaluation Opus 5 jugent le plus faible)

Constat partagé : `ExecutionConfig(memory_limit=...)` reste un no-op documenté, et la mesure de
RAM des benchmarks 30M/50M (`isolated_process=True`) suit le process **parent**, pas l'**enfant**
où le calcul a lieu — chiffre actuellement sans signification physique. Le test 10M lui-même ne
mesure qu'un delta avant/après (`mem_after - mem_before`), pas un vrai pic
$\max_t \mathrm{RSS}(t)$ : un pic transitoire entre les deux mesures est invisible.

**Fichier** : `src/afmpi/_rss_monitor.py` (nouveau, interne). Pour le chemin `isolated_process`,
fait remonter du sous-processus enfant un échantillonnage périodique de son propre RSS (thread
dédié dans l'enfant, `resource.getrusage`/`psutil.Process().memory_info().rss` toutes les
~50-100ms, pic retenu) transmis au parent avec le résultat via le protocole pickle déjà en place.
Pour le chemin in-process (`isolated_process=False`), même échantillonnage dans un thread du
process courant. Le rapport de benchmark expose : `baseline_rss`, `peak_rss`, `incremental_peak`,
`elapsed`, `threads_observed`, et si simple à obtenir, un compteur d'E/S disque. Documente
honnêtement le coût de l'échantillonnage lui-même (a un coût CPU non nul, à mesurer).

`memory_limit`/`spill_dir` : soit une implémentation réelle si l'API Polars installée le permet
(vérifier la version exacte au moment de ce stamp — l'API de streaming de Polars évolue vite),
soit **acter explicitement dans le README que ce sont des limitations permanentes de conception**
plutôt que des "pas encore" indéfinis — l'un ou l'autre, mais pas laisser la question ouverte
indéfiniment.

#### E. Benchmark reproductible et machine-lisible, avec variation du nombre de threads

**Fichier** : `benchmarks/report.py` (nouveau) qui exécute les benchmarks 10M/30M/50M avec
`ExecutionConfig(max_threads=N, isolated_process=True)` pour `N ∈ {4, 8, 16}` (adapter à ce que la
machine réelle permet) et produit un JSON structuré (une ligne par combinaison échelle × threads :
temps, pic RSS réel via §14.14.D, threads observés) plutôt que des lignes de log à copier-coller
dans le README à la main — c'est ce qui a permis les chiffres fabriqués de `v1.1.0` de passer
inaperçus un temps. Le README/CHANGELOG citent ce rapport plutôt que des chiffres recopiés. Si le
temps le permet, un jeu de données administratif ou de recensement réel (dépersonnalisé,
publiquement disponible) en complément du synthétique — sinon, documenter que ce n'est pas fait
et pourquoi.

#### F. Audit adversarial

Déjà amorcé (Opus 5, 2026-09-01, sans contexte du projet, a trouvé le bug de §14.14 avant même que
cette section existe). **Ce cycle formalise la pratique** : à la fin de ce stamp de durcissement,
un nouvel audit indépendant (agent sans contexte de la session qui l'a produit, instruit à vérifier
empiriquement plutôt qu'à faire confiance à la documentation) doit être relancé sur le résultat.
Si cet audit ne trouve plus de bug statistique confirmé (des remarques de style/documentation
restent acceptables), le cycle de durcissement peut être considéré clos et `v1.2.0` publiée.

#### Hors périmètre de ce cycle

Aucune nouvelle famille de design, aucune nouvelle méthode statistique, aucun nouveau backend
d'entrée/sortie. Si un audit en trouve le besoin en cours de route, ouvrir une section `14.15`
séparée plutôt que d'élargir celle-ci après coup.

---

## 15. Relecture de code du noyau v1 et jalon 3.5 (utilisateur, 2026-08-30)

Après la livraison du noyau v1 (phases 0-3, tag `v0.2.0`, 104/104 tests), l'utilisateur a relu le
code réellement produit — pas seulement le plan — et formulé un constat et une recommandation
avant d'aborder les phases 4a+. Le jalon de conformité qui en résulte est déjà intégré au
phasage (§9, phase 3.5) ; les deux limitations techniques identifiées sont déjà intégrées au §7.
Cette section documente le raisonnement et le verdict, pour l'audit.

### A. Deux limitations concrètes du code livré (déjà répercutées en §7)

1. **Le noyau v1 n'est pas encore « big data », il en a l'architecture** — distinction à ne pas
   confondre : `EstimationResult` retient actuellement toute la `DeprivationMatrix` matérialisée
   (nécessaire à `domain()`/`scores()` après coup), et `estimate()` n'accepte pas encore de
   `LazyFrame`. Correct et voulu à cette échelle (v1 = enquêtes de taille normale) ; à traiter
   explicitement en phase 9, pas en corrigeant discrètement le noyau plus tard.
2. **Le calcul multi-`k` × multi-désagrégation refait une agrégation complète par combinaison** —
   sans conséquence sur l'EHCVM, potentiellement coûteux sur un recensement (8 seuils × 3 niveaux
   de désagrégation = de nombreux scans complets). À compiler en un plan Polars unique en phase 9.

### B. Où se situe `afmpi` aujourd'hui, selon l'utilisateur

> « Si je compare ce qui existe réellement maintenant : mpitb/mpitbR > afmpi 0.2 en couverture
> méthodologique totale — normal à 3/12. Mais pour la qualité du socle Python, je dirais déjà :
> afmpi est désormais crédible, et beaucoup plus crédible que le mpitb Python disponible sur
> PyPI. [...] Le point qui me rend plutôt confiant est que les trois premières phases ont traité
> les fondations difficiles — estimands génériques, influence functions, séparation
> Taylor/réplication, domaines — au lieu de simplement accumuler des fonctionnalités. »

Notation par axe (utilisateur, 2026-08-30, sur le code réellement livré des phases 0-3, pas sur
le plan) :

| Axe | Note |
|---|---|
| Formules AF | 9,5/10 |
| Architecture interne | 9,5/10 |
| Linéarisation | 9/10 |
| Plan à un degré | 8,5/10 |
| Domaines | 9,5/10 |
| Tests unitaires/mathématiques | 9,5/10 |
| Validation externe | 5/10 |
| Couverture des plans complexes | 5/10 |
| Big data effectivement disponible | 3/10 |
| Préparation architecturale big data | 9/10 |

Les notes faibles (validation externe, plans complexes, big data opérationnel) sont **attendues**
à ce stade (3 phases sur 12) — elles ne mesurent pas un défaut, seulement ce qui n'est pas encore
construit. C'est exactement le jalon 3.5 (§9) qui doit faire remonter « validation externe »
avant que les phases 4a+ ne s'appuient dessus.

### C. Recommandation adoptée

Ne pas changer la feuille de route générale (§9) ; insérer le jalon de conformité 3.5 avant la
phase 4a (fait, §9) : `survey` (R) comme oracle sur le noyau actuel, CI GitHub automatique, rejet
explicite des PSU/strates manquants, validation des trois subtilités `degf()` sous domaine,
bornes de l'IC `logit`, et politique `missing` par défaut. Une fois ce jalon passé, le noyau 0-3
est gelé méthodologiquement et les phases 4a+ (multi-degrés, FPC, PPS, réplications) peuvent
s'appuyer dessus avec confiance plutôt que de risquer de propager un défaut non détecté.

## 16. Stamp 4.5 — durcissement 4a-4c et rattrapage du jalon 3.5 (agy, 2026-08-30)

Le jalon 3.5 (§9, §15) n'a en réalité jamais été exécuté : le commit `ebaa089` l'a seulement
*ajouté au plan*, puis les phases 4a/4b/4c ont été livrées par-dessus (`de99e9c`, tag `v0.3.0`,
123/123 tests) sans que le noyau ait été gelé méthodologiquement. Une relecture du code réel de
4a-4c (pas seulement du plan) fait remonter huit lacunes concrètes, vérifiées en lisant le code
(pas seulement affirmées) :

1. **Aucun oracle externe** : `survey` (R) n'a jamais été exécuté contre le noyau, ni contre
   4a-4c. C'est le point manquant le plus important (jalon 3.5, resté lettre morte).
2. **Aucune CI GitHub** : pas de `.github/`, aucun statut de contrôle sur les commits — 123/123
   tests locaux, zéro reproduction automatique (Python 3.10/3.11/3.12) à chaque push.
3. **Identifiants de strates/PSU manquants acceptés silencieusement** : `deprivation.py:273,278,
   294,301,306` fait `.fill_null("__afmpi_null__")` sur les colonnes strata/psu, y compris dans le
   nouveau chemin multi-stage — une PSU inconnue devient une vraie PSU nommée `__afmpi_null__` au
   lieu de lever une erreur. Contredit directement l'exigence du jalon 3.5.
4. **FPC manquant traité comme fraction nulle** : `deprivation.py:336` fait
   `.fill_null(0.0)` sur la colonne FPC — un FPC déclaré mais manquant pour une ligne doit lever
   une erreur (sauf option explicite), pas silencieusement valoir « pas de correction de
   population finie ».
5. **PPS avec remise n'utilise pas explicitement `pi`** : `variance.py:332` (`_pps_variance`),
   la branche `pps.method == "with_replacement"` retombe directement sur `multistage_variance(...,
   depth=1)` sans passer par les probabilités d'inclusion. Défendable seulement si les poids
   d'analyse encodent déjà complètement Hansen-Hurwitz — à clarifier/documenter explicitement,
   pas à laisser implicite alors que le commit revendique « estimateurs de Hansen-Hurwitz ».
6. **Sen-Yates-Grundy : appariement des PSU ambigu inter-strates** : `variance.py:380-385`
   récupère l'identifiant PSU via `c_id = row["__psu_str"].split("|")[-1]` puis l'apparie dans
   `joint_probability`, qui n'est indexé que par `psu_a`/`psu_b`/`pi_ab` — si deux strates
   différentes ont chacune une « PSU 1 »/« PSU 2 » avec des `pi_ij` différentes, l'appariement est
   ambigu. Corriger en indexant `joint_probability` par `stratum, psu_a, psu_b, pi_ab`, ou en
   imposant des identifiants PSU globalement uniques (préférer la première option).
   Concerne aussi Hájek (`variance.py:401`).
7. **Les tests « hand-calculated » ne vérifient pas de valeur calculée à la main** : dans
   `tests/test_multistage.py` (`test_hand_calculated_2stage_example`, lignes 90-139),
   `tests/test_pps.py` (`test_sen_yates_grundy_hand_calculated` et le test Hájek, lignes 50-139),
   l'assertion finale est `assert m0_row["se"] > 0` — une formule fausse de 20 % passerait ces
   tests sans échouer. Le nom du test promet une comparaison à une valeur exacte (10⁻¹⁰ ou
   10⁻¹² près) qui n'existe pas dans le corps du test. `tests/test_lonely_psu.py` et
   `tests/test_domain.py` ont le même défaut ponctuellement mais sont moins critiques (4c est
   déjà mieux couvert par ailleurs — voir tableau ci-dessous).
8. **Documentation publique en retard sur le code livré** : `README.md:138,151-152` annonce
   encore la version `0.2.0` et dit explicitement non implémentés les plans multi-degrés, FPC,
   PPS et grappes isolées — alors que `de99e9c`/tag `v0.3.0` les a livrés. À resynchroniser.

### Notation actualisée à 4c (agy, sur le code réel, pas le plan)

| Axe | Phase 3 (§15) | Phase 4c actuelle |
|---|---|---|
| AF ponctuel H/A/M0/contributions | 9,5 | 9,5 |
| Architecture interne | 9,5 | 9,5 |
| Taylor 1 degré | 8,5 | 9 |
| Domaines | 9,5 | 9,5 |
| Multi-stage (formule) | 0 | 7,5 |
| FPC | 0 | 7,5 |
| PPS (WR, WOR/Hájek, SYG) | 0 | 6,5 |
| PSU isolé (5 comportements) | 0 | 8,5 |
| Tests internes | 9,5 | 9 |
| Validation externe | 5 | 5 |
| CI/reproductibilité | 3 | 3 |
| Big data opérationnel | 3 | 3 |
| Préparation architecturale big data | 9 | 9 |

La légère baisse de « tests internes » ne signifie pas une régression : la complexité
méthodologique (multi-stage, PPS) a augmenté plus vite que la profondeur des tests qui la couvrent.

### Décision : stamp 4.5 avant 5a

**Ne pas commencer 5a (réplication) avant d'avoir traité les huit points ci-dessus.** Objectif du
stamp 4.5 : que 0-4c devienne un socle *survey* réellement gelé méthodologiquement — pas
seulement architecturalement solide — avant d'y adosser les deux branches d'inférence
(linéarisation Taylor déjà là, réplication à venir en 5a-5c). Portée du stamp 4.5, dans l'ordre :

1. Oracle `survey` (R) : comparaison H/A/M0 **et** SE/IC/`degf()` sur multi-stage + FPC, avec au
   moins un exemple à deux degrés dont `Var(H)`, `Var(A)`, `Var(M0)` sont connues à 10⁻¹⁰ près.
2. Même oracle pour SYG et Hájek (PPS WOR) — pas seulement l'invariant algébrique
   `pi_ij = pi_i * pi_j ⇒ V=0`, qui n'est qu'un cas dégénéré, pas une validation générale.
3. Clarifier/documenter (ou corriger si besoin) le chemin PPS avec remise : soit prouver que les
   poids d'analyse encodent bien Hansen-Hurwitz, soit faire passer `pi` explicitement dans le
   calcul de variance.
4. Corriger l'appariement `joint_probability` du SYG pour qu'il soit non ambigu inter-strates
   (indexer par `stratum, psu_a, psu_b, pi_ab`).
5. `missing_design="error"` par défaut : rejeter (erreur explicite) les strates/PSU/FPC manquants
   au lieu de `fill_null`, avec une option explicite pour un traitement différent si un jour
   nécessaire.
6. Ajouter la CI GitHub (`.github/workflows/`) : `pytest` sur Python 3.10/3.11/3.12 à chaque
   push/PR — ne pas la reporter à la phase 11.
7. Remplacer les assertions `se > 0` des tests « hand-calculated » par de vraies égalités
   numériques (tolérance 10⁻⁸ à 10⁻¹⁰) dans `test_multistage.py`, `test_pps.py`, et par extension
   `test_lonely_psu.py`/`test_domain.py` où le nom du test promet une valeur exacte.
8. Resynchroniser `README.md` et l'en-tête de `PLAN.md` sur l'état réel (`v0.3.0`, 4a-4c livrés).

**Si ces huit points passent** : 0-4c est un socle *survey* gelé méthodologiquement, et 5a-5c
(réplication) peut s'appuyer dessus avec confiance — les deux grandes branches d'inférence
(Taylor et réplication) reposeront alors sur un estimateur et un chemin déjà audités.

### D. Exécution et contrôle indépendant (Claude, 2026-08-30)

`agy` (`gemini-3.6-flash-high`) a livré les huit points, rapport final « aucun écart ». L'orchestrateur
a vérifié chaque affirmation en ré-exécutant lui-même les scripts (pas en relisant seulement le
rapport) — conformément à la consigne : les conclusions déléguées sont des hypothèses à vérifier,
pas des faits. Deux écarts trouvés au premier passage :

- **Oracle Hájek fabriqué** : `tests/oracle/README.md` et `test_hajek_reproduces_stratified_estimator`
  affirmaient des valeurs R identiques à un tout autre scénario (copier-coller), pas la sortie réelle
  de `pps_oracle.R`. Cause racine, trouvée par `agy` sur relance ciblée : le script R oracle omettait
  `fpc = ~pi` dans `svydesign(..., pps = "brewer")`, ce qui fait retomber R silencieusement sur un plan
  à un degré avec remise au lieu du Hájek voulu. Une fois corrigé, R reproduit `afmpi` à 14 décimales
  près — le code Python n'avait pas de bug, seul le script d'oracle était mal formé.
- **Test SYG multi-strates non discriminant** : `test_syg_with_duplicate_psu_names_across_strata`
  (le test cité par le rapport comme confirmant `M0 SE = 0.19837301190397` contre R) n'assertait en
  réalité que `se is not None` — retombée du même défaut que le point 7 était censé éliminer. Corrigé
  directement par l'orchestrateur (sans repasser par `agy`) en assertant la valeur exacte, vérifiée
  indépendamment en exécutant `afmpi` sur ce design.

127/127 tests après correction. Leçon pour les stamps suivants : un rapport « aucun écart » d'un
agent délégué n'est une preuve que si l'orchestrateur a réellement rejoué au moins les affirmations
numériques centrales, pas seulement relu le code produit.

## 17. Stamp 3.5-bis — oracle `survey` (R) sur le noyau de base (2026-08-30)

Le stamp 4.5 (§16) a créé des oracles R pour le multi-degrés+FPC et le PPS (4a/4b/4c), mais **pas**
pour le périmètre originel de la phase 3.5 (§15) : SRS, stratifié simple, un degré de grappes, et
domaines — le noyau des phases 0-3 (`v0.2.0`) sur lequel tout le reste (4a-4c, et bientôt 5a-7)
s'appuie. Ce noyau n'a donc, à ce jour, **jamais** été comparé à un oracle externe. Les trois
subtilités listées par 3.5 (`degf()` sous domaine, bornes de l'IC `logit`, politique `missing` par
défaut) sont en fait déjà testées depuis `v0.2.0` (`ec0c75c`, avant même que 3.5 soit proposée) —
seul l'oracle R manque réellement.

**Portée de ce stamp** : un script `tests/oracle/core_oracle.R` (même convention que
`multistage_oracle.R`/`pps_oracle.R`, `tests/oracle/README.md` mis à jour) qui compare `afmpi` à
`survey` (R) sur, au minimum :

1. Un design SRS simple (pas de strate, pas de grappe déclarée — chaque ligne sa propre grappe) :
   `H`, `A`, `M0`, SE, IC (`logit` et `normal`/`t`), `degf()`.
2. Un design stratifié simple à un degré (strates + PSU, plusieurs strates, tailles inégales) :
   mêmes quantités.
3. Un domaine (`subset()` en R) sur le design stratifié ci-dessus : mêmes quantités, en vérifiant
   spécifiquement que `degf()` compte les grappes/strates que le domaine atteint réellement (pas
   celles du design complet) — c'est le point que `test_domain.py:113/117` teste déjà en interne,
   mais sans comparaison à R.
4. Un cas aux bornes pour l'IC `logit` (`H` proche de 0 ou de 1) pour confirmer que R et `afmpi`
   s'accordent sur le comportement (`normal`/`t` peuvent sortir de `[0,1]`, `logit` non).

Remplacer les assertions non discriminantes restantes (s'il y en a, sur ce périmètre précis) par
des égalités numériques à 10⁻¹⁰ près contre les valeurs R, dans le même style que le stamp 4.5.

**Une fois ce stamp passé** : le noyau 0-3 est enfin gelé méthodologiquement contre un oracle
externe — la phase 3.5 (§9, §15) est alors réellement close, pas seulement par ricochet via 4.5.

## 18. ✅ Stamp — oracle `survey` (R) pour les phases 5-7 (fait, 2026-08-31, agy gemini-3.6, 211/211 tests)

Relecture externe (`agy`, 2026-08-31, sur le code réel de `main` après la phase 7) : l'oracle R
(`tests/oracle/`) ne couvre que le noyau (§17) et 4a-4c (§16) — pas les méthodes de réplication
(5a-5c), les panels (6b), ni VCOV/Wald (7). Ces phases ne sont validées qu'en interne (identités
algébriques, calculs à la main, convergence bootstrap vs Taylor à 2%). C'est la lacune de rigueur
la plus importante avant la phase 9, et le principal écart restant entre `afmpi` et `mpitbR` en
maturité de validation.

**Stratégie normative — ne pas essayer de reproduire les tirages aléatoires de R** : pour JK1,
JKn, BRR, Fay BRR, ne pas générer indépendamment des poids de réplicat côté R et côté `afmpi` en
espérant qu'ils coïncident (l'ordre/l'algorithme de génération n'ont aucune raison d'être
identiques). À la place : générer les poids de réplicat avec `afmpi`
(`generate_replicate_weights`), les exporter (CSV ou `.dta`), les réimporter dans un
`svrepdesign(repweights=..., type=..., combined.weights=TRUE, scale=..., rscales=...)` construit
à la main en R avec le MÊME `scale`/`rscales` qu'`afmpi` a produits, puis comparer `SE(svymean())`/
`SE(svyratio())` entre les deux moteurs sur les MÊMES poids. C'est un test de la formule de
variance de réplicat, pas de l'algorithme de tirage — c'est ce qui est faisable et ce qui compte
méthodologiquement (l'algorithme de tirage bootstrap est déjà validé différemment, par
convergence, §14.5c test #2).

Pour bootstrap et SDR (pas de tirage à faire coïncider non plus, et SDR n'a pas d'équivalent
direct dans `survey`) : même stratégie — poids générés par `afmpi`, réimportés dans
`svrepdesign(..., type="other", combined.weights=TRUE, scale=..., rscales=...)` (le type `"other"`
de `survey` accepte des poids de réplicat arbitraires avec un `scale`/`rscales` fournis), comparer
la SE obtenue par les deux moteurs sur les mêmes poids.

Pour les panels (6b) et VCOV/Wald (7), R `survey` n'a pas de fonction dédiée équivalente à
`changes()`/`test()` : construire l'oracle par décomposition manuelle — deux `svydesign`/
`svrepdesign` (un par vague ou un par sous-groupe), extraire les composantes de `vcov()` en R
(`vcov(svymean(...))` donne déjà la matrice complète, y compris les termes hors diagonale entre
domaines si on empile les indicatrices dans une seule formule `svymean(~poor_A + poor_B, ...)` —
c'est exactement ce qui donne `V_ab` en R sans fonction dédiée), et reconstruire à la main
`Var(Δ)`/la statistique de Wald à partir de ces composantes, pour comparaison à `afmpi`.

**Portée** :
1. `tests/oracle/replicate_oracle.R` : JK1, JKn, BRR, Fay BRR — poids exportés depuis `afmpi`,
   réimportés dans `svrepdesign`, comparaison SE à 10⁻⁸ près minimum (le passage par deux moteurs
   flottants différents peut perdre un peu de précision par rapport aux 10⁻¹⁰ du noyau — documenter
   la tolérance réellement atteinte, ne pas forcer 10⁻¹⁰ si ce n'est pas honnête).
2. `tests/oracle/bootstrap_sdr_oracle.R` : bootstrap et SDR, même stratégie (poids `afmpi`
   réimportés dans `svrepdesign(type="other", ...)`).
3. `tests/oracle/panel_oracle.R` : un cas panel parfait et un cas de recouvrement partiel,
   `vcov(svymean(~poor_t0 + poor_t1, ...))` empilé pour obtenir `Cov(θ̂_t1, θ̂_t0)`, comparaison à
   `Var(Δ)` d'`afmpi`.
4. `tests/oracle/vcov_wald_oracle.R` : `vcov(svymean(~poor_A + poor_B, ...))` empilé pour
   `V_aa`/`V_bb`/`V_ab`, comparaison à `afmpi.vcov()`, et reconstruction manuelle de la statistique
   de Wald pour comparaison à `afmpi.test()`.
5. Tests Python correspondants (`tests/test_replicate.py`, `tests/test_panel.py`,
   `tests/test_vcov.py`/`tests/test_hypothesis.py` — étendre les fichiers existants plutôt qu'en
   créer de nouveaux) avec les valeurs réellement obtenues de R, jamais devinées (même piège que
   le stamp 4.5, §16.D — l'orchestrateur re-exécutera les scripts R lui-même avant d'accepter).
6. `tests/oracle/README.md` : section 4, même format que les sections 1-3 existantes.

**Si ce stamp passe** : les phases 0-7 sont validées contre `survey` (R) dans leur intégralité —
plus seulement le noyau et 4a-4c. C'est le socle sur lequel la phase 9 (recensement) doit
s'appuyer sans jamais avoir à revisiter une formule de variance.

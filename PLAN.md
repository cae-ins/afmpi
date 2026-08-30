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

Concevoir puis implémenter `afmpi`, un package Python **générique** (pas spécifique à la Côte
d'Ivoire ni à l'EHCVM) pour calculer et analyser des indices de pauvreté multidimensionnelle par
la méthode Alkire-Foster, avec une robustesse comparable à `mpitb`/`mpitbR` : plan de sondage,
intervalles de confiance, décomposition, robustesse à k, évolution dans le temps.

**Ambition explicite (pas seulement la parité)** : `afmpi` doit être **meilleur** que
`mpitb`/`mpitbR` et que tout équivalent existant, sur n'importe quelle plateforme — en
particulier sur le passage à l'échelle (données de recensement, potentiellement des dizaines de
millions d'individus). Voir §7 pour l'exigence de performance détaillée (backend Polars, E/S
parquet, benchmarks chiffrés) : ce n'est pas une optimisation optionnelle ajoutée après coup,
c'est un critère de réussite du projet au même titre que l'exactitude numérique.

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
- **Séquencement** : publier une coquille vide n'aurait pas de sens — le dépôt `cae-ins/afmpi`
  n'est créé qu'après que le socle (§9, phase 1 au minimum) est implémenté, testé, et validé
  contre `PythonIPM` (§8). La publication PyPI, elle, reste un jalon ultérieur distinct, sur
  nouvelle confirmation explicite de l'utilisateur (pas incluse dans l'autorisation ci-dessus).

## 4. Ce que le package doit reproduire (checklist de parité fonctionnelle)

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

## 5. Architecture proposée

```
afmpi/
├── pyproject.toml
├── README.md
├── PLAN.md                    (ce document)
├── src/afmpi/
│   ├── __init__.py             exporte l'API publique
│   ├── backend.py               ingestion pandas -> Polars via Arrow (§7 ; pas de narwhals)
│   ├── io.py                    lecture/écriture parquet (streaming), .dta en export seulement
│   ├── specification.py        Specification : dimensions, indicateurs, poids
│   ├── survey_design.py        SurveyDesign : poids, psu, strates
│   ├── estimation.py           estimate() -> EstimationResult ; censure, H/A/M0, hd/hdk
│   │                            (calcul Polars natif, lazy par défaut — voir §7)
│   ├── contributions.py        actb, pctb, décomposition par dimension
│   ├── decomposition.py        désagrégation par sous-groupe (`over`), vérif décomposabilité
│   ├── robustness.py           robustesse à k (klist), éventuellement à d'autres choix
│   ├── variance.py             les DEUX méthodes d'IC (ultimate cluster tronqué, logit svyciprop)
│   ├── change_over_time.py     comparaison inter-vagues (absolu, relatif, annualisé)
│   └── results.py              EstimationResult : coef(), confint(), summary(), to_frame()
├── tests/
│   ├── test_estimation.py      cas construits à la main (répliquer les auto-contrôles de
│   │                            PythonIPM/pipeline/*.py --check, mêmes valeurs attendues)
│   ├── test_against_mpitb.py   comparaison numérique aux exemples officiels mpitb (voir §8)
│   ├── test_against_pythonipm.py  comparaison aux résultats réels EHCVM 2021 de PythonIPM
│   │                            (H=62,5 %, A=0,502, M0=0,314 avec NEET 16-35 — à figer une
│   │                            fois PythonIPM stabilisé, en tolérance stricte 1e-6)
│   ├── test_performance_scale.py  benchmarks §7 : jeu synthétique à l'échelle recensement,
│   │                            cibles de temps/mémoire, comparaison au backend pandas naïf
│   └── data/                   petits jeux de données synthétiques, pas de données EHCVM réelles
└── docs/
    └── quickstart.md
```

## 6. Esquisse de l'API publique

```python
import afmpi
import pandas as pd

spec = afmpi.Specification()
spec.set(
    dimensions={
        "education": ["d_educ_years", "d_educ_attend"],
        "health":    ["d_nutrition", "d_child_mortality"],
        "living":    ["d_electricity", "d_water", "d_sanitation", "d_housing"],
    },
    weights="equal_nested",   # ou un dict explicite {dimension: poids, ...}
)

design = afmpi.SurveyDesign(weights="hh_weight", psu="cluster_id", strata="stratum_id")

resultat = afmpi.estimate(
    df=df,                     # pandas.DataFrame OU polars.DataFrame/LazyFrame — indicateurs
                                # 0/1 (g0) + colonnes techniques (voir §7, compatibilité d'entrée)
    spec=spec,
    design=design,
    k=[0.20, 1/3, 0.50],       # plusieurs seuils -> tableau de robustesse automatique
    over=["region", "milieu"], # désagrégations, autant que voulu
    ci_method="logit",         # ou "ultimate_cluster"
    backend="polars",          # défaut ; "pandas" en repli (plus lent, documenté comme tel)
    lazy=False,                # True -> renvoie un plan de calcul non exécuté, .collect() pour lancer
)

resultat.coef()                # H, A, M0 ponctuels, par k et par sous-groupe
resultat.confint()             # IC
resultat.contributions()       # hd, hdk, actb, pctb par indicateur
resultat.summary()             # tableau formaté, façon mpitb
resultat.to_frame()            # DataFrame plat, pour export Excel/CSV (même type que l'entrée)

# lecture directe depuis un fichier recensement en parquet, en streaming — §7
lazy_result = afmpi.from_parquet("recensement_2026.parquet", streaming=True) \
                    .estimate(spec=spec, design=design, over=["region"], lazy=True)
resultat = lazy_result.collect()
```

Point de design encore ouvert :
- API orientée objets (`Specification`, `SurveyDesign`, `EstimationResult`) vs fonctionnelle pure
  (fonctions + dataclasses immuables) — privilégier ce qui teste le plus facilement.

**Tranché en revue (`agy`, 2026-08-30) : pas de dépendance à `samplics`.** Réimplémentation
native en Polars de la variance de plan de sondage (linéarisation par grappe, méthode *ultimate
cluster*) — `samplics` impose une structure pandas, alourdit le graphe de dépendances, et bride
le multi-threading de Polars. La linéarisation par grappe s'écrit en moins de 150 lignes
d'expressions Polars (`pl.Expr`) à haute performance ; `PythonIPM/pipeline/05_indices_ipm.py`
(fonction `ratio_et_ic`) en donne déjà la version pandas de référence à porter.

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

## 8. Stratégie de validation

Un package qui prétend la robustesse de `mpitb`/`mpitbR` doit être **vérifié contre eux**, pas
seulement testé unitairement :

1. **Jeux de données de référence OPHI** : `mpitb` est distribué avec des exemples (souvent basés
   sur des extraits DHS publics). Les récupérer (documentation `mpitb`/`mpitbR` sur CRAN/SSC),
   les rejouer dans `afmpi`, comparer H/A/M0/contributions aux valeurs publiées par `mpitb` à
   6 décimales.
2. **PythonIPM comme second cas réel** : une fois `PythonIPM` stabilisé (SU3/NEET/zone inclus),
   ses résultats EHCVM 2021 (`PythonIPM/sorties/csv/indices_ipm_ci.csv`) servent de référence
   indépendante — deux implémentations distinctes (l'une à la main, l'autre via `afmpi`) doivent
   converger à 1e-6 près sur les mêmes données d'entrée.
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

1. **Socle** — périmètre précisé en revue (`agy`, 2026-08-30, voir §10) :
   - Modules : `specification.py`, `survey_design.py` (poids individuels/ménages uniquement, PAS
     encore grappes/strates — phase 2), `estimation.py` (cᵢ, cᵢ(k), H, A, M0, Hⱼ, CHⱼ, actbⱼ,
     pctbⱼ, en Polars in-memory, pour un seul k), `results.py` (`summary()`, `to_frame()`).
   - Entrées acceptées : `pandas.DataFrame` (converti via Arrow) ou `polars.DataFrame` — **Polars
     dès cette phase** (pas ajouté après coup : la logique de calcul doit être écrite
     polars-natif dès le départ, pas migrée plus tard), mais sans E/S parquet avancée ni mode
     streaming (ça, c'est la phase 4).
   - Tests : portage direct des jeux de données synthétiques d'auto-contrôle de
     `PythonIPM/pipeline/{01,02,05}_*.py --check` (résultats calculables à la main).
2. **Plan de sondage complet** : grappes/strates, les deux méthodes d'IC, tests contre un exemple
   `mpitb` officiel.
3. **Désagrégation et robustesse** : `over=[...]`, décomposabilité vérifiée par assertion,
   `klist` (robustesse à k).
4. **Performance et passage à l'échelle** (§7) : E/S parquet, mode streaming/lazy, jeu de données
   synthétique à l'échelle recensement, suite de benchmarks avec cibles chiffrées, comparaison
   mesurée à un équivalent pandas naïf.
5. **Évolution dans le temps** : `compare_over_time`, deltas absolus/relatifs/annualisés.
6. **Validation croisée finale** : comparaison chiffrée à `PythonIPM` sur l'EHCVM 2021 complet,
   rapport de conformité.
7. **Packaging** : `pyproject.toml`, README, docs, CI (tests + lint).
8. **Publication GitHub** : `git init`, commit initial, `gh repo create cae-ins/afmpi --public
   --source=. --push` (ou équivalent) — voir la contrainte de compte actif au §3. Pas de
   publication PyPI à ce stade : jalon distinct, sur nouvelle confirmation de l'utilisateur.

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

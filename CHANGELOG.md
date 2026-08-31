# Changelog

Toutes les modifications notables apportées à ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère à la gestion sémantique de version [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Conformément à la discipline méthodologique du projet, tout écart numérique constaté ou validé face aux références (Stata `mpitb`, R `survey`, calculs manuels) est explicitement chiffré dans chaque entrée.

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

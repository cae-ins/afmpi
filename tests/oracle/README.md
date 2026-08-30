# Oracle Validation Suite (R `survey` package)

This directory contains R validation scripts using R's academic-standard `survey` package (v4.5+) to serve as numeric oracles for `afmpi`'s design-based variance calculations.

## Requirements

- R 4.5.3 or later
- R package `survey` (v4.5+)

On Windows systems where `Rscript.exe` is not added to `%PATH%`, specify the full executable path:
`"C:\Program Files\R\R-4.5.3\bin\Rscript.exe"`

## Executing the Oracle Scripts

Run the scripts directly from the repository root:

```powershell
& "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tests/oracle/core_oracle.R
& "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tests/oracle/multistage_oracle.R
& "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tests/oracle/pps_oracle.R
```

## Covered Oracle Reference Values

### 1. Multi-Stage & FPC (`multistage_oracle.R`)

- **2-Stage Design (f1=0.5, f2=0.25)**:
  - $H = 0.75$, $Var(H) = 0.03125$ ($SE = 0.17677669529664$)
  - $M0 = 0.5625$, $Var(M0) = 0.02685546875 = 55/2048$ ($SE = 0.16387638252659$)
  - $A = 0.75$, $Var(A) = 0.016493055555556 = 119/7200$ ($SE = 0.12842529172852$)

- **2-Stage Design (f1=1.0, f2=0.5)** (Stage 1 census, only Stage 2 contributes):
  - $H = 0.75$, $Var(H) = 0.03125$ ($SE = 0.17677669529664$)
  - $M0 = 0.50$, $Var(M0) = 0.03125$ ($SE = 0.17677669529664$)
  - $A = 2/3$, $Var(A) = 0.0061728395061728 = 1/162$ ($SE = 0.078567420131839$)

### 2. PPS Designs (`pps_oracle.R`)

- **Sen-Yates-Grundy (SYG)**:
  - $H = 0.5$, $Var(H) = 0.083333333333333 = 1/12$ ($SE = 0.28867513459481$)
  - $M0 = 0.5$, $Var(M0) = 0.083333333333333 = 1/12$ ($SE = 0.28867513459481$)
  - $A = 1.0$, $Var(A) = 0.0$ ($SE = 0.0$)

- **Hájek (exact formula)**:
  - $H = 0.75$, $Var(H)_{Hajek} = 0.03125$ ($SE = 0.17677669529664$)
  - $M0 = 0.50$, $Var(M0)_{Hajek} = 0.03125$ ($SE = 0.17677669529664$)
  - $A = 2/3$, $Var(A)_{Hajek} = 0.0061728395061728$ ($SE = 0.078567420131839$)

### 3. Core Survey Engine (`core_oracle.R`)

- **SRS Simple (no strata, no clusters)**:
  - $H = 0.86363636363636$, $Var(H) = 0.017366249522523$ ($SE = 0.13178106663145$)
  - $M0 = 0.48863636363636$, $Var(M0) = 0.0063322795812987$ ($SE = 0.079575621777644$)
  - $A = 0.56578947368421$, $Var(A) = 0.0014169270477838$ ($SE = 0.03764209143743$)
  - $degf = 9$
  - Logit IC for $H$: $[0.33503733422103, 0.9875946230251]$

- **Stratified Simple 1-Stage (3 strata, 8 PSUs)**:
  - $H = 0.88957055214724$, $Var(H) = 0.012212155224313$ ($SE = 0.11050862058823$)
  - $M0 = 0.49079754601227$, $Var(M0) = 0.0035609711124913$ ($SE = 0.059673872946972$)
  - $A = 0.55172413793103$, $Var(A) = 0.0007554596012366$ ($SE = 0.027485625356477$)
  - $degf = 5$ (8 PSUs - 3 Strata = 5)
  - Logit IC for $H$: $[0.30887194903561, 0.99316012399989]$

- **Domain (`subset()`) on Stratified Design (`LAYOUT`)**:
  - Whole design $degf = 3$ (6 PSUs - 3 Strata = 3)
  - Domain design $degf = 1$ (4 PSUs - 3 Strata = 1)
  - Domain $H = 0.856$, $Var(H) = 0.022204809216$ ($SE = 0.14901278205577$)
  - Domain $M0 = 0.45466666666667$, $Var(M0) = 0.0064920009133827$ ($SE = 0.080572953981983$)
  - Domain $A = 0.53115264797508$, $Var(A) = 0.00066850341186061$ ($SE = 0.025855432927348$)

- **Boundary Cases for Logit CI ($df = 4$)**:
  - Low $H = 0.1$ ($SE = 0.095916630466254$):
    - Logit IC: $[0.0057305652086456, 0.68173246012793]$ (delta-method `xlogit`: $[0.0057305648745028, 0.68173246548443]$)
    - Unbounded Student-t / Normal IC lower bound: $-0.1663072591651$ / $-0.087993141232296$ ($< 0$)
  - High $H = 0.9$ ($SE = 0.095916630466254$):
    - Logit IC: $[0.31826753987207, 0.99426943479135]$ (delta-method `xlogit`: $[0.31826753451557, 0.99426943512550]$)
    - Unbounded Student-t / Normal IC upper bound: $1.1663072591651$ / $1.0879931412323$ ($> 1$)

Python unit tests in `tests/test_core_oracle.py`, `tests/test_multistage.py` and `tests/test_pps.py` verify equality to these exact values within $10^{-10}$ tolerance.
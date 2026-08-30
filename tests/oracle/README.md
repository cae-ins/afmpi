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

Python unit tests in `tests/test_multistage.py` and `tests/test_pps.py` verify equality to these exact values within $10^{-10}$ tolerance.

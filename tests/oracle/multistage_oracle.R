# Oracle validation script using R 'survey' package (v4.5+)
# For afmpi stamp 4.5 (PLAN.md §16)
#
# Execution:
# "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tests/oracle/multistage_oracle.R

suppressPackageStartupMessages(library(survey))

options(digits = 14)

cat("=========================================================\n")
cat("afmpi Oracle Validation Script: Multi-stage & FPC (R survey)\n")
cat("=========================================================\n\n")

# -----------------------------------------------------------------------------
# Design 1: 2-stage design with FPC at stage 1 (f1=0.5) and stage 2 (f2=0.25)
# -----------------------------------------------------------------------------
# Stratum H1: 2 PSUs (P1_1, P1_2), 2 SSUs each
# Stratum H2: 2 PSUs (P2_1, P2_2), 2 SSUs each
df_2stage <- data.frame(
  h = c("H1", "H1", "H1", "H1", "H2", "H2", "H2", "H2"),
  psu = c("P1_1", "P1_1", "P1_2", "P1_2", "P2_1", "P2_1", "P2_2", "P2_2"),
  ssu = c("S1_1_1", "S1_1_2", "S1_2_1", "S1_2_2", "S2_1_1", "S2_1_2", "S2_2_1", "S2_2_2"),
  f1 = c(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5),
  f2 = c(0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25),
  w = c(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
  ind1 = c(1, 1, 0, 0, 1, 1, 0, 0),
  ind2 = c(1, 0, 0, 0, 1, 1, 1, 1)
)

df_2stage$c <- 0.5 * df_2stage$ind1 + 0.5 * df_2stage$ind2
df_2stage$poor <- as.numeric(df_2stage$c >= 0.5)
df_2stage$ck <- df_2stage$c * df_2stage$poor

des_2stage <- svydesign(
  ids = ~psu + ssu,
  strata = ~h,
  fpc = ~f1 + f2,
  weights = ~w,
  data = df_2stage,
  nest = TRUE
)

h_2stage <- svymean(~poor, des_2stage)
m0_2stage <- svymean(~ck, des_2stage)
a_2stage <- svyratio(~ck, ~poor, des_2stage)

cat("--- 2-Stage Design (f1=0.5, f2=0.25) ---\n")
cat("H:      est =", coef(h_2stage),  "  var =", SE(h_2stage)^2,  "  SE =", SE(h_2stage), "\n")
cat("M0:     est =", coef(m0_2stage), "  var =", SE(m0_2stage)^2, "  SE =", SE(m0_2stage), "\n")
cat("A:      est =", coef(a_2stage),  "  var =", SE(a_2stage)^2,  "  SE =", SE(a_2stage), "\n\n")

# -----------------------------------------------------------------------------
# Design 2: 2-stage design with f1=1.0 (stage 1 census), f2=0.5 (only stage 2 contributes)
# -----------------------------------------------------------------------------
df_f1_1 <- data.frame(
  h = c("H1", "H1", "H1", "H1"),
  psu = c("P1_1", "P1_1", "P1_2", "P1_2"),
  ssu = c("S1_1_1", "S1_1_2", "S1_2_1", "S1_2_2"),
  f1 = c(1.0, 1.0, 1.0, 1.0),
  f2 = c(0.5, 0.5, 0.5, 0.5),
  w = c(1.0, 1.0, 1.0, 1.0),
  ind1 = c(1, 0, 1, 0),
  ind2 = c(1, 0, 0, 1)
)

df_f1_1$c <- 0.5 * df_f1_1$ind1 + 0.5 * df_f1_1$ind2
df_f1_1$poor <- as.numeric(df_f1_1$c >= 0.5)
df_f1_1$ck <- df_f1_1$c * df_f1_1$poor

des_f1_1 <- svydesign(
  ids = ~psu + ssu,
  strata = ~h,
  fpc = ~f1 + f2,
  weights = ~w,
  data = df_f1_1,
  nest = TRUE
)

h_f1_1 <- svymean(~poor, des_f1_1)
m0_f1_1 <- svymean(~ck, des_f1_1)
a_f1_1 <- svyratio(~ck, ~poor, des_f1_1)

cat("--- 2-Stage Design (f1=1.0, f2=0.5) ---\n")
cat("H:      est =", coef(h_f1_1),  "  var =", SE(h_f1_1)^2,  "  SE =", SE(h_f1_1), "\n")
cat("M0:     est =", coef(m0_f1_1), "  var =", SE(m0_f1_1)^2, "  SE =", SE(m0_f1_1), "\n")
cat("A:      est =", coef(a_f1_1),  "  var =", SE(a_f1_1)^2,  "  SE =", SE(a_f1_1), "\n\n")

cat("Oracle script completed successfully.\n")

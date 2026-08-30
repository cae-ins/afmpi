# Oracle validation script using R 'survey' package (v4.5+) for PPS designs
# For afmpi stamp 4.5 (PLAN.md §16)
#
# Execution:
# "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tests/oracle/pps_oracle.R

suppressPackageStartupMessages(library(survey))

options(digits = 14)

cat("=========================================================\n")
cat("afmpi Oracle Validation Script: PPS Designs (SYG & Hajek)\n")
cat("=========================================================\n\n")

# -----------------------------------------------------------------------------
# 1. Sen-Yates-Grundy (SYG) design
# -----------------------------------------------------------------------------
df_syg <- data.frame(
  h = c("H1", "H1"),
  psu = c("P1", "P2"),
  w = c(10.0, 10.0),
  pi = c(0.2, 0.2),
  ind1 = c(1, 0),
  ind2 = c(1, 0)
)

df_syg$c <- 0.5 * df_syg$ind1 + 0.5 * df_syg$ind2
df_syg$poor <- as.numeric(df_syg$c >= 0.5)
df_syg$ck <- df_syg$c * df_syg$poor

p.mat <- matrix(c(0.2, 0.03, 0.03, 0.2), 2, 2)
rownames(p.mat) <- colnames(p.mat) <- c("P1", "P2")

des_syg <- svydesign(
  ids = ~psu,
  strata = ~h,
  pps = ppsmat(p.mat),
  variance = "YG",
  weights = ~w,
  data = df_syg
)

h_syg <- svymean(~poor, des_syg)
m0_syg <- svymean(~ck, des_syg)
a_syg <- svyratio(~ck, ~poor, des_syg)

cat("--- Sen-Yates-Grundy (SYG) ---\n")
cat("H:      est =", coef(h_syg),  "  var =", SE(h_syg)^2,  "  SE =", SE(h_syg), "\n")
cat("M0:     est =", coef(m0_syg), "  var =", SE(m0_syg)^2, "  SE =", SE(m0_syg), "\n")
cat("A:      est =", coef(a_syg),  "  var =", SE(a_syg)^2,  "  SE =", SE(a_syg), "\n\n")

# -----------------------------------------------------------------------------
# 2. Hajek design (equal pi = 0.5 per PSU)
# -----------------------------------------------------------------------------
df_hajek <- data.frame(
  h = c("H1", "H1", "H1", "H1"),
  psu = c("P1", "P1", "P2", "P2"),
  w = c(1.0, 1.0, 1.0, 1.0),
  pi = c(0.5, 0.5, 0.5, 0.5),
  ind1 = c(1, 1, 0, 0),
  ind2 = c(1, 0, 0, 1)
)

df_hajek$c <- 0.5 * df_hajek$ind1 + 0.5 * df_hajek$ind2
df_hajek$poor <- as.numeric(df_hajek$c >= 0.5)
df_hajek$ck <- df_hajek$c * df_hajek$poor

des_hajek <- svydesign(
  ids = ~psu,
  strata = ~h,
  pps = "brewer",
  fpc = ~pi,
  data = df_hajek
)

h_hajek <- svymean(~poor, des_hajek)
m0_hajek <- svymean(~ck, des_hajek)
a_hajek <- svyratio(~ck, ~poor, des_hajek)

cat("--- Hajek (Brewer in R) ---\n")
cat("H:      est =", coef(h_hajek),  "  var =", SE(h_hajek)^2,  "  SE =", SE(h_hajek), "\n")
cat("M0:     est =", coef(m0_hajek), "  var =", SE(m0_hajek)^2, "  SE =", SE(m0_hajek), "\n")
cat("A:      est =", coef(a_hajek),  "  var =", SE(a_hajek)^2,  "  SE =", SE(a_hajek), "\n\n")

cat("Oracle script completed successfully.\n")

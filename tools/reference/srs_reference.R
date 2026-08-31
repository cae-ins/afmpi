# Reference script for SRS and Stratified SRS (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact rational arithmetic in linear combinations)
# - Standard errors ('se'): 1e-7 (floating-point square root and weighted variance accumulation)
# - Degrees of freedom ('df'): 0 (exact integer degrees of freedom: n - 1 or n - H)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/srs_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)

# -----------------------------------------------------------------------------
# 1. SRS (Simple Random Sample, unstratified)
# -----------------------------------------------------------------------------
df_srs <- read.csv("tools/reference/data/data_srs.csv", check.names = FALSE)
df_srs$pw <- df_srs$w * df_srs$size
df_srs$c <- 0.25 * (df_srs$i0 + df_srs$i1 + df_srs$i2 + df_srs$i3)
k_val <- 1/3
df_srs$poor <- as.numeric(df_srs$c >= k_val)
df_srs$ck <- df_srs$c * df_srs$poor

des_srs <- svydesign(ids = ~1, weights = ~pw, data = df_srs)

h_srs <- svymean(~poor, des_srs)
m0_srs <- svymean(~ck, des_srs)
a_srs <- svyratio(~ck, ~poor, des_srs)
df_srs_val <- degf(des_srs)

srs_json <- list(
  design = "srs",
  generator = "tests/test_conformity/generate.py::generate_srs",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/srs_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    list(measure = "H",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_srs)[1]),  se = as.numeric(SE(h_srs)[1]),  df = as.integer(df_srs_val)),
    list(measure = "M0", k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_srs)[1]), se = as.numeric(SE(m0_srs)[1]), df = as.integer(df_srs_val)),
    list(measure = "A",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_srs)[1]),  se = as.numeric(SE(a_srs)[1]),  df = as.integer(df_srs_val))
  )
)

write_json(srs_json, "tests/test_conformity/reference/srs.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/srs.json\n")

# -----------------------------------------------------------------------------
# 2. Stratified SRS (3 strata)
# -----------------------------------------------------------------------------
df_strat <- read.csv("tools/reference/data/data_stratified_srs.csv", check.names = FALSE)
df_strat$pw <- df_strat$w * df_strat$size
df_strat$c <- 0.25 * (df_strat$i0 + df_strat$i1 + df_strat$i2 + df_strat$i3)
df_strat$poor <- as.numeric(df_strat$c >= k_val)
df_strat$ck <- df_strat$c * df_strat$poor

des_strat <- svydesign(ids = ~1, strata = ~stratum, weights = ~pw, data = df_strat)

h_strat <- svymean(~poor, des_strat)
m0_strat <- svymean(~ck, des_strat)
a_strat <- svyratio(~ck, ~poor, des_strat)
df_strat_val <- degf(des_strat)

strat_json <- list(
  design = "stratified_srs",
  generator = "tests/test_conformity/generate.py::generate_stratified_srs",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/srs_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    list(measure = "H",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_strat)[1]),  se = as.numeric(SE(h_strat)[1]),  df = as.integer(df_strat_val)),
    list(measure = "M0", k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_strat)[1]), se = as.numeric(SE(m0_strat)[1]), df = as.integer(df_strat_val)),
    list(measure = "A",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_strat)[1]),  se = as.numeric(SE(a_strat)[1]),  df = as.integer(df_strat_val))
  )
)

write_json(strat_json, "tests/test_conformity/reference/stratified_srs.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/stratified_srs.json\n")

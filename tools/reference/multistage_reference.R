# Reference script for Multi-stage and FPC designs (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact weighted sums)
# - Standard errors ('se'): 1e-7 (floating-point square root and multi-stage FPC variance calculation)
# - Degrees of freedom ('df'): 0 (exact integer degrees of freedom: n_psu - n_strata)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/multistage_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)
k_val <- 0.5

# -----------------------------------------------------------------------------
# 1. 2-Stage Design with FPC (f1=0.5, f2=0.25)
# -----------------------------------------------------------------------------
df_fpc <- read.csv("tools/reference/data/data_multistage_fpc.csv", check.names = FALSE)
df_fpc$c <- 0.25 * (df_fpc$i0 + df_fpc$i1 + df_fpc$i2 + df_fpc$i3)
df_fpc$poor <- as.numeric(df_fpc$c >= k_val)
df_fpc$ck <- df_fpc$c * df_fpc$poor

des_fpc <- svydesign(
  ids = ~psu + ssu,
  strata = ~stratum,
  fpc = ~f1 + f2,
  weights = ~w,
  data = df_fpc,
  nest = TRUE
)

h_fpc <- svymean(~poor, des_fpc)
m0_fpc <- svymean(~ck, des_fpc)
a_fpc <- svyratio(~ck, ~poor, des_fpc)
df_fpc_val <- degf(des_fpc)

# -----------------------------------------------------------------------------
# 2. 2-Stage Design with Stage 1 Census (f1=1.0, f2=0.5)
# -----------------------------------------------------------------------------
df_census <- read.csv("tools/reference/data/data_multistage_census.csv", check.names = FALSE)
df_census$c <- 0.25 * (df_census$i0 + df_census$i1 + df_census$i2 + df_census$i3)
df_census$poor <- as.numeric(df_census$c >= k_val)
df_census$ck <- df_census$c * df_census$poor

des_census <- svydesign(
  ids = ~psu + ssu,
  strata = ~stratum,
  fpc = ~f1 + f2,
  weights = ~w,
  data = df_census,
  nest = TRUE
)

h_census <- svymean(~poor, des_census)
m0_census <- svymean(~ck, des_census)
a_census <- svyratio(~ck, ~poor, des_census)
df_census_val <- degf(des_census)

ms_json <- list(
  design = "multistage",
  generator = "tests/test_conformity/generate.py::generate_multistage",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/multistage_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    list(measure = "H_fpc",       k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_fpc)[1]),       se = as.numeric(SE(h_fpc)[1]),       df = as.integer(df_fpc_val)),
    list(measure = "M0_fpc",      k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_fpc)[1]),      se = as.numeric(SE(m0_fpc)[1]),      df = as.integer(df_fpc_val)),
    list(measure = "A_fpc",       k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_fpc)[1]),       se = as.numeric(SE(a_fpc)[1]),       df = as.integer(df_fpc_val)),
    list(measure = "H_census1",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_census)[1]),    se = as.numeric(SE(h_census)[1]),    df = as.integer(df_census_val)),
    list(measure = "M0_census1",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_census)[1]),   se = as.numeric(SE(m0_census)[1]),   df = as.integer(df_census_val)),
    list(measure = "A_census1",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_census)[1]),    se = as.numeric(SE(a_census)[1]),    df = as.integer(df_census_val))
  )
)

write_json(ms_json, "tests/test_conformity/reference/multistage.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/multistage.json\n")

# Reference script for AF limits (zero poor, all poor, k=0, k=1) (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact boundaries 0.0 or 1.0 or weighted mean)
# - Standard errors ('se'): 1e-7 (floating-point square root)
# - Degrees of freedom ('df'): 0 (exact integer degrees of freedom: n_psu - n_strata)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/af_limits_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)

# -----------------------------------------------------------------------------
# 1. Zero Poor (nobody deprived, H=0, M0=0, SE=0)
# -----------------------------------------------------------------------------
df_zero <- read.csv("tools/reference/data/data_af_zero_poor.csv", check.names = FALSE)
df_zero$c <- 0.25 * (df_zero$i0 + df_zero$i1 + df_zero$i2 + df_zero$i3)
df_zero$poor <- as.numeric(df_zero$c >= 1/3)
df_zero$ck <- df_zero$c * df_zero$poor

des_zero <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_zero, nest = TRUE)
h_zero <- svymean(~poor, des_zero)
m0_zero <- svymean(~ck, des_zero)
df_val <- degf(des_zero)

# -----------------------------------------------------------------------------
# 2. All Poor (everyone deprived in all indicators, H=1, M0=1, A=1, SE=0)
# -----------------------------------------------------------------------------
df_all <- read.csv("tools/reference/data/data_af_all_poor.csv", check.names = FALSE)
df_all$c <- 0.25 * (df_all$i0 + df_all$i1 + df_all$i2 + df_all$i3)
df_all$poor <- as.numeric(df_all$c >= 1/3)
df_all$ck <- df_all$c * df_all$poor

des_all <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_all, nest = TRUE)
h_all <- svymean(~poor, des_all)
m0_all <- svymean(~ck, des_all)
a_all <- svyratio(~ck, ~poor, des_all)

# -----------------------------------------------------------------------------
# 3. Cutoff k = 0.0 on Mixed data (everyone is poor, H=1, M0=mean(c), A=mean(c))
# -----------------------------------------------------------------------------
df_mixed <- read.csv("tools/reference/data/data_af_mixed.csv", check.names = FALSE)
df_mixed$c <- 0.25 * (df_mixed$i0 + df_mixed$i1 + df_mixed$i2 + df_mixed$i3)
df_mixed$poor_k0 <- as.numeric(df_mixed$c >= 0.0)
df_mixed$ck_k0 <- df_mixed$c * df_mixed$poor_k0

des_mixed <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_mixed, nest = TRUE)
h_k0 <- svymean(~poor_k0, des_mixed)
m0_k0 <- svymean(~ck_k0, des_mixed)
a_k0 <- svyratio(~ck_k0, ~poor_k0, des_mixed)

# -----------------------------------------------------------------------------
# 4. Cutoff k = 1.0 on Mixed data (only those with c=1 are poor)
# -----------------------------------------------------------------------------
df_mixed$poor_k1 <- as.numeric(df_mixed$c >= 1.0)
df_mixed$ck_k1 <- df_mixed$c * df_mixed$poor_k1

des_mixed_k1 <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_mixed, nest = TRUE)
h_k1 <- svymean(~poor_k1, des_mixed_k1)
m0_k1 <- svymean(~ck_k1, des_mixed_k1)
a_k1 <- svyratio(~ck_k1, ~poor_k1, des_mixed_k1)

af_limits_json <- list(
  design = "af_limits",
  generator = "tests/test_conformity/generate.py::generate_af_limits",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/af_limits_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    # zero poor
    list(measure = "H_zero",   k = 1/3, over = NULL, subgroup = NULL, est = as.numeric(coef(h_zero)[[1]]),   se = as.numeric(SE(h_zero)[[1]]),   df = as.integer(df_val)),
    list(measure = "M0_zero",  k = 1/3, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_zero)[[1]]),  se = as.numeric(SE(m0_zero)[[1]]),  df = as.integer(df_val)),
    # all poor
    list(measure = "H_all",    k = 1/3, over = NULL, subgroup = NULL, est = as.numeric(coef(h_all)[[1]]),    se = as.numeric(SE(h_all)[[1]]),    df = as.integer(df_val)),
    list(measure = "M0_all",   k = 1/3, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_all)[[1]]),   se = as.numeric(SE(m0_all)[[1]]),   df = as.integer(df_val)),
    list(measure = "A_all",    k = 1/3, over = NULL, subgroup = NULL, est = as.numeric(coef(a_all)[[1]]),    se = as.numeric(SE(a_all)[[1]]),    df = as.integer(df_val)),
    # k = 0
    list(measure = "H_k0",     k = 0.0, over = NULL, subgroup = NULL, est = as.numeric(coef(h_k0)[[1]]),     se = as.numeric(SE(h_k0)[[1]]),     df = as.integer(df_val)),
    list(measure = "M0_k0",    k = 0.0, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_k0)[[1]]),    se = as.numeric(SE(m0_k0)[[1]]),    df = as.integer(df_val)),
    list(measure = "A_k0",     k = 0.0, over = NULL, subgroup = NULL, est = as.numeric(coef(a_k0)[[1]]),     se = as.numeric(SE(a_k0)[[1]]),     df = as.integer(df_val)),
    # k = 1
    list(measure = "H_k1",     k = 1.0, over = NULL, subgroup = NULL, est = as.numeric(coef(h_k1)[[1]]),     se = as.numeric(SE(h_k1)[[1]]),     df = as.integer(df_val)),
    list(measure = "M0_k1",    k = 1.0, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_k1)[[1]]),    se = as.numeric(SE(m0_k1)[[1]]),    df = as.integer(df_val)),
    list(measure = "A_k1",     k = 1.0, over = NULL, subgroup = NULL, est = as.numeric(coef(a_k1)[[1]]),     se = as.numeric(SE(a_k1)[[1]]),     df = as.integer(df_val))
  )
)

write_json(af_limits_json, "tests/test_conformity/reference/af_limits.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/af_limits.json\n")

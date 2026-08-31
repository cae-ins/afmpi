# Reference script for Data limits (extreme weights 1:10^6 and missing values) (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact weighted sums)
# - Standard errors ('se'): 1e-7 (floating-point square root and linearization under extreme weights / missing value imputation)
# - Degrees of freedom ('df'): 0 (exact integer degrees of freedom: n_psu - n_strata)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/data_limits_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)
k_val <- 0.5

# -----------------------------------------------------------------------------
# 1. Extreme Weights (ratio 1 : 1,000,000)
# -----------------------------------------------------------------------------
df_ext <- read.csv("tools/reference/data/data_extreme_weights.csv", check.names = FALSE)
df_ext$c <- 0.25 * (df_ext$i0 + df_ext$i1 + df_ext$i2 + df_ext$i3)
df_ext$poor <- as.numeric(df_ext$c >= k_val)
df_ext$ck <- df_ext$c * df_ext$poor

des_ext <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_ext, nest = TRUE)
h_ext <- svymean(~poor, des_ext)
m0_ext <- svymean(~ck, des_ext)
a_ext <- svyratio(~ck, ~poor, des_ext)
df_ext_val <- degf(des_ext)

# -----------------------------------------------------------------------------
# 2. Missing Values: listwise deletion
# -----------------------------------------------------------------------------
df_miss <- read.csv("tools/reference/data/data_missing_values.csv", check.names = FALSE)
# Drop rows where any of i0..i3 is NA
valid_mask <- !is.na(df_miss$i0) & !is.na(df_miss$i1) & !is.na(df_miss$i2) & !is.na(df_miss$i3)
df_lw <- df_miss[valid_mask, ]
df_lw$c <- 0.25 * (df_lw$i0 + df_lw$i1 + df_lw$i2 + df_lw$i3)
df_lw$poor <- as.numeric(df_lw$c >= k_val)
df_lw$ck <- df_lw$c * df_lw$poor

des_lw <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_lw, nest = TRUE)
h_lw <- svymean(~poor, des_lw)
m0_lw <- svymean(~ck, des_lw)
a_lw <- svyratio(~ck, ~poor, des_lw)
df_lw_val <- degf(des_lw)

# -----------------------------------------------------------------------------
# 3. Missing Values: treat as non-deprived (NA -> 0)
# -----------------------------------------------------------------------------
df_tan <- df_miss
df_tan$i0[is.na(df_tan$i0)] <- 0
df_tan$i1[is.na(df_tan$i1)] <- 0
df_tan$i2[is.na(df_tan$i2)] <- 0
df_tan$i3[is.na(df_tan$i3)] <- 0
df_tan$c <- 0.25 * (df_tan$i0 + df_tan$i1 + df_tan$i2 + df_tan$i3)
df_tan$poor <- as.numeric(df_tan$c >= k_val)
df_tan$ck <- df_tan$c * df_tan$poor

des_tan <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_tan, nest = TRUE)
h_tan <- svymean(~poor, des_tan)
m0_tan <- svymean(~ck, des_tan)
a_tan <- svyratio(~ck, ~poor, des_tan)
df_tan_val <- degf(des_tan)

# -----------------------------------------------------------------------------
# 4. Missing Values: reweighting (redistribute weights among observed indicators)
# -----------------------------------------------------------------------------
# Rows where all indicators are missing cannot be reweighted and are dropped
obs_counts <- apply(df_miss[, c("i0", "i1", "i2", "i3")], 1, function(r) sum(!is.na(r)))
df_rw <- df_miss[obs_counts > 0, ]
c_rw <- numeric(nrow(df_rw))
for (idx in seq_len(nrow(df_rw))) {
  obs_w <- 0.0
  dep_w <- 0.0
  for (col_name in c("i0", "i1", "i2", "i3")) {
    val <- df_rw[idx, col_name]
    if (!is.na(val)) {
      obs_w <- obs_w + 0.25
      dep_w <- dep_w + 0.25 * val
    }
  }
  c_rw[idx] <- dep_w / obs_w
}
df_rw$c <- c_rw
df_rw$poor <- as.numeric(df_rw$c >= k_val)
df_rw$ck <- df_rw$c * df_rw$poor

des_rw <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_rw, nest = TRUE)
h_rw <- svymean(~poor, des_rw)
m0_rw <- svymean(~ck, des_rw)
a_rw <- svyratio(~ck, ~poor, des_rw)
df_rw_val <- degf(des_rw)

data_limits_json <- list(
  design = "data_limits",
  generator = "tests/test_conformity/generate.py::generate_data_limits",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/data_limits_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    # extreme weights
    list(measure = "H_ext",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_ext)[[1]]),   se = as.numeric(SE(h_ext)[[1]]),   df = as.integer(df_ext_val)),
    list(measure = "M0_ext",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_ext)[[1]]),  se = as.numeric(SE(m0_ext)[[1]]),  df = as.integer(df_ext_val)),
    list(measure = "A_ext",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_ext)[[1]]),   se = as.numeric(SE(a_ext)[[1]]),   df = as.integer(df_ext_val)),
    # listwise deletion
    list(measure = "H_lw",     k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_lw)[[1]]),    se = as.numeric(SE(h_lw)[[1]]),    df = as.integer(df_lw_val)),
    list(measure = "M0_lw",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_lw)[[1]]),   se = as.numeric(SE(m0_lw)[[1]]),   df = as.integer(df_lw_val)),
    list(measure = "A_lw",     k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_lw)[[1]]),    se = as.numeric(SE(a_lw)[[1]]),    df = as.integer(df_lw_val)),
    # treat as non-deprived
    list(measure = "H_tan",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_tan)[[1]]),   se = as.numeric(SE(h_tan)[[1]]),   df = as.integer(df_tan_val)),
    list(measure = "M0_tan",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_tan)[[1]]),  se = as.numeric(SE(m0_tan)[[1]]),  df = as.integer(df_tan_val)),
    list(measure = "A_tan",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_tan)[[1]]),   se = as.numeric(SE(a_tan)[[1]]),   df = as.integer(df_tan_val)),
    # reweighting
    list(measure = "H_rw",     k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_rw)[[1]]),    se = as.numeric(SE(h_rw)[[1]]),    df = as.integer(df_rw_val)),
    list(measure = "M0_rw",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_rw)[[1]]),   se = as.numeric(SE(m0_rw)[[1]]),   df = as.integer(df_rw_val)),
    list(measure = "A_rw",     k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_rw)[[1]]),    se = as.numeric(SE(a_rw)[[1]]),    df = as.integer(df_rw_val))
  )
)

write_json(data_limits_json, "tests/test_conformity/reference/data_limits.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/data_limits.json\n")

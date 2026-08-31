# Reference script for Lonely PSU policies (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact weighted sums)
# - Standard errors ('se'): 1e-7 (floating-point square root and lonely PSU centering/averaging)
# - Degrees of freedom ('df'): 0 (exact integer degrees of freedom: 5 - 3 = 2 for adjust/average/certainty/fail, 5 - 2 = 3 for collapse)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/lonely_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)
k_val <- 0.5

df_lonely <- read.csv("tools/reference/data/data_lonely_psu.csv", check.names = FALSE)
df_lonely$c <- 0.25 * (df_lonely$i0 + df_lonely$i1 + df_lonely$i2 + df_lonely$i3)
df_lonely$poor <- as.numeric(df_lonely$c >= k_val)
df_lonely$ck <- df_lonely$c * df_lonely$poor

# 1. certainty (lonely stratum contributes 0 to variance, df = 4 - 2 = 2)
options(survey.lonely.psu = "certainty")
des_cert <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_lonely, nest = TRUE)
h_cert <- svymean(~poor, des_cert)
m0_cert <- svymean(~ck, des_cert)
a_cert <- svyratio(~ck, ~poor, des_cert)
df_cert_val <- degf(des_cert)

# 2. adjust (lonely stratum centered at grand mean, df = 2)
options(survey.lonely.psu = "adjust")
des_adj <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_lonely, nest = TRUE)
h_adj <- svymean(~poor, des_adj)
m0_adj <- svymean(~ck, des_adj)
a_adj <- svyratio(~ck, ~poor, des_adj)
df_adj_val <- degf(des_adj)

# 3. average (lonely stratum assigned average variance of other strata, df = 2)
options(survey.lonely.psu = "average")
des_avg <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_lonely, nest = TRUE)
h_avg <- svymean(~poor, des_avg)
m0_avg <- svymean(~ck, des_avg)
a_avg <- svyratio(~ck, ~poor, des_avg)
df_avg_val <- degf(des_avg)

# 4. collapse (stratum H3 collapsed with stratum H1, which is sorted(h2_strata_keys)[0])
df_col <- df_lonely
df_col$stratum_col <- ifelse(df_col$stratum == "H3", "H1", df_col$stratum)
des_col <- svydesign(ids = ~psu, strata = ~stratum_col, weights = ~w, data = df_col, nest = TRUE)
h_col <- svymean(~poor, des_col)
m0_col <- svymean(~ck, des_col)
a_col <- svyratio(~ck, ~poor, des_col)
df_col_val <- degf(des_col) # 5 PSUs - 2 strata = 3

# 5. fail (variance NaN, df = 2)
h_est_val <- as.numeric(coef(h_cert)[[1]])
m0_est_val <- as.numeric(coef(m0_cert)[[1]])
a_est_val <- as.numeric(coef(a_cert)[[1]])

lonely_json <- list(
  design = "lonely_psu",
  generator = "tests/test_conformity/generate.py::generate_lonely_psu",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/lonely_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    # fail
    list(measure = "H_fail",        k = k_val, over = NULL, subgroup = NULL, est = h_est_val,  se = NULL, df = as.integer(df_cert_val)),
    list(measure = "M0_fail",       k = k_val, over = NULL, subgroup = NULL, est = m0_est_val, se = NULL, df = as.integer(df_cert_val)),
    list(measure = "A_fail",        k = k_val, over = NULL, subgroup = NULL, est = a_est_val,  se = NULL, df = as.integer(df_cert_val)),
    # certainty
    list(measure = "H_certainty",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_cert)[[1]]),  se = as.numeric(SE(h_cert)[[1]]),  df = as.integer(df_cert_val)),
    list(measure = "M0_certainty",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_cert)[[1]]), se = as.numeric(SE(m0_cert)[[1]]), df = as.integer(df_cert_val)),
    list(measure = "A_certainty",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_cert)[[1]]),  se = as.numeric(SE(a_cert)[[1]]),  df = as.integer(df_cert_val)),
    # adjust
    list(measure = "H_adjust",      k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_adj)[[1]]),   se = as.numeric(SE(h_adj)[[1]]),   df = as.integer(df_adj_val)),
    list(measure = "M0_adjust",     k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_adj)[[1]]),  se = as.numeric(SE(m0_adj)[[1]]),  df = as.integer(df_adj_val)),
    list(measure = "A_adjust",      k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_adj)[[1]]),   se = as.numeric(SE(a_adj)[[1]]),   df = as.integer(df_adj_val)),
    # average
    list(measure = "H_average",     k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_avg)[[1]]),   se = as.numeric(SE(h_avg)[[1]]),   df = as.integer(df_avg_val)),
    list(measure = "M0_average",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_avg)[[1]]),  se = as.numeric(SE(m0_avg)[[1]]),  df = as.integer(df_avg_val)),
    list(measure = "A_average",     k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_avg)[[1]]),   se = as.numeric(SE(a_avg)[[1]]),   df = as.integer(df_avg_val)),
    # collapse
    list(measure = "H_collapse",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_col)[[1]]),   se = as.numeric(SE(h_col)[[1]]),   df = as.integer(df_col_val)),
    list(measure = "M0_collapse",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_col)[[1]]),  se = as.numeric(SE(m0_col)[[1]]),  df = as.integer(df_col_val)),
    list(measure = "A_collapse",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_col)[[1]]),   se = as.numeric(SE(a_col)[[1]]),   df = as.integer(df_col_val))
  )
)

write_json(lonely_json, "tests/test_conformity/reference/lonely_psu.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/lonely_psu.json\n")

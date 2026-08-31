# Reference script for Cluster and Stratified Cluster designs (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact weighted sums)
# - Standard errors ('se'): 1e-7 (floating-point square root and cluster aggregation)
# - Degrees of freedom ('df'): 0 (exact integer degrees of freedom: n_psu - 1 or n_psu - n_strata)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/cluster_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)
k_val <- 1/3

# -----------------------------------------------------------------------------
# 1. Cluster 1-Stage (8 PSUs, unstratified)
# -----------------------------------------------------------------------------
df_cl1 <- read.csv("tools/reference/data/data_cluster_1stage.csv", check.names = FALSE)
df_cl1$pw <- df_cl1$w * df_cl1$size
df_cl1$c <- 0.25 * (df_cl1$i0 + df_cl1$i1 + df_cl1$i2 + df_cl1$i3)
df_cl1$poor <- as.numeric(df_cl1$c >= k_val)
df_cl1$ck <- df_cl1$c * df_cl1$poor

des_cl1 <- svydesign(ids = ~psu, weights = ~pw, data = df_cl1)

h_cl1 <- svymean(~poor, des_cl1)
m0_cl1 <- svymean(~ck, des_cl1)
a_cl1 <- svyratio(~ck, ~poor, des_cl1)
df_cl1_val <- degf(des_cl1)

cl1_json <- list(
  design = "cluster_1stage",
  generator = "tests/test_conformity/generate.py::generate_cluster_1stage",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/cluster_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    list(measure = "H",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_cl1)[1]),  se = as.numeric(SE(h_cl1)[1]),  df = as.integer(df_cl1_val)),
    list(measure = "M0", k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_cl1)[1]), se = as.numeric(SE(m0_cl1)[1]), df = as.integer(df_cl1_val)),
    list(measure = "A",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_cl1)[1]),  se = as.numeric(SE(a_cl1)[1]),  df = as.integer(df_cl1_val))
  )
)

write_json(cl1_json, "tests/test_conformity/reference/cluster_1stage.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/cluster_1stage.json\n")

# -----------------------------------------------------------------------------
# 2. Stratified Cluster (3 strata, 3 PSUs each = 9 PSUs)
# -----------------------------------------------------------------------------
df_scl <- read.csv("tools/reference/data/data_stratified_cluster.csv", check.names = FALSE)
df_scl$pw <- df_scl$w * df_scl$size
df_scl$c <- 0.25 * (df_scl$i0 + df_scl$i1 + df_scl$i2 + df_scl$i3)
df_scl$poor <- as.numeric(df_scl$c >= k_val)
df_scl$ck <- df_scl$c * df_scl$poor

des_scl <- svydesign(ids = ~psu, strata = ~stratum, weights = ~pw, data = df_scl, nest = TRUE)

h_scl <- svymean(~poor, des_scl)
m0_scl <- svymean(~ck, des_scl)
a_scl <- svyratio(~ck, ~poor, des_scl)
df_scl_val <- degf(des_scl)

scl_json <- list(
  design = "stratified_cluster",
  generator = "tests/test_conformity/generate.py::generate_stratified_cluster",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/cluster_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    list(measure = "H",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_scl)[1]),  se = as.numeric(SE(h_scl)[1]),  df = as.integer(df_scl_val)),
    list(measure = "M0", k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_scl)[1]), se = as.numeric(SE(m0_scl)[1]), df = as.integer(df_scl_val)),
    list(measure = "A",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_scl)[1]),  se = as.numeric(SE(a_scl)[1]),  df = as.integer(df_scl_val))
  )
)

write_json(scl_json, "tests/test_conformity/reference/stratified_cluster.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/stratified_cluster.json\n")

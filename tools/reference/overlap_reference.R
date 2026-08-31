# Reference script for Panel and Overlapping Samples (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact difference of means)
# - Standard errors ('se'): 1e-7 (floating-point square root and longitudinal covariance calculation)
# - Degrees of freedom ('df'): 0 (exact integer degrees of freedom: n_psu - n_strata)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/overlap_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)

# -----------------------------------------------------------------------------
# 1. Perfect Panel (4 households in 2 clusters, 1 stratum)
# -----------------------------------------------------------------------------
df_perf <- read.csv("tools/reference/data/data_perfect_panel.csv", check.names = FALSE)
df_perf$c <- 0.5 * (df_perf$i0 + df_perf$i1)
df_perf$poor <- as.numeric(df_perf$c >= 0.5)
df_perf$ck <- df_perf$c * df_perf$poor

df_t0 <- df_perf[df_perf$wave == "t0", c("hhid", "stratum", "cluster", "w", "poor", "ck")]
df_t1 <- df_perf[df_perf$wave == "t1", c("hhid", "poor", "ck")]
colnames(df_t0)[colnames(df_t0) == "poor"] <- "poor_t0"
colnames(df_t0)[colnames(df_t0) == "ck"]   <- "ck_t0"
colnames(df_t1)[colnames(df_t1) == "poor"] <- "poor_t1"
colnames(df_t1)[colnames(df_t1) == "ck"]   <- "ck_t1"

df_wide_perf <- merge(df_t0, df_t1, by = "hhid")
des_perf <- svydesign(ids = ~cluster, strata = ~stratum, weights = ~w, data = df_wide_perf, nest = TRUE)

res_perf_poor <- svymean(~poor_t0 + poor_t1, des_perf)
res_perf_ck <- svymean(~ck_t0 + ck_t1, des_perf)

V_poor <- vcov(res_perf_poor)
V_ck   <- vcov(res_perf_ck)

var_H_diff_perf  <- V_poor["poor_t1", "poor_t1"] + V_poor["poor_t0", "poor_t0"] - 2 * V_poor["poor_t0", "poor_t1"]
var_M0_diff_perf <- V_ck["ck_t1", "ck_t1"] + V_ck["ck_t0", "ck_t0"] - 2 * V_ck["ck_t0", "ck_t1"]

est_H_diff_perf  <- coef(res_perf_poor)["poor_t1"] - coef(res_perf_poor)["poor_t0"]
est_M0_diff_perf <- coef(res_perf_ck)["ck_t1"] - coef(res_perf_ck)["ck_t0"]

se_H_diff_perf  <- sqrt(var_H_diff_perf)
se_M0_diff_perf <- sqrt(var_M0_diff_perf)
df_perf_val <- degf(des_perf)

# -----------------------------------------------------------------------------
# 2. Partial Overlap Panel (7 households across 2 waves)
# -----------------------------------------------------------------------------
df_part <- read.csv("tools/reference/data/data_partial_panel.csv", check.names = FALSE)
df_part$c <- 0.5 * (df_part$i0 + df_part$i1)
df_part$poor <- as.numeric(df_part$c >= 0.5)
df_part$ck <- df_part$c * df_part$poor

hhids <- unique(df_part$hhid)
df_t0_p <- df_part[df_part$wave == "t0", ]
df_t1_p <- df_part[df_part$wave == "t1", ]

rows_wide <- list()
for (h in hhids) {
  row_t0 <- df_t0_p[df_t0_p$hhid == h, ]
  row_t1 <- df_t1_p[df_t1_p$hhid == h, ]
  
  stratum <- if (nrow(row_t0) > 0) row_t0$stratum[1] else row_t1$stratum[1]
  cluster <- if (nrow(row_t0) > 0) row_t0$cluster[1] else row_t1$cluster[1]
  w       <- if (nrow(row_t0) > 0) row_t0$w[1]       else row_t1$w[1]
  
  poor_t0 <- if (nrow(row_t0) > 0) row_t0$poor[1] else 0.0
  poor_t1 <- if (nrow(row_t1) > 0) row_t1$poor[1] else 0.0
  ck_t0   <- if (nrow(row_t0) > 0) row_t0$ck[1]   else 0.0
  ck_t1   <- if (nrow(row_t1) > 0) row_t1$ck[1]   else 0.0
  
  ind_t0 <- if (nrow(row_t0) > 0) 1.0 else 0.0
  ind_t1 <- if (nrow(row_t1) > 0) 1.0 else 0.0
  
  rows_wide[[length(rows_wide) + 1]] <- data.frame(
    hhid = h, stratum = stratum, cluster = cluster, w = w,
    poor_t0 = poor_t0, poor_t1 = poor_t1,
    ck_t0 = ck_t0, ck_t1 = ck_t1,
    ind_t0 = ind_t0, ind_t1 = ind_t1,
    p0_w = poor_t0 * ind_t0, p1_w = poor_t1 * ind_t1,
    ck0_w = ck_t0 * ind_t0, ck1_w = ck_t1 * ind_t1
  )
}
df_wide_part <- do.call(rbind, rows_wide)
des_part <- svydesign(ids = ~cluster, strata = ~stratum, weights = ~w, data = df_wide_part, nest = TRUE)

mean_res <- svymean(~p0_w + ind_t0 + p1_w + ind_t1, des_part)
V_m <- vcov(mean_res)
coef_m <- coef(mean_res)

N0 <- coef_m["ind_t0"]
N1 <- coef_m["ind_t1"]
H0 <- coef_m["p0_w"] / N0
H1 <- coef_m["p1_w"] / N1

g0 <- c(1/N0, -H0/N0, 0, 0)
g1 <- c(0, 0, 1/N1, -H1/N1)
g_diff <- g1 - g0

var_H_diff_part <- as.numeric((t(g_diff) %*% V_m %*% g_diff)[1, 1])
se_H_diff_part  <- sqrt(var_H_diff_part)
est_H_diff_part <- as.numeric(H1 - H0)
df_part_val <- degf(des_part)

overlap_json <- list(
  design = "overlap",
  generator = "tests/test_conformity/generate.py::generate_overlap",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/overlap_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    # perfect panel
    list(measure = "Delta_H_perfect",  k = 0.5, over = NULL, subgroup = NULL, est = as.numeric(est_H_diff_perf),  se = as.numeric(se_H_diff_perf),  df = as.integer(df_perf_val)),
    list(measure = "Delta_M0_perfect", k = 0.5, over = NULL, subgroup = NULL, est = as.numeric(est_M0_diff_perf), se = as.numeric(se_M0_diff_perf), df = as.integer(df_perf_val)),
    # partial panel
    list(measure = "Delta_H_partial",  k = 0.5, over = NULL, subgroup = NULL, est = as.numeric(est_H_diff_part),  se = as.numeric(se_H_diff_part),  df = as.integer(df_part_val))
  )
)

write_json(overlap_json, "tests/test_conformity/reference/overlap.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/overlap.json\n")

# Oracle validation script using R 'survey' package (v4.5+)
# For afmpi stamp (PLAN.md §18) - Panel & Overlapping Samples
#
# Execution:
# "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tests/oracle/panel_oracle.R

suppressPackageStartupMessages(library(survey))

options(digits = 14)

cat("=========================================================\n")
cat("afmpi Oracle Validation Script: Panel & Overlapping Samples (R survey)\n")
cat("=========================================================\n\n")

if (!file.exists("tests/oracle/data_panel_perfect.csv") || !file.exists("tests/oracle/panel_meta.json")) {
  cat("Generating oracle datasets via Python...\n")
  system2("python", c("tests/oracle/export_oracle_data.py"))
}

meta <- jsonlite::fromJSON("tests/oracle/panel_meta.json")

# -----------------------------------------------------------------------------
# 1. Perfect Panel (1 stratum, 2 PSUs, 4 households present in both waves)
# -----------------------------------------------------------------------------
df_perf <- read.csv("tests/oracle/data_panel_perfect.csv", check.names = FALSE)
df_t0 <- df_perf[df_perf$wave == "t0", c("hhid", "stratum", "cluster", "w", "poor", "ck")]
df_t1 <- df_perf[df_perf$wave == "t1", c("hhid", "poor", "ck")]
colnames(df_t0)[colnames(df_t0) == "poor"] <- "poor_t0"
colnames(df_t0)[colnames(df_t0) == "ck"]   <- "ck_t0"
colnames(df_t1)[colnames(df_t1) == "poor"] <- "poor_t1"
colnames(df_t1)[colnames(df_t1) == "ck"]   <- "ck_t1"

df_wide_perf <- merge(df_t0, df_t1, by = "hhid")

des_perf <- svydesign(ids = ~cluster, strata = ~stratum, weights = ~w, data = df_wide_perf, nest = TRUE)
res_perf <- svymean(~poor_t0 + poor_t1, des_perf)
V_perf <- vcov(res_perf)

v0_p  <- V_perf["poor_t0", "poor_t0"]
v1_p  <- V_perf["poor_t1", "poor_t1"]
v01_p <- V_perf["poor_t0", "poor_t1"]
var_diff_p <- v1_p + v0_p - 2 * v01_p
se_diff_p  <- sqrt(var_diff_p)

cat("--- 1. Perfect Panel ---\n")
cat("H_t0:   var =", v0_p, "\n")
cat("H_t1:   var =", v1_p, "\n")
cat("Cov:    cov =", v01_p, "\n")
cat("H Diff: est =", meta$perfect$est_H_diff, "  var =", var_diff_p, "  SE =", se_diff_p, "\n\n")

# -----------------------------------------------------------------------------
# 2. Partial Overlap Panel (2 strata, 4 PSUs, overlapping & disjoint units)
# -----------------------------------------------------------------------------
df_part <- read.csv("tests/oracle/data_panel_partial.csv", check.names = FALSE)

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
  
  ind_t0 <- if (nrow(row_t0) > 0) 1.0 else 0.0
  ind_t1 <- if (nrow(row_t1) > 0) 1.0 else 0.0
  
  rows_wide[[length(rows_wide) + 1]] <- data.frame(
    hhid = h, stratum = stratum, cluster = cluster, w = w,
    poor_t0 = poor_t0, poor_t1 = poor_t1,
    ind_t0 = ind_t0, ind_t1 = ind_t1,
    p0_w = poor_t0 * ind_t0, p1_w = poor_t1 * ind_t1
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

var_diff_part <- (t(g_diff) %*% V_m %*% g_diff)[1, 1]
se_diff_part  <- sqrt(var_diff_part)

cat("--- 2. Partial Overlap Panel ---\n")
cat("H Diff: est =", meta$partial$est_H_diff, "  var =", var_diff_part, "  SE =", se_diff_part, "\n\n")

cat("Panel oracle script completed successfully.\n")

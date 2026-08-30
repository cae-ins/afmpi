# Oracle validation script using R 'survey' package (v4.5+)
# For afmpi stamp (PLAN.md §18) - VCOV Matrix & Wald Hypothesis Testing
#
# Execution:
# "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tests/oracle/vcov_wald_oracle.R

suppressPackageStartupMessages(library(survey))

options(digits = 14)

cat("=========================================================\n")
cat("afmpi Oracle Validation Script: VCOV & Wald Test (R survey)\n")
cat("=========================================================\n\n")

if (!file.exists("tests/oracle/data_vcov_wald.csv") || !file.exists("tests/oracle/vcov_wald_meta.json")) {
  cat("Generating oracle datasets via Python...\n")
  system2("python", c("tests/oracle/export_oracle_data.py"))
}

meta <- jsonlite::fromJSON("tests/oracle/vcov_wald_meta.json")

df <- read.csv("tests/oracle/data_vcov_wald.csv", check.names = FALSE)
df$ind_A <- as.numeric(df$group == "A")
df$ind_B <- as.numeric(df$group == "B")
df$ck_A  <- df$ck * df$ind_A
df$ck_B  <- df$ck * df$ind_B

des <- svydesign(ids = ~psu, strata = ~stratum, weights = ~weight, data = df, nest = TRUE)

mean_res <- svymean(~ck_A + ind_A + ck_B + ind_B, des)
V_m <- vcov(mean_res)
coef_m <- coef(mean_res)

N_A  <- coef_m["ind_A"]
N_B  <- coef_m["ind_B"]
M0_A <- coef_m["ck_A"] / N_A
M0_B <- coef_m["ck_B"] / N_B

g_A <- c(1/N_A, -M0_A/N_A, 0, 0)
g_B <- c(0, 0, 1/N_B, -M0_B/N_B)

v_aa <- (t(g_A) %*% V_m %*% g_A)[1, 1]
v_bb <- (t(g_B) %*% V_m %*% g_B)[1, 1]
v_ab <- (t(g_A) %*% V_m %*% g_B)[1, 1]

diff <- M0_A - M0_B
var_diff <- v_aa + v_bb - 2 * v_ab
se_diff  <- sqrt(var_diff)
F_stat   <- (diff^2) / var_diff
df1      <- 1
df2      <- degf(des)
p_val    <- pf(F_stat, df1 = df1, df2 = df2, lower.tail = FALSE)

cat("--- VCOV Matrix & Cross-Domain Covariance ---\n")
cat(sprintf("M0_A: est = %.14g   V_aa = %.14g\n", M0_A, v_aa))
cat(sprintf("M0_B: est = %.14g   V_bb = %.14g\n", M0_B, v_bb))
cat(sprintf("Cov(M0_A, M0_B):     V_ab = %.14g\n\n", v_ab))

cat("--- Wald Hypothesis Test (M0_A vs M0_B) ---\n")
cat(sprintf("Contrast Diff (M0_A - M0_B):  est = %.14g   SE = %.14g\n", diff, se_diff))
cat(sprintf("Wald Statistic (F):            %.14g\n", F_stat))
cat(sprintf("Degrees of Freedom:            df1 = %d, df2 = %d\n", df1, df2))
cat(sprintf("P-value:                       %.14g\n\n", p_val))

cat("VCOV & Wald oracle script completed successfully.\n")

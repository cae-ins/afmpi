# Oracle validation script using R 'survey' package (v4.5+)
# For afmpi stamp 3.5-bis (PLAN.md §17)
#
# Execution:
# "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tests/oracle/core_oracle.R

suppressPackageStartupMessages(library(survey))

options(digits = 14)

cat("=========================================================\n")
cat("afmpi Oracle Validation Script: Core Survey Engine (R survey)\n")
cat("=========================================================\n\n")

get_ci <- function(prop_obj) {
  ci <- attr(prop_obj, "ci")
  c(ci[1], ci[2])
}

# -----------------------------------------------------------------------------
# 1. SRS Simple (no strata, no clusters — each row is its own PSU)
# -----------------------------------------------------------------------------
df_srs <- data.frame(
  id = 1:10,
  w = c(1.0, 1.2, 0.8, 1.1, 0.9, 1.3, 1.0, 1.4, 0.7, 1.2),
  size = c(4, 3, 5, 2, 6, 4, 3, 5, 4, 2),
  i0 = c(1, 0, 1, 1, 0, 1, 1, 0, 1, 0),
  i1 = c(1, 1, 0, 1, 0, 0, 1, 1, 0, 1),
  i2 = c(0, 1, 1, 0, 1, 0, 0, 1, 1, 0),
  i3 = c(1, 0, 0, 1, 0, 1, 0, 0, 1, 1)
)
df_srs$pw <- df_srs$w * df_srs$size
df_srs$c <- 0.25 * (df_srs$i0 + df_srs$i1 + df_srs$i2 + df_srs$i3)
df_srs$poor <- as.numeric(df_srs$c >= 1/3)
df_srs$ck <- df_srs$c * df_srs$poor

des_srs <- svydesign(
  ids = ~1,
  weights = ~pw,
  data = df_srs
)

h_srs <- svymean(~poor, des_srs)
m0_srs <- svymean(~ck, des_srs)
a_srs <- svyratio(~ck, ~poor, des_srs)
ci_h_logit_srs <- get_ci(svyciprop(~poor, des_srs, method = "logit"))
ci_h_xlogit_srs <- get_ci(svyciprop(~poor, des_srs, method = "xlogit"))
df_srs_val <- degf(des_srs)
h_val <- coef(h_srs)[1]
h_se <- SE(h_srs)[1]
ci_h_t_srs <- c(h_val - qt(0.975, df_srs_val) * h_se, h_val + qt(0.975, df_srs_val) * h_se)
ci_h_norm_srs <- c(h_val - qnorm(0.975) * h_se, h_val + qnorm(0.975) * h_se)

cat("--- 1. SRS Simple ---\n")
cat("H:      est =", coef(h_srs)[1],  "  var =", SE(h_srs)[1]^2,  "  SE =", SE(h_srs)[1], "\n")
cat("M0:     est =", coef(m0_srs)[1], "  var =", SE(m0_srs)[1]^2, "  SE =", SE(m0_srs)[1], "\n")
cat("A:      est =", coef(a_srs)[1],  "  var =", SE(a_srs)[1]^2,  "  SE =", SE(a_srs)[1], "\n")
cat("degf:  ", df_srs_val, "\n")
cat("H CI (logit):   [", ci_h_logit_srs[1], ",", ci_h_logit_srs[2], "]\n")
cat("H CI (xlogit):  [", ci_h_xlogit_srs[1], ",", ci_h_xlogit_srs[2], "]\n")
cat("H CI (t):       [", ci_h_t_srs[1], ",", ci_h_t_srs[2], "]\n")
cat("H CI (normal):  [", ci_h_norm_srs[1], ",", ci_h_norm_srs[2], "]\n\n")

# -----------------------------------------------------------------------------
# 2. Stratified Simple 1-Stage (Strata + PSU, multiple strata, unequal sizes)
# -----------------------------------------------------------------------------
df_strat <- data.frame(
  id = 1:12,
  stratum = c(1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3),
  psu = c(1, 1, 2, 3, 4, 4, 5, 5, 6, 7, 7, 8),
  w = c(1.0, 1.2, 0.8, 1.1, 0.9, 1.3, 1.0, 1.4, 0.7, 1.2, 1.1, 0.9),
  size = c(4, 3, 5, 2, 6, 4, 3, 5, 4, 2, 6, 3),
  i0 = c(1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1),
  i1 = c(1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0),
  i2 = c(0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1),
  i3 = c(1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0)
)
df_strat$pw <- df_strat$w * df_strat$size
df_strat$c <- 0.25 * (df_strat$i0 + df_strat$i1 + df_strat$i2 + df_strat$i3)
df_strat$poor <- as.numeric(df_strat$c >= 1/3)
df_strat$ck <- df_strat$c * df_strat$poor

des_strat <- svydesign(
  ids = ~psu,
  strata = ~stratum,
  weights = ~pw,
  data = df_strat,
  nest = TRUE
)

h_strat <- svymean(~poor, des_strat)
m0_strat <- svymean(~ck, des_strat)
a_strat <- svyratio(~ck, ~poor, des_strat)
ci_h_logit_strat <- get_ci(svyciprop(~poor, des_strat, method = "logit"))
ci_h_xlogit_strat <- get_ci(svyciprop(~poor, des_strat, method = "xlogit"))
df_strat_val <- degf(des_strat)
h_strat_val <- coef(h_strat)[1]
h_strat_se <- SE(h_strat)[1]
ci_h_t_strat <- c(h_strat_val - qt(0.975, df_strat_val) * h_strat_se, h_strat_val + qt(0.975, df_strat_val) * h_strat_se)
ci_h_norm_strat <- c(h_strat_val - qnorm(0.975) * h_strat_se, h_strat_val + qnorm(0.975) * h_strat_se)

cat("--- 2. Stratified Simple 1-Stage ---\n")
cat("H:      est =", coef(h_strat)[1],  "  var =", SE(h_strat)[1]^2,  "  SE =", SE(h_strat)[1], "\n")
cat("M0:     est =", coef(m0_strat)[1], "  var =", SE(m0_strat)[1]^2, "  SE =", SE(m0_strat)[1], "\n")
cat("A:      est =", coef(a_strat)[1],  "  var =", SE(a_strat)[1]^2,  "  SE =", SE(a_strat)[1], "\n")
cat("degf:  ", df_strat_val, "\n")
cat("H CI (logit):   [", ci_h_logit_strat[1], ",", ci_h_logit_strat[2], "]\n")
cat("H CI (xlogit):  [", ci_h_xlogit_strat[1], ",", ci_h_xlogit_strat[2], "]\n")
cat("H CI (t):       [", ci_h_t_strat[1], ",", ci_h_t_strat[2], "]\n")
cat("H CI (normal):  [", ci_h_norm_strat[1], ",", ci_h_norm_strat[2], "]\n\n")

# -----------------------------------------------------------------------------
# 3. Domain (subset in R) on Stratified Design (using LAYOUT from test_domain.py)
# -----------------------------------------------------------------------------
df_layout <- data.frame(
  i0 = c(1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1),
  i1 = c(1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0),
  i2 = c(0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1),
  i3 = c(1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0),
  w = c(1.0, 1.2, 0.8, 1.1, 0.9, 1.3, 1.0, 1.4, 0.7, 1.2, 1.1, 0.9),
  size = c(4, 3, 5, 2, 6, 4, 3, 5, 4, 2, 6, 3),
  strate = c(1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3),
  grappe = c(1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6),
  region = c("A", "A", "B", "B", "A", "A", "A", "A", "B", "B", "A", "A")
)
df_layout$pw <- df_layout$w * df_layout$size
df_layout$c <- 0.25 * (df_layout$i0 + df_layout$i1 + df_layout$i2 + df_layout$i3)
df_layout$poor <- as.numeric(df_layout$c >= 1/3)
df_layout$ck <- df_layout$c * df_layout$poor

des_layout <- svydesign(
  ids = ~grappe,
  strata = ~strate,
  weights = ~pw,
  data = df_layout,
  nest = TRUE
)

des_domain <- subset(des_layout, region == "A")

h_whole <- svymean(~poor, des_layout)
m0_whole <- svymean(~ck, des_layout)
a_whole <- svyratio(~ck, ~poor, des_layout)

h_domain <- svymean(~poor, des_domain)
m0_domain <- svymean(~ck, des_domain)
a_domain <- svyratio(~ck, ~poor, des_domain)

cat("--- 3. Domain (subset in R) on Stratified Design ---\n")
cat("Whole Design degf:  ", degf(des_layout), "\n")
cat("Domain Design degf: ", degf(des_domain), "\n")
cat("Domain H:  est =", coef(h_domain)[1],  "  var =", SE(h_domain)[1]^2,  "  SE =", SE(h_domain)[1], "\n")
cat("Domain M0: est =", coef(m0_domain)[1], "  var =", SE(m0_domain)[1]^2, "  SE =", SE(m0_domain)[1], "\n")
cat("Domain A:  est =", coef(a_domain)[1],  "  var =", SE(a_domain)[1]^2,  "  SE =", SE(a_domain)[1], "\n\n")

# -----------------------------------------------------------------------------
# 4. Boundary cases for Logit CI (H close to 0 or 1)
# -----------------------------------------------------------------------------
df_edge_low <- data.frame(
  stratum = c(1, 1, 1, 1, 1, 2, 2, 2, 2, 2),
  psu = c(1, 1, 2, 2, 3, 4, 4, 5, 5, 6),
  w = rep(1.0, 10),
  poor = c(1, 0, 0, 0, 0, 0, 0, 0, 0, 0)
)
des_edge_low <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_edge_low, nest = TRUE)
h_low <- svymean(~poor, des_edge_low)
ci_low_logit <- get_ci(svyciprop(~poor, des_edge_low, method = "logit"))
ci_low_xlogit <- get_ci(svyciprop(~poor, des_edge_low, method = "xlogit"))
ci_low_mean <- get_ci(svyciprop(~poor, des_edge_low, method = "mean"))
df_low_val <- degf(des_edge_low)
h_low_val <- coef(h_low)[1]
h_low_se <- SE(h_low)[1]
ci_low_t <- c(h_low_val - qt(0.975, df_low_val) * h_low_se, h_low_val + qt(0.975, df_low_val) * h_low_se)
ci_low_norm <- c(h_low_val - qnorm(0.975) * h_low_se, h_low_val + qnorm(0.975) * h_low_se)

df_edge_high <- data.frame(
  stratum = c(1, 1, 1, 1, 1, 2, 2, 2, 2, 2),
  psu = c(1, 1, 2, 2, 3, 4, 4, 5, 5, 6),
  w = rep(1.0, 10),
  poor = c(0, 1, 1, 1, 1, 1, 1, 1, 1, 1)
)
des_edge_high <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_edge_high, nest = TRUE)
h_high <- svymean(~poor, des_edge_high)
ci_high_logit <- get_ci(svyciprop(~poor, des_edge_high, method = "logit"))
ci_high_xlogit <- get_ci(svyciprop(~poor, des_edge_high, method = "xlogit"))
ci_high_mean <- get_ci(svyciprop(~poor, des_edge_high, method = "mean"))
df_high_val <- degf(des_edge_high)
h_high_val <- coef(h_high)[1]
h_high_se <- SE(h_high)[1]
ci_high_t <- c(h_high_val - qt(0.975, df_high_val) * h_high_se, h_high_val + qt(0.975, df_high_val) * h_high_se)
ci_high_norm <- c(h_high_val - qnorm(0.975) * h_high_se, h_high_val + qnorm(0.975) * h_high_se)

cat("--- 4. Boundary cases for Logit CI ---\n")
cat("Low H est:", h_low_val, "SE:", h_low_se, "degf:", df_low_val, "\n")
cat("Low H CI (logit):   [", ci_low_logit[1], ",", ci_low_logit[2], "]\n")
cat("Low H CI (xlogit):  [", ci_low_xlogit[1], ",", ci_low_xlogit[2], "]\n")
cat("Low H CI (mean):    [", ci_low_mean[1], ",", ci_low_mean[2], "]\n")
cat("Low H CI (t):       [", ci_low_t[1], ",", ci_low_t[2], "]\n")
cat("Low H CI (normal):  [", ci_low_norm[1], ",", ci_low_norm[2], "]\n")
cat("High H est:", h_high_val, "SE:", h_high_se, "degf:", df_high_val, "\n")
cat("High H CI (logit):  [", ci_high_logit[1], ",", ci_high_logit[2], "]\n")
cat("High H CI (xlogit): [", ci_high_xlogit[1], ",", ci_high_xlogit[2], "]\n")
cat("High H CI (mean):   [", ci_high_mean[1], ",", ci_high_mean[2], "]\n")
cat("High H CI (t):      [", ci_high_t[1], ",", ci_high_t[2], "]\n")
cat("High H CI (normal): [", ci_high_norm[1], ",", ci_high_norm[2], "]\n\n")

cat("Core oracle script completed successfully.\n")
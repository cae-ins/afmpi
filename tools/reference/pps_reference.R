# Reference script for PPS designs (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact weighted sums)
# - Standard errors ('se'): 1e-7 (floating-point square root and SYG / Hajek / WR calculation)
# - Degrees of freedom ('df'): 0 (exact integer degrees of freedom: n_psu - n_strata)
# - Brewer vs Hajek approximation tolerance: relative difference ~15-20% on small sample (documented in PLAN.md §14.10)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/pps_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)
k_val <- 0.5

df_pps <- read.csv("tools/reference/data/data_pps.csv", check.names = FALSE)
df_pps$c <- 0.25 * (df_pps$i0 + df_pps$i1 + df_pps$i2 + df_pps$i3)
df_pps$poor <- as.numeric(df_pps$c >= k_val)
df_pps$ck <- df_pps$c * df_pps$poor

# -----------------------------------------------------------------------------
# 1. PPS With Replacement (WR)
# -----------------------------------------------------------------------------
des_wr <- svydesign(
  ids = ~psu,
  strata = ~stratum,
  weights = ~w,
  data = df_pps,
  nest = TRUE
)

h_wr <- svymean(~poor, des_wr)
m0_wr <- svymean(~ck, des_wr)
a_wr <- svyratio(~ck, ~poor, des_wr)
df_wr_val <- degf(des_wr)

# -----------------------------------------------------------------------------
# 2. Sen-Yates-Grundy (SYG) with Joint Inclusion Probabilities
# -----------------------------------------------------------------------------
N_hat <- sum(df_pps$w)
H_val <- coef(h_wr)[[1]]
M0_val <- coef(m0_wr)[[1]]
A_val <- coef(a_wr)[[1]]

# Linearized influence terms normalized by N_hat
z_poor <- df_pps$w * (df_pps$poor - H_val) / N_hat
z_ck   <- df_pps$w * (df_pps$ck - M0_val) / N_hat
z_a    <- df_pps$w * (df_pps$ck - A_val * df_pps$poor) / (H_val * N_hat)

calc_syg_var <- function(z_vec) {
  # H1: P1, P2
  t_P1 <- sum(z_vec[df_pps$stratum == "H1" & df_pps$psu == "P1"])
  t_P2 <- sum(z_vec[df_pps$stratum == "H1" & df_pps$psu == "P2"])
  pi_1 <- 0.2; pi_2 <- 0.4; pi_12 <- 0.05
  v_H1 <- ((pi_1 * pi_2 - pi_12) / pi_12) * (t_P1 - t_P2)^2

  # H2: P3, P4
  t_P3 <- sum(z_vec[df_pps$stratum == "H2" & df_pps$psu == "P3"])
  t_P4 <- sum(z_vec[df_pps$stratum == "H2" & df_pps$psu == "P4"])
  pi_3 <- 0.25; pi_4 <- 0.5; pi_34 <- 0.08
  v_H2 <- ((pi_3 * pi_4 - pi_34) / pi_34) * (t_P3 - t_P4)^2

  return(v_H1 + v_H2)
}

var_H_syg  <- calc_syg_var(z_poor)
var_M0_syg <- calc_syg_var(z_ck)
var_A_syg  <- calc_syg_var(z_a)

se_H_syg  <- sqrt(var_H_syg)
se_M0_syg <- sqrt(var_M0_syg)
se_A_syg  <- sqrt(var_A_syg)

# -----------------------------------------------------------------------------
# 3. Hajek approximation (exact formula)
# -----------------------------------------------------------------------------
calc_hajek_var <- function(z_vec) {
  # Stratum H1
  t_P1 <- sum(z_vec[df_pps$stratum == "H1" & df_pps$psu == "P1"])
  t_P2 <- sum(z_vec[df_pps$stratum == "H1" & df_pps$psu == "P2"])
  pi_1 <- 0.2; pi_2 <- 0.4
  s_denom_1 <- (1 - pi_1) + (1 - pi_2)
  t_star_1 <- ((1 - pi_1) * t_P1 + (1 - pi_2) * t_P2) / s_denom_1
  v_H1 <- (2 / 1) * ((1 - pi_1) * (t_P1 - t_star_1)^2 + (1 - pi_2) * (t_P2 - t_star_1)^2)

  # Stratum H2
  t_P3 <- sum(z_vec[df_pps$stratum == "H2" & df_pps$psu == "P3"])
  t_P4 <- sum(z_vec[df_pps$stratum == "H2" & df_pps$psu == "P4"])
  pi_3 <- 0.25; pi_4 <- 0.5
  s_denom_2 <- (1 - pi_3) + (1 - pi_4)
  t_star_2 <- ((1 - pi_3) * t_P3 + (1 - pi_4) * t_P4) / s_denom_2
  v_H2 <- (2 / 1) * ((1 - pi_3) * (t_P3 - t_star_2)^2 + (1 - pi_4) * (t_P4 - t_star_2)^2)

  return(v_H1 + v_H2)
}

var_H_hajek  <- calc_hajek_var(z_poor)
var_M0_hajek <- calc_hajek_var(z_ck)
var_A_hajek  <- calc_hajek_var(z_a)

se_H_hajek  <- sqrt(var_H_hajek)
se_M0_hajek <- sqrt(var_M0_hajek)
se_A_hajek  <- sqrt(var_A_hajek)

# -----------------------------------------------------------------------------
# 4. Brewer in R survey
# -----------------------------------------------------------------------------
des_brewer <- svydesign(
  ids = ~psu,
  strata = ~stratum,
  pps = "brewer",
  fpc = ~pi,
  data = df_pps
)

h_brewer <- svymean(~poor, des_brewer)
m0_brewer <- svymean(~ck, des_brewer)
a_brewer <- svyratio(~ck, ~poor, des_brewer)

pps_json <- list(
  design = "pps",
  generator = "tests/test_conformity/generate.py::generate_pps",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/pps_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    # With replacement
    list(measure = "H_wr",       k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_wr)[[1]]),      se = as.numeric(SE(h_wr)[[1]]),      df = as.integer(df_wr_val)),
    list(measure = "M0_wr",      k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_wr)[[1]]),     se = as.numeric(SE(m0_wr)[[1]]),     df = as.integer(df_wr_val)),
    list(measure = "A_wr",       k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_wr)[[1]]),      se = as.numeric(SE(a_wr)[[1]]),      df = as.integer(df_wr_val)),
    # SYG
    list(measure = "H_syg",      k = k_val, over = NULL, subgroup = NULL, est = as.numeric(H_val),                se = as.numeric(se_H_syg),           df = as.integer(df_wr_val)),
    list(measure = "M0_syg",     k = k_val, over = NULL, subgroup = NULL, est = as.numeric(M0_val),               se = as.numeric(se_M0_syg),          df = as.integer(df_wr_val)),
    list(measure = "A_syg",      k = k_val, over = NULL, subgroup = NULL, est = as.numeric(A_val),                se = as.numeric(se_A_syg),           df = as.integer(df_wr_val)),
    # Hajek
    list(measure = "H_hajek",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(H_val),                se = as.numeric(se_H_hajek),         df = as.integer(df_wr_val)),
    list(measure = "M0_hajek",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(M0_val),               se = as.numeric(se_M0_hajek),        df = as.integer(df_wr_val)),
    list(measure = "A_hajek",    k = k_val, over = NULL, subgroup = NULL, est = as.numeric(A_val),                se = as.numeric(se_A_hajek),         df = as.integer(df_wr_val)),
    # Brewer
    list(measure = "H_brewer",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(h_brewer)[[1]]),  se = as.numeric(SE(h_brewer)[[1]]),  df = as.integer(df_wr_val)),
    list(measure = "M0_brewer",  k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(m0_brewer)[[1]]), se = as.numeric(SE(m0_brewer)[[1]]), df = as.integer(df_wr_val)),
    list(measure = "A_brewer",   k = k_val, over = NULL, subgroup = NULL, est = as.numeric(coef(a_brewer)[[1]]),  se = as.numeric(SE(a_brewer)[[1]]),  df = as.integer(df_wr_val))
  )
)

write_json(pps_json, "tests/test_conformity/reference/pps.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/pps.json\n")

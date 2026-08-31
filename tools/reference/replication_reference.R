# Reference script for Replication methods (JK1, JKn, BRR, Fay BRR, Bootstrap, SDR) (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact weighted sums)
# - Standard errors ('se'): 1e-7 (floating-point square root and replicate sum of squares)
# - Degrees of freedom ('df'): 0 (exact integer replicate degrees of freedom)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/replication_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)
k_val <- 1/3

meta <- fromJSON("tools/reference/data/replication_meta.json")

run_rep <- function(method_name) {
  m_info <- meta[[method_name]]
  csv_file <- paste0("tools/reference/data/data_rep_", tolower(method_name), ".csv")
  df <- read.csv(csv_file, check.names = FALSE)
  
  rep_cols <- m_info$rep_cols
  scale <- m_info$scale
  rscales <- m_info$rscales
  
  rep_des <- svrepdesign(
    repweights = df[, rep_cols],
    weights = ~w,
    type = "other",
    combined.weights = TRUE,
    scale = scale,
    rscales = rscales,
    mse = TRUE,
    data = df
  )
  
  h_res <- svymean(~poor, rep_des)
  m0_res <- svymean(~ck, rep_des)
  a_res <- svyratio(~ck, ~poor, rep_des)
  df_val <- degf(rep_des)
  
  list(
    H_est = as.numeric(coef(h_res)[[1]]),
    H_se  = as.numeric(SE(h_res)[[1]]),
    M0_est = as.numeric(coef(m0_res)[[1]]),
    M0_se  = as.numeric(SE(m0_res)[[1]]),
    A_est = as.numeric(coef(a_res)[[1]]),
    A_se  = as.numeric(SE(a_res)[[1]]),
    df = as.integer(df_val)
  )
}

res_jk1 <- run_rep("JK1")
res_jk1$df <- 3L
res_jkn <- run_rep("JKn")
res_jkn$df <- 2L
res_brr <- run_rep("BRR")
res_brr$df <- 3L
res_fay <- run_rep("Fay_BRR")
res_fay$df <- 3L
res_boot <- run_rep("bootstrap")
res_boot$df <- 19L
res_sdr <- run_rep("SDR")
res_sdr$df <- 7L

rep_json <- list(
  design = "replication",
  generator = "tests/test_conformity/generate.py::generate_replication",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/replication_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    # JK1
    list(measure = "H_JK1",        k = k_val, over = NULL, subgroup = NULL, est = res_jk1$H_est,  se = res_jk1$H_se,  df = res_jk1$df),
    list(measure = "M0_JK1",       k = k_val, over = NULL, subgroup = NULL, est = res_jk1$M0_est, se = res_jk1$M0_se, df = res_jk1$df),
    list(measure = "A_JK1",        k = k_val, over = NULL, subgroup = NULL, est = res_jk1$A_est,  se = res_jk1$A_se,  df = res_jk1$df),
    # JKn
    list(measure = "H_JKn",        k = k_val, over = NULL, subgroup = NULL, est = res_jkn$H_est,  se = res_jkn$H_se,  df = res_jkn$df),
    list(measure = "M0_JKn",       k = k_val, over = NULL, subgroup = NULL, est = res_jkn$M0_est, se = res_jkn$M0_se, df = res_jkn$df),
    list(measure = "A_JKn",        k = k_val, over = NULL, subgroup = NULL, est = res_jkn$A_est,  se = res_jkn$A_se,  df = res_jkn$df),
    # BRR
    list(measure = "H_BRR",        k = k_val, over = NULL, subgroup = NULL, est = res_brr$H_est,  se = res_brr$H_se,  df = res_brr$df),
    list(measure = "M0_BRR",       k = k_val, over = NULL, subgroup = NULL, est = res_brr$M0_est, se = res_brr$M0_se, df = res_brr$df),
    list(measure = "A_BRR",        k = k_val, over = NULL, subgroup = NULL, est = res_brr$A_est,  se = res_brr$A_se,  df = res_brr$df),
    # Fay BRR
    list(measure = "H_Fay_BRR",    k = k_val, over = NULL, subgroup = NULL, est = res_fay$H_est,  se = res_fay$H_se,  df = res_fay$df),
    list(measure = "M0_Fay_BRR",   k = k_val, over = NULL, subgroup = NULL, est = res_fay$M0_est, se = res_fay$M0_se, df = res_fay$df),
    list(measure = "A_Fay_BRR",    k = k_val, over = NULL, subgroup = NULL, est = res_fay$A_est,  se = res_fay$A_se,  df = res_fay$df),
    # Bootstrap
    list(measure = "H_bootstrap",  k = k_val, over = NULL, subgroup = NULL, est = res_boot$H_est,  se = res_boot$H_se,  df = res_boot$df),
    list(measure = "M0_bootstrap", k = k_val, over = NULL, subgroup = NULL, est = res_boot$M0_est, se = res_boot$M0_se, df = res_boot$df),
    list(measure = "A_bootstrap",  k = k_val, over = NULL, subgroup = NULL, est = res_boot$A_est,  se = res_boot$A_se,  df = res_boot$df),
    # SDR
    list(measure = "H_SDR",        k = k_val, over = NULL, subgroup = NULL, est = res_sdr$H_est,  se = res_sdr$H_se,  df = res_sdr$df),
    list(measure = "M0_SDR",       k = k_val, over = NULL, subgroup = NULL, est = res_sdr$M0_est, se = res_sdr$M0_se, df = res_sdr$df),
    list(measure = "A_SDR",        k = k_val, over = NULL, subgroup = NULL, est = res_sdr$A_est,  se = res_sdr$A_se,  df = res_sdr$df)
  )
)

write_json(rep_json, "tests/test_conformity/reference/replication.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/replication.json\n")

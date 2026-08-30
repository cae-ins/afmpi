# Oracle validation script using R 'survey' package (v4.5+)
# For afmpi stamp (PLAN.md §18) - Bootstrap & SDR Replicate Weights
#
# Execution:
# "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tests/oracle/bootstrap_sdr_oracle.R

suppressPackageStartupMessages(library(survey))

options(digits = 14)

cat("=========================================================\n")
cat("afmpi Oracle Validation Script: Bootstrap & SDR (R survey)\n")
cat("=========================================================\n\n")

if (!file.exists("tests/oracle/data_bootstrap.csv") || !file.exists("tests/oracle/replicate_meta.json")) {
  cat("Generating oracle datasets via Python...\n")
  system2("python", c("tests/oracle/export_oracle_data.py"))
}

meta <- jsonlite::fromJSON("tests/oracle/replicate_meta.json")

run_bootstrap_sdr_oracle <- function(method_name) {
  m_info <- meta[[method_name]]
  csv_file <- paste0("tests/oracle/data_", tolower(method_name), ".csv")
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
  
  h_est <- coef(h_res)[[1]]
  h_se  <- SE(h_res)[[1]]
  
  m0_est <- coef(m0_res)[[1]]
  m0_se  <- SE(m0_res)[[1]]
  
  a_est <- coef(a_res)[[1]]
  a_se  <- SE(a_res)[[1]]
  
  cat(sprintf("--- %s ---\n", method_name))
  cat(sprintf("H:  est = %.14g   var = %.14g   SE = %.14g\n", h_est, h_se^2, h_se))
  cat(sprintf("M0: est = %.14g   var = %.14g   SE = %.14g\n", m0_est, m0_se^2, m0_se))
  cat(sprintf("A:  est = %.14g   var = %.14g   SE = %.14g\n\n", a_est, a_se^2, a_se))
}

run_bootstrap_sdr_oracle("bootstrap")
run_bootstrap_sdr_oracle("SDR")

cat("Bootstrap & SDR oracle script completed successfully.\n")

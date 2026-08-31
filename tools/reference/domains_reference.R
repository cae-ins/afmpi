# Reference script for Domain and Subpopulation estimation (PLAN.md §14.10)
#
# Tolerance justification:
# - Point estimates ('est'): 1e-9 (exact weighted domain estimates)
# - Standard errors ('se'): 1e-7 (floating-point square root and domain variance linearization)
# - Degrees of freedom ('df'): 0 (exact integer domain degrees of freedom: n_psu_domain - n_strata_domain)
#
# Execution:
# & "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" tools/reference/domains_reference.R

suppressPackageStartupMessages({
  library(survey)
  library(jsonlite)
})

options(digits = 14)

dir.create("tests/test_conformity/reference", showWarnings = FALSE, recursive = TRUE)
k_val <- 0.5

df_dom <- read.csv("tools/reference/data/data_domains.csv", check.names = FALSE)
df_dom$c <- 0.25 * (df_dom$i0 + df_dom$i1 + df_dom$i2 + df_dom$i3)
df_dom$poor <- as.numeric(df_dom$c >= k_val)
df_dom$ck <- df_dom$c * df_dom$poor

des_full <- svydesign(ids = ~psu, strata = ~stratum, weights = ~w, data = df_dom, nest = TRUE)

# 1. Domain: region == 'North' (present in 4 PSUs: P1, P3, P4, P6 across 3 strata -> df = 4 - 3 = 1)
des_north <- subset(des_full, region == "North")
h_north <- svymean(~poor, des_north)
m0_north <- svymean(~ck, des_north)
a_north <- svyratio(~ck, ~poor, des_north)
df_north_val <- degf(des_north)

# 2. Domain: region == 'South' (present in 2 PSUs: P2, P5 across 2 strata -> df = 2 - 2 = 0)
des_south <- subset(des_full, region == "South")
h_south <- svymean(~poor, des_south)
m0_south <- svymean(~ck, des_south)
a_south <- svyratio(~ck, ~poor, des_south)
df_south_val <- degf(des_south)

# 3. Small Domain: group == 'G3' (present in only 1 PSU: P6 in stratum S3 -> df = 1 - 1 = 0)
des_g3 <- subset(des_full, group == "G3")
h_g3 <- svymean(~poor, des_g3)
m0_g3 <- svymean(~ck, des_g3)
a_g3 <- svyratio(~ck, ~poor, des_g3)
df_g3_val <- degf(des_g3)

domains_json <- list(
  design = "domains",
  generator = "tests/test_conformity/generate.py::generate_domains",
  generator_seed = 20260830,
  reference_software = "R survey 4.5",
  reference_script = "tools/reference/domains_reference.R",
  produced_on = "2026-08-31",
  tolerance = list(est = 1e-9, se = 1e-7, df = 0),
  values = list(
    # North
    list(measure = "H",  k = k_val, over = "region", subgroup = "North", est = as.numeric(coef(h_north)[[1]]),  se = as.numeric(SE(h_north)[[1]]),  df = as.integer(df_north_val)),
    list(measure = "M0", k = k_val, over = "region", subgroup = "North", est = as.numeric(coef(m0_north)[[1]]), se = as.numeric(SE(m0_north)[[1]]), df = as.integer(df_north_val)),
    list(measure = "A",  k = k_val, over = "region", subgroup = "North", est = as.numeric(coef(a_north)[[1]]),  se = as.numeric(SE(a_north)[[1]]),  df = as.integer(df_north_val)),
    # South
    list(measure = "H",  k = k_val, over = "region", subgroup = "South", est = as.numeric(coef(h_south)[[1]]),  se = as.numeric(SE(h_south)[[1]]),  df = as.integer(df_south_val)),
    list(measure = "M0", k = k_val, over = "region", subgroup = "South", est = as.numeric(coef(m0_south)[[1]]), se = as.numeric(SE(m0_south)[[1]]), df = as.integer(df_south_val)),
    list(measure = "A",  k = k_val, over = "region", subgroup = "South", est = as.numeric(coef(a_south)[[1]]),  se = as.numeric(SE(a_south)[[1]]),  df = as.integer(df_south_val)),
    # Small group G3
    list(measure = "H",  k = k_val, over = "group",  subgroup = "G3",    est = as.numeric(coef(h_g3)[[1]]),     se = as.numeric(SE(h_g3)[[1]]),     df = as.integer(df_g3_val)),
    list(measure = "M0", k = k_val, over = "group",  subgroup = "G3",    est = as.numeric(coef(m0_g3)[[1]]),    se = as.numeric(SE(m0_g3)[[1]]),    df = as.integer(df_g3_val)),
    list(measure = "A",  k = k_val, over = "group",  subgroup = "G3",    est = as.numeric(coef(a_g3)[[1]]),     se = as.numeric(SE(a_g3)[[1]]),     df = as.integer(df_g3_val))
  )
)

write_json(domains_json, "tests/test_conformity/reference/domains.json", pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 14)
cat("Wrote tests/test_conformity/reference/domains.json\n")

* Stata Reference Script: Data Limits (extreme weights and missing values) (PLAN.md §14.10)
* Tool: Stata 17/18

version 17
clear all
set more off

* 1. Extreme weights
import delimited "tools/reference/data/data_extreme_weights.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 0.5)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)
svyset psu_id [pweight = w], strata(stratum_id)
svy: mean poor ck

* 2. Missing values - listwise deletion
import delimited "tools/reference/data/data_missing_values.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 0.5)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)
svyset psu_id [pweight = w], strata(stratum_id)
svy, subpop(!missing(i0, i1, i2, i3)): mean poor ck

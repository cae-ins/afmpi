* Stata Reference Script: PPS Designs (PLAN.md §14.10)
* Tool: Stata 17/18 svyset

version 17
clear all
set more off

import delimited "tools/reference/data/data_pps.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 0.5)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)

* 1. PPS with replacement
svyset psu_id [pweight = w], strata(stratum_id)
svy: mean poor ck

* 2. PPS without replacement (Brewer approximation)
* Stata svyset with fpc as sampling probability
svyset psu_id [pweight = w], strata(stratum_id) fpc(pi)
svy: mean poor ck

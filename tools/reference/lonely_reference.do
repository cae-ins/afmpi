* Stata Reference Script: Lonely PSU Policies (PLAN.md §14.10)
* Tool: Stata 17/18 svyset singleunit options

version 17
clear all
set more off

import delimited "tools/reference/data/data_lonely_psu.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 0.5)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)

* 1. singleunit(certainty)
svyset psu_id [pweight = w], strata(stratum_id) singleunit(certainty)
svy: mean poor ck

* 2. singleunit(scaled) -> corresponds to adjust / centered
svyset psu_id [pweight = w], strata(stratum_id) singleunit(scaled)
svy: mean poor ck

* 3. singleunit(centered)
svyset psu_id [pweight = w], strata(stratum_id) singleunit(centered)
svy: mean poor ck

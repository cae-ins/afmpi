* Stata Reference Script: Domains and Subpopulations (PLAN.md §14.10)
* Tool: Stata 17/18 svy, subpop()

version 17
clear all
set more off

import delimited "tools/reference/data/data_domains.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 0.5)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)

generate byte is_north = (region == "North")
generate byte is_south = (region == "South")
generate byte is_g3    = (group == "G3")

svyset psu_id [pweight = w], strata(stratum_id)

* 1. Subpop North
svy, subpop(is_north): mean poor ck

* 2. Subpop South
svy, subpop(is_south): mean poor ck

* 3. Subpop G3
svy, subpop(is_g3): mean poor ck

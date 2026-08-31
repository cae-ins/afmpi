* Stata Reference Script: AF Limits (PLAN.md §14.10)
* Tool: Stata 17/18

version 17
clear all
set more off

* 1. Zero poor
import delimited "tools/reference/data/data_af_zero_poor.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 1/3)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)
svyset psu_id [pweight = w], strata(stratum_id)
svy: mean poor ck

* 2. All poor
import delimited "tools/reference/data/data_af_all_poor.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 1/3)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)
svyset psu_id [pweight = w], strata(stratum_id)
svy: mean poor ck

* 3. Mixed k=0 and k=1
import delimited "tools/reference/data/data_af_mixed.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor_k0 = (c >= 0.0)
generate double ck_k0 = c * poor_k0
generate byte poor_k1 = (c >= 1.0)
generate double ck_k1 = c * poor_k1
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)
svyset psu_id [pweight = w], strata(stratum_id)
svy: mean poor_k0 ck_k0
svy: mean poor_k1 ck_k1

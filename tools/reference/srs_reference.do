* Stata Reference Script: SRS and Stratified SRS (PLAN.md §14.10)
* Tool: Stata 17/18 with mpitb (Nicolai Suppa) or svy: mean

version 17
clear all
set more off

* -----------------------------------------------------------------------------
* 1. Simple Random Sampling (SRS)
* -----------------------------------------------------------------------------
import delimited "tools/reference/data/data_srs.csv", clear
generate double pw = w * size
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 1/3)
generate double ck = c * poor

svyset _n [pweight = pw]
svy: mean poor ck
estat sd

* mpitb alternative:
* mpitb i0 i1 i2 i3 [pweight = pw], k(33.33333333333333)

* -----------------------------------------------------------------------------
* 2. Stratified Simple Random Sampling
* -----------------------------------------------------------------------------
import delimited "tools/reference/data/data_stratified_srs.csv", clear
generate double pw = w * size
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 1/3)
generate double ck = c * poor
encode stratum, generate(stratum_id)

svyset _n [pweight = pw], strata(stratum_id)
svy: mean poor ck
estat sd

* mpitb alternative:
* mpitb i0 i1 i2 i3 [pweight = pw], strata(stratum_id) k(33.33333333333333)

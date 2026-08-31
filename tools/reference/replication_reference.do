* Stata Reference Script: Replication Methods (PLAN.md §14.10)
* Tool: Stata 17/18 svyset with bsrweights, jkrweights, brrweights

version 17
clear all
set more off

* 1. BRR / Fay
import delimited "tools/reference/data/data_rep_brr.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 1/3)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)

* Using generated replicate weights __afmpi_repwgt_*
svyset [pweight = w], brrweight(__afmpi_repwgt_*)
svy: mean poor ck

* 2. JKn
import delimited "tools/reference/data/data_rep_jkn.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 1/3)
generate double ck = c * poor
svyset [pweight = w], jkrweight(__afmpi_repwgt_*, multiplier(0.5))
svy: mean poor ck

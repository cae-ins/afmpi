* Stata Reference Script: Multi-Stage with FPC (PLAN.md §14.10)
* Tool: Stata 17/18 svyset multi-stage with FPC

version 17
clear all
set more off

* -----------------------------------------------------------------------------
* 1. 2-Stage Design with FPC at each stage (f1=0.5, f2=0.25)
* -----------------------------------------------------------------------------
import delimited "tools/reference/data/data_multistage_fpc.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 0.5)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)
encode ssu, generate(ssu_id)

* In Stata, fpc can be sampling fraction
svyset psu_id [pweight = w], strata(stratum_id) fpc(f1) || ssu_id, fpc(f2)
svy: mean poor ck

* -----------------------------------------------------------------------------
* 2. 2-Stage Design with Stage 1 Census (f1=1.0, f2=0.5)
* -----------------------------------------------------------------------------
import delimited "tools/reference/data/data_multistage_census.csv", clear
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 0.5)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)
encode ssu, generate(ssu_id)

svyset psu_id [pweight = w], strata(stratum_id) fpc(f1) || ssu_id, fpc(f2)
svy: mean poor ck

* Stata Reference Script: Cluster and Stratified Cluster (PLAN.md §14.10)
* Tool: Stata 17/18 with mpitb or svy: mean

version 17
clear all
set more off

* -----------------------------------------------------------------------------
* 1. 1-Stage Cluster Design (8 PSUs)
* -----------------------------------------------------------------------------
import delimited "tools/reference/data/data_cluster_1stage.csv", clear
generate double pw = w * size
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 1/3)
generate double ck = c * poor
encode psu, generate(psu_id)

svyset psu_id [pweight = pw]
svy: mean poor ck

* -----------------------------------------------------------------------------
* 2. Stratified Cluster Design (3 strata, 9 PSUs)
* -----------------------------------------------------------------------------
import delimited "tools/reference/data/data_stratified_cluster.csv", clear
generate double pw = w * size
generate double c = 0.25 * (i0 + i1 + i2 + i3)
generate byte poor = (c >= 1/3)
generate double ck = c * poor
encode stratum, generate(stratum_id)
encode psu, generate(psu_id)

svyset psu_id [pweight = pw], strata(stratum_id)
svy: mean poor ck

* Stata Reference Script: Panel and Overlapping Samples (PLAN.md §14.10)
* Tool: Stata 17/18 svy: mean with lincom

version 17
clear all
set more off

* 1. Perfect panel
import delimited "tools/reference/data/data_perfect_panel.csv", clear
generate double c = 0.5 * (i0 + i1)
generate byte poor = (c >= 0.5)
generate double ck = c * poor

reshape wide poor ck i0 i1 w, i(hhid) j(wave) string
encode stratumt0, generate(stratum_id)
encode clustert0, generate(cluster_id)

svyset cluster_id [pweight = wt0], strata(stratum_id)
svy: mean poort0 poort1
lincom _b[poort1] - _b[poort0]

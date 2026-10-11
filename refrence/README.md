# Project reference sources

This directory contains the nine original PDF reference files supplied for the paneldemand project. The directory name `refrence` follows the project owner's requested spelling. Original filenames and PDF bytes are preserved.

## Source index

| No. | Reference PDF |
| --- | --- |
| 01 | [Wooldridge — Econometric Analysis of Cross Section and Panel Data](./01-Wooldridge-Cross-section-and-Panel-Data.pdf) |
| 02 | [Wooldridge — Introductory Econometrics: A Modern Approach](./02-Introductory_Econometrics_A_Modern_Approach.pdf) |
| 03 | [Wooldridge — Two-Way Fixed Effects and the Two-Way Mundlak Regression](./03-two_way_mundlak-Wooldridge.pdf) |
| 04 | [Wooldridge (2015) — Control Function Methods in Applied Econometrics](./04-The-Journal-of-Human-Resources-2015-apr-28-vol.-50-iss.-2-Control-Function-Methods-in-Applied-Econometrics-Wooldridge-Jeffrey-M.-2015-10.3368_jhr.50.2.420-45983108-libgen.li.pdf) |
| 05 | [Platoni, Sckokai and Moro (2012) — Panel Data Estimation Techniques and Farm-level Data Models](./05-American-Journal-of-Agricultural-Economics-2012-oct-vol.-94-iss.-5-Panel-Data-Estimation-Techniques-and-Farm-level-Data-Models-Platoni-S._-Sckokai-P._-Moro-D.-2012-10.1093_ajae_aas072-25167732-libgen.li.pdf) |
| 06 | [Shonkwiler and Yen (1999) — Two-Step Estimation of a Censored System of Equations](./06-Two-Step-Estimation-of-a-Censored-System-of-Equations-J_-Scott-Shonkwiler-and-Steven-T_-Yen-American-Journal-of-Agricultural-Economics-4-81-10_2307_1244339-173414b26effac345dac66daf01349a2-Anna-s-Archive-1-1-.pdf) |
| 07 | [Food Demand Estimation from Consumption and Expenditure Data: Meat Demand in Nigeria](./07-food-demand-estimation-from-consumption-and-expenditure-data-meat-demand-in-nigeria.pdf) |
| 08 | [A Household-level Demand System Analysis of Nuts in the United States](./08-a-household-level-demand-system-analysis-of-nuts-in-the-united-states.pdf) |
| 09 | [Meyerhoefer, Ranney and Sahn (2005) — Consistent Estimation of Censored Demand Systems Using Panel Data](./09-American-Journal-of-Agricultural-Economics-2005-aug-vol.-87-iss.-3-Consistent-Estimation-of-Censored-Dem...ta-Meyerhoefer-Chad-D._-Ranney-Christine-K._-Sahn-David-E.-2005-10.1111_j.1467-8276.2005.00754.x-42413091-libgen.li.pdf) |

## Guidance for research and coding agents

- Consult the relevant original source before choosing an estimator or implementing model changes. Record the section, equation, or printed page supporting a methodological choice.
- For panel heterogeneity, correlated random effects and Mundlak controls, begin with references 01 and 03.
- For expenditure endogeneity and control functions, consult reference 04 and the applied implementation in reference 07.
- For censored demand systems and zero expenditures, consult references 06 and 09; reference 09 addresses panel data.
- References 05, 07 and 08 provide additional applied demand and panel-estimation context. Identify the actual demand-system specification used in each paper before transferring its implementation.
- To search a PDF locally, extract its text with `pdftotext -layout <source.pdf> <temporary.txt>`, then search with `rg`. Use a PDF viewer or rendered pages for mathematical notation that does not extract correctly.
- Keep temporary text extractions outside this directory. These source PDFs are references, not executable code or a statement that every method in them has been adopted by this project.

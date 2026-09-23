# Standards and source policy

CleanroomX separates standards-defined classification from engineering airflow and HVAC inputs.

## Primary references

- ISO 14644-1:2015 — Cleanrooms and associated controlled environments — Part 1: Classification of air cleanliness by particle concentration.
  Official page: https://www.iso.org/standard/53394.html
- ISO 14644-4:2022 — Cleanrooms and associated controlled environments — Part 4: Design, construction and start-up.
  Official page: https://www.iso.org/standard/72379.html
- ASHRAE Design Guide for Cleanrooms: Fundamentals, Systems, and Performance.
  Official page: https://www.ashrae.org/technical-resources/bookstore/ashrae-design-guide-for-cleanrooms
- 2025 ASHRAE Handbook—Fundamentals, Chapter 1, Psychrometrics.
  Official page: https://handbook.ashrae.org/Handbooks/F25/SI/F25_Ch01/F25_Ch01_si.aspx
- 2025 ASHRAE Handbook—Fundamentals, Chapter 21, Duct Design.
  Official handbook page: https://www.ashrae.org/technical-resources/ashrae-handbook
- ASHRAE Duct Fitting Database — reference source for fitting loss coefficients.
  Official page: https://www.ashrae.org/technical-resources/bookstore/duct-fitting-database

## Implementation policy

The software does not infer a universal fixed ACH from an ISO cleanliness class. Numeric project requirements remain explicit inputs.

Copyrighted standards text is not bundled with the repository. Detailed rule packs should be implemented only from appropriately licensed material, public authoritative requirements, or user-entered project criteria.

The duct pressure-loss model implements general Darcy-Weisbach/Colebrook relationships. Air properties, roughness, geometry, section airflow, and local loss coefficients remain explicit project inputs. CleanroomX does not bundle proprietary ASHRAE fitting-coefficient tables.

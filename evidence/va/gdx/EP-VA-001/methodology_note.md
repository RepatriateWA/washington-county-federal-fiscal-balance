# EP-VA-001 Methodology Note

## Source and Scope
The source domain is the U.S. Department of Veterans Affairs Geographic
Distribution of Expenditures (GDX) series for all 39 Washington counties.

## FY2015–FY2023
These years use the legacy `WA` worksheet structure. Published expenditure
amounts are in thousands of dollars. The normalized database preserves the
high-precision source value and source unit while also storing dollars.

## FY2024
FY2024 uses separate `County Direct Exp` and `County Indirect Exp` tables.
Direct and Indirect classifications remain explicit in the database.

## Source Blanks
Blank FY2024 component cells are preserved as NULL, not silently converted
to zero. Control totals are numeric and component reconciliations pass.

## County Control
FY2015–FY2023 use `Total Expenditure`.
FY2024 uses `Total Direct Expenditure + Total Indirect Expenditure`.

## USAspending Overlap Warning
This package does not establish additivity with USAspending-derived VA
activity. An explicit source-control and deduplication methodology is required
before combining the two domains.

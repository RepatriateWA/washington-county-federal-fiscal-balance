

AUDIT 1

SELECT
    fiscal_year,
    state_name,
    tax_category,
    gross_collections_thousands,
    source_file
FROM irs.state_collections
WHERE state_name = 'Washington'
  AND tax_category = 'Total'
ORDER BY fiscal_year;


AUDIT 2

SELECT
    fiscal_year,
    COUNT(DISTINCT state_id) AS states_loaded
FROM irs.state_collections
WHERE tax_category='Total'
GROUP BY fiscal_year
ORDER BY fiscal_year;

AUDIT 3

SELECT
    fiscal_year,
    state_name,
    tax_category,
    COUNT(*)
FROM irs.state_collections
GROUP BY fiscal_year,state_name,tax_category
HAVING COUNT(*)>1;


AUDIT 4

SELECT
    fiscal_year,
    tax_category,
    COUNT(*)
FROM irs.state_collections
GROUP BY fiscal_year,tax_category
ORDER BY fiscal_year,tax_category;


AUDIT 5

SELECT
    fiscal_year,
    gross_collections_thousands
FROM irs.state_collections
WHERE state_name='Washington'
  AND tax_category='Total'
ORDER BY fiscal_year;




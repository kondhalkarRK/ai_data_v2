from app.core.config import Industry
from app.services.security.region_scope import RegionScope, apply_region_sql

queries = [
    "SELECT dealer_id, dealer_name, city FROM automotive.dim_dealer ORDER BY dealer_name",
    "SELECT dealer_id, dealer_name, city FROM automotive.dim_dealer WHERE dealer_id = ANY(:ids)",
    "SELECT s.sales_person_id, s.first_name, s.last_name, s.active FROM automotive.dim_salesman s WHERE s.sales_person_id IN (SELECT DISTINCT sales_person_id FROM automotive.fact_sales WHERE dealer_id = :d) ORDER BY s.first_name, s.last_name",
]

scope = RegionScope(unrestricted=False, zones=("North",))
for i, sql in enumerate(queries, 1):
    out = apply_region_sql(sql, Industry.AUTOMOTIVE, scope)
    print(f'--- QUERY {i} ---')
    print(out)
    print()

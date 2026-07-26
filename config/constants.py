"""
config/constants.py
"""
# ─────────────────────────────────────────────────────────────────
# KPI ENGINE — column candidates
# ─────────────────────────────────────────────────────────────────
_REV_CANDIDATES    = ["revenue","sales_amount","revenue_value","turnover","sale_price",
                      "price","amount","total","value"]
_VOL_CANDIDATES    = ["units_sold","quantity","vehicle_sales","sales_volume","units","count","qty"]
_DATE_CANDIDATES   = ["date","month","quarter","year","sale_date","order_date","transaction_date"]
_SEG_CANDIDATES    = ["segment","category","type","car_type","vehicle_type","class"]
_MODEL_CANDIDATES  = ["model","vehicle_model","product_name","make","brand","car_model"]
_REGION_CANDIDATES = ["region","territory","state","country","area","zone","city"]
_SALES_CANDIDATES  = ["salesperson","sales_person","sales_rep","agent",
                      "seller","employee","staff","rep"]
_MKTSH_CANDIDATES  = ["market_share","marketshare","share"]
_FIRST_NAME_CANDIDATES = ["first_name","firstname","fname","first"]
_LAST_NAME_CANDIDATES  = ["last_name","lastname","lname","last","surname"]

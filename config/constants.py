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

# ─────────────────────────────────────────────────────────────────
# Conversation
# ─────────────────────────────────────────────────────────────────
MAX_CONVERSATION_TURNS = 10
FOLLOWUP_TRIGGER_TOKENS = [
    "same", "now", "also", "but", "only",
    "filter", "instead", "what about",
    "how about", "additionally", "too",
    "and what", "show only", "just",
]
MAX_FOLLOWUP_QUESTION_WORDS = 8

# OOB Guard
OOB_PATTERNS = [
    r"\bwrite\s+(me\s+)?code\b",
    r"\bdelete\s+(the\s+)?data\b",
    r"\bdrop\s+table\b",
    r"\binsert\s+into\b",
    r"\bpredict\s+future\b",
    r"\bml\s+model\b",
    r"\btrain\s+(a\s+)?model\b",
]

# Evidence
EXECUTION_PATHS = ["deterministic", "fallback", "cache"]
MAX_EVIDENCE_HISTORY = 20

# Registry
METRIC_REGISTRY_PATH = "semantic/metric_registry.yaml"

# Badges
BADGE_DETERMINISTIC = {
    "icon": "✅",
    "label": "Deterministic",
    "colour": "green",
}
BADGE_FALLBACK = {
    "icon": "⚠️",
    "label": "AI Generated",
    "colour": "orange",
}
BADGE_CACHED = {
    "icon": "🔒",
    "label": "Cached",
    "colour": "blue",
}
BADGE_OOB = {
    "icon": "🚫",
    "label": "Out of Scope",
    "colour": "red",
}

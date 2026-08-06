"""
config/constants.py
"""
# ─────────────────────────────────────────────────────────────────
# KPI ENGINE — column candidates
# ─────────────────────────────────────────────────────────────────
_REV_CANDIDATES    = ["total_sales","revenue","sales_amount","revenue_value","turnover",
                      "sale_price","amount","sales_value"]
_VOL_CANDIDATES    = ["order_qty","units_sold","quantity","vehicle_sales","sales_volume","qty"]
_DATE_CANDIDATES   = ["sales_date","date","month","quarter","year","sale_date","order_date","transaction_date"]
_SEG_CANDIDATES    = ["car_type","segment","category","type","vehicle_type","class"]
_MODEL_CANDIDATES  = ["model","vehicle_model","product_name","car_model","carline_name"]
_REGION_CANDIDATES = ["region_name","region","territory","state","area","zone","city"]
_SALES_CANDIDATES  = ["salesperson","sales_person","sales_rep","agent",
                      "seller","employee","staff","rep"]
_MKTSH_CANDIDATES  = ["market_share","marketshare","share"]
_FIRST_NAME_CANDIDATES = ["first_name","firstname","fname"]
_LAST_NAME_CANDIDATES  = ["last_name","lastname","lname","surname"]

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

# OOB Guard — destructive + lifestyle / off-domain chat
OOB_PATTERNS = [
    r"\bwrite\s+(me\s+)?code\b",
    r"\bdelete\s+(the\s+)?data\b",
    r"\bdrop\s+table\b",
    r"\binsert\s+into\b",
    r"\bpredict\s+future\b",
    r"\bml\s+model\b",
    r"\btrain\s+(a\s+)?model\b",
    # Lifestyle / chit-chat — redirect politely to data questions
    r"\b(dinner|lunch|breakfast|brunch|recipe|cook|eat|food|restaurant)\b",
    r"\b(weather|joke|movie|song|music|football|cricket|news)\b",
    r"\bplan\s+for\s+(dinner|lunch|tonight|weekend)\b",
    r"\bwhat\s+should\s+i\s+(eat|cook|wear|do)\b",
    r"\b(tell\s+me\s+a\s+joke|how\s+are\s+you\s+feeling)\b",
]

# Evidence
EXECUTION_PATHS = ["deterministic", "fallback", "cache"]
MAX_EVIDENCE_HISTORY = 20

# OKF business-document RAG — disabled until re-wired (see features/okf_knowledge/)
OKF_ENABLED = False

# Narration — rule-based default for speed/cost; LLM only when user asks explain/why
NARRATION_USE_LLM = False
NARRATION_MAX_COMPLETION_TOKENS = 400
NARRATION_MAX_SAMPLE_ROWS = 12

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

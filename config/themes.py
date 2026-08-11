"""
config/themes.py
Theme overlays for Light / Dark / AI appearance modes.
Base styles in styles.py are Dark; Light and AI inject overrides.
"""

LIGHT_THEME_CSS = r"""
/* ═══ LIGHT MODE ═══ */
:root{
  --bg:#f4f7fb;--bg-2:#eef2f7;--panel:#ffffff;--panel-2:#f8fafc;
  --primary:#4f46e5;--secondary:#7c3aed;--success:#059669;--warn:#d97706;--danger:#dc2626;
  --text:#0f172a;--subtext:#475569;--border:rgba(15,23,42,0.10);
  --color-primary:#4f46e5;
  --color-primary-bg:rgba(79,70,229,0.08);
  --color-primary-border:rgba(79,70,229,0.18);
  --color-success:#059669;
  --color-success-bg:rgba(5,150,105,0.08);
  --color-warning:#d97706;
  --color-warning-bg:rgba(217,119,6,0.08);
  --color-danger:#dc2626;
  --color-danger-bg:rgba(220,38,38,0.08);
  --color-surface:rgba(255,255,255,0.92);
  --color-surface-2:rgba(241,245,249,0.95);
  --color-border:rgba(15,23,42,0.10);
  --color-text-primary:#0f172a;
  --color-text-secondary:#475569;
  --color-text-muted:#64748b;
}
html,body,#root,div[role="main"],.stApp,.block-container{
  background:
    radial-gradient(ellipse at 15% 10%, rgba(79,70,229,0.06) 0%, transparent 45%),
    radial-gradient(ellipse at 85% 0%, rgba(14,165,233,0.05) 0%, transparent 40%),
    linear-gradient(160deg,#f8fafc,#eef2f7 55%,#f1f5f9) !important;
  color:#0f172a !important;
}

/* Global readable text (overrides dark-theme silver fonts) */
.stApp p,.stApp li,.stApp label,.stApp span.st-emotion-cache,
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stMarkdownContainer"] li,
.stApp [data-testid="stMarkdownContainer"] span,
.stApp [data-testid="stWidgetLabel"] label,
.stApp [data-testid="stCaptionContainer"],
.stApp .stCaption,
.stApp small,
.stApp .stAlert p{
  color:#1e293b !important;
}
.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6{
  color:#0f172a !important;
}

[data-testid="stHeader"]{border-bottom:1px solid rgba(15,23,42,.08) !important;}
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child{
  background:linear-gradient(180deg,#ffffff 0%,#f1f5f9 100%) !important;
  border-right:1px solid rgba(15,23,42,.08) !important;
  color:#0f172a !important;
}

/* Sidebar text — force dark on light surfaces */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] li,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] label,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] small{
  color:#1e293b !important;
}
[data-testid="stSidebar"] .sb-title{
  color:#b45309 !important;
}
[data-testid="stSidebar"] .sb-label{
  color:#64748b !important;
}
[data-testid="stSidebar"] .sb-value{
  font-weight:700 !important;
}
[data-testid="stSidebar"] .sidebar-hero-title{
  color:#0f172a !important;
}
[data-testid="stSidebar"] .sidebar-hero-sub{
  color:#475569 !important;
}
[data-testid="stSidebar"] .sidebar-pill,
[data-testid="stSidebar"] .small-badge{
  color:#1e293b !important;
  background:rgba(15,23,42,0.05) !important;
  border-color:rgba(15,23,42,0.10) !important;
}
[data-testid="stSidebar"] .stExpander summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary p,
[data-testid="stSidebar"] details summary{
  color:#1e293b !important;
}
[data-testid="stSidebar"] div[data-baseweb="select"] *,
[data-testid="stSidebar"] div[data-baseweb="select"] > div{
  color:#0f172a !important;
}

.stButton > button{
  background:linear-gradient(135deg,rgba(79,70,229,0.10),rgba(124,58,237,0.08)) !important;
  border:1px solid rgba(79,70,229,0.28) !important;
  color:#3730a3 !important;
  box-shadow:0 1px 4px rgba(15,23,42,0.06) !important;
}
.stButton > button:hover{
  background:rgba(79,70,229,0.16) !important;
  color:#312e81 !important;
}
button[kind="primary"],.stButton > button[kind="primary"]{
  background:linear-gradient(135deg,#4f46e5,#7c3aed) !important;
  border:1px solid rgba(79,70,229,0.5) !important;
  color:#fff !important;
}
[data-testid="stSidebar"] .stButton > button{
  background:#fff !important;
  border:1px solid rgba(15,23,42,0.12) !important;
  color:#334155 !important;
}
[data-testid="stSidebar"] div[class*="st-key-sidebar_cache"] button{
  color:#047857 !important;
  border-color:rgba(5,150,105,0.35) !important;
  background:rgba(5,150,105,0.08) !important;
}
[data-testid="stSidebar"] div[class*="st-key-sidebar_clear_views"] button{
  color:#b91c1c !important;
  border-color:rgba(220,38,38,0.3) !important;
  background:rgba(220,38,38,0.06) !important;
}
.sidebar-hero{
  background:linear-gradient(135deg,rgba(79,70,229,0.10),rgba(14,165,233,0.08)) !important;
  border:1px solid rgba(15,23,42,0.08) !important;
}
.brand-header,.brand-header-left{
  background:linear-gradient(115deg,rgba(255,255,255,0.95),rgba(241,245,249,0.9)) !important;
  border:1px solid rgba(15,23,42,0.08) !important;
  box-shadow:0 8px 24px rgba(15,23,42,0.06) !important;
}
.brand-eyebrow{color:#b45309 !important;text-shadow:none !important;}
.brand-tagline{color:#475569 !important;}
.brand-pill,.brand-pill-inline{
  background:linear-gradient(90deg,#4f46e5,#7c3aed) !important;
  color:#fff !important;
  border-color:transparent !important;
}
.glass-card,.hero-card,.kpi-card,.status-card,
.card-chat,.card-query,.trust-score-card,.cgpt-assistant-card,
.kpi-chart-card,.stat-card,.dq-stat-box{
  background:#ffffff !important;
  border:1px solid rgba(15,23,42,0.08) !important;
  color:#0f172a !important;
  box-shadow:0 6px 20px rgba(15,23,42,0.05) !important;
}
.kpi-card{
  background:linear-gradient(145deg,#ffffff,#f8fafc) !important;
}
.kpi-card .kv,.kpi-card .kpi-value{color:#0f172a !important;-webkit-text-fill-color:#0f172a !important;}
.kpi-card .kl,.kpi-card .kpi-label{color:#64748b !important;}
.kpi-card .ks,.kpi-card .kpi-sub,.hero-sub{color:#475569 !important;}
.kpi-section-title{
  background:none !important;
  -webkit-text-fill-color:#0f172a !important;
  color:#0f172a !important;
}
.kpi-section-sub,.stat-card .sl,.dq-stat-box .sl{color:#64748b !important;}
.stat-card .sv,.dq-stat-box .sv{color:#4f46e5 !important;}
.hero-title{color:#0f172a !important;}
.cgpt-user-bubble{
  background:linear-gradient(145deg,#eef2ff,#e0e7ff) !important;
  border:1px solid rgba(79,70,229,0.18) !important;
  color:#1e1b4b !important;
}
.cgpt-welcome-title{
  background:linear-gradient(90deg,#0f172a,#4338ca) !important;
  -webkit-background-clip:text !important;background-clip:text !important;
  color:transparent !important;
}
.cgpt-welcome-sub,.chat-reply-text,.finding-bullet,
.assistant-card,.assistant-bubble,
.narration-card,.narration-headline,.narration-body,.narration-recommendation{
  color:#1e293b !important;
}
.narration-card{
  background:#fff !important;
  border:1px solid rgba(15,23,42,0.08) !important;
}
.cgpt-input-wrap,.cgpt-composer{
  background:#fff !important;
  border:1px solid rgba(15,23,42,0.12) !important;
  box-shadow:0 8px 24px rgba(15,23,42,0.06) !important;
}
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-baseweb="select"] > div,
div[data-testid="stNumberInput"] input{
  background:#ffffff !important;
  color:#0f172a !important;
  border-color:rgba(15,23,42,0.14) !important;
}
div[data-baseweb="select"] span,
div[data-baseweb="select"] div{
  color:#0f172a !important;
}

/* Dataframes — force light readable cells (all tabs) */
div[data-testid="stDataFrame"] div[role="grid"],
div[data-testid="stDataFrame"] div[role="grid"] *,
div[data-testid="stDataFrame"] div[role="row"],
div[data-testid="stDataFrame"] div[role="row"] > div,
div[data-testid="stDataFrame"] div[role="gridcell"],
div[data-testid="stDataFrame"] div[role="columnheader"],
div[data-testid="stDataFrame"] table,
div[data-testid="stDataFrame"] th,
div[data-testid="stDataFrame"] td,
div[data-testid="stDataFrame"] thead th,
div[data-testid="stDataFrame"] tbody td,
div[data-testid="stDataFrame"] div.stDataFrame,
div[data-testid="stDataFrame"] div.stDataFrame > div{
  background:#ffffff !important;
  color:#0f172a !important;
  border-color:rgba(15,23,42,0.08) !important;
}
div[data-testid="stDataFrame"] thead th,
div[data-testid="stDataFrame"] div[role="columnheader"]{
  background:#f1f5f9 !important;
  color:#0f172a !important;
  font-weight:700 !important;
}

[data-testid="stMetricValue"]{color:#4f46e5 !important;}
[data-testid="stMetricLabel"]{color:#475569 !important;}
[data-testid="stTabs"] button,
[data-testid="stTabs"] [role="tab"]{
  color:#475569 !important;
}
[data-testid="stTabs"] button[aria-selected="true"],
[data-testid="stTabs"] [aria-selected="true"]{
  color:#4f46e5 !important;
}
div[data-testid="stExpander"] summary,
div[data-testid="stExpander"] summary p{
  color:#1e293b !important;
}
div[data-testid="stRadio"] label,
div[data-testid="stRadio"] p,
div[role="radiogroup"] label,
div[role="radiogroup"] p{
  color:#1e293b !important;
}
.ai-animated-bg{opacity:0.22 !important;filter:saturate(0.7) brightness(1.3);}
.ai-animated-bg .glow{opacity:0.18 !important;}
.sb-divider{border-color:rgba(15,23,42,0.08) !important;opacity:1 !important;}
.chat-results-label,.cgpt-meta,.cgpt-meta-right{color:#64748b !important;}
.code-card,pre,code{color:#1e293b !important;background:rgba(15,23,42,0.04) !important;}
.trust-title,.trust-score-card,.trust-score-summary{color:#334155 !important;}
.sem-ctx-expander-hint{color:#047857 !important;background:rgba(5,150,105,0.08) !important;}
.conv-context-banner{color:#1e293b !important;background:rgba(79,70,229,0.08) !important;}
.status-card{background:#fff !important;color:#0f172a !important;border-color:rgba(15,23,42,0.1) !important;}
.status-card code{color:#4f46e5 !important;background:rgba(79,70,229,0.08) !important;}
.join-status-card,.join-info-banner{
  background:#ffffff !important;
  border:1px solid rgba(15,23,42,0.10) !important;
  color:#0f172a !important;
}
.join-status-card .join-status-title{color:#1d4ed8 !important;}
.join-status-card .join-status-desc,
.join-status-card .join-status-meta,
.join-info-banner{color:#334155 !important;}

/* Light hero bar */
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ui_theme"]){
  background:linear-gradient(115deg,rgba(255,255,255,0.98),rgba(241,245,249,0.95)) !important;
  border:1px solid rgba(15,23,42,0.08) !important;
  box-shadow:0 8px 24px rgba(15,23,42,0.05) !important;
}
div[class*="st-key-ui_theme"] div[data-baseweb="select"] > div{
  background:#ffffff !important;
  border:1px solid rgba(15,23,42,0.16) !important;
  color:#0f172a !important;
  min-height:38px !important;
}
div[class*="st-key-ui_theme"] svg{fill:#334155 !important;}
div[class*="st-key-ui_theme"] span,
div[class*="st-key-ui_theme"] div{color:#0f172a !important;}
div[class*="st-key-chat_answer_mode"] div[data-baseweb="select"] > div{
  background:#f8fafc !important;
  border:1px solid rgba(15,23,42,0.14) !important;
  color:#0f172a !important;
}

/* ── Light: tabs, sections, chat shell, decision room ── */
.tab-section-eyebrow{color:#4338ca !important;}
.tab-section-sub{color:#64748b !important;}
.cgpt-chat-shell{
  background:linear-gradient(180deg,#ffffff,#f8fafc) !important;
  border:1px solid rgba(15,23,42,0.10) !important;
  box-shadow:0 8px 24px rgba(15,23,42,0.06) !important;
}
.cgpt-composer{
  background:#ffffff !important;
  border:1px solid rgba(15,23,42,0.12) !important;
  box-shadow:0 4px 16px rgba(15,23,42,0.05) !important;
}
.cgpt-composer-hint{color:#64748b !important;}
.dr-landing-eyebrow{color:#4338ca !important;}
.dr-landing-title{color:#0f172a !important;}
.dr-landing-sub{color:#64748b !important;}
.dr-priority-card{
  background:#ffffff !important;
  border:1px solid rgba(15,23,42,0.10) !important;
}
.dr-priority-title{color:#0f172a !important;}
.dr-priority-summary{color:#64748b !important;}
.dr-pinned-label{color:#4338ca !important;}
.dr-pin-card{
  background:#f8fafc !important;
  border:1px solid rgba(79,70,229,0.18) !important;
}
.dr-pin-headline{color:#0f172a !important;}
.dr-pin-meta{color:#64748b !important;}
.dr-share-link{
  background:rgba(79,70,229,0.08) !important;
  border-color:rgba(79,70,229,0.22) !important;
  color:#3730a3 !important;
}
.dr-icon-actions .stButton > button,
.dr-icon-actions [data-testid="stPopover"] > button{
  background:#ffffff !important;
  border:1px solid rgba(15,23,42,0.14) !important;
  color:#334155 !important;
}

[data-testid="stTabs"] [role="tablist"]{
  background:#f1f5f9 !important;
  border:1px solid rgba(15,23,42,0.08) !important;
}
[data-testid="stTabs"] [role="tabpanel"],
[data-testid="stTabs"] > div > div{
  background:transparent !important;
}
.stTabs [role="tablist"] button{
  color:#64748b !important;
  background:transparent !important;
}
.stTabs [role="tablist"] button[aria-selected="true"]{
  color:#4338ca !important;
  background:#ffffff !important;
  border-bottom:2px solid #4f46e5 !important;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"]{
  background:linear-gradient(145deg,#eef2ff,#e0e7ff) !important;
  color:#1e1b4b !important;
  border:1px solid rgba(79,70,229,0.15) !important;
}
[data-testid="stChatMessage"]:not(:has([data-testid="chatAvatarIcon-user"])) [data-testid="stChatMessageContent"]{
  background:#ffffff !important;
  color:#0f172a !important;
  border:1px solid rgba(15,23,42,0.08) !important;
}

.result-header-bar,.result-stat-pill{
  color:#475569 !important;
}
.badge-semantic,.badge-cached,.badge-fallback,.badge-deterministic{
  color:#334155 !important;
}
.card-query,.card-chat,.card-whatif,.card-surprise{
  background:#ffffff !important;
  border-color:rgba(15,23,42,0.08) !important;
  color:#0f172a !important;
}
.surprise-header,.surprise-highlight,.surprise-rec-title{color:#0f172a !important;}
.finding-bullet{color:#334155 !important;}

[data-testid="stStatusWidget"],
[data-testid="stAlert"],
.stAlert{
  background:#ffffff !important;
  color:#0f172a !important;
  border-color:rgba(15,23,42,0.10) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]{
  background:#ffffff !important;
  border-color:rgba(15,23,42,0.10) !important;
}
section[data-testid="stMain"] > div > div > div > div{
  color:#0f172a;
}

/* Popover / download menus */
[data-testid="stPopoverBody"],
div[data-baseweb="popover"]{
  background:#ffffff !important;
  color:#0f172a !important;
  border:1px solid rgba(15,23,42,0.12) !important;
}
[data-testid="stPopoverBody"] p,
[data-testid="stPopoverBody"] label,
[data-testid="stPopoverBody"] span{color:#0f172a !important;}

/* Plotly + code blocks */
.js-plotly-plot .plotly,.stPlotlyChart{background:#ffffff !important;}
div[data-testid="stCode"] pre,
div[data-testid="stCode"] code{
  background:#f1f5f9 !important;
  color:#0f172a !important;
}

/* KPI / join / preview panels — kill dark grey panels */
.kpi-filter-panel,.kpi-side-panel,.preview-hero,.dq-panel,
[data-testid="stMain"] [data-testid="stVerticalBlock"] > div[style*="background"]{
  background:transparent !important;
}
.stat-card,.dq-stat-box,.kpi-chart-card{
  background:#ffffff !important;
  border:1px solid rgba(15,23,42,0.08) !important;
}
.small-badge,.result-stat-pill{
  background:rgba(79,70,229,0.06) !important;
  color:#4338ca !important;
  border:1px solid rgba(79,70,229,0.12) !important;
}

/* Override dark hero strip from ASK_ALIGN when light */
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ui_theme"]):before{
  background:linear-gradient(90deg,#4f46e5,#7c3aed,#059669,#4f46e5) !important;
}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ui_theme"]){
  background:linear-gradient(115deg,rgba(255,255,255,0.98),rgba(248,250,252,0.96)) !important;
  border:1px solid rgba(15,23,42,0.08) !important;
}
.header-toolbar{color:#0f172a !important;}
"""

AI_THEME_CSS = r"""
/* ═══ AI MODE — classy aurora / glass / motion ═══ */
:root{
  --bg:#020617;--bg-2:#060b1a;--panel:#0a1224;--panel-2:#101a33;
  --primary:#67e8f9;--secondary:#a78bfa;--success:#34d399;--warn:#fbbf24;--danger:#fb7185;
  --text:#f8fafc;--subtext:#94a3b8;--border:rgba(103,232,249,0.14);
  --color-primary:#67e8f9;
  --color-primary-bg:rgba(103,232,249,0.08);
  --color-primary-border:rgba(167,139,250,0.25);
}
html,body,#root,div[role="main"],.stApp,.block-container{
  background:
    radial-gradient(ellipse at 12% 8%, rgba(56,189,248,0.14) 0%, transparent 42%),
    radial-gradient(ellipse at 88% 12%, rgba(167,139,250,0.16) 0%, transparent 45%),
    radial-gradient(ellipse at 50% 100%, rgba(52,211,153,0.08) 0%, transparent 40%),
    linear-gradient(145deg,#020617 0%,#07111f 45%,#0b1328 100%) !important;
}
[data-testid="stSidebar"]{
  background:
    linear-gradient(180deg, rgba(8,15,35,0.96) 0%, rgba(12,20,48,0.98) 100%) !important;
  border-right:1px solid rgba(103,232,249,0.10) !important;
  box-shadow:8px 0 40px rgba(56,189,248,0.05);
}
.brand-header{
  position:relative;overflow:hidden;
  background:linear-gradient(120deg,rgba(15,23,42,0.75),rgba(30,27,75,0.55),rgba(8,47,73,0.55)) !important;
  border:1px solid rgba(103,232,249,0.22) !important;
  box-shadow:0 0 0 1px rgba(167,139,250,0.08), 0 16px 50px rgba(56,189,248,0.12) !important;
  animation:aiHeaderGlow 6s ease-in-out infinite;
}
.brand-header:before{
  content:"";position:absolute;inset:-40% -20%;
  background:linear-gradient(105deg,transparent 30%,rgba(103,232,249,0.18) 50%,transparent 70%);
  animation:aiShimmer 4.5s linear infinite;
  pointer-events:none;
}
.brand-pill{
  background:linear-gradient(90deg,#22d3ee,#a78bfa,#34d399) !important;
  background-size:200% 100% !important;
  animation:aiGradientShift 5s ease infinite !important;
  color:#04101f !important;
  font-weight:800 !important;
  box-shadow:0 0 20px rgba(103,232,249,0.35) !important;
}
.sidebar-hero{
  background:linear-gradient(135deg,rgba(34,211,238,0.12),rgba(167,139,250,0.14)) !important;
  border:1px solid rgba(103,232,249,0.22) !important;
  box-shadow:0 0 28px rgba(167,139,250,0.12);
  position:relative;overflow:hidden;
}
.sidebar-hero:after{
  content:"";position:absolute;width:120px;height:120px;right:-30px;top:-40px;border-radius:50%;
  background:radial-gradient(circle,rgba(103,232,249,0.35),transparent 70%);
  animation:floatGlow 10s ease-in-out infinite;
}
.stButton > button{
  background:linear-gradient(135deg,rgba(34,211,238,0.14),rgba(167,139,250,0.16)) !important;
  border:1px solid rgba(103,232,249,0.28) !important;
  color:#cffafe !important;
  box-shadow:0 0 16px rgba(34,211,238,0.08) !important;
  transition:transform .2s ease, box-shadow .2s ease !important;
}
.stButton > button:hover{
  transform:translateY(-1px);
  box-shadow:0 0 22px rgba(167,139,250,0.28) !important;
  border-color:rgba(167,139,250,0.45) !important;
}
button[kind="primary"],.stButton > button[kind="primary"]{
  background:linear-gradient(135deg,rgba(34,211,238,0.35),rgba(167,139,250,0.4)) !important;
  border:1px solid rgba(103,232,249,0.45) !important;
  color:#ecfeff !important;
  box-shadow:0 0 24px rgba(34,211,238,0.22) !important;
}
.glass-card,.hero-card,.kpi-card,.cgpt-assistant-card,.trust-score-card{
  background:linear-gradient(160deg,rgba(15,23,42,0.72),rgba(30,27,75,0.35)) !important;
  border:1px solid rgba(103,232,249,0.16) !important;
  backdrop-filter:blur(16px) saturate(140%) !important;
  box-shadow:0 12px 40px rgba(2,6,23,0.45), inset 0 1px 0 rgba(255,255,255,0.05) !important;
}
.kpi-card:hover,.hero-card:hover{
  border-color:rgba(167,139,250,0.4) !important;
  box-shadow:0 16px 48px rgba(56,189,248,0.18) !important;
}
.cgpt-user-bubble{
  background:linear-gradient(145deg,rgba(34,211,238,0.18),rgba(167,139,250,0.22)) !important;
  border:1px solid rgba(103,232,249,0.28) !important;
  box-shadow:0 8px 28px rgba(34,211,238,0.12) !important;
}
.cgpt-assistant-avatar{
  animation:cgptPulse 2.8s ease-in-out infinite;
  box-shadow:0 0 22px rgba(103,232,249,0.45) !important;
}
.cgpt-welcome-title{
  background:linear-gradient(90deg,#67e8f9,#c4b5fd,#86efac,#67e8f9) !important;
  background-size:220% auto !important;
  -webkit-background-clip:text !important;background-clip:text !important;
  animation:aiGradientShift 6s linear infinite !important;
}
.cgpt-input-wrap{
  background:linear-gradient(180deg,rgba(15,23,42,0.8),rgba(8,15,35,0.95)) !important;
  border:1px solid rgba(103,232,249,0.28) !important;
  box-shadow:0 0 0 1px rgba(167,139,250,0.08), 0 14px 40px rgba(34,211,238,0.12) !important;
}
.ai-animated-bg{opacity:1 !important;}
.ai-animated-bg .glow{opacity:0.55 !important;filter:blur(100px);}
.ai-animated-bg .g1{background:radial-gradient(circle at 30% 30%, rgba(34,211,238,0.95), transparent 38%) !important;}
.ai-animated-bg .g2{background:radial-gradient(circle at 70% 70%, rgba(167,139,250,0.9), transparent 38%) !important;animation-duration:12s;}
.ai-animated-bg .g3{background:radial-gradient(circle at 50% 50%, rgba(52,211,153,0.8), transparent 40%) !important;animation-duration:14s;}
.ai-animated-bg.theme-bg-ai .g4{
  position:absolute;width:360px;height:360px;left:55%;top:55%;border-radius:50%;
  filter:blur(110px);opacity:0.4;
  background:radial-gradient(circle, rgba(244,114,182,0.7), transparent 45%);
  animation:floatGlow 11s ease-in-out infinite reverse;
}
@keyframes aiShimmer{
  0%{transform:translateX(-40%) rotate(8deg)}
  100%{transform:translateX(40%) rotate(8deg)}
}
@keyframes aiGradientShift{
  0%{background-position:0% 50%}
  50%{background-position:100% 50%}
  100%{background-position:0% 50%}
}
@keyframes aiHeaderGlow{
  0%,100%{box-shadow:0 0 0 1px rgba(167,139,250,0.08), 0 16px 50px rgba(56,189,248,0.10)}
  50%{box-shadow:0 0 0 1px rgba(103,232,249,0.2), 0 18px 60px rgba(167,139,250,0.18)}
}
"""

ASK_ALIGN_CSS = r"""
/* Query tab: keep Run + Clear on one baseline with the text input */
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ask_run_btn"]){
  align-items:flex-end !important;
  gap:0.5rem !important;
}
div[class*="st-key-ask_run_btn"] button,
div[class*="st-key-ask_clear_btn"] button{
  height:2.75rem !important;
  min-height:2.75rem !important;
  margin-bottom:0 !important;
}
div[class*="st-key-ask_question_input"] input{
  min-height:2.75rem !important;
}
div[class*="st-key-ask_run_btn"] button{
  font-size:16px !important;
  padding-top:0 !important;
  padding-bottom:0 !important;
}

/* Unified hero bar: title + pill + theme in one aligned strip */
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ui_theme"]){
  align-items:center !important;
  gap:12px !important;
  padding:14px 18px !important;
  margin:-6px 0 14px 0 !important;
  border-radius:16px !important;
  background:linear-gradient(100deg, rgba(79,124,255,0.14), rgba(124,58,237,0.10) 55%, rgba(0,209,122,0.06)) !important;
  border:1px solid rgba(255,255,255,0.08) !important;
  position:relative;overflow:hidden;
}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ui_theme"]):before{
  content:"";position:absolute;left:0;top:0;width:100%;height:2px;
  background:linear-gradient(90deg,#4f7cff,#7c3aed,#00d17a,#4f7cff);
  background-size:300% 100%;animation:brandSheen 6s linear infinite;
}
.brand-title-stack{padding:2px 0;position:relative;z-index:1;}
.brand-pill-inline{
  display:inline-flex;align-items:center;justify-content:center;
  height:38px;width:100%;box-sizing:border-box;text-align:center;
  position:relative;z-index:1;
}
div[class*="st-key-ui_theme"]{position:relative;z-index:1;}
div[class*="st-key-ui_theme"] div[data-baseweb="select"] > div{
  min-height:38px !important;
  border-radius:999px !important;
  background:linear-gradient(90deg, rgba(79,124,255,.14), rgba(124,58,237,.14)) !important;
  border:1px solid rgba(255,255,255,.12) !important;
  color:#e2e8f0 !important;
  font-weight:700 !important;
  font-size:12px !important;
}
div[class*="st-key-ui_theme"] svg{fill:#e2e8f0 !important;}

/* Chat answer-mode picker inside input bar */
.cgpt-composer{
  display:block;
  background: linear-gradient(180deg, rgba(30,41,59,0.65), rgba(15,23,42,0.9));
  border: 1px solid rgba(148,163,184,0.22);
  border-radius: 16px;
  padding: 8px 10px 6px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.22);
  margin-top: 8px;
}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-chat_answer_mode"]){
  align-items:center !important;
  gap:8px !important;
  margin-bottom:2px !important;
}
div[class*="st-key-chat_answer_mode"] div[data-baseweb="select"] > div{
  min-height:34px !important;
  border-radius:10px !important;
  background:rgba(15,23,42,0.55) !important;
  border:1px solid rgba(148,163,184,0.22) !important;
  font-size:12px !important;
  font-weight:600 !important;
}
"""


def theme_css(theme: str) -> str:
    t = (theme or "dark").lower()
    if t == "light":
        return ASK_ALIGN_CSS + LIGHT_THEME_CSS
    if t == "ai":
        return ASK_ALIGN_CSS + AI_THEME_CSS
    return ASK_ALIGN_CSS


def theme_bg_html(theme: str) -> str:
    t = (theme or "dark").lower()
    if t == "light":
        return """
<div class="ai-animated-bg theme-bg-light">
    <div class="glow g1"></div>
    <div class="glow g2"></div>
</div>
"""
    if t == "ai":
        return """
<div class="ai-animated-bg theme-bg-ai">
    <div class="glow g1"></div>
    <div class="glow g2"></div>
    <div class="glow g3"></div>
    <div class="glow g4"></div>
</div>
"""
    return """
<div class="ai-animated-bg theme-bg-dark">
    <div class="glow g1"></div>
    <div class="glow g2"></div>
    <div class="glow g3"></div>
</div>
"""

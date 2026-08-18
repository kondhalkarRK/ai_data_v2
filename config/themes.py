"""
config/themes.py
Theme overlays for Light / Dark / AI appearance modes.
Base styles in styles.py are Dark; Light and AI inject overrides.
"""

LIGHT_THEME_CSS = r"""
/* ═══ LIGHT MODE — cool, natural, consistent ═══ */
:root{
  --bg:#f3f5f8;--bg-2:#eef1f6;--panel:#ffffff;--panel-2:#f7f8fb;
  --primary:#2563eb;--secondary:#4f46e5;--success:#0f9d6e;--warn:#c2410c;--danger:#dc2626;
  --text:#1b2430;--subtext:#5b6575;--border:rgba(27,36,48,0.10);
  --color-primary:#2563eb;
  --color-primary-bg:rgba(37,99,235,0.08);
  --color-primary-border:rgba(37,99,235,0.18);
  --color-success:#0f9d6e;
  --color-success-bg:rgba(15,157,110,0.08);
  --color-warning:#c2410c;
  --color-warning-bg:rgba(194,65,12,0.08);
  --color-danger:#dc2626;
  --color-danger-bg:rgba(220,38,38,0.08);
  --color-surface:#ffffff;
  --color-surface-2:#f7f8fb;
  --color-border:rgba(27,36,48,0.10);
  --color-text-primary:#1b2430;
  --color-text-secondary:#5b6575;
  --color-text-muted:#7b8494;
}
html,body,#root,div[role="main"],.stApp,.block-container{
  background:
    radial-gradient(ellipse at 12% 0%, rgba(37,99,235,0.045) 0%, transparent 42%),
    linear-gradient(180deg,#f7f8fb 0%, #f3f5f8 100%) !important;
  color:#1b2430 !important;
}
[data-testid="stHeader"]{background:transparent !important;border-bottom:1px solid rgba(27,36,48,.06) !important;}

.stApp p,.stApp li,.stApp label,.stApp span,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stMarkdownContainer"] li,
.stApp [data-testid="stMarkdownContainer"] span,
.stApp [data-testid="stWidgetLabel"] label,
.stApp [data-testid="stCaptionContainer"],
.stApp .stCaption,.stApp small,.stApp .stAlert p{
  color:#1b2430 !important;
}
.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6{color:#1b2430 !important;}
.stApp [data-testid="stCaptionContainer"],.stApp .stCaption,.stApp small{color:#5b6575 !important;}

/* Sidebar — invert the dark “force white text” rule */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child,
section[data-testid="stSidebar"]{
  background:#ffffff !important;
  border:none !important;
  border-right:none !important;
  box-shadow:none !important;
  outline:none !important;
  color:#1b2430 !important;
}
[data-testid="stSidebarContent"],
[data-testid="stSidebarUserContent"]{
  border:none !important;
  box-shadow:none !important;
  outline:none !important;
}
[data-testid="stSidebar"] .block-container,
section[data-testid="stSidebar"] .block-container{
  padding:10px 12px 16px 12px !important;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"]{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.08) !important;
  box-shadow:none !important;
}
[data-testid="stSidebar"] *{color:#1b2430 !important;}
[data-testid="stSidebar"] .sb-join-kicker,
[data-testid="stSidebar"] .sb-join-status,
[data-testid="stSidebar"] .sb-join-status-active,
[data-testid="stSidebar"] .sb-join-status-fallback,
[data-testid="stSidebar"] .sb-join-status-pending,
[data-testid="stSidebar"] .sb-join-status-idle{color:unset !important;}
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] .sb-label,
[data-testid="stSidebar"] .sidebar-hero-sub{color:#5b6575 !important;}
[data-testid="stSidebar"] .sb-title{
  color:#2563eb !important;
  text-shadow:none !important;
  border-bottom-color:rgba(37,99,235,.16) !important;
}
[data-testid="stSidebar"] .sb-value{font-weight:700 !important;}
[data-testid="stSidebar"] .sidebar-hero{
  background:linear-gradient(135deg,rgba(37,99,235,0.08),rgba(14,165,233,0.06)) !important;
  border:1px solid rgba(27,36,48,0.08) !important;
  box-shadow:none !important;
}
[data-testid="stSidebar"] .sidebar-hero-title{color:#1b2430 !important;}
[data-testid="stSidebar"] .sidebar-hero-icon{
  background:linear-gradient(135deg,#2563eb,#4f46e5) !important;
  box-shadow:0 4px 12px rgba(37,99,235,.22) !important;
}
[data-testid="stSidebar"] .sidebar-pill,
[data-testid="stSidebar"] .small-badge{
  color:#1b2430 !important;
  background:rgba(27,36,48,0.04) !important;
  border-color:rgba(27,36,48,0.10) !important;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"]{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.08) !important;
}
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stButton button{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.12) !important;
  color:#334155 !important;
}
[data-testid="stSidebar"] .stButton > button:hover,
[data-testid="stSidebar"] .stButton button:hover{
  background:#f7f8fb !important;
  color:#1b2430 !important;
  border-color:rgba(37,99,235,0.28) !important;
}
[data-testid="stSidebar"] .stProgress > div{background:#e8ecf2 !important;}
[data-testid="stSidebar"] .stProgress > div > div{background:linear-gradient(90deg,#2563eb,#38bdf8) !important;}
[data-testid="stSidebar"] .sb-divider{border-color:rgba(27,36,48,0.08) !important;opacity:1 !important;}
[data-testid="stSidebar"] .sb-upload-wrap{background:rgba(37,99,235,0.04) !important;border-color:rgba(37,99,235,0.16) !important;}
[data-testid="stSidebar"] .sb-upload-wrap .sb-title{color:#1d4ed8 !important;}
[data-testid="stSidebar"] .sb-semantic-wrap .sb-title{color:#4338ca !important;background:rgba(79,70,229,0.08) !important;border-color:rgba(79,70,229,0.16) !important;}
[data-testid="stSidebar"] .sb-views-wrap .sb-title{color:#2563eb !important;}
[data-testid="stSidebar"] .sb-conv-wrap .sb-title{color:#7c3aed !important;}
[data-testid="stSidebar"] .sb-llm-wrap .sb-title{color:#1d4ed8 !important;}
[data-testid="stSidebar"] .sb-join-label{color:#1b2430 !important;}
[data-testid="stSidebar"] div[class*="st-key-sidebar_join_settings"] button{
  background:#ffffff !important;color:#1b2430 !important;
  border:1px solid rgba(27,36,48,0.12) !important;
}

[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ui_theme"]){
  background:transparent !important;
  border:none !important;
  box-shadow:none !important;
  padding:0 !important;
  min-height:0 !important;
  margin:0 0 6px 0 !important;
}
[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ui_theme"]):before{
  display:none !important;
}
.brand-eyebrow{color:#1b2430 !important;text-shadow:none !important;font-weight:750 !important;}
.brand-tagline{color:#5b6575 !important;}
.brand-pill,.brand-pill-inline{
  background:#2563eb !important;color:#fff !important;border-color:transparent !important;
}
.header-toolbar{color:#1b2430 !important;}
.header-toolbar [data-testid="stPopover"] button,
.header-toolbar [data-testid="stPopover"] > button{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.12) !important;
  color:#334155 !important;
}
div[class*="st-key-ui_theme"] div[data-baseweb="select"] > div{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.14) !important;
  color:#1b2430 !important;
  min-height:32px !important;
}
div[class*="st-key-ui_theme"] svg{fill:#334155 !important;}
div[class*="st-key-ui_theme"] span,
div[class*="st-key-ui_theme"] div{color:#1b2430 !important;}

/* Buttons */
.stButton > button{
  background:#ffffff !important;
  border:1px solid rgba(37,99,235,0.22) !important;
  color:#1d4ed8 !important;
  box-shadow:0 1px 2px rgba(27,36,48,0.04) !important;
}
.stButton > button:hover{
  background:rgba(37,99,235,0.06) !important;
  color:#1e3a8a !important;
}
button[kind="primary"],.stButton > button[kind="primary"]{
  background:#2563eb !important;
  border:1px solid #2563eb !important;
  color:#fff !important;
}

/* Surfaces / cards */
.glass-card,.hero-card,.kpi-card,.status-card,
.card-chat,.card-query,.trust-score-card,.cgpt-assistant-card,
.kpi-chart-card,.stat-card,.dq-stat-box,.assistant-card,
.card-whatif,.card-surprise,.card-blocked,.card-oob,.card-clarification,.card-error{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.08) !important;
  color:#1b2430 !important;
  box-shadow:0 4px 16px rgba(27,36,48,0.04) !important;
}
.kpi-card{background:linear-gradient(180deg,#ffffff,#f9fafc) !important;}
.kpi-card .kv,.kpi-card .kpi-value{color:#1b2430 !important;-webkit-text-fill-color:#1b2430 !important;}
.kpi-card .kl,.kpi-card .kpi-label,.kpi-section-sub,.stat-card .sl,.dq-stat-box .sl{color:#7b8494 !important;}
.kpi-card .ks,.kpi-card .kpi-sub,.hero-sub{color:#5b6575 !important;}
.kpi-section-title{
  background:none !important;-webkit-text-fill-color:#1b2430 !important;color:#1b2430 !important;
}
.stat-card .sv,.dq-stat-box .sv,[data-testid="stMetricValue"]{color:#2563eb !important;}
[data-testid="stMetricLabel"]{color:#5b6575 !important;}
.hero-title{color:#1b2430 !important;}

/* Tabs — no grey grade */
.stTabs [role="tablist"],
[data-testid="stTabs"] [role="tablist"]{
  background:transparent !important;
  border-bottom:1px solid rgba(27,36,48,0.08) !important;
  padding:6px 4px 12px !important;
  gap:16px !important;
}
.stTabs [role="tablist"] button,
[data-testid="stTabs"] button,
[data-testid="stTabs"] [role="tab"]{
  color:#5b6575 !important;
  background:transparent !important;
  border:none !important;
  box-shadow:none !important;
  border-radius:8px 8px 0 0 !important;
  font-weight:600 !important;
}
.stTabs [role="tablist"] button[aria-selected="true"],
[data-testid="stTabs"] button[aria-selected="true"],
[data-testid="stTabs"] [aria-selected="true"]{
  color:#2563eb !important;
  background:#ffffff !important;
  border-bottom:2px solid #2563eb !important;
  box-shadow:none !important;
  font-weight:700 !important;
}
.stTabs [role="tablist"] button:hover{color:#1d4ed8 !important;background:rgba(37,99,235,0.05) !important;}
[data-testid="stTabs"] [role="tabpanel"],
[data-testid="stTabs"] > div > div{background:transparent !important;}

/* Chat */
.cgpt-chat-shell{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.08) !important;
  box-shadow:0 8px 24px rgba(27,36,48,0.05) !important;
}
.cgpt-composer{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.10) !important;
  box-shadow:0 2px 10px rgba(27,36,48,0.04) !important;
}
.cgpt-composer-hint{color:#7b8494 !important;}
.cgpt-user-bubble{
  background:#eef3ff !important;
  border:1px solid rgba(37,99,235,0.14) !important;
  color:#1e3a8a !important;
}
.cgpt-welcome-title{
  background:none !important;-webkit-text-fill-color:#1b2430 !important;color:#1b2430 !important;
}
.cgpt-welcome-sub,.chat-reply-text,.finding-bullet,
.narration-body,.narration-recommendation{color:#334155 !important;}
.narration-headline{color:#0f9d6e !important;}
.narration-card{
  background:#f4fbf8 !important;
  border:1px solid rgba(15,157,110,0.16) !important;
}
.cgpt-mode-bar{
  background:#f7f8fb !important;
  border:1px solid rgba(27,36,48,0.08) !important;
}
.cgpt-mode-bar [data-testid="stRadio"] label{color:#334155 !important;}
.chat-input-area,.chat-input-area-visible{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.10) !important;
  box-shadow:none !important;
}
[data-testid="stChatInput"],
[data-testid="stChatInput"] textarea{
  background:#ffffff !important;
  border-color:rgba(27,36,48,0.12) !important;
  color:#1b2430 !important;
  caret-color:#2563eb !important;
}
[data-testid="stChatInput"] textarea::placeholder{color:#9aa3b2 !important;}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"]{
  background:#eef3ff !important;color:#1e3a8a !important;border:1px solid rgba(37,99,235,0.12) !important;
}
[data-testid="stChatMessage"]:not(:has([data-testid="chatAvatarIcon-user"])) [data-testid="stChatMessageContent"]{
  background:#ffffff !important;color:#1b2430 !important;border:1px solid rgba(27,36,48,0.08) !important;
}
div[class*="st-key-chat_answer_mode"] div[data-baseweb="select"] > div{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.12) !important;
  color:#1b2430 !important;
}

/* Chat Room landing / pins */
.dr-landing-eyebrow{color:#2563eb !important;}
.dr-landing-title{color:#1b2430 !important;}
.dr-landing-sub{color:#5b6575 !important;}
.dr-priority-card,.dr-pin-card{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.08) !important;
}
.dr-priority-title,.dr-pin-headline{color:#1b2430 !important;}
.dr-priority-summary,.dr-pin-meta,.dr-pinned-label{color:#5b6575 !important;}
.dr-share-link{
  background:rgba(37,99,235,0.07) !important;
  border-color:rgba(37,99,235,0.18) !important;
  color:#1d4ed8 !important;
}
.dr-icon-actions .stButton > button,
.dr-icon-actions [data-testid="stPopover"] > button{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.12) !important;
  color:#334155 !important;
}

/* Inputs */
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-baseweb="select"] > div,
div[data-testid="stNumberInput"] input{
  background:#ffffff !important;
  color:#1b2430 !important;
  border-color:rgba(27,36,48,0.14) !important;
}
div[data-baseweb="select"] span,div[data-baseweb="select"] div{color:#1b2430 !important;}
div[data-baseweb="popover"] ul,div[data-baseweb="menu"],ul[role="listbox"]{
  background:#ffffff !important;border:1px solid rgba(27,36,48,0.12) !important;
}
div[data-baseweb="popover"] li,ul[role="listbox"] li{color:#1b2430 !important;}
div[data-baseweb="popover"] li:hover,ul[role="listbox"] li:hover{background:rgba(37,99,235,0.07) !important;}

/* Dataframes */
div[data-testid="stDataFrame"] div[role="grid"],
div[data-testid="stDataFrame"] div[role="grid"] *,
div[data-testid="stDataFrame"] div[role="row"],
div[data-testid="stDataFrame"] div[role="gridcell"],
div[data-testid="stDataFrame"] table,
div[data-testid="stDataFrame"] th,
div[data-testid="stDataFrame"] td{
  background:#ffffff !important;color:#1b2430 !important;border-color:rgba(27,36,48,0.08) !important;
}
div[data-testid="stDataFrame"] thead th,
div[data-testid="stDataFrame"] div[role="columnheader"]{
  background:#f3f5f8 !important;color:#1b2430 !important;font-weight:700 !important;
}

/* Expanders / alerts */
div[data-testid="stExpander"],
[data-testid="stExpander"]{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.10) !important;
}
div[data-testid="stExpander"] summary,
div[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary{color:#1b2430 !important;}
[data-testid="stExpander"] summary:hover{color:#2563eb !important;}
[data-testid="stExpander"] [data-testid="stExpanderDetails"]{
  background:#f7f8fb !important;color:#334155 !important;
}
[data-testid="stAlert"],.stAlert,[data-testid="stStatusWidget"]{
  background:#ffffff !important;color:#1b2430 !important;border-color:rgba(27,36,48,0.10) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]{
  background:#ffffff !important;border-color:rgba(27,36,48,0.10) !important;
}
[data-testid="stPopoverBody"],div[data-baseweb="popover"]{
  background:#ffffff !important;color:#1b2430 !important;border:1px solid rgba(27,36,48,0.12) !important;
}
div[data-testid="stDialog"] > div,
div[role="dialog"]{
  background:#ffffff !important;color:#1b2430 !important;border:1px solid rgba(27,36,48,0.10) !important;
}

/* File uploader */
div[data-testid="stFileUploader"],
div[data-testid="stFileUploader"] section,
div[data-testid="stFileUploader"] > div{
  background:#ffffff !important;border-color:rgba(27,36,48,0.12) !important;color:#1b2430 !important;
}
div[data-testid="stFileUploader"] button{
  background:rgba(37,99,235,0.08) !important;color:#1d4ed8 !important;border-color:rgba(37,99,235,0.22) !important;
}

/* KPI / DQ / join / code */
.kpi-filter-panel,.kpi-side-panel,.preview-hero,.dq-panel{background:transparent !important;}
.dq-issue-row{background:#f7f8fb !important;border:1px solid rgba(27,36,48,0.08) !important;color:#334155 !important;}
.dq-banner-ok{color:#0f9d6e !important;background:rgba(15,157,110,0.08) !important;}
.dq-banner-warn{color:#c2410c !important;background:rgba(194,65,12,0.08) !important;}
.dq-banner-err{color:#b91c1c !important;background:rgba(220,38,38,0.08) !important;}
.join-status-card,.join-info-banner{
  background:#ffffff !important;border:1px solid rgba(27,36,48,0.10) !important;color:#1b2430 !important;
}
.join-status-card .join-status-title{color:#1d4ed8 !important;}
.join-status-card .join-status-desc,.join-status-card .join-status-meta,.join-info-banner{color:#334155 !important;}
.status-card{background:#fff !important;color:#1b2430 !important;}
.status-card code{color:#2563eb !important;background:rgba(37,99,235,0.08) !important;}
.code-card,pre,code,div[data-testid="stCode"] pre,div[data-testid="stCode"] code{
  color:#1b2430 !important;background:#f3f5f8 !important;
}
.js-plotly-plot .plotly,.stPlotlyChart{background:#ffffff !important;}
.ai-animated-bg{opacity:0.18 !important;filter:saturate(0.55) brightness(1.35);}
.result-header-bar,.result-stat-pill,.chat-results-label,.cgpt-meta{color:#5b6575 !important;}
.small-badge,.result-stat-pill{
  background:rgba(37,99,235,0.07) !important;color:#1d4ed8 !important;border:1px solid rgba(37,99,235,0.12) !important;
}
.badge-semantic,.badge-cached,.badge-fallback,.badge-deterministic{color:#334155 !important;}
.sem-term-badge.measure{color:#4338ca !important;background:rgba(79,70,229,0.08) !important;}
.sem-term-badge.dimension{color:#1d4ed8 !important;background:rgba(37,99,235,0.08) !important;}
.sem-term-badge.attribute{color:#0f9d6e !important;background:rgba(15,157,110,0.08) !important;}
.sem-term-badge.glossary{color:#c2410c !important;background:rgba(194,65,12,0.08) !important;}
.trust-score-card,.trust-score-summary{background:#ffffff !important;border:1px solid rgba(27,36,48,0.10) !important;color:#5b6575 !important;}
.trust-title{color:#1b2430 !important;}
.finding-bullet{background:rgba(37,99,235,0.05) !important;border-left-color:#2563eb !important;color:#334155 !important;}
.clarification-chip{background:rgba(37,99,235,0.06) !important;border-color:rgba(37,99,235,0.16) !important;color:#1e3a8a !important;}
.surprise-header,.surprise-opp{color:#c2410c !important;}
.surprise-highlight{background:#fff7ed !important;border-color:rgba(194,65,12,0.18) !important;color:#9a3412 !important;}
.mod-context-banner,.sem-ctx-expander-hint{color:#0f9d6e !important;background:rgba(15,157,110,0.08) !important;}
.conv-context-banner{color:#1b2430 !important;background:rgba(37,99,235,0.07) !important;}
.app-footer{color:#7b8494 !important;}
div[data-testid="stRadio"] label,div[role="radiogroup"] label{color:#1b2430 !important;}

/* Brand / join / DQ / expanders — kill leftover dark fills */
.sidebar-brand{
  background:transparent !important;
  border:none !important;
  box-shadow:none !important;
}
.sidebar-brand .sidebar-hero-title{color:#1b2430 !important;}
.sidebar-brand .sidebar-hero-sub,
.sidebar-tagline{color:#334155 !important;}
.askdb-logo{filter:none !important;}
[data-testid="stSidebar"] [data-testid="stImage"] img{
  box-shadow:0 6px 18px rgba(27,36,48,0.10) !important;
}
[data-testid="stSidebar"] [data-testid="stPopover"] > button,
[data-testid="stSidebar"] [data-testid="stPopover"] button{
  color:#111827 !important;
  background:#ffffff !important;
  border:1px solid rgba(17,24,39,0.16) !important;
  box-shadow:none !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"]{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.08) !important;
  box-shadow:none !important;
}
.sb-join-card{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.12) !important;
}
[data-testid="stSidebar"] .sb-join-kicker{color:#1b2430 !important;}
[data-testid="stSidebar"] .sb-join-status-active{color:#059669 !important;}
[data-testid="stSidebar"] .sb-join-status-fallback{color:#c2410c !important;}
[data-testid="stSidebar"] .sb-join-status-pending{color:#dc2626 !important;}
[data-testid="stSidebar"] .sb-join-status-idle{color:#64748b !important;}
[data-testid="stSidebar"] div[class*="st-key-sidebar_join_settings"] button{
  background:#ffffff !important;color:#1b2430 !important;
  border:1px solid rgba(27,36,48,0.16) !important;
  visibility:visible !important;opacity:1 !important;
}

details,[data-testid="stExpander"],
[data-testid="stExpander"] > div,
[data-testid="stExpander"] details,
[data-testid="stExpander"] [data-testid="stExpanderDetails"],
[data-testid="stExpander"] [data-testid="stExpanderDetails"] > div{
  background:#ffffff !important;
  color:#1b2430 !important;
  border-color:rgba(27,36,48,0.10) !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p,
details > summary{
  background:#ffffff !important;
  color:#1b2430 !important;
}
.dq-stat-box,.dq-badge-green,.dq-badge-amber,.dq-badge-red{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.08) !important;
}
.dq-badge-green{color:#0f9d6e !important;background:#ecfdf5 !important;}
.dq-badge-amber{color:#c2410c !important;background:#fff7ed !important;}
.dq-badge-red{color:#b91c1c !important;background:#fef2f2 !important;}
.dq-status-pill{color:#0f9d6e !important;background:#ecfdf5 !important;border-color:rgba(15,157,110,0.22) !important;}
.dq-health-label{color:#5b6575 !important;}
.schema-pill.num{color:#1d4ed8 !important;background:#eff6ff !important;}
.schema-pill.txt{color:#0f9d6e !important;background:#ecfdf5 !important;}
.schema-pill.date{color:#c2410c !important;background:#fff7ed !important;}
.schema-pill.bool{color:#6d28d9 !important;background:#f5f3ff !important;}
.kpi-card,.kpi-chart-card,.stat-card{
  background:#ffffff !important;
  border:1px solid rgba(27,36,48,0.08) !important;
}
.js-plotly-plot,.js-plotly-plot .plot-container,.stPlotlyChart > div{
  background:#ffffff !important;
}
.block-container{padding-top:10px !important;}
[data-testid="stSidebar"] div[class*="st-key-ui_theme"] div[data-baseweb="select"] > div{
  background:#ffffff !important;color:#1b2430 !important;
  border:1px solid rgba(27,36,48,0.14) !important;
}
[data-testid="stSidebar"] div[class*="st-key-ui_theme"] svg{fill:#334155 !important;}
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

/* Theme picker lives in the sidebar — keep it compact, not a page banner */
[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ui_theme"]){
  align-items:center !important;
  gap:8px !important;
  padding:0 !important;
  margin:0 0 6px 0 !important;
  min-height:0 !important;
  background:transparent !important;
  border:none !important;
  box-shadow:none !important;
}
[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-ui_theme"]):before{
  display:none !important;
}
div[class*="st-key-ui_theme"]{position:relative;z-index:1;}
div[class*="st-key-ui_theme"] div[data-baseweb="select"] > div{
  min-height:32px !important;
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

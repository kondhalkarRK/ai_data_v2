Copy-paste this entire prompt into Claude.

I need you to act as a Principal Product Designer, Senior Streamlit Architect, Frontend Engineer, SaaS Design Expert, and AI UX Designer.

I have already built a highly advanced AI Analytics Platform in Streamlit. The backend is powerful and must remain untouched. My problem is not functionality. My problem is presentation, visual impact, user experience, wow factor, AI-first feeling, and premium enterprise design.

The current application feels like a standard Streamlit application.

I want it to feel like a combination of:

Microsoft Fabric
Databricks Genie
Snowflake Cortex
Palantir Foundry
OpenAI ChatGPT Enterprise
Perplexity Labs
Modern SaaS AI Products

Current architecture:

app.py

config/
  settings.py
  styles.py
  constants.py

core/
  llm_client.py
  sql_guardrails.py
  schema_builder.py
  nlq_engine.py
  join_engine.py
  chart_engine.py
  analysis_engine.py
  kpi_engine.py
  data_quality_engine.py
  utils.py

ui/
  sidebar.py
  tab_join.py
  tab_preview.py
  tab_kpi.py
  tab_query.py

semantic/
  business_glossary.yaml
  semantic_context_builder.py
  semantic_loader.py
  semantic_model.yaml
  semantic_vector_search.py


Current capabilities already exist and must NOT be broken:

CSV Upload
Multi-file Analytics
Semantic Layer
Semantic Search
Business Glossary
NLQ to SQL
Auto Join
Semantic Join
SQL Join
KPI Engine
Data Quality Engine
AI Analysis
Chart Generation
DuckDB Processing
Usage Tracking
Materialized Views

You are NOT allowed to modify any business logic.

Do NOT modify:

core/*
semantic/*
config/settings.py
config/constants.py


Only redesign the UI and UX.

Files allowed to change:

config/styles.py
ui/sidebar.py
ui/tab_query.py
ui/tab_kpi.py
ui/tab_preview.py
ui/tab_join.py


The redesign should be approximately:

styles.py      = 70%
sidebar.py     = 10%
tab_query.py   = 10%
tab_kpi.py     = 5%
tab_preview.py = 3%
tab_join.py    = 2%


I want a complete enterprise-grade futuristic dark AI platform.

Visual direction:

Dark futuristic theme
Glassmorphism
Premium SaaS design
AI-first experience
Executive dashboard feel
Neon glow effects
Floating light effects
High-end typography
Large rounded cards
Smooth hover animations
Subtle motion design
Modern dashboards
Professional color hierarchy
Beautiful KPI cards
Command center appearance

Color system:

Background: #070B17
Background Secondary: #0F172A

Card: #111827
Card Hover: #1E293B

Primary: #4F7CFF
Secondary: #7C3AED

Success: #00D17A
Warning: #FFB020
Danger: #FF6B6B

Text: #F8FAFC
Subtext: #94A3B8

Border: rgba(255,255,255,.08)


I want the application to look similar to the attached examples:

Premium SaaS Dashboard
Data Quality Command Center
AI Assistant Analytics Workspace

My goals:

Users should immediately think:

"This looks expensive."
"This looks enterprise-grade."
"This looks AI-powered."
"This does not look like Streamlit."

FILE-BY-FILE REQUIREMENTS

═══════════════════════════════════════════════ STYLES.PY ═══════════════════════════════════════════════

This file should drive most of the redesign.

Create a complete production-grade CSS design system.

Include:

Global Theme
stApp
body
container spacing
typography
page layout
Animated Background

Create floating glows.

Add:

radial gradients
blue glow
purple glow
animated movement
Sidebar Styling

Style:

[data-testid="stSidebar"]


Make it look like:

Premium AI platform
Glass container
Enterprise navigation
Tabs Styling

Redesign Streamlit tabs.

Features:

Rounded pills
Active state glow
Hover transitions
Fabric-like appearance
Button Styling

Transform all buttons into premium buttons.

Requirements:

Gradient background
Hover lift
Glow effect
Input Fields

Style:

text_input
text_area
selectbox
multiselect
KPI Cards

Create reusable classes:

.metric-card
.kpi-card
.ai-card
.section-card
.glass-card
.hero-card
.status-card


Each card should have:

gradient border
hover animation
glass effect
Metric Styling

Override default Streamlit metrics.

Make metrics look premium.

DataFrame Styling

Modern enterprise tables.

Expander Styling

Scrollbar Styling

Animation Library

Create:

fadeIn
pulseGlow
floatGlow
cardLift
glowBorder

Hero Banner Styling

Support large top banners.

Footer Styling

Semantic Status Badges

AI Copilot Badges

Create complete ready-to-run CSS.

I expect 500+ lines if needed.

═══════════════════════════════════════════════ SIDEBAR.PY ═══════════════════════════════════════════════

Keep all existing functionality.

Only change visuals.

Transform sidebar into:

AI COMMAND CENTER

Top section:

🧠 AI DATA INTELLIGENCE PLATFORM
Semantic Analytics Engine


Create visual cards for:

Uploaded Files
Semantic Layer Status
Join Strategy
LLM Usage
Materialized Views

Add icons.

Add section dividers.

Add premium info cards.

Use the CSS classes from styles.py.

DO NOT break existing session state logic.

═══════════════════════════════════════════════ TAB_QUERY.PY ═══════════════════════════════════════════════

This is the most important page.

Treat this like ChatGPT Enterprise meets Microsoft Copilot.

Keep all business logic.

Add:

Top hero banner:

AI Business Copilot
Semantic AI Analytics Workspace


Add AI status section.

Add quick AI suggestion chips:

Top Customers
Revenue Trend
Regional Sales
Product Performance
Forecast Revenue


Create modern query container.

Create premium result area.

Wrap result sections inside cards.

Wrap generated SQL inside beautiful code card.

Wrap analysis inside Copilot-style response card.

Create beautiful summary section.

Create beautiful insights section.

Charts must appear inside glass cards.

Make the page feel like an AI workspace rather than a BI report.

═══════════════════════════════════════════════ TAB_KPI.PY ═══════════════════════════════════════════════

Transform into Executive KPI Cockpit.

Create:

Hero Section

Executive KPI Dashboard
Monitor business performance in real time


Create premium KPI grid.

Create larger KPI cards.

Add icons.

Add hover glow.

Add premium executive feel.

Keep KPI calculations intact.

═══════════════════════════════════════════════ TAB_PREVIEW.PY ═══════════════════════════════════════════════

Transform into Data Observatory.

Add hero section.

Create metric summary cards:

Rows
Columns
Numeric Columns

Wrap preview tables in premium cards.

Wrap data quality in glass sections.

Wrap column profiling in professional cards.

Keep all logic unchanged.

═══════════════════════════════════════════════ TAB_JOIN.PY ═══════════════════════════════════════════════

Transform into Data Fusion Studio.

Hero Section:

Data Fusion Studio
Semantic Relationship Intelligence


Create professional AI join workspace.

Create semantic join status cards.

Create join quality cards.

Create join method selector styling.

Create premium SQL section styling.

Keep:

Semantic Join
Auto Join
Manual Join
SQL Join

exactly as they work today.

═══════════════════════════════════════════════ OUTPUT FORMAT ═══════════════════════════════════════════════

Provide:

Full replacement code for styles.py
Exact modifications for sidebar.py
Exact modifications for tab_query.py
Exact modifications for tab_kpi.py
Exact modifications for tab_preview.py
Exact modifications for tab_join.py

Do not give theory.

Do not explain design concepts.

Do not summarize.

Provide production-ready code only.

Assume I will directly copy and paste into my project.
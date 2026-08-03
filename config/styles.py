"""
config/styles.py
"""
import streamlit as st


def apply_styles() -> None:
    st.markdown(r"""
<style>
:root{
  --bg:#030711;--bg-2:#050a14;--panel:#07111f;--panel-2:#0d1728;
  --primary:#818cf8;--secondary:#7C3AED;--success:#6ee7b7;--warn:#fcd34d;--danger:#fca5a5;
  --text:#e2e8f0;--subtext:#94a3b8;--border:rgba(148,163,184,0.1);
  --color-primary: #818cf8;
  --color-primary-bg: rgba(99,102,241,0.1);
  --color-primary-border: rgba(99,102,241,0.2);
  --color-success: #6ee7b7;
  --color-success-bg: rgba(16,185,129,0.08);
  --color-warning: #fcd34d;
  --color-warning-bg: rgba(245,158,11,0.08);
  --color-danger: #fca5a5;
  --color-danger-bg: rgba(239,68,68,0.08);
  --color-surface: rgba(15,23,42,0.8);
  --color-surface-2: rgba(30,41,59,0.6);
  --color-border: rgba(148,163,184,0.1);
  --color-text-primary: #e2e8f0;
  --color-text-secondary: #94a3b8;
  --color-text-muted: #64748b;
}
header, [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], footer, #MainMenu {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
header {background:transparent !important;}
[data-testid="stHeader"]{background:transparent !important;border-bottom:1px solid rgba(255,255,255,.05) !important;}
[data-testid="stToolbar"]{right:1rem !important;}
[data-testid="stDecoration"]{display:none !important;}
#MainMenu{visibility:hidden !important;}
footer{visibility:hidden !important;}
html,body,#root,div[role="main"],.stApp,.block-container{
  background:
    radial-gradient(ellipse at 20% 50%, rgba(99,102,241,0.03) 0%, transparent 60%),
    radial-gradient(ellipse at 80% 20%, rgba(16,185,129,0.02) 0%, transparent 50%),
    linear-gradient(135deg,var(--bg),var(--bg-2)) !important;
  color:var(--text) !important;
}
.stApp,.block-container{
  padding:16px 1rem 28px 1rem !important;
  max-width:100% !important;
}

.ai-animated-bg{position:fixed;left:0;top:0;width:100%;height:100%;z-index:0;pointer-events:none;overflow:hidden}
.ai-animated-bg .glow{position:absolute;border-radius:50%;filter:blur(90px);opacity:0.35;animation:floatGlow 14s linear infinite}
.ai-animated-bg .g1{width:520px;height:520px;left:-140px;top:-140px;background:radial-gradient(circle at 30% 30%, rgba(79,124,255,0.9), transparent 35%)}
.ai-animated-bg .g2{width:440px;height:440px;right:-120px;bottom:-120px;background:radial-gradient(circle at 70% 70%, rgba(124,58,237,0.85), transparent 35%);animation-duration:16s}
.ai-animated-bg .g3{width:280px;height:280px;left:40%;top:20%;background:radial-gradient(circle at 50% 50%, rgba(0,209,122,0.75), transparent 40%);animation-duration:18s}
@keyframes floatGlow{0%{transform:translateY(0) scale(1)}50%{transform:translateY(-20px) scale(1.04)}100%{transform:translateY(0) scale(1)}}

.glass-card{background:linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.01));border:1px solid var(--border);backdrop-filter:blur(12px) saturate(120%);border-radius:16px;padding:16px;color:var(--text);box-shadow:0 10px 32px rgba(2,6,23,0.65);}
.hero-card{display:flex;gap:16px;align-items:center;padding:18px 20px;border-radius:18px;margin-bottom:16px;background:linear-gradient(115deg, rgba(79,124,255,0.12), rgba(124,58,237,0.08));border:1px solid rgba(255,255,255,0.08);transition:border-color .25s ease, box-shadow .25s ease, transform .25s ease}
.hero-card:hover{border-color:rgba(124,158,255,.35);box-shadow:0 12px 30px rgba(79,124,255,0.16);transform:translateY(-1px)}
.hero-title{font-size:20px;font-weight:800;color:var(--text);margin:0}
.hero-sub{color:var(--subtext);margin-top:4px;font-size:13px}
.hero-cta{background:linear-gradient(90deg,var(--primary),var(--secondary));padding:10px 14px;border-radius:12px;color:#fff;font-weight:800;box-shadow:0 8px 24px rgba(79,124,255,0.18)}

/* CHANGED: lighter sidebar background */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #071224 0%, #0d1a32 100%);
}

[data-testid="stMetricValue"] {
    color: #67e8f9 !important;
}

/* =============================================
   BUTTONS — frosted primary (no solid dark blue)
   ============================================= */
.stButton > button {
    border-radius: 10px;
    border: 1px solid rgba(139, 92, 246, 0.4);
    background: linear-gradient(135deg, rgba(99,102,241,0.25), rgba(139,92,246,0.2));
    color: #c4b5fd;
    font-weight: 600;
    letter-spacing: 0.3px;
    box-shadow: 0 2px 8px rgba(139,92,246,0.15);
}
.stButton > button:hover {
    border-color: rgba(139, 92, 246, 0.55);
    background: rgba(139, 92, 246, 0.35) !important;
    box-shadow: 0 4px 14px rgba(139,92,246,0.25);
    color: #ddd6fe;
}
button[kind="primary"],
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, rgba(124,58,237,0.4), rgba(99,102,241,0.3)) !important;
    border: 1px solid rgba(139, 92, 246, 0.5) !important;
    color: #ddd6fe !important;
    border-radius: 10px !important;
    box-shadow: 0 2px 12px rgba(124,58,237,0.25) !important;
}
button[kind="primary"]:hover,
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 18px rgba(124,58,237,0.4) !important;
    opacity: 1 !important;
}

/* Sidebar buttons — muted secondary by default */
[data-testid="stSidebar"] .stButton > button {
    height: 30px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    border-radius: 7px;
    border: 1px solid rgba(148, 163, 184, 0.15);
    background: rgba(30, 41, 59, 0.7);
    color: #94a3b8;
    margin-top: 4px;
    margin-bottom: 4px;
    box-shadow: none;
}
[data-testid="stSidebar"] .stButton > button:hover {
    border-color: rgba(148,163,184,0.3);
    background: rgba(30, 41, 59, 0.85);
    color: #cbd5e1;
    box-shadow: none;
}
/* Semantic sidebar button variants via st-key-* */
[data-testid="stSidebar"] div[class*="st-key-sidebar_reset"] button {
    background: rgba(148,163,184,0.08) !important;
    border: 1px solid rgba(148,163,184,0.15) !important;
    color: #94a3b8 !important;
}
[data-testid="stSidebar"] div[class*="st-key-sidebar_cache"] button {
    background: rgba(16,185,129,0.08) !important;
    border: 1px solid rgba(16,185,129,0.2) !important;
    color: #6ee7b7 !important;
}
[data-testid="stSidebar"] div[class*="st-key-sidebar_cache"] button:hover {
    background: rgba(16,185,129,0.15) !important;
}
[data-testid="stSidebar"] div[class*="st-key-sidebar_clear_views"] button {
    background: rgba(239,68,68,0.07) !important;
    border: 1px solid rgba(239,68,68,0.18) !important;
    color: #fca5a5 !important;
}
[data-testid="stSidebar"] div[class*="st-key-sidebar_clear_views"] button:hover {
    background: rgba(239,68,68,0.14) !important;
    border-color: rgba(239,68,68,0.3) !important;
}
[data-testid="stSidebar"] div[class*="st-key-sidebar_clear_conv"] button {
    background: rgba(249,168,212,0.08) !important;
    border: 1px solid rgba(249,168,212,0.15) !important;
    color: #f9a8d4 !important;
}
[data-testid="stSidebar"] div[class*="st-key-sidebar_upload_plus"] button {
    background: rgba(245,158,11,0.15) !important;
    border: 1px solid rgba(245,158,11,0.3) !important;
    color: #fcd34d !important;
    border-radius: 8px !important;
    height: 28px !important;
    min-height: 28px !important;
}

/* =============================================
   PROGRESS BARS — CHANGED: much lighter shades
   ============================================= */
.stProgress > div > div {
    background: linear-gradient(90deg, #60a5fa, #c084fc);
}

/* CHANGED: progress bar track lighter */
[data-testid="stSidebar"] .stProgress > div {
    background: rgba(255,255,255,0.12) !important;
    border-radius: 6px !important;
    height: 7px !important;
    margin-top: 8px !important;
    margin-bottom: 10px !important;
}

[data-testid="stSidebar"] .stProgress > div > div {
    background: linear-gradient(
        90deg,
        #7dd3fc,
        #c4b5fd
    ) !important;
    height: 7px !important;
    border-radius: 6px !important;
}

/* ======================================
   SIDEBAR TEXT VISIBILITY
====================================== */
[data-testid="stSidebar"] * {
    color: #ffffff !important;
}

[data-testid="stSidebar"] .stCaption {
    color: #cbd5e1 !important;
}

[data-testid="stSidebar"] p {
    color: #ffffff !important;
}

[data-testid="stSidebar"] label {
    color: #ffffff !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] h4 {
    color: #ffffff !important;
}

[data-testid="stSidebar"] .stButton button {
    color: white !important;
}

[data-testid="stSidebar"] .stProgress {
    color: white !important;
}

/* =====================================
   AI COMMAND CENTER SIDEBAR
===================================== */
.ai-loader{
    position:fixed;
    top:50%;
    left:50%;
    transform:translate(-50%,-50%);
    z-index:99999;
    width:420px;
    padding:24px;
    border-radius:18px;
    background:linear-gradient(180deg, rgba(10,15,30,.98), rgba(18,25,45,.98));
    border:1px solid rgba(79,124,255,.25);
    backdrop-filter:blur(16px);
    box-shadow:0 0 40px rgba(79,124,255,.20);
    text-align:center;
}

.ai-loader-title{
    color:#fbbf24;
    font-size:12px;
    letter-spacing:2px;
    font-weight:700;
    margin-bottom:14px;
}

.ai-loader-main{
    color:white;
    font-size:20px;
    font-weight:700;
}

.ai-loader-sub{
    color:#94a3b8;
    margin-top:8px;
}

.loader-dots{
    margin-top:16px;
}

.loader-dots span{
    width:8px;
    height:8px;
    display:inline-block;
    margin:0 4px;
    border-radius:50%;
    background:#4f7cff;
    animation:pulseDots 1.4s infinite;
}

.loader-dots span:nth-child(2){ animation-delay:.2s; }
.loader-dots span:nth-child(3){ animation-delay:.4s; }

@keyframes pulseDots{
  0%,80%,100%{ transform:scale(0.8); opacity:.4; }
  40%{ transform:scale(1.4); opacity:1; }
}

/* CHANGED: added bottom margin for spacing after title */
.sb-title{
    color:#fbbf24;
    font-size:11px;
    font-weight:800;
    letter-spacing:1.5px;
    text-shadow:
        0 0 5px rgba(251,191,36,.8),
        0 0 10px rgba(251,191,36,.5),
        0 0 20px rgba(251,191,36,.2);
    padding-bottom:4px;
    border-bottom:1px solid rgba(251,191,36,.15);
    margin-bottom:8px;
}

.active-status{
    color:#22c55e;
    text-shadow:0 0 8px rgba(34,197,94,.35);
}

.pending-status{
    color:#ef4444;
    text-shadow:0 0 8px rgba(239,68,68,.35);
}

.loaded-status{
    color:#facc15;
    text-shadow:0 0 8px rgba(250,204,21,.35);
}

.metric-status{
    color:#38bdf8;
    text-shadow:0 0 8px rgba(56,189,248,.25);
}

/* CHANGED: more vertical padding + subtle row divider */
.sb-row{
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:7px 0;
    border-bottom:1px solid rgba(255,255,255,0.04);
}

.sb-row:last-of-type{
    border-bottom:none;
}

.sb-label{
    color:#94a3b8;
    font-size:13px;
    letter-spacing:0.3px;
}

.sb-value{
    font-size:14px;
    font-weight:700;
}

[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]{
    background:transparent !important;
}

/* =============================================
   SIDEBAR BUTTONS (detailed override) — muted
   ============================================= */
[data-testid="stSidebar"] .stButton button{
    background:rgba(30, 41, 59, 0.7) !important;
    border:1px solid rgba(148, 163, 184, 0.15) !important;
    color:#94a3b8 !important;
    border-radius:7px !important;
    font-size:11px !important;
    font-weight:600 !important;
    text-transform:uppercase;
    letter-spacing:0.8px;
    height:30px !important;
    min-height:30px !important;
    box-shadow:none !important;
    margin-top:4px !important;
    margin-bottom:3px !important;
}

[data-testid="stSidebar"] .stButton button:hover{
    border-color:rgba(148,163,184,0.3) !important;
    background:rgba(30, 41, 59, 0.9) !important;
    color:#cbd5e1 !important;
    box-shadow:none !important;
    transform:none !important;
}

/* =============================================
   PROGRESS BARS (global sidebar override)
   CHANGED: lighter track + lighter fill
   ============================================= */
[data-testid="stSidebar"] .stProgress > div > div{
    background:linear-gradient(90deg, #7dd3fc, #c4b5fd) !important;
}

/* ====================================================
   Workspace Header
==================================================== */
.workspace-header{
    margin-top:-10px;
    margin-bottom:10px;
    padding:8px 12px;
    border-radius:12px;
    background:linear-gradient(90deg, rgba(79,124,255,.06), rgba(124,58,237,.04));
    border:1px solid rgba(255,255,255,.06);
    position:relative;
    overflow:hidden;
}

.workspace-header:before{
    content:"";
    position:absolute;
    left:0;top:0;
    width:100%;height:2px;
    background:linear-gradient(90deg, #4f7cff, #7c3aed, #4f7cff);
    box-shadow:0 0 12px rgba(79,124,255,.5);
}

.workspace-name{
    font-size:11px;
    letter-spacing:2px;
    font-weight:800;
    color:#fbbf24;
    text-transform:uppercase;
    text-shadow:0 0 8px rgba(251,191,36,.35);
}

.workspace-tagline{
    margin-top:3px;
    font-size:24px;
    font-weight:700;
    color:#e2e8f0;
    line-height:1.2;
}

/* ==========================================
   RADIO BUTTONS / SEGMENT CONTROL
========================================== */
div[role="radiogroup"]{gap:8px !important;}

div[role="radiogroup"] label{
    background:#111827 !important;
    border:1px solid rgba(79,124,255,.15) !important;
    border-radius:10px !important;
    padding:6px 12px !important;
    color:#fde68a !important;
    transition:all .2s ease;
}

div[role="radiogroup"] label:hover{
    border-color:#4f7cff !important;
    box-shadow:0 0 12px rgba(79,124,255,.20);
}

div[role="radiogroup"] label:has(input:checked){
    background:linear-gradient(90deg, rgba(79,124,255,.20), rgba(124,58,237,.20)) !important;
    border:1px solid #4f7cff !important;
    color:white !important;
    box-shadow:0 0 16px rgba(79,124,255,.25);
}

div[role="radiogroup"] input{accent-color:#4f7cff !important;}

/* =============================================
   SIDEBAR SHELL — CHANGED: lighter background
   + more vertical gap between components
   ============================================= */
[data-testid="stSidebar"]{
    background:linear-gradient(180deg,#071224,#0d1a32) !important;
    padding:12px 10px 14px 10px !important;
    border-right:1px solid rgba(255,255,255,0.06);
    box-shadow:inset 0 1px 0 rgba(255,255,255,0.03),0 0 0 1px rgba(79,124,255,0.06);
}

section[data-testid="stSidebar"]{
    background:linear-gradient(180deg,#071224,#0d1a32) !important;
}

/* CHANGED: increased gap between stacked sidebar blocks */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{
    gap:0.55rem !important;
}

[data-testid="stSidebar"] hr{
    margin:8px 0 !important;
    border-color:rgba(255,255,255,0.07) !important;
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{
    margin-bottom:0 !important;
}

.sidebar-shell{display:flex;flex-direction:column;gap:10px}

.sidebar-hero{
    display:flex;
    align-items:center;
    gap:10px;
    padding:12px;
    border-radius:14px;
    margin-bottom:8px;
    background:linear-gradient(135deg, rgba(79,124,255,0.22), rgba(124,58,237,0.14));
    border:1px solid rgba(255,255,255,0.10);
    position:relative;
    overflow:hidden;
    box-shadow:0 10px 26px rgba(79,124,255,0.10);
}

.sidebar-hero:before{
    content:"";
    position:absolute;inset:0;
    background:radial-gradient(120px 60px at 15% 0%, rgba(255,255,255,0.10), transparent 70%);
}

.sidebar-hero-icon{
    width:36px;height:36px;
    border-radius:10px;flex:0 0 36px;
    background:linear-gradient(135deg,#4f7cff,#7c3aed);
    display:flex;align-items:center;justify-content:center;
    font-size:18px;
    box-shadow:0 6px 16px rgba(79,124,255,.35);
}

.sidebar-hero-text{position:relative;z-index:1;}
.sidebar-hero-title{font-size:13.5px;font-weight:800;color:#fff;letter-spacing:.3px;}
.sidebar-hero-sub{font-size:10.5px;color:#b9c6e0;margin-top:1px;}

.sidebar-title{font-size:16px;font-weight:800;color:#fff}
.sidebar-subtitle{font-size:11px;color:var(--subtext);margin-top:2px}

.sidebar-card{
    padding:10px 10px 11px 10px;
    border-radius:14px;
    background:linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015));
    border:1px solid rgba(255,255,255,0.07);
    box-shadow:0 6px 18px rgba(2,6,23,0.35);
}

.sidebar-pill{display:inline-block;padding:6px 8px;border-radius:999px;background:rgba(255,255,255,0.04);color:#dce7ff;font-size:10px;font-weight:800;margin:2px 0;letter-spacing:.2px;border:1px solid rgba(255,255,255,0.05)}
.sidebar-mini{padding:8px;border-radius:10px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04)}
.small-badge{display:inline-block;padding:6px 8px;border-radius:999px;background:linear-gradient(90deg, rgba(79,124,255,0.12), rgba(124,58,237,0.10));color:#e5edff;font-weight:800;font-size:10px;box-shadow:0 6px 14px rgba(79,124,255,0.05)}
.stat-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}
.stat-card{flex:1;min-width:110px;padding:8px 8px 9px 8px;border-radius:10px;background:rgba(255,255,255,0.025);border:1px solid rgba(255,255,255,0.05);text-align:center}
.stat-card .sv{font-size:16px;font-weight:800;color:var(--primary)}
.stat-card .sl{font-size:10px;color:var(--subtext);text-transform:uppercase;margin-top:2px}

/* CHANGED: section containers more padding + spacing */
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"]{
    background:linear-gradient(180deg, rgba(255,255,255,0.028), rgba(255,255,255,0.01)) !important;
    border:1px solid rgba(255,255,255,0.07) !important;
    border-radius:12px !important;
    margin-bottom:8px !important;
    transition:border-color .2s ease;
}

[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"]:hover{
    border-color:rgba(124,158,255,.28) !important;
}

[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] > div{
    padding:11px 13px 11px 13px !important;
    gap:0.45rem !important;
}

/* compact sidebar buttons */
[data-testid="stSidebar"] .stButton{margin-top:4px !important;}
[data-testid="stSidebar"] .stButton button{
    height:32px !important;
    min-height:32px !important;
    font-size:10.5px !important;
    letter-spacing:.4px;
}

[data-testid="stSidebar"] [data-testid="stFileUploader"]{padding:2px !important;}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"]{padding:8px !important;min-height:0 !important;}

/* CHANGED: progress bar spacing inside sidebar */
[data-testid="stSidebar"] .stProgress{
    margin:6px 0 8px 0 !important;
}

[data-testid="stSidebar"] .stProgress > div{
    background:rgba(255,255,255,0.12) !important;
    border-radius:6px !important;
    height:7px !important;
}

[data-testid="stSidebar"] .stProgress > div > div{
    background:linear-gradient(90deg,#7dd3fc,#c4b5fd) !important;
    height:7px !important;
    border-radius:6px !important;
}

.status-card{background:#111827;color:#67e8f9;border:1px solid rgba(255,255,255,0.12);border-radius:16px;padding:16px;margin-bottom:18px;box-shadow:0 20px 40px rgba(0,0,0,0.18)}
.status-card .status-title{font-size:13px;font-weight:800;color:var(--primary);margin-bottom:8px}
.status-card .status-meta{font-size:12px;color:var(--subtext);line-height:1.5}
.status-card code{background:rgba(255,255,255,0.05);padding:2px 6px;border-radius:6px;color:var(--text);}

.stTabs [role="tablist"]{
  background:rgba(15,23,42,0.6);
  border-bottom:1px solid rgba(99,102,241,0.1);
  padding:4px 8px;
  gap:4px;
}
.stTabs [role="tablist"] button{
  background:transparent;
  border:1px solid transparent;
  padding:10px 16px;
  border-radius:8px;
  margin-right:4px;
  color:#64748b;
  font-weight:500;
  font-size:13px;
  transition:all .15s ease;
}
.stTabs [role="tablist"] button[aria-selected="true"]{
  background:linear-gradient(135deg, rgba(124,58,237,0.9), rgba(99,102,241,0.85));
  color:#fff;
  font-weight:700;
  border-radius:20px;
  padding:6px 18px;
  box-shadow:0 4px 15px rgba(124,58,237,0.35), 0 2px 6px rgba(124,58,237,0.2);
  border:1px solid rgba(255,255,255,0.1);
}
.stTabs [role="tablist"] button:hover{
  color:#94a3b8;
  background:rgba(99,102,241,0.05);
  border-color:rgba(99,102,241,0.1);
  transform:none;
}

/* Sidebar / global buttons — frosted, no solid blue fill */
[data-testid="stSidebar"] div[data-testid="stButton"]>button{
    background:rgba(30, 41, 59, 0.7) !important;
    border:1px solid rgba(148, 163, 184, 0.15) !important;
    color:#94a3b8 !important;
    padding:6px 10px !important;
    border-radius:7px !important;
    font-weight:600 !important;
    box-shadow:none !important;
}

[data-testid="stSidebar"] div[data-testid="stButton"]>button:hover{
    transform:none !important;
    background:rgba(30, 41, 59, 0.9) !important;
    color:#cbd5e1 !important;
    border-color:rgba(148,163,184,0.3) !important;
}

div[data-testid="stButton"]>button{
    background:linear-gradient(135deg, rgba(99,102,241,0.25), rgba(139,92,246,0.2)) !important;
    border:1px solid rgba(139, 92, 246, 0.4) !important;
    color:#c4b5fd !important;
    border-radius:10px !important;
    font-weight:600 !important;
    box-shadow:0 2px 8px rgba(139,92,246,0.15) !important;
}

div[data-testid="stFileUploader"]{
    background:linear-gradient(180deg, rgba(12,18,33,0.98), rgba(20,26,45,0.98)) !important;
    border:1px solid rgba(255,255,255,0.08) !important;
    border-radius:16px !important;
    padding:10px !important;
    box-shadow:inset 0 1px 0 rgba(255,255,255,0.04) !important;
}

div[data-testid="stFileUploader"] section,
div[data-testid="stFileUploader"] > div{
    background:rgba(10,14,26,0.95) !important;
    border:1px solid rgba(255,255,255,0.05) !important;
    border-radius:12px !important;
}

div[data-testid="stFileUploader"] button,
div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]{
    background:rgba(93,130,255,0.22) !important;
    color:#eef2ff !important;
    border:1px solid rgba(93,130,255,0.30) !important;
    box-shadow:none !important;
}

div[data-testid="stFileUploader"] button:hover{
    background:rgba(93,130,255,0.30) !important;
}

div[data-testid="stFileUploader"] *{
    background:transparent !important;
    color:var(--text) !important;
    border-color:rgba(255,255,255,0.08) !important;
}

div[data-testid="stFileUploader"] input,
div[data-testid="stFileUploader"] label,
div[data-testid="stFileUploader"] button{
    color:var(--text) !important;
}

div[data-testid="stDataFrame"] div[role="grid"],
div[data-testid="stDataFrame"] div[role="grid"] *{
    background:#030711 !important;
    color:#f8fafc !important;
    border-color:rgba(255,255,255,0.05) !important;
}

div[data-testid="stDataFrame"] div[role="row"],
div[data-testid="stDataFrame"] div[role="row"] > div,
div[data-testid="stDataFrame"] div[role="gridcell"],
div[data-testid="stDataFrame"] div[role="columnheader"]{
    background:#030711 !important;
    color:#f8fafc !important;
    border-color:rgba(255,255,255,0.05) !important;
}

div[data-testid="stDataFrame"] div.stDataFrame,
div[data-testid="stDataFrame"] div.stDataFrame > div{
    background:#030711 !important;
}

div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-testid="stSelectbox"] select,
div[data-testid="stMultiselect"] div,
div[data-testid="stSlider"] div{
    background:rgba(5,9,18,0.95) !important;
    border:1px solid rgba(255,255,255,0.08) !important;
    border-radius:10px !important;
    padding:10px !important;
    color:var(--primary) !important;
}

div[data-testid="stTextInput"] input::placeholder,
div[data-testid="stTextArea"] textarea::placeholder{
    color:rgba(111,167,255,0.6) !important;
}

div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea{
    box-shadow:inset 0 0 0 1px rgba(255,255,255,0.06) !important;
}

div[data-testid="stDataFrame"]{background:transparent !important;}
div[data-testid="stDataFrame"] table{background:#030711 !important;color:#f8fafc !important;}
div[data-testid="stDataFrame"] th,
div[data-testid="stDataFrame"] td{
    background:#030711 !important;
    color:#f8fafc !important;
    border-color:rgba(255,255,255,0.05) !important;
}
div[data-testid="stDataFrame"] thead th{
    background:#050a14 !important;
    color:#fff !important;
    border-bottom:1px solid rgba(255,255,255,0.08) !important;
}
div[data-testid="stDataFrame"] tbody td{
    background:#030711 !important;
    color:#f8fafc !important;
    border-color:rgba(255,255,255,0.05) !important;
}

.kpi-row{display:flex;gap:16px;margin-bottom:18px;flex-wrap:wrap}
.kpi-card{
    position:relative;
    background:linear-gradient(145deg, rgba(15,23,42,0.9), rgba(30,41,59,0.7));
    border:1px solid rgba(99,102,241,0.12);
    border-radius:14px;
    padding:18px 20px;
    min-height:110px;
    overflow:hidden;
    transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.kpi-card:hover{
    transform:translateY(-2px);
    border-color:rgba(99,102,241,0.25);
    box-shadow:0 8px 24px rgba(0,0,0,0.2);
}
.kpi-card .kpi-accent{
    position:absolute;left:0;top:0;width:100%;height:2px;
}
.kpi-card.accent-revenue .kpi-accent{background:linear-gradient(90deg,#6366f1,transparent)}
.kpi-card.accent-units .kpi-accent{background:linear-gradient(90deg,#10b981,transparent)}
.kpi-card.accent-yoy .kpi-accent{background:linear-gradient(90deg,#f59e0b,transparent)}
.kpi-card.accent-person .kpi-accent{background:linear-gradient(90deg,#ec4899,transparent)}
.kpi-card.accent-model .kpi-accent{background:linear-gradient(90deg,#8b5cf6,transparent)}
.kpi-card.accent-regions .kpi-accent{background:linear-gradient(90deg,#06b6d4,transparent)}
.kpi-card.accent-aov .kpi-accent{background:linear-gradient(90deg,#14b8a6,transparent)}
.kpi-card.accent-colour .kpi-accent{background:linear-gradient(90deg,#f97316,transparent)}
.kpi-card.accent-orders .kpi-accent{background:linear-gradient(90deg,#818cf8,transparent)}
.kpi-card.accent-rpu .kpi-accent{background:linear-gradient(90deg,#34d399,transparent)}
.kpi-card.accent-date .kpi-accent{background:linear-gradient(90deg,#64748b,transparent)}
.kpi-card.accent-make .kpi-accent{background:linear-gradient(90deg,#a855f7,transparent)}
.kpi-card.accent-share .kpi-accent{background:linear-gradient(90deg,#6366f1,transparent)}
.kpi-card.kpi-featured{
    box-shadow:0 0 0 1px rgba(99,102,241,0.4), 0 4px 20px rgba(99,102,241,0.15);
}
.kpi-card .kv{font-size:26px;font-weight:800;color:#f1f5f9;letter-spacing:-0.5px;line-height:1.1;margin-bottom:4px;position:relative;z-index:1;}
.kpi-card .kl{font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1.2px;display:flex;align-items:center;gap:5px;position:relative;z-index:1;}
.kpi-card .ks{font-size:11px;color:#475569;margin-top:6px;position:relative;z-index:1;}
.kpi-card .kpi-trend{
    position:absolute;top:12px;right:14px;font-size:11px;font-weight:700;z-index:2;
}
.kpi-card .kpi-trend.up{color:#6ee7b7}
.kpi-card .kpi-trend.down{color:#fca5a5}
@keyframes countUp{
  from{opacity:0;transform:translateY(4px)}
  to{opacity:1;transform:translateY(0)}
}
.kpi-card.kpi-anim{
  animation:countUp .3s ease-out both;
}
.kpi-section-title{
  font-size:22px;font-weight:800;letter-spacing:-0.3px;margin:0 0 4px 0;
  background:linear-gradient(135deg,#e2e8f0,#94a3b8);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.kpi-section-sub{font-size:11px;color:#475569;margin-bottom:14px}
.kpi-chart-card{
  background:linear-gradient(145deg, rgba(15,23,42,0.9), rgba(30,41,59,0.7));
  border:1px solid rgba(99,102,241,0.12);
  border-radius:14px;padding:14px 16px;margin-bottom:8px;
}
.kpi-filter-row{margin-bottom:8px}
.kpi-filter-sep{border:none;border-top:1px solid rgba(99,102,241,0.1);margin:8px 0 14px 0}

.sql-strip{display:flex;align-items:center;gap:10px;background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.008));border-radius:10px;padding:8px;border:1px solid var(--border)}
.sql-strip .badge{background:rgba(79,124,255,0.12);color:var(--primary);padding:6px 8px;border-radius:6px;font-weight:800}
.code-card{font-family:SFMono-Regular,Menlo,monospace;background:rgba(0,0,0,0.35);padding:12px;border-radius:8px;border:1px solid rgba(255,255,255,0.04)}
.exec-box{background:linear-gradient(90deg, rgba(79,124,255,0.08), rgba(124,58,237,0.04));border-left:3px solid var(--primary);border-radius:10px;padding:12px;color:var(--text)}
.dq-badge-green{background:rgba(0,209,122,0.08);color:var(--success);padding:6px 8px;border-radius:8px;font-weight:700}
.dq-badge-amber{background:rgba(255,176,32,0.06);color:var(--warn);padding:6px 8px;border-radius:8px;font-weight:700}
.dq-badge-red{background:rgba(255,107,107,0.06);color:var(--danger);padding:6px 8px;border-radius:8px;font-weight:700}

/* ══════════════════════════════════════════════════════════════
   V11 POLISH PASS
   ══════════════════════════════════════════════════════════════ */

/* Global scrollbar */
*{scrollbar-width:thin;scrollbar-color:rgba(79,124,255,.35) transparent;}
*::-webkit-scrollbar{width:7px;height:7px;}
*::-webkit-scrollbar-thumb{background:rgba(79,124,255,.35);border-radius:8px;}
*::-webkit-scrollbar-thumb:hover{background:rgba(79,124,255,.55);}

/* Branding header */
.brand-header{
    display:flex;align-items:center;justify-content:space-between;gap:14px;
    padding:14px 20px;margin:-6px 0 14px 0;border-radius:16px;
    background:linear-gradient(100deg, rgba(79,124,255,0.14), rgba(124,58,237,0.10) 55%, rgba(0,209,122,0.06));
    border:1px solid rgba(255,255,255,0.08);position:relative;overflow:hidden;
    transition:border-color .25s ease, box-shadow .25s ease, transform .25s ease;
}
.brand-header:before{
    content:"";position:absolute;left:0;top:0;width:100%;height:2px;
    background:linear-gradient(90deg,#4f7cff,#7c3aed,#00d17a,#4f7cff);
    background-size:300% 100%;animation:brandSheen 6s linear infinite;
    box-shadow:0 0 14px rgba(79,124,255,.55);
}
@keyframes brandSheen{0%{background-position:0% 0}100%{background-position:300% 0}}
.brand-header:hover{
    border-color:rgba(124,158,255,.45);
    box-shadow:0 12px 34px rgba(79,124,255,0.18), 0 0 0 1px rgba(124,58,237,0.12);
    transform:translateY(-1px);
}
.brand-left{display:flex;flex-direction:column;gap:2px;}
.brand-eyebrow{
    color:#fbbf24;font-size:15px;font-weight:800;letter-spacing:1.6px;text-transform:uppercase;
    text-shadow:0 0 10px rgba(251,191,36,.25);display:flex;align-items:center;gap:8px;
}
.brand-tagline{font-size:11.5px;font-weight:500;color:#aebbd0;letter-spacing:.2px;}
.brand-pill{
    font-size:10.5px;font-weight:800;letter-spacing:1px;color:#dce7ff;
    background:linear-gradient(90deg, rgba(79,124,255,.18), rgba(124,58,237,.18));
    border:1px solid rgba(255,255,255,.10);border-radius:999px;padding:6px 12px;white-space:nowrap;
    transition:all .2s ease;
}
.brand-header:hover .brand-pill{
    border-color:rgba(124,158,255,.5);
    box-shadow:0 0 14px rgba(79,124,255,.25);
}

/* Sidebar width */
[data-testid="stSidebar"]{width:308px !important;}
[data-testid="stSidebar"] > div{padding-top:6px !important;}
section[data-testid="stSidebar"] .block-container{padding:6px 10px 10px 10px !important;}

/* Aligned stat grids */
.stat-row{display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:10px;margin-top:8px;align-items:stretch;}
.stat-card{
    min-width:0;padding:12px 10px;border-radius:12px;text-align:center;
    background:linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.012));
    border:1px solid rgba(255,255,255,0.07);
    transition:border-color .2s ease, transform .2s ease;
}
.stat-card:hover{border-color:rgba(124,158,255,.30);transform:translateY(-2px);}
.stat-card .sv{font-size:17px;font-weight:800;color:var(--primary);}
.stat-card .sl{font-size:10px;color:var(--subtext);text-transform:uppercase;letter-spacing:.5px;margin-top:3px;}

/* Data quality issue rows */
.dq-issue-row{
    display:flex;align-items:center;gap:8px;flex-wrap:wrap;
    padding:7px 10px;border-radius:8px;
    background:rgba(255,255,255,0.015);
    border:1px solid rgba(255,255,255,0.04);
    margin-bottom:4px;
}

/* Expanders */
[data-testid="stExpander"]{
    background:linear-gradient(180deg, rgba(255,255,255,0.025), rgba(255,255,255,0.008)) !important;
    border:1px solid rgba(255,255,255,0.08) !important;
    border-radius:12px !important;
    overflow:hidden;
}
[data-testid="stExpander"] summary{
    color:#e8eefc !important;font-weight:700 !important;padding:10px 12px !important;
}
[data-testid="stExpander"] summary:hover{color:#8fb4ff !important;}
[data-testid="stExpander"] [data-testid="stExpanderDetails"]{
    background:rgba(3,7,17,0.4) !important;padding:10px 12px !important;
}

/* Selects / dropdowns */
div[data-baseweb="select"] > div{
    background:rgba(5,9,18,0.95) !important;
    border:1px solid rgba(255,255,255,0.10) !important;
    border-radius:10px !important;
    color:var(--text) !important;
}
div[data-baseweb="popover"] ul,
div[data-baseweb="menu"],
ul[role="listbox"]{
    background:#0a0f1c !important;
    border:1px solid rgba(255,255,255,0.10) !important;
}
div[data-baseweb="popover"] li,
ul[role="listbox"] li{color:var(--text) !important;}
div[data-baseweb="popover"] li:hover,
ul[role="listbox"] li:hover{background:rgba(79,124,255,0.18) !important;}

/* AI Query search bar */
.sql-text{color:#a9c4ff;font-family:SFMono-Regular,Menlo,monospace;font-size:12px;}
div[data-testid="stTextInput"] input:focus{
    border-color:#4f7cff !important;
    box-shadow:0 0 0 3px rgba(79,124,255,0.18) !important;
}
[data-testid="stChatInput"] textarea,
div[data-testid="stTextInput"] input{
    transition:box-shadow .2s ease, border-color .2s ease;
}

/* Button hover interactions */
.stButton>button,
div[data-testid="stButton"]>button,
[data-testid="stDownloadButton"]>button{
    transition:transform .15s ease, box-shadow .15s ease, filter .15s ease !important;
}
.stButton>button:hover,
div[data-testid="stButton"]>button:hover,
[data-testid="stDownloadButton"]>button:hover{
    transform:translateY(-2px) !important;
    filter:brightness(1.08);
}
.stButton>button:active,
div[data-testid="stButton"]>button:active{
    transform:translateY(0) !important;
}
[data-testid="stDownloadButton"]>button{
    background:linear-gradient(90deg,#00b96b,#00d17a) !important;
    border:none !important;
    color:#04140c !important;
    font-weight:800 !important;
}

/* Radio spacing */
div[role="radiogroup"] label{font-weight:700 !important;font-size:12.5px !important;}

/* Metrics */
[data-testid="stMetric"]{
    background:linear-gradient(180deg, rgba(255,255,255,0.025), rgba(255,255,255,0.008));
    border:1px solid rgba(255,255,255,0.07);
    border-radius:12px;
    padding:10px 14px;
}

/* ══════════════════════════════════════════════════════════════
   CUSTOM AI LOADING OVERLAY
   ══════════════════════════════════════════════════════════════ */

/* Hide Streamlit's native running indicator */
[data-testid="stStatusWidget"]{
    opacity:0 !important;
    pointer-events:none !important;
}

/* Full-screen overlay */
.ai-loader-overlay{
    position:fixed;inset:0;z-index:99998;
    display:none;align-items:center;justify-content:center;
    background:rgba(3,7,17,0.62);
    backdrop-filter:blur(4px);
    animation:fadeInOverlay .2s ease;
}
@keyframes fadeInOverlay{from{opacity:0}to{opacity:1}}

/* CHANGED: trigger overlay via Streamlit running state */
body:has([data-testid="stStatusWidget"]) .ai-loader-overlay{
    display:flex;
}

/* Loader card */
.ai-loader{
    position:static;
    width:300px;
    padding:26px 24px;
    border-radius:20px;
    background:linear-gradient(180deg, rgba(10,15,30,.98), rgba(18,25,45,.98));
    border:1px solid rgba(79,124,255,.28);
    box-shadow:0 0 50px rgba(79,124,255,.22), 0 20px 60px rgba(0,0,0,.5);
    text-align:center;
}

/* AI orb spinner */
.ai-orb{width:64px;height:64px;margin:2px auto 14px auto;position:relative;}
.ai-orb .ring{position:absolute;inset:0;border-radius:50%;border:2px solid transparent;}
.ai-orb .ring1{
    border-top-color:#4f7cff;
    border-right-color:#4f7cff;
    animation:orbSpin 1.1s linear infinite;
}
.ai-orb .ring2{
    inset:9px;
    border-bottom-color:#7c3aed;
    border-left-color:#7c3aed;
    animation:orbSpin 1.6s linear infinite reverse;
}
.ai-orb .core{
    position:absolute;inset:23px;border-radius:50%;
    background:radial-gradient(circle at 35% 35%, #b9cdff, #4f7cff 55%, #7c3aed);
    box-shadow:0 0 20px rgba(79,124,255,.85);
    animation:orbPulse 1.3s ease-in-out infinite;
}
@keyframes orbSpin{to{transform:rotate(360deg);}}
@keyframes orbPulse{
    0%,100%{transform:scale(1);opacity:1;}
    50%{transform:scale(1.14);opacity:.82;}
}

/* Fallback for browsers without :has() */
@supports not selector(:has(a)){
    .ai-loader-overlay{display:none !important;}
}

/* Execution path badges */
.badge-deterministic {
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.3);
    color: #6ee7b7;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
    display: inline-block;
}

.badge-fallback {
    background: rgba(245, 158, 11, 0.12);
    border: 1px solid rgba(245, 158, 11, 0.3);
    color: #fcd34d;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    display: inline-block;
}

.badge-cached {
    background: rgba(59, 130, 246, 0.12);
    border: 1px solid rgba(59, 130, 246, 0.3);
    color: #93c5fd;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    display: inline-block;
}

.badge-oob {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.2);
    color: #fca5a5;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    display: inline-block;
}

/* Conversation context banner */
.conv-context-banner {
    background: rgba(99, 102, 241, 0.1);
    border-left: 3px solid #6366f1;
    padding: 6px 12px;
    border-radius: 0 8px 8px 0;
    font-size: 12px;
    color: #a5b4fc;
    margin-bottom: 8px;
}

/* OOB deflection card */
.oob-card {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.2);
    border-radius: 12px;
    padding: 16px 20px;
    margin: 12px 0;
}

/* Evidence detail panel */
.evidence-panel {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(99, 102, 241, 0.15);
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 11px;
    color: #94a3b8;
}

/* Metric resolution info */
.metric-info-pill {
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.2);
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 11px;
    color: #6ee7b7;
    display: inline-block;
    margin: 4px 0;
}

/* Conversation state panel in sidebar */
.conv-state-panel {
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(99, 102, 241, 0.2);
    border-radius: 10px;
    padding: 12px;
    margin: 8px 0;
}

/* Query stats row */
.query-stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    border-bottom: 1px solid rgba(99,102,241,0.08);
    font-size: 11px;
}

/* ═══════════════════════════════════
   CHAT MODE STYLES (Prompt 2)
═══════════════════════════════════ */
.chat-outer-wrap { display:flex; flex-direction:column; height:100%; }
.chat-controls-bar {
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(99, 102, 241, 0.15);
    border-radius: 12px;
    padding: 10px 16px;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
}
.user-bubble {
    display: flex; justify-content: flex-end; align-items: flex-end;
    gap: 8px; margin: 10px 0 4px 60px;
}
.user-bubble-text {
    background: rgba(99, 102, 241, 0.12);
    border: 1px solid rgba(99, 102, 241, 0.25);
    color: #e2e8f0;
    padding: 10px 16px;
    border-radius: 18px 18px 4px 18px;
    font-size: 14px; line-height: 1.5;
    max-width: 100%;
}
.user-avatar, .assistant-avatar {
    width: 30px; height: 30px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; flex-shrink: 0;
}
.user-avatar {
    background: rgba(99, 102, 241, 0.15);
    border: 1px solid rgba(99, 102, 241, 0.3);
    color: #818cf8;
}
.assistant-avatar {
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.25);
    color: #34d399;
    margin-top: 4px;
}
.assistant-bubble {
    display: flex; align-items: flex-start; gap: 8px;
    margin: 10px 60px 4px 0;
}
.assistant-card {
    background: rgba(15, 23, 42, 0.5);
    border: 1px solid rgba(148, 163, 184, 0.1);
    border-radius: 4px 18px 18px 18px;
    padding: 14px 18px; width: 100%;
}
.narration-card {
    background: rgba(16, 185, 129, 0.05);
    border: 1px solid rgba(16, 185, 129, 0.15);
    border-left: 3px solid #34d399;
    border-radius: 0 8px 8px 0;
    padding: 14px 18px; margin-bottom: 12px;
}
.narration-headline {
    font-size: 13px; font-weight: 700; color: #6ee7b7;
    margin-bottom: 8px; display: flex; align-items: center; gap: 6px;
}
.narration-body {
    font-size: 13px; color: #cbd5e1; line-height: 1.7; margin-bottom: 10px;
}
.chat-input-area {
    background: rgba(30, 41, 59, 0.85);
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 14px;
    padding: 10px 12px;
    margin-top: 10px;
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.25);
}
.chat-input-area-visible {
    background: linear-gradient(180deg, rgba(51, 65, 85, 0.55), rgba(30, 41, 59, 0.9));
    border: 1.5px solid rgba(165, 180, 252, 0.45);
}
[data-testid="stChatInput"] {
    background: rgba(15, 23, 42, 0.75) !important;
    border: 1px solid rgba(148, 163, 184, 0.4) !important;
    border-radius: 12px !important;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] {
    border-color: rgba(165, 180, 252, 0.45) !important;
    color: #e2e8f0 !important;
    caret-color: #a5b4fc !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #94a3b8 !important;
    opacity: 1 !important;
}
.sem-term-badge {
    display: inline-block;
    background: rgba(99, 102, 241, 0.12);
    border: 1px solid rgba(99, 102, 241, 0.28);
    color: #c7d2fe;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    margin: 2px 4px 6px 0;
}
.badge-semantic {
    background: rgba(99, 102, 241, 0.14);
    border: 1px solid rgba(99, 102, 241, 0.35);
    color: #a5b4fc;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    display: inline-block;
}
.narration-findings {
    border-top: 1px solid rgba(16,185,129,0.1);
    padding-top: 8px; margin-top: 8px;
}
.narration-finding-item {
    font-size: 12px; color: #94a3b8; margin: 3px 0; line-height: 1.4;
}
.narration-recommendation {
    background: rgba(245,158,11,0.07);
    border-left: 3px solid #f59e0b;
    padding: 8px 12px; border-radius: 0 6px 6px 0;
    font-size: 12px; color: #fcd34d; margin-top: 8px;
}
.whatif-baseline-box {
    background: rgba(99,102,241,0.1);
    border: 1px solid rgba(99,102,241,0.2);
    border-radius: 10px; padding: 16px; text-align: center;
}
.whatif-scenario-box-up {
    background: rgba(16,185,129,0.1);
    border: 1px solid rgba(16,185,129,0.25);
    border-radius: 10px; padding: 16px; text-align: center;
}
.whatif-scenario-box-down {
    background: rgba(239,68,68,0.1);
    border: 1px solid rgba(239,68,68,0.2);
    border-radius: 10px; padding: 16px; text-align: center;
}
.whatif-value-label {
    font-size: 10px; color: #94a3b8; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 6px;
}
.whatif-value-number { font-size: 22px; font-weight: 800; margin-bottom: 4px; }
.proactive-insight-card {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(99, 102, 241, 0.1);
    border-radius: 10px; padding: 12px 16px; margin: 5px 0;
    display: flex; align-items: center; gap: 12px;
    transition: all 0.2s ease;
}
.proactive-insight-card:hover {
    border-color: rgba(99, 102, 241, 0.3);
    background: rgba(99, 102, 241, 0.08);
    transform: translateX(2px);
}
.proactive-insight-icon { font-size: 20px; flex-shrink: 0; }
.proactive-insight-title { font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 2px; }
.proactive-insight-summary { font-size: 11px; color: #94a3b8; line-height: 1.4; }
.proactive-ask-arrow { margin-left: auto; font-size: 11px; color: #6366f1; font-weight: 600; }
.chat-welcome-card {
    background: linear-gradient(135deg, rgba(99,102,241,0.07), rgba(16,185,129,0.04));
    border: 1px solid rgba(99, 102, 241, 0.12);
    border-radius: 14px; padding: 20px 24px; margin-bottom: 16px;
}
.chat-welcome-title { font-size: 15px; font-weight: 700; color: #e2e8f0; margin-bottom: 4px; }
.chat-welcome-subtitle { font-size: 12px; color: #64748b; margin-bottom: 16px; }
.msg-timestamp { font-size: 10px; color: #475569; margin: 2px 0 8px; padding-left: 40px; }
.msg-timestamp-right { font-size: 10px; color: #475569; margin: 2px 0 8px; text-align: right; padding-right: 40px; }
.result-header-bar {
    display: flex; align-items: center; gap: 10px; padding: 6px 0 10px;
    border-bottom: 1px solid rgba(99,102,241,0.08); margin-bottom: 10px; flex-wrap: wrap;
}
.result-stat-pill {
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(99, 102, 241, 0.1);
    border-radius: 10px; padding: 2px 10px; font-size: 11px; color: #94a3b8;
    display: inline-flex; align-items: center; gap: 4px;
}
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}
.fade-in-up { animation: fadeInUp 0.25s ease forwards; }
.chat-error-card {
    background: rgba(239, 68, 68, 0.06);
    border: 1px solid rgba(239, 68, 68, 0.15);
    border-left: 3px solid #ef4444;
    border-radius: 8px; padding: 12px 16px; margin: 4px 0;
}
.chat-oob-card {
    background: rgba(245, 158, 11, 0.06);
    border: 1px solid rgba(245, 158, 11, 0.15);
    border-left: 3px solid #f59e0b;
    border-radius: 8px; padding: 12px 16px;
}
.suggestion-chip {
    display: inline-block;
    background: rgba(99,102,241,0.08);
    border: 1px solid rgba(99,102,241,0.15);
    border-radius: 16px; padding: 4px 12px;
    font-size: 11px; color: #a5b4fc; margin: 3px;
}
.suggestion-chip:hover {
    background: rgba(99,102,241,0.18);
    border-color: rgba(99,102,241,0.35);
    color: #c7d2fe;
}

/* ══════════════════════════════════════════════════════════════
   UI UPGRADE — DQ, sidebar, query chrome, cards
   ══════════════════════════════════════════════════════════════ */
.stat-card,.dq-stat-box{
  background:rgba(15,23,42,0.8);
  border:1px solid rgba(99,102,241,0.1);
  border-radius:10px;
  padding:12px 16px;
  text-align:center;
  transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.stat-card:hover,.dq-stat-box:hover{
  transform:translateY(-2px);
  box-shadow:0 8px 24px rgba(0,0,0,0.2);
  border-color:rgba(99,102,241,0.25);
}
.dq-stat-box .sv{font-size:22px;font-weight:800}
.dq-stat-box .sl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#475569;margin-top:4px}
.dq-banner-ok{
  background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.2);
  border-left:3px solid #10b981;border-radius:0 8px 8px 0;
  padding:10px 16px;color:#6ee7b7;font-size:13px;font-weight:500;margin:8px 0;
}
.dq-banner-warn{
  background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.2);
  border-left:3px solid #f59e0b;border-radius:0 8px 8px 0;
  padding:10px 16px;color:#fcd34d;font-size:13px;font-weight:500;margin:8px 0;
}
.dq-banner-err{
  background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);
  border-left:3px solid #ef4444;border-radius:0 8px 8px 0;
  padding:10px 16px;color:#fca5a5;font-size:13px;font-weight:500;margin:8px 0;
}
.dq-health-label{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:6px}
.dq-status-pill{
  background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.25);
  color:#6ee7b7;border-radius:20px;padding:4px 12px;font-size:11px;font-weight:700;
  display:inline-block;margin-top:8px;
}
.schema-pill{
  display:inline-block;border-radius:12px;padding:3px 10px;font-size:11px;font-weight:600;margin:2px 4px 2px 0;
}
.schema-pill.num{background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.25);color:#93c5fd}
.schema-pill.txt{background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.22);color:#6ee7b7}
.schema-pill.date{background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.22);color:#fcd34d}
.schema-pill.bool{background:rgba(139,92,246,0.12);border:1px solid rgba(139,92,246,0.22);color:#c4b5fd}

.sb-title{font-size:10px !important;font-weight:800 !important;letter-spacing:1.5px !important;text-transform:uppercase;margin-bottom:4px}
.sb-divider{border:none;border-top:1px solid rgba(99,102,241,0.08);margin:8px 0}
.sb-upload-wrap{
  background:rgba(245,158,11,0.06);border:1px dashed rgba(245,158,11,0.25);
  border-radius:10px;padding:10px 12px;
}
.sb-upload-wrap .sb-title{color:#fcd34d !important}
.sb-semantic-wrap .sb-title{
  display:inline-block;background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.2);
  color:#c4b5fd !important;border-radius:4px;padding:2px 8px;
}
.sb-views-wrap .sb-title{color:#818cf8 !important}
.sb-conv-wrap .sb-title{color:#f9a8d4 !important}
.sb-llm-wrap .sb-title{color:#a5b4fc !important}

.sem-term-badge.measure{
  background:rgba(124,58,237,0.12);border:1px solid rgba(124,58,237,0.25);color:#c4b5fd;
}
.sem-term-badge.dimension{
  background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.25);color:#93c5fd;
}
.sem-term-badge.attribute{
  background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.2);color:#6ee7b7;
}
.sem-term-badge.glossary{
  background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);color:#fde68a;
}
.sem-term-badge .sem-expr{
  color:#64748b;font-size:9px;font-style:italic;margin-left:4px;opacity:1;
}
.badge-semantic{
  background:linear-gradient(135deg, rgba(236,72,153,0.15), rgba(99,102,241,0.15)) !important;
  border:1px solid rgba(236,72,153,0.25) !important;
  color:#f9a8d4 !important;
  border-radius:20px !important;
}
.result-stat-pill{
  background:rgba(30,41,59,0.7) !important;
  border:1px solid rgba(99,102,241,0.1) !important;
  color:#94a3b8 !important;
}
.sem-ctx-expander-hint{
  background:rgba(16,185,129,0.05);border-left:2px solid #10b981;
  border-radius:0 6px 6px 0;color:#6ee7b7;font-size:12px;font-weight:600;
  padding:6px 10px;margin-bottom:6px;
}
div[data-testid="stExpander"] details:hover summary{
  background:rgba(99,102,241,0.04);border-radius:6px;
}
.ask-run-btn-wrap button{
  font-size:16px !important;
}

/* ═══ chat_ench.md — message types, trust, surprise ═══ */
.chat-msg-gap{margin-bottom:16px;}
.assistant-card{padding:12px 18px;}
.card-chat{
  background:rgba(30,41,59,0.5);border:1px solid rgba(148,163,184,0.1);
  border-radius:4px 18px 18px 18px;
}
.card-query{
  background:rgba(15,23,42,0.7);border:1px solid rgba(99,102,241,0.15);
  border-left:3px solid #6366f1;border-radius:4px 18px 18px 18px;
}
.card-whatif{
  background:rgba(245,158,11,0.05);border:1px solid rgba(245,158,11,0.15);
  border-left:3px solid #f59e0b;border-radius:4px 18px 18px 18px;
}
.card-surprise{
  background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.2);
  border-left:3px solid #f59e0b;border-radius:4px 18px 18px 18px;
}
.card-blocked{
  background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.15);
  border-left:3px solid #ef4444;border-radius:4px 18px 18px 18px;color:#fca5a5;
}
.card-oob{
  background:rgba(245,158,11,0.05);border:1px solid rgba(245,158,11,0.12);
  border-left:3px solid #f59e0b;border-radius:4px 18px 18px 18px;color:#fde68a;
}
.card-clarification{
  background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.15);
  border-left:3px solid #818cf8;border-radius:4px 18px 18px 18px;
}
.card-error{
  background:rgba(239,68,68,0.05);border:1px solid rgba(239,68,68,0.12);
  border-left:3px solid #ef4444;border-radius:4px 18px 18px 18px;
}
.chat-reply-text{font-size:13px;line-height:1.7;color:#cbd5e1;}
.finding-bullet{
  background:rgba(99,102,241,0.05);border-left:2px solid #6366f1;
  padding:6px 10px;border-radius:0 4px 4px 0;margin:3px 0;font-size:12px;color:#cbd5e1;
}
.chat-results-label{font-size:11px;color:#64748b;margin:8px 0 4px;font-weight:600;}
.surprise-header{font-size:14px;font-weight:700;color:#fcd34d;margin-bottom:10px;}
.surprise-highlight{
  background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.25);
  border-radius:10px;padding:12px 14px;font-size:15px;font-weight:700;color:#fde68a;margin-bottom:12px;
}
.surprise-rec-title{font-size:12px;color:#94a3b8;margin:8px 0;}
.surprise-opp{font-size:13px;font-weight:700;color:#fcd34d;margin-top:10px;}
.trust-score-card{
  background:rgba(15,23,42,0.6);border:1px solid rgba(148,163,184,0.15);
  border-radius:10px;padding:12px 14px;margin:10px 0;color:#94a3b8;
}
.trust-score-summary{
  background:rgba(15,23,42,0.45);border:1px solid rgba(148,163,184,0.12);
  border-radius:10px;padding:10px 12px;margin:8px 0 4px;color:#94a3b8;
  display:flex;flex-wrap:wrap;align-items:center;gap:10px;
}
.trust-title{font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:6px;}
.trust-score-line{display:flex;align-items:baseline;gap:10px;margin-bottom:6px;}
.trust-pct{font-size:22px;font-weight:800;line-height:1;}
.trust-band{font-size:13px;font-weight:700;}
.trust-bar{height:6px;background:rgba(148,163,184,0.15);border-radius:4px;overflow:hidden;margin-bottom:0;flex:1;min-width:120px;}
.trust-bar-fill{height:100%;border-radius:4px;}
.trust-based{font-size:11px;margin-bottom:4px;color:#64748b;}
.trust-row{display:flex;justify-content:space-between;font-size:11px;padding:2px 0;}
.trust-note{font-size:11px;margin-top:8px;color:#94a3b8;}
.trust-note.warn{color:#fcd34d;}
.okf-citation{
  font-size:11px;color:#7dd3fc;margin:6px 0 4px;
  background:rgba(14,165,233,0.06);border-left:3px solid #38bdf8;
  padding:6px 10px;border-radius:0 6px 6px 0;
}
.badge-modified{
  display:inline-block;font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px;
  background:rgba(16,185,129,0.12);color:#6ee7b7;border:1px solid rgba(16,185,129,0.25);
  margin:4px 0 8px;
}
.mod-context-banner{
  background:rgba(16,185,129,0.06);border-left:3px solid #10b981;
  font-size:11px;color:#6ee7b7;padding:6px 12px;border-radius:0 6px 6px 0;
  margin:6px 0 8px;
}
</style>

<div class="ai-loader-overlay">
  <div class="ai-loader">
    <div class="ai-loader-title">AI DATA PLATFORM</div>
    <div class="ai-orb">
      <div class="ring ring1"></div>
      <div class="ring ring2"></div>
      <div class="core"></div>
    </div>
    <div class="ai-loader-main">Thinking…</div>
    <div class="ai-loader-sub">Crunching data with semantic intelligence</div>
    <div class="loader-dots"><span></span><span></span><span></span></div>
  </div>
</div>

<div class="ai-animated-bg">
    <div class="glow g1"></div>
    <div class="glow g2"></div>
    <div class="glow g3"></div>
</div>
""", unsafe_allow_html=True)
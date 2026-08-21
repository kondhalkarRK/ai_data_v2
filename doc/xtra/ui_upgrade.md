PROMPT: UI VISUAL OVERHAUL — KPI SUMMARY, DATA PREVIEW & AI QUERY
====================================================================

You are a senior UI/UX engineer upgrading the visual design of
ai_data_v2. Based on three screenshots provided, make targeted
improvements to three tabs and the global colour system.

No functionality must be removed. Only visual and layout changes.

════════════════════════════════════════════════════════════════
SECTION 1 — GLOBAL COLOUR & STYLE SYSTEM
════════════════════════════════════════════════════════════════

FILE: config/styles.py

PROBLEM OBSERVED IN SCREENSHOTS:
  - Too many solid dark blue buttons (#4f46e5, #6366f1)
  - Buttons look heavy and congested
  - Sidebar buttons (RESET, CACHE, CLEAR) are
    solid dark blue rectangles — too dominant
  - Tab selector pills are solid purple/blue
  - Everything feels same-weight visually
  - No colour hierarchy — everything competes

REPLACE ALL SOLID DARK BLUE BUTTONS WITH:

Primary action buttons (Run, Submit, Execute):
  background: linear-gradient(
    135deg,
    rgba(99, 102, 241, 0.25),
    rgba(139, 92, 246, 0.2)
  )
  border: 1px solid rgba(139, 92, 246, 0.4)
  color: #c4b5fd
  border-radius: 10px
  font-weight: 600
  letter-spacing: 0.3px
  box-shadow: 0 2px 8px rgba(139,92,246,0.15)
  hover: background shifts to rgba(139,92,246,0.35)
  NOT solid fill

Secondary buttons (Reset, Cache, Clear, Views):
  background: rgba(30, 41, 59, 0.7)
  border: 1px solid rgba(148, 163, 184, 0.15)
  color: #94a3b8
  border-radius: 8px
  hover: border-color rgba(148,163,184,0.3)
         color #cbd5e1
  No glow, no gradient — understated

Danger/Clear buttons:
  background: rgba(239, 68, 68, 0.08)
  border: 1px solid rgba(239, 68, 68, 0.2)
  color: #fca5a5
  hover: rgba(239, 68, 68, 0.15)

Success/Active state:
  background: rgba(16, 185, 129, 0.1)
  border: 1px solid rgba(16, 185, 129, 0.25)
  color: #6ee7b7

ACTIVE TAB PILL STYLE:
  Currently: solid purple fill
  Change to: gradient pill
  background: linear-gradient(
    135deg, #7c3aed, #6366f1
  )
  box-shadow: 0 4px 15px rgba(124,58,237,0.4)
  color: white
  border-radius: 20px
  padding: 6px 18px
  font-weight: 700
  Inactive tabs: transparent, color #64748b

GLOBAL COLOUR TOKENS (add as CSS variables):
  --color-primary: #818cf8
  --color-primary-bg: rgba(99,102,241,0.1)
  --color-primary-border: rgba(99,102,241,0.2)
  --color-success: #6ee7b7
  --color-success-bg: rgba(16,185,129,0.08)
  --color-warning: #fcd34d
  --color-warning-bg: rgba(245,158,11,0.08)
  --color-danger: #fca5a5
  --color-danger-bg: rgba(239,68,68,0.08)
  --color-surface: rgba(15,23,42,0.8)
  --color-surface-2: rgba(30,41,59,0.6)
  --color-border: rgba(148,163,184,0.1)
  --color-text-primary: #e2e8f0
  --color-text-secondary: #94a3b8
  --color-text-muted: #64748b

SIDEBAR BUTTON REDESIGN:
  RESET and CACHE buttons in LLM Usage section:
    Side by side, equal width
    RESET: secondary style (grey/muted)
    CACHE: success style (green tint)
    Height: 32px, compact
    Font-size: 11px, uppercase, letter-spacing

  CLEAR button in Views section:
    Danger style (red tint)
    Full width, height 32px
    Font-size: 11px

  All sidebar buttons:
    Remove the heavy dark blue fill
    Use appropriate semantic colour above

════════════════════════════════════════════════════════════════
SECTION 2 — KPI SUMMARY TAB OVERHAUL
════════════════════════════════════════════════════════════════

FILE: ui/tab_kpi.py

PROBLEMS OBSERVED IN SCREENSHOT:
  1. Only 6 KPI cards shown — feels empty
     especially bottom row has 2 wide cards
  2. Bottom row cards (SUV, 15) are too wide
     taking up full half-screen each
  3. Cards show raw column names as subtitles
     (price_per_unit, order_qty) — ugly
  4. Layout is inconsistent — top 4 cards
     then bottom 2 cards — not uniform grid
  5. Filter section has too much empty space
     below Year and Month dropdowns
  6. "All metrics computed directly from data"
     line looks orphaned
  7. No visual hierarchy between cards

CHANGE 1 — ADD MORE KPI CARDS:
The KPI tab must always show AT LEAST 8 cards
arranged in a uniform 4-column grid.

Keep existing 6 metrics and ADD these new ones
computed directly from the DataFrame:

  Card 7 — Average Order Value:
    Metric: SUM of revenue / COUNT of orders
    Look for: total_sales / order_id columns
    Label: "AVG ORDER VALUE"
    Icon: 🛒
    Format: currency

  Card 8 — Top Colour by Revenue:
    Metric: colour_name with highest total_sales
    Look for: colour_name column
    Label: "TOP COLOUR"
    Icon: 🎨
    Format: text (colour name)

  Card 9 — Total Orders:
    Metric: COUNT of order_id
    Label: "TOTAL ORDERS"
    Icon: 📦
    Format: integer with K suffix

  Card 10 — Revenue Per Unit:
    Metric: SUM(total_sales) / SUM(order_qty)
    Label: "REV PER UNIT"
    Icon: 💰
    Format: currency

  Card 11 — Date Range:
    Metric: MIN(date) to MAX(date)
    Look for: date column
    Label: "DATE RANGE"
    Icon: 📅
    Format: "Jan 2022 — Dec 2024"

  Card 12 — Top Make by Units:
    Metric: make with highest SUM(order_qty)
    Look for: make column
    Label: "TOP MAKE"
    Icon: 🏭
    Format: text (make name)

  For any card where required column does
  not exist in the DataFrame:
    Skip that card gracefully
    Do not show empty cards
    Grid fills with available cards only

CHANGE 2 — UNIFORM 4-COLUMN GRID:
  Always arrange cards in 4-column rows
  Every card identical size and shape
  No wide half-screen cards
  Last row: if fewer than 4 remaining,
    use st.columns with equal width
    cards align left, rest stays empty
  DO NOT use different column widths
    for different rows

CHANGE 3 — CARD VISUAL REDESIGN:
  Each card must have:

  Container:
    background: linear-gradient(
      145deg,
      rgba(15, 23, 42, 0.9),
      rgba(30, 41, 59, 0.7)
    )
    border: 1px solid rgba(99,102,241,0.12)
    border-radius: 14px
    padding: 18px 20px
    min-height: 110px
    position: relative
    overflow: hidden

  Top accent bar (coloured per card):
    Each card type gets unique accent colour:
    Revenue:      #6366f1 (indigo)
    Units Sold:   #10b981 (green)
    YoY Growth:   #f59e0b (amber)
    Best Person:  #ec4899 (pink)
    Top Model:    #8b5cf6 (purple)
    Active Regions: #06b6d4 (cyan)
    Avg Order:    #14b8a6 (teal)
    Top Colour:   #f97316 (orange)
    Total Orders: #6366f1 (indigo lighter)
    Rev Per Unit: #10b981 (green lighter)
    Date Range:   #64748b (slate)
    Top Make:     #a855f7 (violet)

    Height: 2px at top of card
    Full width
    gradient from accent to transparent

  Value (number/text):
    font-size: 26px
    font-weight: 800
    color: #f1f5f9
    letter-spacing: -0.5px
    margin-bottom: 4px
    line-height: 1.1

  Label:
    font-size: 10px
    font-weight: 700
    color: #64748b
    text-transform: uppercase
    letter-spacing: 1.2px
    display: flex
    align-items: center
    gap: 5px

  Sub-label (context text):
    font-size: 11px
    color: #475569
    margin-top: 6px
    NEVER show raw column names
    ALWAYS show human-readable context:
      "vs 2023" for YoY
      "by revenue" for top performers
      "Jan 2022 — Dec 2024" for date range
      "based on {N:,} orders" for averages

  Trend indicator (if applicable):
    Small arrow + percentage in corner
    ▲ green for positive
    ▼ red for negative
    position: absolute top-right
    font-size: 11px
    font-weight: 700

  Hover effect:
    border-color: rgba(99,102,241,0.25)
    box-shadow: 0 4px 20px rgba(0,0,0,0.2)
    transform: translateY(-1px)
    transition: all 0.2s ease

CHANGE 4 — FILTER SECTION COMPACT:
  Current filter section has too much space.
  Make it compact:

  Combine Year and Month into one row
  Use 2 columns side by side
  No heading "Filter Charts by Period"
    Replace with inline label approach:
    Small label above each dropdown
  Reduce padding below filter area
  Add thin separator line after filters
  Total filter section height: max 80px

CHANGE 5 — SECTION HEADER REDESIGN:
  "Executive KPI Summary" heading:
    Add gradient text effect:
    background: linear-gradient(
      135deg, #e2e8f0, #94a3b8
    )
    -webkit-background-clip: text
    font-size: 22px
    font-weight: 800
    letter-spacing: -0.3px

  Subtitle text:
    Change "All metrics computed directly
    from your data — no AI involved." to:
    "📊 Live metrics · Zero AI · Pure data"
    Style: font-size 11px, color #475569

CHANGE 6 — CHARTS SECTION (below KPIs):
  If charts exist below KPI cards,
  ensure they also use 2-column layout
  not single full-width columns
  Charts should have same card container
  style as KPI cards (matching aesthetic)

════════════════════════════════════════════════
SECTION 3 — DATA PREVIEW TAB ENHANCEMENT
════════════════════════════════════════════════

FILE: ui/tab_preview.py

PROBLEMS OBSERVED IN SCREENSHOT:
  1. Data Quality section looks good but
     stat boxes (Rows, Columns, Null Rate,
     Duplicates, Outlier Cols) are
     inconsistently sized and spaced
  2. The 5 stat boxes dont fill the row
     evenly — there is unused space
  3. Outlier Cols box sits alone on second
     row — should be same row as others
  4. Gauge chart and score take up too much
     left space — right side stat boxes
     look squished and small
  5. Need more DQ metrics that clients love
  6. Green success banner is good but
     could be more polished

CHANGE 1 — REBALANCE DQ HEADER LAYOUT:
  Current: gauge takes 30% left,
           stat boxes take 70% right
  Change to: 3-column layout

  Column 1 (25%): Score + gauge + badge
  Column 2 (45%): Primary stat boxes
  Column 3 (30%): Secondary/new stat boxes

  Primary stats (Column 2) — all 5 in grid:
    Row 1: Total Rows | Columns | Null Rate
    Row 2: Duplicates | Outlier Cols
    Equal width within column
    No orphaned single box on new row

  Secondary new stats (Column 3):
    Completeness % (inverse of null rate)
    Numeric Columns count
    Text Columns count
    Date Columns count

CHANGE 2 — ADD MORE DQ METRICS:
  Compute and display these additional checks
  below the existing DQ header section:

  METRIC A — Column Completeness Table:
    For each column show:
    - Column name
    - Data type (icon: 🔢 numeric, 📝 text, 📅 date)
    - Completeness % (non-null / total)
    - Unique values count
    - Status badge:
        ✅ Complete (100%)
        🟡 Minor gaps (95-99%)
        🟠 Gaps (80-94%)
        🔴 Sparse (<80%)
    Show as compact styled table
    Label: "📋 Column Health Report"
    Show first 15 columns
    Collapsible expander
    Self-aligning — no empty columns

  METRIC B — Data Type Distribution:
    Small visual breakdown:
    "Numeric: X | Text: Y | Date: Z | Boolean: W"
    Shown as small coloured pills in a row
    Numeric: blue pill
    Text: green pill
    Date: amber pill
    Boolean: purple pill
    Label: "🔬 Schema Composition"
    Single compact row — no wasted space

  METRIC C — Value Range Summary:
    For each numeric column show:
    Min | Max | Mean | Std Dev
    Only for numeric columns
    Max 8 columns shown
    Compact table format
    Label: "📊 Numeric Column Profiles"
    Collapsible expander
    Colour-code mean cell by proximity
    to median (red = skewed, green = normal)

  METRIC D — Top Values Preview:
    For each categorical/text column:
    Top 3 most frequent values + count
    Max 5 columns shown
    Compact horizontal layout
    Label: "🏷️ Top Values by Column"
    Collapsible expander

  METRIC E — Duplicate Analysis:
    Already shown but enhance:
    If duplicates = 0: show celebration
      "🎉 Perfect — No duplicate rows"
    If duplicates > 0: show which columns
      have the most repeated values
      "Top repeated: column_name (N times)"
    Add: % duplicate rate
      "X.X% of rows are duplicates"

CHANGE 3 — STAT BOX REDESIGN:
  The 5 DQ stat boxes must all be uniform:

  Container:
    background: rgba(15, 23, 42, 0.8)
    border: 1px solid rgba(99,102,241,0.1)
    border-radius: 10px
    padding: 12px 16px
    text-align: center
    flex: 1 (equal width, fills row)

  Value:
    font-size: 22px
    font-weight: 800
    Colour by meaning:
      Rows: #818cf8 (indigo)
      Columns: #818cf8 (indigo)
      Null Rate: green if 0%, amber if <5%, red if >5%
      Duplicates: green if 0, red if >0
      Outlier Cols: green if 0, amber if >0

  Label:
    font-size: 9px
    font-weight: 700
    text-transform: uppercase
    letter-spacing: 1px
    color: #475569

  All 5 boxes in ONE row using st.columns(5)
  No box on second row

CHANGE 4 — DATA HEALTH SCORE SECTION:
  Score display enhancement:
    The percentage number: font-size 52px
    Weight: 900
    Colour based on score:
      90-100: #10b981 (green)
      70-89:  #f59e0b (amber)
      50-69:  #f97316 (orange)
      <50:    #ef4444 (red)

  "Data Health Score" label:
    font-size: 11px
    color: #64748b
    uppercase + letter-spacing

  Status badge ("Excellent" etc):
    background: rgba(16,185,129,0.12)
    border: 1px solid rgba(16,185,129,0.25)
    color: #6ee7b7
    border-radius: 20px
    padding: 4px 12px
    font-size: 11px
    font-weight: 700

CHANGE 5 — SUCCESS/WARNING BANNERS:
  Current: green banner "No null values..."
  Redesign:

  Success banner:
    background: rgba(16,185,129,0.06)
    border: 1px solid rgba(16,185,129,0.2)
    border-left: 3px solid #10b981
    border-radius: 0 8px 8px 0
    padding: 10px 16px
    color: #6ee7b7
    font-size: 13px
    font-weight: 500
    icon: ✅ on left

  Warning banner (if issues found):
    border-left: 3px solid #f59e0b
    color: #fcd34d
    icon: ⚠️ on left

  Error banner (if critical issues):
    border-left: 3px solid #ef4444
    color: #fca5a5
    icon: 🔴 on left

CHANGE 6 — DATA PREVIEW TABLE:
  The actual data table at bottom:
  Add these controls above the table:
    - "Showing first N rows" selector:
      [25] [50] [100] as segmented buttons
    - Column type filter:
      [All] [Numeric] [Text] [Date]
      as small pill buttons
    - Search column names input (small)
  Table styling:
    Alternate row shading:
      even rows: rgba(99,102,241,0.03)
      odd rows: transparent
    Header: font-weight 700, color #94a3b8

CHANGE 7 — SELF-ALIGNING LAYOUT:
  All sections must use st.columns()
  with explicit ratios — never rely on
  default spacing.
  Add CSS:
    .block-container {
      max-width: 100% !important;
      padding-left: 1rem !important;
      padding-right: 1rem !important;
    }
  All expanders use use_container_width=True
  All dataframes use use_container_width=True
  All charts use use_container_width=True

════════════════════════════════════════════════
SECTION 4 — AI QUERY TAB COLOUR FIXES
════════════════════════════════════════════════

FILE: ui/tab_query.py

PROBLEMS OBSERVED IN SCREENSHOT:
  1. Run button (▶) is solid dark purple/blue
     rectangle — too heavy
  2. Query/Chat pill selector has solid
     dark blue active state
  3. Table/Chart/Insights tab pills at bottom
     look similar weight to main content
  4. Semantic term badges look ok but could
     be more polished
  5. "Semantic Context Injected" expander
     header blends with background

CHANGE 1 — RUN BUTTON:
  Current: solid dark blue/purple rectangle
  Change to:
    background: linear-gradient(
      135deg,
      rgba(124, 58, 237, 0.4),
      rgba(99, 102, 241, 0.3)
    )
    border: 1px solid rgba(139, 92, 246, 0.5)
    color: #ddd6fe
    border-radius: 10px
    font-size: 16px
    box-shadow: 0 2px 12px rgba(124,58,237,0.25)
    hover: opacity 1.0, box-shadow larger
    Feels: glowing, active, premium

CHANGE 2 — QUERY/CHAT PILL SELECTOR:
  Query pill (active):
    background: linear-gradient(
      135deg, #7c3aed, #6366f1
    )
    color: white
    box-shadow: 0 2px 10px rgba(124,58,237,0.3)
    border-radius: 20px
    padding: 5px 20px

  Chat pill (inactive):
    background: rgba(30, 41, 59, 0.6)
    border: 1px solid rgba(148,163,184,0.15)
    color: #64748b
    border-radius: 20px

  When Chat is active: swap styles

CHANGE 3 — RESULT VIEW TABS (Table/Chart/Insights):
  Active tab:
    Use accent colour matching content type:
    Table:    indigo accent #818cf8
    Chart:    green accent #6ee7b7
    Insights: amber accent #fcd34d
    
    Active style:
    border-bottom: 2px solid {accent}
    color: {accent}
    font-weight: 700
    background: transparent (not pill)
    
  Inactive tabs:
    color: #475569
    no border
    hover: color #94a3b8

CHANGE 4 — SEMANTIC TERM BADGES:
  Current badges look ok but update colours:

  Measure badge:
    background: rgba(124, 58, 237, 0.12)
    border: 1px solid rgba(124, 58, 237, 0.25)
    color: #c4b5fd

  Dimension badge:
    background: rgba(59, 130, 246, 0.12)
    border: 1px solid rgba(59, 130, 246, 0.25)
    color: #93c5fd

  Attribute badge:
    background: rgba(16, 185, 129, 0.1)
    border: 1px solid rgba(16, 185, 129, 0.2)
    color: #6ee7b7

  Glossary badge:
    background: rgba(245, 158, 11, 0.1)
    border: 1px solid rgba(245, 158, 11, 0.2)
    color: #fde68a

  SQL expression text inside badge:
    color: #64748b
    font-size: 9px
    font-style: italic
    Not competing with term name

CHANGE 5 — SEMANTIC CONTEXT EXPANDER:
  "Semantic Context Injected" expander:
  Header:
    background: rgba(16,185,129,0.05)
    border-left: 2px solid #10b981
    border-radius: 0 6px 6px 0
    color: #6ee7b7
    font-size: 12px
    font-weight: 600
  Content area:
    background: rgba(15,23,42,0.6)
    Code blocks for SQL hints:
      background: rgba(0,0,0,0.3)
      border: 1px solid rgba(99,102,241,0.15)
      color: #a5f3fc
      font-family: monospace

CHANGE 6 — STATUS BADGES ROW:
  The badges row showing:
  "Semantic + AI | 2 rows | 2.59s"

  Semantic + AI badge:
    background: linear-gradient(
      135deg,
      rgba(236,72,153,0.15),
      rgba(99,102,241,0.15)
    )
    border: 1px solid rgba(236,72,153,0.25)
    color: #f9a8d4
    border-radius: 20px

  Rows badge:
    background: rgba(30,41,59,0.7)
    border: 1px solid rgba(99,102,241,0.1)
    color: #94a3b8

  Time badge:
    background: rgba(30,41,59,0.7)
    border: 1px solid rgba(99,102,241,0.1)
    color: #94a3b8

════════════════════════════════════════════════
SECTION 5 — SIDEBAR VISUAL UPDATE
════════════════════════════════════════════════

FILE: ui/sidebar.py

PROBLEMS OBSERVED IN SCREENSHOT:
  - RESET, CACHE, CLEAR buttons are solid
    dark blue rectangles dominating the space
  - Too much visual weight on utility buttons
  - Section headers (SEMANTIC LAYER, LLM USAGE
    STATUS, VIEWS) look flat
  - Upload area looks like any other section

CHANGE 1 — UPLOAD SECTION:
  "UPLOAD FILES HERE" area:
    background: rgba(245,158,11,0.06)
    border: 1px dashed rgba(245,158,11,0.25)
    border-radius: 10px
    padding: 10px 12px
    Section header:
      color: #fcd34d
      font-size: 10px
      font-weight: 800
      letter-spacing: 1.5px
    "+" button:
      background: rgba(245,158,11,0.15)
      border: 1px solid rgba(245,158,11,0.3)
      color: #fcd34d
      border-radius: 8px
      width: 28px height: 28px

CHANGE 2 — SEMANTIC LAYER SECTION:
  Header badge:
    background: rgba(124,58,237,0.1)
    border: 1px solid rgba(124,58,237,0.2)
    color: #c4b5fd
    font-size: 10px
    font-weight: 800
    letter-spacing: 1.2px
    border-radius: 4px
    padding: 2px 8px
  Status values (ACTIVE, LOADED):
    color: #6ee7b7
    font-weight: 700

CHANGE 3 — LLM USAGE SECTION CONTINUED:
  RESET button:
    background: rgba(148,163,184,0.08)
    border: 1px solid rgba(148,163,184,0.15)
    color: #94a3b8
    border-radius: 7px
    font-size: 11px
    font-weight: 600
    text-transform: uppercase
    letter-spacing: 0.8px
    height: 30px
    hover: border-color rgba(148,163,184,0.3)
           color: #cbd5e1
    NOT solid blue fill

  CACHE button:
    background: rgba(16,185,129,0.08)
    border: 1px solid rgba(16,185,129,0.2)
    color: #6ee7b7
    border-radius: 7px
    font-size: 11px
    font-weight: 600
    text-transform: uppercase
    letter-spacing: 0.8px
    height: 30px
    hover: rgba(16,185,129,0.15)
    NOT solid blue fill

CHANGE 4 — VIEWS SECTION:
  Header:
    color: #818cf8
    font-size: 10px
    letter-spacing: 1.2px
  "Active: 3" value:
    color: #a5b4fc
    font-weight: 700
  CLEAR button:
    background: rgba(239,68,68,0.07)
    border: 1px solid rgba(239,68,68,0.18)
    color: #fca5a5
    border-radius: 7px
    font-size: 11px
    font-weight: 600
    text-transform: uppercase
    letter-spacing: 0.8px
    height: 30px
    hover: rgba(239,68,68,0.14)
           border-color rgba(239,68,68,0.3)
    NOT solid blue fill

CHANGE 5 — CONVERSATION SECTION:
  Section header:
    color: #f9a8d4
    font-size: 10px
    letter-spacing: 1.2px
  Content values:
    color: #e2e8f0
    font-size: 12px
  Any buttons in this section:
    Use secondary style:
    background: rgba(249,168,212,0.08)
    border: 1px solid rgba(249,168,212,0.15)
    color: #f9a8d4

CHANGE 6 — SECTION DIVIDERS IN SIDEBAR:
  Between each section add thin separator:
    border: none
    border-top: 1px solid rgba(99,102,241,0.08)
    margin: 8px 0
  Creates visual breathing room
  without heavy lines

CHANGE 7 — SIDEBAR SECTION HEADER PATTERN:
  All section headers follow same pattern:
    Uppercase text
    Font-size: 10px
    Font-weight: 800
    Letter-spacing: 1.5px
    Colour per section (unique per section)
    Small left accent dot or icon
  Values/stats below header:
    Font-size: 12px
    Font-weight: 600
    Right-aligned

════════════════════════════════════════════════
SECTION 6 — GLOBAL WOW FACTOR ELEMENTS
════════════════════════════════════════════════

FILE: config/styles.py — additions

ADD these global effects to elevate the
overall look-and-feel:

EFFECT 1 — CARD MICRO-ANIMATION:
  All cards (.stat-card, KPI cards, DQ cards):
  Add transition on hover:
    transition: transform 0.18s ease,
                box-shadow 0.18s ease,
                border-color 0.18s ease
    hover: transform: translateY(-2px)
           box-shadow: 0 8px 24px rgba(0,0,0,0.2)
  Feels responsive and alive

EFFECT 2 — GRADIENT BORDERS ON FOCUS CARDS:
  For the most important KPI card on each tab
  (first card, highest value):
    border: 1px solid transparent
    background-clip: padding-box
    position: relative
    ::before pseudo-element:
      gradient border effect
      background: linear-gradient(
        135deg, #7c3aed, #6366f1, #10b981
      )
  Achievable via box-shadow instead:
    box-shadow: 0 0 0 1px rgba(99,102,241,0.4),
                0 4px 20px rgba(99,102,241,0.15)

EFFECT 3 — SUBTLE BACKGROUND TEXTURE:
  Main content area:
    background: radial-gradient(
      ellipse at 20% 50%,
      rgba(99,102,241,0.03) 0%,
      transparent 60%
    ),
    radial-gradient(
      ellipse at 80% 20%,
      rgba(16,185,129,0.02) 0%,
      transparent 50%
    )
  Subtle depth without distraction

EFFECT 4 — NUMBER COUNTER ANIMATION:
  KPI card values should appear to count up
  when the tab loads.
  Use CSS animation approach:
    @keyframes countUp {
      from { opacity: 0; transform: translateY(4px); }
      to   { opacity: 1; transform: translateY(0); }
    }
  Apply with staggered delay per card:
    card 1: animation-delay: 0.05s
    card 2: animation-delay: 0.10s
    card 3: animation-delay: 0.15s
    ... and so on
  Duration: 0.3s ease-out

EFFECT 5 — GLOWING ACCENT LINE ON ACTIVE TAB:
  The active tab in the tab bar:
    After the tab pill add a subtle
    glow effect below:
    box-shadow: 0 4px 15px rgba(124,58,237,0.35),
                0 2px 6px rgba(124,58,237,0.2)
  The selected tab should feel illuminated

EFFECT 6 — DATA HEALTH SCORE RING:
  The gauge/ring in Data Preview:
    Add outer glow when score is high:
    If score >= 90:
      drop-shadow(0 0 12px rgba(16,185,129,0.4))
    If score 70-89:
      drop-shadow(0 0 10px rgba(245,158,11,0.3))
    If score < 70:
      drop-shadow(0 0 10px rgba(239,68,68,0.3))
  Makes the gauge feel dynamic not static

EFFECT 7 — EXPANDER CHEVRON ANIMATION:
  All st.expander() elements:
    When opening: chevron rotates smoothly
    transition: transform 0.2s ease
  Expander header on hover:
    background: rgba(99,102,241,0.04)
    border-radius: 6px

════════════════════════════════════════════════
SECTION 7 — TAB BAR GLOBAL STYLING
════════════════════════════════════════════════

FILE: config/styles.py

The tab bar (Join/Combine, Data Preview,
KPI Summary, AI Query) needs consistent
premium styling across all screenshots.

CURRENT ISSUE:
  Active tab uses solid purple pill
  which is good but inactive tabs
  are too faded — no visual engagement

TAB BAR CONTAINER:
  background: rgba(15,23,42,0.6)
  border-bottom: 1px solid rgba(99,102,241,0.1)
  padding: 0 16px

INDIVIDUAL TAB — INACTIVE:
  color: #64748b
  font-size: 13px
  font-weight: 500
  padding: 10px 16px
  border-radius: 8px
  border: 1px solid transparent
  transition: all 0.15s ease
  hover:
    color: #94a3b8
    background: rgba(99,102,241,0.05)
    border-color: rgba(99,102,241,0.1)

INDIVIDUAL TAB — ACTIVE:
  background: linear-gradient(
    135deg,
    rgba(124,58,237,0.9),
    rgba(99,102,241,0.85)
  )
  color: white
  font-weight: 700
  border-radius: 20px
  padding: 6px 18px
  box-shadow: 0 4px 15px rgba(124,58,237,0.35)
  border: 1px solid rgba(255,255,255,0.1)

TAB ICONS:
  Each tab icon should be slightly larger
  when active: font-size 1.1em
  Inactive: font-size 1em, opacity 0.7

════════════════════════════════════════════════
SECTION 8 — IMPLEMENTATION NOTES
════════════════════════════════════════════════

IMPORTANT RULES:

RULE 1 — NO FUNCTIONALITY REMOVED:
  Every existing feature must still work.
  Only visual changes are in scope.
  KPI calculations unchanged.
  DQ checks unchanged.
  Query functionality unchanged.

RULE 2 — GRACEFUL COLUMN FALLBACK:
  New KPI cards added in Section 2 must
  check column existence before computing.
  If required column missing: skip card.
  If all 12 KPIs available: show all 12.
  If only 6 available: show 6 in clean grid.
  Never show an empty card placeholder.

RULE 3 — STREAMLIT STYLING APPROACH:
  All custom styles via st.markdown()
  with unsafe_allow_html=True.
  Use CSS classes defined in styles.py
  applied via apply_styles() call.
  For Streamlit native elements (buttons,
  tabs, expanders) use CSS selectors:
    button[kind="primary"]
    .stTabs [data-baseweb="tab"]
    .stExpander
    .stSelectbox
  Test that CSS actually applies to
  Streamlit's generated class names.

RULE 4 — SELF-ALIGNING MEANS:
  Every section uses explicit st.columns()
  All columns use use_container_width=True
  No section relies on default spacing
  Expanders always expand to full width
  Tables always fill available width
  Charts always fill available width
  Cards always equal height in a row

RULE 5 — DARK THEME CONSISTENCY:
  Background palette must stay dark.
  Do NOT introduce light backgrounds.
  All new elements use dark surface colours.
  The aesthetic is: dark space + light accents
  Not: dark on light or flat material.

RULE 6 — COLOUR MEANING IS CONSISTENT:
  Green (#10b981, #6ee7b7):
    Good, healthy, success, positive trend
  Amber (#f59e0b, #fcd34d):
    Warning, moderate, needs attention
  Red (#ef4444, #fca5a5):
    Error, critical, negative, blocked
  Indigo (#6366f1, #818cf8):
    Primary, interactive, AI/semantic
  Purple (#7c3aed, #c4b5fd):
    Premium, action, highlight
  Cyan (#06b6d4, #67e8f9):
    Info, data, metrics
  Pink (#ec4899, #f9a8d4):
    Person/people metrics
  These colours must be used consistently
  across ALL three tabs and sidebar.

RULE 7 — ANIMATION PERFORMANCE:
  All animations must use:
    transform (not position)
    opacity (not visibility)
    transition (not animation where possible)
  Keep durations under 300ms
  No animations that loop or pulse
    continuously — only on hover/load

RULE 8 — RESPONSIVE TO DATA:
  KPI cards must adapt their sub-label text
  based on actual data in the DataFrame.
  Do not hardcode "by revenue" if the
  DataFrame has no revenue column.
  Check column existence then set label.
  Date range sub-label reads actual dates.
  "Based on N orders" reads actual count.

════════════════════════════════════════════════
TESTING CHECKLIST
════════════════════════════════════════════════

KPI SUMMARY TAB:
  □ No solid dark blue buttons visible
  □ All 8+ KPI cards shown when data supports
  □ All cards same size in 4-column grid
  □ Bottom row left-aligns remaining cards
  □ No raw column names shown in sub-labels
  □ Each card has unique accent colour bar
  □ Filter section is compact single row
  □ Cards animate in staggered on load
  □ Hover effect lifts card slightly
  □ Charts use same card container style

DATA PREVIEW TAB:
  □ All 5 DQ stat boxes in ONE row
  □ No orphaned box on second row
  □ Score ring has glow effect by health
  □ Column Health Report expander works
  □ Schema Composition pills render
  □ Numeric Column Profiles expander works
  □ Top Values expander works
  □ Duplicate analysis enhanced
  □ Success/warning banners redesigned
  □ Preview table has row controls
  □ All sections self-align to full width

AI QUERY TAB:
  □ Run button has gradient glow style
  □ Query/Chat pills correct colours
  □ Table/Chart/Insights tabs correct
  □ Semantic badges updated colours
  □ Semantic Context expander styled
  □ Status badges row looks premium
  □ No solid dark blue elements visible

SIDEBAR:
  □ RESET button muted grey style
  □ CACHE button green tint style
  □ CLEAR button red tint style
  □ Section headers unique colours
  □ Upload section amber bordered
  □ Semantic section purple tinted
  □ Dividers between sections visible
  □ No solid dark blue buttons anywhere

GLOBAL:
  □ Tab bar active pill has glow
  □ Inactive tabs hover correctly
  □ Card hover animations smooth
  □ Background has subtle gradient texture
  □ Colour meanings consistent across tabs
  □ Dark theme maintained throughout

════════════════════════════════════════════════
FILES CHANGED SUMMARY
════════════════════════════════════════════════

MAJOR CHANGES:
  config/styles.py
    → Complete colour system update
    → All button styles replaced
    → Card styles added
    → Animation keyframes added
    → Tab bar styling
    → Sidebar section styles

  ui/tab_kpi.py
    → Add 6 new KPI cards
    → Uniform 4-column grid layout
    → Card visual redesign
    → Filter section compact
    → Section header redesign

  ui/tab_preview.py
    → DQ header layout rebalanced
    → Add 5 new DQ metric sections
    → Stat box redesign
    → Health score display enhanced
    → Banners redesigned
    → Preview table controls added

MINOR CHANGES:
  ui/tab_query.py
    → Run button style
    → Query/Chat pill colours
    → Result view tab colours
    → Semantic badge colours
    → Status badge row style

  ui/sidebar.py
    → All button colours
    → Section header styles
    → Divider lines

NO CHANGE:
  core/ (all files)
  semantic/ (all files)
  features/ (all files)
  Any Python logic files
  Only visual/CSS/layout changes

END OF PROMPT
════════════════════════════════════════════════


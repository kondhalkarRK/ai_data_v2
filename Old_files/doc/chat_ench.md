PROMPT: CHAT INTELLIGENCE + UI ENHANCEMENT
============================================

You are upgrading the Chat mode of ai_data_v2.
Four specific features need implementation.
No code — only precise instructions.

════════════════════════════════════════════════
FEATURE 1 — SURPRISE ME
════════════════════════════════════════════════

TRIGGER:
  Only activate when user types exactly or
  closely matches:
    "surprise me"
    "surprise me!"
    "what's interesting"
    "impress me"
    "show me something interesting"
  
  DO NOT trigger on any other message.
  This is a special deliberate command only.

WHAT IT DOES:
  Runs 3-5 automated analysis queries
  on the loaded DataFrame silently,
  then surfaces the single most
  interesting finding.

DETECTION LOGIC (in process_chat_message):
  Check BEFORE is_data_question()
  Add: is_surprise = any token in
    ["surprise me", "impress me",
     "what's interesting",
     "show me something interesting"]

ANALYSIS STEPS TO RUN:
  Step 1 — Find highest concentration:
    Which single value in any categorical
    column holds the highest % of revenue
    e.g. "Black colour = 34% of all revenue"

  Step 2 — Find best cross-segment:
    Combine two categorical columns
    find the combination with highest
    revenue per order vs company average
    e.g. "Red SUVs = 2.3x avg revenue per order"

  Step 3 — Find unexpected performer:
    Find a value that ranks low on volume
    but high on revenue per unit
    e.g. "Silver ranks 7th on units
          but 2nd on revenue per unit"

  Step 4 — Find trend anomaly:
    If date column exists:
    Find the month with biggest deviation
    from rolling average

  Step 5 — Generate 3 recommendations:
    Based on findings above, generate
    3 business decisions using LLM:
    
    Prompt to LLM:
    "Based on these data findings:
     {findings_list}
     Generate exactly 3 business decisions
     a sales director would make today.
     Each decision: one action sentence.
     Then estimate combined revenue
     opportunity as a single number.
     Format: decision | revenue_impact"

RESPONSE FORMAT IN CHAT:
  Show as special card:

  Header:
    "✨ Here's something interesting
     I found in your data..."

  Finding card:
    Metric highlight: the cross-segment
    finding with 2.3x type comparison
    Make it visually distinct

  Recommendations section:
    "Based on everything analysed,
     here are 3 decisions I recommend today:"
    1. {decision_1}
    2. {decision_2}
    3. {decision_3}

    "Estimated revenue opportunity: {total}"

  Footer note:
    "Analysis based on {N} data points
     across {M} dimensions"

  message_type = "surprise"
  Style: golden/amber accent
    border-left: 3px solid #f59e0b
    background: rgba(245,158,11,0.06)

════════════════════════════════════════════════
FEATURE 2 — DATA TRUST SCORE
════════════════════════════════════════════════

WHEN TO SHOW:
  Show on EVERY data query response
  in the chat bubble and ask mode result.
  NOT shown for conversational replies.
  NOT shown for OOB responses.

WHAT IT CALCULATES:
  Five components, each scored 0-20:

  Component 1 — Semantic Match (0-20):
    Count of glossary terms resolved
    from the question via semantic layer.
    0 matches = 0 points
    1 match   = 10 points
    2+ matches = 20 points
    Source: last_glossary_matches
            in session_state

  Component 2 — Glossary Match (0-20):
    Whether sql_expression was found
    in glossary for the primary metric.
    Expression found = 20 points
    Partial/fallback = 10 points
    Not found = 0 points
    Source: last_glossary_hints non-empty

  Component 3 — SQL Validation (0-20):
    Whether SQL passed guardrails cleanly.
    Passed first attempt = 20 points
    Passed after retry = 10 points
    Required manual fix = 5 points
    Source: evidence execution_path
    "semantic" = 20, "fallback" = 10

  Component 4 — Row Coverage (0-20):
    Result rows vs total DataFrame rows.
    >50% covered = 20 points
    10-50% = 15 points
    1-10% = 10 points
    <1% but >0 = 5 points
    Source: len(result_df) vs len(working_df)

  Component 5 — Join Quality (0-20):
    Were all columns in SQL found in df.
    All columns valid = 20 points
    Minor issues = 10 points
    Fallback used = 5 points
    Source: evidence resolution_source
    "semantic_llm" = 20, "cache" = 15,
    "fallback" = 5

  Total = sum of 5 components (max 100)

SCORE BANDS:
  90-100: "Excellent" — #10b981 green
  75-89:  "High"      — #6ee7b7 light green
  60-74:  "Good"      — #fcd34d amber
  40-59:  "Moderate"  — #f97316 orange
  <40:    "Low"       — #ef4444 red

DISPLAY FORMAT:
  Show as compact card in assistant bubble
  BELOW the response content
  ABOVE the data table

  Layout:
  ┌─────────────────────────────────────┐
  │ 🎯 Data Trust Score                 │
  │                                     │
  │  96%  Excellent                     │
  │  ████████████████████░  (progress)  │
  │                                     │
  │  Based on:                          │
  │  ✅ Semantic match    20/20         │
  │  ✅ Glossary match    20/20         │
  │  ✅ SQL validation    20/20         │
  │  ✅ Row coverage      18/20         │
  │  ✅ Join quality      18/20         │
  └─────────────────────────────────────┘

  When score < 75 add note:
  "⚠️ Lower confidence — review SQL
   for accuracy before decisions"

  When score = 100:
  "🏆 Perfect data confidence"

COLOUR CODING:
  Score number colour = band colour above
  Progress bar fill = band colour
  Background: rgba(15,23,42,0.6)
  Border: 1px solid band colour at 0.2 opacity

COMPUTE IN:
  process_chat_message() after result
  Store as: evidence["trust_score"] = score
  Store breakdown as:
  evidence["trust_breakdown"] = {
    semantic: int,
    glossary: int,
    sql_validation: int,
    row_coverage: int,
    join_quality: int
  }

════════════════════════════════════════════════
FEATURE 3 — AI CONCIERGE PATTERN
════════════════════════════════════════════════

CONCIERGE BEHAVIOUR RULES:

RULE 1 — GREETINGS:
  When user sends greeting
  (hi, hello, hey, good morning etc):
  
  Response must:
  a) Greet warmly by time of day:
     Before 12: "Good morning! 👋"
     12-17:     "Good afternoon! 👋"
     After 17:  "Good evening! 👋"
  
  b) Mention dataset context:
     "I can see you have {N} rows of
      automotive sales data loaded."
  
  c) Offer 2-3 starting points:
     "Here are a few things I can
      help you explore today:
      • Revenue performance by colour
        or make
      • Top performing salespeople
      • Sales trends over time
      What would you like to start with?"
  
  d) Keep it under 5 sentences total

RULE 2 — CONVERSATION STARTER:
  Track: is this the first message
  in the session? (turn_count == 1)
  
  If first message AND is greeting:
    Also mention:
    "I noticed {proactive_insight_title}
     — want me to dig into that?"
    Pull first proactive insight as hook

RULE 3 — OOB POLITE REDIRECT:
  Current: cold rejection
  New: warm redirect with 2 options
  
  When OOB detected:
  "I'm focused on helping you get
   insights from your sales data —
   that's where I can add real value! 😊
   
   Could I help you with something like:
   → '{suggested_question_1}'
   → '{suggested_question_2}'
   
   Or just ask me anything about your
   data and I'll do my best!"
  
  Pull suggested_question_1 and _2
  from proactive_engine.get_suggested_
  questions(df, limit=2)

RULE 4 — BLOCK DESTRUCTIVE QUESTIONS:
  When question contains:
    delete, drop, remove data, update,
    truncate, modify, alter, overwrite,
    wipe, destroy, erase, clear data
  
  Current: generic OOB message
  New: firm but professional block:
  
  "🔒 Data Protection — I can only
   read and analyse your data.
   I'm not able to modify, delete
   or update any records.
   
   Your data is safe. If you need
   to make changes, please use your
   source system directly."
  
  message_type = "blocked"
  Style: red left border
    border-left: 3px solid #ef4444
    background: rgba(239,68,68,0.06)
  
  Store separately from OOB:
  is_destructive = check for above terms
  Check BEFORE general OOB check

RULE 5 — MULTI-TURN QUESTIONS:
  LLM concierge can ask clarifying
  questions when query is ambiguous.
  
  Examples of ambiguous queries:
  "show me the best" → best what? by what metric?
  "how is performance" → which dimension?
  "compare them" → compare what? no prior context?
  
  When ambiguity detected:
  Store: pending_clarification = question
  
  Ask ONE clarifying question:
  "I want to make sure I give you
   the right answer! Are you asking
   about:
   A) Revenue performance
   B) Units sold
   C) Order count
   
   Just reply A, B or C"
  
  On follow-up A/B/C response:
  Detect as clarification reply
  Reconstruct original question with
  the chosen metric and run it
  
  Clarification triggers:
    "show me the best" (no metric)
    "compare them" (no prior context)
    "how is it doing" (no subject)
    "what's the performance" (no dim)
    "tell me about X" where X is
      a dimension not a metric

RULE 6 — FRIENDLY ERROR HANDLING:
  When data query returns error:
  
  Current: raw error string shown
  New: empathetic response:
  
  "Hmm, I had trouble with that one 🤔
   
   I tried: {plain_english_description}
   Issue: {simplified_error_reason}
   
   Want to try:
   → '{simpler_version_of_question}'
   
   Or I can show you what data is
   available to query."
  
  simplified_error_reason logic:
    If "column not found": 
      "I couldn't find that column
       in your data"
    If "syntax": 
      "The query structure was unexpected"
    If "no rows":
      "No data matched those filters"
    Default: "Unexpected technical issue"

════════════════════════════════════════════════
FEATURE 4 — CHAT UI COLOUR & READABILITY
════════════════════════════════════════════════

PROBLEM:
  Responses look flat, hard to distinguish
  between types, low contrast on dark bg,
  data tables buried in chat flow

COLOUR CODING BY MESSAGE TYPE:

  User bubble:
    background: rgba(99, 102, 241, 0.12)
    border: 1px solid rgba(99,102,241,0.25)
    text: #e2e8f0
    avatar bg: rgba(99,102,241,0.15)
    border accent: none

  Assistant — conversational reply:
    background: rgba(30, 41, 59, 0.5)
    border: 1px solid rgba(148,163,184,0.1)
    left accent: none
    text: #cbd5e1
    Feel: neutral, clean

  Assistant — data query result:
    background: rgba(15, 23, 42, 0.7)
    border: 1px solid rgba(99,102,241,0.15)
    border-left: 3px solid #6366f1
    text: #e2e8f0
    Feel: data-focused, structured

  Assistant — narration/insight:
    background: rgba(16, 185, 129, 0.05)
    border: 1px solid rgba(16,185,129,0.15)
    border-left: 3px solid #10b981
    text: #cbd5e1
    headline: #6ee7b7
    Feel: insight, analytical

  Assistant — what-if scenario:
    background: rgba(245, 158, 11, 0.05)
    border: 1px solid rgba(245,158,11,0.15)
    border-left: 3px solid #f59e0b
    text: #cbd5e1
    Feel: exploratory, forward-looking

  Assistant — surprise me:
    background: rgba(245, 158, 11, 0.06)
    border: 1px solid rgba(245,158,11,0.2)
    border-left: 3px solid #f59e0b
    header colour: #fcd34d
    Feel: special, premium, discovery

  Assistant — blocked/destructive:
    background: rgba(239, 68, 68, 0.06)
    border: 1px solid rgba(239,68,68,0.15)
    border-left: 3px solid #ef4444
    text: #fca5a5
    Feel: firm, protective

  Assistant — OOB redirect:
    background: rgba(245, 158, 11, 0.05)
    border: 1px solid rgba(245,158,11,0.12)
    border-left: 3px solid #f59e0b
    text: #fde68a
    Feel: warm, redirecting

  Trust score card:
    background: rgba(15, 23, 42, 0.6)
    border: 1px solid {band_colour}@0.2
    text: #94a3b8
    score number: {band_colour}
    Feel: analytical, trustworthy

READABILITY IMPROVEMENTS:

  Narration text:
    font-size: 13px (currently too small)
    line-height: 1.7 (increase from 1.5)
    color: #cbd5e1 (brighter than current)
    paragraph spacing: 8px between sections

  Key findings bullets:
    Show as styled list not plain markdown:
    Each bullet:
      background: rgba(99,102,241,0.05)
      border-left: 2px solid #6366f1
      padding: 6px 10px
      border-radius: 0 4px 4px 0
      margin: 3px 0
      font-size: 12px

  Data tables in chat:
    Add header above table:
    "📋 Query Results ({N} rows)"
    font-size: 11px, color: #64748b
    Table max-height: 280px
    Scrollable within bubble
    Alternate row shading:
      even: rgba(99,102,241,0.03)
    Column headers: font-weight 700
                    color: #94a3b8

  SQL expander in chat:
    Current: plain expander
    New: styled with label:
    "🔍 SQL used (click to inspect)"
    Code block:
      background: rgba(0,0,0,0.3)
      border: 1px solid rgba(99,102,241,0.1)
      color: #a5f3fc (cyan for readability)
      font-size: 11px

  Timestamps:
    Current: barely visible
    New: font-size: 10px
         color: #475569
         always shown, not hoverable only

  Message spacing:
    Between messages: 16px gap
    Within assistant card: 12px padding
    Avatar to card gap: 8px
    No tight cramping

  Semantic badges in chat:
    Current: small text hard to read
    New:
      font-size: 11px (up from 9px)
      padding: 3px 8px (more breathing room)
      border-radius: 6px
      Show max 3 not 5 (less clutter)

════════════════════════════════════════════════
LLM PROMPT TEMPLATE — CONCIERGE RESPONSES
════════════════════════════════════════════════

This is the prompt template to use when
calling call_llm() for conversational
(non-data) responses. Replace current
_conversational_reply() prompt with this:

─────────────────────────────────────────
SYSTEM CONTEXT (inject once per session):

You are an AI Data Concierge embedded in
Capgemini's AI Data Platform.

Your personality:
  Professional but warm
  Confident but not arrogant
  Helpful and solution-oriented
  Brief and precise — no waffle

Your purpose:
  Help users explore their automotive
  sales dataset using natural language.
  You understand business metrics like
  Revenue, Units Sold, Salesperson
  performance, Make/Colour/Car Type.

You can:
  Answer data questions about the dataset
  Explain results in plain business English
  Run what-if scenarios
  Surface interesting patterns
  Guide users to better questions

You cannot:
  Modify, delete or update any data
  Access external systems or the internet
  Answer questions outside this dataset
  Make predictions about future data

Current dataset context:
  {data_summary}

Semantic terms available:
  {glossary_bits}

Conversation history:
  {history}
─────────────────────────────────────────

GREETING PROMPT (turn_count == 1 or greeting):

Given it is {time_of_day}, greet the user
warmly. Mention the dataset size briefly.
Offer 3 specific things they can explore.
If there is a proactive insight available,
mention it as a hook.
Keep response under 5 sentences.
End with a clear invitation to ask.

─────────────────────────────────────────

OOB REDIRECT PROMPT:

User asked something outside data scope:
"{question}"

Respond warmly. Acknowledge what they
asked without dismissing them.
Redirect to 2 specific data questions
they COULD ask instead, pulled from:
{suggested_questions}
Do not say "I cannot" — say "I'm focused
on" instead.
Keep to 3-4 sentences maximum.

─────────────────────────────────────────

DESTRUCTIVE BLOCK PROMPT:

User asked: "{question}"
This involves modifying or deleting data.

Respond with:
1. Clear statement you cannot do this
2. Reassurance data is safe
3. Redirect to what you CAN do
4. Professional tone — not robotic
Keep to 2-3 sentences.

─────────────────────────────────────────

CLARIFICATION PROMPT:

User asked: "{question}"
This is ambiguous — missing:
{missing_context}

Ask ONE clarifying question.
Offer 2-3 specific options labelled A/B/C.
Keep it short — max 3 sentences total.
Sound curious and helpful not interrogative.

─────────────────────────────────────────

ERROR RECOVERY PROMPT:

A data query failed.
Original question: "{question}"
Error type: {error_type}
Simplified reason: {simplified_reason}

Respond empathetically.
Explain in plain English what went wrong.
Suggest one simpler version of the question.
Keep to 3 sentences maximum.

─────────────────────────────────────────

GENERAL CONVERSATIONAL PROMPT:

User: "{question}"
This is not a data question.

Respond naturally and helpfully.
If related to your capabilities, explain.
If completely off-topic, gently redirect.
Keep to 2-3 sentences.
Always end with an invitation to ask
about the data.

════════════════════════════════════════════════
FILE CHANGES SUMMARY
════════════════════════════════════════════════

NEW LOGIC TO ADD:
  ui/tab_query.py
    → detect_surprise_me() function
    → run_surprise_analysis() function
    → compute_trust_score() function
    → render_trust_score_card() function
    → detect_destructive() function
    → detect_ambiguous() function
    → handle_clarification_reply() function
    → updated process_chat_message() routing
    → updated render_assistant_bubble()
      with colour coding per message_type
    → updated _conversational_reply()
      with new LLM prompt templates
    → updated OOB handler (warm redirect)
    → new message_type values:
      "surprise", "blocked", "clarification",
      "clarification_reply", "error_friendly"

  config/styles.py
    → colour per message_type CSS classes
    → readability improvements
    → trust score card styles
    → surprise card styles
    → blocked card styles

  core/conversation_state.py
    → pending_clarification field in state
    → is_awaiting_clarification() function
    → resolve_clarification() function

════════════════════════════════════════════════
ROUTING ORDER IN process_chat_message()
════════════════════════════════════════════════

Process messages in this exact order:

1. is_destructive(q)
   → blocked response FIRST
   → never reaches LLM

2. detect_surprise_me(q)
   → surprise analysis
   → special flow

3. is_awaiting_clarification()
   AND q in ["a","b","c","1","2","3"]
   → resolve_clarification()
   → run original question with choice

4. detect_oob(q)
   → warm redirect response
   → pull 2 suggestions

5. is_greeting(q)
   → concierge greeting
   → time-aware response

6. detect_ambiguous(q)
   → ask clarifying question
   → store pending_clarification

7. is_data_question(q)
   → whatif check
   → run_query()

8. else
   → _conversational_reply()
   → general LLM chat

════════════════════════════════════════════════
END OF PROMPT
════════════════════════════════════════════════


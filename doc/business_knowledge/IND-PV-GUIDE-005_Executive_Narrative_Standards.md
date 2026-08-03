# IND-PV-GUIDE-005 — Executive Narrative & Insight Standards

**Document ID:** IND-PV-GUIDE-005  
**Version:** 1.2  
**Effective date:** 01-Jan-2025  
**Last review:** 25-Jun-2026  
**Owner:** Business Insights Office  
**Audience:** AI Copilot designers, Analysts, CXO briefing authors  
**Companion SOPs:** 001 (metrics), 002 (COVID), 003 (EV), 004 (regions)

---

## 1. Purpose

Raise narrative quality from “chart caption” to **decision-grade commentary** that executives trust. This guide is the behavioural contract for AI-generated narration when OKF knowledge is available.

## 2. Insight classes (use the highest that data supports)

| Class | Definition | Example |
|---|---|---|
| L1 Descriptive | What happened | “Maruti leads units in 2024.” |
| L2 Comparative | Vs peer / prior | “Tata units grew faster than Maruti YoY.” |
| L3 Contextual | Links to SOP market knowledge | “2020 dip is COVID lockdown, not brand failure (SOP-002).” |
| L4 Prescriptive | Recommended action | “Reallocate demo inventory to South EV hubs where EV share > national.” |

AI answers should aim for **L2 minimum**, **L3 when OKF retrieves a relevant SOP**, **L4 only when thresholds in SOP-004 are met**.

## 3. Structure of a best-in-class narrative

1. **Headline** — one line, metric + winner + period.  
2. **Story** — 2–4 sentences: magnitude, leader, context.  
3. **Findings** — max 3 bullets.  
4. **Recommendation** — one next drill or action.  
5. **Knowledge citation** — when SOP text influenced the story: `(IND-PV-SOP-00X)`.

### 3.1 Currency & volume formatting (India)

- Revenue: ₹ with Lakh / Crore scaling for large numbers.  
- Volume: integers with thousand separators + “units”.  
- Never show £ or $ for this India PV domain.

### 3.2 Forbidden narrative patterns

- “Breakdown of revenue” without naming the leader.  
- Decimal quarters (`2024-Q1.333`).  
- Units Sold = 0 while orders exist (metric mapping bug).  
- Blaming an OEM for 2020 industry trough.  
- Calling Hybrid an EV without saying electrified.

## 4. Domain storylines that resonate with leaders

Use these arcs when data supports them:

1. **COVID scar & recovery** — 2019 baseline → 2020 trough → 2023+ strength (SOP-002).  
2. **EV adoption curve** — share rising into mid-teens; ICE still majority (SOP-003).  
3. **OEM oligopoly of volume** — Maruti, Tata, Mahindra concentration (SOP-001 / 004).  
4. **SUVisation** — SUV share of body style mix.  
5. **Festive H2 uplift** — Sep–Dec seasonality.

## 5. Hybrid answer pattern (data + knowledge)

When both SQL results and OKF snippets exist:

```
[Data finding]
[SOP context sentence]
[Recommended next question]
Source: IND-PV-SOP-00X
```

Example:

> Tata leads EV units in the latest period. Per IND-PV-SOP-003, EV share should be reported on units (not orders), and Petrol remains the volume backbone nationally. Next: compare EV share by South vs West metros.

## 6. Role-based emphasis

| Persona | Emphasise | De-emphasise |
|---|---|---|
| CXO | YoY, recovery, EV share, concentration risk | Colour SKUs, individual order IDs |
| Regional Head | Zone/city units, salesperson productivity | National OEM philosophy |
| FP&A | Revenue, ASP, AOV, certified formulas | Subjective brand stories |
| Product | Powertrain, model, car_type mix | Corp ID lists |

## 7. Quality checklist before publish / show in chat

- [ ] Metric matches SOP-001  
- [ ] Time label is Q1-YYYY / YYYY-MM compliant  
- [ ] COVID disclaimer if 2020-centric  
- [ ] EV formula stated if share discussed  
- [ ] No raw surrogate keys  
- [ ] Citation present if OKF used  
- [ ] One clear next step

## 8. Success definition

A “best class” answer is one an executive can paste into a leadership email **without rewriting definitions**, and an analyst can reproduce exactly from certified SQL.

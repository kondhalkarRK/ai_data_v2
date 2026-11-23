# Indian automotive market dataset (2M+ rows)

A deterministic, realistic dataset for the existing `automotive` schema, covering
**2015-01-01 to today** for the Indian passenger-vehicle market. It is modelled data built from
public market structure (brand shares, model launches, festivals, macro shocks), not OEM sales
figures, and is designed so that the Knowledge Graph, Entity Catalog, AI Chat and dashboards
all return plausible answers.

No DDL changes are needed: the generator writes exactly the columns of migrations
`0001`–`0003` (`fact_sales.total_sales` is a generated column and is never loaded).

## Files

| Path | Role |
|---|---|
| `apps/api/app/analytics/india_auto_market.py` | Market knowledge: brands, 143 models with launch windows and variants, cities, colours, festivals, macro events, price indices |
| `apps/api/app/analytics/india_auto_generator.py` | The generator (pure standard library, seeded) |
| `scripts/generate_india_auto_dataset.py` | CLI: writes the CSVs |
| `scripts/load_india_auto_dataset.py` | CLI: bulk-loads the CSVs with PostgreSQL `COPY` |
| `scripts/validate_india_auto_dataset.py` | CLI: 42 data-quality and realism checks |
| `apps/api/tests/test_india_auto_generator.py` | Small-scale generator test (catalog, integrity, launch windows, split) |

## Run it

From `askdb/` with the API virtual environment (the automotive migrations must be at head:
`python scripts/migrate.py automotive upgrade head`):

```powershell
.\apps\api\.venv\Scripts\python.exe scripts\generate_india_auto_dataset.py          # ~70-110 s, ~0.4 GB of CSV in data\india_auto
.\apps\api\.venv\Scripts\python.exe scripts\load_india_auto_dataset.py --replace    # ~70 s
.\apps\api\.venv\Scripts\python.exe scripts\validate_india_auto_dataset.py          # exits 1 if any check fails
```

Then restart the API (so the updated semantic pack loads) and use
**Semantic Atlas > Entity Catalog > Refresh catalog** to re-baseline the catalog.

Useful flags:

* `--rows 2100000` (default), `--seed 20260930` (default): the same seed and end date always
  produce byte-identical CSVs.
* `--end-date 2026-09-30`: default is today.
* `--split-date 2026-06-30`: rows introduced after this date (new cities, dealers,
  salespeople, carlines, targets, forecasts and sales) go to `data\india_auto\increment\`.
  Load the base with `--stage base --replace`, refresh the Entity Catalog, then load
  `--stage increment` and refresh again: new values show up as **NEW**.
* The loader reads the migration database URL from settings; `--database-url` overrides it.

The loader runs in one transaction: `TRUNCATE ... RESTART IDENTITY CASCADE`, drop the
`fact_sales` / `fact_forecast_monthly` indexes and foreign keys, `COPY` each CSV, re-add the
foreign keys (validated in one set-based pass) and indexes, `ANALYZE`, refresh
`mv_sales_monthly`, and verify that every sale's region equals its dealer's region.

`manifest.json` (counts, seed, yearly shares) and `reference_model_calendar.csv` (each
carline's on-sale dates and anchor price) are written next to the CSVs for traceability; they
are not loaded.

## Output (default run, end date 2026-09-30)

| Table | Rows |
|---|---|
| `fact_sales` | 2,098,110 |
| `fact_forecast_monthly` | 427,341 (includes 6 future months) |
| `dim_targets` | ~1,900 (brand x month) |
| `dim_carline` | 251 (143 models x powertrains) |
| `dim_color` | 24 |
| `dim_region` | 69 cities |
| `dim_dealer` | 433 |
| `dim_salesman` | 3,766 (2,050 inactive) |

One `fact_sales` row is one order. About 98% of orders are for one unit, so the table
represents roughly 5% of national volume (a national sample, not the full market).

## Market-share logic

Each model has yearly **volume keyframes** (units per month, taken from its real market
position) interpolated month by month. The sum over all models is calibrated each full year to
the national market size (`MARKET_UNITS_MILLION`: 2.77M in 2015, 2.43M in 2020, 4.65M in 2026),
so brand shares come from the model mix rather than a fixed percentage:

* Maruti Suzuki leads every year (about 50% in 2015 falling to about 39% in 2026; the Nexa
  channel launches July 2015).
* Hyundai is second overall (16.4%).
* Tata rises from 4.9% (2015–19) to 12.7% (2022+), driven by Nexon, Punch and EVs.
* Mahindra's volume is 98% SUV.
* MG enters in June 2019 and Kia in August 2019. Citroen and BYD stay niche (BYD about 0.05%).
* Models exit when they did in reality, and Honda, Nissan and Renault shrink.

## Model lifecycle logic

* Every model has one or more **on-sale windows** (`"YYYY-MM"` to `"YYYY-MM"`). Models with a
  gap have several windows (Safari, Thar, Carnival, Superb, Kodiaq, Grand Cherokee). No sales
  can happen outside a window.
* The launch spike, growth, peak, stable and decline phases come from the volume keyframes plus
  a lifecycle multiplier. Months 0–5 after launch are ×1.30, 1.25, 1.10, then 0.92 (the
  post-launch dip). The last three months before discontinuation run out at ×0.80, 0.65, 0.45,
  with an extra 4% run-out discount.
* Powertrain variants have their own windows and shares. For example, diesel small cars stop
  at BS6 (April 2020), and CNG / hybrid / EV versions arrive later.
* Launches assumed for 2025–26 (e Vitara 2026-01, Sierra 2025-11, etc.) are approximations.

## Seasonality logic

Daily demand weight = weekday factor × national calendar × regional festivals × macro events.

* **National:** Navratri ×1.35 and Dussehra ×2.6; the 10 days before Diwali ×1.45 and
  Dhanteras ×3.2, with a lull right after Diwali. Pitru Paksha (16 days before Navratri) is
  ×0.62. The last 3 days of every month are ×1.12. The FY-end push (20–31 March) is ×1.3. The
  December year-end clearance (second half) is ×1.08, the first week of January ×1.1, and
  Akshaya Tritiya ×1.7. June, July and early August are slow (monsoon).
* **Regional:** each festival applies only to its states:
  * Ganesh Chaturthi (MH, GA, GJ, KA, TS);
  * Onam (KL);
  * Gudi Padwa / Ugadi (MH, GA, KA, AP, TS);
  * Durga Puja (WB, OD, AS, JH, BR);
  * Pongal / Makar Sankranti (TN, AP, KA, GJ);
  * Baisakhi (PB, HR, CH);
  * and others in `REGIONAL_FESTIVALS`.
* **Festival dates** follow the lunar calendar for each year from 2015 to 2026 and may be off
  by a day.
* **Macro events:**
  * demonetisation (Nov–Dec 2016);
  * GST roll-out (2017);
  * NBFC slowdown (2019);
  * COVID: the national lockdown from 2020-03-25 to 2020-05-03 is exactly zero sales, followed
    by a phased unlock and pent-up demand;
  * the second wave (Apr–Jun 2021);
  * the semiconductor shortage (Aug 2021–Mar 2022);
  * the 2024 election and inventory glut;
  * GST 2.0: buyers wait from mid-August 2025, then a surge after the rate cut on 22 Sep 2025.

Validated: median Oct/Nov festive peak index 1.38, April 2020 = 0 units, median March /
February = 1.27.

## Pricing logic

`price_per_unit` = anchor ex-showroom price (2024 level, in lakh) ×
`PRICE_INDEX[year]` (0.74 in 2015 to 1.03 in 2026) × EV price factor × regulation steps ×
model price steps (facelifts / generations) × GST factor × trim × (1 − discount) ×
(1 ± 1% noise), rounded to ₹100.

* BS6 (April 2020) adds cost to diesels, and BS6 phase 2 (April 2023) adds cost to every
  internal combustion engine.
* GST 2.0 (from 22 Sep 2025): small cars ×0.915 and other internal combustion cars ×0.955.
  EVs are unchanged (already at 5%).
* The trim mix (base / mid / upper / top at ×0.87 / 1.00 / 1.12 / 1.25) moves toward top
  trims over time.
* Discounts:
  * an introductory price (×0.97) for the first 3 months;
  * festive offers of 1.5–3.5%;
  * a run-out discount of 4%;
  * a fleet discount of 4%;
  * random dealer discounts of up to 1.2%.

Example: Swift petrol averages ₹5.2 lakh in 2016 and ₹7.5 lakh in 2024. Nexon EV sells at a
large premium over Nexon petrol.

## EV growth logic

EV variants only exist from their real launch dates (e2o / Tigor EV fleet, Nexon EV 2020,
Tiago EV / ZS EV / XUV400, Punch EV, Windsor, BE 6, Creta Electric, e Vitara, BYD models...).
Their volume keyframes follow the adoption curve:

| Year | 2015–18 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| EV share | 0% | 0.04% | 0.33% | 0.62% | 1.2% | 2.1% | 2.7% | 4.3% | 4.8% |

Tata, MG and Mahindra are the EV leaders. EV demand is boosted in states with EV policies:
Karnataka and Delhi ×1.5, Kerala ×1.4, and Maharashtra and Telangana ×1.3. The EV price premium
shrinks from ×1.09 (2022) to ×0.93 (2026) relative to the model's base anchor.

## Geography and dealer network

* **Cities:** 69 cities in 5 zones (North, West, South, East, Central), each with a state and a
  market-size weight (Delhi NCR, Mumbai MMR, Bengaluru, Pune, Chennai and Hyderabad are the
  largest).
  * `dim_region.region_name` is the zone, and `state_code` is the 2-letter state.
  * Four cities enter later: Belagavi 2022-09, Warangal 2023-06, Tirupati 2026-02 and Bareilly
    2026-04. Their dealers and sales start at that point.
* **Dealers:** 433 brand-exclusive outlets. Maruti is split into Arena and Nexa outlets.
  * Each brand's dealer count (`DEALER_TARGETS`) is spread over its reachable cities in
    proportion to city weight × brand zone preference. Maruti reaches every tier, while Jeep,
    Citroen and BYD reach metros only.
  * Outlets open with the brand's entry and some close (Honda, Nissan and Renault closures).
  * Grade follows tier: A in metros (84%), B in tier-2 cities (79%) and C in smaller markets
    (73%). Grade drives size and staffing.
* **Demand allocation:** demand goes to open outlets weighted by city weight, brand zone
  preference, the segment's tier preference (entry cars skew to tier-3, premium cars to
  metros), the EV state preference, and the state's festival factor for that month.
* **Salesforce:** 3,766 people. Each outlet keeps a headcount by grade (A 4–6, B 3–4, C 2–3
  concurrent staff), and tenures average about 9 years. Seats are refilled as people leave, so
  2,050 are inactive today. Every salesperson belongs to one dealer, and new joiners sell less
  in their first 90 days. Names are drawn from zone-appropriate name lists.

## Colours

There are 24 colours grouped into families (white, off-white, silver, black, grey, red, blue,
cyan, green, orange, gold, beige, pink, purple, bronze). The code gives each colour's family and
dual-tone flag (`rcg_combination`), and some colours carry a design registration number
(`patent_number`). Shares drift from 2015 to 2026: white dominates
throughout, silver declines and grey rises. Profiles differ by segment (premium cars are darker,
entry cars carry more silver and red), and fleet orders are mostly white and silver.
Validated order: white > silver > black > rest.

## Orders

About 98.3% of orders are qty = 1. Private orders of 2–3 units are rare. Fleet orders (qty 2–25)
come mainly from taxi and fleet models (Indica, Etios, Xcent / Aura, Eeco, Bolero, Innova,
Tigor EV, BYD e6). They are 1.8× more likely in March and get a 4% fleet discount.

## Forecast logic (`fact_forecast_monthly`)

Forecasts are derived from the generated history, month by month, per carline × region, the
way a planning team would build them:

* **Seasonal naive:** the last 3 months' level × the seasonal profile learned from prior years
  (2020–21 excluded as abnormal) × trend × 1.03 (sales optimism) × lognormal noise.
* **Launches:** the first 3 months use the launch plan (expected volume) instead of history.
* **Horizon:** history months plus 6 future months (`--forecast-horizon`).
* Revenue = forecast units × the carline's current average price.

Validated: median monthly error 7.4%.

## Target logic (`dim_targets`)

Targets are set per brand and month, planned once per financial year (April–March):

1. Take the last-12-month run-rate at planning time (January before the FY). Young brands are
   annualised, and models retired before the FY are removed.
2. Apply the ambition: clip(0.5 × brand growth + 0.5 × market growth + 3%, −8%, +35%).
3. Phase the annual target by the seasonal profile.
4. Add planned launches at 1.1× their expected volume. Brands without 12 months of history use
   expected volume × 1.04.
5. FY2020 is re-planned at ×0.82 from July 2020 (COVID).
6. Every month from brand entry gets a target (at least one unit).

Revenue targets = units × the run-rate average selling price × 1.04. Validated: median
achievement 88% excluding 2020–21.

## Data-quality rules (validator)

The validator runs **integrity** checks that must hold at any scale:

* volume and table counts;
* no null business keys and no orphans;
* every dealer has sales;
* valid engine type, car type, capacity (0.6–3.6 L, NULL for EVs) and make;
* every brand/model/powertrain combination exists in the catalog;
* no sales before launch, after discontinuation or while off market;
* valid city/state/zone, and sale region = dealer region;
* brand-exclusive dealers, one dealer per salesperson;
* no negative or inconsistent revenue, sales dates in range, valid targets and forecasts.

It also runs **realism** checks: grade by tier, market leaders, niche BYD, Tata growth,
SUV-led Mahindra, EV curve and leaders, colour ranking, festive peak, COVID dip, FY-end push,
order sizes, price inflation, EV premium, target coverage and achievement, and forecast
accuracy.

The default run passes 42/42. With very small samples (`--rows` below about 100k), "every
dealer has sales" can fail for a remote outlet; that is a sampling effect, not a data error.

## Assumptions and limits

* Volumes, prices and shares are modelled to be realistic, not copied from OEM data.
* Festival dates are approximate (±1 day), and 2025–26 launches and prices are assumptions.
* The dataset is a ~5% national sample, so absolute unit counts are smaller than SIAM figures
  while the shares and trends match.
* The semantic pack (`semantic/packs/automotive`) was updated with the new models, brands
  (Jeep, Citroen, BYD), granular car-type families ("SUV" means all four SUV types), city
  families (NCR, MMR) and zone names, so AI Chat resolves the new vocabulary.

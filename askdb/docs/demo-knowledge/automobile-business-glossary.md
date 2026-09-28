# Automobile Business Glossary

**Owner:** Sales Operations and Motor Insurance Analytics
**Scope:** India passenger-vehicle sales, the authorised dealer network, and motor insurance written on vehicles we sell
**Version:** 2026.3
**Review cycle:** Quarterly, approved by the Data Governance Council

This glossary is the single agreed definition of the business terms used in sales reviews, dealer scorecards, regional performance packs and insurance loss reporting. When two teams use different words for the same thing, the glossary names one **canonical term** and lists the others as **also known as**. Reports, dashboards and Ask DB answers should always use the canonical term.

---

## Vehicle

**Canonical term:** Vehicle
**Also known as:** Car, Automobile, Car Line, Model, Passenger Vehicle, PV
**Category:** Business entity

A Vehicle is a specific passenger car line that we manufacture or distribute, identified by its make, model, body type, engine capacity and engine type (petrol, diesel, CNG, hybrid or electric). Each Vehicle belongs to exactly one body type: SUV, Sedan, Hatchback or MPV.

**Key relationships**

- A Customer owns one or more Vehicles.
- A Vehicle is sold by a Dealer through a Sale.
- A Vehicle is available in one or more Colour Variants.
- A Policy covers exactly one Vehicle.
- Sales targets are set per make of Vehicle per month.

**Business rules**

- A Vehicle is counted once per unit sold, never per order line.
- Demo, fleet-test and pre-registered vehicles are excluded from retail Sales unless a report explicitly states "including fleet".
- "Model" in everyday speech usually means the car line (for example "Nexon" or "City"), not the model year.

**Example:** "Which Vehicle sold the most units in the West region last quarter?"

---

## SUV

**Canonical term:** SUV
**Also known as:** Sport Utility Vehicle, Crossover, Compact SUV, Utility Vehicle, UV
**Category:** Vehicle segment (a kind of Vehicle)

An SUV is a Vehicle with raised ground clearance and a body designed for both city and rough-road use. We split SUVs into three sub-segments by length and price: Compact SUV (under 4 metres), Mid-size SUV and Premium SUV.

**Key relationships**

- An SUV is a type of Vehicle.
- SUVs are sold by Dealers in every Region.
- SUV Policies usually carry a higher premium than Sedan Policies because of higher repair costs.

**Business rules**

- SUV share is calculated as SUV units sold divided by total units sold in the same period and region.
- A crossover built on a hatchback platform is still classified as an SUV if its official body type is SUV.

**Example:** "Show SUV share of units sold by Region for 2025."

---

## Sedan

**Canonical term:** Sedan
**Also known as:** Saloon, Three-box car, Notchback
**Category:** Vehicle segment (a kind of Vehicle)

A Sedan is a Vehicle with a separate boot, typically four doors and five seats. Sedans are bought mostly by families and corporate fleets and are sold in Entry, Mid and Executive price bands.

**Key relationships**

- A Sedan is a type of Vehicle.
- Sedans are sold by Dealers and frequently financed through partner banks.
- Fleet Sedans are often covered by a single commercial Policy per fleet customer.

**Business rules**

- Sedan share is calculated the same way as SUV share.
- Executive Sedans are reported separately in the premium segment pack.

**Example:** "Compare Sedan revenue versus SUV revenue by month."

---

## Dealer

**Canonical term:** Dealer
**Also known as:** Dealership, Outlet, Showroom, Retailer, Channel Partner, Authorised Dealer
**Category:** Business entity

A Dealer is an authorised retail outlet that sells our Vehicles to Customers, handles delivery, and usually offers finance and insurance at the point of sale. Each Dealer has a unique dealer code, belongs to exactly one Region, is located in one city, and is assigned a Dealer Grade of A, B or C.

**Key relationships**

- A Dealer is located in a Region.
- A Dealer sells Vehicles to Customers through Sales.
- A Dealer employs Salespeople.
- A Dealer can issue a Policy on a Vehicle it sells, acting as an insurance point of sale.

**Dealer Grade**

| Grade | Meaning |
|-------|---------|
| A | Flagship outlet, full service workshop, meets 100% or more of the monthly target for 3 consecutive months |
| B | Standard outlet, meets 80–99% of target |
| C | Developing or rural outlet, below 80% of target or opened in the last 12 months |

**Business rules**

- Only active Dealers are included in the dealer scorecard.
- A Sale belongs to the Dealer that raised the invoice, even if the Vehicle was delivered from another outlet.

**Example:** "Top 10 Dealers by revenue in the North region this quarter."

---

## Customer

**Canonical term:** Customer
**Also known as:** Buyer, Purchaser, Client, Vehicle Owner, Policyholder (in insurance context)
**Category:** Business entity

A Customer is an individual or organisation that buys a Vehicle from a Dealer, owns a Vehicle, or holds a Policy with us. A single Customer can own several Vehicles and hold several Policies.

**Key relationships**

- A Customer owns a Vehicle.
- A Customer buys a Vehicle from a Dealer through a Sale.
- A Customer holds a Policy that covers a Vehicle.
- A Customer raises a Claim against a Policy.

**Customer types**

- **Retail Customer** — an individual buying for personal use.
- **Fleet Customer** — a company buying five or more Vehicles in a year.
- **First-time Buyer** — a Customer with no previous Vehicle registered with us.
- **Repeat Buyer** — a Customer who has bought at least one earlier Vehicle from any of our Dealers.

**Example:** "How many first-time buyers bought an SUV in 2025?"

---

## Region

**Canonical term:** Region
**Also known as:** Territory, Zone, Geography, Sales Region, Area
**Category:** Business entity

A Region is a sales territory used for planning, targets and reporting. We operate four Regions — North, South, East and West — each made up of states and cities. Every Dealer belongs to exactly one Region.

**Key relationships**

- A Dealer is located in a Region.
- A Sale is recorded against the Region of the selling Dealer.
- Regional managers own the Sales targets for their Region.

**Business rules**

- Regional results roll up from Dealer results; a Region's revenue is the sum of the revenue of its Dealers.
- When a Dealer is moved to a different Region, history stays with the original Region.

**Example:** "Revenue by Region and month compared with target."

---

## Revenue

**Canonical term:** Revenue
**Also known as:** Sales Value, Turnover, Total Sales, Gross Sales Value
**Category:** KPI

Revenue is the total invoiced value of Vehicles sold, before discounts funded by the manufacturer and excluding taxes. It is calculated as the sum of the total sale value across all Sales in the period.

**Formula:** Revenue = Sum of total sale value of all Sales in the period

**Key relationships**

- Revenue is measured from Sales.
- Revenue can be broken down by Dealer, Region, Vehicle, Salesperson, Colour and Date.
- Revenue is compared with Target Revenue in regional reviews.

**Business rules**

- Cancelled orders are excluded.
- Revenue is recognised on the sales date (invoice date), not the delivery date.
- In everyday speech "sales" often means Revenue; when a report says "sales" without a unit, assume Revenue in rupees.

**Example:** "What was Revenue last year and how does it compare with the year before?"

---

## Sales

**Canonical term:** Sale (event), Units Sold (KPI)
**Also known as:** Sales Transaction, Order, Retail, Booking (after invoicing), Deal
**Category:** Business event

A Sale is a single invoiced order in which a Customer buys one or more Vehicles from a Dealer. Each Sale records the Vehicle, colour, Salesperson, Dealer, Region, sales date, quantity, price per unit and total sale value.

**Key relationships**

- A Sale is sold by a Dealer.
- A Sale is for a Vehicle.
- A Sale is made to a Customer.
- A Sale is handled by a Salesperson.
- A Sale is recorded in a Region.
- Revenue, Units Sold, Orders and Average Selling Price are all measured from Sales.

**Related KPIs**

- **Units Sold** — the total quantity of Vehicles across all Sales.
- **Orders** — the number of distinct Sales.
- **Average Selling Price** — Revenue divided by Units Sold.

**Business rules**

- A booking becomes a Sale only when it is invoiced.
- "Sales" on its own is ambiguous: say "Units Sold" for volume and "Revenue" for value.

**Example:** "Show total sales per year." — interpreted as Revenue by year unless units are requested.

---

## Policy

**Canonical term:** Policy
**Also known as:** Motor Policy, Insurance Policy, Cover, Motor Insurance, Contract
**Category:** Business entity

A Policy is a motor insurance contract that covers one Vehicle for a fixed term, usually one year. It records the policy number, Customer (policyholder), Vehicle, product (Comprehensive, Third-party or Own-damage only), start and end dates, sum insured and premium.

**Key relationships**

- A Policy covers a Vehicle.
- A Policy is held by a Customer.
- A Policy can be sold by a Dealer at the time of the Vehicle Sale.
- A Claim is linked to a Policy.
- Premium is earned from a Policy over its term.

**Business rules**

- A Policy is "in force" between its start and end date unless cancelled.
- Renewal Rate = Policies renewed divided by Policies due for renewal in the period.
- Earned Premium is spread evenly over the months the Policy is in force.

**Example:** "How many Policies sold at the Dealer are renewed with us after year one?"

---

## Claim

**Canonical term:** Claim
**Also known as:** Insurance Claim, Motor Claim, Loss, Accident Claim
**Category:** Business event

A Claim is a request by a policyholder for payment under a Policy after an insured event such as an accident, theft, fire or flood damage to the covered Vehicle. Each Claim records the claim number, Policy, reported date, loss date, cause, status and incurred amount.

**Key relationships**

- A Claim is linked to a Policy.
- A Claim involves the Vehicle covered by that Policy.
- A Claim is raised by a Customer.
- Loss Ratio, Claim Frequency and Average Claim Severity are measured from Claims.

**Claim statuses:** Reported → Under Survey → Approved or Rejected → Settled → Closed

**Related KPIs**

- **Loss Ratio** — incurred claim amount divided by earned premium.
- **Claim Frequency** — number of Claims divided by exposure (vehicle-years insured).
- **Average Claim Severity** — incurred claim amount divided by number of Claims.
- **Approval Rate** — approved Claims divided by decided Claims.

**Example:** "Loss ratio by Vehicle segment for Policies written in 2025."

---

## Supporting terms

| Term | Also known as | Meaning |
|------|---------------|---------|
| Salesperson | Sales Executive, Sales Consultant, Seller | A Dealer employee who handles a Sale |
| Colour Variant | Paint, Colour, Shade | The exterior paint option chosen for a Vehicle |
| Sales Target | Target, Quota, Plan | Planned units and revenue per make per month |
| Premium | Written Premium, Policy Price | The amount a Customer pays for a Policy |
| Earned Premium | — | The part of the premium that relates to the elapsed cover period |
| Exposure | Vehicle-years | Total time Vehicles were insured, used for Claim Frequency |

---

## Relationship summary

These are the approved business relationships between the core terms. Each one reads as a sentence.

- Customer **owns** Vehicle
- Customer **buys from** Dealer
- Vehicle **sold by** Dealer
- Dealer **located in** Region
- Dealer **employs** Salesperson
- Sale **for product** Vehicle
- Sale **sold by** Dealer
- Sale **recorded in** Region
- Revenue **measured from** Sale
- Units Sold **measured from** Sale
- Policy **covers** Vehicle
- Policy **held by** Customer
- Claim **linked to** Policy
- Loss Ratio **calculated from** Claim and Premium

# Standalone shopping agent

Copy `agent.py` into your existing ADK agent package, replacing its current file
after making a backup. Keep the package's existing `__init__.py` importing `agent`.
The AskDB application and existing environment files have not been changed.

Install with Python 3.11+:

```powershell
python -m pip install -r requirements-shopping.txt
```

In your agent's existing `.env`, configure:

```dotenv
OPENAI_API_KEY=your_capgemini_gateway_key
SERPAPI_API_KEY=your_serpapi_key
```

Do not commit this file. Dependencies above identify the locally installed versions;
use an isolated environment rather than upgrading an unrelated application.

Run `python agent.py --check-model` from your package directory to make one live
gateway call that tests native tool selection. It prints no response text or secrets.
A pass confirms tool selection only; test a complete comparison in ADK Web too.
An unsupported model/gateway is a blocker: the script never switches your model.
Start `adk web` from the parent of your existing agent package. Example request:
"Compare Samsung Galaxy S25 256 GB prices across the four stores."

## Data coverage and limits

Uses SerpApi's documented Google Shopping endpoint and fields:
https://serpapi.com/shopping-results

Four domain-targeted queries run concurrently. Provider requests are fixed to
`https://serpapi.com/search.json`; no user or retailer URL is fetched, and redirects
are disabled. There is no arbitrary URL retrieval or CAPTCHA bypass. Only merchant
links on the four approved exact domains or their `www` hosts are displayed.
Google product-page links and other stores are discarded. Consequently some searches
may return no usable listings even if a store sells the product. Coverage is not guaranteed.

**This is a preliminary search-feed comparison, not a verified checkout-price
comparison.** Search prices can be stale or conditional. Stock, delivery, mandatory
fees, exact variants, bundles and new condition remain unknown unless the source
explicitly supplies them. No verified winner is declared. No discounts are subtracted,
unknown charges remain null, and no misleading total is computed. Decimal is used
for reported price normalization. No cache is used. Rating counts may be available;
review text and review-theme summaries are not supported.

Retailer-confirmed offer verification and review-text retrieval are unfinished
capabilities requiring an appropriate additional data source. This implementation
must not be described as fulfilling those capabilities.

Callbacks use documented ADK contracts:
https://github.com/google/adk-docs/blob/main/docs/callbacks/types-of-callbacks.md

The tool budget is two calls per invocation (ADK `temp:` state), each with four
concurrent retailer searches. Each request has one transient retry, a 12-second
HTTP timeout and 1 MB decoded response cap. Provider errors are sanitized. An
LLM instruction is used for topic focus and injection resistance; it is not a
guarantee against prompt injection. Network restrictions are enforced by code.

## Checks

Run `python -m unittest test_shopping_agent -v`. These are mocked/offline checks.
Live provider coverage, real store prices and the gateway round trip require the
appropriate credentials and network access. Never treat fixture results as live.

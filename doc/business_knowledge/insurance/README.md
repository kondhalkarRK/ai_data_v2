# Insurance RAG demo documents

The two `INS-CFO-*.pptx` files are synthetic quarterly-result decks created
only for the ASK-DB demonstration. They are not real company disclosures.

Each deck contains:

- executive summary;
- governed KPI scorecard;
- line-of-business performance;
- regional claims performance;
- claims and underwriting drivers;
- capital, liquidity, outlook, and management actions.

When the Insurance industry pack is active, use **Knowledge base → INDEX
ACTIVE PACK** in the sidebar. ASK-DB extracts slide text and tables locally,
embeds them with the local sentence-transformer model, and stores the concepts
in Chroma. Citations appear as the PowerPoint filename plus slide number.

Regenerate both decks:

```powershell
python doc/business_knowledge/insurance/generate_cfo_quarterly_decks.py
```

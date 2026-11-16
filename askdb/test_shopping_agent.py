"""Offline fixture checks; never a live shopping comparison."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import agent


class ShoppingChecks(unittest.TestCase):
    def test_urls(self):
        for url in ("http://amazon.in/x", "https://amazon.in.evil.com/x",
                    "https://127.0.0.1/x", "https://amazon.in@evil.com/x",
                    "https://amazon.in:8080/x", "https://amazon.in/\nfoo"):
            self.assertIsNone(agent._retailer_url(url, "amazon.in"))
        self.assertEqual(agent._retailer_url("https://www.amazon.in/dp/x", "amazon.in"),
                         "https://www.amazon.in/dp/x")

    def test_prices_and_variant(self):
        row = {"title": "Samsung S25 256 GB", "product_link": "https://amazon.in/dp/x",
               "extracted_price": 71000, "old_price": "90000", "delivery": "Free delivery",
               "snippet": "Exchange discount 10000"}
        offer = agent._offers({"shopping_results": [row]}, "Amazon India", "Samsung S25 256 GB")[0]
        self.assertEqual(offer["listed_price"], "71000.00")
        self.assertIsNone(offer["shipping_cost"])
        self.assertIsNone(offer["total_price"])
        self.assertEqual(offer["verification_status"], "unverified_search_feed")
        self.assertNotEqual(offer["match_status"], "exact")
        self.assertEqual(agent._match("S25 512 GB", row["title"]), "uncertain_or_mismatch")
        self.assertIsNone(agent._money("NaN"))
        self.assertIsNone(agent._money(-1))

    def test_budget(self):
        context = SimpleNamespace(state={})
        tool = SimpleNamespace(name="compare_store_prices")
        args = {"product_query": "Samsung S25 256 GB"}
        self.assertIsNone(agent.before_tool(tool, args, context))
        self.assertIsNone(agent.before_tool(tool, args, context))
        self.assertEqual(agent.before_tool(tool, args, context)["status"], "tool_budget_exhausted")

    def test_missing_config(self):
        with patch.dict(agent.os.environ, {}, clear=True):
            result = asyncio.run(agent.compare_store_prices("Samsung S25 256 GB", SimpleNamespace(state={})))
        self.assertEqual(len(result["stores"]), 4)
        self.assertEqual(result["status"], "no_data")
        self.assertTrue(all(s["status"] == "missing_SERPAPI_API_KEY" for s in result["stores"]))

    def test_partial_failure(self):
        async def search(query, key):
            if "site:amazon.in" in query:
                return {"shopping_results": [{"title": "Samsung S25 256 GB", "product_link": "https://amazon.in/dp/x", "extracted_price": 71000}]}
            return {"error_code": "network_or_timeout"}
        with patch.dict(agent.os.environ, {"SERPAPI_API_KEY": "fixture"}), patch.object(agent, "_search", search):
            result = asyncio.run(agent.compare_store_prices("Samsung S25 256 GB", SimpleNamespace(state={})))
        self.assertEqual(result["status"], "preliminary_comparison")
        self.assertEqual(len(result["stores"]), 4)
        self.assertIsNone(result["verified_winner"])
        self.assertEqual(sum(bool(s["offers"]) for s in result["stores"]), 1)

    def test_agent_callbacks_and_schema(self):
        self.assertEqual(agent.root_agent.name, "root_agent")
        self.assertIs(agent.root_agent.before_tool_callback, agent.before_tool)
        from google.adk.tools import FunctionTool
        declaration = FunctionTool(agent.compare_store_prices)._get_declaration()
        self.assertIn("product_query", str(declaration))


if __name__ == "__main__":
    unittest.main()

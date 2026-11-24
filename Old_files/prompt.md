Hello Everyone, Welcome to the AI Era!
Capgemini Invent  presents AskDB - Ask Questions on Your Data and Get Instant Insights

Home Page: This is our landing page of AskDB. Here, it provides a sample visual representation of how the AI chat works. As we scroll down, we can find the active connections currently available in the application. All databases are connected, and the LLM API key is also configured.

This application supports multi-domain databases and multiple data modules, which can be toggled from here.

Now let's move further to the Data Preview section. As the name suggests, it provides a view of the data available in our system. In the current database, we have around 2 million records for the automotive domain, while the insurance domain contains approximately 100K records.

As we are dealing with data, we require a strong Data Quality mechanism. AskDB provides a "Data Trust Center", which consists of six data quality indicators used to calculate quality scores. We have implemented 15+ DQ rules to ensure data quality remains at the highest standard.

This is completely represented through dashboards, making it easy for business users to navigate and understand the module.

On top of our data, we have built a semantic layer called "Semantic Atlas." This semantic layer significantly enhances the quality of the application. Since LLMs do not inherently understand business data, the semantic layer helps user questions navigate the correct path and provides the right business context and keywords to the LLM, enabling accurate SQL generation.

For example, if a user asks, "Revenue by Month," the semantic layer understands that Revenue = Total Sales. Similarly, it maps business measures and dimensions, making the semantic layer powerful in reducing LLM hallucinations and improving response accuracy.

A few more examples:

If a user asks for "ASP," the AI understands it as "Average Selling Price."
If a user asks for the "top-selling car in NCR," the AI understands NCR as the Delhi NCR region.

Ontology Browser: This helps users understand the business meaning of data and see how a Sales table is connected to other tables or entities.

It provides visibility into relationships, showing where a table is connected and how those connections are established.

Relationship Network: Concepts are arranged in concentric rings, similar to a target. The most central concept appears in the bullseye, while concepts become less central as they move outward. The top five concepts are numbered, making it easy to identify key business hubs. For example, the #1 hub could be Sales.


Executive KPI Analytics: This module provides executive KPI dashboards with various dashboard utilities that can be managed and customized as needed. We have incorporated most major chart types to support business analysis.

These are interactive dashboards that business users can utilize based on their specific requirements and preferences.

Now, coming to the core part of the application, the AI Chat.

Users can ask questions in natural language and receive responses in the form of charts, narratives, and SQL queries.

If users have a SQL background, they can validate the generated SQL. We also have mechanisms in place to ensure responses remain grounded in the available data, along with generating a trust score for each response.

The system also suggests follow-up questions, allowing users to drill down further into their analysis. Each question is stored in the backend using a unique hash key.

Users can also monitor LLM usage, including token consumption and API call statistics.


Analytics Builder: This module is designed for business users who want to perform ad hoc analysis. Users can leverage metrics, dimensions, and advanced analytics capabilities to perform deeper analysis directly from this section.

Query History: This is the place where users can view their complete query history.

Users can also monitor their individual token usage and API call consumption.

Admin Center: This is the area where administrators can manage multiple aspects of the application.

LLM Settings: Administrators can change LLM models, adjust temperature settings, select the best-performing models, and analyze model-related costs.

Admin LLM Dashboard: Administrators can view LLM usage statistics across all users, including trend reports and usage analytics.

Audit Center: The application records every action performed within the system and stores it in the audit logs, which can later be used for monitoring and analysis.

Data Trust Admin: Administrators can enable or disable DQ rules whenever changes are required within the Data Quality Engine.

RBAC: We have integrated role-based access control at the regional level. For example, a North_User can only view North region data, while South_User can only access South region data. The same access restrictions apply to users from the other regions.

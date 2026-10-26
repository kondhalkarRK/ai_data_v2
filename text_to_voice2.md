Hello Everyone, Welcome to the AI Era!
Capgemini Invent presents AskDB - Ask Questions on Your Data and Get Instant Insights.

Home Page: This is the landing page of AskDB. Here, we provide a sample visual representation of how the AI chat experience works. As we scroll down, we can see the active connections currently configured within the application. All databases are connected, and the LLM API key has also been successfully configured.

Now let's move to the Data Preview section (wait for 2 sec). As the name suggests, it provides a view of the data available within our system. In the current database, we have approximately 2 million records for the automotive domain.

As we are dealing with data, having a strong Data Quality mechanism is essential. AskDB provides a "Data Trust Center" (wait for 2 sec), which consists of six key data quality indicators used to calculate quality scores. We have implemented 20+ Data Quality rules to ensure data quality remains at the highest standard. All these DQ rules are fully configurable by administrators and can also be managed through YAML configuration files.
Everything is represented through intuitive dashboards, making it easy for business users to navigate and understand the module.

On top of our data, we have built a semantic layer called "Semantic Atlas" (wait for 2 sec).
This semantic layer significantly enhances the intelligence and accuracy of the application. Since LLMs do not inherently understand business data and terminology, the semantic layer helps route user questions in the right direction and provides the appropriate business context and keywords to the LLM.
The beauty of Semantic Atlas is that both the semantic layer and business glossary are fully configurable through YAML files, allowing organizations to customize them according to their business requirements.

For example, if a user asks, "Revenue by Month," the semantic layer understands that Revenue = Total Sales. Similarly, it maps business measures and dimensions, making the semantic layer highly effective in reducing LLM hallucinations and improving response accuracy.
It also understands various business date formats and time-based expressions automatically.

A few more examples:
If a user asks for "ASP," the AI understands it as "Average Selling Price."
If a user asks for the "top-selling car in NCR," the AI understands NCR as the Delhi NCR region.

Ontology Browser (wait for 2 sec): This helps users understand the business meaning of data and visualize how a Sales table is connected to other tables and business entities.
It provides complete visibility into relationships, showing where a table is connected and how those connections are established.
We have created two separate ontologies for the Automotive and Insurance domains, and users can easily navigate between them from this section.

(wait for 2 sec)
Relationship Network: Concepts are arranged in concentric rings. The most important concept appears in the center, while other concepts are positioned outward based on their relevance. The top five concepts are highlighted, making it easy to identify key business hubs. For example, the #1 hub could be Sales.

Executive KPI Analytics (wait for 2 sec):
This module provides executive KPI dashboards with various visualization capabilities that can be managed and customized as needed.
We have incorporated most major chart types to support business analysis and decision-making.
These are fully interactive dashboards that business users can utilize based on their specific requirements and preferences.

Now, coming to the core part of the application, the AI Chat (wait for 2 sec).
Users can ask questions in natural language and instantly receive data-driven insights.
For example, let's enter "Top-selling Tata cars."
As we can see, the result shows that Nexon is the top-selling model.
We can also navigate to the Charts section (wait for 2 sec). Here, users can change the chart type using the available dropdown options.
Next, we have the Narration section. Based on the retrieved results, the LLM automatically generates a business-friendly summary along with key highlights and insights.
Now coming to the Trust Factor. How can users trust the generated result?
Users can review and validate the generated SQL query, and based on the Semantic Layer, a confidence score is calculated. The system also shows what it understood from the question, which business terms were mapped, and which join operations were performed (wait for 2 sec).
The application also suggests intelligent follow-up questions (wait for 3 sec).

Users can continue to drill down for deeper analysis and additional insights (wait for 2 sec).
Each question is stored in the backend using a unique hash key for traceability and auditing.

Users can also monitor LLM usage, including token consumption and API call statistics.

Analytics Builder (wait for 2 sec):
This module is designed for business users who want to perform ad hoc analysis.
Users can leverage metrics, dimensions, and advanced analytics capabilities to perform deeper business analysis directly from this section.


Query History (wait for 2 sec):
This is the place where users can view their complete query history and revisit previous analyses.
Users can also monitor their individual token usage and API call consumption.
RBAC - Role-Based Access Control
We have integrated role-based access control at the regional level.

Let's log out from the Admin account and log in as a North User.

We have created security roles based on geography.
A North_User can only view North region data, while a South_User can only access South region data. Similar restrictions apply to users from all other regions.

Now let's ask a question (wait for 3 sec).
This is just a sample use case. The access model is fully configurable and can be customized according to business requirements during deployment.


Now let's go back to the Admin Panel by logging out.
Admin Center (wait for 2 sec):

This is the area where administrators can manage multiple aspects of the application.
LLM Settings: Administrators can change LLM models, adjust temperature settings, select the most suitable models, and analyze model-related costs.

Admin LLM Dashboard: Administrators can view user-level and organization-wide LLM usage statistics, trend reports, and overall adoption metrics.

Audit Center: The application records every action performed within the system and stores it in audit logs. These logs can later be used for monitoring, compliance, and analysis purposes.
Data Trust Admin: Administrators can enable or disable DQ rules whenever changes are required within the Data Quality Engine.

Now, coming to what's next.

We are also making our application capable of handling unstructured data, which is currently available in Beta under a module called "Knowledge Hub."

Knowledge Hub can store business documents and other content that contains valuable business context. These documents are embedded into a Vector Database and integrated into our AI framework, enabling the AI Chat experience to generate more context-aware, intelligent, and accurate responses.

This is all about the AskDB application.
Thank you for your time, and stay tuned for more exciting updates and enhancements coming soon.

Thank You.
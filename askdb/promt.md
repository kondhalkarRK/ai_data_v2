You are a Principal AI Platform Architect, Senior Python Engineer, Senior Next.js Engineer, Database Architect, and enterprise UI/UX designer.

Build the next generation of the existing ASK-DB application, branded as “NQL Insight”.

This is a production implementation task. Do not provide pseudocode. Analyze the complete existing repository before editing or generating code.

==================================================
1. SOURCE AND TARGET DIRECTORIES
==================================================

Existing source application:

E:\ai_data_rag\ai_data_v2

Create the complete new standalone application only under:

E:\ai_data_rag\ai_data_v2\askdb

Critical directory rules:

1. Do not mix new frontend/backend files into the existing root.
2. Do not modify or delete the existing application during migration.
3. Copy and adapt only the required reusable Python modules into the new askdb directory.
4. The askdb directory must be independently:
   - Committable to GitHub
   - Installable on another machine
   - Runnable locally
   - Deployable without importing files from its parent directory
5. Do not reference E:\ai_data_rag\ai_data_v2 at runtime.
6. Do not copy node_modules, caches, logs, local databases, secrets, build output, or temporary files.
7. Preserve the legacy source as a rollback reference until the new application passes parity tests.

==================================================
2. REQUIRED ARCHITECTURE
==================================================

Remove Streamlit completely from the new application.

Use:

Frontend:
- Next.js App Router
- React
- TypeScript strict mode
- Tailwind CSS
- shadcn/ui
- TanStack Query
- Zustand for lightweight client state
- Framer Motion
- React Flow for ontology visualization
- Recharts or Apache ECharts for dashboards

Backend:
- FastAPI
- Pydantic v2
- SQLAlchemy 2 async
- psycopg
- Alembic
- Uvicorn
- Argon2 password hashing
- JWT access and refresh tokens
- SSE for streaming AI responses

Data:
- PostgreSQL for structured analytics and authentication
- MongoDB for raw unstructured documents and document metadata
- Qdrant for vector retrieval
- Existing semantic YAML remains the semantic source of truth

Deployment:
- Frontend optimized for Vercel
- FastAPI containerized for Railway, Render, or another Python host
- PostgreSQL, MongoDB, and Qdrant configured through environment variables
- GitHub-ready monorepo
- Docker Compose for local development

Use this structure:

askdb/
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── public/
│   │   └── tests/
│   └── api/
│       ├── app/
│       │   ├── api/
│       │   ├── auth/
│       │   ├── core/
│       │   ├── services/
│       │   ├── repositories/
│       │   ├── models/
│       │   ├── schemas/
│       │   ├── rag/
│       │   ├── semantic/
│       │   └── observability/
│       ├── migrations/
│       └── tests/
├── packages/
│   └── shared-types/
├── database/
│   ├── automotive/
│   ├── insurance/
│   └── app/
├── scripts/
├── docs/
├── docker-compose.yml
├── .env.example
├── README.md
└── vercel.json

Vercel must use apps/web as its project root. Do not attempt to run the long-lived FastAPI, RAG ingestion, or PostgreSQL connection pool inside Vercel serverless functions.

==================================================
3. PYTHON ENGINE PRESERVATION
==================================================

Do not rewrite the proven Python engines in TypeScript.

Analyze and selectively copy/adapt the reusable logic from:

- core/nlq_engine.py
- core/sql_guardrails.py
- core/sql_compiler.py
- core/question_normaliser.py
- core/intent_resolver.py
- core/intent_cache.py
- core/semantic_resolver.py
- core/evidence_builder.py
- core/llm_client.py
- core/data_backend/
- core/kpi_engine.py
- core/insurance_kpi_engine.py
- core/data_quality_engine.py
- core/postgres_dq_engine.py
- core/join_engine.py
- core/schema_builder.py
- core/semantic_joins.py
- core/chart_engine.py
- core/analysis_engine.py
- semantic/
- relevant cache and memory features
- utils/logger.py
- utils/decorators.py

Preservation rules:

1. Preserve business logic and SQL behavior.
2. Do not rewrite NLQ, semantic resolution, SQL guardrails, or metric calculations unless required to remove Streamlit coupling.
3. Remove:
   - import streamlit
   - st.session_state
   - st.secrets
   - st.cache_data
   - st.cache_resource
   - st.markdown
   - st.dataframe
   - all Streamlit rendering functions
4. Replace session state with typed request/session context.
5. Replace st.secrets with environment-based settings.
6. Replace Streamlit caching with application-level TTL caching.
7. Split compute logic from presentation logic.
8. Return typed Pydantic models from services.
9. The frontend must never generate SQL, execute database queries, enforce guardrails, or hold LLM secrets.

Create thin FastAPI services around the preserved engines:

- NLQService
- KPIService
- DataPreviewService
- DataQualityService
- SemanticService
- OntologyService
- RAGService
- ConversationService
- CostAnalyticsService
- LoggingService

==================================================
4. FEATURES DROPPED
==================================================

Do not implement:

- Streamlit
- MLflow
- OKF
- Neo4j
- Any graph database
- Agent catalog
- Agentic workflows
- Multi-agent orchestration
- Capgemini SSO
- Entra ID SSO

The “Knowledge Graph” UI means visualization of YAML relationships through React Flow. It does not mean a graph database.

==================================================
5. AUTHENTICATION
==================================================

Implement normal email/password authentication.

Requirements:

- Admin-created or seeded user accounts
- Email and password login
- Argon2 password hashes
- JWT access token
- Rotating refresh token
- HTTP-only, Secure, SameSite cookies where appropriate
- Logout and token revocation
- Rate limiting for login attempts
- Roles:
  - admin
  - analyst
  - viewer
- Route and API authorization
- Passwords and secrets must never appear in source control
- Include a CLI script for securely creating the initial admin user
- Include auth audit events

Do not provide hard-coded production credentials.

==================================================
6. INDUSTRY DATABASES
==================================================

Support two PostgreSQL analytics databases:

1. askdb_automotive
2. askdb_insurance

Automotive must contain four schemas:

- sales
- inventory
- claims
- master

Example Automotive tables:

sales:
- fact_sales
- fact_orders
- fact_returns

inventory:
- fact_inventory_snapshot
- fact_stock_movement
- dim_warehouse

claims:
- fact_warranty_claims
- fact_service_tickets

master:
- dim_carline
- dim_color
- dim_salesman
- dim_region
- dim_dealer
- dim_targets

Insurance should preserve the existing fact/dimension model:

- fact_claims
- fact_policy_monthly
- dim_policy
- dim_product
- dim_agent
- dim_region
- relevant operating expense and KPI tables

Requirements:

- Alembic migrations
- Primary and foreign keys
- Date and join-key indexes
- Schema-qualified SQL
- Connection pooling
- Read-only analytics transaction mode
- Statement timeout
- Maximum result-row enforcement
- Server-side pagination
- Efficient support for at least 2 million records per database
- KPI calculations performed in SQL
- Materialized summary views for expensive executive metrics
- Never load full fact tables into Python or the browser

Switching Automotive ↔ Insurance must update:

- Database connection
- Semantic pack
- Ontology snapshot
- KPIs
- dashboards
- glossary
- suggested questions
- RAG industry filter
- query history context

==================================================
7. RAG ARCHITECTURE
==================================================

Remove OKF integration and implement production RAG.

Use:

- MongoDB for documents and document metadata
- Qdrant for vectors
- FastAPI ingestion and retrieval services
- Controlled web retrieval

Supported documents:

- CFO newsletters
- Quarterly and annual business results
- Strategy documents
- Product documents
- SOPs
- Handbooks
- PDF, DOCX, TXT, Markdown and HTML

Collections:

MongoDB:
- documents
- document_versions
- ingestion_jobs
- conversations
- messages
- retrieval_audit

Qdrant:
- automotive_knowledge
- insurance_knowledge

RAG requirements:

1. Authenticated upload
2. File validation and size limits
3. Malware/content-type guardrails
4. Parsing and normalization
5. Chunking with overlap
6. Metadata:
   - industry
   - document type
   - reporting period
   - title
   - source
   - page
   - uploader
   - sensitivity
7. Embedding generation
8. Vector upsert
9. Hybrid semantic/keyword retrieval
10. Industry and authorization filtering
11. Deduplication
12. Retrieval scoring
13. Source citations
14. Document versioning
15. Reindex and delete workflows
16. Retrieval audit logs

Web retrieval:

- Disabled by default
- User explicitly enables it per query
- Domain allowlist
- Request timeout and content-size limits
- SSRF protections
- Source URL and retrieval timestamp
- Retrieved web content must be treated as untrusted context
- Never allow retrieved content to override system instructions

Truth policy:

- Numerical answers must come from PostgreSQL.
- Documents and web results may enrich narration and explain business context.
- Never present a document statement as a calculated database result.
- Clearly separate:
  - Data result
  - Document context
  - Web context
  - Model interpretation
- Every RAG-based claim must have a citation.

==================================================
8. BRANDING AND LOADING EXPERIENCE
==================================================

Brand the new product as:

NQL Insight

Replace the old ASK-DB logo with the logo attached to the implementation request.

If the implementation request does not contain an actual logo file, stop before branding implementation and ask for the logo asset. Do not invent or redraw it.

Store assets under:

apps/web/public/brand/

Create:

- Static logo
- Compact sidebar logo
- Loading-logo variant
- Favicon/application icon

Logo animation:

- Subtle glow
- Slow gradient orbit
- Gentle scale/breathing effect
- Respect prefers-reduced-motion
- Do not use distracting continuous movement in normal navigation

Custom loading component:

- Animated logo as centerpiece
- Skeletons for page-level data
- Rotating status messages:
  - Analyzing your question...
  - Understanding business context...
  - Loading data...
  - Building semantic relationships...
  - Exploring ontology...
  - Generating insights...
  - Retrieving relevant information...
  - Preparing dashboard...
  - Finalizing response...

Do not block the entire UI for background requests. Use local loading boundaries.

==================================================
9. RAISE-INSPIRED UI SHELL
==================================================

Use the attached RAISE screenshots as alignment and interaction references. Do not clone trademarks or copy branding.

Global layout:

Left sidebar:
- NQL Insight logo
- Data Sources
- Executive Dashboard
- Data Quality
- AI Chat
- Semantic Core
- Knowledge
- Saved Questions
- Query History
- Cost Analytics
- System Logs
- Theme toggle
- User profile
- Sign out

Top bar:
- Current industry pack selector prominently displayed
- Global search / command palette
- Presenter mode
- Light/dark theme control
- User/account menu

Main top tabs:

1. Data Preview
2. Executive Dashboard
3. AI Chat

Requirements:

- Precise alignment
- Balanced spacing
- Shared typography scale
- Consistent card radius, borders and shadows
- Light theme by default
- Dark theme fully supported
- Instant client-side theme change
- Responsive desktop/tablet/mobile behavior
- Keyboard navigation
- Accessible focus states
- WCAG-conscious contrast
- Premium enterprise SaaS appearance

==================================================
10. SEMANTIC CORE HUB
==================================================

Clicking Semantic Core opens a capability-card hub:

- Semantic Models
- Semantic Relationships
- Join Definitions
- Business Glossary
- Ontology Browser
- Data Products
- Memory / Knowledge Search
- Unified Search

Each card must show:

- Icon
- Title
- Short explanation
- Current pack
- Metadata count/status
- Navigation affordance

The “Semantic & Join” functions from the old sidebar belong under Semantic Core.

==================================================
11. ONTOLOGY BROWSER
==================================================

Use existing semantic YAML as the only source of truth.

Compile YAML into an optimized snapshot:

{
  "nodes": [],
  "edges": [],
  "clusters": [],
  "metadata": {}
}

Do not query PostgreSQL when clicking an ontology node.

Graph features:

- Force layout
- Centrality layout
- Hierarchy layout
- Draggable nodes
- Search
- Filtering
- Zoom, fit and reset
- Cluster chips
- Optional dashed cluster zones
- Node sizing by degree
- Edge tracing
- Egonet focus
- Hover highlighting
- Selected-node pulse
- Smooth layout transitions
- Graph build-time display
- Virtualized/visible-element rendering
- Memoized layouts
- Web Worker for expensive layouts

Target:

- 500+ nodes
- 2,000+ edges
- Initial snapshot parse and normal layout target below 200ms
- Node drawer opens immediately without network calls

Node drawer tabs:

- Overview
- Schema
- Relationships
- Lineage

Overview:
- Description
- Synonyms
- Source/physical table bindings
- Domain
- Entity type

Schema:
- Column name
- Display name
- Type
- Role
- Primary-key icon
- Foreign-key reference
- Nullable status when present

Relationships:
- Incoming/outgoing relationships
- Cardinality
- Join columns

Lineage:
- Source tables
- Referenced dimensions
- Metric dependencies

Use the RAISE screenshots for clean white canvas, colored clusters, compact graph stats, polished drawer, and AI-inspired effects.

==================================================
12. DATA PREVIEW
==================================================

Build an enterprise data-grid experience:

- Industry, database, schema and table selector
- Column search
- Sorting
- Server-side pagination
- Sticky headers
- Column visibility
- Column resizing
- Type badges
- Null indicators
- Search/filter builder
- Export current filtered page
- Responsive layout
- Row cap and query timeout
- Empty/error/loading states

Never download 2 million rows to the browser.

==================================================
13. EXECUTIVE DASHBOARD
==================================================

Create industry-driven dashboards from metric definitions.

Features:

- KPI cards
- Interactive charts
- Date ranges
- Region/product/LOB filters
- Drill-down
- Cross-filtering
- Period comparisons
- Dynamic tooltips
- Export
- Presenter mode
- Industry-specific metric registry
- Automatic refresh when the industry changes

Automotive examples:

- Sales revenue
- Units sold
- Inventory days
- Dealer performance
- Warranty claims
- Return rate
- Target versus actual

Insurance examples:

- Gross written premium
- Earned premium
- Claims incurred
- Loss ratio
- Claim frequency
- Severity
- Approval rate
- Renewal rate

What-if analysis:

- Keep separate from ordinary KPI reporting.
- Display only when predictive/forecast data exists.
- Clearly label Scenario Mode.
- Sliders must not silently overwrite actual metrics.
- Support relevant controls such as:
  - volume uplift
  - price or discount change
  - inventory-days target
  - premium growth
  - loss-ratio target
  - approval threshold
- Include reset scenario.
- Show Actual versus Scenario.

==================================================
14. DATA QUALITY
==================================================

Create a RAISE-inspired quality dashboard using existing Python DQ computations:

- Tables checked
- Data-quality score
- Evaluation runs
- Pass rate
- Open issues
- Severity distribution
- Trend chart
- Rule list
- Run history
- Issue details
- Industry-aware rules

Do not create agents or agent quality metrics.

==================================================
15. AI CHAT
==================================================

Create a premium streaming chat:

- SSE streaming
- Clean message hierarchy
- Markdown and safe code rendering
- SQL drawer
- Trust score
- Data-result table/chart
- RAG citations
- Pin conversation
- Save conversation
- Share with permission controls
- Export
- Suggested follow-up questions
- Query history
- Cancel generation
- Retry
- Copy response
- Clear context
- Industry-aware suggested prompts
- Token and estimated-cost indicator

Chat execution:

1. Authenticate.
2. Select industry.
3. Resolve semantic context.
4. Generate guarded SQL.
5. Execute bounded SQL.
6. Retrieve RAG context when relevant.
7. Build narration.
8. Stream response.
9. Persist query, usage and citations.
10. Log performance.

No agents or multi-agent loops.

==================================================
16. COST ANALYTICS
==================================================

Track and display:

- Prompt tokens
- Completion tokens
- Total tokens
- Estimated cost
- Model
- User
- Query ID
- Industry
- Daily trends
- Monthly trends
- Cost by model
- Cost by user
- Cost by query
- Cache savings
- Optimization insights

All provider prices must be configuration-driven.

==================================================
17. SAVED QUESTIONS AND HISTORY
==================================================

Saved Questions:

- Personal collections
- Shared collections
- Tags
- Search
- Run again
- Pin
- Rename
- Delete
- Permissions
- Show estimated saved tokens/cache benefit

Query History:

- Question
- Industry
- SQL
- Status
- Runtime
- Rows
- Tokens
- Cost
- Timestamp
- Error
- RAG citations

==================================================
18. LOGGING AND MONITORING
==================================================

Remove MLflow completely from the new application.

Keep and adapt centralized Python logging.

Capture:

- Last 10 execution logs in UI
- Query execution logs
- Error logs
- AI response logs
- Performance stages
- RAG retrieval logs
- Authentication audit
- Query ID
- User ID
- Industry
- API calls
- DB calls
- Rows
- Status
- Error stack

Do not expose sensitive prompts, passwords, tokens, connection strings, or document contents in general logs.

Provide `/health`, `/ready`, and protected diagnostics endpoints.

==================================================
19. PERFORMANCE REQUIREMENTS
==================================================

Targets:

- Client navigation below 100ms perceived latency
- Theme toggle below 50ms
- Ontology node drawer immediate
- First streaming event emitted promptly
- API endpoints paginated and bounded
- 2 million rows per analytics database supported
- No full fact-table DataFrames
- Query result cap
- SQL statement timeout
- Connection pooling
- Indexed joins and date filters
- Query cancellation
- Lazy route loading
- Code splitting
- Memoized charts
- Virtualized tables
- React Flow visible-element rendering
- Cache stable semantic snapshots and metadata
- No page-wide rerender for local component changes

==================================================
20. SECURITY
==================================================

Implement:

- Secure password hashing
- JWT validation and rotation
- CORS allowlist
- CSRF protection appropriate to cookie strategy
- Rate limiting
- SQL read-only mode
- SQL allowlist/guardrails
- Upload validation
- RAG prompt-injection defenses
- SSRF-safe web retrieval
- Role checks
- Audit logs
- Secret redaction
- Pydantic request validation
- Security headers
- No `eval`
- No raw HTML rendering without sanitization

==================================================
21. TESTING
==================================================

Backend:

- Unit tests for preserved Python engines
- API contract tests
- Auth tests
- SQL guardrail tests
- Industry routing tests
- Pagination tests
- RAG retrieval/citation tests
- 2-million-row query-plan smoke tests
- Regression tests against existing golden NLQ questions

Frontend:

- Vitest/component tests
- React Testing Library
- Playwright end-to-end tests
- Login
- Industry switching
- Data Preview
- Executive Dashboard
- Chat
- Ontology layouts and node drawer
- Saved Questions
- Cost Analytics
- Light/dark theme
- Accessibility checks

==================================================
22. EXECUTION STRATEGY
==================================================

Before implementation:

1. Analyze the complete legacy repository.
2. Produce a migration inventory:
   - keep
   - adapt
   - replace
   - retire
3. Map existing Streamlit screens to Next.js routes.
4. Identify every `streamlit` import in reusable Python code.
5. Identify all environment variables and secrets.
6. Map Automotive and Insurance semantic packs and tables.
7. Identify existing OKF and MLflow code to exclude.
8. Confirm the attached logo asset is available.
9. Produce a phased plan with acceptance criteria.
10. Do not delete the legacy source.

Implement in phases:

Phase 1:
- Standalone monorepo
- Authentication
- API foundation
- Shared design system
- RAISE-inspired shell
- Health endpoints

Phase 2:
- Semantic API
- Ontology Browser
- Industry switching

Phase 3:
- PostgreSQL migrations
- Automotive and Insurance routing
- Data Preview
- Data Quality

Phase 4:
- Executive Dashboard
- KPI filters
- Predictive-only What-if

Phase 5:
- AI Chat parity
- SSE
- Saved Questions
- History
- Cost Analytics

Phase 6:
- Mongo/Qdrant RAG
- Knowledge Hub
- Web retrieval
- Citations

Phase 7:
- Performance, security and deployment hardening
- Vercel frontend deployment
- Backend deployment
- Full parity validation

Do not remove the legacy Streamlit application until all parity tests pass. The new standalone askdb project itself must contain no Streamlit dependency.

==================================================
23. REQUIRED DELIVERABLES
==================================================

Deliver:

1. Complete production-ready code under:
   E:\ai_data_rag\ai_data_v2\askdb
2. Migration inventory
3. Architecture document
4. API documentation
5. Database migrations
6. Seed scripts
7. `.env.example`
8. Docker Compose
9. Vercel configuration
10. Backend Dockerfile
11. Local Windows startup scripts
12. README with exact commands
13. Test suite
14. Deployment guide
15. Security checklist
16. Performance checklist
17. Feature-parity checklist
18. List of preserved Python files
19. List of adapted Python files
20. List of retired Streamlit files

==================================================
24. ENGINEERING RULES
==================================================

- No pseudocode
- No placeholder components presented as complete
- No silent exception swallowing
- Strict type checking
- Python type hints
- Modular design
- Accessible UI
- Production error states
- Preserve business logic
- Do not fabricate database results
- Do not modify the original project
- Do not add agents, Neo4j, OKF, MLflow or Streamlit
- Keep numerical truth in PostgreSQL
- Keep semantic truth in YAML
- Keep RAG claims cited
- Validate each phase before proceeding
- Report blockers instead of guessing credentials or infrastructure

At completion, provide:

- Files created
- Legacy files reused
- Business logic adaptations
- Test results
- Build results
- Performance observations
- Remaining deployment prerequisites
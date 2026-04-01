# AI Browser Agent Landscape Research

Research date: 2026-03-31. Focus: AI agents that can autonomously operate web browsers to gather data, with emphasis on data extraction for restaurant market intelligence in European markets (Poland).

---

## 1. Major Browser-Operating Agent Frameworks

### 1.1 Anthropic Computer Use (Claude)

**What it is:** Anthropic's computer use capability allows Claude to control a computer the way a human does -- looking at the screen (via screenshots), moving a cursor, clicking, and typing. Available via API since October 2024 (public beta), with consumer-facing desktop agent launching March 2026.

**Open source:** No. Proprietary API. However, it is a client-side tool -- screenshots, mouse actions, and keyboard inputs are captured in YOUR environment, not by Anthropic. Anthropic processes images in real-time but does not retain them.

**Headless operation:** Yes. Since it operates via API + screenshots, you provide the environment. You can run it against a headless browser in a container. The model sees screenshots you send it and returns actions.

**Reliability for data extraction:** Moderate. Computer use relies on screenshot-based vision, which is slower and less precise than DOM-based approaches. Better for complex GUI interactions than for structured data extraction. Anthropic themselves caution it is "still early compared to Claude's ability to code or interact with text."

**Speed/cost:** Expensive per action. Each step requires sending a screenshot (image tokens) + receiving action instructions. Using Sonnet 4.6 at $3/$15 per million input/output tokens, a multi-step workflow can cost $0.05-0.50 per task depending on complexity. Batch API (50% discount) and prompt caching (90% savings) can reduce costs significantly for repeated patterns.

**Auth/login flows:** Yes. Since it controls a real browser session, it can handle login flows. However, you need to manage credentials securely in your environment.

**CAPTCHAs/anti-bot:** Limited. Vision models can sometimes solve simple image CAPTCHAs, but modern behavioral CAPTCHAs (Cloudflare Turnstile, hCaptcha) analyze mouse movements and device fingerprinting that screenshot-based agents cannot replicate convincingly.

**Best for:** Complex, unpredictable GUI interactions where you need general intelligence. Not ideal for high-volume data extraction.

**Models:** Claude Opus 4.6, Sonnet 4.6 recommended. Available via Anthropic API, Amazon Bedrock, and Google Vertex AI.

---

### 1.2 OpenAI Operator / Computer-Using Agent (CUA)

**What it is:** OpenAI's Computer-Using Agent (CUA), powered by GPT-4o vision + reinforcement learning. Originally launched as "Operator" (January 2025), a consumer product where CUA controlled a Chrome browser to complete tasks. Operator was deprecated August 2025 and folded into ChatGPT as "agent mode." CUA is also available via the Responses API for developers. The consumer experience now lives in ChatGPT Atlas (a dedicated browser, launched October 2025, macOS only).

**Open source:** No. Proprietary. Sample app available on GitHub (openai/openai-cua-sample-app).

**Headless operation:** Via API: yes. CUA through the Responses API can operate in a developer-controlled environment including containers. The consumer products (Atlas, ChatGPT agent mode) require a visible browser.

**Reliability for data extraction:** Moderate-low for complex workflows. Benchmarks: 87% on WebVoyager, 58.1% on WebArena, 38.1% on OSWorld. Best for single-step or few-step browser tasks. Extended multi-step workflows are unreliable.

**Speed/cost:** API pricing: $3/$12 per million input/output tokens. Consumer access requires ChatGPT Pro ($200/month) for full agent capabilities. Plus subscribers ($20/month) have limited access.

**Auth/login flows:** Yes. Operator/Atlas work in the user's authenticated browser sessions. API version requires you to manage the browser environment.

**CAPTCHAs/anti-bot:** Same limitations as Anthropic -- screenshot-based, cannot convincingly replicate human behavioral signals for modern anti-bot systems.

**Best for:** Tasks where you want a managed experience (ChatGPT Pro). Developer API access via CUA for custom integrations.

---

### 1.3 Google Project Mariner / Gemini Browser Agents

**What it is:** Google DeepMind research prototype built on Gemini 2.0. Uses an "Observe-Plan-Act" loop: observes web elements (text, code, images, forms), plans actionable steps, acts by navigating/clicking/filling. Can handle up to 10 simultaneous tasks. Being integrated into Gemini app as "Agent Mode" and into Chrome browser via Google AI subscriptions.

**Open source:** No. Proprietary research prototype.

**Headless operation:** No standalone API for developers yet. Available to Google AI Ultra subscribers in the US. Being integrated into Gemini API and Vertex AI, but browser agent capabilities specifically are not yet generally available as a developer API.

**Reliability for data extraction:** Strong. 83.5% success rate on WebVoyager benchmark. Google's advantage is deep integration with Chrome's internals rather than just screenshots.

**Speed/cost:** Consumer: requires Google AI Ultra subscription (US-only). Developer API pricing not yet public for browser agent features. Standard Gemini 2.5 Pro via Vertex AI: $1.25/$10 per million input/output tokens.

**Auth/login flows:** Yes, operates within the user's authenticated Chrome session (consumer product). API integration would need to handle this programmatically.

**CAPTCHAs/anti-bot:** Better positioned than competitors because it operates within Chrome itself (not as an external agent), but specific anti-bot capabilities are not documented.

**Best for:** Users already in the Google ecosystem. Not yet practical for developer-driven data extraction at scale.

---

### 1.4 Browser Use (Open Source)

**What it is:** The leading open-source AI browser automation framework. Python library (TypeScript SDK also available) that combines DOM parsing with vision-based analysis. Model-agnostic -- works with OpenAI, Anthropic, Gemini, or any LLM. Uses Playwright under the hood. 78,000+ GitHub stars.

**Open source:** Yes. MIT License.

**Headless operation:** Yes. Playwright-based, fully supports headless mode.

**Reliability for data extraction:** Strong. 89.1% success rate on WebVoyager benchmark (586 tasks). Operates as an autonomous agent in a continuous reasoning loop: observe page, determine action, execute, reassess.

**Speed/cost:** The library is free. Costs come from LLM API calls (continuous inference at every step) and infrastructure. Cloud service also available with pricing: $0.01 per task initialization + $0.025/step (GPT-4.1) per step. A 10-step task costs ~$0.26. Subscription plans from $75/month.

**Auth/login flows:** Yes. Supports cookie persistence and authentication. Can handle login flows programmatically.

**CAPTCHAs/anti-bot:** No built-in CAPTCHA solving. Can integrate with third-party CAPTCHA services. Stealth technology available in newer versions.

**Multi-language support:** Model-dependent. Since it uses LLMs for page understanding, it handles Polish and other languages as well as the underlying model does (GPT-4o, Claude, Gemini all handle Polish well).

**Best for:** Developers who want full control, model flexibility, and an active open-source community. Excellent for exploratory and unpredictable workflows.

**Cloud pricing details:**

- Task initialization: $0.01/task
- Steps: $0.01-$0.025/step depending on model
- Subscription tiers: $75/mo (25 concurrent sessions) to enterprise custom
- Proxy and browser sessions billed separately

---

### 1.5 Playwright MCP (Microsoft)

**What it is:** Model Context Protocol (MCP) server by Microsoft that enables LLMs and AI agents to control browsers via Playwright. Released March 2025. Uses the browser's accessibility tree (structured, text-based representation) rather than screenshots, making it 10-100x more efficient in token consumption. Published as `@playwright/mcp` on npm.

**Open source:** Yes. Part of the Playwright ecosystem (Apache 2.0).

**Headless operation:** Yes. Full Playwright headless support.

**Reliability for data extraction:** High for structured pages. The accessibility tree approach is deterministic and fast. However, it cannot handle Shadow DOM well (modern component libraries hide elements in shadow roots). Also limited on highly visual/canvas-based pages where the accessibility tree doesn't capture the content.

**Speed/cost:** Very fast and cheap. An accessibility tree snapshot is 2-5KB vs. 500KB-2MB for a screenshot. No vision model needed -- works with text-only LLMs. Cost is essentially just the LLM inference on small text payloads.

**Auth/login flows:** Yes. Playwright handles cookies, sessions, and auth natively.

**CAPTCHAs/anti-bot:** No built-in CAPTCHA solving. Standard Playwright anti-detection limitations apply. Headless Chrome is detectable by sophisticated anti-bot systems.

**Best for:** Developers already using Playwright. Fast, cheap, deterministic browser control. Excellent for well-structured websites. Now built into GitHub Copilot Coding Agent.

**Limitation:** Shadow DOM is a known weakness. Many modern web apps use component libraries that hide elements in shadow roots, making them invisible to accessibility tree snapshots.

---

### 1.6 Stagehand by Browserbase

**What it is:** AI browser automation SDK built on top of Playwright. Adds three AI primitives -- `act()`, `extract()`, `observe()` -- on top of a standard Playwright page object. TypeScript-first. Think "Playwright with an AI brain." Version 3 (February 2026) was a complete rewrite, 44% faster, driver-agnostic via Chrome DevTools Protocol.

**Open source:** Yes. MIT License. 10,000+ GitHub stars.

**Headless operation:** Yes. Playwright-based. Also integrates with Browserbase cloud for managed headless browsers.

**Reliability for data extraction:** Good. The `extract(instruction, schema)` method pulls structured data with Zod schema integration. Introduces "auto-caching" that records successful actions and replays them without LLM calls on repeat runs, with self-healing when sites change.

**Speed/cost:** Lower costs on repeated workflows through cached action replay. Initial runs cost LLM inference; subsequent runs can skip API calls. Browserbase cloud: Free tier (1 concurrent browser, 1 hour), Developer ($20/mo, 25 browsers, 100 hours), Startup ($99/mo, 100 browsers, 500 hours).

**Auth/login flows:** Managed through Playwright sessions. No native 2FA/TOTP support (unlike Skyvern).

**CAPTCHAs/anti-bot:** Browserbase provides anti-detection features including stealth mode and proxy rotation. Stagehand itself doesn't handle CAPTCHAs.

**Best for:** TypeScript developers who want to enhance existing Playwright suites with AI capabilities. The caching mechanism makes it cost-effective for repeated workflows.

---

### 1.7 AgentQL

**What it is:** A semantic query language and toolkit for AI agents to interact with web elements and extract data. Uses AI to analyze page structure and find data based on meaning rather than DOM selectors. SDKs for Python and Node.js, built on top of Playwright.

**Open source:** Partially. SDK and tools on GitHub (tinyfish-io/agentql). Commercial service with API.

**Headless operation:** Yes. Integrates with Playwright headless browsers. Also offers remote browser sessions via cloud.

**Reliability for data extraction:** Strong for structured data. The semantic selector approach means scripts continue working even when websites change their DOM structure. Designed specifically for precise data extraction rather than general-purpose automation.

**Speed/cost:**

- Free Trial: 300 API calls, 1 hour remote browser, 1 concurrent session
- Starter: Free, 50 calls/month + $0.02/additional call, 10 hours remote browser
- Professional: $99/month, 10,000 calls, 500 hours remote browser, 100 concurrent sessions
- Enterprise: Custom pricing, managed cloud, on-premise option

**Auth/login flows:** Yes. Can interact with forms and handle login flows via Playwright integration.

**CAPTCHAs/anti-bot:** Not documented as a core feature. Relies on underlying browser infrastructure.

**Best for:** Structured data extraction from websites. The query language approach is particularly useful for extracting specific data fields reliably across changing websites.

---

### 1.8 Skyvern

**What it is:** AI browser automation platform that uses Vision LLMs and computer vision to interact with websites visually rather than through DOM selectors. Y Combinator-backed. Planner-actor-validator architecture. Visual workflow builder for no-code automation.

**Open source:** Core framework: Yes (AGPL-3.0 license). Anti-bot measures are cloud-only.

**Headless operation:** Yes. Both self-hosted and cloud options.

**Reliability for data extraction:** Good. 85.85% on WebVoyager 2.0 benchmark. 64.4% on WebBench (SOTA). Visual approach means it works on any website regardless of DOM structure.

**Speed/cost:**

- Self-hosted: Free (AGPL-3.0), bring your own infrastructure
- Cloud: Free (1,000 credits/mo), Hobby ($29/mo, 30K credits), Pro ($149/mo, 150K credits), Enterprise (custom, unlimited)
- Pay-per-use: $0.05/step including infrastructure, proxies, anti-bot
- Enterprise: Self-hosted deployment, HIPAA, SOC2, SSO

**Auth/login flows:** Yes. Native 2FA and TOTP authentication support -- a standout feature.

**CAPTCHAs/anti-bot:** Yes (cloud version). Bundled proxy network, CAPTCHA solvers, and anti-bot detection mechanisms. The open-source version does NOT include anti-bot measures.

**Best for:** Production automation across unfamiliar websites. The only framework with native 2FA/TOTP, built-in CAPTCHA solving, and proxy network in its cloud offering. Good for delivery platform scraping where anti-bot is critical.

---

### 1.9 MultiOn

**What it is:** AI agent platform for autonomous web actions. Offers a Chrome extension for natural language browser commands and an API for programmatic access. Integrates with LangChain and LlamaIndex.

**Open source:** No. Proprietary API and Chrome extension.

**Headless operation:** API supports server-side execution. Chrome extension requires a visible browser.

**Reliability for data extraction:** Moderate. Good for browsing and data retrieval via natural language. Offers a Retrieve API specifically for web information extraction. Reliability data/benchmarks not publicly available.

**Speed/cost:** Pricing not publicly documented as of March 2026. API-based with Python and JavaScript SDKs.

**Auth/login flows:** Chrome extension works in existing browser sessions (logged-in state). API requires separate session management.

**CAPTCHAs/anti-bot:** Documentation mentions CAPTCHA and authentication handling capabilities.

**Best for:** Quick prototyping of browser agents. Good integration ecosystem (CrewAI, LangChain, LlamaIndex). Less proven for production-scale data extraction.

---

### 1.10 Amazon Nova Act

**What it is:** AWS service for building reliable AI agents for UI workflow automation. Powered by custom Nova 2 Lite model. SDK released March 2025, now generally available. Combines natural language instructions with Python code and Playwright for browser control.

**Open source:** SDK is open source on GitHub (aws/nova-act). The model itself is proprietary AWS.

**Headless operation:** Yes. Integrates with Amazon Bedrock AgentCore Browser Tool for scalable cloud-based browser execution.

**Reliability for data extraction:** Strong. Claims >90% accuracy on internal evals for tricky UI elements (date pickers, dropdowns, popups). Best-in-class on ScreenSpot (0.939) and GroundUI Web benchmarks. Designed for reliable atomic commands.

**Speed/cost:** AWS pricing model. Specific per-step costs not detailed in research. Integrates with S3, IAM, and Bedrock infrastructure.

**Auth/login flows:** Yes. Can alternate between AI actions and direct Playwright manipulation (e.g., for entering passwords securely).

**CAPTCHAs/anti-bot:** Not explicitly documented. AgentCore Browser Tool includes "Web Bot Auth" preview feature to reduce CAPTCHAs.

**Best for:** Teams already on AWS. Production-grade reliability with CI/CD integration. Strong for QA testing, data entry, and structured extraction workflows.

---

### 1.11 Manus Browser Operator (acquired by Meta, January 2026)

**What it is:** AI agent that operates your local browser directly, using your existing logins and sessions. Launched November 2025. Acquired by Meta for $2 billion in January 2026. Works as a Chrome/Edge extension rather than cloud-based.

**Open source:** No. Proprietary.

**Headless operation:** No. Operates on your local browser. This is by design -- the local browser approach bypasses CAPTCHAs and anti-bot measures because it uses your real, trusted browser session.

**Reliability for data extraction:** Good for authenticated workflows. Can handle multi-step tasks across sites. Complex interactions like drag-and-drop still have limitations.

**Speed/cost:** Pricing details not fully public post-Meta acquisition.

**Auth/login flows:** Excellent. Its primary advantage is using your already-authenticated browser sessions.

**CAPTCHAs/anti-bot:** Effectively bypasses these by operating within a real, trusted browser session with genuine cookies and browsing history.

**Best for:** Tasks requiring authenticated access to platforms where you're already logged in. Not suitable for headless/automated data collection at scale.

---

### 1.12 Other Notable Frameworks

**Crawl4AI** (open source, Apache 2.0)

- Python crawler specifically built for RAG pipelines and LLM data ingestion
- Generates clean Markdown from web pages, removes boilerplate
- Supports LLM-driven structured extraction, CSS/XPath selectors, semantic filtering
- Async browser pool for concurrent crawling, stealth modes, proxy support
- Free and open source. No API keys or paywalls required
- 100% focused on data extraction, not general browser automation
- Best for: Converting websites into LLM-ready data at scale

**Firecrawl** (partially open source)

- Web data infrastructure with /scrape, /crawl, /map, /extract endpoints
- 95.3% success rate vs Crawl4AI's 89.7%, lower noise ratio (6.8% vs 11.3%)
- SDKs for Python, JavaScript, Go, Rust
- Pricing: Free (500 credits), paid from $16/month
- 96% web coverage with anti-bot measures
- Best for: Managed web scraping with reliable structured output

**Steel** (open source, self-hostable)

- Open-source headless browser API purpose-built for AI agents
- Auto CAPTCHA solving, proxy management, browser fingerprinting
- /scrape, /screenshot, /pdf endpoints for quick data extraction
- 80B+ tokens scraped, 200K+ browser hours served
- SDKs for Python and Node.js
- Best for: Self-hosted browser infrastructure for agents

**Lightpanda** (open source, early stage)

- Headless browser written in Zig, purpose-built for machines
- 9x less memory than headless Chrome
- Puppeteer/Playwright compatible via Chrome DevTools Protocol
- Best for: High-performance, resource-efficient headless browsing

**Sigma AI Browser** (free consumer browser)

- Full agentic features including login, forms, data extraction
- Runs locally without cloud dependency
- Available on Windows, macOS, Linux, Android, iOS
- Best for: Free experimentation with browser agents

---

## 2. Comparison Matrix

| Framework                  | Open Source  | Headless           | WebVoyager Score       | Data Extraction   | Auth/Login | CAPTCHA                  | Cost                         |
| -------------------------- | ------------ | ------------------ | ---------------------- | ----------------- | ---------- | ------------------------ | ---------------------------- |
| **Anthropic Computer Use** | No           | Yes (API)          | N/A                    | Moderate          | Yes        | Limited                  | $3-15/M tokens               |
| **OpenAI CUA**             | No           | Yes (API)          | 87%                    | Moderate          | Yes        | Limited                  | $3-12/M tokens + $200/mo Pro |
| **Google Mariner**         | No           | No (consumer only) | 83.5%                  | Good              | Yes        | Unknown                  | AI Ultra subscription        |
| **Browser Use**            | Yes (MIT)    | Yes                | 89.1%                  | Strong            | Yes        | No (integrate 3rd party) | Free + LLM costs             |
| **Playwright MCP**         | Yes (Apache) | Yes                | N/A                    | High (structured) | Yes        | No                       | Near-free (text LLM)         |
| **Stagehand**              | Yes (MIT)    | Yes                | N/A                    | Good (schema)     | Yes        | Via Browserbase          | Free + Browserbase $20-99/mo |
| **AgentQL**                | Partial      | Yes                | N/A                    | Strong (semantic) | Yes        | No                       | Free-$99/mo                  |
| **Skyvern**                | Yes (AGPL)   | Yes                | 85.85%                 | Good (visual)     | Yes + 2FA  | Yes (cloud)              | Free-$149/mo cloud           |
| **MultiOn**                | No           | Partial            | N/A                    | Moderate          | Yes        | Claimed                  | Unknown                      |
| **Amazon Nova Act**        | SDK only     | Yes                | N/A (0.939 ScreenSpot) | Strong            | Yes        | Partial                  | AWS pricing                  |
| **Manus**                  | No           | No (local)         | N/A                    | Good              | Excellent  | Bypasses (local)         | Unknown (Meta)               |
| **Crawl4AI**               | Yes (Apache) | Yes                | N/A                    | Excellent         | Partial    | No                       | Free                         |
| **Firecrawl**              | Partial      | Yes                | N/A                    | Excellent (95.3%) | Partial    | Yes                      | Free-$16+/mo                 |
| **Steel**                  | Yes          | Yes                | N/A                    | Good              | Yes        | Yes                      | Free (self-host)             |

---

## 3. Data Scraping / Research Use Cases

### 3.1 Best for Extracting Structured Data from Websites

**Tier 1 -- Purpose-built for extraction:**

1. **Crawl4AI** -- Best pure extraction tool. Free, fast, produces clean Markdown and structured JSON. Excellent for converting restaurant websites, review pages, and delivery platform pages into structured data. Supports CSS/XPath + LLM-based extraction.
2. **Firecrawl** -- More reliable (95.3% vs 89.7%) with managed infrastructure. Better for production use where you want someone else to handle scaling and anti-bot.
3. **AgentQL** -- Semantic query approach is ideal for extracting specific fields (restaurant name, price, rating) that persist even when site layouts change.

**Tier 2 -- Agent frameworks with extraction capabilities:** 4. **Stagehand** -- `extract(instruction, schema)` with Zod typing. Good for TypeScript teams. Caching reduces cost on repeated extractions. 5. **Skyvern** -- Schema-based extraction with visual understanding. Best when sites have complex layouts or resist DOM-based scraping.

**Tier 3 -- General-purpose agents (less efficient for pure extraction):** 6. **Browser Use** -- Can extract data but each step requires LLM inference. More expensive for high-volume extraction. 7. **Playwright MCP** -- Very efficient for well-structured pages but limited by accessibility tree gaps.

### 3.2 Best for Complex Multi-Step Workflows (Delivery Platforms, Booking Sites)

Navigating platforms like Wolt, Pyszne.pl, Glovo, Uber Eats requires:

- Handling location/address inputs
- Navigating category menus
- Pagination through restaurant listings
- Opening individual restaurant pages
- Extracting menu items, prices, and metadata
- Potentially handling login flows

**Recommended approaches:**

1. **Skyvern Cloud** ($0.05/step) -- Best single option. Built-in anti-bot, proxies, CAPTCHA solving. Visual approach handles delivery platform UIs well regardless of DOM changes. Native 2FA support for platforms requiring login. AGPL license for self-hosting the core logic.

2. **Browser Use + Steel/Browserbase** -- Open-source agent (Browser Use) running on managed browser infrastructure (Steel for self-hosted, Browserbase for cloud). More flexible but requires more setup. Good for custom workflows.

3. **Apify pre-built actors** -- Still the most practical option for specific platforms. Pre-built scrapers exist for Uber Eats and Wolt on Apify ($100-500/month). Less flexible but immediately productive.

4. **Amazon Nova Act + AgentCore Browser** -- For teams on AWS. High reliability for form-filling and navigation. Good CI/CD integration for scheduled scraping.

### 3.3 Polish Language / Non-English Site Support

**How AI browser agents handle non-English content:**

The agents themselves are language-agnostic in their browser control (clicking, scrolling, typing). Language matters in two areas:

1. **Understanding page content to decide what to do next:** This depends on the underlying LLM. GPT-4o, Claude 4 Sonnet/Opus, and Gemini 2.5 Pro all handle Polish well. Browser Use and Stagehand are model-agnostic, so you can choose any model with strong Polish support.

2. **Extracting and structuring text:** Again LLM-dependent. For Polish menu items, restaurant names, review text, etc., all major models perform well. Crawl4AI and Firecrawl extract raw text without language concerns; the LLM step for structuring handles Polish naturally.

**Specific considerations for Polish sites (Pyszne.pl, Wolt Poland, Glovo Poland):**

- These platforms are standard web applications. No special Polish-language challenges for browser agents.
- The main challenge is anti-bot measures, not language.
- Pyszne.pl (Just Eat Takeaway) uses Cloudflare protection -- requires stealth browser or residential proxies.
- Wolt Poland has relatively standard React frontend -- DOM-based extraction works.
- Glovo uses dynamic loading -- needs scroll simulation and wait handling.

**Recommendation:** Use Browser Use or Stagehand with a model that handles Polish well (any major model). For anti-bot challenges, pair with Browserbase or Steel for stealth features. Skyvern Cloud handles both language and anti-bot out of the box.

---

## 4. Anti-Detection and Ethical Considerations

### 4.1 Terms of Service Implications

**Legal landscape as of early 2026:**

- **Publicly accessible data:** The Meta v. Bright Data ruling (2024) established that scraping publicly available data while logged out may not violate a website's ToS, because no contract is formed without login or explicit agreement.

- **EU AI Act (enforcement August 2, 2026):** Will require AI developers to respect machine-readable signals from content owners (robots.txt, metadata, ToS) indicating data should not be used for AI training. This primarily targets AI training data, but sets precedent for automated data collection broadly.

- **Bypassing technical barriers:** High risk. If you defeat a protection mechanism (auth walls, access tokens, rate limiters) to get data, you are likely in dangerous legal territory in 2026.

- **Terms of service are contracts, not laws.** Violating ToS can lead to account termination, IP blocking, or civil claims, but is not automatically criminal. However, the legal exposure is higher when scraping involves circumventing access controls.

**Practical guidance for Superextra:**

- Scraping publicly viewable restaurant data (menus, prices, ratings) from delivery platforms carries moderate legal risk.
- Using managed services (Apify, Grepsr, Bright Data) transfers some legal risk to the service provider.
- AI browser agents add a layer of complexity because they mimic human browsing -- legally gray area.
- European markets (Poland) are subject to stricter data protection (GDPR). Restaurant business data (menus, prices) is less sensitive than personal data.

### 4.2 Rate Limiting

**How platforms detect and block scrapers:**

1. **Request rate:** Too many requests from one IP/session triggers blocks. Solution: distributed proxies, randomized delays.
2. **Behavioral patterns:** Non-human mouse movements, instant page loads, no scroll events. AI agents are better at mimicking human behavior than traditional scrapers, but still detectable.
3. **Browser fingerprinting:** Headless Chrome has detectable signatures (navigator.webdriver, missing plugins, etc.). Stealth plugins (puppeteer-extra-plugin-stealth) and managed services (Browserbase, Steel, Skyvern Cloud) address this.
4. **TLS fingerprinting:** Server-side analysis of TLS handshake to identify non-browser clients.

**Anti-detection approaches by tool:**

| Tool          | Anti-Detection Strategy                                              |
| ------------- | -------------------------------------------------------------------- |
| Skyvern Cloud | Bundled proxy network, CAPTCHA solvers, anti-bot mechanisms          |
| Browserbase   | Stealth mode, session recordings, proxy rotation                     |
| Steel         | CAPTCHA solving, proxy management, browser fingerprinting            |
| Browser Use   | Stealth technology in newer versions; pair with infrastructure       |
| Crawl4AI      | Stealth modes, proxy support, hooks for custom evasion               |
| Manus         | Uses local browser (inherently undetectable -- it IS a real browser) |

### 4.3 CAPTCHA Handling

**Modern CAPTCHAs in 2026 are behavioral, not just visual:**

- **Cloudflare Turnstile:** Invisible CAPTCHA using proof-of-work, client-side checks, behavioral analysis. Rarely shows a puzzle. Automation must acquire a valid Turnstile token.
- **hCaptcha:** Still effective against AI agents in 2026. Relies on behavioral data and device fingerprinting, not just image recognition.
- **reCAPTCHA v3:** Scores user behavior. AI agents often get low trust scores.

**Approaches to solving CAPTCHAs:**

1. **Integrated platforms (Skyvern, Steel):** Most reliable for production. Handle CAPTCHAs as part of the automation workflow.
2. **Human-powered services (Anti-Captcha, 2Captcha):** High accuracy but create scalability bottlenecks ($1-3 per 1,000 solves).
3. **AI-only solutions (CapSolver, NopeCHA):** Work for standard image CAPTCHAs. Struggle with complex behavioral implementations.
4. **Local browser approach (Manus):** Bypasses CAPTCHAs entirely by using a real, trusted browser session. Not scalable.
5. **AWS Web Bot Auth (preview):** Amazon's approach to reducing CAPTCHAs for AI agents in AgentCore Browser.

### 4.4 Ethical Framework for Data Collection

**Recommended approach for Superextra:**

1. **Respect robots.txt** -- Check and honor robots.txt directives. Many delivery platforms explicitly disallow scraping of menu/price data.
2. **Rate limit aggressively** -- Even if technically capable of faster collection, throttle to 1-2 requests per second per target site.
3. **Don't circumvent authentication** -- Only collect publicly viewable data (menus/prices visible without login).
4. **Use managed services where possible** -- Apify, Grepsr, Bright Data handle legal/ethical gray areas as part of their business model.
5. **Cache and minimize re-scraping** -- Don't hit the same pages repeatedly. Cache data and update on reasonable schedules (weekly for menus, daily for prices if needed).
6. **Clearly articulate purpose** -- Document why data is collected and how it is used. Stronger legal position in EU.

---

## 5. Recommendations for Superextra

### For restaurant data extraction from delivery platforms (Wolt, Pyszne.pl, Glovo, Uber Eats):

**Option A: Managed services (lowest risk, fastest time to value)**

- Use **Apify pre-built actors** for Uber Eats and Wolt ($100-500/month)
- Use **Grepsr** for managed menu data collection from remaining platforms
- Supplement with **Firecrawl** ($16+/month) for restaurant website scraping
- Total: $200-1,000/month. Handles anti-bot, proxies, maintenance.

**Option B: Self-built with AI browser agents (more control, higher effort)**

- **Crawl4AI** (free) for bulk extraction from restaurant websites, review sites, and simple pages
- **Browser Use** (free) + **Browserbase** ($99/month) for complex multi-step delivery platform navigation
- **Skyvern Cloud** ($149/month) for platforms with strong anti-bot (Pyszne.pl/Cloudflare)
- Add **AgentQL** ($99/month) for reliable semantic extraction across changing site layouts
- Total: $350-500/month + LLM API costs (~$50-200/month depending on volume)

**Option C: Hybrid (recommended)**

- **Apify actors** for platforms where pre-built scrapers exist (Uber Eats, Wolt)
- **Skyvern Cloud** for platforms needing anti-bot handling (Pyszne.pl, Glovo)
- **Crawl4AI** for restaurant website and review data extraction
- **Browser Use** for ad-hoc research tasks and complex workflows
- Total: $300-700/month + LLM costs

### What NOT to use for data extraction:

- **Anthropic Computer Use / OpenAI CUA** -- Too expensive per action for high-volume data extraction. Better for one-off complex tasks.
- **Google Mariner** -- Not available as developer API. Consumer-only.
- **Manus** -- Local browser, not scalable. Good for manual research but not automated pipelines.
- **ChatGPT Atlas / Perplexity Comet** -- Consumer browsers, not programmable for data pipelines.

---

## Sources

### General Comparisons

- [11 Best AI Browser Agents in 2026 -- Firecrawl](https://www.firecrawl.dev/blog/best-browser-agents)
- [The Agentic Browser Landscape in 2026 -- No Hacks](https://nohacks.co/blog/agentic-browser-landscape-2026)
- [Top 10 Browser AI Agents 2026 -- O-Mega](https://o-mega.ai/articles/top-10-browser-use-agents-full-review-2026)
- [10 Best Agentic Browsers for AI Automation in 2026 -- Bright Data](https://brightdata.com/blog/ai/best-agent-browsers)
- [Stagehand vs Browser Use vs Playwright Compared 2026 -- NxCode](https://www.nxcode.io/resources/news/stagehand-vs-browser-use-vs-playwright-ai-browser-automation-2026)

### Individual Tools

- [Browser Use GitHub](https://github.com/browser-use/browser-use)
- [Browser Use Cloud Pricing](https://browser-use.com/pricing)
- [Stagehand GitHub](https://github.com/browserbase/stagehand)
- [Browserbase Pricing](https://www.browserbase.com/pricing)
- [Skyvern GitHub](https://github.com/Skyvern-AI/skyvern)
- [Skyvern Pricing](https://www.skyvern.com/pricing)
- [AgentQL Pricing](https://www.agentql.com/pricing)
- [AgentQL GitHub](https://github.com/tinyfish-io/agentql)
- [Crawl4AI GitHub](https://github.com/unclecode/crawl4ai)
- [Steel GitHub](https://github.com/steel-dev/steel-browser)
- [Microsoft Playwright MCP GitHub](https://github.com/microsoft/playwright-mcp)
- [Amazon Nova Act GitHub](https://github.com/aws/nova-act)
- [Amazon Nova Act -- AWS](https://aws.amazon.com/nova/act/)
- [Firecrawl](https://www.firecrawl.dev/)

### Anthropic / OpenAI / Google

- [Anthropic Computer Use Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
- [OpenAI Computer Use Guide](https://developers.openai.com/api/docs/guides/tools-computer-use)
- [OpenAI CUA Sample App](https://github.com/openai/openai-cua-sample-app)
- [Google Project Mariner](https://deepmind.google/models/project-mariner/)
- [Manus Browser Operator](https://manus.im/blog/manus-browser-operator)

### Legal / Ethical

- [Is Web Scraping Legal? 2026 -- AIMultiple](https://research.aimultiple.com/is-web-scraping-legal/)
- [Ethical AI Scraping in 2026 -- Use Apify](https://use-apify.com/blog/web-scraping-legal-landscape-2026)
- [Is Web Scraping Legal in 2026? -- Rayobyte](https://rayobyte.com/blog/is-web-scraping-legal-2026)

### CAPTCHA / Anti-Bot

- [2026 Guide to CAPTCHA Systems for AI Agents -- CapSolver](https://www.capsolver.com/blog/web-scraping/2026-ai-agent-captcha)
- [hCaptcha Effectiveness Against Bots in 2026](https://www.hcaptcha.com/post/hcaptcha-captchas-are-highly-effective-against-bots-and-agents-in-2026)
- [AWS Web Bot Auth for AI Agents](https://aws.amazon.com/blogs/machine-learning/reduce-captchas-for-ai-agents-browsing-the-web-with-web-bot-auth-preview-in-amazon-bedrock-agentcore-browser/)

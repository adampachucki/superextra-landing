# Restaurant Data Acquisition Research

Research date: 2026-03-31 (updated with verified API findings). Focus: scalable data solutions for restaurant market intelligence in European markets (especially Poland). Infrastructure: Google Cloud (Vertex AI, BigQuery), EUR 120K credits.

---

## 1. Google's Own Data APIs

### Google Places API (New)

The most relevant first-party source. The "New" version (replacing legacy Places API) has rich restaurant-specific fields.

**Restaurant-relevant fields by billing tier (verified pricing per 1,000 calls at 0-100K volume):**

| Tier                    | Fields                                                                                                                                                                                                                                                                                                                                                | Per 1K calls (Details) | Per 1K calls (Text/Nearby Search) |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | --------------------------------- |
| Essentials              | place_id, address, location, types, addressComponents, formattedAddress, shortFormattedAddress, plusCode                                                                                                                                                                                                                                              | $5.00                  | $5.00 (IDs only)                  |
| Pro                     | displayName, businessStatus, primaryType, primaryTypeDisplayName, googleMapsUri, googleMapsLinks, timeZone, openingDate, accessibilityOptions                                                                                                                                                                                                         | $17.00                 | $32.00                            |
| Enterprise              | phone, website, rating, userRatingCount, reviews, openingHours, currentOpeningHours, secondaryOpeningHours, priceLevel, priceRange                                                                                                                                                                                                                    | $20.00                 | $35.00                            |
| Enterprise + Atmosphere | dineIn, takeout, delivery, curbsidePickup, reservable, servesBreakfast/Brunch/Lunch/Dinner, servesCoffee/Dessert/Beer/Wine/Cocktails, servesVegetarianFood, menuForChildren, outdoorSeating, liveMusic, goodForChildren/Groups/WatchingSports, allowsDogs, restroom, priceLevel, priceRange, parkingOptions, paymentOptions, photos, editorialSummary | $25.00 est.            | $40.00 est.                       |

**Volume discounts (verified):** Up to ~92% discount at 5M+ monthly requests. Example: Place Details Essentials drops from $5.00/1K to $0.38/1K at 5M+ volume. Essentials tier includes 10,000 free events monthly for most services.

**Key limitations:**

- Text Search returns max 60 results per query (3 pages of 20)
- Nearby Search returns max 20 results per request, radius max 50km
- No bulk download or export mechanism -- must be queried record by record
- No menu text/items (only flags like servesBreakfast, not actual menu data)
- Reviews returned are "most recent" -- no way to get all reviews
- Google ToS prohibit storing/caching responses beyond session use (enforcement varies)

**Subscription plans (as of March 2025):**

- Starter: $100/mo (50K calls)
- Essentials: $275/mo (100K calls)
- Pro: $1,200/mo (250K calls)

**Cost estimate for restaurant coverage:**

- 100K restaurants in Poland via Text Search Enterprise+Atmosphere: ~$4,000 (100K \* $0.040)
- Getting full details on each: ~$2,500 additional (100K \* $0.025)
- Total initial sweep: ~$6,500
- Monthly refresh of 100K records: same cost

**What you get:** Name, address, coordinates, phone, website, rating, review count, opening hours, price level, dining attributes (dine-in/takeout/delivery), cuisine indicators, photos. No actual menu items or prices.

**What you DON'T get (verified):** Actual menu text, dish prices, competitor delivery platform presence, social media metrics, review sentiment analysis, full review history. Also NOT available via API but visible on Google Maps website: **popular times** (hourly foot traffic patterns), **live busyness** (real-time crowding), **wait times**, **time spent** (average visit duration).

**Popular times workaround:** The `populartimes` Python library (github.com/m-wrzr/populartimes) extracts these fields by leveraging the Places Web Service in a non-standard way. Returns hourly popularity scores (0-100 scale), weekly patterns by day/hour, wait times in minutes, time spent ranges (e.g., 90-180 min), and current popularity snapshots. Supports multi-threading for batch requests. Uses place type + coordinate filtering to discover locations. Note: This library may be fragile as Google frequently updates Maps internals.

### Google Maps Datasets API

For uploading and managing your OWN geospatial datasets in Cloud Console, used with data-driven map styling. Not a data source -- it's a storage/visualization tool for data you already have.

### BigQuery Public Datasets

No restaurant-specific public datasets found in BigQuery. Useful adjacent datasets: US Census (demographics), geographic boundaries, weather data. Nothing for European restaurant markets specifically.

---

## 2. Restaurant Data Aggregators / Providers

### Foursquare Places

**What:** 100M+ POIs across 200+ countries. Strong restaurant/venue data from their consumer app history.

**Data fields:** Name, categories, address, coordinates, phone, email, website, hours, rating, popularity score, photos, menu URL, price tier (1-4), tips/reviews, social media handles (Facebook, Instagram, Twitter).

**Access methods:**

- Places API (search, details, autocomplete, photos, tips)
- Bulk data licensing (enterprise)
- Data contributed to Overture Maps Foundation

**Pricing:** Free developer tier available. Paid tiers not publicly listed (contact sales). The API returns richer social/engagement data than Google Places.

**European coverage:** 200+ countries. Foursquare/Swarm was popular in Europe but user-generated data quality varies by market. Poland coverage exists but is thinner than US/UK.

**Advantage over Google:** Social media handles, menu URLs, tips/reviews from Foursquare users, popularity scores. Can supplement Google data.

### SafeGraph (now part of Dewey)

**What:** Global POI data with verified place polygons, brand affiliations, open/close status, store IDs.

**Coverage:** Global, including Europe. Used by Clear Channel Europe.

**Data:** Location data, foot traffic patterns, building geometries. More focused on location analytics than restaurant-specific attributes.

**Pricing:** Enterprise only, contact for quotes.

### Datarade Marketplace Providers

Datarade lists these restaurant data sellers:

| Provider                           | Data Type                                           | Coverage                         | Pricing           |
| ---------------------------------- | --------------------------------------------------- | -------------------------------- | ----------------- |
| **Istari.AI**                      | 40M+ company profiles, 40+ attributes, POI data     | 250+ countries incl. Germany, UK | Contact sales     |
| **Xverum**                         | 230M+ global POIs, 5000+ categories                 | 250+ countries                   | $1,800-2,000/mo   |
| **Grepsr**                         | Restaurant menu data, 99% accuracy, custom datasets | Global                           | Contact sales     |
| **SafeGraph**                      | Restaurant POIs                                     | Global                           | Contact sales     |
| **Michelin Mobility Intelligence** | Hospitality/dining POIs                             | 50+ countries                    | Contact sales     |
| **Xtract**                         | Fast food/QSR locations                             | USA/Canada only                  | $868/purchase     |
| **GapMaps**                        | Retail precincts with restaurants                   | APAC/Middle East                 | From $50/precinct |

**Best fit for Superextra:** Grepsr (menu data focus), Istari.AI (European coverage), Xverum (broad POI coverage with reasonable pricing).

### Dataprovider.com

**What:** Indexes 350M+ domains monthly. REST API with 200+ structured fields per domain.

**Relevant for:** Finding restaurant websites, detecting technology stacks, classifying businesses by category.

**European coverage:** Netherlands-based, strong EU coverage (14M+ EU business domains analyzed), GDPR-compliant.

**Pricing:** Contact for demo/quotes. Could be useful for discovering restaurant digital presence at scale.

---

## 3. Web Scraping Platforms (Managed/Cloud)

### Apify

**What:** Cloud scraping platform with 22,000+ pre-built "actors" (scrapers).

**Restaurant-relevant actors (known to exist):**

- Google Maps Scraper (compass/google-maps-scraper) -- extracts business data, reviews, photos from Google Maps
- TripAdvisor scrapers -- restaurant details, reviews, ratings
- Uber Eats scrapers -- menus, prices, restaurant listings
- Instagram scrapers -- posts, engagement, follower data
- TikTok scrapers -- video data, engagement metrics
- Yelp scrapers -- business details, reviews

**Pricing model:** Compute-unit based. Plans range from Free tier to Enterprise. Actors consume compute units based on CPU/memory/time used. Typical Google Maps scraper costs roughly $1-5 per 1,000 results depending on data depth.

**Key advantage:** Pre-built scrapers for most restaurant data sources. No need to build custom scrapers. Can export to BigQuery via integrations.

**Limitation:** JS-rendered site content was hard to verify from their storefront -- best to test specific actors directly.

### Bright Data

**What:** Major data collection platform. Proxy network + Web Scraper API + pre-built datasets.

**Products relevant to restaurants:**

- **Web Scraper API:** Pre-configured for 38+ targets, handles anti-bot measures
- **SERP API:** Google search/maps results
- **Datasets marketplace:** Pre-collected datasets (Google Maps, TripAdvisor, Yelp, etc.)
- **Proxy network:** 72M+ IPs for custom scraping

**Pricing:** Site was unreachable during research (ECONNREFUSED). Known to offer dataset pricing per record ($0.001-0.01/record typical) and API pricing per request.

**Note:** Bright Data acquired Import.io. Their combined platform offers AI-powered extraction with self-healing scrapers.

### Oxylabs

**What:** Web scraping infrastructure with pre-configured targets.

**Pricing:**

- Micro: $49/mo (98K results)
- Starter: $99/mo (220K results)
- Advanced: $249/mo (622K results)
- JS rendering: +$1.25-1.35 per 1,000 results

**Cost per 1K results:** $0.40-0.50 base + $1.25 for JS rendering

**Good for:** General-purpose scraping of any restaurant site. No restaurant-specific pre-built scrapers mentioned, but universal scraper works on any URL.

### ScrapFly

**What:** Scraping API with AI-powered extraction.

**Pricing:**

- Free: 1,000 credits
- Discovery: $30/mo (200K credits)
- Pro: $100/mo (1M credits)
- Startup: $250/mo (2.5M credits)
- Enterprise: $500/mo (5.5M credits)

**Credit multipliers:** Browser rendering = 5x credits, residential proxy = 25x credits per request.

**Pre-built scrapers:** Amazon, eBay, Booking.com, Instagram, LinkedIn, 40+ others on GitHub.

**Extraction API:** AI/LLM-based extraction with pre-built models for reviews, products, articles. Can create custom templates.

**Advantage:** LLM integration (LlamaIndex, LangChain) for structured extraction from unstructured pages.

### SerpAPI

**What:** Google search results API including Google Maps.

**Google Maps data:** Business names, addresses, GPS coordinates, ratings, review counts, hours, phone, website, service options (dine-in/takeout/delivery), price ranges, photos.

**Pricing:**

- Free: 250 searches/mo
- Starter: $25/mo (1K searches)
- Developer: $75/mo (5K searches)
- Production: $150/mo (15K searches)
- Big Data: $275/mo (30K searches)
- Enterprise: Custom

**Cost per search:** $0.009-0.025 depending on tier. Each search returns up to ~20 results.

**Good for:** Structured Google Maps data at moderate scale. Cheaper than direct Google Places API for basic listing data.

### Zenserp

**What:** SERP + Google Maps API.

**Pricing:**

- Free: 50 searches
- Small: $49.99/mo (25K searches)
- Large: $299.99/mo (250K searches)
- Enterprise: $899.99/mo (1M searches)

20% discount on annual plans.

### Crawlbase

**What:** Scraping API with pay-per-success model.

**Features:** TripAdvisor support mentioned specifically. 140M residential + 98M datacenter proxies. CAPTCHA handling.

**Pricing:** Pay per success (not per attempt). 1,000 free requests to start.

### Crawlee (Self-Hosted Scraping Framework)

**What:** Open-source Node.js/TypeScript library by Apify for building web scrapers and browser automation. Available on npm.

**Key features (verified):**

- Unified interface for HTTP and headless browser crawling (Playwright + Puppeteer)
- Anti-detection: automatic browser-like headers, TLS fingerprint replication, human-like fingerprint generation
- HTTP/2 support with zero configuration
- Fast HTML parsers (Cheerio, JSDOM) for server-rendered content
- JSON API scraping capabilities (useful for Wolt consumer API, etc.)
- Persistent URL queue (breadth-first and depth-first)
- Integrated proxy rotation and session management
- Pluggable storage for datasets and files
- Automatic resource scaling based on available system resources

**Architecture for restaurant scraping:**

1. `PlaywrightCrawler` for JS-rendered sites (Glovo, Instagram)
2. `CheerioCrawler` for server-rendered sites (Pyszne.pl)
3. `HttpCrawler` for direct API scraping (Wolt consumer API)
4. `enqueueLinks()` for pagination traversal
5. `Dataset` API for structured data storage
6. Export to BigQuery via Cloud Functions

**Cost:** Free (open source, MIT license). Self-hosted on Cloud Run or GCE. Only compute costs.

**When to use over Apify:** When you need full control over scraping logic, want to avoid per-compute-unit billing, or need to run scrapers inside your own infrastructure for compliance reasons. Apify platform is built on top of Crawlee.

### Octoparse

**What:** No-code scraping platform with cloud execution.

**Features:** Pre-built templates including Google Maps. Can extract "food review from a map application" -- title, description, coordinates. 24/7 cloud execution with IP rotation.

**Pricing:** Standard (100 tasks), Professional (250 tasks), Enterprise (custom). Specific costs not publicly listed.

---

## 4. Review Data APIs

### TripAdvisor Content API

**Endpoints (verified):**

1. **Location Search** — `GET /api/v1/location/search?searchQuery={query}&key={key}`
   - Parameters: searchQuery (required), category (hotels/attractions/restaurants/geos), phone, address, latLong, radius, radiusUnit (km/mi/m), language
   - Returns: up to 10 locations with location_id, name, distance, bearing, address_obj
2. **Nearby Location Search** — coordinate-based discovery
3. **Location Details** — `GET /api/v1/location/{locationId}/details?key={key}`
   - Returns: location_id, name, description, web_url, email, phone, website, latitude, longitude, timezone, rating, rating_image_url, num_reviews, review_rating_count (by level), subratings, price_level, hours (ISO 8601 with weekday_text), cuisine (name/localized_name pairs), features, category, subcategory, groups, ranking_data (Popularity Index), trip_types breakdown, awards, ancestors (geo hierarchy), photo_count
4. **Location Reviews** — up to 5 reviews per location
5. **Location Photos** — up to 5 photos per location

**Authentication:** API key passed as query parameter `?key=YOUR_API_KEY`.

**Rate limits:** Up to 50 calls/second.

**Pricing:** Pay-per-use, monthly subscription, cancel anytime. Daily spend limits configurable. Specific per-call pricing not publicly listed.

**Restaurant-specific data (verified):** cuisine types, features array, price_level (localized currency symbols), ranking data (Popularity Index), trip_types breakdown, awards with images, subratings (food, service, value, atmosphere).

**Limitation:** Only 5 reviews and 5 photos per location. No menu or pricing data. But provides TripAdvisor rating + review snippets + restaurant-specific attributes.

**Coverage:** Global including Europe/Poland. TripAdvisor is widely used in European restaurant discovery.

### Yelp Fusion API (Yelp Places)

**Endpoints:**

- Business Search (keyword, category, location, price level)
- Business Details (name, address, phone, photos, rating, price, hours)
- Reviews (up to 3 review excerpts per business)
- Transaction Search (delivery-enabled businesses)
- Business Match (match external data to Yelp listings)

**Data returned:** Name, address, phone, photos, rating, price levels (1-4), hours, coordinates, review count, up to 3 review excerpts with ratings.

**Limitations:** Only 3 review excerpts per business. Commercial use requires "Yelp Places Enterprise" approval.

**European coverage:** Yelp has presence in Europe but is much weaker than in the US. Poland coverage is minimal compared to Google/TripAdvisor.

### Reputation.com

**What:** Reputation management platform with review aggregation.

**Features:** Review monitoring across platforms, AI-powered Q&A from review data ("Reputation IQ"), competitive benchmarking, local SEO.

**Restaurant support:** Explicit "Food & Beverage" industry solution.

**Pricing:** Enterprise only, not publicly listed.

**Use case:** More of an ongoing reputation management tool than a bulk data source. Could complement scraped data with ongoing monitoring.

### ReviewTrackers

**What:** Multi-platform review monitoring.

**Features:** Review aggregation, competitor analysis, local SEO, social media monitoring.

**Pricing:** Not publicly available.

### Birdeye

**What:** Review management platform for multi-location brands.

**Features:** Review aggregation from multiple platforms, listing management, competitive benchmarking. 200K+ businesses served.

**Restaurant support:** Listed as a supported industry.

**Limitation:** Designed as a SaaS tool for businesses managing their own reviews, not as a data provider for third-party intelligence.

---

## 5. Delivery Platform Data

### Official APIs

**Uber Eats:** No public consumer API for restaurant discovery/menu data. The Uber Eats Marketplace APIs (Menu API, Store API, Order API, Promotions/Reporting) exist but require written approval from Uber and are designed for POS integration partners, menu management platforms, and restaurant partners -- not for third-party data extraction. Endpoints like `GET /eats/stores/{store_id}/menus` are partner-only.

**Wolt:** No public data API. Wolt (now DoorDash in many markets) does not offer third-party data access.

**Pyszne.pl (Takeaway/Just Eat):** No public API for menu/restaurant data. Just Eat Takeaway has developer tools for restaurant partners only, not for data extraction.

**Glovo:** No public data API. Partner APIs exist only for active restaurant partners.

### Scraping Delivery Platforms

This is the only realistic path for delivery platform data:

**Apify actors:** Known to have Uber Eats scrapers that extract menus, prices, restaurant details, delivery fees, ratings.

**Custom scraping:** Delivery platforms (Wolt, Pyszne.pl, Glovo) have relatively structured web frontends that can be scraped with general-purpose tools (Oxylabs, ScrapFly, etc.).

**Data available through scraping:**

- Restaurant names, addresses, delivery zones
- Full menus with item names, descriptions, prices
- Photos of menu items
- Delivery fees, minimum order amounts
- Ratings and review counts
- Operating hours and delivery times
- Promotions and discounts

**Legal/ethical note:** Scraping delivery platforms likely violates their ToS. The data is publicly viewable but bulk extraction may face legal challenges, especially in the EU under GDPR for any personal data. Restaurant business data (menus, prices) is generally less sensitive.

**Grepsr** (from Datarade): Explicitly advertises "Restaurant and Food Menu Data" with 99% accuracy. This is likely a managed scraping service that handles delivery platform extraction as a service.

---

## 6. Social Media Data

### Instagram

**Official API (Instagram Graph API):**

- Requires Business or Creator account connection
- Can access: posts, comments, insights (engagement, reach), follower demographics
- Rate limits: Varies by endpoint
- Limitation: Can only access data for accounts YOU manage, or public content via specific endpoints
- Not suitable for monitoring competitor restaurant accounts at scale

**Third-party options:**

- **Apify Instagram Scraper:** Can extract public profile data, posts, engagement, hashtag data
- **ScrapFly:** Pre-built Instagram scraper
- **PhantomBuster:** Social media automation tools (requires JS-enabled access, couldn't verify pricing -- plans typically $56-320/mo)

**Data available via scraping:**

- Post count, follower/following counts
- Public posts with captions, likes, comments
- Hashtag usage and engagement
- Posting frequency and timing

### TikTok

**Official TikTok Research API:**

- Restricted to academic institutions and non-profits in US, EEA, UK, Switzerland
- Requires 4-week approval process
- Not available for commercial use
- Data accessed through Virtual Compute Environment (cannot export freely)

**Third-party options:**

- **Apify TikTok Scraper:** Public video data, engagement metrics, profile info
- General scraping tools can extract public TikTok data

**Data available via scraping:**

- Video views, likes, comments, shares
- Profile follower counts
- Hashtag performance
- Content themes and posting patterns

### Social Media Intelligence Platforms

**Emplifi (formerly Socialbakers):** Social media analytics across Instagram, TikTok, Facebook, YouTube. Benchmarking, competitive analysis. Enterprise pricing.

**Reputation.com:** Includes social media monitoring in their platform.

**Note:** These are expensive enterprise SaaS tools. For Superextra's use case, Apify scrapers for Instagram/TikTok data are likely more cost-effective and provide raw data that can feed into BigQuery.

---

## 7. Alternative / Open Data Approaches

### Overture Maps Foundation

**What:** Linux Foundation project building open map data. Major contributors: Meta (~58.8M places), Foursquare (~6.5M), AllThePlaces (~1.65M), Microsoft, and others.

**Places data:** 64M+ POIs globally. Includes: name, categories, address, coordinates, phone, website, social media, hours, operating status, confidence scores.

**Restaurant data:** Includes restaurant categories. Documentation shows examples of conflating Overture data with OpenStreetMap to enrich restaurant records.

**Data access:** Free. Available on AWS S3 and Azure Blob Storage in GeoParquet format. Can query with DuckDB, Python client, or import into BigQuery.

**Licensing:** CDLA-Permissive-2.0 (most sources) or CC0 (AllThePlaces). Free for commercial use.

**European coverage:** Global coverage. Meta's contribution (58.8M features) provides strong baseline but quality varies by region.

**Limitation:** No reviews, ratings, menus, or pricing data. Just basic POI information. Good for building the initial restaurant universe/registry.

### OpenStreetMap (OSM)

**Restaurant tags:** amenity=restaurant, amenity=cafe, amenity=fast_food, amenity=bar, amenity=pub.

**Available fields:** name, cuisine, diet:_ (vegetarian/vegan), opening_hours, phone, website, addr:_, wheelchair, payment:\*.

**Access:** Free via Overpass Turbo API, bulk Planet file, or regional extracts (Geofabrik). Can import into BigQuery.

**European coverage:** Strong in Europe, especially Germany, France, UK. Poland coverage is moderate -- major cities well mapped, rural areas less complete.

**Licensing:** ODbL (share-alike, attribution required).

**Limitation:** Volunteer-maintained data -- inconsistent completeness. No reviews, ratings, photos, menus, or prices. But excellent for basic restaurant universe in Europe.

### AllThePlaces

**What:** Open-source project running 4,100+ web scrapers to collect POI data from business websites worldwide.

**Output:** 20M+ locations in GeoJSON/NDJSON format. Updated weekly.

**Licensing:** CC0 (data), MIT (code). Completely free.

**Relevance:** Good for chain restaurant locations. Scrapers target brand websites (McDonald's, Starbucks, etc.) and aggregate locations. Less useful for independent restaurants.

**Data feeds into Overture Maps as a source.**

### Eurostat / National Statistics

**Eurostat Structural Business Statistics:** NACE code I (Accommodation and Food Service Activities) provides aggregate statistics: number of enterprises, employment, turnover by country. Useful for market sizing but not individual restaurant data.

**Polish GUS (Central Statistical Office):** Publishes food service sector statistics. Aggregate data only -- not individual restaurant listings.

### European Business Registries

**Poland (KRS/CEIDG):** Business registration data is publicly available. Could be filtered by NACE/PKD codes for restaurant businesses to build a restaurant universe.

**EU Open Data Portal (data.europa.eu):** 1.78M+ datasets across 36 countries. No restaurant-specific datasets found on homepage, but searchable for business registry data by country.

---

## Recommended Architecture

Given the research findings, here is a proposed data acquisition stack:

### Layer 1: Restaurant Universe (WHO exists)

Build the base registry of restaurant entities:

- **Overture Maps** (free, 64M POIs) -- bulk download, import to BigQuery
- **OpenStreetMap** (free, good EU coverage) -- enrich with cuisine/diet tags
- **Google Places Text Search** (~$4K per 100K restaurants) -- fill gaps, get place_ids
- **Polish business registry (CEIDG/KRS)** -- official business data for Poland

### Layer 2: Rich Restaurant Profiles (WHAT they offer)

- **Google Places Details Enterprise+Atmosphere** ($0.025/request) -- ratings, reviews, hours, dining attributes, photos
- **Foursquare Places API** -- social media handles, menu URLs, popularity, tips
- **TripAdvisor Content API** -- TripAdvisor ratings, reviews, photos

### Layer 3: Menu & Pricing Data (HOW MUCH)

- **Grepsr** (managed service) -- custom menu data collection from delivery platforms
- **Apify actors** -- Uber Eats, Wolt, Pyszne.pl, Glovo scrapers for menus + prices
- Alternatively: **Oxylabs/ScrapFly** for self-managed scraping of delivery platforms

### Layer 4: Competitive Intelligence (HOW they perform)

- **Google Places reviews** (via API) -- review text, ratings
- **TripAdvisor reviews** (via Content API) -- up to 5 reviews per location
- **Apify scrapers** -- for deeper review collection from Google, TripAdvisor
- **Instagram/TikTok scrapers** (Apify) -- social media presence and engagement

### Layer 5: Ongoing Monitoring

- **SerpAPI or Zenserp** ($150-300/mo) -- periodic Google Maps monitoring
- **Apify scheduled runs** -- refresh delivery platform data weekly/monthly
- **Reputation.com or Birdeye** -- if real-time review monitoring needed (expensive)

### Data Pipeline: Everything into BigQuery

All sources feed into BigQuery via:

- Direct BigQuery connectors (Google Places API results)
- Cloud Functions processing API responses
- Apify webhook integrations -> Cloud Functions -> BigQuery
- GCS staging for bulk imports (Overture Maps GeoParquet -> BigQuery)
- Vertex AI Search for semantic search across restaurant data

---

## Cost Estimates (Monthly, Poland Market Focus)

| Source                              | Estimated Monthly Cost | Data Volume                |
| ----------------------------------- | ---------------------- | -------------------------- |
| Google Places API (initial sweep)   | $6,500 one-time        | 100K restaurants           |
| Google Places API (monthly refresh) | $2,000-3,000           | 100K records               |
| Apify (scraping actors)             | $100-500               | Delivery platforms, social |
| SerpAPI or Zenserp                  | $150-300               | Monitoring searches        |
| TripAdvisor Content API             | Pay-per-use            | 100K lookups               |
| Foursquare Places API               | Contact for pricing    | 100K lookups               |
| Overture Maps + OSM                 | Free                   | Full universe              |
| Grepsr (managed menu data)          | Contact for quotes     | Custom                     |
| **Total estimated**                 | **$3,000-6,000/mo**    | After initial setup        |

All well within EUR 120K annual budget, with room for scaling to other European markets.

---

## Key Decisions Needed

1. **Build vs. buy for delivery platform data:** Apify pre-built actors ($100-500/mo) vs. Grepsr managed service (likely $1-5K/mo but higher quality/reliability)

2. **Google Places vs. Foursquare as primary POI source:** Google is more comprehensive but more expensive. Foursquare provides social handles and menu URLs that Google doesn't. Consider using both.

3. **Review depth:** Google/TripAdvisor APIs give limited reviews (5 max). For full review corpus, need scraping (Apify, Bright Data). Decide if sentiment analysis needs full review text or just ratings.

4. **Social media monitoring scope:** Instagram/TikTok scraping is legally grey. Start with Apify actors for top competitor accounts, scale if value proven.

5. **Data freshness requirements:** Daily (delivery prices), weekly (reviews/ratings), monthly (basic listings), or quarterly (market structure)?

---

## 8. Polish Government Data APIs (Deep Dive)

Research date: 2026-03-31.

### CEIDG (Central Registration and Information on Business)

The primary registry for sole proprietorships (jednoosobowa dzialalnosc gospodarcza) in Poland. Most independent restaurants are registered here, not in KRS.

**API versions:**

- **Legacy SOAP API** (datastore.ceidg.gov.pl) — deprecated, scheduled end-of-life was September 2021. Uses WCF/SOAP protocol. Still referenced in older docs but should not be used for new integrations.
- **Data Warehouse REST API v2** (dane.biznes.gov.pl) — current production API. JSON-based REST.
- **Data Warehouse REST API v3** — newest version, endpoint: `GET /api/ceidg/v3/firmy`

**Base URLs:**

- Production: `https://dane.biznes.gov.pl/api/ceidg/v3/firmy`
- Test: `https://test-dane.biznes.gov.pl/api/ceidg/v3/firmy`

**Access:** Free under Creative Commons Attribution 3.0 Poland license. Registration required via Trusted Profile (Profil Zaufany) at https://biznes.gov.pl/pl/e-uslugi/00_9999_00. Documentation at https://akademia.biznes.gov.pl/hurtownia-danych-instrukcje-i-dokumentacja/

**PKD codes for restaurant businesses (PKD 2025, effective January 2025):**

- `56.11.Z` — Restauracje (Restaurants) — replaces old 56.10.A
- `56.12.Z` — Ruchome placowki gastronomiczne (Mobile food establishments) — replaces old 56.10.B
- `56.21.Z` — Catering (Event catering)
- `56.29.Z` — Pozostala uslugowa dzialalnosc gastronomiczna (Other food service)
- `56.30.Z` — Przygotowywanie i podawanie napojow (Bars/beverage service)

Note: Existing businesses have until December 31, 2026 to update from old PKD 2007 codes to PKD 2025. During transition, both code systems coexist.

**Data fields available:** Business name, NIP (tax ID), REGON, address, registration date, status (active/suspended/closed), PKD codes (primary and secondary), owner name.

**Data Warehouse portal (verified):** The dane.biznes.gov.pl portal explicitly offers data download/browsing, statistics, and reports on businesses registered in CEIDG. Portal confirms existence of "Instrukcje dla uzytkownikow i dokumentacja API" (user instructions and API documentation). Access requires registration via Trusted Profile (Profil Zaufany) and acceptance of data protection terms. Data is published under Creative Commons Attribution 3.0 Poland license.

**Limitation:** The API documentation is gated behind Trusted Profile authentication, so exact endpoint specifications could not be verified without registration. May require downloading bulk data and filtering locally by PKD code, or using the Apify CEIDG Scraper which extracts data from the biznes.gov.pl web interface. The legacy SOAP API (datastore.ceidg.gov.pl) timed out during testing and appears non-functional.

### KRS (National Court Register) Open API

KRS covers legal entities: sp. z o.o. (LLC), spolka akcyjna (joint stock), etc. Larger restaurant groups and chains register here.

**Official Open API:** Available at https://prs.ms.gov.pl/krs/openApi

**Format:** RESTful API returning JSON. Scope matches complete and current KRS excerpts.

**Verified working endpoint (tested):**

```
GET https://api-krs.ms.gov.pl/api/krs/OdpisPelny/{krsNumber}?rejestr=P&format=json
```

Example: `https://api-krs.ms.gov.pl/api/krs/OdpisPelny/0000019193?rejestr=P&format=json`

**Access:** Free, public. No authentication required. No API key needed.

**Verified JSON response structure:**

```
{
  "odpis": {
    "rodzaj": "Pelny",  // "Full" excerpt type
    "naglowekP": {
      "rejestr": "P",
      "numerKRS": "0000019193",
      "dataCzasOdpisu": "2026-03-31T...",
      "stanZDnia": "2026-03-31",
      "wpis": [...],  // array of registry entries with dates
      "stanPozycji": 205
    },
    "dane": {
      "dzial1": {
        "danePodmiotu": {
          // Legal form, REGON, NIP, company names, previous registrations
        },
        "siedzibaIAdres": {
          // Registered office, addresses, websites, emails
        },
        "jednostkiTerenoweOddzialy": [...],  // Branch offices
        "umowaStatut": {
          // Constitutional documents, amendments
        }
      }
    }
  }
}
```

**Data fields returned (verified):** Legal form (e.g., SPOLKA AKCYJNA), REGON, NIP, company name (multiple variants), registered office address, branch addresses, email, website, notarial act details, constitutional document amendments with dates, complete modification history (200+ entries for large companies).

**Limitation:** Lookup by KRS number only. Cannot search by PKD code, business name, or NIP directly. For discovery of restaurant entities, you'd need to cross-reference with REGON data or use a third-party provider.

**Third-party options for KRS data:**

- **Rejestr.io** (rejestr.io/api) — KRS data search with programmatic access. Returns 403 on direct API docs access; likely requires registration.
- **Transparent Data** (transparentdata.pl) — commercial API covering KRS, CEIDG, REGON. 99% SLA, ISO 27001. Supports search by NIP, KRS, REGON. Pricing: contact sales. Good option if official APIs prove too limited for discovery queries.

### GUS REGON / BIR1 (Central Statistical Office)

REGON is the statistical business register. Every Polish business entity has a REGON number. This registry contains PKD classification codes, making it the best source for finding all businesses of a specific type.

**API:** BIR1 (Baza Internetowa REGON) — SOAP/WCF web service at https://api.stat.gov.pl/Home/RegonApi

**Verified endpoint URLs:**

- Production: `https://wyszukiwarkaregon.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc`
- Sandbox: `https://wyszukiwarkaregontest.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc`

**Registration:** Email regon_bir@stat.gov.pl with:

- Entity name and REGON number
- Contact person details
- IP addresses for production access
- Estimated monthly query volume

**Authentication:** User Key provided after registration. Sandbox mode available with a built-in test key (returns real anonymized data).

**Cost:** Free.

**Verified SOAP operations:**

1. `Zaloguj` — authenticate with API key, returns session ID
2. `DaneSzukaj` — search by NIP, REGON, or KRS number
3. `DanePobierzPelnyRaport` — fetch full report for a specific entity

**Available report types (verified from source code):**

- Physical person (sole proprietor): `PublDaneRaportDzialalnoscFizycznejCeidg`, `PublDaneRaportDzialalnoscFizycznejRolnicza`, `PublDaneRaportDzialalnoscFizycznejPozostala`, `PublDaneRaportDzialalnoscFizycznejWKrupgn`, `PublDaneRaportLokalnaFizycznej`
- Legal entity: `PublDaneRaportDzialalnosciPrawnej`, `PublDaneRaportPrawna`, `PublDaneRaportLokalnaPrawnej`
- PKD classification: `PublDaneRaportDzialalnosciFizycznej`, `PublDaneRaportDzialalnosciPrawnej`

**Rate limits (verified, time-of-day dependent):**

- 8:00-16:59: 6,000/hour, 120/minute, 3/second
- 6:00-7:59 & 17:00-21:59: 8,000/hour, 150/minute, 3/second
- 22:00-5:59: 10,000/hour, 200/minute, 4/second

**Python library:** `gusregon` (pip install gusregon) — wraps BIR1 SOAP service. Provides `get_address()`, `get_pkd()`, and `search()` methods. Supports querying by NIP, REGON, or KRS.

**Search parameters:** NIP, REGON, or KRS numbers. Does not support bulk search by PKD code or business name. To find "all restaurants in Warsaw," you'd need to combine CEIDG/KRS data with REGON enrichment.

**Limitation:** Designed for lookup by identifier, not bulk discovery by business type. Cannot search "give me all businesses with PKD 56.11.Z" — must know the entity identifier first.

### Recommended approach for Polish business registry data

1. **Use CEIDG Data Warehouse API v3** to search for sole proprietorships with restaurant PKD codes (56.11.Z, 56.12.Z, etc.) — this covers the majority of independent restaurants
2. **Use Transparent Data API** as a fallback/enrichment source if CEIDG API search capabilities prove limited — they aggregate KRS, CEIDG, and REGON data into a single commercial API
3. **Use GUS BIR1** to enrich records with detailed REGON data (exact PKD codes, statistical classification)
4. **Use KRS Open API** to look up specific restaurant groups/chains by KRS number
5. **Apify CEIDG Scraper** as a pragmatic alternative if the official API is too restrictive for bulk discovery

---

## 9. Booking & Reservation Platforms

### Booksy

Polish-founded platform (originally for beauty services, expanding to restaurants).

**API:** Public REST API exists at https://alpha.docs.booksy.net/index.html (returned 401 — requires authentication to view docs).

**Authentication:** OAuth2 with access token (10h lifetime), refresh token (24h). Also supports password grant type.

**Access:** Requires partnership/registration. Not publicly documented for third-party data access.

**Apify option:** "Booksy Leads Scraper" available on Apify marketplace — extracts business data from Booksy listings.

**Relevance for Superextra:** Limited. Booksy is primarily beauty/wellness. Restaurant presence on Booksy is minimal compared to dedicated reservation platforms.

### OpenTable

Major restaurant reservation platform, primarily US/UK/Germany/Japan.

**API:** Affiliate API available at https://docs.opentable.com/

**Data available:** Restaurant info (address, postal code, aggregated rating, reviews, food types), reservation links.

**Access:** Requires affiliate partnership approval (3-4 week review). Designed for embedding reservation widgets, not bulk data extraction.

**Poland coverage:** Very limited. OpenTable has minimal presence in Poland.

**Alternative:** SerpAPI offers an OpenTable Reviews API for extracting review data.

### TheFork (TripAdvisor company)

Major European reservation platform. Strong in France, Italy, Spain, Belgium, Netherlands. Growing in Poland.

**Official B2B API:** https://docs.thefork.io/B2B-API/introduction

- Create/manage reservations
- Access customer data (allergies, preferences, seating)
- CRM integration capabilities
- Enterprise package includes full API access

**Data available via scraping (Apify):**

- Restaurant details, reviews, menus with prices, photos
- Ratings, Michelin stars, TripAdvisor scores
- Contact details, booking availability
- 100+ data fields per restaurant

**Apify actors:** "TheFork Restaurant Intelligence API" and "TheFork Scraper" available.

**Poland coverage:** Growing. TheFork is actively expanding in Central/Eastern Europe.

---

## 10. Delivery Platforms (Deep Dive on Polish Market)

### Pyszne.pl (Just Eat Takeaway)

The dominant food delivery platform in Poland.

**Official API:** Just Eat Takeaway Developer Portal at https://developers.just-eat.com/ — APIs are for restaurant PARTNERS only (order management, menu sync). No public data access API.

**Scraping approaches:**

- **Apify:** "Just Eat Restaurant Menu Scraper" — extracts menu items, prices, deals, variations, nutritional content in structured format
- **FoodSpark:** Dedicated Pyszne.pl/Just Eat API with real-time menu and pricing data
- **Crawlbase:** Pre-built Just Eat/Pyszne scraping support with TripAdvisor-specific mention
- **Custom scraping:** Pyszne.pl has a relatively structured frontend. Server-rendered content makes basic scraping feasible without heavy JS rendering.

**Data extractable:** Restaurant names, full menus with prices, delivery fees, minimum orders, ratings, operating hours, delivery zones, promotions.

### Uber Eats

Second-largest delivery platform in Poland.

**Official API:** Uber Direct API exists for delivery logistics only. No public API for restaurant/menu data.

**Apify actors (multiple available):**

- "Uber Eats Menu Scraper" by sian.agency — menus, prices, modifiers
- "UberEats Menu Scraper V2" with MCP server integration
- "Uber Eats Restaurant Scraper" — listing-level data
- "Uber Eats Scraper" by sovereigntaylor — restaurants, menus, prices
- Note: several Uber Eats scrapers have been deprecated over time; verify current status before committing

**Data extractable:** Restaurant listings, full menus with item names/descriptions/prices/modifiers, restaurant images, ratings, delivery fees, estimated delivery times. Supports filtering by cuisine type (13+ categories).

### Wolt (DoorDash)

Growing presence in Poland, especially in larger cities.

**Official Partner API:** Menu API exists at https://developer.wolt.com/docs/api/menu — for restaurant PARTNERS only (menu management). No public data access.

**Undocumented Consumer API (verified, working, no auth required):**

The Wolt consumer-facing API is publicly accessible without authentication. Verified endpoint:

```
GET https://consumer-api.wolt.com/v1/pages/restaurants?lat={lat}&lon={lon}
```

Example for Warsaw: `https://consumer-api.wolt.com/v1/pages/restaurants?lat=52.2297&lon=21.0122`

**Verified response fields per restaurant:**

- `name`, `id`, `slug`, `address`, `city`, `country` ("POL")
- `location`: [longitude, latitude] coordinates
- `online`: boolean (currently accepting orders)
- `delivers`: boolean
- `estimate_range`: delivery time (e.g., "20-30" minutes)
- `price_range`: 1-4 scale
- `rating`: object with `score` (e.g., 8.4/10), `volume` (review count), `rating`
- `currency`: "PLN"
- `tags`: array of cuisine types (e.g., ["american", "burger", "chicken"])
- `short_description`: text description
- `image`: URL with blurhash
- `venue_preview_items`: sample menu items with `name`, `price`, `currency`, `image`
- `filtering`: available filter categories

Response also includes `city_data` (metadata), `filtering` options, and `sections` grouping restaurants by category.

Note: The `restaurant-api.wolt.com` and `consumer-api.wolt.com` endpoints were discovered in the page source. The v1 restaurants endpoint works; older v3/v4 venue detail endpoints return 410 Gone.

**Apify:** "Wolt Restaurants Scraper" by lucen_data — extracts restaurant names, addresses, zip codes, phone numbers, ratings by city.

**Third-party services:**

- FoodSpark: Wolt API coverage
- DoubleData: Wolt data extraction
- Various managed scraping services (FoodDataScrape, WebDataCrawler, etc.)

**Data extractable:** Restaurant names, addresses, phone numbers, menus with prices, delivery fees, ratings, operating hours.

### Glovo

Active in Poland, especially for quick commerce.

**Official API:** Glovo Partners API at https://api-docs.glovoapp.com/partners/

- Order API (POS integration, order management)
- Stock & Price API (item availability, pricing updates)
- Menu validation endpoint
- All for PARTNERS only. No public data access.

**Undocumented consumer API:** Base URL `https://api.glovoapp.com` found in page source. However, the v3 stores endpoint returns "This endpoint is disabled for decommission" -- Glovo is actively shutting down older consumer API paths. The web app uses Next.js with client-side rendering, loading restaurant data dynamically via JS (not pre-rendered HTML). Scraping requires full browser rendering.

**Apify:** "Glovo Scraper" by antonionduarte.

**Third-party:** ScrapingBee has a dedicated Glovo Scraper API. DoubleData covers Glovo.

**Data extractable:** Restaurant listings, menus, prices, delivery fees, ratings. Requires browser-based scraping due to client-side rendering.

### Delivery Platform Data Aggregators

**FoodSpark** (foodspark.io):

- Covers: Pyszne.pl/Just Eat, Uber Eats, Wolt, Glovo, Deliveroo, and 10+ other platforms
- Data: menus, pricing, reviews, ratings, promotions, restaurant listings
- European coverage confirmed (Wolt, Just Eat, Deliveroo, Glovo listed)
- Pricing: "competitive" — contact for quotes. Free demo API available.
- Best fit if you want a single provider for all delivery platform data.

**DoubleData** (doubledata.com):

- Covers: Uber Eats, DoorDash, Glovo, Google Maps
- Data: real-time menu pricing, competitor promotions, delivery fees, market share analytics, cuisine categorization
- Intelligent cross-platform venue matching (deduplication)
- Pricing: Web scraping from $200, Dedicated scraping from $850, Data matching from $450, Custom datasets from $800
- "Any city" coverage claim.

---

## 11. Browser Automation Agents (Architecture for What APIs Cannot Cover)

### What data REQUIRES browser automation (no API available)

| Data Type                                    | Source                            | Why No API                        |
| -------------------------------------------- | --------------------------------- | --------------------------------- |
| Full delivery menus with prices              | Pyszne.pl, Uber Eats, Wolt, Glovo | Partner-only APIs                 |
| Competitor delivery fees & promotions        | All delivery platforms            | No public data access             |
| Full review text (beyond 3-5 snippets)       | Google Maps, TripAdvisor          | API limits to snippets            |
| Instagram engagement for restaurant accounts | Instagram                         | Graph API only for owned accounts |
| TheFork restaurant details & availability    | TheFork                           | B2B API for partners only         |
| Booksy listings                              | Booksy                            | Requires partner authentication   |
| Restaurant website menus/prices              | Individual restaurant sites       | No standard API                   |
| CEIDG bulk discovery by PKD code             | biznes.gov.pl                     | API may not support PKD search    |

### AI Browser Agent Landscape (2026)

Three tiers of tools have emerged:

**Tier 1: Agent Frameworks (the AI reasoning layer)**

| Framework        | Language   | Architecture                  | Key Feature                               | GitHub Stars |
| ---------------- | ---------- | ----------------------------- | ----------------------------------------- | ------------ |
| **Browser Use**  | Python     | Full LLM control of browser   | Model-agnostic, 89.1% WebVoyager score    | 78K+         |
| **Stagehand v3** | TypeScript | Hybrid: deterministic + AI    | 3 primitives: act(), extract(), observe() | Large        |
| **Skyvern**      | Python     | Computer vision + LLM         | Visual builder, form automation           | Growing      |
| **AgentQL**      | Python     | Query language for extraction | Structured data extraction focus          | Growing      |

**Tier 2: Cloud Browser Infrastructure (where agents run)**

| Service          | Pricing                 | Key Feature                                                 |
| ---------------- | ----------------------- | ----------------------------------------------------------- |
| **Browserbase**  | Free trial, $20-99/mo+  | Stagehand integration, 50M sessions in 2025, anti-detection |
| **Browserless**  | Free 1K units, $140/mo+ | BrowserQL (GraphQL-based), stealth-first                    |
| **Steel**        | Free (open source)      | Self-hosted option, REST API                                |
| **Hyperbrowser** | Various tiers           | Cloud browser instances                                     |

**Tier 3: Google's Own Option (Gemini Computer Use)**

Directly relevant since Superextra uses Vertex AI and has EUR 120K Gemini credits.

- **Model:** Gemini 3 Flash preview (only model supporting Computer Use during preview)
- **How it works:** Agentic loop of screenshot -> LLM analysis -> function call -> execute action -> new screenshot
- **12 supported actions:** click_at, hover_at, type_text_at, navigate, search, scroll_document, scroll_at, key_combination, go_back, go_forward, wait_5_seconds, drag_and_drop
- **Coordinate system:** Normalized 0-1000 grid mapped to actual pixels
- **Requires:** Playwright for screenshot capture and action execution
- **Safety:** Mandatory human-in-the-loop confirmation for flagged actions (CAPTCHA, form submissions)
- **Pricing:** Standard Gemini token pricing
- **Limitations:** Cannot bypass CAPTCHAs, preview-quality (may have errors), Python SDK only

**Advantage for Superextra:** Uses existing Gemini credits, runs on Vertex AI, integrates with existing agent architecture (ADK). Could be the browser automation layer for Phase 2/3 agents.

### Practical Architecture: Browser Agent Data Pipeline

```
                                    +------------------+
                                    |   Cloud Scheduler |
                                    |   (cron triggers) |
                                    +--------+---------+
                                             |
                                             v
+------------------+              +----------+----------+
|  API Data Layer  |              |    Pub/Sub Topic     |
|  (fast, reliable)|              |  "research-jobs"     |
|                  |              +----------+----------+
|  Google Places   |                         |
|  CEIDG/KRS APIs  |              +----------+----------+
|  TripAdvisor API |              |   Cloud Functions    |
|  Foursquare API  |              |   (job dispatcher)   |
+--------+---------+              +----------+----------+
         |                                   |
         |                        +----------+----------+
         |                        |    Browser Agent     |
         |                        |    Worker Pool       |
         |                        |                      |
         |                        |  Option A: Apify     |
         |                        |  Option B: Browserbase|
         |                        |    + Stagehand       |
         |                        |  Option C: Cloud Run |
         |                        |    + Gemini Computer |
         |                        |    Use + Playwright  |
         |                        +----------+----------+
         |                                   |
         +-------------------+---------------+
                             |
                             v
                    +--------+--------+
                    |    BigQuery     |
                    |  (unified data) |
                    +--------+--------+
                             |
                             v
                    +--------+--------+
                    | Vertex AI Search |
                    | (semantic index) |
                    +-----------------+
```

**Option A: Apify (recommended for Phase 2)**

- Pre-built actors for Pyszne.pl, Uber Eats, Wolt, Glovo, Instagram, Google Maps
- Webhook integration: Apify run completes -> webhook -> Cloud Function -> BigQuery
- Scheduled runs (daily/weekly) via Apify's built-in scheduler
- Cost: $49-499/mo depending on compute needs
- Advantage: fastest time to production, no infrastructure to manage
- Disadvantage: dependent on third-party actor maintenance (actors get deprecated)

**Option B: Browserbase + Stagehand (recommended for Phase 3)**

- Self-built TypeScript agents using Stagehand's act/extract/observe primitives
- Agents run on Browserbase cloud infrastructure (anti-detection, session management)
- Cloud Functions dispatch jobs via Pub/Sub -> Browserbase sessions
- Cost: Browserbase $20-99/mo + Cloud Functions compute
- Advantage: full control over extraction logic, resilient to site changes (AI adapts)
- Disadvantage: requires building and maintaining agent code

**Option C: Gemini Computer Use on Cloud Run (experimental)**

- Gemini 3 Flash as the browser agent brain
- Playwright running in Cloud Run containers for browser environment
- Uses existing EUR 120K Vertex AI credits
- Cloud Tasks or Pub/Sub for job queuing
- Cost: Gemini token costs only (covered by credits)
- Advantage: leverages existing Vertex AI investment, integrates with ADK agents
- Disadvantage: preview-quality, Python only, cannot bypass CAPTCHAs, mandatory human-in-the-loop for some actions

### Queue/Job Architecture for Long-Running Browser Tasks

Browser research tasks are inherently slow (30s-5min per site visit). Architecture must handle:

**Using Google Cloud native services:**

1. **Cloud Scheduler** triggers periodic research jobs (e.g., "refresh all Pyszne.pl data for Warsaw" every Tuesday)
2. **Pub/Sub** queues individual research tasks as messages (one message per restaurant per platform)
3. **Cloud Functions** (2nd gen) or **Cloud Run** picks up messages and dispatches to browser agents
4. **Cloud Tasks** provides retry logic, rate limiting, and deadline management for long-running browser operations

**Using BullMQ (verified architecture):**

- BullMQ on Redis/Memorystore for job queuing
- Worker processes running on Cloud Run (auto-scaling)
- Features: retries, rate limits, job delays, concurrency control, priority queues, LIFO/FIFO ordering
- **Flow pattern (verified):** BullMQ `FlowProducer` enables parent-child job trees — a parent job spawns multiple children and waits for ALL to complete before processing. Perfect for fan-out data acquisition:
  ```typescript
  const flow = await flowProducer.add({
    name: 'research-restaurant',
    queueName: 'parent-queue',
    data: { restaurantId: 'abc123' },
    children: [
      { name: 'scrape-pyszne', queueName: 'browser-queue', data: {...} },
      { name: 'scrape-wolt', queueName: 'browser-queue', data: {...} },
      { name: 'fetch-google-places', queueName: 'api-queue', data: {...} },
      { name: 'fetch-tripadvisor', queueName: 'api-queue', data: {...} }
    ]
  });
  // Parent aggregates results: const results = await job.getChildrenValues();
  ```
- Different queues for fast API calls vs slow browser tasks (different concurrency/rate limits)
- Polling-free design = minimal CPU usage during idle periods
- Dashboard via BullBoard for monitoring

**Using Temporal (alternative for complex orchestration):**

- Temporal workflows maintain durable state across hours-long executions
- If a worker crashes mid-research, another worker resumes from the last recorded event (deterministic replay)
- Child workflows enable fan-out: spawn parallel research workflows per platform
- Activities have configurable timeouts (e.g., `start_to_close_timeout=timedelta(hours=4)`)
- Better for complex multi-step research with conditional logic; overkill for simple scraping jobs
- Python SDK: `execute_child_workflow()` (wait for result) and `start_child_workflow()` (fire and forget)

**Job design for browser research:**

```
Job: research_restaurant_delivery
{
  restaurant_id: "abc123",
  restaurant_name: "Restauracja Pod Orlem",
  city: "Warszawa",
  platforms: ["pyszne", "uber_eats", "wolt", "glovo"],
  tasks: [
    "extract_menu_with_prices",
    "extract_delivery_fee",
    "extract_rating_and_reviews",
    "extract_promotions"
  ],
  priority: "normal",
  max_retries: 3,
  timeout_ms: 300000  // 5 minutes per platform
}
```

**Concurrency considerations:**

- Rate-limit browser sessions per platform (e.g., max 5 concurrent Pyszne.pl sessions)
- Stagger requests to avoid detection (random delays between 2-10 seconds)
- Use residential proxies for platforms with aggressive bot detection (Uber Eats, Wolt)
- Rotate user agents and browser fingerprints

---

## 12. Hybrid Approach: Combining APIs and Browser Agents

### Data Source Classification by Access Method

| Data Category             | API Sources (Fast, Reliable)                                                     | Browser Agent Sources (Slow, Comprehensive)             |
| ------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------- |
| **Restaurant universe**   | Google Places Text Search, Overture Maps (BigQuery), CEIDG API, GUS REGON        | CEIDG web portal (if API lacks PKD search)              |
| **Basic profiles**        | Google Places Details, Foursquare Places                                         | Restaurant websites (contact info, about)               |
| **Ratings & reviews**     | Google Places (5 reviews), TripAdvisor API (5 reviews), Yelp Fusion (3 excerpts) | Full review scraping via Apify/Browserbase              |
| **Menu & pricing**        | None available                                                                   | Pyszne.pl, Uber Eats, Wolt, Glovo, restaurant websites  |
| **Delivery intelligence** | None available                                                                   | Delivery fees, minimums, zones, ETAs from all platforms |
| **Social media**          | Instagram Graph API (owned accounts only)                                        | Instagram/TikTok/Facebook public profile scraping       |
| **Business registry**     | CEIDG v3, KRS Open API, GUS BIR1                                                 | Web portal scraping for bulk PKD discovery              |
| **Reservation data**      | TheFork B2B API (if partner), OpenTable affiliate                                | TheFork/Booksy public listing scraping                  |

### Recommended Phased Implementation

**Phase 1 (Month 1-2): API Foundation**
Build the restaurant universe using free/cheap API sources:

1. Import Overture Maps restaurant data for Poland into BigQuery (free, 64M+ POIs)
2. Enrich with Google Places Details for ratings, hours, contact info (~$6,500 for 100K restaurants)
3. Cross-reference with CEIDG API for business registration data (free)
4. Set up Foursquare Places API for social media handles and menu URLs
5. Connect TripAdvisor Content API for ratings and review snippets
   Total cost: ~$7,000 one-time + ongoing API costs

**Phase 2 (Month 2-4): Apify Scraping Layer**
Add data that APIs cannot provide:

1. Deploy Apify actors for Pyszne.pl, Uber Eats, Wolt, Glovo
2. Schedule weekly menu/pricing refreshes via Apify scheduler
3. Set up webhook -> Cloud Function -> BigQuery pipeline for scraped data
4. Add Instagram scraping for top restaurant accounts
5. Build entity matching logic to link scraped data to API-sourced restaurant records
   Total cost: ~$200-500/mo for Apify compute

**Phase 3 (Month 4-6): Custom Browser Agents**
For data requiring more intelligence than simple scraping:

1. Build Stagehand/Gemini Computer Use agents for complex research tasks
2. Agent researches a specific restaurant across all platforms, compiles a unified profile
3. Agent explores restaurant websites for menus not on delivery platforms
4. Integrate with ADK multi-agent system (researcher agent dispatches browser sub-agents)
5. Cloud Run workers with Playwright for browser environment
   Total cost: Gemini token costs (covered by credits) + Cloud Run compute

### Entity Resolution Pipeline

Critical challenge: the same restaurant appears differently across platforms.

```
Google Places:    "Pod Orlem Restaurant" at ul. Marszalkowska 15, Warsaw
Pyszne.pl:        "Restauracja Pod Orlem" - Menu items, prices
Uber Eats:        "Pod Orłem" - Menu items, delivery fees
Wolt:             "Pod Orłem - Polish Kitchen" - Menu items, ratings
CEIDG:            "Jan Kowalski JDG" (business name) with PKD 56.11.Z
TripAdvisor:      "Pod Orłem" - 4.2 stars, 127 reviews
Instagram:        @podorlem_warszawa - 2.3K followers
```

Resolution approach:

1. **Google Place ID** as the primary identifier (most restaurants have a Google listing)
2. **Name + address fuzzy matching** with Levenshtein distance / embedding similarity
3. **Phone number matching** (most reliable cross-platform identifier)
4. **NIP/REGON matching** for CEIDG/KRS cross-reference
5. **Vertex AI embeddings** for semantic matching of restaurant names
6. **Human review queue** for low-confidence matches

---

## 13. Open & Alternative Data Sources

### Overture Maps Foundation (Updated Details)

**Latest release:** 2026-03-18.0 with 64M+ place features.

**BigQuery access (free via public dataset):**

```sql
-- Find all restaurants in Poland
SELECT
  id,
  names.primary AS name,
  phones.list[0].element AS phone,
  addresses[1].freeform AS address,
  categories.primary AS category
FROM `bigquery-public-data.overture_maps.place`
WHERE categories.primary = 'restaurant'
  AND addresses[1].country = 'PL'
LIMIT 1000;
```

**DuckDB access (for local analysis):**

```sql
SELECT *
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-03-18.0/theme=places/type=place/*')
WHERE categories.primary ILIKE '%restaurant%'
  AND addresses[1].country = 'PL';
```

**Fields available:** id, name (primary + alternates), full address, coordinates, phone, email, website, social media links, brand, categories, confidence score, operating status, data sources.

**What it lacks:** Reviews, ratings, menus, prices, photos. Just POI data.

**Best use:** Free baseline for building the restaurant universe. Cross-reference with Google Places for enrichment.

### Social Media Data Sources

**Instagram:**

- Official Graph API: two versions exist. (1) Instagram API with Instagram Login — for managing your own business/creator accounts. (2) Instagram API with Facebook Login for Business — includes **Business Discovery endpoint** that CAN access other business accounts' data.
- **Business Discovery endpoint (verified):** Can retrieve `followers_count`, `media_count`, and `media` objects (posts) for ANY public Instagram Business/Creator account. Individual media items include `comments_count`, `like_count`, `view_count`. Does NOT require the target account's permission -- only your app's Instagram user access token. Limitation: no data returned for accounts with age restrictions; cannot directly GET media objects from the response (only metadata).
- Apify Instagram scrapers: public profile data, posts, engagement, hashtags. Legally grey but widely used.
- Data available: follower count, post count, recent posts with likes/comments, posting frequency, hashtag usage.

**TikTok:**

- Research API restricted to academic/non-profit in US/EEA. Not available for commercial use.
- Apify TikTok scrapers: public video data, engagement metrics, profile info.
- Data available: video views, likes, comments, shares, follower counts, content themes.

**Facebook Pages:**

- Graph API requires page admin access for most data.
- Public page data (name, category, rating, address, phone) accessible via search.
- Apify scrapers available for public page data.

### Data Aggregator Services Summary

| Provider              | Best For                                                | European Coverage     | Pricing Model        |
| --------------------- | ------------------------------------------------------- | --------------------- | -------------------- |
| **FoodSpark**         | All delivery platforms (Pyszne, Uber Eats, Wolt, Glovo) | Confirmed EU coverage | Contact for quotes   |
| **DoubleData**        | Cross-platform venue matching, market analytics         | "Any city"            | From $200/project    |
| **Grepsr**            | Custom menu data at 99% accuracy                        | Global                | Contact for quotes   |
| **Transparent Data**  | Polish business registry aggregation (KRS+CEIDG+REGON)  | Poland specialist     | Contact for quotes   |
| **Apify**             | DIY scraping with pre-built actors                      | Platform-agnostic     | $49-499/mo           |
| **Foursquare Places** | Social handles, menu URLs, popularity scores            | 200+ countries        | Free dev tier + paid |
| **Overture Maps**     | Free restaurant universe baseline                       | Global (64M POIs)     | Free (CDLA/CC0)      |

---

## 14. Platforms NOT Active in Poland

**Zomato:** Not operating in Poland. Zomato withdrew from most international markets to focus on India. Not a relevant data source for the Polish market.

**OpenTable:** Very limited presence in Poland. Primarily US/UK/Germany/Japan. Not a significant data source for Polish restaurants.

**Yelp:** Minimal presence in Poland. Much weaker than Google/TripAdvisor for European restaurant discovery. Not worth integrating for Polish market.

**TheFork:** Growing in Central/Eastern Europe but still limited in Poland compared to Western European markets (France, Italy, Spain are strongholds). Worth monitoring but not a primary data source yet.

**Booksy:** Polish-founded but primarily a beauty/wellness booking platform. Restaurant presence is minimal. The API exists (https://alpha.docs.booksy.net/) but requires partner authentication. Not relevant for restaurant data.

---

## 15. Legal & Compliance Notes

### GDPR considerations (EU/Poland)

- Restaurant business data (menus, prices, hours, address) is generally not personal data
- Owner names from CEIDG/KRS are public record but their use should be limited to legitimate business purposes
- Review text may contain personal data if reviewers are identifiable
- Delivery platform scraping likely violates platform ToS but the data itself (menus, prices) is publicly visible
- Polish CEIDG data is explicitly published under Creative Commons license

### Platform Terms of Service

- Google Places API: ToS prohibit caching beyond session use (enforcement varies). Using SerpAPI/Zenserp as intermediaries provides a buffer.
- Delivery platforms: All prohibit scraping in ToS. Using managed services (FoodSpark, DoubleData) shifts compliance risk to the data provider.
- Social media: Instagram/TikTok/Facebook prohibit unauthorized scraping. Apify actors operate in a legal grey zone.

### Recommended risk mitigation

1. Use official APIs wherever available (Google Places, TripAdvisor, CEIDG, KRS)
2. For delivery platform data, prefer managed data providers (FoodSpark, DoubleData) over self-scraping — they assume compliance risk
3. For social media, start with Apify for initial research; evaluate Emplifi or similar enterprise tools if the data proves valuable
4. Keep personal data handling minimal and GDPR-compliant
5. Document data sources and processing purposes for GDPR accountability

---

## Updated Cost Estimates (Monthly, Poland Market Focus)

| Source                           | Monthly Cost        | One-Time Cost        | Data Volume               |
| -------------------------------- | ------------------- | -------------------- | ------------------------- |
| Overture Maps + OSM              | Free                | —                    | Full restaurant universe  |
| CEIDG/KRS/GUS APIs               | Free                | —                    | All registered businesses |
| Google Places API                | $2,000-3,000        | $6,500 initial sweep | 100K restaurants          |
| TripAdvisor Content API          | Pay-per-use         | —                    | 100K lookups              |
| Foursquare Places API            | Contact             | —                    | 100K lookups              |
| Apify actors (delivery + social) | $200-500            | —                    | Weekly refreshes          |
| FoodSpark or DoubleData          | $500-2,000 est.     | —                    | Delivery platform data    |
| Browserbase (Phase 3)            | $99-200             | —                    | Custom browser agents     |
| SerpAPI or Zenserp               | $150-300            | —                    | Monitoring searches       |
| **Total estimated**              | **$3,000-6,500/mo** | **$6,500 setup**     | After initial sweep       |

All within EUR 120K annual budget. Gemini Computer Use costs covered by Vertex AI credits.

---

## Sources

### Polish Government Registries

- [CEIDG Data Warehouse](https://dane.biznes.gov.pl/) — free business registry data
- [CEIDG API v3 Documentation](https://akademia.biznes.gov.pl/hurtownia-danych-instrukcje-i-dokumentacja/)
- [KRS Open API](https://prs.ms.gov.pl/krs/openApi) — National Court Register
- [GUS REGON BIR1 API](https://api.stat.gov.pl/Home/RegonApi?lang=en) — statistical business register
- [Transparent Data API](https://transparentdata.pl/en/api-company-information-poland) — commercial aggregator
- [PKD 2025 gastronomy codes](https://restauracja.online/blog/nowe-kody-PKD-2025-w-gastronomii-co-sie-zmienia)

### Delivery Platforms

- [Just Eat Takeaway Developer Portal](https://developers.just-eat.com/) — partner APIs only
- [Wolt Developer Docs](https://developer.wolt.com/docs/api/menu) — partner menu API only
- [Glovo Partners API](https://api-docs.glovoapp.com/partners/) — partner APIs only
- [FoodSpark Food Data API](https://www.foodspark.io/food-data-api/) — delivery platform data aggregator
- [DoubleData Food Delivery](https://doubledata.com/food-delivery) — cross-platform intelligence

### Reservation Platforms

- [OpenTable API Documentation](https://docs.opentable.com/) — affiliate API
- [TheFork B2B API](https://docs.thefork.io/B2B-API/introduction) — partner API
- [Booksy Public API](https://alpha.docs.booksy.net/index.html) — requires auth

### Browser Automation & AI Agents

- [Firecrawl: Best AI Browser Agents 2026](https://www.firecrawl.dev/blog/best-browser-agents)
- [Agentic Browser Landscape 2026](https://nohacks.co/blog/agentic-browser-landscape-2026)
- [Gemini Computer Use Documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/computer-use)
- [Browserbase](https://www.browserbase.com/pricing) — cloud browser infrastructure
- [Stagehand by Browserbase](https://github.com/browserbase/stagehand) — TypeScript agent framework
- [Browser Use](https://github.com/browser-use/browser-use) — Python agent framework

### Data Sources

- [Overture Maps Places Guide](https://docs.overturemaps.org/guides/places/)
- [Overture Maps in BigQuery](https://docs.overturemaps.org/getting-data/data-mirrors/bigquery/)
- [Apify Marketplace](https://apify.com/store) — pre-built scrapers
- [TripAdvisor Content API](https://developer-tripadvisor.com/content-api/)

### Queue Architecture

- [BullMQ Documentation](https://docs.bullmq.io/)
- [BullMQ Flows](https://docs.bullmq.io/guide/flows) — parent-child job hierarchies
- [Temporal Python SDK](https://docs.temporal.io/develop/python/core-application) — durable workflows
- [Vertex AI Agents + Cloud Pub/Sub](https://medium.com/@kamal.aboulhosn/vertex-ai-agents-cloud-pub-sub-8a11dc949246)

### Scraping Frameworks

- [Crawlee](https://github.com/apify/crawlee) — Node.js/TypeScript scraping library by Apify with Playwright/Puppeteer support, anti-detection (TLS fingerprint, human-like headers), persistent URL queues, proxy rotation, auto-scaling
- [populartimes](https://github.com/m-wrzr/populartimes) — Python library for Google Maps popular times data
- [gusregon](https://pypi.org/project/gusregon/) — Python wrapper for GUS BIR1 SOAP API

### Verified API Endpoints

- Wolt Consumer API: `https://consumer-api.wolt.com/v1/pages/restaurants?lat={lat}&lon={lon}` (no auth)
- KRS Open API: `https://api-krs.ms.gov.pl/api/krs/OdpisPelny/{krsNumber}?rejestr=P&format=json` (no auth)
- GUS BIR1 Production: `https://wyszukiwarkaregon.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc` (API key)
- GUS BIR1 Sandbox: `https://wyszukiwarkaregontest.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc` (test key)
- TripAdvisor: `https://api.content.tripadvisor.com/api/v1/location/{locationId}/details?key={key}`
- CEIDG Data Warehouse: `https://dane.biznes.gov.pl` (Trusted Profile auth, CC BY 3.0 PL license)
- Glovo consumer API: `https://api.glovoapp.com` (v3 stores endpoint decommissioned)

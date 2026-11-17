# Pizza Hut UAE – Competitor Intelligence Platform

## 1. Project Vision
Build a fully functioning web application that researches competitor pizza prices in the UAE, extracts real information, validates findings and generates comparison reports.

This is an independent prototype, not an officially affiliated Pizza Hut system.

## 2. Core Objective
Automate competitor price intelligence using publicly accessible online sources.

## 3. Non-Negotiable Principles
- All production research data must be real.
- Never invent prices, products, promotions or sources.
- Every finding must have a source URL.
- Record the date and time of collection.
- Record location and ordering method.
- Distinguish verified, needs review and unavailable.
- Never silently substitute missing information.
- Do not bypass logins, CAPTCHAs or website restrictions.
- Keep the initial architecture simple.
- Maintain a zero-cost development strategy.

## 4. Initial Scope
- Business context: Pizza Hut UAE
- Market: United Arab Emirates
- Initial pilot city: To be decided
- Research category: Pizza products
- Competitors: To be decided
- Sources: Publicly accessible competitor websites
- Output: Web dashboard and Excel reports

## 5. Core Features
1. Research request interface
2. Competitor selection
3. Website research and data extraction
4. Product matching
5. Price and promotion comparison
6. Source evidence and timestamps
7. Historical price records
8. Accuracy validation
9. Excel report generation

## 6. Proposed Technology
- Development assistant: Gemini CLI
- Language: Python
- Browser automation: Playwright
- Dashboard: Streamlit
- Database: SQLite initially
- Version control: Git and GitHub
- Hosting: Free hosting options

All technology choices are subject to validation before implementation.

## 7. Data Requirements
Every collected observation should support:
- Competitor name
- Product name
- Product size
- Price
- Currency (AED)
- Location
- Order method
- Promotional conditions
- Original source URL
- Collection timestamp
- Verification status

## 8. Development Method
Build incrementally:
1. Establish environment
2. Define requirements
3. Build dashboard
4. Build research engine
5. Connect database
6. Implement validation
7. Generate reports
8. Test against manually verified real prices
9. Deploy a shareable application

## 9. Development Rules
- No unnecessary features.
- No paid APIs without explicit approval.
- No hardcoded fake research results.
- No exposed API keys or credentials.
- Explain technical decisions in plain English.
- Test each milestone before proceeding.
- Keep documentation updated.

## 10. Current Status
The existing Streamlit dashboard and SQLite database are in place. A Pizza Hut UAE public-menu collector, evidence-backed manual benchmark workflow, accuracy evaluator, and read-only audit of legacy live-extraction rows are implemented. The first live run captured 31 regional menu variants; all remain in QA until a selected branch/channel is checked. Existing historical rows are preserved; all 684 seed observations remain quarantined. See `TAKEOVER_AUDIT.md` for the repository, database, source, and test audit.

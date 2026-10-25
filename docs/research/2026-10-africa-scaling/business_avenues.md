# Business models, go-to-market paths, target customers and precedents for Okada Router

Research date: 25 October 2026. Method note: ~26 web searches were completed; direct page fetches (WebFetch/curl) were blocked by the sandbox proxy for every external domain, so findings rely on search-result extracts rather than full-page reads, and the search budget ran out before several planned follow-ups (LiteLLM commercial terms, Kiwix/Ushahidi, M-KOPA/Tizeti, Paystack/Flutterwave early-traction stories, Safaricom AI, Nigerian clinic AI pilots, Termii's naira price list). Those are listed as gaps. Product facts about Okada Router come from the repository README at the time of research.

Product baseline (from the repo, for the report writer): Okada Router is an OpenAI-compatible FastAPI gateway that routes on *network* conditions (latency/packet loss/offline) rather than provider-side signals, with a degraded-mode ladder (primary cloud -> smaller cloud -> alternate provider -> exact cache -> local quantized model via Ollama/llama.cpp -> offline queue with replay). Its benchmark claims "direct 69.6% answered vs Okada 100%; offline 0% vs 100%" over 8 requests x 7 simulated profiles. Self-declared gaps: exact-match single-tenant cache with no PII handling, non-incremental streaming, queue not replayed after restart, no encryption at rest, no tenant isolation, no mobile SDK. — [Okada Router README](https://github.com/demimadeit/okada-router)

---

## Key Question 1: Who in Africa pays today for AI API access or AI features, what do they pay, and is there evidence that outages hurt them?

### Takeaway
There is strong evidence that Nigerian connectivity failures are frequent and hit financial services, and that paying for US-dollar AI APIs from Nigeria is a real friction; there is almost no public evidence of how much specific African fintechs spend on LLM APIs, so the "who pays what for AI" picture must be inferred from adjacent signals (telco AI deals, donor programs, SME adoption studies).

### Cited Findings

Outage and infrastructure pain (demand-side evidence for "resilience")
- Nigeria recorded 19,384 fibre-optic cable cuts across 2025; MTN Nigeria alone reported 5,478 cuts in the first seven months of 2025. — [TechEconomy](https://v2.techeconomy.ng/telecom-operator-in-nigeria-reports-5478-fibre-cuts-in-2025); [TechEconomy CNII workshop](https://techeconomy.ng/cnii-nigeria-to-hold-stakeholders-workshop-on-telecom-infrastructure-protection-as-fibre-cuts-surge-nationwide)
- Fibre cuts, mostly from road construction or vandalism, accounted for about 70% of disruptions in early 2025; MTN logged 1,002 major outages in full-year 2025, ahead of T2 Mobile at 632. — [Daba Finance](https://dabafinance.com/en/news/nigerias-telecom-outages-expose-infrastructure-and-response-gaps)
- The June 2025 designation of telecom infrastructure as Critical National Information Infrastructure (CNII) "fails to stop fibre cuts" per TechCabal; Lagos telcos lost an estimated NGN 5 billion (~$10.8m) in 2024 to more than 2,500 fibre cuts, and the industry lost ~NGN 27 billion (~$58.6m) to fibre damage in 2023. — [TechCabal](https://techcabal.com/2025/06/13/cnii-order-fails-to-stop-fibre-cuts/); [Daba Finance](https://dabafinance.com/en/news/nigerias-telecom-outages-expose-infrastructure-and-response-gaps)
- Q1 2026: 5,934 fibre cuts between January and March 2026. (A later May 2026 report's monthly figures do not reconcile arithmetically and should not be cited.) — [TechEconomy](https://techeconomy.ng/cnii-nigeria-to-hold-stakeholders-workshop-on-telecom-infrastructure-protection-as-fibre-cuts-surge-nationwide)
- Every major fibre cut "affects banking systems, ATMs, Point-of-Sale terminals, fintech applications" (general statement, not a measured loss). — [Daba Finance](https://dabafinance.com/en/news/nigerias-telecom-outages-expose-infrastructure-and-response-gaps)
- Fintech-side outage evidence: Paystack's status page logged UBA-side downtime on 7 April 2025 and again on 10 and 13 May 2025 with high card failure rates; Paystack also logged a NIBSS central-switch degradation delaying outward transfers and Direct Debit. — [Paystack status (April)](https://status.paystack.com/incidents/n9xbc53npcbp); [Paystack status (May)](https://status.paystack.com/incidents/wsmb06pmhgkd); [Paystack status (NIBSS)](https://status.paystack.com/cmo1h2zf000ihogx77ypja0tr)
- NIBSS downtime episodes left customers unable to complete transactions in mobile banking apps and fintech platforms; Eversend and Kuda warned customers of delayed payouts; one Guardian report describes ~3 days of failed transactions and delayed salary payments. — [BusinessDay](https://businessday.ng/?p=1131602); [TheCable](https://thecable.ng/?p=1020432); [Guardian Nigeria](https://guardian.ng/?p=10079)
- Paga attributed transaction delays to intermittent NIBSS downtime. — [TechEconomy](https://techeconomy.ng/?p=181638)
- Nigerians spent NGN 20.87 billion per day on mobile data in 2025 (headline of a TechCabal analysis). — [TechCabal](https://techcabal.com/2026/02/09/how-nigerians-spent-%E2%82%A620-87billion-daily-on-data-in-2025/)

Paying for AI from Nigeria (friction evidence)
- Premium AI services including the OpenAI and Anthropic APIs are billed in US dollars via payment systems that "routinely reject African cards"; Nigerian banks re-enabled international payments on naira cards only in mid-2025, with per-quarter limits that vary by bank (vendor press release, LinkPay). — [Global Fintech Series](https://globalfintechseries.com/banking/digital-payments/africa-leads-the-world-in-ai-adoption-but-cant-pay-for-it-linkpay-brings-instant-virtual-cards-for-ai-services/)
- Some Nigerian banks cap international naira-card spend at ~$500 per month (TechCabal guide, 2025). — [TechCabal (ES)](https://techcabal.com/es/?p=165651)
- OpenAI bills in USD through Stripe; naira cards generally fail; a $20 subscription was ~NGN 25,000–30,000/month in 2025 (fintech vendor guide, Grey). — [Grey blog](https://grey.co/blog/how-to-pay-for-chatgpt-plus-in-nigeria)
- Nigerian developers report repeated card declines paying for the OpenAI API with no clear resolution (OpenAI community thread). — [OpenAI Community](https://community.openai.com/t/how-do-i-make-payement-for-api-from-nigeria-my-card-is-constantly-been-declined/567647)
- Nigeria's GitHub developer community passed 1.1 million, growing 28% YoY (GitHub Octoverse, as cited by a vendor release; not independently verified here). — [Global Fintech Series](https://globalfintechseries.com/banking/digital-payments/africa-leads-the-world-in-ai-adoption-but-cant-pay-for-it-linkpay-brings-instant-virtual-cards-for-ai-services/)

Who is visibly using/buying AI
- Fraud detection is the most concrete fintech AI use found: "Flutterwave and Paystack report fraud reduction rates of up to 35% in pilot programs" (thin source, unverified elsewhere); Pastel sells AI fraud/AML tools to African financial institutions. — [af.net](https://af.net/realtime/african-fintech-startups-harness-ai-for-fraud-detection/)
- MTN Nigeria integrated OpenAI (ChatGPT 3.5) into its Zigi customer-service chatbot with Microsoft and Superbo (undated; the GPT-3.5 reference implies pre-2025). — [MarTechVibe](https://martechvibe.com/?p=38354); [The Founder Africa](https://thefounder.africa/revolutionizing-customer-service-mtn-nigeria-introduces-africas-first-ai-powered-chatbot/)
- Airtel Africa signed a multi-year, multi-million-dollar deal with Xtelify (Bharti Airtel subsidiary) in August 2025 to deploy AI software across its 14 African markets. — [Nairametrics](https://nairametrics.com/2025/08/04/airtel-africa-signs-multi-million-dollar-deal-with-xtelify-to-deploy-ai-across-14-markets/); [ITWeb Africa](https://itweb.africa/article/airtel-africa-taps-indian-tech-muscle-in-xtelify-ai-deal/KPNG878NlgYq4mwD)
- MTN–Microsoft: Microsoft 365 with Copilot to be available to MTN subscribers in selected markets from early 2026. — [MEA Tech Watch](https://meatechwatch.com/?p=39023)
- South Africa (not Nigeria): GenAI adoption reached 67% of large enterprises in 2025, up from 45% in 2024 (sample >100 medium/large firms). — [Engineering News](https://www.engineeringnews.co.za/article/marked-increase-in-companies-using-genai-but-market-still-maturing-study-2025-07-17)
- Microsoft Research ran a qualitative study of SMBs in Kenya and Nigeria using generative AI tools in everyday work (no adoption percentage given). — [Microsoft Research](https://www.microsoft.com/en-us/research/wp-json/wp/v2/msr-research-item/1104276)
- A small (n=120) 2025 study found 64.2% of surveyed Nigerian small-scale farmers had used generative AI, mainly for information access. — [DUT repository / Indian Journal of Extension Education via search](https://ir.dut.ac.za/handle/10321/5721)
- Opera Mini: Kenya is its largest market (~13m users, 12% of a claimed 100m global base); Opera says it invested >$100m in Africa since 2020; Opera partnered with MTN for 3GB free data per month for Opera Mini users; Aria browser AI was rolled out to Opera Mini users in April 2025. — [TechCabal](https://techcabal.com/2025/04/16/opera-mini-mobile-browser/); [ITWeb](https://itweb.co.za/article/opera-mini-eyes-african-expansion-with-ai-infusion/JN1gPvOA36YMjL6m); [Seeking Alpha PR](https://seekingalpha.com/pr/20068580-fully-integrated-browser-ai-aria-is-now-available-to-millions-of-opera-mini-users)

Funding context (ability to pay)
- Partech: African startups raised ~$4.1B in 2025 (+25%), equity $2.4B (+8%) across 462 deals, debt a record $1.6B (+63%); 570 transactions; Kenya led total capital ($1.04B); fintech remained the largest equity sector but its share declined; AI "is present across fintech, healthtech, logistics and enterprise startups, yet rarely categorized separately in funding data." — [Partech](https://partechpartners.com/news/2025-partech-africa-tech-vc-report-african-tech-funding-rebounds-to-us41b-driven-by-record-debt-activity-and-disciplined-equity-growth); [MEA Tech Watch commentary](https://meatechwatch.com/?p=46970)
- Other trackers give different 2025 totals ($2.8B TechCabal; ~$3.4–3.5B others) due to methodology. — [TechCabal](https://techcabal.com/2025/12/12/fintechs-lead-africas-2025-valuation-table/); [Analytics Insight](https://www.analyticsinsight.net/startups/top-10-african-fintech-startups-to-watch-in-2026)
- Moniepoint processed NGN 412 trillion (~$294B) in 2025 and serves ~10m businesses/individuals; Flutterwave acquired Mono (Jan 2026, all-stock, $25–40m). — [Techpoint](https://techpoint.africa/guide/best-fintech-companies-in-nigeria/); [TechCrunch](https://techcrunch.com/2026/01/05/flutterwave-buys-nigerias-mono-in-rare-african-fintech-exit/)

### Inferences
- The most defensible buyer thesis is not "African companies spend a lot on LLM APIs" (unproven) but "African companies that already run customer-facing automation (chatbots, fraud scoring, support) suffer measurable channel failures, and a resilience layer that keeps those features answering during fibre cuts/NIBSS-style outages has a quantifiable value." Okada's own metric vocabulary (answered-rate, fallback counts) maps directly onto this.
- Dollar-billing friction creates a second, orthogonal pain: a Nigerian reseller/gateway that can be paid in naira (or that reduces cloud spend via cache/local fallback) has a wedge independent of resilience. This is inference from the card-decline evidence; no source quantified how much AI spend is lost to it.
- Telco deals (Airtel–Xtelify, MTN–Microsoft, MTN–Huawei) show telcos are buying AI from large vendors, not startups; a solo founder is more likely to reach telcos through their developer/SME programs than as a core vendor.

### Gaps
- No public figures were found for LLM/API spend at Moniepoint, Flutterwave, Paystack, Kuda, OPay, Jumia, Wasoko, Sendy, Termii or Africa's Talking, nor any announcement of LLM-based customer-support bots at Moniepoint/Kuda/OPay in 2025–2026 (search returned only directory pages).
- No NIBSS/CBN cost-of-outage estimate exists in the public sources found.
- No Nigeria-specific SME GenAI adoption percentage was found for 2025–2026.

---

## Key Question 2: Pricing anchors and monetization models from open-source AI gateways and OSS infra companies (LiteLLM, Portkey, Helicone, Ollama, PostHog, Supabase, Cal.com)

### Takeaway
The standalone LLM-gateway category consolidated in 2026 (Helicone into Mintlify in maintenance mode; Portkey into Palo Alto Networks), the published price points are low ($49–$79/month entry tiers, ~$250/month unverified for LiteLLM enterprise), and the surviving pattern is OSS core + hosted cloud + enterprise features (SSO, audit logs, SLA). Okada's differentiation must therefore be the network-aware/offline ladder and Africa-specific compliance, not "another gateway."

### Cited Findings
- LiteLLM: core SDK and proxy are open-source and free to self-host; Enterprise license adds SSO/SAML, audit logs, custom SLAs, feature prioritization, dedicated support; pricing not public (sales-led); one secondary source says "Enterprise from ~$250/mo" (unverified); one review flags a documented security history. — [Dupple](https://dupple.com/learn/best-llm-gateways); [Tech Jack Solutions](https://techjacksolutions.com/ai-tools/llm-gateways/best-llm-gateways-2026/); [dev.to](https://dev.to/debmckinney/top-5-litellm-alternatives-in-2025-1pki)
- Portkey: Developer plan free (10,000 logs/month, 3-day retention); Production $49/month + $9 per 100K logs; total funding ~$18M; acquired by Palo Alto Networks, announced 30 April 2026, closed 29 May 2026 (PitchBook date; deal terms not found). — [Eden AI comparison](https://www.edenai.co/post/best-portkey-alternatives-7-ai-gateways-compared); [PitchBook](https://pitchbook.com/profiles/company/529193-62); [Dupple](https://dupple.com/learn/best-llm-gateways)
- Helicone: free 10k requests/month, Pro $79/month; 16,000 organisations over three years; acquired by Mintlify (March 2026); founders joined Mintlify in SF; product in maintenance mode (security updates and bug fixes only, no new features). — [Helicone blog](https://www.helicone.ai/blog/joining-mintlify); [Mintlify blog](https://www.mintlify.com/blog/mintlify-acquires-helicone); [Dealroom](https://ai-startups.dealroom.co/news/feed/mintlify-acquires-open-source-ai-observability-platform-helicone)
- PostHog: founded 2019, pivoted to product analytics during YC (early 2020), $3M seed (Apr 2020), $9M Series A led by GV (Dec 2020), later $15M Series B; open-core with self-hosted "Scale" and fully hosted "Cloud" enterprise tiers; 3,000 deployments by Dec 2020 (deployments, not paying customers). — [BusinessWire](https://www.businesswire.com/news/home/20201217006165/en/PostHog-Raises-%2412-Million-in-Funding-Led-by-GV-and-Y-Combinator-to-Bring-Open-Source-Product-Analytics-Platform-to-Engineers); [VentureBeat](https://venturebeat.com/business/open-source-product-analytics-platform-posthog-raises-15m)
- N-ATLAS (Nigeria's government-backed open-source LLM by Awarri, launched 20 Sept 2025 at UNGA80; Llama-3 8B, 400M+ tokens of Yoruba/Hausa/Igbo/Nigerian-English instruction data): free for research, prototyping and small-scale use; a separate licence is required once deployed commercially with more than 1,000 end users (fee not disclosed). — [TechCabal](https://techcabal.com/2025/09/25/nigerian-government-awarri-launch-n-atlas/); [Open Source For U](https://www.opensourceforu.com/2025/09/nigeria-unveils-open-source-n-atlas-ai-model-to-champion-african-languages-at-unga80/); [TechCabal analysis](https://techcabal.com/2025/09/26/the-high-stakes-push-to-build-nigerias-first-open-source-llm/)
- Africa's Talking (precedent for African developer-API pricing): prepaid wallet, volume tiers, ~$0.0075–$0.01 per SMS (US) per third-party comparison pages; Nigerian bulk SMS runs NGN 5.62–7.00 per 160-char page (competitor marketing, March 2025). — [Courier](https://www.courier.com/providers/pricing/sms/); [BulkSMSNigeria](https://www.bulksmsnigeria.com/resources/sms-pricing-calculator)
- Termii: prepaid pay-as-you-go wallet; unit prices vary by country/network/channel/route; third-party listing shows USD and says exact rates must be confirmed in-dashboard. — [apis.io](https://apis.io/plans/termii/termii-plans-pricing/)

### Inferences
- Pricing anchor for a hosted "Okada Cloud" aimed at African startups: a free self-host tier, a $19–$49/month team tier (below Portkey/Helicone because of purchasing power), and an "enterprise/on-prem" tier sold in naira to banks/telcos. Nobody found in the research sells a gateway in naira; that is an open niche (inference).
- The acquisitions suggest the exit path for a standalone gateway is acqui-hire or feature absorption by a larger platform; "the next Starlink" via gateway SaaS alone is not supported by comparables. The more durable value is in the vertical deployments and the dataset (see Q6).
- Time-to-revenue for OSS infra (PostHog as example) was roughly 12 months from pivot to paid tiers, with venture capital underwriting it; a $0-raised solo founder should expect paid pilots rather than self-serve SaaS revenue in year one.

### Gaps
- LiteLLM's actual revenue/customer count and official enterprise price were not found; Ollama's business model, Supabase and Cal.com monetization timelines were not researched before the search budget ended.
- Termii's naira price list could not be fetched (termii.com blocked by proxy).

---

## Key Question 3: Precedents and lessons from African infrastructure/distribution companies (hardware cautionary tales vs software wins)

### Takeaway
The clearest pattern in the evidence: hardware-first ventures (BRCK/Moja, Mara Phones) died when a demand shock or production targets hit, while software/API distribution plays (Opera Mini, Africa's Talking, Viamo's voice-AI) scaled by riding existing channels (telco bundles, developer APIs, basic phones). Hardware in Africa is survivable only with external subsidy or financing.

### Cited Findings
- BRCK (Nairobi; rugged connectivity box, Kio Kit classroom kit, Moja free public Wi-Fi): acquired Surf/EveryLayer in Feb 2019 (1,200 hotspots, 200,000 active customers in 22 Kenyan cities); Moja reached 2,700 locations and 700,000 monthly unique visitors; expanded to South Africa in Dec 2019; model was free to users, subsidised by commercial partners (survey/app-download/ad for faster access). — [TechCrunch](https://techcrunch.com/2019/02/15/brck-acquires-isps-everylayer-and-surf-to-boost-africas-public-wi-fi); [Stuff.co.za](https://stuff.co.za/2019/12/04/brck-brings-free-wifi-to-south-africa/); [RCR Wireless](https://rcrwireless.com/20190802/network-infrastructure/brck-free-public-wi-fi-kenyan-buses)
- BRCK outcome: Unreasonable Group lists BRCK as "no longer operating"; Engineering for Change says the BRCK device is "no longer in production"; Business Daily (2022) reported BRCK among six Kenyan startups that shut down fully or partly in a short window, and that its Facebook-funded free Wi-Fi business "was wiped out by the Covid-19 wave"; no founder post-mortem was found. — [Unreasonable Group](https://unreasonablegroup.com/ventures/brck); [Engineering for Change](https://www.engineeringforchange.org/?p=12396); [Business Daily Africa](https://www.businessdailyafrica.com/bd/corporate/technology/why-six-kenyan-promising-tech-start-ups-fell-3987374)
- Mara Phones (Durban factory, launched 2019): funder IDC "decided to pull the plug" because it did not meet production targets after Covid-19; factory shut and sold by order of IDC and Standard Bank. — [Africa.com](https://africa.com/top-10-news/a-promising-venture-for-a-made-in-south-africa-smartphone-dashed)
- Africa's Talking: founded 2010 by MIT grads Samuel Gikandi and Eston Kimani; several pivots before the API platform; by 2019 in 18 countries serving ~5,000 businesses; Series A mid-2018; founder Gikandi said in a September 2025 post he had been forced out, amid reported governance disputes (single source, unverified). — [MIT News](https://news.mit.edu/2019/africas-talking-mobile-0611); [CB Insights](https://www.cbinsights.com/investor/africas-talking)
- Viamo "Ask Viamo Anything" (voice GenAI over toll-free calls on basic phones, Zambia pilot): initial 500 power users produced 453 valid answers (93%); later >5,000 users and 46,000 questions; >60% of interactions from women; >half of questions tied to SDGs; rollout planned to Pakistan, India, Nigeria, Tanzania; GSMA summary dated March 2025; all figures are Viamo's own. — [Viamo](https://viamo.io/ask-viamo-anything/); [Viamo CEO letter 2023](https://viamo.io/viamo-platform/ceo-annual-letter-2023/); [GSMA M4D](https://www.gsma.com/solutions-and-impact/connectivity-for-good/mobile-for-development/gsma_resources/voice-first-generative-ai-for-impact-insights-from-viamos-ask-viamo-anything-pilot-in-zambia/); [Silicon UK press release](https://www.silicon.co.uk/press-release/ask-viamo-anything-combines-ai-with-basic-mobile-calls-to-bring-next-billion-online)
- Opera Mini: distribution via telco data bundles (MTN 3GB free/month; Safaricom renewal in late 2025 produced a 93% surge in DAU among Safaricom users per Opera). — [ITWeb](https://itweb.co.za/article/opera-mini-eyes-african-expansion-with-ai-infusion/JN1gPvOA36YMjL6m); [TechTrends KE](https://techtrendske.co.ke/2025/04/18/opera-mini-ai-integration-aria-africa/)
- Starlink Nigeria: ~66,523 subscribers in Q2 2025 (second to Spectranet) and ~98,642 in a 2026 ranking (second-largest ISP, ~3 years after launch); residential pricing reports conflict (NGN 38,000 -> 57,000 in May 2025 per one source; NGN 75,000 per another; a 2026 report of a 97% hike with prices "as high as NGN 717,000"); kits ~NGN 590,000; in high-demand Lagos areas residential orders are closed and only Priority (NGN 159,000/month) is offered; Amazon Kuiper obtained Nigerian landing rights January 2026. — [Global Brands Magazine](https://www.globalbrandsmagazine.com/?p=117092); [Daba Finance](https://dabafinance.com/en/news/starlink-doubles-subscription-prices-in-nigeria-amid-inflation-surge); [TechEconomy](https://techeconomy.ng/starlink-hikes-subscription-fees-in-nigeria-by-97-prices-now-as-high-as-%e2%82%a6717000); [BusinessDay](https://businessday.ng/technology/article/starlinks-n159000-lifeline-hits-nigerias-starved-cities)
- Juza AI (Kenya): solar-powered, offline-first "AI in a box" curriculum tutor on a low-power computer in classrooms in Samburu, Isiolo and Garissa; Mastercard Foundation EdTech Fellowship; "still early." — [iHub Future of Learning directory](https://futureoflearning.ihub.co.ke/startup-directory/juza-ai/); [Africa Practice/Brink report](https://africapractice.com/?p=6100)
- Ethiopia's Ministry of Education pilot-launched an offline AI teacher assistant; 79% of Ethiopian schools lack reliable internet. — [Kana Television](https://kanatelevision.com/news/offline-artificial-intelligence-tool-launched-to-help-ethiopian-secondary-school-teachers/)
- A 2025 UNESCO GEM background paper reportedly makes "start offline" its first principle for scaling AI in African schools (secondhand; paper not located). — [The Cairo Review](https://www.thecairoreview.com/essays/artificial-intelligence-offers-learning-opportunities-in-the-global-south/)

### Inferences
- Lesson for an "Okada box": BRCK's hardware line is out of production and its Wi-Fi business collapsed when ad/sponsor revenue vanished; Mara died on production targets. A solo founder with $0 should not manufacture; if hardware is needed, ship software onto commodity hardware the customer already owns (a Windows PC, a Raspberry Pi/mini-PC bought locally) or let an NGO/donor fund devices (Juza AI route).
- Starlink itself is an instructive precedent for the "Starlink of X" ambition: even with SpaceX's capital it reached only ~100k Nigerian subscribers in ~3 years, is capacity-constrained in Lagos, and prices in naira are volatile; ubiquity in Africa comes from telco-bundled distribution (Opera Mini, Viamo via toll-free voice), not from premium kit.
- Viamo's result (93% valid answers on first 500 users; 46k questions) is the closest evidence that demand for AI answers exists among low-connectivity users; its delivery channel (voice/USSD over GSM) is the opposite of Okada's current design (IP gateway). A Pidgin/voice bot built on Okada would need a telco or Viamo-like partner.

### Gaps
- No founder-authored post-mortem for BRCK; shutdown date is approximate (2022 per Business Daily; Moja's current status unknown).
- Kiwix, Ushahidi, M-Pesa, Tizeti/Wi-Flix, M-KOPA, and Paystack/Flutterwave early-traction stories were not researched before the search budget ended.

---

## Key Question 4: Telco/MNO, government, donor and NGO channels (MTN, Airtel, Safaricom; Gates/OpenAI; GSMA; UNICEF/GIZ/World Bank)

### Takeaway
Telcos are investing in AI at the network layer and via large vendors (Huawei, Microsoft, Xtelify) and are co-funding African-language models through the GSMA; donors (Gates/OpenAI Horizon 1000, Gates/Anthropic $200m) are putting money into health and education AI in Africa; nothing found shows a UNICEF/GIZ/World Bank offline-LLM pilot, which is both a gap in the evidence and a potential white space.

### Cited Findings
- GSMA + Airtel, MTN, Orange, Vodacom, Ethio Telecom, Axian Telecom and AI/research groups announced a continent-wide collaboration at MWC Kigali (October 2025) to build African-language AI models, addressing data, compute, talent and policy gaps; a GSMA feasibility study found such models "technically feasible and economically viable"; GSMA's Mobile Economy Africa 2026 reports a Swahili model already live (secondary reporting). — [Engineering News](https://www.engineeringnews.co.za/article/gsma-african-mobile-operators-ai-ecosystem-unite-to-accelerate-development-of-inclusive-african-ai-2025-10-21); [Mobile World Live](https://www.mobileworldlive.com/gsma/gsma-teams-with-africa-heavyweights-on-ai-mobile-access-initiatives/); [Connecting Africa](https://www.connectingafrica.com/ai/mwc-kigali-2025-alliance-forms-to-accelerate-inclusive-ai-language-models); [Techpoint](https://techpoint.africa/news/africa-ai-language-models/)
- MTN–Huawei MoU at MWC 2026 (March 2026) on AI-driven network operations and Level 4 autonomous networks. — [Ecofin Agency](https://www.ecofinagency.com/news-digital/1203-53726-mtn-expands-huawei-partnership-to-deploy-ai-driven-telecom-networks-in-africa)
- MTN–Microsoft: Microsoft 365 with Copilot for MTN subscribers in selected markets from early 2026. — [MEA Tech Watch](https://meatechwatch.com/?p=39023)
- Airtel Africa–Xtelify: multi-year AI software deployment across 14 markets (Aug 2025). — [Nairametrics](https://nairametrics.com/2025/08/04/airtel-africa-signs-multi-million-dollar-deal-with-xtelify-to-deploy-ai-across-14-markets/)
- Gates Foundation + OpenAI "Horizon 1000" (announced 20 Jan 2026): $50m in funding, technology and technical support; pilot targeting 1,000 primary healthcare clinics and surrounding communities by 2028, starting in Rwanda with 50+ clinics; tools focus on administrative load (transcription, record-keeping); Rwanda has ~1 health worker per 1,000 people vs WHO's 4; concern raised that most AI tools are English-only while ~75% of Rwandans speak Kinyarwanda. — [OpenAI](https://openai.com/index/horizon-1000/); [Semafor](https://www.semafor.com/article/01/21/2026/gates-foundation-openai-launch-50m-ai-health-program-in-africa); [AP via WTOP](https://wtop.com/world/2026/01/rwanda-to-test-ai-powered-technology-in-clinics-under-a-new-gates-foundation-project/)
- Gates Foundation + Anthropic: $200m over four years for AI public goods with a focus on health and education in Africa (research centres using Claude for drug-candidate prediction; literacy/numeracy, tutoring and career-guidance tools). — [GRIP/Global Relay](https://www.grip.globalrelay.com/gates-foundation-expands-ai-partnerships-across-health-education-and-development/); [AU Startups](https://au-startups.com/news/anthropic-gates-foundation-africa-ai-health-education)
- Gates "Grand Challenges: Catalyzing Equitable AI Use" funded ~50 grants including a Kenyan youth-health LLM project with Children's National. — [Children's National](https://innovationdistrict.childrensnational.org/?p=17247)
- Nigeria's N-ATLAS was launched by the Minister of Communications, Innovation and Digital Economy (Bosun Tijani) at UNGA80 (20 Sept 2025) and is not yet a consumer app. — [WeAreTech Africa](https://www.wearetech.africa/en/fils-uk/news/tech/nigeria-launches-n-atlas-an-ai-language-model-in-yoruba-igbo-hausa-and-nigerian-english)
- Lagos compute: Kasi Cloud LOS1 is a 40MW-designed campus starting at 7.2MW IT load with Nvidia H100/H200 GPUs serving local enterprise AI workloads; Africa Data Centres' Eko Atlantic site runs 1.2MW of a planned 10MW; Airtel's Lagos facility is designed for AI compute (GPU delivery unconfirmed); Cassava–Nvidia "AI factory" plans ~12,000 GPUs over 3–4 years starting with 3,000 in South Africa, Nigeria later; operators face a 64.1% energy-cost surge since January 2026, unstable grid and currency volatility; Lagos State aims to triple data-centre capacity by 2030. — [TechCabal (Jan 2026)](https://techcabal.com/2026/01/08/will-nigeria-get-its-first-ai-data-centre-in-2026/); [TechCabal (May 2026)](https://techcabal.com/2026/05/20/lagos-wants-to-triple-its-data-centre-capacity-by-2030/); [Spheron (vendor blog)](https://www.spheron.network/blog/gpu-cloud-providers-africa-2026/)

### Inferences
- Telco channel: realistic entry is not a core network contract but (a) being the resilience layer for a telco's own AI-powered customer-service bot (MTN's Zigi is a named precedent) or (b) a developer-program/APN bundle where Okada's cache + local fallback cuts data use; the GSMA language-model alliance could consume Okada as the "edge serving" layer for the models it produces. All of this requires an intro and is 12-month, not 90-day, work.
- Donor channel: Horizon 1000's own stated concerns (connectivity, language, clinic staffing) are exactly Okada's pitch; the Rwanda-first scope means a Nigerian founder would approach through implementing partners or the Nigeria phase rather than directly. Gates/Anthropic's education-and-health focus and Grand Challenges-style small grants are the most plausible non-dilutive money for a solo founder.
- Local inference in Lagos is now physically possible (Kasi H100/H200) but expensive and power-constrained; a hosted "Okada edge" on Lagos GPUs would have to be rented, not built, and the data-residency argument (Q5) is what makes the extra cost sellable.

### Gaps
- No evidence found of UNICEF, GIZ or World Bank offline-LLM pilots in Africa 2025–2026 (searches returned only Gates/OpenAI/Anthropic programs).
- No Safaricom AI partnership was found (not searched separately before the budget ended).
- No confirmation of Cloudflare or AWS presence in Lagos.

---

## Key Question 5: Regulatory and trust issues (NDPA/GAID 2025, CBN data localisation, health data) and whether local inference is a compliance selling point

### Takeaway
Nigeria now has a concrete, dated data-localisation mandate for payments (CBN circular, June 2026, deadline 1 January 2027) layered on the NDPA 2023/GAID 2025 regime, which classifies finance and health as "extra-high-level" sectors requiring annual compliance audits and DPIAs for automated decision-making. This makes "prompts and transaction context never leave Nigeria" a saleable, time-bound compliance feature for fintechs and health providers, though no source yet quantifies what buyers will pay for it.

### Cited Findings
- CBN circular (June 2026) requires payment transaction data to be stored in Nigeria with a 1 January 2027 compliance deadline; covers banks, fintechs, mobile money operators and payment service providers; CBN has insisted the deadline is firm; the circular also introduces market-structure and ultimate-beneficial-ownership requirements. — [tech.africa](https://tech.africa/?p=88017); [Guardian Nigeria](https://guardian.ng/?p=2931152); [Mondaq (fintech localisation)](https://www.mondaq.com/nigeria/fin-tech/1722826/how-nigerias-data-localization-regime-shapes-fintechs-handling-of-financial-identity-and-transaction-data)
- Nigeria has no single comprehensive localisation law; it layers the NDPA 2023, GAID 2025, the 2019 National Cloud Computing Policy, sector regulators (CBN, NITDA) and procurement policy; the NDPA governs transfers abroad rather than mandating residency; sovereign/government data must be stored locally with NITDA approval for cross-border hosting; the CBN BVN framework requires BVN data to stay in Nigeria. — [Mondaq (myth vs reality)](https://www.mondaq.com/nigeria/new-technology/1821620/data-localisation-in-nigeria-separating-myth-from-reality); [Africloud](https://africloud.com/news/nigeria-data-protection-act-data-residency); [Banwo & Ighodalo PDF](https://www.banwo-ighodalo.com/media-files/2025/12/data-localization.pdf); [Global Law Experts](https://globallawexperts.com/data-localisation-vs-crossborder-transfer-nigeria-2026/)
- GAID 2025: issued by NDPC on 20 March 2025 under s.61 NDPA, replacing the NDPR 2019 from 19 September 2025; applies to data subjects in Nigeria, data transferred to or in transit through Nigeria, and Nigerian citizens abroad. — [Afriwise](https://www.afriwise.com/blog/key-updates-from-the-nigeria-data-protection-act---general-application-and-implementation-directive-2025); [Captain Compliance](https://captaincompliance.com/education/nigerias-data-protection-act-and-gaid-are-operationalizing-a-modern-data-privacy-regime/)
- GAID: automated decision-making with legal/similar effects, profiling and health-care services trigger registration and audit requirements; DPIAs are mandatory for automated decision-making/profiling, sensitive data, vulnerable subjects, "innovative tech deployments"; cross-border transfer to a country without an NDPC adequacy decision and automated processing require prior consideration. — [Legal Bytes](https://legalbytes.substack.com/p/gaid-2025-what-nigerian-businesses); [Mondaq (GAID guide)](https://www.mondaq.com/nigeria/privacy-protection/1693812/navigating-the-nigeria-data-protection-act-general-application-and-implementation-directive-ndpa-gaid-a-guide-for-businesses)
- GAID tiers: finance and health are "Extra-High Level" sectors; UHL and EHL entities must file annual Compliance Audit Returns via licensed Data Protection Compliance Organisations; one commentary lists registration fees of NGN 250,000 (UHL), NGN 100,000 (EHL), NGN 10,000 (OHL) — not confirmed against the NDPC text. — [Omaplex](https://omaplex.com.ng/critical-assessment-of-the-nigerian-data-protection-act-general-application-and-implementation-directive-2025/); [Mondaq highlights](https://webiis10.mondaq.com/nigeria/data-protection/1624030/highlights-of-the-nigeria-data-protection-act-general-application-and-implementation-directive-2025)

### Inferences
- A gateway that (a) keeps the cache, queue and telemetry on Nigerian soil, (b) strips/pseudonymises PII before any cloud call, and (c) can route sensitive requests to a local model only, is a direct answer to the CBN 2027 deadline and the GAID DPIA burden. Okada's README admits the cache has no PII handling and no encryption at rest, so this is a build item before it can be sold on compliance.
- "Data stays in Nigeria" is likely worth more to banks/PSPs (hard deadline, regulator with teeth) than to SMEs; health (NHIA) rules were not found, so the health compliance pitch should be framed as GAID "extra-high-level sector" obligations rather than a specific NHIA rule.
- Being a processor for an EHL-tier controller means Okada itself would need to be NDPA-registered and auditable; budget for a DPCO audit in year one if selling to fintechs.

### Gaps
- No NDPC guidance specific to AI/LLMs was found (GAID's automated-decision-making provisions are the nearest).
- No NHIA or health-sector data-residency rule was found.
- No source quantifies what buyers pay for data residency; the CBN circular text itself could not be fetched.

---

## Key Question 6: Avenue-by-avenue evaluation (first customer, pricing, what to build, 90-day and 12-month steps, risks) and realism for a solo founder with $0 raised

### Takeaway
On the evidence, the realistic 12-month paths for a solo, unfunded founder are the developer-infra OSS + small hosted tier (Avenue 1), a compliance-led on-prem deployment for one Nigerian fintech/PSP (Avenue 5 variant), and a donor-funded vertical pilot in health or education (Avenue 4/6); hardware manufacturing (Avenue 2 as a box) and telco bundling (Avenue 3) are capital- and relationship-gated. Everything below marked "Inference" is the researcher's synthesis; the cited facts are in Questions 1–5.

### Cited Findings
- Okada's current benchmark and limitations (basis for "what to build"): 100% vs 69.6% answered under simulated degradation; missing multi-tenant cache/PII handling, incremental streaming, queue replay after restart, encryption at rest, tenant isolation, mobile SDK; every request emits an `okada` block and a JSONL telemetry line "the seed of the routing dataset." — [Okada Router README](https://github.com/demimadeit/okada-router)
- Comparable gateway pricing: Portkey $49/mo + $9/100K logs; Helicone Pro $79/mo; LiteLLM enterprise sales-led. — [Dupple](https://dupple.com/learn/best-llm-gateways); [Eden AI](https://www.edenai.co/post/best-portkey-alternatives-7-ai-gateways-compared)
- CBN localisation deadline 1 Jan 2027 for payment data. — [tech.africa](https://tech.africa/?p=88017)
- Viamo pilot metrics (93% valid answers; 46k questions; >60% women). — [Viamo](https://viamo.io/ask-viamo-anything/)
- Horizon 1000: 1,000 clinics by 2028, Rwanda first; Gates/Anthropic $200m health+education. — [OpenAI](https://openai.com/index/horizon-1000/); [GRIP](https://www.grip.globalrelay.com/gates-foundation-expands-ai-partnerships-across-health-education-and-development/)
- Juza AI and Ethiopia offline teacher assistant exist as education precedents; 79% of Ethiopian schools lack reliable internet. — [iHub](https://futureoflearning.ihub.co.ke/startup-directory/juza-ai/); [Kana TV](https://kanatelevision.com/news/offline-artificial-intelligence-tool-launched-to-help-ethiopian-secondary-school-teachers/)
- BRCK and Mara hardware failures; Starlink Nigeria ~98.6k subs after ~3 years. — [Business Daily](https://www.businessdailyafrica.com/bd/corporate/technology/why-six-kenyan-promising-tech-start-ups-fell-3987374); [Africa.com](https://africa.com/top-10-news/a-promising-venture-for-a-made-in-south-africa-smartphone-dashed); [Global Brands Magazine](https://www.globalbrandsmagazine.com/?p=117092)
- N-ATLAS free below 1,000 end users, licence above. — [TechCabal](https://techcabal.com/2025/09/25/nigerian-government-awarri-launch-n-atlas/)
- GSMA operator alliance on African-language models (Oct 2025). — [Engineering News](https://www.engineeringnews.co.za/article/gsma-african-mobile-operators-ai-ecosystem-unite-to-accelerate-development-of-inclusive-african-ai-2025-10-21)
- Nigerian developer base >1.1m (Octoverse via vendor); naira-card USD-billing friction. — [Global Fintech Series](https://globalfintechseries.com/banking/digital-payments/africa-leads-the-world-in-ai-adoption-but-cant-pay-for-it-linkpay-brings-instant-virtual-cards-for-ai-services/); [Grey](https://grey.co/blog/how-to-pay-for-chatgpt-plus-in-nigeria)

### Inferences (avenue designs; researcher synthesis grounded in the findings above)

Avenue 1 — Developer infra: OSS gateway + small hosted tier ("LiteLLM with an Africa-first resilience ladder")
- First customer: a Lagos/Nairobi developer agency or a seed-stage startup already running a customer-facing chatbot on OpenAI/Groq (the 1.1m-developer base and the card-decline threads show the audience exists).
- Pricing anchor: free self-host; hosted team tier $19–29/month (deliberately under Portkey's $49 and Helicone's $79) billed in naira via Paystack/Flutterwave; usage add-on per 100K requests. The naira-billing option itself is a differentiator no comparable offers.
- What to build (90 days): multi-tenant API keys, PII scrubbing in cache, token-level streaming relay, queue replay after restart, a public benchmark page with the 100%-vs-69.6% result reproduced on real Nigerian links (set profile `real` on an MTN/Airtel SIM and a Starlink link), a one-click Railway/Fly/VPS deploy.
- 90-day steps: ship v0.2 with the above; write 3 case-study posts (TechCabal/Techpoint pitch: "we measured X fibre-cut hours and kept answering"); get 10 self-host installs and 3 design partners; Groq/OpenRouter-style free credits for design partners.
- 12-month steps: 50 paying teams at ~$25 = ~$1,250 MRR (honest scale), enterprise on-prem licence for 1–2 fintechs, apply to YC/Antler/Norrsken/Google for Startups Africa.
- Risks: category consolidation (Helicone absorbed, Portkey acquired) shows gateways are features, not companies; LiteLLM/OpenRouter can add a "local fallback" in a release; low willingness to pay below $50/month. Realistic for a solo founder: yes, and it is the prerequisite for every other avenue.

Avenue 2 — "Okada box" edge appliance for SMEs/clinics/schools (sold or leased)
- First customer: a private clinic chain or a school chain that already owns a PC/server per site; the "box" should be an installer image on commodity hardware, not manufactured hardware.
- Pricing anchor: NGN 25,000–60,000/site/month software-plus-support (inferred from what SMEs pay for connectivity: Starlink residential has been NGN 38,000–75,000/month), hardware bought by the customer or financed by an NGO/donor.
- What to build: a self-contained installer (Docker already exists) with local model selection by CPU/RAM, offline queue replay, remote fleet dashboard, auto-updates over flaky links (delta updates, resume), and a solar/UPS power-aware mode.
- 90 days: 3–5 sites with a single chain (pharmacies or clinics in Lagos), measure answered-rate, cache hit rate, data saved (MB), and staff time saved; 12 months: 50–100 sites via one or two chains plus an NGO grant for devices.
- Risks: BRCK and Mara show manufacturing and field-hardware support kill unfunded teams; power (190 days/year grid downtime per the README's own framing) means devices die; support burden per site is high. Realistic solo: only as software-on-your-hardware; manufacturing needs capital and a hardware co-founder.

Avenue 3 — Telco/MNO partnership (bundled network service or zero-rated AI)
- First customer: a telco's own AI chatbot team (MTN's Zigi precedent) or its developer/SME program; alternatively the GSMA African-language-model alliance needing an edge-serving layer.
- Pricing anchor: revenue-share or per-subscriber licence; telcos bundle (Opera Mini 3GB/month, MTN Copilot) rather than pay upfront.
- What to build: APN/zero-rating-aware routing, a model-serving profile for the alliance's Swahili/Nigerian-language models, SLA reporting.
- 90 days: get one warm intro (MTN MoMo/API program, Airtel developer program, ATC/Nigerian Communications Commission innovation events); submit to telco accelerator programs. 12 months: one paid proof-of-concept.
- Risks: procurement cycles of 12–24 months; telcos buy from Huawei/Microsoft/Xtelify; a solo founder has no delivery capacity for a telco SLA. Not realistic in 12 months without a co-founder with telco relationships; keep as an option, do not plan revenue on it.

Avenue 4 — Vertical apps on Okada (offline health assistant, teacher assistant, agri advisory, Pidgin customer-service bot)
- First customer: an implementing NGO or state education/health program (precedents: Juza AI classrooms in Kenya, Ethiopia's offline teacher assistant, Horizon 1000 clinics, Viamo's SDG-aligned questions).
- Pricing anchor: grant-funded pilot (tens of thousands of USD) rather than SaaS; Gates Grand Challenges-style grants and the Gates/Anthropic education and health envelope are the named sources.
- What to build: one vertical only, with a curated knowledge pack (e.g., Nigerian standard treatment guidelines or curriculum) retrieval layer on top of the local model, plus answer-quality evaluation (Viamo's 93% valid-answer metric is the bar funders recognise).
- 90 days: pick one vertical, build a 200-question evaluation set with a domain partner, run with 5 sites; 12 months: a funded pilot of 20–50 sites with published results.
- Risks: domain liability (health), language quality of small local models in Yoruba/Hausa/Igbo/Pidgin (N-ATLAS is 8B and not yet an app; the Horizon 1000 language concern shows this is a live problem), scope creep away from the gateway. Realistic solo: yes for one vertical with a domain partner; needs a clinician/teacher collaborator.

Avenue 5 — OSS + managed cloud / on-prem with Nigerian data residency ("hosted Okada on Lagos edge")
- First customer: one fintech/PSP or microfinance bank facing the 1 Jan 2027 CBN localisation deadline that uses LLMs for support or KYC document reading.
- Pricing anchor: on-prem/VPC licence in naira (NGN 1–5m/year inferred from local enterprise software norms; no public comparable found) or hosted at ~$200–500/month on a Lagos VPS/GPU slice (Kasi Cloud, Africa Data Centres rates not found).
- What to build: encryption at rest, PII redaction before cloud calls, "Nigeria-only" routing policy, audit logs (the same features LiteLLM sells as enterprise), DPIA-ready documentation; register with NDPC.
- 90 days: write the compliance one-pager mapping Okada controls to GAID/CBN requirements; get a DPCO to review; land one paid pilot. 12 months: 3–5 on-prem deployments; this is the most plausible route to five-figure USD revenue for a solo founder.
- Risks: enterprise sales cycles, security review burden, the founder becomes a consultancy. Realistic solo: yes, but it needs a security hardening sprint first.

Avenue 6 — Government/NGO/donor projects
- First customer: implementing partners of Horizon 1000 (if/when it reaches Nigeria), Gates/Anthropic education grantees, GIZ/UNICEF country offices (no offline-LLM pilots found, so cold outreach).
- Pricing: grants and subcontracts; donor procurement favours registered entities with audited accounts.
- 90 days: register a company, publish the open-source benchmark and a "connectivity-resilient AI for clinics" white paper (docs/whitepaper.html already exists), apply to 3 calls. 12 months: one subcontract.
- Risks: slow, reporting-heavy, and dependent on partner relationships; Rwanda-first programs may not reach Nigeria in 12 months. Realistic solo: partially; better as a funding source for Avenue 4 than a business model.

Avenue 7 — Mobile SDK licensing to app developers
- First customer: a Nigerian consumer app with an in-app assistant (Opera Mini's Aria rollout shows the pattern at scale).
- Pricing: per-MAU or flat licence; comparables not found.
- What to build: the README states no mobile SDK exists; on-device small-model inference plus queue-and-sync on Android is a multi-month build.
- Risks: on-device inference on low-end Android is constrained; platform vendors (Google, Opera) can bundle it. Not realistic in 90 days for a solo founder; a 12-month item only if a mobile engineer joins.

Avenue 8 — Data play: routing/telemetry dataset and African-language prompt corpus
- First customer: the GSMA operator alliance, N-ATLAS/Awarri, academic groups, and model vendors wanting African network-condition and language data.
- Pricing: licensing or research partnerships; no comparable price found.
- What to build: consented, anonymised telemetry export (route, network state, latency, fallback) and an opt-in prompt corpus with PII removal; a public "African network conditions for AI" dataset would also be marketing for Avenue 1.
- Risks: NDPA/GAID obligations on prompt data; tiny volume until Avenues 1/4/5 produce traffic. Realistic solo: as a by-product only; not a revenue line in 12 months.

Hype check (researcher's assessment)
- Realistic in 12 months for one unfunded person: a hardened OSS gateway with a few hundred installs, 1–3 paid on-prem/compliance deployments, one grant-funded vertical pilot with published metrics, and a public dataset/benchmark. Revenue on the order of low tens of thousands of USD is plausible; SaaS MRR from African startups alone will be small.
- Needs a co-founder or hire: telco channel (Avenue 3), mobile SDK (7), any hardware (2), and enterprise security certifications.
- Needs capital: manufacturing, Lagos GPU hosting at scale, multi-country rollout.
- "Next Starlink" framing: Starlink Nigeria has ~99k subscribers after three years with SpaceX's balance sheet; ubiquity in Africa historically came via telco bundles (Opera Mini) and basic-phone channels (Viamo), so the Starlink-like outcome for Okada is "default resilience layer inside other people's apps and NGO deployments," reached through open-source distribution, not a premium product.

Pilot designs and convincing metrics (inference from Okada's own telemetry fields and the Viamo/Horizon 1000 evidence)
- Pharmacies/clinics (5 sites, Lagos): answered-rate during outages vs a direct-cloud control, % requests served locally/cached, MB of data saved, median latency, staff minutes saved per query, clinician-rated answer validity (Viamo's 93% is the reference).
- Bank/PSP branch or support team: answered-rate during a NIBSS/fibre incident window, cost per 1k requests (cloud vs Okada with cache), share of requests that never left Nigeria, audit-log completeness for DPIA.
- School chain: lessons/sessions completed offline, sync success after reconnect, cost per student per month.

### Gaps
- No public naira price for any Nigerian enterprise AI/software licence was found; pricing anchors above for Avenues 2, 5, 7, 8 are inferences.
- No evidence of any African company currently paying for an AI gateway as a category.
- Realistic GPU/VPS rental rates in Lagos (Kasi Cloud, Africa Data Centres) were not found.
- Searches on M-KOPA (PAYG hardware financing), Tizeti/Wi-Flix, Kiwix, Ushahidi, Safaricom AI and Nigerian clinic AI pilots could not be run before the budget ended; these would strengthen Avenues 2, 4 and 6.

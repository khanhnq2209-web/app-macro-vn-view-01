# Plan: Data API platform (07/10/2026) — draft, awaiting decisions

## Why

| Today | With a data API |
|---|---|
| Data files committed to the app repo (~34 MB, incl. licensed vendor data) | Repo holds code only; data lives in a database behind the API |
| Licensed data hidden only in the UI (`SHOW_VENDOR_DATA`) | Licensing enforced on the server: a token only gets the sources its scope allows |
| Refresh = run on a laptop, rebuild, git push | Scheduled ingestion jobs; app always reads the latest |
| dulieukinhte free quota (100 calls/month) spent per laptop | One central fetch, shared by every consumer |
| Only this Streamlit app can use the data | Any consumer with a token: this app, Excel/Power BI, notebooks, other apps |
| Revised numbers overwrite old ones | Every fetch stored as a vintage → "as-of" history, audit, no look-ahead in backtests (roadmap A2) |

## Target architecture

```
 Sources (FRED, Yahoo, CME, VBMA, LME, Simplize, dulieukinhte API, Excel inbox)
        │  ingestion jobs (existing io/* modules, scheduled)
        ▼
 Database ── raw_observations (series_id, date, value, source, vintage_at)
         ├── indicators (computed by existing recipes/*)       ── catalog (config/catalog.yaml)
         ├── scorecards (profiles, rows, history)              ── forecast_map, profiles
         └── api_keys (hashed), usage_log
        │
        ▼
 Data API (FastAPI, /v1, HTTPS, token)  ──►  Streamlit app (token in Secrets)
                                        ──►  Excel / Power BI / notebooks / other apps
```

Most logic is reused as-is: `io/*` (fetch), `metrics/recipes.py` + `transforms.py` (indicators),
`metrics/scorecard.py` (scores), `metrics/forward.py` (plans/forecasts). Only the storage and the
app's data loader (`ui/data.py`) change.

## API (v1, read endpoints first)

| Endpoint | Returns |
|---|---|
| `GET /v1/indicators` | Catalog: code, name, unit, frequency, source, last date |
| `GET /v1/indicators/{code}/observations?from&to&as_of` | Time series (optionally as known on a past date) |
| `GET /v1/latest` | Latest value, change, status for all indicators (Overview table) |
| `GET /v1/scorecards/{profile}/{segment}` | Score, rows, history, plan/forecast columns |
| `GET /v1/fedwatch?asof` | Meeting × rate-range probabilities, expected path |
| `GET /v1/forecasts` | Indicator → plan/forecast mapping with values |
| `POST /v1/refresh/{source}` (admin scope) | Trigger an ingestion job |
| `PUT /v1/profiles/{slug}`, `PUT /v1/forecasts` (admin scope) | Replace config files edited in the app |

Auth: `Authorization: Bearer <token>`.
- Tokens are random, stored hashed, and can be revoked or rotated.
- Each token has scopes:
  - `read:public`: FRED, GSO/VBMA, government targets.
  - `read:licensed`: Yahoo, LME, CME, Simplize, dulieukinhte, S&P PMI.
  - `admin`: refresh and config writes.
- Each token has a rate limit, and every call is written to a usage log.
- Tokens never appear in logs or error messages.

## Hosting options (decision needed)

| | A. Managed (Supabase) | B. FastAPI + Postgres (recommended) | C. Files in a private bucket |
|---|---|---|---|
| What | Postgres + auto REST + API keys + row-level security | Own API service (Cloud Run / Render / company server) + Postgres (Neon or internal) | Parquet files on S3/R2 behind signed URLs |
| Build effort | Lowest (tables + policies) | Medium (~1–2 weeks) | Lowest |
| Fits "platform API" for many consumers | Partly (generic table REST, scorecard logic must live elsewhere) | Yes (endpoints shaped for consumers, reuse Python logic) | No (file download, no query/as-of/scopes) |
| Licensing enforcement | Row-level policies | Scopes in code | Per-bucket only |
| Ops | Vendor-managed | You run one service + DB | Minimal |
| Cost (indicative, verify) | Free tier → paid by usage | Free/low tiers for a small service + DB | Very low |

Recommendation: **B**, ideally on company infrastructure (internal hub) if available. It reuses the
existing Python code and gives a real multi-consumer API with server-side licensing control. If speed
matters more than shape, start with A and move later.

## Phases

| # | Phase | Output | Test (DoD) | Estimate |
|---|---|---|---|---|
| 0 | Decide hosting + DB, licensing check | Decisions in spec | — | — |
| 1 | Schema + migration | Tables; current store and vintages loaded | Row counts and control totals match current `series.parquet` | 1–2 days |
| 2 | Ingestion jobs → DB, scheduled | Daily / weekly jobs, stale-data alerts | Job writes a new vintage; failure keeps previous data | 1–2 days |
| 3 | Read API + tokens/scopes | `/v1` read endpoints, key management CLI | Golden tests: API output = current app numbers; licensed data refused without scope | 2–3 days |
| 4 | App switches to API client | `ui/data.py` calls API (token in Secrets), local-file fallback for dev | Full pytest + screenshots identical; repo no longer contains data | 1 day |
| 5 | Admin endpoints + config in DB | Profiles / forecast map edited via API | Edit in app → visible to other consumers | 1–2 days |
| 6 | Other consumers | Excel / Power BI connector guide, OpenAPI docs | One external consumer reads with its own token | 0.5 day |

## Open questions

1. **Hosting:**
   - Company server or internal hub, or a public cloud?
   - Is there an existing company Postgres to use?
2. **Consumers:** only this app, or also Power BI, Excel, other teams?
   - This decides how many tokens and scopes are needed.
3. **Licensing:** do the Simplize, dulieukinhte, CME and S&P terms allow serving the data through an internal API to multiple internal users?
   - dulieukinhte requires attribution and limits calls by plan.
   - Yahoo and LME are personal or non-redistributable.
4. **Refresh cadence and freshness SLA per source:** daily markets, monthly Vietnam data.

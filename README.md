# Finvia — SME Financial Intelligence App

Mobile-first SME finance web app / PWA prototype:

- **Cash-flow forecasting & financing referral** — upload transactions, see an interactive 7/14/30-day forecast with likely range, upcoming payments and weekly view, tap Available cash for a full breakdown, spot a possible shortfall and (with consent) request a referral to a participating bank. The bank decides; Finvia does not approve loans.
- **Tax-incentive signals & documents** — flag potentially relevant expenses and keep supporting documents together. Signals are indicative only.
- **Annual Tax-Incentive Report** — signals, documents and next steps.

**Sign-in:** Supabase Auth (email + password). Confirmation emails are sent through Brevo SMTP, configured in the Supabase dashboard.

## Technologies used

| Layer | Technology | Role |
|---|---|---|
| Backend | Python 3.12, FastAPI 0.116.1, Uvicorn 0.35.0 | REST API, static file serving, security headers, upload limits |
| Data processing | pandas 2.3.2, openpyxl 3.1.5, xlrd 2.0.1 | Read CSV/XLSX/XLS statements, build forecast and tax signals |
| Authentication | Supabase Auth (email + password); Brevo SMTP | Sign-up/sign-in, HttpOnly cookie session, confirmation emails |
| Frontend | HTML, CSS, vanilla JavaScript, SVG charts | Mobile-first single-page interface |
| PWA | Web app manifest, service worker | Installable app, cached app shell |
| Testing / CI | pytest 8.4.1, httpx 0.28.1, GitHub Actions | Automated backend tests, container /health check |
| Packaging / cloud | Docker, Amazon ECR, AWS ECS Express Mode | One image serving API and frontend on port 8080 |
| Tools | Visual Studio Code, Git/GitHub, AI assistants (Claude) | Editing, version control, code and test generation |

## Brand colours

`#dfeeff` background · `#a9cbf7` panel · `#2124a0` indigo · `#021b3a` navy · `#2f7bff` bright blue · `#f0ccff` pink accent · Poppins.

## Layout

```
backend/    FastAPI app (main.py, auth.py, supabase_client.py, analysis.py), requirements, tests
frontend/   index.html, app.css, app.js, PWA manifest, service worker, icons
aws/        setup.sh — one-time AWS setup
docs/       AWS deployment guide
Dockerfile  single image: API + frontend on port 8080
.github/    CI (tests + image build) and deploy to ECS Express Mode
```

Only `frontend/` is served publicly; source code and uploads are never exposed.

## Note for reviewers

- **Easiest way to review:** open the live prototype at https://fi-fc120b2209524842b70c60b1814dc4ef.ecs.ap-southeast-2.on.aws (demo only; please do not upload real bank statements).
- **Running the folder yourself:** the app needs two environment variables, `SUPABASE_URL` and `SUPABASE_KEY` (the Supabase project URL and public anon key). Without them sign-in will not work. Set them with `export` (see below) or in a `backend/.env` file.
- The automated tests do not need Supabase (sign-in is simulated in the tests).

## Run locally

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
export SUPABASE_URL=your-project-url
export SUPABASE_KEY=your-anon-key
cd backend && uvicorn main:app --reload --port 8000     # http://127.0.0.1:8000
python -m pytest -q                                      # run the tests
```

Docker: `docker build -t finvia . && docker run --rm -p 8080:8080 finvia`

## Deploy to AWS

See [docs/AWS-ECS-EXPRESS.md](docs/AWS-ECS-EXPRESS.md).

## Upload format

CSV/XLSX/XLS with a date column and either one amount column (negative = money out, or a `Type` column of Debit/Credit) or separate `Debit`/`Credit` (`Money Out`/`Money In`) columns; optional description and balance. Comma, semicolon or tab separated; title lines above the table, `RM 1,200.00`, `(300.00)` negatives and `dd/mm/yyyy` or `yyyy-mm-dd` dates are all handled. PDF/JPG/PNG are stored but not analysed yet. Max 10 MB.

## How the forecast works

Repeating payments (payroll, rent, weekly suppliers...) are detected from the history and projected on their usual rhythm. Everything else follows your typical money in / money out for each day of the week. The shaded band is a likely range that widens over time. The cash buffer is set to about two weeks of your average spending.

## Troubleshooting

- **"Cannot reach the Finvia server" when uploading:** the page is open but the API is not running or not reachable. Open `/health` on the same address; it must return `{"status":"ok"}`. Locally run `uvicorn main:app --port 8010` from `backend/` (do not serve `frontend/` with a plain static server). On AWS check the ECS service logs in CloudWatch.
- **After a new deploy,** hard-refresh once (Cmd+Shift+R) so the old service worker cache is replaced.

## Limitations

Demo prototype, not a banking or tax platform. Forecasts are estimates; tax signals do not confirm eligibility. Each signed-in user has a private in-memory workspace that resets when the container restarts.

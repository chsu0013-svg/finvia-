# Finvia — SME Financial Intelligence App

Mobile-first SME finance web app / PWA prototype:

- **Cash-flow forecasting & financing referral** — upload transactions, see a 7/14/30-day forecast, spot a possible shortfall and (with consent) request a referral to a participating bank. The bank decides; Finvia does not approve loans.
- **Tax-incentive signals & documents** — flag potentially relevant expenses and keep supporting documents together. Signals are indicative only.
- **Annual Tax-Incentive Report** — signals, documents and next steps.

## Brand colours
`#dfeeff` background · `#a9cbf7` panel · `#2124a0` indigo · `#021b3a` navy · `#2f7bff` bright blue · `#f0ccff` pink accent · Poppins.

## Layout
```
backend/    FastAPI app (main.py, analysis.py), requirements, tests
frontend/   index.html, app.css, app.js, PWA manifest, service worker, icons
aws/        setup.sh — one-time AWS setup
docs/       AWS deployment guide
Dockerfile  single image: API + frontend on port 8080
.github/    CI (tests + image build) and deploy to ECS Express Mode
```
Only `frontend/` is served publicly; source code and uploads are never exposed.

## Run locally
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend && uvicorn main:app --reload --port 8000     # http://127.0.0.1:8000
python -m pytest -q                                      # run the tests
```
Docker: `docker build -t finvia . && docker run --rm -p 8080:8080 finvia`

## Deploy to AWS
See [docs/AWS-ECS-EXPRESS.md](docs/AWS-ECS-EXPRESS.md).

## Upload format
CSV/XLSX/XLS with a `Date` column and either `Amount`, or `Debit` + `Credit`; optional `Description` and `Balance`. PDF/JPG/PNG are stored but not analysed yet. Max 10 MB.

## Limitations
Demo prototype, not a banking or tax platform. Forecasts are estimates; tax signals do not confirm eligibility. Each browser gets a private in-memory workspace that resets when the container restarts.

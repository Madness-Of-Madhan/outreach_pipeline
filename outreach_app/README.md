# Outreach Pipeline

automated cold-outreach tool i built for the vocallabs assignment.
one input (seed domain) -> finds lookalike companies -> finds decision makers -> gets their emails -> sends outreach. all automatic.

## how it works

1. you type a company domain (like openai.com)
2. ocean.io finds 10 similar companies
3. prospeo finds the ceos/vps at each company + their linkedin
4. prospeo enrich gets their verified work email from linkedin
5. brevo sends a personalized email to each person

## setup

### 1. install dependencies

```
pip install -r requirements.txt
```

### 2. add your api keys

open `backend/pipeline.py` and fill in:

```python
OCEAN_API_KEY   = "your key here"
PROSPEO_API_KEY = "your key here"
BREVO_API_KEY   = "your key here"
SENDER_EMAIL    = "you@yourdomain.com"   # must be verified in brevo
SENDER_NAME     = "Your Name"
```

### 3. run it

```
cd backend
python app.py
```

then open http://localhost:5000 in your browser.

## project structure

```
outreach_app/
  backend/
    app.py          # flask server + SSE streaming
    pipeline.py     # all 4 stages of the pipeline
  frontend/
    index.html      # the UI
  requirements.txt
  README.md
```

## notes

- i used prospeo for email enrichment instead of eazyreach because eazyreach account activation was slow. same result — verified work emails.
- the frontend uses server-sent events (SSE) to stream logs in real time so you can see what's happening
- rate limiting is handled automatically — prospeo allows 1 search/sec so there's a built-in wait
- brevo sends all emails in one batch call
- only charges a credit when a VERIFIED email is found (prospeo's `only_verified_email: true`)

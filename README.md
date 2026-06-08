Outreach Pipeline
An automated B2B outreach tool that finds lookalike companies, locates decision-makers, verifies their work emails, and sends personalized cold emails — all from a single domain input.

How It Works
The pipeline runs 4 stages sequentially:

Ocean.io — Takes a seed domain (e.g. stripe.com) and returns 10 similar companies
Prospeo Search — For each company, finds decision-makers (C-Suite, VPs, Directors, Founders)
Prospeo Enrich — Resolves LinkedIn profiles to verified work emails
Brevo — Sends personalized cold emails to everyone with a verified email

Progress streams live to the browser via Server-Sent Events (SSE).

Project Structure
outreach_app/
├── backend/
│   ├── app.py          # Flask server + SSE streaming endpoint
│   └── pipeline.py     # Core pipeline logic (4 stages)
└── frontend/
    └── index.html      # Single-page UI with live logs and results table

Prerequisites

Python 3.8+
pip


Setup
1. Clone or download the project
bashcd outreach_app
2. Create and activate a virtual environment
bashpython -m venv env

# Windows
env\Scripts\activate

# macOS / Linux
source env/bin/activate
3. Install dependencies
bashpip install flask flask-cors requests pandas
4. Add your API keys
Open backend/pipeline.py and replace the placeholder values:
pythonOCEAN_API_KEY   = "your_ocean_api_key"
PROSPEO_API_KEY = "your_prospeo_api_key"
BREVO_API_KEY   = "your_brevo_api_key"

SENDER_EMAIL = "you@yourdomain.com"   # must be verified in Brevo
SENDER_NAME  = "Your Name"

Recommended: Use a .env file instead of hardcoding keys (see Environment Variables below).

5. Verify your Brevo sender
Before emails will send, your sender address must be verified in Brevo:

Go to app.brevo.com → Senders & IP → Senders
Add your email address and click the verification link Brevo sends you


Running the App
bashcd backend
python app.py
Then open your browser and go to:
http://localhost:5000

Important: Always open the app via http://localhost:5000, not by double-clicking index.html. Opening the file directly (file:///...) will cause CORS errors and the pipeline won't connect.


Usage

Enter a seed domain in the input field (e.g. hubspot.com, notion.so)
Click Run Pipeline
Watch the live log stream as each stage runs
View the results table when the pipeline completes — it shows every contact, their email, and whether an email was sent


API Keys — Where to Get Them
ServicePurposeSign upOcean.ioLookalike company discoveryocean.io/pricingProspeoPeople search + email enrichmentprospeo.ioBrevoTransactional email sendingbrevo.com

Environment Variables
Instead of hardcoding keys, store them in a .env file:
bash# .env
OCEAN_API_KEY=your_key_here
PROSPEO_API_KEY=your_key_here
BREVO_API_KEY=your_key_here
SENDER_EMAIL=you@yourdomain.com
SENDER_NAME=Your Name
Then install python-dotenv and load them in pipeline.py:
bashpip install python-dotenv
pythonimport os
from dotenv import load_dotenv
load_dotenv()

OCEAN_API_KEY   = os.getenv("OCEAN_API_KEY")
PROSPEO_API_KEY = os.getenv("PROSPEO_API_KEY")
BREVO_API_KEY   = os.getenv("BREVO_API_KEY")
SENDER_EMAIL    = os.getenv("SENDER_EMAIL")
SENDER_NAME     = os.getenv("SENDER_NAME")
Add .env to your .gitignore so keys are never committed:
.env
env/
__pycache__/

Rate Limits
APILimitNotesProspeo Search1 req/sec, ~50–100/day (free)Pipeline waits automatically; stops early if daily limit hitProspeo Enrich5 req/secOnly charges a credit when a verified email is foundBrevo300 emails/day (free)Upgrade for higher volume

Troubleshooting
"Connection error" in the browser log
Open the app via http://localhost:5000, not by opening the HTML file directly.
Stage 1 fails immediately
Your Ocean.io API key is invalid or expired. Test it:
bashpython -c "import requests; r = requests.post('https://api.ocean.io/v3/search/companies', headers={'X-Api-Token': 'YOUR_KEY', 'Content-Type': 'application/json'}, json={'size': 2, 'companiesFilters': {'lookalikeDomains': ['stripe.com']}}); print(r.status_code, r.text[:200])"
"daily limit hit" in stage 2
You've used up your Prospeo daily search quota. Wait until midnight UTC for it to reset.
Stage 4 sends 0 emails

Make sure SENDER_EMAIL is verified in your Brevo account
Add temporary debug logging to see the exact Brevo error:

python  print(f"BREVO STATUS: {resp.status_code}")
  print(f"BREVO RESPONSE: {resp.text}")
Lookalike results look unrelated
Ocean.io's free/trial tier has limited data quality. Try well-known B2B seed domains like stripe.com, hubspot.com, or notion.so for better results.

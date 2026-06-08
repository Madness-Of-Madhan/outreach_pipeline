import requests
import time
import pandas as pd

# --- put your api keys here ---
# pip install python-dotenv
from dotenv import load_dotenv
import os
load_dotenv()

OCEAN_API_KEY   = os.getenv("OCEAN_API_KEY")
PROSPEO_API_KEY = os.getenv("PROSPEO_API_KEY")
BREVO_API_KEY   = os.getenv("BREVO_API_KEY")

SENDER_EMAIL = "mathiappa2@gmail.com"
SENDER_NAME  = "skcet1"

PROSPEO_HEADERS = {
    "X-KEY": PROSPEO_API_KEY,
    "Content-Type": "application/json"
}

TARGET_SENIORITY = ["C-Suite", "Vice President", "Founder/Owner", "Director"]


# i had to add this because prospeo rate limits at 1 req/sec
# learned this the hard way after getting 429s lol
class RateLimiter:
    def __init__(self, per_sec, name):
        self.per_sec     = per_sec
        self.name        = name
        self.min_left    = None
        self.day_left    = None
        self.min_reset   = None

    def update(self, headers):
        def gi(k):
            v = headers.get(k)
            return int(v) if v else None
        self.min_left  = gi("x-minute-request-left")
        self.day_left  = gi("x-daily-request-left")
        self.min_reset = gi("x-minute-reset-seconds")

    def wait(self):
        time.sleep(1.0 / self.per_sec)
        if self.min_left is not None and self.min_left <= 2:
            secs = (self.min_reset or 60) + 2
            time.sleep(secs)
        if self.day_left is not None and self.day_left <= 1:
            raise Exception(f"{self.name}: daily limit hit")

rl_search = RateLimiter(1, "search")
rl_enrich = RateLimiter(5, "enrich")


# stage 1 - ocean.io
# give it a seed domain, get back lookalike company domains
def get_lookalikes(seed_domain, count=10):
    try:
        resp = requests.post(
            "https://api.ocean.io/v3/search/companies",
            headers={
                "X-Api-Token": OCEAN_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "size": count,
                "companiesFilters": {
                    "lookalikeDomains": [seed_domain],
                    "excludeDomains":   [seed_domain]
                }
            },
            timeout=30
        )
    except requests.exceptions.ConnectionError as e:
        raise Exception(f"Ocean.io: could not connect - {e}")
    except requests.exceptions.Timeout:
        raise Exception("Ocean.io: request timed out")

    if resp.status_code == 401:
        raise Exception("Ocean.io: invalid API key")
    if resp.status_code == 403:
        raise Exception("Ocean.io: forbidden - check plan/permissions")
    if resp.status_code != 200:
        raise Exception(f"Ocean error: {resp.status_code} - {resp.text[:200]}")

    data = resp.json()
    domains = []
    for item in data.get("companies", []):
        company = item.get("company", {})
        d = company.get("domain", "")
        if d:
            domains.append(d)

    return domains


# stage 2 part 1 - prospeo search
# for each domain find the decision makers (ceo, vp etc)
def search_people(domain, retry=0):
    rl_search.wait()

    try:
        resp = requests.post(
            "https://api.prospeo.io/search-person",
            headers=PROSPEO_HEADERS,
            json={
                "page": 1,
                "filters": {
                    "company": {"websites": {"include": [domain]}},
                    "person_seniority": {"include": TARGET_SENIORITY},
                    "max_person_per_company": 5
                }
            },
            timeout=30
        )
    except Exception as e:
        return []

    rl_search.update(dict(resp.headers))

    if resp.status_code == 429:
        if retry >= 2:
            return []
        wait = int(resp.headers.get("x-minute-reset-seconds", 60)) + 3
        time.sleep(wait)
        return search_people(domain, retry + 1)

    try:
        data = resp.json()
    except:
        return []

    if data.get("error"):
        code = data.get("error_code", "")
        if code == "INSUFFICIENT_CREDITS":
            raise Exception("prospeo: out of credits")
        return []

    return data.get("results", [])


def parse_person(result, source_domain):
    p = result.get("person", {})
    d = p.get("data", p)

    linkedin = (
        d.get("linkedin_url") or
        d.get("linkedin_profile_url") or
        (d.get("socials") or {}).get("linkedin") or
        ""
    )

    return {
        "full_name":      f"{d.get('first_name','')} {d.get('last_name','')}".strip(),
        "company_name":   d.get("company_name", source_domain),
        "company_domain": d.get("company_website", source_domain),
        "linkedin_url":   linkedin,
        "work_email":     ""
    }


# stage 2 part 2 - prospeo enrich
# takes linkedin url -> returns verified work email
# only charges a credit if it actually finds a verified email
def get_email(person, retry=0):
    linkedin = person.get("linkedin_url", "")
    if not linkedin:
        return ""

    rl_enrich.wait()

    try:
        resp = requests.post(
            "https://api.prospeo.io/enrich-person",
            headers=PROSPEO_HEADERS,
            json={
                "only_verified_email": True,
                "data": {"linkedin_url": linkedin}
            },
            timeout=20
        )
    except:
        return ""

    rl_enrich.update(dict(resp.headers))

    if resp.status_code == 429:
        if retry >= 2:
            return ""
        wait = int(resp.headers.get("x-minute-reset-seconds", 60)) + 3
        time.sleep(wait)
        return get_email(person, retry + 1)

    try:
        data = resp.json()
    except:
        return ""

    if data.get("error"):
        code = data.get("error_code", "")
        if code == "INSUFFICIENT_CREDITS":
            raise Exception("prospeo enrich: out of credits")
        return ""

    email_obj = data.get("person", {}).get("email", {})
    email  = email_obj.get("email", "")
    status = email_obj.get("status", "")

    if email and status == "VERIFIED":
        return email
    return ""


# stage 4 - brevo
# sends personalized emails in one batch call
def send_emails(contacts, log_fn=None):
    if not contacts:
        return {"sent": 0, "error": "no contacts"}

    EMAIL_SUBJECT = "Quick question about {{params.company_name}}"

    EMAIL_HTML = """<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; font-size: 15px; color: #222; max-width: 580px; margin: 0 auto; padding: 20px;">

<p>Hi {{params.first_name}},</p>

<p>I came across <strong>{{params.company_name}}</strong> and was really impressed by the work you're doing.</p>

<p>I'm building tools that help companies like yours find and reach the right people faster — without spending hours doing it manually.</p>

<p>Would love to show you what it looks like. Got 15 minutes this week?</p>

<p>Best,<br>
<strong>{{params.sender_name}}</strong><br>
<a href="mailto:{{params.sender_email}}">{{params.sender_email}}</a>
</p>

<p style="font-size: 11px; color: #aaa; margin-top: 40px;">
Reply "unsubscribe" to stop receiving emails.
</p>

</body>
</html>"""

    versions = []
    for c in contacts:
        name  = c.get("full_name", "there")
        fname = name.strip().split()[0] if name.strip() else "there"
        co    = c.get("company_name", "your company")
        email = c.get("work_email", "")

        if not email:
            continue

        versions.append({
            "to": [{"email": email, "name": name}],
            "subject": f"Quick question about {co}",
            "params": {
                "first_name":   fname,
                "company_name": co,
                "sender_name":  SENDER_NAME,
                "sender_email": SENDER_EMAIL
            }
        })

    if not versions:
        return {"sent": 0, "error": "no valid emails"}

    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "accept":       "application/json",
            "api-key":      BREVO_API_KEY,
            "content-type": "application/json"
        },
        json={
            "sender":          {"email": SENDER_EMAIL, "name": SENDER_NAME},
            "subject":         EMAIL_SUBJECT,
            "htmlContent":     EMAIL_HTML,
            "messageVersions": versions
        },
        timeout=30
    )

    if resp.status_code == 201:
        ids = resp.json().get("messageIds", [])
        return {"sent": len(ids), "message_ids": ids}
    else:
        return {"sent": 0, "error": resp.json()}


# runs all 4 stages, calls log_fn(msg) to stream progress to the frontend
def run_pipeline(seed_domain, log_fn=None):
    def log(msg):
        if log_fn:
            log_fn(msg)

    results = {
        "seed": seed_domain,
        "domains": [],
        "contacts": [],
        "emails_sent": 0,
        "errors": []
    }

    # stage 1
    log(f"[stage 1] finding lookalikes for {seed_domain}...")
    try:
        domains = get_lookalikes(seed_domain)
        results["domains"] = domains
        log(f"[stage 1] found {len(domains)} companies: {', '.join(domains)}")
    except Exception as e:
        results["errors"].append(str(e))
        log(f"[stage 1] failed: {e}")  # this already exists
        log(f"[stage 1] exception type: {type(e).__name__}")  # add this
        return results

    if not domains:
        results["errors"].append("no lookalike domains found")
        return results

    # stage 2 - search
    log(f"[stage 2] searching for decision makers...")
    all_contacts = []
    for i, domain in enumerate(domains):
        log(f"[stage 2] ({i+1}/{len(domains)}) searching {domain}")
        try:
            people = search_people(domain)
            for p in people:
                all_contacts.append(parse_person(p, domain))
            log(f"[stage 2] {domain} -> {len(people)} people")
        except Exception as e:
            log(f"[stage 2] {domain} error: {e}")
            results["errors"].append(str(e))
            break

    log(f"[stage 2] total contacts found: {len(all_contacts)}")

    # stage 2 - enrich emails
    log(f"[stage 3] enriching emails via prospeo...")
    for i, contact in enumerate(all_contacts):
        log(f"[stage 3] ({i+1}/{len(all_contacts)}) {contact['full_name']}")
        try:
            email = get_email(contact)
            contact["work_email"] = email
            if email:
                log(f"[stage 3] got email: {email}")
        except Exception as e:
            log(f"[stage 3] error: {e}")
            results["errors"].append(str(e))
            break

    # only keep people we have emails for
    with_email = [c for c in all_contacts if c.get("work_email")]
    results["contacts"] = all_contacts

    log(f"[stage 3] {len(with_email)} contacts have verified emails")

    if not with_email:
        log("[stage 4] no emails to send, stopping")
        return results

    # stage 4
    log(f"[stage 4] sending {len(with_email)} emails via brevo...")
    try:
        send_result = send_emails(with_email, log_fn=log)
        results["emails_sent"] = send_result.get("sent", 0)
        results["message_ids"] = send_result.get("message_ids", [])
        log(f"[stage 4] sent {results['emails_sent']} emails!")
    except Exception as e:
        log(f"[stage 4] brevo error: {e}")
        results["errors"].append(str(e))

    return results

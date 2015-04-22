"""Check emails to prose@lifelinter.com, lint them, and reply."""

from apscheduler.schedulers.blocking import BlockingScheduler
import gmail
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from worker import conn
import requests
import hashlib
import json
import os
import logging

logging.basicConfig()
scheduler = BlockingScheduler()

# Settings
user = "hello@lifelinter.com"
user_to = "prose@lifelinter.com"
name = "proselint"
password = os.environ['gmail_password']

tagline = "Linted by proselint"
url = "http://prose.lifelinter.com"
api_url = "http://api.prose.lifelinter.com/v0/"


@scheduler.scheduled_job('interval', minutes=0.25)
def check_email():
    """Check the mail account and lint new mail."""
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(user, password)

    g = gmail.login(user, password)

    # Check for unread messages.
    unread = g.inbox().mail(unread=True)

    # Submit a job to lint each email sent to prose@lifelinter.com. Record the
    # resulting job_ids somewhere (in Redis, I suppose), keyed by a hash of the
    # email.
    for u in unread:

        u.fetch()

        signature = (u.fr.decode('utf-8') +
                     u.subject.decode('utf-8') +
                     u.body.decode('utf-8'))

        hash = hashlib.sha256(signature.encode('utf-8')).hexdigest()

        if user_to in u.to or user_to in u.headers['Cc']:

            job_id = conn.get(hash)

            if not job_id:
                # If the email hasn't been sent for processing, send it.
                r = requests.post(api_url, data={"text": u.body})
                conn.set(hash, r.json()["job_id"])

            else:
                # Otherwise, check whether the results are ready, and if so,
                # reply with them.
                r = requests.get(api_url, params={"job_id": job_id})

                if r.json()["status"] == "success":

                    errors = json.dumps(r.json()['data'])

                    msg = MIMEMultipart()
                    msg["From"] = "{} <{}>".format(name, user)
                    msg["To"] = u.fr
                    msg["Subject"] = "Re: " + u.subject

                    msg.add_header("In-Reply-To", u.headers['Message-ID'])
                    msg.add_header("References", u.headers['Message-ID'])

                    body = errors + "\n\n--\n" + tagline + "\n" + url
                    msg.attach(MIMEText(body, "plain"))

                    text = msg.as_string()
                    server.sendmail(user, u.fr, text)

                    # Mark the email as read.
                    u.read()
                    u.archive()

scheduler.start()
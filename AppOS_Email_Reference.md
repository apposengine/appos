# AppOS — Email Reference

> **Referenced from:** `AppOS_Design.md` §5.5 Connected System  
> **Version:** 2.1 — February 12, 2026

---

## Overview

AppOS integrates with **Microsoft Outlook** (Exchange Online / Microsoft Graph API) for email send and receive. Email is NOT a built-in object type — it uses the existing Connected System + Integration architecture.

---

## Architecture

### Sending Email

Uses a Connected System of type `smtp` or `rest_api` (Microsoft Graph).

```python
@connected_system(
    name="outlook_email",
    type="rest_api",
    description="Microsoft Graph API for Outlook email"
)
def outlook_email():
    return {
        "default": {
            "base_url": "https://graph.microsoft.com/v1.0",
            "timeout": 30,
        },
        "auth": {
            "type": "oauth2",
            "grant_type": "client_credentials",
            "tenant_id": "...",         # managed in admin console
            "client_id": "...",         # managed in admin console
            "scope": "https://graph.microsoft.com/.default",
        },
    }
```

### Sending via Integration

```python
@integration(connected_system="outlook_email")
def send_email(ctx, to, subject, body, cc=None, bcc=None, attachments=None):
    """Send email via Microsoft Graph API."""
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body},
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in to],
        }
    }
    if cc:
        payload["message"]["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]
    if attachments:
        payload["message"]["attachments"] = attachments

    return ctx.http.post("/me/sendMail", json=payload)
```

### Receiving Email (Polling)

For inbound email processing, use a scheduled process that polls the inbox:

```python
@process(
    permissions=["system_admin"],
    schedule="*/5 * * * *"  # every 5 minutes
)
def check_inbox(ctx):
    step("fetch_unread", fetch_unread_emails)
    step("process_emails", process_emails)
    step("mark_read", mark_as_read)
```

---

## Admin Console Configuration

Email Connected System credentials (OAuth2 client ID/secret, tenant ID) are managed via:

**Admin > Connected Systems > outlook_email**

- No credentials in code or environment files
- Encrypted at rest in the platform database
- Environment overrides supported (dev → test mailbox, prod → real mailbox)

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Outlook / Microsoft Graph | Enterprise standard; OAuth2 client credentials flow |
| No built-in email object type | Email is just an Integration + Connected System — no special handling needed |
| Admin-managed credentials | Consistent with all Connected System credential management |
| Polling for receive (not webhooks) | Simpler deployment; webhooks require public endpoint + subscription management |

---

*Reference document — see `AppOS_Design.md` §5.5 and §5.11 for Connected System and Integration context.*

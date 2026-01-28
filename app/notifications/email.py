"""E-Mail notifications for high-priority tenders."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings

logger = get_logger("notifications.email")


def send_tender_notification(
    tenders: List[dict],
    recipient: Optional[str] = None,
) -> bool:
    """Send email notification for high-priority tenders.

    Args:
        tenders: List of dicts with keys: title, score, source, url, deadline, client_name
        recipient: Email address (falls back to settings.notification_email)

    Returns:
        True if email was sent successfully
    """
    to_email = recipient or getattr(settings, "notification_email", None)
    smtp_host = getattr(settings, "smtp_host", None)
    smtp_port = getattr(settings, "smtp_port", 587)
    smtp_user = getattr(settings, "smtp_user", None)
    smtp_password = getattr(settings, "smtp_password", None)
    from_email = getattr(settings, "smtp_from", smtp_user)

    if not to_email or not smtp_host:
        logger.debug("E-Mail-Benachrichtigung nicht konfiguriert (SMTP/E-Mail fehlt)")
        return False

    if not tenders:
        return False

    subject = f"Akquise-Bot: {len(tenders)} neue High-Priority Ausschreibung(en)"

    # Build plain text body
    lines = [
        f"Es wurden {len(tenders)} Ausschreibung(en) mit hohem Score gefunden:",
        "",
    ]

    for t in tenders:
        lines.append(f"  {t['title'][:80]}")
        lines.append(f"    Score: {t.get('score', '-')}/100")
        lines.append(f"    Quelle: {t.get('source', '-')}")
        lines.append(f"    Auftraggeber: {t.get('client_name', '-')}")
        lines.append(f"    Deadline: {t.get('deadline', '-')}")
        if t.get("url"):
            lines.append(f"    Link: {t['url']}")
        lines.append("")

    lines.append("---")
    lines.append("Automatisch generiert vom Akquise-Bot")

    body = "\n".join(lines)

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info("E-Mail-Benachrichtigung gesendet an %s (%d Ausschreibungen)", to_email, len(tenders))
        return True

    except Exception as e:
        logger.error("E-Mail-Versand fehlgeschlagen: %s", e)
        return False

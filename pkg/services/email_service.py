import os
import logging
from flask import current_app, render_template

logger = logging.getLogger(__name__)

def load_local_env():
    """
    Loads local .env variables into os.environ if not already present.
    Does NOT overwrite variables already set in the operating system environment.
    Handles quotes (' and "), inline comments (#), and whitespace cleanly.
    Safe for local development; handles errors gracefully without exposing secrets.
    """
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        env_path = os.path.join(base_dir, '.env')

        if not os.path.isfile(env_path):
            return False

        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip()

                    # Strip inline comments for unquoted values
                    if not (val.startswith('"') and val.endswith('"')) and not (val.startswith("'") and val.endswith("'")):
                        if '#' in val:
                            val = val.split('#', 1)[0].strip()

                    # Strip surrounding quotes
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]

                    if key and key not in os.environ:
                        os.environ[key] = val
        return True
    except Exception as e:
        logger.warning(f"[Email Service] Failed to load local .env file safely: {e}")
        return False

# Execute on module load so os.environ is populated when email_service is imported
load_local_env()

# Outbox for testing/verification inspection

_sent_outbox = []

def get_outbox():
    return _sent_outbox

def clear_outbox():
    _sent_outbox.clear()

def get_contact_info():
    """
    Returns centrally configured Phone and WhatsApp contact numbers.
    Authoritative default Odacity contact number is +2347071501135.
    Can be overridden via env vars ODACITY_PHONE / ODACITY_WHATSAPP or app config PHONE_NUMBER / WHATSAPP_NUMBER.
    """
    phone = os.environ.get('ODACITY_PHONE')
    if not phone and current_app:
        phone = current_app.config.get('PHONE_NUMBER') or current_app.config.get('ODACITY_PHONE')
    if not phone:
        phone = '+2347071501135'

    whatsapp = os.environ.get('ODACITY_WHATSAPP')
    if not whatsapp and current_app:
        whatsapp = current_app.config.get('WHATSAPP_NUMBER') or current_app.config.get('ODACITY_WHATSAPP')
    if not whatsapp:
        whatsapp = '+2347071501135'

    return phone, whatsapp

def send_enquiry_acknowledgement(recipient_email, full_name, enquiry_type="Enquiry"):
    """
    Sends Email 1 — Enquiry Submission Acknowledgement to the applicant.
    Uses dynamic name mapping and central phone/WhatsApp configuration.
    """
    phone, whatsapp = get_contact_info()
    subject = "Thank You for Your Enquiry — Odacity"

    body_text = f"""Dear {full_name},

Thank you for your interest in Odacity.

We are pleased to have received your enquiry and appreciate the opportunity to connect with you.

Your enquiry has been received by our administration team and will be carefully reviewed. We will contact you within one business day to provide an update on your enquiry, outline the next steps, and provide any relevant information you may require.

For immediate assistance or further enquiries, you may also reach us via:

Phone: {phone}
WhatsApp: {whatsapp}

We appreciate your interest in Odacity and look forward to assisting you.

Best regards,
Odacity Team
Property Ownership Without the Stress"""

    try:
        body_html = render_template('email/enquiry_acknowledgement.html', full_name=full_name, phone=phone, whatsapp=whatsapp)
    except Exception as e:
        logger.warning(f"Failed to render HTML email template: {e}")
        body_html = None

    email_record = {
        "to": recipient_email,
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "full_name": full_name,
        "enquiry_type": enquiry_type,
        "phone": phone,
        "whatsapp": whatsapp
    }

    _sent_outbox.append(email_record)
    logger.info(f"[Email 1] Sent acknowledgement to {recipient_email} for {full_name} ({enquiry_type})")
    return email_record


def send_intent_approval_notification(recipient_email, full_name, enquiry_type="Enquiry", customized_link_url=None):
    """
    Sends Email 2 — Intent Approval Notification to the applicant.
    Dispatched ONLY after administrative Intent Approval (Submitted -> Passed).
    Optionally includes the secure Customized Listing Link.
    """
    phone, whatsapp = get_contact_info()
    subject = "Your Enquiry Intent Has Been Approved — Odacity"

    link_text_block = f"\nYour Customized Listing Link:\n{customized_link_url}\n" if customized_link_url else "\nOur team will provide you with your authorized submission access link shortly.\n"

    body_text = f"""Dear {full_name},

We are pleased to inform you that your {enquiry_type} onboarding enquiry intent has been reviewed and APPROVED by our administration team.

Your application has successfully completed the initial intent review phase. You are now authorized to proceed to the next controlled stage of the Odacity onboarding process.
{link_text_block}
If you have any questions or require assistance, please contact us:

Phone: {phone}
WhatsApp: {whatsapp}

Best regards,
Odacity Team
Property Ownership Without the Stress"""

    try:
        body_html = render_template('email/intent_approval.html', full_name=full_name, enquiry_type=enquiry_type, phone=phone, whatsapp=whatsapp, customized_link_url=customized_link_url)
    except Exception as e:
        logger.warning(f"Failed to render intent approval HTML email template: {e}")
        body_html = None

    email_record = {
        "to": recipient_email,
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "full_name": full_name,
        "enquiry_type": enquiry_type,
        "customized_link_url": customized_link_url,
        "phone": phone,
        "whatsapp": whatsapp
    }

    _sent_outbox.append(email_record)
    logger.info(f"[Email 2] Sent intent approval notification to {recipient_email} for {full_name} ({enquiry_type})")
    return email_record



def send_intent_decline_notification(recipient_email, full_name, enquiry_type="Enquiry"):
    """
    Sends Email 2 Decline — Intent Decline Notification to the applicant.
    Dispatched ONLY after administrative Intent Decline (Submitted -> Failed).
    """
    phone, whatsapp = get_contact_info()
    subject = "Update Regarding Your Enquiry — Odacity"

    body_text = f"""Dear {full_name},

Thank you for submitting your {enquiry_type} onboarding enquiry to Odacity.

After careful review, we regret to inform you that your enquiry intent cannot be approved at this time.

If you believe this decision was made in error or if you wish to provide additional documentation for reconsideration, please contact our support team:

Phone: {phone}
WhatsApp: {whatsapp}

Best regards,
Odacity Team
Property Ownership Without the Stress"""

    try:
        body_html = render_template('email/intent_decline.html', full_name=full_name, enquiry_type=enquiry_type, phone=phone, whatsapp=whatsapp)
    except Exception as e:
        logger.warning(f"Failed to render intent decline HTML email template: {e}")
        body_html = None

    email_record = {
        "to": recipient_email,
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "full_name": full_name,
        "enquiry_type": enquiry_type,
        "phone": phone,
        "whatsapp": whatsapp
    }

    _sent_outbox.append(email_record)
    logger.info(f"[Email 2] Sent intent decline notification to {recipient_email} for {full_name} ({enquiry_type})")
    return email_record


def create_user_notification(
    user_id,
    notification_type,
    subject,
    message,
    url=None,
    send_email=False,
    email_template=None,
    email_context=None,
    idempotency_window_minutes=5
):
    """
    Phase 23.1 — Unified Notification Dispatch Helper
    Creates an in-app Notification record for the target user (is_read=False, read_at=None)
    and optionally dispatches a transactional email to the user's registered email via _sent_outbox.

    Enforces defensive duplicate suppression using existing schema fields (user_id, notification_type, subject, created_at).
    """
    from datetime import datetime, timedelta
    from pkg.models import db, User, Notification

    if not user_id:
        logger.warning("[Notification] Cannot create notification: Missing user_id")
        return None

    user = User.query.get(user_id)
    if not user:
        logger.warning(f"[Notification] Cannot create notification: User #{user_id} not found")
        return None

    now = datetime.utcnow()

    # Defensive Idempotency Suppression Check (No schema changes)
    if idempotency_window_minutes and idempotency_window_minutes > 0:
        window_start = now - timedelta(minutes=idempotency_window_minutes)
        existing = Notification.query.filter(
            Notification.user_id == user_id,
            Notification.notification_type == notification_type,
            Notification.subject == subject,
            Notification.created_at >= window_start
        ).first()

        if existing:
            logger.info(f"[Notification] Defensive duplicate check suppressed duplicate alert for user #{user_id} ({notification_type}: '{subject}') within {idempotency_window_minutes}m window.")
            return existing

    # Create In-App Notification (is_read=False, read_at=None)
    notif = Notification(
        user_id=user_id,
        notification_type=notification_type,
        type=notification_type,
        subject=subject,
        body=message,
        message=message,
        url=url,
        is_read=False,
        read_at=None,
        created_at=now
    )

    db.session.add(notif)
    db.session.commit()
    logger.info(f"[Notification] In-app notification #{notif.notification_id} created for user #{user_id} ({notification_type})")

    # Optional Email Outbox Dispatch
    if send_email and user.email:
        phone, whatsapp = get_contact_info()
        ctx = email_context.copy() if email_context else {}
        ctx.setdefault('full_name', user.full_name or "Valued Customer")
        ctx.setdefault('phone', phone)
        ctx.setdefault('whatsapp', whatsapp)
        ctx.setdefault('subject', subject)
        ctx.setdefault('message', message)
        ctx.setdefault('url', url)

        body_html = None
        if email_template:
            try:
                body_html = render_template(email_template, **ctx)
            except Exception as e:
                logger.warning(f"[Notification] Failed to render email template '{email_template}': {e}")

        email_record = {
            "to": user.email,
            "subject": subject,
            "body_text": message,
            "body_html": body_html,
            "full_name": user.full_name,
            "notification_type": notification_type,
            "url": url,
            "phone": phone,
            "whatsapp": whatsapp
        }

        _sent_outbox.append(email_record)
        logger.info(f"[Email Notification] Sent transactional email to {user.email} for user #{user_id} ({notification_type})")

    return notif


def check_email_configuration():
    """
    Stage 3 Helper: Inspects environment variables for SMTP configuration.
    Returns status dictionary without exposing sensitive secret values.
    """
    server = os.environ.get('MAIL_SERVER')
    port = os.environ.get('MAIL_PORT')
    username = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    sender = os.environ.get('MAIL_DEFAULT_SENDER')
    test_mode = os.environ.get('EMAIL_TEST_MODE', 'false').lower() in ('true', '1', 'yes')
    test_recipient = os.environ.get('EMAIL_TEST_RECIPIENT')

    is_configured = bool(server and port and username and password and sender)

    return {
        "configured": is_configured,
        "MAIL_SERVER": "PRESENT" if server else "MISSING",
        "MAIL_PORT": "PRESENT" if port else "MISSING",
        "MAIL_USERNAME": "PRESENT" if username else "MISSING",
        "MAIL_PASSWORD": "PRESENT" if password else "MISSING",
        "MAIL_DEFAULT_SENDER": "PRESENT" if sender else "MISSING",
        "EMAIL_TEST_MODE": test_mode,
        "EMAIL_TEST_RECIPIENT": "PRESENT" if test_recipient else "MISSING"
    }


def send_smtp_test_email():
    """
    Stage 3 Helper: Sends a single controlled test email via Gmail SMTP using Google App Password.
    Requires EMAIL_TEST_MODE=true in environment.
    Target recipient is strictly taken from EMAIL_TEST_RECIPIENT environment variable.
    Never exposes credentials or secrets.
    """
    import smtplib
    from email.message import EmailMessage

    test_mode = os.environ.get('EMAIL_TEST_MODE', 'false').lower() in ('true', '1', 'yes')
    if not test_mode:
        logger.warning("[SMTP Test] Dispatch aborted: EMAIL_TEST_MODE is disabled.")
        return {
            "success": False,
            "error": "EMAIL_TEST_MODE is disabled in environment"
        }

    target_recipient = os.environ.get('EMAIL_TEST_RECIPIENT')
    if not target_recipient:
        logger.warning("[SMTP Test] Dispatch aborted: EMAIL_TEST_RECIPIENT is not configured.")
        return {
            "success": False,
            "error": "No test recipient specified. Set EMAIL_TEST_RECIPIENT in environment."
        }

    mail_server = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    try:
        mail_port = int(os.environ.get('MAIL_PORT', 587))
    except (ValueError, TypeError):
        mail_port = 587

    mail_use_tls = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes')
    mail_username = os.environ.get('MAIL_USERNAME')
    mail_password = os.environ.get('MAIL_PASSWORD')
    sender_email = os.environ.get('MAIL_DEFAULT_SENDER') or mail_username
    sender_name = os.environ.get('MAIL_DEFAULT_SENDER_NAME', 'Odacity')

    if not mail_username or not mail_password:
        logger.error("[SMTP Test] Dispatch failed: MAIL_USERNAME or MAIL_PASSWORD missing.")
        return {
            "success": False,
            "error": "SMTP credentials missing. Set MAIL_USERNAME and MAIL_PASSWORD in environment."
        }

    msg = EmailMessage()
    msg['Subject'] = "Odacity SMTP Test — Email Delivery Successful"
    msg['From'] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    msg['To'] = target_recipient

    body_text = f"""Hello,

This is a temporary SMTP test from the Odacity application.

If you received this email, the Odacity Flask application has successfully connected to the configured Gmail SMTP server using Google App Password and delivered the email.

SMTP Provider:
Gmail SMTP

SMTP Server:
{mail_server}

Port:
{mail_port}

Authentication Mode:
Google App Password

This is a temporary test configuration and will later be replaced with the production Odacity transactional email provider.

Regards,
Odacity Team"""

    body_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #0f172a; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
        <h2 style="color: #ffffff; margin: 0; font-size: 24px;">ODACITY</h2>
    </div>
    <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 8px 8px;">
        <h3 style="color: #0f172a; margin-top: 0;">Odacity SMTP Test — Delivery Successful</h3>
        <p>Hello,</p>
        <p>This is a temporary SMTP test from the Odacity application.</p>
        <p>If you received this email, the Odacity Flask application has successfully connected to the configured Gmail SMTP server and delivered the email.</p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr><td style="padding: 8px; border-bottom: 1px solid #e2e8f0; font-weight: bold;">SMTP Server:</td><td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{mail_server}:{mail_port}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #e2e8f0; font-weight: bold;">Auth Mode:</td><td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">Google App Password</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #e2e8f0; font-weight: bold;">Recipient:</td><td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{target_recipient}</td></tr>
        </table>
        <p style="font-size: 13px; color: #64748b;">This is a temporary test configuration and will later be replaced with the production Odacity transactional email provider.</p>
        <p style="margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 20px;">Best regards,<br><strong>Odacity Team</strong></p>
    </div>
</body>
</html>"""

    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype='html')

    try:
        logger.info(f"[SMTP Test] Connecting to {mail_server}:{mail_port} (Auth=App Password)...")
        if mail_port == 465:
            with smtplib.SMTP_SSL(mail_server, mail_port, timeout=15) as server:
                server.login(mail_username, mail_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
                server.ehlo_or_helo_if_needed()
                if mail_use_tls:
                    server.starttls()
                    server.ehlo_or_helo_if_needed()
                server.login(mail_username, mail_password)
                server.send_message(msg)

        logger.info(f"[SMTP Test] Successfully delivered test email to {target_recipient}")
        return {
            "success": True,
            "message": f"Test email successfully delivered to {target_recipient}",
            "recipient": target_recipient,
            "server": f"{mail_server}:{mail_port}",
            "auth_mode": "Google App Password"
        }
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"[SMTP Test] Authentication failed: {e.smtp_code} {e.smtp_error}")
        return {
            "success": False,
            "error": "SMTP Authentication Failed. Check MAIL_USERNAME and Google App Password."
        }
    except smtplib.SMTPConnectError as e:
        logger.error(f"[SMTP Test] Connection failed: {e}")
        return {
            "success": False,
            "error": f"SMTP Connection Failed: Unable to connect to {mail_server}:{mail_port}."
        }
    except Exception as e:
        logger.error(f"[SMTP Test] Dispatch exception: {e}")
        return {
            "success": False,
            "error": f"SMTP Delivery Error: {str(e)}"
        }

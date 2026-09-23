import os
import logging
from flask import current_app, render_template

logger = logging.getLogger(__name__)

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


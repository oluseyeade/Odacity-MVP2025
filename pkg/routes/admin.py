import os
import json
import secrets
import logging
from datetime import datetime
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, session, abort, send_from_directory
from pkg import app
from pkg.models import db, User, VerificationCase, VerificationEvent, AuditLog, SecurityEvent
from pkg.services.email_service import send_intent_approval_notification, send_intent_decline_notification

logger = logging.getLogger(__name__)


def admin_required(f):
    """
    Decorator to enforce server-side administrator authorization.
    Verifies that the user is logged in, active, and has is_super_admin = True.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))
        
        user = User.query.get(user_id)
        if not user or not user.is_active or not user.is_super_admin:
            flash('Access denied. Administrative privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def get_entity_display_name(entity_type):
    """Returns human-readable title for an enquiry entity type."""
    mapping = {
        'dab_individual': 'DAB Individual',
        'dab_institution': 'DAB Institution / Organization',
        'dab_agent': 'DAB Agent',
        'general_enquiry': 'General Enquiry'
    }
    return mapping.get(entity_type, entity_type or 'Enquiry')


def extract_contact_info(v_case):
    """
    Extracts recipient email and full name from the initial submission VerificationEvent payload data.
    """
    first_event = VerificationEvent.query.filter_by(
        verification_case_id=v_case.verification_case_id
    ).order_by(VerificationEvent.created_at.asc()).first()

    email = None
    full_name = None

    if first_event and first_event.data and isinstance(first_event.data, dict):
        payload = first_event.data
        if 'dab_individual' in payload:
            ind = payload['dab_individual']
            email = ind.get('email')
            full_name = ind.get('full_name')
        elif 'institution' in payload:
            inst = payload['institution']
            email = inst.get('email')
            full_name = inst.get('contact_person') or inst.get('name')
        elif 'agent' in payload:
            agent = payload['agent']
            email = agent.get('email')
            full_name = agent.get('name')
        elif 'general_enquiry' in payload:
            gen = payload['general_enquiry']
            email = gen.get('email')
            full_name = gen.get('name')

    if not email and v_case.notes:
        if 'submitted by ' in v_case.notes:
            name_part = v_case.notes.split('submitted by ')[-1].split(' - ')[0].strip()
            full_name = full_name or name_part

    return email, full_name or "Valued Applicant"


def get_or_create_customized_link(v_case, admin_user_id=None):
    """
    Idempotent helper to retrieve or generate a cryptographically safe tokenized
    Customized Listing Link for an approved VerificationCase (status == 'Passed').
    
    Stores metadata inside VerificationCase.result_details (JSON string) and logs
    a VerificationEvent of event_type='CUSTOMIZED_LINK_GENERATED'.
    """
    if v_case.status != 'Passed':
        return None, None

    # Check for existing link in result_details
    existing_token = None
    if v_case.result_details:
        try:
            parsed = json.loads(v_case.result_details)
            if isinstance(parsed, dict) and 'customized_listing_link' in parsed:
                existing_token = parsed['customized_listing_link'].get('token')
        except (json.JSONDecodeError, TypeError):
            pass

    now = datetime.utcnow()

    if existing_token:
        token = existing_token
    else:
        # Generate cryptographically unpredictable token (256-bit entropy)
        token = secrets.token_urlsafe(32)
        link_data = {
            "token": token,
            "created_at": now.isoformat(),
            "status": "active"
        }
        
        # Persist safely in result_details
        current_data = {}
        if v_case.result_details:
            try:
                current_data = json.loads(v_case.result_details)
                if not isinstance(current_data, dict):
                    current_data = {}
            except Exception:
                current_data = {}

        current_data['customized_listing_link'] = link_data
        v_case.result_details = json.dumps(current_data)
        v_case.updated_at = now

        # Log VerificationEvent
        v_event = VerificationEvent(
            verification_case_id=v_case.verification_case_id,
            event_type='CUSTOMIZED_LINK_GENERATED',
            description=f"Customized Listing Link generated for VerificationCase #{v_case.verification_case_id}",
            data=link_data,
            status='Passed',
            created_by_user_id=admin_user_id,
            performed_by_user_id=admin_user_id,
            created_at=now
        )
        db.session.add(v_event)

    link_url = url_for('customized_listing_entry', token=token, _external=True)
    return token, link_url


@app.route('/admin/intents/')
@admin_required
def admin_intents():
    """
    Admin Dashboard: List all submitted, approved, and declined enquiry intents (VerificationCases).
    Supports filtering by status and entity type.
    """
    status_filter = request.args.get('status', 'all')
    type_filter = request.args.get('type', 'all')

    query = VerificationCase.query

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if type_filter != 'all':
        query = query.filter_by(entity_type=type_filter)

    cases = query.order_by(VerificationCase.created_at.desc()).all()

    # Calculate statistics
    all_cases = VerificationCase.query.all()
    stats = {
        'total': len(all_cases),
        'pending': sum(1 for c in all_cases if c.status == 'Submitted'),
        'approved': sum(1 for c in all_cases if c.status == 'Passed'),
        'declined': sum(1 for c in all_cases if c.status == 'Failed')
    }

    case_list = []
    for c in cases:
        email, full_name = extract_contact_info(c)
        case_list.append({
            'case': c,
            'display_name': get_entity_display_name(c.entity_type),
            'applicant_name': full_name,
            'applicant_email': email
        })

    return render_template(
        'admin/intents.html',
        case_list=case_list,
        stats=stats,
        current_status=status_filter,
        current_type=type_filter,
        title='Admin Intent Management — Odacity'
    )


@app.route('/admin/intents/<int:case_id>/')
@admin_required
def admin_intent_detail(case_id):
    """
    Admin Detail View: Inspect specific enquiry intent case, payload details, uploaded documents, history logs, and Customized Listing Link.
    """
    v_case = VerificationCase.query.get_or_404(case_id)
    events = VerificationEvent.query.filter_by(
        verification_case_id=v_case.verification_case_id
    ).order_by(VerificationEvent.created_at.asc()).all()

    initial_event = events[0] if events else None
    payload_data = initial_event.data if initial_event else {}

    email, full_name = extract_contact_info(v_case)

    # Extract existing Customized Listing Link if case is Passed
    customized_token = None
    customized_url = None
    if v_case.status == 'Passed' and v_case.result_details:
        try:
            parsed = json.loads(v_case.result_details)
            if isinstance(parsed, dict) and 'customized_listing_link' in parsed:
                customized_token = parsed['customized_listing_link'].get('token')
                if customized_token:
                    customized_url = url_for('customized_listing_entry', token=customized_token, _external=True)
        except Exception:
            pass

    return render_template(
        'admin/intents.html',
        selected_case=v_case,
        events=events,
        payload_data=payload_data,
        applicant_email=email,
        applicant_name=full_name,
        display_name=get_entity_display_name(v_case.entity_type),
        customized_token=customized_token,
        customized_url=customized_url,
        title=f'Review Intent #{case_id} — Odacity Admin'
    )


@app.route('/admin/intents/<int:case_id>/approve/', methods=['POST'])
@admin_required
def admin_intent_approve(case_id):
    """
    State Transition: Submitted -> Passed (Intent Approved).
    Authorized for super administrators only.
    Generates Customized Listing Link and dispatches Email 2 notification upon successful commit.
    """
    v_case = VerificationCase.query.get_or_404(case_id)

    if v_case.status == 'Passed':
        flash(f'Intent #{case_id} has already been approved.', 'warning')
        return redirect(url_for('admin_intents'))
    
    if v_case.status == 'Failed':
        flash(f'Cannot approve Intent #{case_id} because it has already been declined.', 'danger')
        return redirect(url_for('admin_intents'))

    if v_case.status != 'Submitted':
        flash(f'Cannot approve Intent #{case_id} in state "{v_case.status}". Only "Submitted" intents can be approved.', 'danger')
        return redirect(url_for('admin_intents'))

    admin_user_id = session.get('user_id')
    now = datetime.utcnow()

    try:
        # 1. State Transition: Submitted -> Passed
        v_case.status = 'Passed'
        v_case.completed_at = now
        v_case.assigned_to = admin_user_id
        v_case.updated_at = now

        # 2. Generate/Retrieve Customized Listing Link for Phase 5
        token, link_url = get_or_create_customized_link(v_case, admin_user_id)

        # 3. Log VerificationEvent: INTENT_APPROVED
        v_event = VerificationEvent(
            verification_case_id=v_case.verification_case_id,
            event_type='INTENT_APPROVED',
            description=f"Intent approved for VerificationCase #{v_case.verification_case_id} ({v_case.entity_type})",
            data={
                "action": "INTENT_APPROVED",
                "approved_by_user_id": admin_user_id,
                "previous_status": "Submitted",
                "new_status": "Passed",
                "customized_listing_link_token": token,
                "timestamp": now.isoformat()
            },
            status='Passed',
            created_by_user_id=admin_user_id,
            performed_by_user_id=admin_user_id,
            created_at=now
        )
        db.session.add(v_event)

        # 4. Log AuditLog Entry
        audit_entry = AuditLog(
            user_id=admin_user_id,
            action='INTENT_APPROVED',
            entity_type=v_case.entity_type,
            entity_id=v_case.verification_case_id,
            resource_type='VerificationCase',
            resource_id=v_case.verification_case_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            previous_values={"status": "Submitted"},
            new_values={"status": "Passed", "approved_by": admin_user_id},
            created_at=now
        )
        db.session.add(audit_entry)

        # 5. Log SecurityEvent Entry
        sec_event = SecurityEvent(
            user_id=admin_user_id,
            event_type='INTENT_APPROVED',
            description=f"Intent #{v_case.verification_case_id} ({v_case.entity_type}) approved by admin #{admin_user_id}",
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)

        # 6. Commit Transaction
        db.session.commit()
        logger.info(f"[Intent Approval] Successfully approved VerificationCase #{v_case.verification_case_id} by Admin #{admin_user_id}")

        # 7. Dispatch Email 2 (ONLY AFTER SUCCESSFUL COMMIT)
        email, full_name = extract_contact_info(v_case)
        if email:
            try:
                send_intent_approval_notification(
                    recipient_email=email,
                    full_name=full_name,
                    enquiry_type=get_entity_display_name(v_case.entity_type),
                    customized_link_url=link_url
                )
            except Exception as e:
                logger.warning(f"Failed to dispatch Email 2 notification for case #{case_id}: {e}")

        flash(f'Intent #{case_id} ({get_entity_display_name(v_case.entity_type)}) has been APPROVED successfully. Customized Listing Link created and notification sent.', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving intent #{case_id}: {e}")
        flash(f'An error occurred while approving Intent #{case_id}: {str(e)}', 'danger')

    return redirect(url_for('admin_intents'))


@app.route('/admin/intents/<int:case_id>/generate-link/', methods=['POST'])
@admin_required
def admin_generate_customized_link(case_id):
    """
    Admin Route: Generate or retrieve the Customized Listing Link for an approved intent (status == 'Passed').
    Enforces server-side super admin access control and CSRF validation.
    """
    v_case = VerificationCase.query.get_or_404(case_id)

    if v_case.status == 'Submitted':
        flash(f'Cannot generate Customized Listing Link for Intent #{case_id} because it is currently unapproved (Submitted). Please approve the intent first.', 'danger')
        return redirect(url_for('admin_intent_detail', case_id=case_id))

    if v_case.status == 'Failed':
        flash(f'Cannot generate Customized Listing Link for Intent #{case_id} because it has been declined.', 'danger')
        return redirect(url_for('admin_intent_detail', case_id=case_id))

    if v_case.status != 'Passed':
        flash(f'Cannot generate Customized Listing Link for Intent #{case_id} in state "{v_case.status}".', 'danger')
        return redirect(url_for('admin_intent_detail', case_id=case_id))

    admin_user_id = session.get('user_id')

    try:
        token, link_url = get_or_create_customized_link(v_case, admin_user_id)

        # Log AuditLog & SecurityEvent
        now = datetime.utcnow()
        audit_entry = AuditLog(
            user_id=admin_user_id,
            action='CUSTOMIZED_LINK_GENERATED',
            entity_type=v_case.entity_type,
            entity_id=v_case.verification_case_id,
            resource_type='VerificationCase',
            resource_id=v_case.verification_case_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            new_values={"action": "CUSTOMIZED_LINK_GENERATED", "generated_by": admin_user_id},
            created_at=now
        )
        db.session.add(audit_entry)

        sec_event = SecurityEvent(
            user_id=admin_user_id,
            event_type='CUSTOMIZED_LINK_GENERATED',
            description=f"Customized Listing Link generated for intent #{case_id} by admin #{admin_user_id}",
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)

        db.session.commit()
        flash(f'Customized Listing Link successfully generated/retrieved for Intent #{case_id}.', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error generating link for case #{case_id}: {e}")
        flash(f'Failed to generate Customized Listing Link: {str(e)}', 'danger')

    return redirect(url_for('admin_intent_detail', case_id=case_id))


@app.route('/admin/intents/<int:case_id>/decline/', methods=['POST'])
@admin_required
def admin_intent_decline(case_id):
    """
    State Transition: Submitted -> Failed (Intent Declined).
    Authorized for super administrators only.
    Dispatches Email 2 decline notification upon successful commit.
    """
    v_case = VerificationCase.query.get_or_404(case_id)

    if v_case.status == 'Failed':
        flash(f'Intent #{case_id} has already been declined.', 'warning')
        return redirect(url_for('admin_intents'))

    if v_case.status == 'Passed':
        flash(f'Cannot decline Intent #{case_id} because it has already been approved.', 'danger')
        return redirect(url_for('admin_intents'))

    if v_case.status != 'Submitted':
        flash(f'Cannot decline Intent #{case_id} in state "{v_case.status}". Only "Submitted" intents can be declined.', 'danger')
        return redirect(url_for('admin_intents'))

    admin_user_id = session.get('user_id')
    now = datetime.utcnow()

    try:
        v_case.status = 'Failed'
        v_case.completed_at = now
        v_case.assigned_to = admin_user_id
        v_case.updated_at = now

        v_event = VerificationEvent(
            verification_case_id=v_case.verification_case_id,
            event_type='INTENT_DECLINED',
            description=f"Intent declined for VerificationCase #{v_case.verification_case_id} ({v_case.entity_type})",
            data={
                "action": "INTENT_DECLINED",
                "declined_by_user_id": admin_user_id,
                "previous_status": "Submitted",
                "new_status": "Failed",
                "timestamp": now.isoformat()
            },
            status='Failed',
            created_by_user_id=admin_user_id,
            performed_by_user_id=admin_user_id,
            created_at=now
        )
        db.session.add(v_event)

        audit_entry = AuditLog(
            user_id=admin_user_id,
            action='INTENT_DECLINED',
            entity_type=v_case.entity_type,
            entity_id=v_case.verification_case_id,
            resource_type='VerificationCase',
            resource_id=v_case.verification_case_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            previous_values={"status": "Submitted"},
            new_values={"status": "Failed", "declined_by": admin_user_id},
            created_at=now
        )
        db.session.add(audit_entry)

        sec_event = SecurityEvent(
            user_id=admin_user_id,
            event_type='INTENT_DECLINED',
            description=f"Intent #{v_case.verification_case_id} ({v_case.entity_type}) declined by admin #{admin_user_id}",
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)

        db.session.commit()
        logger.info(f"[Intent Decline] Successfully declined VerificationCase #{v_case.verification_case_id} by Admin #{admin_user_id}")

        email, full_name = extract_contact_info(v_case)
        if email:
            try:
                send_intent_decline_notification(
                    recipient_email=email,
                    full_name=full_name,
                    enquiry_type=get_entity_display_name(v_case.entity_type)
                )
            except Exception as e:
                logger.warning(f"Failed to dispatch Email 2 decline notification for case #{case_id}: {e}")

        flash(f'Intent #{case_id} ({get_entity_display_name(v_case.entity_type)}) has been DECLINED.', 'warning')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error declining intent #{case_id}: {e}")
        flash(f'An error occurred while declining Intent #{case_id}: {str(e)}', 'danger')

    return redirect(url_for('admin_intents'))


@app.route('/admin/uploads/<path:filename>')
@admin_required
def admin_serve_upload(filename):
    """
    Secure Admin Endpoint: Serves uploaded verification documents (PDFs) to authorized super admins only.
    Prevents unauthenticated or public document exposure.
    """
    upload_folder = os.path.join(app.root_path, 'static', 'uploads')
    return send_from_directory(upload_folder, filename)

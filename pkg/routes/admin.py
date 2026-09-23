import os
import json
import secrets
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, session, abort, send_from_directory
from pkg import app
from pkg.models import db, User, VerificationCase, VerificationEvent, AuditLog, SecurityEvent, Property, DirectAssetBrief, PropertyDocument, PropertyMedia, Inspection, CustomerProfile, Offer
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

    now = datetime.utcnow()
    public_eligible_at = None
    if v_case.dab and v_case.dab.approved_at:
        public_eligible_at = v_case.dab.approved_at + timedelta(hours=72)

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
        now=now,
        public_eligible_at=public_eligible_at,
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


@app.route('/admin/documents/<int:document_id>/verify/', methods=['POST'])
@admin_required
def admin_verify_document(document_id):
    """
    Phase 7 Document Inspection: Verifies or rejects individual title deeds / survey documents.
    Updates PropertyDocument.review_status to 'Verified' or 'Rejected'.
    """
    doc = PropertyDocument.query.get_or_404(document_id)
    prop = doc.property
    dab = prop.dab if prop else None

    v_case = VerificationCase.query.filter_by(dab_id=dab.dab_id).first() if dab else None
    case_id = v_case.verification_case_id if v_case else None

    action = request.form.get('action', 'verify').lower()
    notes = request.form.get('notes', '').strip()
    rejection_reason = request.form.get('rejection_reason', '').strip()

    admin_user_id = session.get('user_id')
    now = datetime.utcnow()

    try:
        if action == 'verify':
            doc.review_status = 'Verified'
            doc.verified_at = now
            doc.verified_by_user_id = admin_user_id
            if notes:
                doc.notes = notes
            flash(f"Document '{doc.document_type}' for Property #{prop.property_id} has been VERIFIED.", 'success')
        elif action == 'reject':
            doc.review_status = 'Rejected'
            if rejection_reason:
                doc.rejection_reason = rejection_reason
            if notes:
                doc.notes = notes
            flash(f"Document '{doc.document_type}' for Property #{prop.property_id} has been REJECTED.", 'warning')

        if prop and prop.status == 'Submitted':
            prop.status = 'Under Verification'
            prop.publication_status = 'Under Verification'
        if dab and dab.status == 'Submitted':
            dab.status = 'Under Verification'

        if v_case:
            v_evt = VerificationEvent(
                verification_case_id=v_case.verification_case_id,
                event_type='PROPERTY_DOCUMENT_VERIFIED' if action == 'verify' else 'PROPERTY_DOCUMENT_REJECTED',
                description=f"Document #{doc.document_id} ({doc.document_type}) {action}ed by Admin #{admin_user_id}",
                data={"document_id": doc.document_id, "action": action, "notes": notes, "rejection_reason": rejection_reason},
                status='Passed' if action == 'verify' else 'Failed',
                created_by_user_id=admin_user_id,
                performed_by_user_id=admin_user_id,
                created_at=now
            )
            db.session.add(v_evt)

        audit_entry = AuditLog(
            user_id=admin_user_id,
            action='PROPERTY_DOCUMENT_VERIFIED' if action == 'verify' else 'PROPERTY_DOCUMENT_REJECTED',
            entity_type='PropertyDocument',
            entity_id=doc.document_id,
            resource_type='Property',
            resource_id=prop.property_id if prop else None,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            new_values={"review_status": doc.review_status, "action": action},
            created_at=now
        )
        db.session.add(audit_entry)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error processing document #{document_id}: {e}")
        flash(f"An error occurred while processing document #{document_id}: {str(e)}", 'danger')

    if case_id:
        return redirect(url_for('admin_intent_detail', case_id=case_id))
    return redirect(url_for('admin_intents'))


@app.route('/admin/media/<int:media_id>/review/', methods=['POST'])
@admin_required
def admin_review_media(media_id):
    """
    Phase 7 Media Review: Approves or rejects individual property photographs.
    Updates PropertyMedia.review_status to 'Approved' or 'Rejected' (asset quality level only).
    """
    med = PropertyMedia.query.get_or_404(media_id)
    prop = med.property
    dab = prop.dab if prop else None

    v_case = VerificationCase.query.filter_by(dab_id=dab.dab_id).first() if dab else None
    case_id = v_case.verification_case_id if v_case else None

    action = request.form.get('action', 'approve').lower()
    rejection_reason = request.form.get('rejection_reason', '').strip()

    admin_user_id = session.get('user_id')
    now = datetime.utcnow()

    try:
        if action == 'approve':
            med.review_status = 'Approved'
            flash(f"Property photo #{media_id} quality approved.", 'success')
        elif action == 'reject':
            med.review_status = 'Rejected'
            if rejection_reason:
                med.rejection_reason = rejection_reason
            flash(f"Property photo #{media_id} rejected.", 'warning')

        audit_entry = AuditLog(
            user_id=admin_user_id,
            action='PROPERTY_MEDIA_REVIEWED',
            entity_type='PropertyMedia',
            entity_id=med.media_id,
            resource_type='Property',
            resource_id=prop.property_id if prop else None,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            new_values={"review_status": med.review_status, "action": action},
            created_at=now
        )
        db.session.add(audit_entry)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error reviewing media #{media_id}: {e}")
        flash(f"An error occurred while reviewing photo #{media_id}: {str(e)}", 'danger')

    if case_id:
        return redirect(url_for('admin_intent_detail', case_id=case_id))
    return redirect(url_for('admin_intents'))


@app.route('/admin/properties/<int:property_id>/verify/', methods=['POST'])
@admin_required
def admin_verify_property(property_id):
    """
    Phase 7 Terminal Gate: Administrative Property Verification.
    Updates Property.status = 'Verified', DirectAssetBrief.status = 'Under Verification',
    Property.publication_status = 'Under Verification' (MUST NOT BE 'Approved').
    Creates/updates distinct Property VerificationCase with status = 'Passed'.
    """
    prop = Property.query.get_or_404(property_id)
    dab = prop.dab

    if not dab:
        flash(f"Cannot verify Property #{property_id} because no parent DirectAssetBrief is associated.", 'danger')
        return redirect(url_for('admin_intents'))

    intent_case = VerificationCase.query.filter_by(dab_id=dab.dab_id).first()
    case_id = intent_case.verification_case_id if intent_case else None

    action = request.form.get('action', 'verify').lower()
    admin_user_id = session.get('user_id')
    now = datetime.utcnow()

    try:
        if action == 'verify':
            # Prerequisite Gate Validation: Ensure all submitted title documents are verified
            if prop.documents:
                unverified_docs = [d for d in prop.documents if d.review_status != 'Verified']
                if unverified_docs:
                    rejected_docs = [d for d in unverified_docs if d.review_status == 'Rejected']
                    if rejected_docs:
                        flash(f"Cannot verify Property #{property_id}: One or more title documents have been REJECTED. All documents must be VERIFIED.", 'danger')
                    else:
                        flash(f"Cannot verify Property #{property_id}: All submitted title documents must be VERIFIED before property verification.", 'danger')
                    if case_id:
                        return redirect(url_for('admin_intent_detail', case_id=case_id))
                    return redirect(url_for('admin_intents'))

            # Prerequisite Gate Validation: Ensure all property media photos are approved
            if prop.media:
                unapproved_media = [m for m in prop.media if m.review_status != 'Approved']
                if unapproved_media:
                    rejected_media = [m for m in unapproved_media if m.review_status == 'Rejected']
                    if rejected_media:
                        flash(f"Cannot verify Property #{property_id}: One or more property photos have been REJECTED. All media must be APPROVED.", 'danger')
                    else:
                        flash(f"Cannot verify Property #{property_id}: All property photos must be APPROVED before property verification.", 'danger')
                    if case_id:
                        return redirect(url_for('admin_intent_detail', case_id=case_id))
                    return redirect(url_for('admin_intents'))

            # 1. Terminal Phase 7 Property state transition
            prop.status = 'Verified'
            prop.publication_status = 'Under Verification'  # MUST NOT BE 'Approved'
            prop.updated_at = now

            dab.status = 'Under Verification'  # MUST NOT BE 'Approved'
            dab.updated_at = now

            # 2. Distinct Property VerificationCase handling
            prop_case = VerificationCase.query.filter_by(
                dab_id=dab.dab_id,
                verifier_type='property'
            ).first()

            if not prop_case:
                prop_case = VerificationCase(
                    dab_id=dab.dab_id,
                    entity_type='property',
                    entity_id=prop.property_id,
                    verifier_type='property',
                    verification_type='property_verification',
                    status='Passed',
                    started_at=now,
                    completed_at=now,
                    assigned_to=admin_user_id,
                    result_details=json.dumps({"action": "PROPERTY_VERIFIED", "verified_by": admin_user_id}),
                    created_at=now,
                    updated_at=now
                )
                db.session.add(prop_case)
            else:
                prop_case.status = 'Passed'
                prop_case.completed_at = now
                prop_case.assigned_to = admin_user_id
                prop_case.updated_at = now

            db.session.flush()

            # 3. Log VerificationEvent: PROPERTY_VERIFIED
            v_evt = VerificationEvent(
                verification_case_id=prop_case.verification_case_id,
                event_type='PROPERTY_VERIFIED',
                description=f"Property #{prop.property_id} ('{prop.title}') verified by Admin #{admin_user_id}",
                data={
                    "action": "PROPERTY_VERIFIED",
                    "property_id": prop.property_id,
                    "dab_id": dab.dab_id,
                    "verified_by_user_id": admin_user_id,
                    "property_status": "Verified",
                    "dab_status": "Under Verification",
                    "publication_status": "Under Verification",
                    "timestamp": now.isoformat()
                },
                status='Passed',
                created_by_user_id=admin_user_id,
                performed_by_user_id=admin_user_id,
                created_at=now
            )
            db.session.add(v_evt)

            # 4. Log AuditLog & SecurityEvent
            audit_entry = AuditLog(
                user_id=admin_user_id,
                action='PROPERTY_VERIFIED',
                entity_type='Property',
                entity_id=prop.property_id,
                resource_type='Property',
                resource_id=prop.property_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                previous_values={"status": "Submitted", "publication_status": "Submitted"},
                new_values={"status": "Verified", "publication_status": "Under Verification", "dab_status": "Under Verification"},
                created_at=now
            )
            db.session.add(audit_entry)

            sec_event = SecurityEvent(
                user_id=admin_user_id,
                event_type='PROPERTY_VERIFIED',
                description=f"Property #{prop.property_id} ('{prop.title}') verified by admin #{admin_user_id}. Phase 7 complete.",
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec_event)

            db.session.commit()
            flash(f"Property #{property_id} ('{prop.title}') has been VERIFIED successfully.", 'success')

        elif action == 'fail':
            prop.status = 'Rejected'
            prop.publication_status = 'Under Verification'
            dab.status = 'Rejected'
            dab.updated_at = now

            prop_case = VerificationCase.query.filter_by(
                dab_id=dab.dab_id,
                verifier_type='property'
            ).first()

            if not prop_case:
                prop_case = VerificationCase(
                    dab_id=dab.dab_id,
                    entity_type='property',
                    entity_id=prop.property_id,
                    verifier_type='property',
                    verification_type='property_verification',
                    status='Failed',
                    started_at=now,
                    completed_at=now,
                    assigned_to=admin_user_id,
                    result_details=json.dumps({"action": "PROPERTY_VERIFICATION_FAILED", "rejected_by": admin_user_id}),
                    created_at=now,
                    updated_at=now
                )
                db.session.add(prop_case)
            else:
                prop_case.status = 'Failed'
                prop_case.completed_at = now
                prop_case.assigned_to = admin_user_id
                prop_case.updated_at = now

            db.session.flush()

            v_evt = VerificationEvent(
                verification_case_id=prop_case.verification_case_id,
                event_type='PROPERTY_VERIFICATION_FAILED',
                description=f"Property verification failed for Property #{prop.property_id} by Admin #{admin_user_id}",
                data={"action": "PROPERTY_VERIFICATION_FAILED", "property_id": prop.property_id, "dab_id": dab.dab_id},
                status='Failed',
                created_by_user_id=admin_user_id,
                performed_by_user_id=admin_user_id,
                created_at=now
            )
            db.session.add(v_evt)

            db.session.commit()
            flash(f"Property verification for Property #{property_id} has failed (status: Rejected).", 'warning')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error verifying property #{property_id}: {e}")
        flash(f"An error occurred while verifying property #{property_id}: {str(e)}", 'danger')

    if case_id:
        return redirect(url_for('admin_intent_detail', case_id=case_id))
    return redirect(url_for('admin_intents'))


@app.route('/admin/properties/<int:property_id>/approve/', methods=['POST'])
@admin_required
def admin_approve_property(property_id):
    """
    Phase 8 Terminal Gate: Administrative Property Approval.
    Transitions verified property to Approved state:
    Property.status = 'Approved', DirectAssetBrief.status = 'Approved',
    Property.publication_status = 'Approved'.
    Prerequisites: Property.status must be 'Verified', all title documents Verified,
    all media Approved, Property VerificationCase status == 'Passed'.
    """
    prop = Property.query.get_or_404(property_id)
    dab = prop.dab

    if not dab:
        flash(f"Cannot approve Property #{property_id} because no parent DirectAssetBrief is associated.", 'danger')
        return redirect(url_for('admin_intents'))

    intent_case = VerificationCase.query.filter_by(dab_id=dab.dab_id).first()
    case_id = intent_case.verification_case_id if intent_case else None

    action = request.form.get('action', 'approve').lower()
    admin_user_id = session.get('user_id')
    now = datetime.utcnow()

    # Idempotency Check: Property already Approved
    if prop.status == 'Approved' and dab.status == 'Approved' and prop.publication_status in ['Approved', 'Private Listing', 'Public Listing']:
        flash(f"Property #{property_id} ('{prop.title}') is already APPROVED. Phase 8/9 complete.", 'info')
        if case_id:
            return redirect(url_for('admin_intent_detail', case_id=case_id))
        return redirect(url_for('admin_intents'))

    # Prerequisite Gate Validation: Property must be Verified
    if prop.status != 'Verified':
        flash(f"Cannot approve Property #{property_id}: Property status is currently '{prop.status}'. Property must be VERIFIED in Phase 7 before approval.", 'danger')
        if case_id:
            return redirect(url_for('admin_intent_detail', case_id=case_id))
        return redirect(url_for('admin_intents'))

    # Prerequisite Gate Validation: Property VerificationCase must exist and be Passed
    prop_case = VerificationCase.query.filter_by(
        dab_id=dab.dab_id,
        verifier_type='property'
    ).first()

    if not prop_case or prop_case.status != 'Passed':
        flash(f"Cannot approve Property #{property_id}: Property verification case is missing or not PASSED.", 'danger')
        if case_id:
            return redirect(url_for('admin_intent_detail', case_id=case_id))
        return redirect(url_for('admin_intents'))

    # Prerequisite Gate Validation: All submitted title documents must be Verified
    if prop.documents:
        unverified_docs = [d for d in prop.documents if d.review_status != 'Verified']
        if unverified_docs:
            rejected_docs = [d for d in unverified_docs if d.review_status == 'Rejected']
            if rejected_docs:
                flash(f"Cannot approve Property #{property_id}: One or more title documents have been REJECTED. All documents must be VERIFIED.", 'danger')
            else:
                flash(f"Cannot approve Property #{property_id}: All submitted title documents must be VERIFIED before approval.", 'danger')
            if case_id:
                return redirect(url_for('admin_intent_detail', case_id=case_id))
            return redirect(url_for('admin_intents'))

    # Prerequisite Gate Validation: All property media photos must be Approved
    if prop.media:
        unapproved_media = [m for m in prop.media if m.review_status != 'Approved']
        if unapproved_media:
            rejected_media = [m for m in unapproved_media if m.review_status == 'Rejected']
            if rejected_media:
                flash(f"Cannot approve Property #{property_id}: One or more property photos have been REJECTED. All media must be APPROVED.", 'danger')
            else:
                flash(f"Cannot approve Property #{property_id}: All property photos must be APPROVED before approval.", 'danger')
            if case_id:
                return redirect(url_for('admin_intent_detail', case_id=case_id))
            return redirect(url_for('admin_intents'))

    try:
        if action == 'approve':
            # 1. Phase 8/9 State Transition: Approved & Private Listing 72h window
            prop.status = 'Approved'
            prop.publication_status = 'Private Listing'
            prop.updated_at = now

            dab.status = 'Approved'
            dab.approved_at = dab.approved_at or now
            dab.updated_at = now

            db.session.flush()

            # 2. Log VerificationEvent: PROPERTY_APPROVED
            v_evt = VerificationEvent(
                verification_case_id=prop_case.verification_case_id,
                event_type='PROPERTY_APPROVED',
                description=f"Property #{prop.property_id} ('{prop.title}') approved by Admin #{admin_user_id}. Phase 8/9 complete.",
                data={
                    "action": "PROPERTY_APPROVED",
                    "property_id": prop.property_id,
                    "dab_id": dab.dab_id,
                    "approved_by_user_id": admin_user_id,
                    "property_status": "Approved",
                    "dab_status": "Approved",
                    "publication_status": "Private Listing",
                    "approved_at": dab.approved_at.isoformat(),
                    "timestamp": now.isoformat()
                },
                status='Passed',
                created_by_user_id=admin_user_id,
                performed_by_user_id=admin_user_id,
                created_at=now
            )
            db.session.add(v_evt)

            # 3. Log AuditLog & SecurityEvent
            audit_entry = AuditLog(
                user_id=admin_user_id,
                action='PROPERTY_APPROVED',
                entity_type='Property',
                entity_id=prop.property_id,
                resource_type='Property',
                resource_id=prop.property_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                previous_values={"status": "Verified", "publication_status": "Under Verification", "dab_status": "Under Verification"},
                new_values={"status": "Approved", "publication_status": "Private Listing", "dab_status": "Approved", "approved_at": dab.approved_at.isoformat()},
                created_at=now
            )
            db.session.add(audit_entry)

            sec_event = SecurityEvent(
                user_id=admin_user_id,
                event_type='PROPERTY_APPROVED',
                description=f"Property #{prop.property_id} ('{prop.title}') approved by admin #{admin_user_id}. Phase 8/9 complete.",
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec_event)

            db.session.commit()
            flash(f"Property #{property_id} ('{prop.title}') has been APPROVED successfully. Entered Private Listing (72-Hour Window). Phase 8/9 complete.", 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving property #{property_id}: {e}")
        flash(f"An error occurred while approving property #{property_id}: {str(e)}", 'danger')

    if case_id:
        return redirect(url_for('admin_intent_detail', case_id=case_id))
    return redirect(url_for('admin_intents'))


@app.route('/admin/properties/<int:property_id>/update-status/', methods=['POST'])
@admin_required
def admin_update_property_status(property_id):
    """
    Phase 10 Administrative Property Status Transition (Sold / Unavailable).
    Allows super administrators to transition an approved/listed property to:
    - 'Sold': Terminal state.
    - 'Unavailable': Owner/Platform availability hold.
    Prerequisites: Property must be in an approved/listing state ('Approved', 'Private Listing', 'Public Listing').
    Terminal State Protections:
    - Sold properties CANNOT return to Public Listing, Private Listing, or Unavailable.
    - Unavailable properties CANNOT be marked Sold directly without being active.
    - Unapproved properties CANNOT be marked Sold or Unavailable.
    """
    prop = Property.query.get_or_404(property_id)
    dab = prop.dab

    if not dab:
        flash(f"Cannot update Property #{property_id} status because no parent DirectAssetBrief is associated.", 'danger')
        return redirect(url_for('admin_intents'))

    intent_case = VerificationCase.query.filter_by(dab_id=dab.dab_id).first()
    case_id = intent_case.verification_case_id if intent_case else None

    action = request.form.get('action', '').lower().strip()
    admin_user_id = session.get('user_id')
    now = datetime.utcnow()

    # 1. Terminal State Protection: Property is already Sold
    if prop.publication_status == 'Sold' or prop.status == 'Sold':
        if action == 'sold':
            flash(f"Property #{property_id} ('{prop.title}') is already marked as SOLD.", 'info')
        else:
            flash(f"Cannot change status for Property #{property_id}: Property is SOLD. Sold is a non-reversible terminal state.", 'danger')
        if case_id:
            return redirect(url_for('admin_intent_detail', case_id=case_id))
        return redirect(url_for('admin_intents'))

    # 2. Prerequisite Gate: Property must be in Approved / Listed stage
    if prop.status not in ['Approved', 'Sold'] and prop.publication_status not in ['Approved', 'Private Listing', 'Public Listing', 'Sold', 'Unavailable']:
        flash(f"Cannot update status for Property #{property_id}: Property must be APPROVED before changing availability or marking as Sold. Current status is '{prop.status}'.", 'danger')
        if case_id:
            return redirect(url_for('admin_intent_detail', case_id=case_id))
        return redirect(url_for('admin_intents'))

    # 3. Transition: Action = 'sold'
    if action == 'sold':
        if prop.publication_status == 'Unavailable':
            flash(f"Cannot mark Property #{property_id} as Sold: Property is currently Unavailable.", 'danger')
            if case_id:
                return redirect(url_for('admin_intent_detail', case_id=case_id))
            return redirect(url_for('admin_intents'))

        previous_pub_status = prop.publication_status
        previous_prop_status = prop.status

        prop.publication_status = 'Sold'
        prop.status = 'Sold'
        prop.availability_status = 'Sold'
        prop.updated_at = now

        db.session.flush()

        prop_case = VerificationCase.query.filter_by(dab_id=dab.dab_id, verifier_type='property').first()
        if prop_case:
            v_evt = VerificationEvent(
                verification_case_id=prop_case.verification_case_id,
                event_type='PROPERTY_SOLD',
                description=f"Property #{prop.property_id} ('{prop.title}') marked as SOLD by Admin #{admin_user_id}. Phase 10 complete.",
                data={
                    "action": "PROPERTY_SOLD",
                    "property_id": prop.property_id,
                    "dab_id": dab.dab_id,
                    "admin_user_id": admin_user_id,
                    "previous_publication_status": previous_pub_status,
                    "new_publication_status": "Sold",
                    "timestamp": now.isoformat()
                },
                status='Passed',
                created_by_user_id=admin_user_id,
                performed_by_user_id=admin_user_id,
                created_at=now
            )
            db.session.add(v_evt)

        audit_entry = AuditLog(
            user_id=admin_user_id,
            action='PROPERTY_SOLD',
            entity_type='Property',
            entity_id=prop.property_id,
            resource_type='Property',
            resource_id=prop.property_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            previous_values={"status": previous_prop_status, "publication_status": previous_pub_status},
            new_values={"status": "Sold", "publication_status": "Sold", "availability_status": "Sold"},
            created_at=now
        )
        db.session.add(audit_entry)

        sec_event = SecurityEvent(
            user_id=admin_user_id,
            event_type='PROPERTY_SOLD',
            description=f"Property #{prop.property_id} ('{prop.title}') marked as SOLD by admin #{admin_user_id}.",
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)

        db.session.commit()
        flash(f"Property #{property_id} ('{prop.title}') has been marked as SOLD. Phase 10 terminal state active.", 'success')

    # 4. Transition: Action = 'unavailable'
    elif action == 'unavailable':
        if prop.publication_status == 'Unavailable':
            flash(f"Property #{property_id} ('{prop.title}') is already marked as UNAVAILABLE.", 'info')
            if case_id:
                return redirect(url_for('admin_intent_detail', case_id=case_id))
            return redirect(url_for('admin_intents'))

        previous_pub_status = prop.publication_status
        previous_prop_status = prop.status

        prop.publication_status = 'Unavailable'
        prop.availability_status = 'Unavailable'
        prop.updated_at = now

        db.session.flush()

        prop_case = VerificationCase.query.filter_by(dab_id=dab.dab_id, verifier_type='property').first()
        if prop_case:
            v_evt = VerificationEvent(
                verification_case_id=prop_case.verification_case_id,
                event_type='PROPERTY_UNAVAILABLE',
                description=f"Property #{prop.property_id} ('{prop.title}') marked as UNAVAILABLE by Admin #{admin_user_id}.",
                data={
                    "action": "PROPERTY_UNAVAILABLE",
                    "property_id": prop.property_id,
                    "dab_id": dab.dab_id,
                    "admin_user_id": admin_user_id,
                    "previous_publication_status": previous_pub_status,
                    "new_publication_status": "Unavailable",
                    "timestamp": now.isoformat()
                },
                status='Passed',
                created_by_user_id=admin_user_id,
                performed_by_user_id=admin_user_id,
                created_at=now
            )
            db.session.add(v_evt)

        audit_entry = AuditLog(
            user_id=admin_user_id,
            action='PROPERTY_UNAVAILABLE',
            entity_type='Property',
            entity_id=prop.property_id,
            resource_type='Property',
            resource_id=prop.property_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            previous_values={"status": previous_prop_status, "publication_status": previous_pub_status},
            new_values={"status": prop.status, "publication_status": "Unavailable", "availability_status": "Unavailable"},
            created_at=now
        )
        db.session.add(audit_entry)

        sec_event = SecurityEvent(
            user_id=admin_user_id,
            event_type='PROPERTY_UNAVAILABLE',
            description=f"Property #{prop.property_id} ('{prop.title}') marked as UNAVAILABLE by admin #{admin_user_id}.",
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)

        db.session.commit()
        flash(f"Property #{property_id} ('{prop.title}') has been marked as UNAVAILABLE.", 'warning')

    else:
        flash(f"Invalid status action specified for Property #{property_id}.", 'danger')

    if case_id:
        return redirect(url_for('admin_intent_detail', case_id=case_id))
    return redirect(url_for('admin_intents'))


# ==========================================
# PHASE 12 — ADMIN INSPECTION MANAGEMENT
# ==========================================

@app.route('/admin/inspections/')
@admin_required
def admin_inspections():
    status_filter = request.args.get('status', '').strip()
    query = Inspection.query.order_by(Inspection.requested_at.desc())

    if status_filter in ['Requested', 'Scheduled', 'Completed', 'Cancelled']:
        query = query.filter_by(status=status_filter)

    inspections_list = query.all()

    counts = {
        'total': Inspection.query.count(),
        'requested': Inspection.query.filter_by(status='Requested').count(),
        'scheduled': Inspection.query.filter_by(status='Scheduled').count(),
        'completed': Inspection.query.filter_by(status='Completed').count(),
        'cancelled': Inspection.query.filter_by(status='Cancelled').count(),
    }

    return render_template(
        'admin/inspections.html',
        title='Inspection Management — Odacity Admin',
        inspections=inspections_list,
        counts=counts,
        active_status=status_filter
    )


@app.route('/admin/inspections/<int:inspection_id>/schedule/', methods=['POST'])
@admin_required
def admin_schedule_inspection(inspection_id):
    admin_user_id = session.get('user_id')
    insp = Inspection.query.get_or_404(inspection_id)

    if insp.status not in ['Requested', 'Scheduled']:
        flash(f'Cannot schedule an inspection with terminal status "{insp.status}".', 'danger')
        return redirect(url_for('admin_inspections'))

    date_str = request.form.get('scheduled_for', '').strip()
    time_str = request.form.get('scheduled_time', '').strip()
    notes = request.form.get('inspector_notes', '').strip() or None

    if not date_str or not time_str:
        flash('Please provide both a valid schedule date and time.', 'warning')
        return redirect(url_for('admin_inspections'))

    try:
        scheduled_for_dt = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
    except ValueError:
        flash('Invalid inspection appointment date or time format.', 'danger')
        return redirect(url_for('admin_inspections'))

    if scheduled_for_dt < datetime.utcnow():
        flash('Inspection appointment date/time cannot be in the past.', 'danger')
        return redirect(url_for('admin_inspections'))

    prev_status = insp.status
    now = datetime.utcnow()
    insp.status = 'Scheduled'
    insp.scheduled_for = scheduled_for_dt
    insp.scheduled_at = now
    if notes:
        insp.inspector_notes = notes

    audit_entry = AuditLog(
        user_id=admin_user_id,
        action='INSPECTION_SCHEDULED',
        entity_type='Inspection',
        entity_id=insp.inspection_id,
        resource_type='Inspection',
        resource_id=insp.inspection_id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        previous_values={"status": prev_status},
        new_values={"status": "Scheduled", "scheduled_for": scheduled_for_dt.isoformat()},
        created_at=now
    )
    db.session.add(audit_entry)

    sec_event = SecurityEvent(
        user_id=admin_user_id,
        event_type='INSPECTION_SCHEDULED',
        description=f"Inspection #{inspection_id} scheduled for {scheduled_for_dt.strftime('%Y-%m-%d %H:%M')} by admin #{admin_user_id}.",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)

    db.session.commit()
    flash(f'Inspection #{inspection_id} has been successfully scheduled for {scheduled_for_dt.strftime("%b %d, %Y %H:%M")}.', 'success')
    return redirect(url_for('admin_inspections'))


@app.route('/admin/inspections/<int:inspection_id>/complete/', methods=['POST'])
@admin_required
def admin_complete_inspection(inspection_id):
    admin_user_id = session.get('user_id')
    insp = Inspection.query.get_or_404(inspection_id)

    # Correction B: Completion MUST accept ONLY Scheduled -> Completed
    if insp.status != 'Scheduled':
        flash(f'Cannot complete an inspection in status "{insp.status}". Inspection must be Scheduled first.', 'danger')
        return redirect(url_for('admin_inspections'))

    notes = request.form.get('inspector_notes', '').strip() or None
    prev_status = insp.status
    now = datetime.utcnow()

    insp.status = 'Completed'
    insp.completed_at = now
    if notes:
        insp.inspector_notes = notes

    audit_entry = AuditLog(
        user_id=admin_user_id,
        action='INSPECTION_COMPLETED',
        entity_type='Inspection',
        entity_id=insp.inspection_id,
        resource_type='Inspection',
        resource_id=insp.inspection_id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        previous_values={"status": prev_status},
        new_values={"status": "Completed", "completed_at": now.isoformat()},
        created_at=now
    )
    db.session.add(audit_entry)

    sec_event = SecurityEvent(
        user_id=admin_user_id,
        event_type='INSPECTION_COMPLETED',
        description=f"Inspection #{inspection_id} marked COMPLETED by admin #{admin_user_id}.",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)

    db.session.commit()
    flash(f'Inspection #{inspection_id} marked as COMPLETED.', 'success')
    return redirect(url_for('admin_inspections'))


@app.route('/admin/inspections/<int:inspection_id>/cancel/', methods=['POST'])
@admin_required
def admin_cancel_inspection(inspection_id):
    admin_user_id = session.get('user_id')
    insp = Inspection.query.get_or_404(inspection_id)

    if insp.status in ['Completed', 'Cancelled']:
        flash(f'Cannot cancel an inspection in terminal status "{insp.status}".', 'warning')
        return redirect(url_for('admin_inspections'))

    cancel_reason = request.form.get('notes', '').strip() or None
    prev_status = insp.status
    now = datetime.utcnow()

    insp.status = 'Cancelled'
    if cancel_reason:
        insp.notes = cancel_reason

    audit_entry = AuditLog(
        user_id=admin_user_id,
        action='INSPECTION_ADMIN_CANCELLED',
        entity_type='Inspection',
        entity_id=insp.inspection_id,
        resource_type='Inspection',
        resource_id=insp.inspection_id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        previous_values={"status": prev_status},
        new_values={"status": "Cancelled"},
        created_at=now
    )
    db.session.add(audit_entry)

    sec_event = SecurityEvent(
        user_id=admin_user_id,
        event_type='INSPECTION_ADMIN_CANCELLED',
        description=f"Inspection #{inspection_id} administratively CANCELLED by admin #{admin_user_id}.",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)

    db.session.commit()
    flash(f'Inspection #{inspection_id} has been administratively CANCELLED.', 'info')
    return redirect(url_for('admin_inspections'))


# ==========================================
# PHASE 13 — ADMIN OFFER MANAGEMENT & AUDIT ROUTE
# ==========================================

@app.route('/admin/offers/')
@admin_required
def admin_offers():
    status_filter = request.args.get('status', '').strip()
    query = Offer.query.order_by(Offer.submitted_at.desc())

    if status_filter:
        query = query.filter_by(status=status_filter)

    offers = query.all()

    return render_template(
        'admin/offers.html',
        title='Purchase Offers Audit — Odacity Admin',
        offers=offers,
        status_filter=status_filter
    )

import os
import json
import secrets
import logging
import uuid
from sqlalchemy import func
from decimal import Decimal
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash
from flask import render_template, request, redirect, url_for, flash, session, abort, send_from_directory
from flask import jsonify
from pkg.services.admin_overview import (
    get_business_snapshot, get_superadmin_tasks, get_performance_indices,
    get_funnel_metrics, get_activity_feed, get_metric_catalogue
)
from pkg import app
from pkg.models import db, User, Role, UserRole, VerificationCase, VerificationEvent, AuditLog, SecurityEvent, Property, DirectAssetBrief, PropertyDocument, PropertyMedia, Inspection, CustomerProfile, Offer, Transaction, Invoice, Payment, PerformanceGuarantee, GuaranteeCycle, GuaranteeEvent, GuaranteeSettlement, BankGuaranteeReference, Mandate, TransactionDocument, Referral, ReferralReward, ReferralEvent, GoldAccount, GoldReward, GoldEvent
from pkg.services.email_service import send_intent_approval_notification, send_intent_decline_notification, create_user_notification

logger = logging.getLogger(__name__)


ADMIN_ROLES = {
    'super admin', 'property admin', 'mandate manager', 'transaction manager',
    'finance admin', 'compliance admin', 'customer support', 'audit admin',
    'super_admin', 'property_admin', 'mandate_manager', 'transaction_manager',
    'finance_admin', 'compliance_admin', 'customer_support', 'audit_admin'
}

OPERATIONAL_ADMIN_ROLES = {
    'super admin', 'transaction manager', 'property admin', 'mandate manager',
    'super_admin', 'transaction_manager', 'property_admin', 'mandate_manager'
}

PHASE16_OPERATIONAL_ADMIN_ROLES = {
    'super admin', 'transaction manager', 'finance admin',
    'super_admin', 'transaction_manager', 'finance_admin'
}

PERFORMANCE_OPERATIONAL_ADMIN_ROLES = {
    'super admin', 'mandate manager', 'transaction manager',
    'super_admin', 'mandate_manager', 'transaction_manager'
}

SETTLEMENT_APPROVAL_ADMIN_ROLES = {
    'super admin', 'transaction manager', 'finance admin',
    'super_admin', 'transaction_manager', 'finance_admin'
}

SETTLEMENT_PAYMENT_ADMIN_ROLES = {
    'super admin', 'finance admin',
    'super_admin', 'finance_admin'
}

PROPERTY_ADMIN_ROLES = {
    'super admin', 'property admin', 'mandate manager',
    'super_admin', 'property_admin', 'mandate_manager'
}

COMPLIANCE_ADMIN_ROLES = {
    'super admin', 'compliance admin',
    'super_admin', 'compliance_admin'
}

SUPPORT_ADMIN_ROLES = {
    'super admin', 'customer support', 'property admin', 'mandate manager',
    'super_admin', 'customer_support', 'property_admin', 'mandate_manager'
}

AUDIT_ADMIN_ROLES = {
    'super admin', 'audit admin',
    'super_admin', 'audit_admin'
}


def has_admin_permission(user):
    """
    Verifies if a user has any of the 8 Master PRD administrative roles or is_super_admin flag.
    Master PRD Admin Roles:
    1. Super Admin
    2. Property Admin
    3. Mandate Manager
    4. Transaction Manager
    5. Finance Admin
    6. Compliance Admin
    7. Customer Support
    8. Audit Admin
    """
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return True
    if hasattr(user, 'user_roles') and user.user_roles:
        for ur in user.user_roles:
            if ur.role and ur.role.name:
                rname = ur.role.name.strip().lower()
                if rname in ADMIN_ROLES:
                    return True
    return False


def has_transaction_initiation_permission(user):
    """
    Verifies if an administrative user has operational initiation permissions for transactions.
    Operational Roles: Super Admin, Transaction Manager, Property Admin, Mandate Manager.
    Audit/Read-Only Roles: Finance Admin, Compliance Admin, Customer Support, Audit Admin (restricted from transaction initiation).
    """
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return True
    if hasattr(user, 'user_roles') and user.user_roles:
        for ur in user.user_roles:
            if ur.role and ur.role.name:
                rname = ur.role.name.strip().lower()
                if rname in OPERATIONAL_ADMIN_ROLES:
                    return True
    return False


def has_phase16_operational_permission(user):
    """
    Verifies if an administrative user has operational permissions for Phase 16 actions
    (Invoice Generation, Payment Recording, Transaction Progress Updates).
    Operational Roles: Super Admin, Transaction Manager, Finance Admin.
    Read-Only / Non-Operational Roles: Property Admin, Mandate Manager, Compliance Admin, Customer Support, Audit Admin.
    """
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return True
    if hasattr(user, 'user_roles') and user.user_roles:
        for ur in user.user_roles:
            if ur.role and ur.role.name:
                rname = ur.role.name.strip().lower()
                if rname in PHASE16_OPERATIONAL_ADMIN_ROLES:
                    return True
    return False


def has_performance_operational_permission(user):
    """
    Verifies if an administrative user has operational permissions for Performance Journey actions
    (Performance Guarantee Activation, Milestone/Event Recording).
    Operational Roles: Super Admin, Mandate Manager, Transaction Manager.
    Read-Only / Non-Operational Roles: Property Admin, Finance Admin, Compliance Admin, Customer Support, Audit Admin.
    """
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return True
    if hasattr(user, 'user_roles') and user.user_roles:
        for ur in user.user_roles:
            if ur.role and ur.role.name:
                rname = ur.role.name.strip().lower()
                if rname in PERFORMANCE_OPERATIONAL_ADMIN_ROLES:
                    return True
    return False


def has_settlement_approval_permission(user):
    """
    Verifies if an administrative user has permission to approve performance guarantee settlements.
    Operational Roles: Super Admin, Transaction Manager, Finance Admin.
    Read-Only / Non-Operational Roles: Property Admin, Mandate Manager, Compliance Admin, Customer Support, Audit Admin.
    """
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return True
    if hasattr(user, 'user_roles') and user.user_roles:
        for ur in user.user_roles:
            if ur.role and ur.role.name:
                rname = ur.role.name.strip().lower()
                if rname in SETTLEMENT_APPROVAL_ADMIN_ROLES:
                    return True
    return False


def has_settlement_payment_permission(user):
    """
    Verifies if an administrative user has permission to record performance guarantee settlement payments.
    Operational Roles: Super Admin, Finance Admin.
    Read-Only / Non-Operational Roles: Property Admin, Mandate Manager, Transaction Manager, Compliance Admin, Customer Support, Audit Admin.
    """
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return True
    if hasattr(user, 'user_roles') and user.user_roles:
        for ur in user.user_roles:
            if ur.role and ur.role.name:
                rname = ur.role.name.strip().lower()
                if rname in SETTLEMENT_PAYMENT_ADMIN_ROLES:
                    return True
    return False


def user_has_any_role(user, allowed_roles_set):
    """Helper to check if user is active and has any role in allowed_roles_set or is_super_admin."""
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return True
    if hasattr(user, 'user_roles') and user.user_roles:
        for ur in user.user_roles:
            if ur.role and ur.role.name:
                rname = ur.role.name.strip().lower()
                if rname in allowed_roles_set:
                    return True
    return False


def finance_admin_required(f):
    """Decorator allowing strictly Super Admin and Finance Admin for financial mutations."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))

        user = User.query.get(user_id)
        if not user or not user_has_any_role(user, SETTLEMENT_PAYMENT_ADMIN_ROLES):
            flash('Access denied. Financial administration privileges required.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def superadmin_required(f):
    """Decorator requiring strictly active Superadmin status."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))

        user = User.query.get(user_id)
        if not user or not user.is_active or not user.is_super_admin:
            flash('Access denied. Superadmin privileges required.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Legacy alias for superadmin_required where strict superadmin is needed."""
    return superadmin_required(f)


def admin_view_required(f):
    """Decorator allowing read-only administrative access for all 8 Master PRD roles."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))

        user = User.query.get(user_id)
        if not user or not has_admin_permission(user):
            flash('Access denied. Administrative privileges required.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def property_admin_required(f):
    """Decorator allowing Property Admin, Mandate Manager, and Super Admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))

        user = User.query.get(user_id)
        if not user or not user_has_any_role(user, PROPERTY_ADMIN_ROLES):
            flash('Access denied. Property administration privileges required.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def compliance_admin_required(f):
    """Decorator allowing strictly Compliance Admin and Super Admin for legal document verification."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))

        user = User.query.get(user_id)
        if not user or not user_has_any_role(user, COMPLIANCE_ADMIN_ROLES):
            flash('Access denied. Compliance administration privileges required.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def support_admin_required(f):
    """Decorator allowing Customer Support, Property Admin, Mandate Manager, and Super Admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))

        user = User.query.get(user_id)
        if not user or not user_has_any_role(user, SUPPORT_ADMIN_ROLES):
            flash('Access denied. Customer support privileges required.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def audit_admin_required(f):
    """Decorator allowing Audit Admin and Super Admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))

        user = User.query.get(user_id)
        if not user or not user_has_any_role(user, AUDIT_ADMIN_ROLES):
            flash('Access denied. Audit administration privileges required.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def transaction_admin_required(f):
    """
    Decorator to enforce server-side authorization for transaction administration routes.
    Allows all 8 Master PRD administrative roles (and Super Admin) to view transaction records.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))

        user = User.query.get(user_id)
        if not user or not has_admin_permission(user):
            flash('Access denied. Administrative privileges required.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def performance_admin_required(f):
    """
    Decorator to enforce server-side authorization for Phase 17 Performance Guarantee admin routes.
    Allows all 8 Master PRD administrative roles (and Super Admin) to view performance records.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in as an administrator to access the admin portal.', 'warning')
            return redirect(url_for('login', next=request.url))

        user = User.query.get(user_id)
        if not user or not has_admin_permission(user):
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
@admin_view_required
def admin_intents():
    """
    Admin Dashboard: List all submitted, approved, and declined enquiry intents (VerificationCases).
    Supports filtering by status and entity type.
    """
    status_filter = request.args.get('status', 'all')
    type_filter = request.args.get('type', 'all')
    property_id_param = request.args.get('property_id', type=int)

    query = VerificationCase.query

    if property_id_param:
        prop = Property.query.get(property_id_param)
        prop_vcase = VerificationCase.query.filter_by(entity_type='property', entity_id=property_id_param).first()
        if prop_vcase:
            query = query.filter_by(entity_type='property', entity_id=property_id_param)
        elif prop and prop.dab_id:
            query = query.filter_by(dab_id=prop.dab_id)
        else:
            query = query.filter_by(entity_type='property', entity_id=property_id_param)

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
        title='Admin Intent Management â€” Odacity'
    )


@app.route('/admin/intents/<int:case_id>/')
@admin_view_required
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
        title=f'Review Intent #{case_id} â€” Odacity Admin'
    )


@app.route('/admin/intents/<int:case_id>/approve/', methods=['POST'])
@property_admin_required
def admin_intent_approve(case_id):
    """
    State Transition: Submitted -> Passed (Intent Approved).
    Authorized for property administrators and mandate managers.
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

        # 7. Dispatch Email 2 (ONLY AFTER SUCCESSFUL COMMIT) & In-App Notification
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

            target_user = User.query.filter_by(email=email).first()
            if target_user:
                create_user_notification(
                    user_id=target_user.user_id,
                    notification_type='INTENT_APPROVED',
                    subject='Enquiry Intent Approved',
                    message=f'Your {get_entity_display_name(v_case.entity_type)} enquiry intent has been approved.',
                    url=link_url,
                    send_email=False
                )

        flash(f'Intent #{case_id} ({get_entity_display_name(v_case.entity_type)}) has been APPROVED successfully. Customized Listing Link created and notification sent.', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving intent #{case_id}: {e}")
        flash(f'An error occurred while approving Intent #{case_id}: {str(e)}', 'danger')

    return redirect(url_for('admin_intents'))


@app.route('/admin/intents/<int:case_id>/generate-link/', methods=['POST'])
@property_admin_required
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
@property_admin_required
def admin_intent_decline(case_id):
    """
    State Transition: Submitted -> Failed (Intent Declined).
    Authorized for property administrators and mandate managers.
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

            target_user = User.query.filter_by(email=email).first()
            if target_user:
                create_user_notification(
                    user_id=target_user.user_id,
                    notification_type='INTENT_DECLINED',
                    subject='Enquiry Intent Status Update',
                    message=f'Your {get_entity_display_name(v_case.entity_type)} enquiry intent has been reviewed.',
                    url='/dashboard/',
                    send_email=False
                )

        flash(f'Intent #{case_id} ({get_entity_display_name(v_case.entity_type)}) has been DECLINED.', 'warning')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error declining intent #{case_id}: {e}")
        flash(f'An error occurred while declining Intent #{case_id}: {str(e)}', 'danger')

    return redirect(url_for('admin_intents'))


@app.route('/admin/uploads/<path:filename>')
@admin_view_required
def admin_serve_upload(filename):
    """
    Secure Admin Endpoint: Serves uploaded verification documents (PDFs) to authorized admins.
    Prevents unauthenticated or public document exposure.
    """
    upload_folder = os.path.join(app.root_path, 'static', 'uploads')
    return send_from_directory(upload_folder, filename)


@app.route('/admin/documents/<int:document_id>/verify/', methods=['POST'])
@compliance_admin_required
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

    # G-25-02 Lock Enforcement: Prevent re-verification/mutation of locked verified document
    if doc.locked_at:
        flash(f"Document '{doc.document_type}' for Property #{prop.property_id if prop else document_id} is verified and locked against further modification.", 'warning')
        if case_id:
            return redirect(url_for('admin_intent_detail', case_id=case_id))
        return redirect(url_for('admin_intents'))

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
            doc.locked_at = now
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
@property_admin_required
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

        sec_event = SecurityEvent(
            user_id=admin_user_id,
            event_type='PROPERTY_MEDIA_REVIEWED',
            description=f"Property photo #{med.media_id} quality reviewed ({action}) by admin #{admin_user_id}",
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error reviewing media #{media_id}: {e}")
        flash(f"An error occurred while reviewing photo #{media_id}: {str(e)}", 'danger')

    if case_id:
        return redirect(url_for('admin_intent_detail', case_id=case_id))
    return redirect(url_for('admin_intents'))


@app.route('/admin/properties/<int:property_id>/verify/', methods=['POST'])
@property_admin_required
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
@property_admin_required
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

            # Phase 17 Corrected Performance Guarantee Clock Trigger:
            # When DAB Property is Approved & Listed, owner Performance Guarantee activates immediately using dab.approved_at
            if dab and dab.owner_profile_id:
                owner_guarantee = PerformanceGuarantee.query.filter_by(
                    property_id=prop.property_id,
                    owner_profile_id=dab.owner_profile_id,
                    guarantee_type='owner_guarantee',
                    status='Eligible'
                ).first()

                if not owner_guarantee:
                    owner_guarantee = PerformanceGuarantee.query.filter_by(
                        owner_profile_id=dab.owner_profile_id,
                        guarantee_type='owner_guarantee',
                        status='Eligible'
                    ).first()
                    if owner_guarantee and not owner_guarantee.property_id:
                        owner_guarantee.property_id = prop.property_id

                if owner_guarantee and owner_guarantee.status == 'Eligible':
                    if owner_guarantee.period_days is not None:
                        start_ts = dab.approved_at or now
                        owner_guarantee.status = 'Active'
                        owner_guarantee.start_at = start_ts
                        owner_guarantee.start_date = start_ts
                        owner_guarantee.end_date = start_ts + timedelta(days=owner_guarantee.period_days)

                        if owner_guarantee.cycle_days is not None:
                            existing_c1 = GuaranteeCycle.query.filter_by(
                                performance_guarantee_id=owner_guarantee.guarantee_id,
                                cycle_number=1
                            ).first()
                            if not existing_c1:
                                c1 = GuaranteeCycle(
                                    performance_guarantee_id=owner_guarantee.guarantee_id,
                                    cycle_number=1,
                                    cycle_start=start_ts.date(),
                                    cycle_end=(start_ts + timedelta(days=owner_guarantee.cycle_days)).date(),
                                    days_elapsed=0,
                                    days_remaining=owner_guarantee.cycle_days,
                                    status='Active',
                                    created_at=now
                                )
                                db.session.add(c1)

                        audit_pg = AuditLog(
                            user_id=admin_user_id,
                            action='PERFORMANCE_GUARANTEE_ACTIVATED',
                            entity_type='PerformanceGuarantee',
                            entity_id=owner_guarantee.guarantee_id,
                            previous_values={'status': 'Eligible', 'start_at': None},
                            new_values={'status': 'Active', 'start_at': start_ts.isoformat()},
                            ip_address=request.remote_addr,
                            created_at=now
                        )
                        db.session.add(audit_pg)

                        sec_pg = SecurityEvent(
                            user_id=admin_user_id,
                            event_type='PERFORMANCE_GUARANTEE_ACTIVATED',
                            description=f"Performance Guarantee #{owner_guarantee.guarantee_id} activated automatically upon property approval & listing (Approved at {start_ts.isoformat()}).",
                            ip_address=request.remote_addr,
                            created_at=now
                        )
                        db.session.add(sec_pg)

            db.session.commit()

            owner_user_id = dab.owner.user_id if (dab and dab.owner) else None
            if owner_user_id:
                create_user_notification(
                    user_id=owner_user_id,
                    notification_type='PROPERTY_APPROVED',
                    subject='Property Approved & Listed',
                    message=f'Your property "{prop.title}" has been approved and listed.',
                    url=f'/properties/{prop.property_id}/',
                    send_email=True
                )

            flash(f"Property #{property_id} ('{prop.title}') has been APPROVED successfully. Entered Private Listing (72-Hour Window). Phase 8/9 complete.", 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving property #{property_id}: {e}")
        flash(f"An error occurred while approving property #{property_id}: {str(e)}", 'danger')

    if case_id:
        return redirect(url_for('admin_intent_detail', case_id=case_id))
    return redirect(url_for('admin_intents'))


@app.route('/admin/properties/<int:property_id>/update-status/', methods=['POST'])
@property_admin_required
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
# PHASE 12 â€” ADMIN INSPECTION MANAGEMENT
# ==========================================

@app.route('/admin/inspections/')
@admin_view_required
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
        title='Inspection Management â€” Odacity Admin',
        inspections=inspections_list,
        counts=counts,
        active_status=status_filter
    )


@app.route('/admin/inspections/<int:inspection_id>/schedule/', methods=['POST'])
@support_admin_required
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

    buyer_user_id = insp.customer.user_id if insp.customer else None
    if buyer_user_id:
        create_user_notification(
            user_id=buyer_user_id,
            notification_type='INSPECTION_SCHEDULED',
            subject='Inspection Date Scheduled',
            message=f'Your inspection for "{insp.property.title if insp.property else "property"}" is scheduled for {scheduled_for_dt.strftime("%b %d, %Y %H:%M")}.',
            url='/renter/inspections/',
            send_email=True
        )

    flash(f'Inspection #{inspection_id} has been successfully scheduled for {scheduled_for_dt.strftime("%b %d, %Y %H:%M")}.', 'success')
    return redirect(url_for('admin_inspections'))


@app.route('/admin/inspections/<int:inspection_id>/complete/', methods=['POST'])
@property_admin_required
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

    buyer_user_id = insp.customer.user_id if insp.customer else None
    if buyer_user_id:
        create_user_notification(
            user_id=buyer_user_id,
            notification_type='INSPECTION_COMPLETED',
            subject='Inspection Completed',
            message=f'Your inspection for "{insp.property.title if insp.property else "property"}" has been marked as Completed.',
            url='/renter/inspections/',
            send_email=True
        )
    flash(f'Inspection #{inspection_id} marked as COMPLETED.', 'success')
    return redirect(url_for('admin_inspections'))


@app.route('/admin/inspections/<int:inspection_id>/cancel/', methods=['POST'])
@support_admin_required
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
# PHASE 13 â€” ADMIN OFFER MANAGEMENT & AUDIT ROUTE
# ==========================================

@app.route('/admin/offers/')
@admin_view_required
def admin_offers():
    status_filter = request.args.get('status', '').strip()
    query = Offer.query.order_by(Offer.submitted_at.desc())

    if status_filter:
        query = query.filter_by(status=status_filter)

    offers = query.all()

    return render_template(
        'admin/offers.html',
        title='Purchase Offers Audit â€” Odacity Admin',
        offers=offers,
        status_filter=status_filter
    )


# ==========================================
# PHASE 15 â€” ADMIN TRANSACTION AUDIT ROUTE
# ==========================================

@app.route('/admin/transactions/')
@transaction_admin_required
def admin_transactions():
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id) if user_id else None
    is_operational_admin = user_rec and has_phase16_operational_permission(user_rec)

    status_filter = request.args.get('status', '').strip()
    invoice_id_param = request.args.get('invoice_id', type=int)
    query = Transaction.query.order_by(Transaction.created_at.desc())

    if invoice_id_param:
        inv = Invoice.query.get(invoice_id_param)
        if inv and inv.transaction_id:
            query = query.filter_by(transaction_id=inv.transaction_id)
    elif status_filter:
        query = query.filter_by(status=status_filter)

    transactions = query.all()

    return render_template(
        'admin/transactions.html',
        title='Transactions Audit â€” Odacity Admin',
        transactions=transactions,
        status_filter=status_filter,
        is_operational_admin=is_operational_admin
    )


# ==========================================
# PHASE 16 â€” INVOICE, PAYMENT & PROGRESS ADMIN ROUTES
# ==========================================

@app.route('/admin/transactions/<int:transaction_id>/generate-invoice/', methods=['POST'])
@finance_admin_required
def admin_generate_invoice(transaction_id):
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id)

    tx = Transaction.query.get_or_404(transaction_id)

    # Prevent duplicate invoice creation: return existing active invoice if present
    existing_inv = Invoice.query.filter_by(transaction_id=tx.transaction_id).filter(Invoice.status != 'Cancelled').first()
    if existing_inv:
        flash(f'An active invoice ({existing_inv.invoice_number}) already exists for Transaction #{tx.transaction_id}.', 'info')
        return redirect(url_for('transaction_detail', transaction_id=tx.transaction_id))

    amt_due_dec = Decimal(str(tx.transaction_value or tx.total_amount or 0))

    while True:
        cand_ref = f"INV-{uuid.uuid4().hex[:8].upper()}"
        if not Invoice.query.filter_by(invoice_number=cand_ref).first():
            inv_number = cand_ref
            break

    now = datetime.utcnow()
    due_dt = now + timedelta(days=14)

    new_inv = Invoice(
        transaction_id=tx.transaction_id,
        invoice_number=inv_number,
        amount_due=amt_due_dec,
        amount_paid=Decimal('0.00'),
        issue_date=now.date(),
        due_date=due_dt,
        status='Issued',
        payment_instructions='Payment via Odacity platform bank transfer or secured gateway.',
        created_at=now
    )
    db.session.add(new_inv)
    db.session.flush()

    audit = AuditLog(
        user_id=user_id,
        action='INVOICE_GENERATED',
        entity_type='Invoice',
        entity_id=new_inv.invoice_id,
        previous_values=None,
        new_values={
            'invoice_number': inv_number,
            'transaction_id': tx.transaction_id,
            'amount_due': float(amt_due_dec),
            'status': 'Issued'
        },
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='INVOICE_GENERATED',
        description=f"Invoice {inv_number} issued for Transaction #{tx.transaction_id} by admin user #{user_id}",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)
    db.session.commit()

    buyer_user_id = tx.customer.user_id if tx.customer else None
    if buyer_user_id:
        create_user_notification(
            user_id=buyer_user_id,
            notification_type='INVOICE_GENERATED',
            subject=f'Invoice Generated for Transaction #{tx.transaction_id}',
            message=f'Invoice #{inv_number} for â‚¦{amt_due_dec:,.2f} is ready for payment.',
            url='/buyer/dashboard/',
            send_email=True
        )

    flash(f'Invoice {inv_number} successfully issued for Transaction #{tx.transaction_id}.', 'success')
    return redirect(url_for('transaction_detail', transaction_id=tx.transaction_id))


@app.route('/admin/transactions/<int:transaction_id>/invoices/<int:invoice_id>/record-payment/', methods=['POST'])
@finance_admin_required
def admin_record_payment(transaction_id, invoice_id):
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id)

    tx = Transaction.query.get_or_404(transaction_id)
    inv = Invoice.query.get_or_404(invoice_id)

    if inv.transaction_id != tx.transaction_id:
        flash('Invoice does not belong to the specified transaction.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    raw_amount = request.form.get('amount', '').strip()
    raw_ref = request.form.get('payment_reference', '').strip()
    payment_method = request.form.get('payment_method', 'bank_transfer').strip()

    try:
        pay_amt = Decimal(raw_amount)
    except Exception:
        flash('Invalid payment amount specified.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    if pay_amt <= Decimal('0.00'):
        flash('Payment amount must be greater than zero.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    amt_due_dec = Decimal(str(inv.amount_due or 0))
    amt_paid_dec = Decimal(str(inv.amount_paid or 0))
    outstanding = amt_due_dec - amt_paid_dec

    if pay_amt > outstanding:
        flash(f'Payment amount (â‚¦{pay_amt:,.2f}) exceeds outstanding invoice balance (â‚¦{outstanding:,.2f}).', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    if raw_ref:
        pay_ref = raw_ref
        if Payment.query.filter_by(payment_reference=pay_ref).first():
            flash(f'Duplicate payment reference {pay_ref} detected.', 'danger')
            return redirect(url_for('transaction_detail', transaction_id=transaction_id))
    else:
        while True:
            cand_ref = f"PAY-{uuid.uuid4().hex[:8].upper()}"
            if not Payment.query.filter_by(payment_reference=cand_ref).first():
                pay_ref = cand_ref
                break

    now = datetime.utcnow()
    new_payment = Payment(
        invoice_id=inv.invoice_id,
        transaction_id=tx.transaction_id,
        payment_reference=pay_ref,
        amount=pay_amt,
        method=payment_method,
        payment_method=payment_method,
        status='Completed',
        transaction_ref=tx.transaction_reference,
        paid_at=now,
        payment_date=now,
        reconciliation_note=f'Administratively recorded payment by admin #{user_id}',
        created_at=now
    )
    db.session.add(new_payment)

    new_total_paid = amt_paid_dec + pay_amt
    inv.amount_paid = new_total_paid
    if new_total_paid >= amt_due_dec:
        inv.status = 'Paid'
        inv.paid_at = now
    else:
        inv.status = 'Partially_Paid'

    audit_pay = AuditLog(
        user_id=user_id,
        action='PAYMENT_RECORDED',
        entity_type='Payment',
        entity_id=new_payment.payment_id,
        previous_values=None,
        new_values={
            'payment_reference': pay_ref,
            'amount': float(pay_amt),
            'invoice_id': inv.invoice_id,
            'invoice_status': inv.status
        },
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit_pay)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='PAYMENT_COMPLETED',
        description=f"Payment {pay_ref} of â‚¦{pay_amt:,.2f} recorded for Invoice {inv.invoice_number}",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)
    db.session.commit()

    buyer_user_id = tx.customer.user_id if tx.customer else None
    if buyer_user_id:
        create_user_notification(
            user_id=buyer_user_id,
            notification_type='PAYMENT_RECORDED',
            subject=f'Payment Confirmed for Invoice {inv.invoice_number}',
            message=f'Payment {pay_ref} of â‚¦{pay_amt:,.2f} has been recorded for Invoice {inv.invoice_number}.',
            url='/buyer/dashboard/',
            send_email=True
        )

    flash(f'Payment {pay_ref} of â‚¦{pay_amt:,.2f} recorded successfully.', 'success')
    return redirect(url_for('transaction_detail', transaction_id=transaction_id))


@app.route('/admin/transactions/<int:transaction_id>/update-status/', methods=['POST'])
@transaction_admin_required
def admin_update_transaction_status(transaction_id):
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id)
    if not user_rec or not has_phase16_operational_permission(user_rec):
        flash('Access denied. Operational privileges required to update transaction progress.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    tx = Transaction.query.get_or_404(transaction_id)

    new_status = request.form.get('new_status', '').strip()
    sequence = [
        'Initiated', 'Mandate', 'Terms_Accepted', 'Inspection',
        'Offer', 'Payment', 'Documentation', 'Completion'
    ]

    if new_status not in sequence:
        flash(f'Invalid status string: {new_status}', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    prev_status = tx.status
    curr_idx = sequence.index(prev_status) if prev_status in sequence else 0
    new_idx = sequence.index(new_status)

    if new_idx <= curr_idx:
        flash(f'Backward or duplicate transaction status transition from {prev_status} to {new_status} is not allowed.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    if new_status == 'Completion' and prev_status != 'Documentation':
        flash('Transactions can only reach Completion from the Documentation stage.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    now = datetime.utcnow()
    tx.status = new_status
    tx.updated_at = now
    if new_status == 'Completion':
        tx.completion_date = now
        try:
            from pkg.routes.user import process_referral_qualification
            process_referral_qualification(tx)
        except Exception as e:
            logger.error(f"Referral qualification trigger failed for transaction #{tx.transaction_id}: {e}")

    audit = AuditLog(
        user_id=user_id,
        action='TRANSACTION_PROGRESS_UPDATED',
        entity_type='Transaction',
        entity_id=tx.transaction_id,
        previous_values={'status': prev_status},
        new_values={'status': new_status},
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='TRANSACTION_PROGRESS_UPDATED',
        description=f"Transaction #{tx.transaction_id} ({tx.transaction_reference}) status updated from {prev_status} to {new_status}",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)
    db.session.commit()

    if new_status == 'Completion':
        buyer_user_id = tx.customer.user_id if tx.customer else None
        if buyer_user_id:
            create_user_notification(
                user_id=buyer_user_id,
                notification_type='TRANSACTION_COMPLETED',
                subject=f'Transaction #{tx.transaction_id} Completed',
                message=f'Congratulations! Your transaction #{tx.transaction_id} for property "{tx.property.title if tx.property else "property"}" is COMPLETED.',
                url='/buyer/dashboard/',
                send_email=True
            )

        owner_user_id = tx.property.dab.owner.user_id if (tx.property and tx.property.dab and tx.property.dab.owner) else None
        if owner_user_id:
            create_user_notification(
                user_id=owner_user_id,
                notification_type='TRANSACTION_COMPLETED',
                subject=f'Transaction #{tx.transaction_id} Completed',
                message=f'Transaction #{tx.transaction_id} for property "{tx.property.title if tx.property else "property"}" has been COMPLETED.',
                url='/owner/dashboard/',
                send_email=True
            )

    flash(f'Transaction status updated to {new_status}.', 'success')
    return redirect(url_for('transaction_detail', transaction_id=transaction_id))


DOC_OPERATIONAL_ADMIN_ROLES = {
    'super admin', 'transaction manager', 'property admin', 'mandate manager',
    'super_admin', 'transaction_manager', 'property_admin', 'mandate_manager'
}

def has_doc_operational_permission(user):
    """
    Verifies if an administrative user has operational permissions for Transaction Document review/approval.
    Operational Roles: Super Admin, Transaction Manager, Property Admin, Mandate Manager.
    Read-Only Roles: Finance Admin, Compliance Admin, Customer Support, Audit Admin.
    """
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return True
    if hasattr(user, 'user_roles') and user.user_roles:
        for ur in user.user_roles:
            if ur.role and ur.role.name:
                rname = ur.role.name.strip().lower()
                if rname in DOC_OPERATIONAL_ADMIN_ROLES:
                    return True
    return False


@app.route('/admin/transactions/<int:transaction_id>/documents/<int:document_id>/approve/', methods=['POST'])
@transaction_admin_required
def admin_approve_transaction_document(transaction_id, document_id):
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id)
    if not user_rec or not has_doc_operational_permission(user_rec):
        flash('Access denied. Operational privileges required to approve transaction documents.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    tx = Transaction.query.get_or_404(transaction_id)
    doc = TransactionDocument.query.get_or_404(document_id)

    if doc.transaction_id != tx.transaction_id:
        flash('Document record does not belong to the specified transaction.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    if doc.status == 'Approved':
        flash(f'Transaction document #{document_id} is already Approved.', 'warning')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    now = datetime.utcnow()
    prev_status = doc.status or 'Submitted'
    doc.status = 'Approved'

    audit = AuditLog(
        user_id=user_id,
        action='TRANSACTION_DOCUMENT_APPROVED',
        entity_type='TransactionDocument',
        entity_id=doc.transaction_document_id,
        previous_values={'status': prev_status},
        new_values={'status': 'Approved'},
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='TRANSACTION_DOCUMENT_APPROVED',
        description=f"Transaction document #{doc.transaction_document_id} ({doc.document_type}) approved for Transaction #{tx.transaction_id} by admin #{user_id}",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)
    db.session.commit()

    buyer_user_id = tx.customer.user_id if tx.customer else None
    if buyer_user_id:
        create_user_notification(
            user_id=buyer_user_id,
            notification_type='DOCUMENT_APPROVED',
            subject='Transaction Legal Document Approved',
            message=f'Legal document "{doc.document_type}" for Transaction #{tx.transaction_id} has been approved.',
            url='/buyer/dashboard/',
            send_email=True
        )

    flash(f'Transaction document "{doc.document_type}" (#{document_id}) approved successfully.', 'success')
    return redirect(url_for('transaction_detail', transaction_id=transaction_id))


@app.route('/admin/transactions/<int:transaction_id>/documents/<int:document_id>/reject/', methods=['POST'])
@transaction_admin_required
def admin_reject_transaction_document(transaction_id, document_id):
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id)
    if not user_rec or not has_doc_operational_permission(user_rec):
        flash('Access denied. Operational privileges required to reject transaction documents.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    tx = Transaction.query.get_or_404(transaction_id)
    doc = TransactionDocument.query.get_or_404(document_id)

    if doc.transaction_id != tx.transaction_id:
        flash('Document record does not belong to the specified transaction.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    now = datetime.utcnow()
    prev_status = doc.status or 'Submitted'
    doc.status = 'Rejected'

    audit = AuditLog(
        user_id=user_id,
        action='TRANSACTION_DOCUMENT_REJECTED',
        entity_type='TransactionDocument',
        entity_id=doc.transaction_document_id,
        previous_values={'status': prev_status},
        new_values={'status': 'Rejected'},
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='TRANSACTION_DOCUMENT_REJECTED',
        description=f"Transaction document #{doc.transaction_document_id} ({doc.document_type}) rejected for Transaction #{tx.transaction_id} by admin #{user_id}",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)
    db.session.commit()

    flash(f'Transaction document "{doc.document_type}" (#{document_id}) rejected.', 'warning')
    return redirect(url_for('transaction_detail', transaction_id=transaction_id))


@app.route('/admin/performance/', methods=['GET'])
@performance_admin_required
def admin_performance():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    is_operational = has_performance_operational_permission(user)
    can_approve_settlement = has_settlement_approval_permission(user)
    can_record_payment = has_settlement_payment_permission(user)

    status_filter = request.args.get('status', '').strip()
    settlement_id_param = request.args.get('settlement_id', type=int)

    query = PerformanceGuarantee.query
    if settlement_id_param:
        s = GuaranteeSettlement.query.get(settlement_id_param)
        if s and s.performance_guarantee_id:
            query = query.filter_by(guarantee_id=s.performance_guarantee_id)
    elif status_filter:
        query = query.filter_by(status=status_filter)

    perf_guarantees = query.order_by(PerformanceGuarantee.created_at.desc()).all()

    now = datetime.utcnow()
    for g in perf_guarantees:
        if g.start_at:
            elapsed = (now - g.start_at).days
            g.calc_days_elapsed = max(0, elapsed)
            if g.period_days is not None:
                g.calc_days_remaining = max(0, g.period_days - g.calc_days_elapsed)
            else:
                g.calc_days_remaining = None
        else:
            g.calc_days_elapsed = 0
            g.calc_days_remaining = g.period_days

        event_types = [e.event_type for e in g.events] if g.events else []
        g.has_m3 = 'Milestone_3_Months' in event_types
        g.has_m6 = 'Milestone_6_Months' in event_types
        g.pending_settlement = next((s for s in g.settlements if s.status == 'Pending'), None) if g.settlements else None
        g.approved_settlement = next((s for s in g.settlements if s.status == 'Approved'), None) if g.settlements else None

    return render_template(
        'admin/performance.html',
        title='Performance Guarantee Engine â€” Odacity Admin',
        perf_guarantees=perf_guarantees,
        status_filter=status_filter,
        is_operational=is_operational,
        can_approve_settlement=can_approve_settlement,
        can_record_payment=can_record_payment
    )


@app.route('/admin/performance/<int:guarantee_id>/activate/', methods=['POST'])
@performance_admin_required
def admin_activate_performance_guarantee(guarantee_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    if not user or not has_performance_operational_permission(user):
        flash('Access denied. Operational privileges required to activate performance guarantees.', 'danger')
        return redirect(url_for('admin_performance'))

    guarantee = PerformanceGuarantee.query.get_or_404(guarantee_id)

    if guarantee.status != 'Eligible':
        flash(f'Cannot activate guarantee #{guarantee_id}. Current status is "{guarantee.status}" (must be "Eligible").', 'danger')
        return redirect(url_for('admin_performance'))

    if guarantee.period_days is None:
        flash(f'Cannot activate guarantee #{guarantee_id}: missing period_days configuration.', 'danger')
        return redirect(url_for('admin_performance'))

    if guarantee.cycle_days is None:
        flash(f'Cannot activate guarantee #{guarantee_id}: missing cycle_days configuration.', 'danger')
        return redirect(url_for('admin_performance'))

    prop = guarantee.property
    dab = prop.dab if prop else None
    start_ts = dab.approved_at if (dab and dab.approved_at) else guarantee.eligible_at

    if not start_ts:
        flash(f'Cannot activate guarantee #{guarantee_id}: DAB Property is not yet Approved & Listed (dab.approved_at missing).', 'danger')
        return redirect(url_for('admin_performance'))

    now = datetime.utcnow()
    period_days = guarantee.period_days
    cycle_days = guarantee.cycle_days

    guarantee.status = 'Active'
    guarantee.start_at = start_ts
    guarantee.start_date = start_ts
    guarantee.end_date = start_ts + timedelta(days=period_days)


    existing_c1 = GuaranteeCycle.query.filter_by(
        performance_guarantee_id=guarantee.guarantee_id,
        cycle_number=1
    ).first()

    if not existing_c1:
        cycle1 = GuaranteeCycle(
            performance_guarantee_id=guarantee.guarantee_id,
            cycle_number=1,
            cycle_start=start_ts.date(),
            cycle_end=(start_ts + timedelta(days=cycle_days)).date(),
            days_elapsed=0,
            days_remaining=cycle_days,
            status='Active',
            created_at=now
        )
        db.session.add(cycle1)

    audit = AuditLog(
        user_id=user_id,
        action='PERFORMANCE_GUARANTEE_ACTIVATED',
        entity_type='PerformanceGuarantee',
        entity_id=guarantee.guarantee_id,
        previous_values={'status': 'Eligible', 'start_at': None},
        new_values={'status': 'Active', 'start_at': start_ts.isoformat()},
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='PERFORMANCE_GUARANTEE_ACTIVATED',
        description=f'Performance Guarantee #{guarantee.guarantee_id} activated by user #{user_id} using property approval timestamp {start_ts.isoformat()}',
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)

    db.session.commit()

    flash(f'Performance Guarantee #{guarantee.guarantee_id} activated successfully using property approval timestamp.', 'success')
    return redirect(url_for('admin_performance'))


@app.route('/admin/performance/<int:guarantee_id>/trigger-milestone/', methods=['POST'])
@performance_admin_required
def admin_trigger_guarantee_milestone(guarantee_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    if not user or not has_performance_operational_permission(user):
        flash('Access denied. Operational privileges required to trigger milestones.', 'danger')
        return redirect(url_for('admin_performance'))

    guarantee = PerformanceGuarantee.query.get_or_404(guarantee_id)

    if guarantee.guarantee_type != 'owner_guarantee':
        flash(f'Guarantee #{guarantee_id} is not an owner performance guarantee.', 'danger')
        return redirect(url_for('admin_performance'))

    if guarantee.status not in ['Active', 'Completed', 'Redeemed_Partial', 'Redeemed_Full']:
        flash(f'Cannot trigger milestone for guarantee #{guarantee_id}. Current status is "{guarantee.status}".', 'danger')
        return redirect(url_for('admin_performance'))

    if not guarantee.start_at:
        flash(f'Cannot trigger milestone for guarantee #{guarantee_id}: start_at clock timestamp is missing.', 'danger')
        return redirect(url_for('admin_performance'))

    now = datetime.utcnow()
    elapsed_days = max(0, (now - guarantee.start_at).days)

    existing_events = GuaranteeEvent.query.filter_by(performance_guarantee_id=guarantee.guarantee_id).all()
    recorded_types = {e.event_type for e in existing_events}

    recorded_milestones = []

    if elapsed_days >= 90 and 'Milestone_3_Months' not in recorded_types:
        evt3 = GuaranteeEvent(
            performance_guarantee_id=guarantee.guarantee_id,
            event_type='Milestone_3_Months',
            details=f'3-Month Milestone reached ({elapsed_days} days elapsed)',
            occurred_at=now,
            created_at=now
        )
        db.session.add(evt3)
        recorded_milestones.append('Milestone_3_Months')

        audit3 = AuditLog(
            user_id=user_id,
            action='GUARANTEE_MILESTONE_RECORDED',
            entity_type='PerformanceGuarantee',
            entity_id=guarantee.guarantee_id,
            previous_values=None,
            new_values={'event_type': 'Milestone_3_Months', 'elapsed_days': elapsed_days},
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(audit3)

        sec3 = SecurityEvent(
            user_id=user_id,
            event_type='GUARANTEE_MILESTONE_REACHED',
            description=f'Performance Guarantee #{guarantee.guarantee_id} reached 3-Month milestone ({elapsed_days} days elapsed)',
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec3)

    if elapsed_days >= 180 and 'Milestone_6_Months' not in recorded_types:
        evt6 = GuaranteeEvent(
            performance_guarantee_id=guarantee.guarantee_id,
            event_type='Milestone_6_Months',
            details=f'6-Month Milestone reached ({elapsed_days} days elapsed)',
            occurred_at=now,
            created_at=now
        )
        db.session.add(evt6)
        recorded_milestones.append('Milestone_6_Months')

        c1 = GuaranteeCycle.query.filter_by(
            performance_guarantee_id=guarantee.guarantee_id,
            cycle_number=1
        ).first()
        if c1 and c1.status == 'Active':
            c1.status = 'Completed'

        audit6 = AuditLog(
            user_id=user_id,
            action='GUARANTEE_MILESTONE_RECORDED',
            entity_type='PerformanceGuarantee',
            entity_id=guarantee.guarantee_id,
            previous_values=None,
            new_values={'event_type': 'Milestone_6_Months', 'elapsed_days': elapsed_days},
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(audit6)

        sec6 = SecurityEvent(
            user_id=user_id,
            event_type='GUARANTEE_MILESTONE_REACHED',
            description=f'Performance Guarantee #{guarantee.guarantee_id} reached 6-Month milestone ({elapsed_days} days elapsed)',
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec6)

    if recorded_milestones:
        db.session.commit()

        owner_user_id = guarantee.owner.user_id if guarantee.owner else None
        if owner_user_id:
            create_user_notification(
                user_id=owner_user_id,
                notification_type='GUARANTEE_MILESTONE',
                subject=f'Performance Guarantee #{guarantee_id} Milestone Reached',
                message=f'Recorded milestone(s) for Performance Guarantee #{guarantee_id}: {", ".join(recorded_milestones)}.',
                url='/owner/dashboard/',
                send_email=True
            )

        flash(f'Recorded milestone(s) for Guarantee #{guarantee_id}: {", ".join(recorded_milestones)}', 'success')
    else:
        flash(f'No new milestones to record for Guarantee #{guarantee_id} ({elapsed_days} days elapsed).', 'info')

    return redirect(url_for('admin_performance'))


@app.route('/admin/performance/sync-milestones/', methods=['POST'])
@performance_admin_required
def admin_sync_performance_milestones():
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    if not user or not has_performance_operational_permission(user):
        flash('Access denied. Operational privileges required to sync milestones.', 'danger')
        return redirect(url_for('admin_performance'))

    active_guarantees = PerformanceGuarantee.query.filter_by(
        guarantee_type='owner_guarantee',
        status='Active'
    ).all()

    now = datetime.utcnow()
    total_processed = 0
    total_milestones_recorded = 0

    for guarantee in active_guarantees:
        if not guarantee.start_at:
            continue

        elapsed_days = max(0, (now - guarantee.start_at).days)
        existing_events = GuaranteeEvent.query.filter_by(performance_guarantee_id=guarantee.guarantee_id).all()
        recorded_types = {e.event_type for e in existing_events}

        processed_for_g = False
        if elapsed_days >= 90 and 'Milestone_3_Months' not in recorded_types:
            evt3 = GuaranteeEvent(
                performance_guarantee_id=guarantee.guarantee_id,
                event_type='Milestone_3_Months',
                details=f'3-Month Milestone reached ({elapsed_days} days elapsed)',
                occurred_at=now,
                created_at=now
            )
            db.session.add(evt3)
            total_milestones_recorded += 1
            processed_for_g = True

            audit3 = AuditLog(
                user_id=user_id,
                action='GUARANTEE_MILESTONE_RECORDED',
                entity_type='PerformanceGuarantee',
                entity_id=guarantee.guarantee_id,
                previous_values=None,
                new_values={'event_type': 'Milestone_3_Months', 'elapsed_days': elapsed_days},
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(audit3)

            sec3 = SecurityEvent(
                user_id=user_id,
                event_type='GUARANTEE_MILESTONE_REACHED',
                description=f'Performance Guarantee #{guarantee.guarantee_id} reached 3-Month milestone ({elapsed_days} days elapsed)',
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec3)

        if elapsed_days >= 180 and 'Milestone_6_Months' not in recorded_types:
            evt6 = GuaranteeEvent(
                performance_guarantee_id=guarantee.guarantee_id,
                event_type='Milestone_6_Months',
                details=f'6-Month Milestone reached ({elapsed_days} days elapsed)',
                occurred_at=now,
                created_at=now
            )
            db.session.add(evt6)
            total_milestones_recorded += 1
            processed_for_g = True

            c1 = GuaranteeCycle.query.filter_by(
                performance_guarantee_id=guarantee.guarantee_id,
                cycle_number=1
            ).first()
            if c1 and c1.status == 'Active':
                c1.status = 'Completed'

            audit6 = AuditLog(
                user_id=user_id,
                action='GUARANTEE_MILESTONE_RECORDED',
                entity_type='PerformanceGuarantee',
                entity_id=guarantee.guarantee_id,
                previous_values=None,
                new_values={'event_type': 'Milestone_6_Months', 'elapsed_days': elapsed_days},
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(audit6)

            sec6 = SecurityEvent(
                user_id=user_id,
                event_type='GUARANTEE_MILESTONE_REACHED',
                description=f'Performance Guarantee #{guarantee.guarantee_id} reached 6-Month milestone ({elapsed_days} days elapsed)',
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec6)

        if processed_for_g:
            total_processed += 1

    db.session.commit()
    flash(f'Batch milestone sync completed. Processed {total_processed} guarantees, recorded {total_milestones_recorded} milestone events.', 'success')
    return redirect(url_for('admin_performance'))


@app.route('/admin/performance/<int:guarantee_id>/initiate-redemption/', methods=['POST'])
@performance_admin_required
def admin_initiate_performance_redemption(guarantee_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    if not user or not has_performance_operational_permission(user):
        flash('Access denied. Operational privileges required to initiate redemption claims.', 'danger')
        return redirect(url_for('admin_performance'))

    guarantee = PerformanceGuarantee.query.get_or_404(guarantee_id)

    if guarantee.guarantee_type != 'owner_guarantee':
        flash(f'Guarantee #{guarantee_id} is not an owner performance guarantee.', 'danger')
        return redirect(url_for('admin_performance'))

    if guarantee.status in ['Redeemed_Full', 'Completed']:
        flash(f'Cannot initiate redemption for guarantee #{guarantee_id}. Current status is "{guarantee.status}".', 'danger')
        return redirect(url_for('admin_performance'))

    pending_settlement = GuaranteeSettlement.query.filter_by(
        performance_guarantee_id=guarantee.guarantee_id,
        status='Pending'
    ).first()
    if pending_settlement:
        flash(f'Guarantee #{guarantee_id} already has a pending redemption settlement (ID #{pending_settlement.id}).', 'danger')
        return redirect(url_for('admin_performance'))

    amount_raw = request.form.get('amount', '').strip()
    if not amount_raw:
        flash('Settlement amount is required.', 'danger')
        return redirect(url_for('admin_performance'))

    try:
        amount = Decimal(amount_raw)
    except Exception:
        flash(f'Invalid settlement amount format: {amount_raw}', 'danger')
        return redirect(url_for('admin_performance'))

    if amount <= 0:
        flash('Settlement amount must be positive.', 'danger')
        return redirect(url_for('admin_performance'))

    if guarantee.cap_amount is not None:
        cap_dec = Decimal(str(guarantee.cap_amount))
        if amount > cap_dec:
            flash(f'Settlement amount â‚¦{amount:,.2f} exceeds guarantee cap amount of â‚¦{cap_dec:,.2f}.', 'danger')
            return redirect(url_for('admin_performance'))

    now = datetime.utcnow()
    ref_note = request.form.get('reference', '').strip() or f'Redemption claim initiated by admin #{user_id}'

    settlement = GuaranteeSettlement(
        performance_guarantee_id=guarantee.guarantee_id,
        amount=amount,
        settlement_type='redemption',
        status='Pending',
        reference=ref_note,
        created_at=now
    )
    db.session.add(settlement)
    db.session.flush()

    evt = GuaranteeEvent(
        performance_guarantee_id=guarantee.guarantee_id,
        event_type='Redemption_Initiated',
        details=f'Redemption claim initiated for â‚¦{amount:,.2f}. Settlement ID #{settlement.id}',
        occurred_at=now,
        created_at=now
    )
    db.session.add(evt)

    audit = AuditLog(
        user_id=user_id,
        action='GUARANTEE_REDEMPTION_INITIATED',
        entity_type='GuaranteeSettlement',
        entity_id=settlement.id,
        previous_values=None,
        new_values={'guarantee_id': guarantee.guarantee_id, 'amount': float(amount), 'status': 'Pending'},
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit)

    sec = SecurityEvent(
        user_id=user_id,
        event_type='GUARANTEE_REDEMPTION_INITIATED',
        description=f'Redemption claim of â‚¦{amount:,.2f} initiated for Guarantee #{guarantee_id} (Settlement #{settlement.id})',
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec)
    db.session.commit()

    flash(f'Redemption claim of â‚¦{amount:,.2f} initiated for Guarantee #{guarantee_id} (Settlement ID #{settlement.id}).', 'success')
    return redirect(url_for('admin_performance'))


@app.route('/admin/performance/settlement/<int:settlement_id>/approve/', methods=['POST'])
@performance_admin_required
def admin_approve_guarantee_settlement(settlement_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    if not user or not has_settlement_approval_permission(user):
        flash('Access denied. Settlement approval privileges required.', 'danger')
        return redirect(url_for('admin_performance'))

    settlement = GuaranteeSettlement.query.get_or_404(settlement_id)

    if settlement.status != 'Pending':
        flash(f'Cannot approve settlement #{settlement_id}. Current status is "{settlement.status}" (must be "Pending").', 'danger')
        return redirect(url_for('admin_performance'))

    now = datetime.utcnow()
    settlement.status = 'Approved'
    settlement.approved_at = now

    audit = AuditLog(
        user_id=user_id,
        action='GUARANTEE_SETTLEMENT_APPROVED',
        entity_type='GuaranteeSettlement',
        entity_id=settlement.id,
        previous_values={'status': 'Pending'},
        new_values={'status': 'Approved', 'approved_at': now.isoformat()},
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit)

    sec = SecurityEvent(
        user_id=user_id,
        event_type='GUARANTEE_SETTLEMENT_APPROVED',
        description=f'Guarantee Settlement #{settlement.id} (â‚¦{settlement.amount:,.2f}) approved by user #{user_id}',
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec)
    db.session.commit()

    flash(f'Settlement #{settlement_id} approved successfully.', 'success')
    return redirect(url_for('admin_performance'))


@app.route('/admin/performance/settlement/<int:settlement_id>/record-payment/', methods=['POST'])
@performance_admin_required
def admin_record_guarantee_settlement_payment(settlement_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    if not user or not has_settlement_payment_permission(user):
        flash('Access denied. Settlement payment recording privileges required.', 'danger')
        return redirect(url_for('admin_performance'))

    settlement = GuaranteeSettlement.query.get_or_404(settlement_id)

    if settlement.status != 'Approved':
        flash(f'Cannot record payment for settlement #{settlement_id}. Current status is "{settlement.status}" (must be "Approved").', 'danger')
        return redirect(url_for('admin_performance'))

    now = datetime.utcnow()
    settlement.status = 'Paid'
    settlement.paid_at = now

    guarantee = settlement.performance_guarantee
    guarantee.settled_at = now

    evt = GuaranteeEvent(
        performance_guarantee_id=guarantee.guarantee_id,
        event_type='Settlement_Completed',
        details=f'Settlement #{settlement.id} payment of â‚¦{settlement.amount:,.2f} recorded.',
        occurred_at=now,
        created_at=now
    )
    db.session.add(evt)

    all_paid = GuaranteeSettlement.query.filter_by(
        performance_guarantee_id=guarantee.guarantee_id,
        status='Paid'
    ).all()
    paid_ids = {s.id for s in all_paid}
    if settlement.id not in paid_ids:
        all_paid.append(settlement)

    total_paid = sum(Decimal(str(s.amount)) for s in all_paid)

    if guarantee.cap_amount is not None:
        cap_dec = Decimal(str(guarantee.cap_amount))
        if total_paid >= cap_dec:
            guarantee.status = 'Redeemed_Full'
        else:
            guarantee.status = 'Redeemed_Partial'
    else:
        guarantee.status = 'Redeemed_Full'

    c1 = GuaranteeCycle.query.filter_by(
        performance_guarantee_id=guarantee.guarantee_id,
        cycle_number=1
    ).first()
    if c1 and c1.status in ['Active', 'Completed']:
        c1.status = 'Redeemed'

    audit = AuditLog(
        user_id=user_id,
        action='GUARANTEE_SETTLEMENT_PAID',
        entity_type='PerformanceGuarantee',
        entity_id=guarantee.guarantee_id,
        previous_values={'status': guarantee.status, 'settled_at': None},
        new_values={'status': guarantee.status, 'settled_at': now.isoformat(), 'settlement_id': settlement.id, 'amount': float(settlement.amount)},
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit)

    sec = SecurityEvent(
        user_id=user_id,
        event_type='GUARANTEE_SETTLEMENT_COMPLETED',
        description=f'Settlement #{settlement.id} payment of â‚¦{settlement.amount:,.2f} recorded for Guarantee #{guarantee.guarantee_id}. New guarantee status: {guarantee.status}',
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec)
    db.session.commit()

    flash(f'Settlement #{settlement_id} payment of â‚¦{settlement.amount:,.2f} recorded successfully. Guarantee status updated to {guarantee.status}.', 'success')
    return redirect(url_for('admin_performance'))


# ==========================================
# PHASE 20 â€” REFERRALS ADMIN CONTROL ROUTE
# ==========================================
@app.route('/admin/referrals/', methods=['GET'])
@admin_view_required
def admin_referrals():
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id) if user_id else None

    status_filter = request.args.get('status', 'all').strip()
    reward_id_param = request.args.get('reward_id', type=int)

    query = Referral.query.order_by(Referral.created_at.desc())
    if reward_id_param:
        gr = GoldReward.query.get(reward_id_param)
        if gr and gr.customer_id:
            query = query.filter(Referral.referrer_customer_id == gr.customer_id)
    elif status_filter and status_filter != 'all':
        query = query.filter_by(status=status_filter)

    referrals = query.all()

    total_referrals = Referral.query.count()
    attributed_count = Referral.query.filter_by(status='Attributed').count()
    qualified_count = Referral.query.filter_by(status='Qualified').count()
    completed_count = Referral.query.filter_by(status='Completed').count()

    total_reward_sum = db.session.query(func.sum(ReferralReward.reward_amount)).scalar() or 0.0

    return render_template(
        'admin/referrals.html',
        title='Referrals Audit & Governance â€” Odacity Admin',
        referrals=referrals,
        status_filter=status_filter,
        total_referrals=total_referrals,
        attributed_count=attributed_count,
        qualified_count=qualified_count,
        completed_count=completed_count,
        total_reward_sum=total_reward_sum,
        user=user_rec
    )


# ==========================================
# PHASE 24 â€” SUPERADMIN COMMAND CENTRE & BI
# ==========================================
@app.route('/admin/', methods=['GET'])
@superadmin_required
def admin_command_centre():
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id) if user_id else None

    view = request.args.get('view', 'operations').strip().lower()
    if view not in ['operations', 'performance']:
        view = 'operations'

    period = request.args.get('period', '30d').strip().lower()
    if period not in ['7d', '30d', '90d', '12m', 'all']:
        period = '30d'

    # Delegate aggregations to service layer
    snap = get_business_snapshot(period, user_rec)
    tasks = get_superadmin_tasks(user_rec)
    indices = get_performance_indices(period)
    funnel = get_funnel_metrics(period)
    feed = get_activity_feed(15)
    catalogue = get_metric_catalogue()

    # Maintain backward compatibility KPI dict
    kpis = {
        'total_users': snap['total_users'],
        'active_users': snap['active_users'],
        'new_users_period': snap['new_users_curr'],
        'admin_users_count': snap['admin_users_count'],
        'total_dabs': snap['total_dabs'],
        'pending_dabs': snap['pending_dabs'],
        'approved_dabs': snap['approved_dabs'],
        'dabs_period': snap['dabs_curr'],
        'total_props': snap['total_props'],
        'unverified_props': snap['unverified_props'],
        'published_props': snap['published_props'],
        'reserved_props': snap['reserved_props'],
        'properties_period': snap['props_curr'],
        'active_txs': snap['active_txs'],
        'completed_txs': snap['completed_txs_curr'],
        'total_tx_val': snap['tx_val_curr'],
        'total_commission': snap['commission_curr'],
        'requested_inspections': snap['requested_inspections'],
        'scheduled_inspections': snap['scheduled_inspections'],
        'inspections_period': snap['inspections_curr'],
        'submitted_offers': snap['submitted_offers'],
        'offers_period': snap['offers_curr'],
        'active_guarantees': snap['active_guarantees'],
        'total_earned_rewards': snap['total_earned_rewards'],
        'referrals_period': snap['referrals_curr'],
        'pending_withdrawals_sum': snap['pending_withdrawals_sum'],
        'pending_withdrawals_count': snap['pending_withdrawals_count'],
        'overdue_invoices_count': snap['overdue_invoices_count'],
    }

    # Backward compatibility alerts
    alerts = []
    if snap['pending_dabs'] > 0:
        alerts.append({
            'severity': 'warning',
            'title': 'DAB Review Bottleneck',
            'count': snap['pending_dabs'],
            'label': 'DAB(s) Pending Review',
            'description': 'Direct Asset Briefs submitted by users requiring verification.',
            'url': url_for('admin_intents')
        })
    if snap['unverified_props'] > 0:
        alerts.append({
            'severity': 'warning',
            'title': 'Unverified Property Supply',
            'count': snap['unverified_props'],
            'label': 'Property(ies) Unverified',
            'description': 'Listings pending compliance verification before publication.',
            'url': url_for('admin_intents')
        })
    if snap['requested_inspections'] > 0:
        alerts.append({
            'severity': 'info',
            'title': 'Requested Inspections',
            'count': snap['requested_inspections'],
            'label': 'Inspection(s) Requested',
            'description': 'Customer booking requests awaiting visit scheduling.',
            'url': url_for('admin_inspections')
        })
    if snap['submitted_offers'] > 0:
        alerts.append({
            'severity': 'primary',
            'title': 'Submitted Offers Queue',
            'count': snap['submitted_offers'],
            'label': 'Offer(s) Pending Review',
            'description': 'Buyer property offers awaiting evaluation.',
            'url': url_for('admin_offers')
        })
    if snap['pending_withdrawals_count'] > 0:
        alerts.append({
            'severity': 'danger',
            'title': 'Outstanding Cash Withdrawals',
            'count': snap['pending_withdrawals_count'],
            'label': 'Withdrawal Request(s)',
            'description': 'Pending cash reward redemptions requiring finance action.',
            'url': url_for('admin_referrals')
        })
    if snap['overdue_invoices_count'] > 0:
        alerts.append({
            'severity': 'warning',
            'title': 'Unpaid / Overdue Invoices',
            'count': snap['overdue_invoices_count'],
            'label': 'Unpaid Invoice(s)',
            'description': 'Transaction invoices currently outstanding.',
            'url': url_for('admin_transactions')
        })

    return render_template(
        'admin/command_centre.html',
        title='Superadmin Executive Control Centre — Odacity Admin',
        user=user_rec,
        view=view,
        period=period,
        snap=snap,
        tasks=tasks,
        indices=indices,
        funnel=funnel,
        feed=feed,
        catalogue=catalogue,
        kpis=kpis,
        alerts=alerts
    )


@app.route('/admin/task-centre/', methods=['GET'])
@superadmin_required
def admin_task_centre_feed():
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id) if user_id else None
    tasks_data = get_superadmin_tasks(user_rec)
    return jsonify(tasks_data)
# ==========================================
# PHASE 24 â€” ADMIN GOVERNANCE & USERS
# ==========================================
@app.route('/admin/users/', methods=['GET'])
@superadmin_required
def admin_users():
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id) if user_id else None

    users = User.query.order_by(User.created_at.desc()).all()
    roles = Role.query.order_by(Role.name).all()

    return render_template(
        'admin/users.html',
        title='Admin Governance & Access Control â€” Odacity Admin',
        users=users,
        roles=roles,
        user=user_rec
    )


@app.route('/admin/users/create/', methods=['POST'])
@superadmin_required
def admin_user_create():
    acting_user_id = session.get('user_id')

    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '')
    role_id = request.form.get('role_id')

    if not full_name or not email or not password:
        flash('Full Name, Email, and Password are required.', 'danger')
        return redirect(url_for('admin_users'))

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash(f'An account with email {email} already exists.', 'warning')
        return redirect(url_for('admin_users'))

    pw_hash = generate_password_hash(password)

    # Check if target role is Super Admin
    is_super = False
    target_role = None
    if role_id:
        target_role = Role.query.get(int(role_id))
        if target_role and target_role.name.strip().lower() in ('super admin', 'super_admin'):
            is_super = True

    new_user = User(
        email=email,
        password_hash=pw_hash,
        full_name=full_name,
        phone=phone or None,
        is_active=True,
        is_super_admin=is_super,
        created_at=datetime.utcnow()
    )
    db.session.add(new_user)
    db.session.flush()

    if target_role:
        user_role = UserRole(
            user_id=new_user.user_id,
            role_id=target_role.role_id,
            assigned_at=datetime.utcnow()
        )
        db.session.add(user_role)

    # Log Audit Entry
    audit = AuditLog(
        user_id=acting_user_id,
        action='USER_CREATE',
        entity_type='User',
        entity_id=new_user.user_id,
        new_values=json.dumps({
            'full_name': full_name,
            'email': email,
            'role': target_role.name if target_role else 'None',
            'is_super_admin': is_super
        }),
        created_at=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Admin user "{full_name}" created successfully.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/toggle-active/', methods=['POST'])
@superadmin_required
def admin_user_toggle_active(user_id):
    acting_user_id = session.get('user_id')

    if acting_user_id == user_id:
        flash('Action prohibited: You cannot deactivate your own active session account.', 'danger')
        return redirect(url_for('admin_users'))

    target_user = User.query.get_or_404(user_id)

    # Superadmin protection guard
    if target_user.is_super_admin:
        acting_user = User.query.get(acting_user_id)
        if not acting_user or not acting_user.is_super_admin:
            flash('Action prohibited: Non-Superadmins cannot deactivate a Superadmin account.', 'danger')
            return redirect(url_for('admin_users'))

    old_status = target_user.is_active
    target_user.is_active = not old_status

    audit = AuditLog(
        user_id=acting_user_id,
        action='USER_TOGGLE_ACTIVE',
        entity_type='User',
        entity_id=target_user.user_id,
        previous_values=json.dumps({'is_active': old_status}),
        new_values=json.dumps({'is_active': target_user.is_active}),
        created_at=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    status_str = 'activated' if target_user.is_active else 'deactivated'
    flash(f'User "{target_user.full_name or target_user.email}" has been {status_str}.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/assign-role/', methods=['POST'])
@superadmin_required
def admin_user_assign_role(user_id):
    acting_user_id = session.get('user_id')

    if acting_user_id == user_id:
        flash('Action prohibited: You cannot modify roles on your own active session account.', 'danger')
        return redirect(url_for('admin_users'))

    target_user = User.query.get_or_404(user_id)
    acting_user = User.query.get(acting_user_id)

    role_id_str = request.form.get('role_id')
    if not role_id_str:
        flash('Please select a valid role to assign.', 'warning')
        return redirect(url_for('admin_users'))

    role = Role.query.get_or_404(int(role_id_str))
    role_name_clean = role.name.strip().lower()

    # Guard: non-superadmin cannot assign superadmin role
    if role_name_clean in ('super admin', 'super_admin') and (not acting_user or not acting_user.is_super_admin):
        flash('Action prohibited: Only active Superadmins can assign the Super Admin role.', 'danger')
        return redirect(url_for('admin_users'))

    # F-24-06 FIX: Preserve existing role assignments for multi-role architecture
    existing_user_roles = UserRole.query.filter_by(user_id=target_user.user_id).all()
    old_roles = [ur.role.name for ur in existing_user_roles if ur.role]
    existing_role_ids = {ur.role_id for ur in existing_user_roles}

    if role.role_id not in existing_role_ids:
        new_user_role = UserRole(
            user_id=target_user.user_id,
            role_id=role.role_id,
            assigned_at=datetime.utcnow()
        )
        db.session.add(new_user_role)

    # Maintain is_super_admin consistency
    if role_name_clean in ('super admin', 'super_admin') or target_user.is_super_admin:
        target_user.is_super_admin = True

    audit = AuditLog(
        user_id=acting_user_id,
        action='USER_ROLE_ASSIGN',
        entity_type='User',
        entity_id=target_user.user_id,
        previous_values=json.dumps({'assigned_roles': old_roles}),
        new_values=json.dumps({'role_id': role.role_id, 'role_name': role.name, 'is_super_admin': target_user.is_super_admin}),
        created_at=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Role "{role.name}" assigned to "{target_user.full_name or target_user.email}" successfully.', 'success')
    return redirect(url_for('admin_users'))


# ==========================================
# PHASE 24 â€” CONTROLLED OVERRIDE ENGINE
# ==========================================
ALLOWED_RAW_OVERRIDE_TRANSITIONS = {
    'dab': {
        'Submitted': ['Under Verification'],
        'Rejected': ['Under Verification']
    },
    'property': {
        'Submitted': ['Under Verification'],
        'Under Verification': ['Archived'],
        'Available': ['Archived', 'Under Verification']
    },
    'inspection': {
        'Requested': ['Cancelled'],
        'Scheduled': ['Cancelled']
    },
    'transaction': {
        'Initiated': ['Cancelled'],
        'Mandate': ['Cancelled'],
        'Terms_Accepted': ['Cancelled'],
        'Inspection': ['Cancelled'],
        'Offer': ['Cancelled'],
        'Payment': ['Cancelled'],
        'Documentation': ['Cancelled']
    }
}


@app.route('/admin/override/<string:entity_type>/<int:entity_id>/', methods=['POST'])
@superadmin_required
def admin_controlled_override(entity_type, entity_id):
    acting_user_id = session.get('user_id')

    target_status = request.form.get('target_status', '').strip()
    override_reason = request.form.get('override_reason', '').strip()

    if not override_reason:
        flash('Override failed: A mandatory operational justification/reason must be provided.', 'danger')
        return redirect(request.referrer or url_for('admin_command_centre'))

    if not target_status:
        flash('Override failed: Target status is required.', 'danger')
        return redirect(request.referrer or url_for('admin_command_centre'))

    entity_type_clean = entity_type.strip().lower()
    if entity_type_clean not in ALLOWED_RAW_OVERRIDE_TRANSITIONS:
        flash(f'Invalid entity type "{entity_type}" for controlled override.', 'danger')
        return redirect(url_for('admin_command_centre'))

    # Fetch Entity & Current Status
    if entity_type_clean == 'dab':
        item = DirectAssetBrief.query.get_or_404(entity_id)
        old_status = item.status or 'Draft'
        entity_name = f'DAB #{item.dab_id}'
    elif entity_type_clean == 'property':
        item = Property.query.get_or_404(entity_id)
        old_status = item.publication_status or 'Draft'
        entity_name = f'Property #{item.property_id}'
    elif entity_type_clean == 'inspection':
        item = Inspection.query.get_or_404(entity_id)
        old_status = item.status or 'Requested'
        entity_name = f'Inspection #{item.inspection_id}'
    elif entity_type_clean == 'transaction':
        item = Transaction.query.get_or_404(entity_id)
        old_status = item.status or 'Initiated'
        entity_name = f'Transaction #{item.transaction_id}'

    # Validate Transition Matrix
    allowed_targets = ALLOWED_RAW_OVERRIDE_TRANSITIONS[entity_type_clean].get(old_status, [])
    if target_status not in allowed_targets:
        flash(f'Override failed: Transitioning {entity_name} from "{old_status}" to "{target_status}" via raw override is prohibited.', 'danger')
        return redirect(request.referrer or url_for('admin_command_centre'))

    # Execute Validated Raw State Mutation
    now = datetime.utcnow()
    if entity_type_clean == 'property':
        item.publication_status = target_status
    else:
        item.status = target_status

    # Audit Trail (Logged strictly on successful validation and mutation)
    audit = AuditLog(
        user_id=acting_user_id,
        action='CONTROLLED_OVERRIDE',
        entity_type=entity_type_clean.upper(),
        entity_id=entity_id,
        previous_values=json.dumps({'status': old_status}),
        new_values=json.dumps({
            'status': target_status,
            'override_reason': override_reason
        }),
        created_at=now
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Controlled override executed for {entity_name}: Status updated from "{old_status}" to "{target_status}". Reason: {override_reason}', 'success')
    return redirect(request.referrer or url_for('admin_command_centre'))


# ==========================================
# PHASE 24 â€” AUDIT LOG VIEWER
# ==========================================
@app.route('/admin/audit-logs/', methods=['GET'])
@audit_admin_required
def admin_audit_logs():
    user_id = session.get('user_id')
    user_rec = User.query.get(user_id) if user_id else None

    period = request.args.get('period', '30d').strip().lower()
    selected_action = request.args.get('action', 'all').strip()
    selected_entity_type = request.args.get('entity_type', 'all').strip()
    selected_admin_id = request.args.get('admin_id', 'all').strip()
    page = request.args.get('page', 1, type=int)

    query = AuditLog.query

    now = datetime.utcnow()
    if period == '7d':
        query = query.filter(AuditLog.created_at >= now - timedelta(days=7))
    elif period == '90d':
        query = query.filter(AuditLog.created_at >= now - timedelta(days=90))
    elif period == 'all':
        pass
    else:  # 30d default
        period = '30d'
        query = query.filter(AuditLog.created_at >= now - timedelta(days=30))

    if selected_action and selected_action != 'all':
        query = query.filter(AuditLog.action.ilike(f"%{selected_action}%"))

    if selected_entity_type and selected_entity_type != 'all':
        query = query.filter(AuditLog.entity_type.ilike(f"%{selected_entity_type}%"))

    if selected_admin_id and selected_admin_id != 'all':
        try:
            query = query.filter(AuditLog.user_id == int(selected_admin_id))
        except ValueError:
            pass

    query = query.order_by(AuditLog.created_at.desc())
    pagination = query.paginate(page=page, per_page=25, error_out=False)
    audit_logs = pagination.items

    actions = [row[0] for row in db.session.query(AuditLog.action).distinct().all() if row[0]]
    actions.sort()

    entity_types = [row[0] for row in db.session.query(AuditLog.entity_type).distinct().all() if row[0]]
    entity_types.sort()

    admin_users = User.query.filter((User.is_super_admin == True) | (User.user_roles.any())).order_by(User.full_name).all()

    return render_template(
        'admin/audit_logs.html',
        title='Audit Log Viewer â€” Odacity Admin',
        user=user_rec,
        audit_logs=audit_logs,
        pagination=pagination,
        actions=actions,
        entity_types=entity_types,
        admin_users=admin_users,
        period=period,
        selected_action=selected_action,
        selected_entity_type=selected_entity_type,
        selected_admin_id=selected_admin_id
    )

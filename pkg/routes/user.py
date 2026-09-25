import os
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse
from sqlalchemy.orm.attributes import flag_modified
from flask import render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image

from pkg import app
from pkg.models import db, User, CustomerProfile, PropertyOwnerProfile, DirectAssetBrief, SecurityEvent, Property, PropertyMedia, PropertyDocument, PerformanceGuarantee, SavedProperty, SavedSearch, Application, Inspection, Offer, Transaction, GoldReward, GoldAccount, Referral, ReferralReward, ReferralEvent, GoldEvent, Mandate, GuaranteeCycle, Notification, VerificationCase, VerificationEvent, AuditLog, Negotiation, Invoice, Payment, TransactionDocument
from pkg.forms import RegisterForm, LoginForm, CustomerProfileForm, CustomerKycForm, SavePropertyForm, SaveSearchForm, DeleteSavedSearchForm, RentalApplicationForm, ScheduleInspectionForm, CancelApplicationForm, CancelInspectionForm, PurchaseOfferForm, CancelOfferForm, PropertyOwnerProfileForm, DirectAssetBriefForm, RespondOfferForm, BuyerRespondOfferForm, DabInstitutionEnquiryForm, DabAgentEnquiryForm, DabIndividualEnquiryForm, GeneralEnquiryForm, ControlledPropertySubmissionForm
from pkg.services.email_service import send_enquiry_acknowledgement, create_user_notification
from pkg.routes.admin import has_admin_permission, has_transaction_initiation_permission, has_phase16_operational_permission, has_performance_operational_permission



# ==========================================
# PHASE 1 — ERROR HANDLERS
# ==========================================
@app.errorhandler(404)
def not_found_error(error):
    return render_template('user/404.html', title='404 Page Not Found'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('user/403.html', title='403 Access Denied'), 403

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('user/500.html', title='500 Internal System Error'), 500

def is_publicly_eligible(prop):
    """
    Phase 9 Helper: Determines if a property is eligible for public marketplace discovery (past 72h window or explicit Public Listing).
    """
    if not prop:
        return False
    if prop.publication_status == 'Public Listing':
        return True
    if prop.publication_status in ['Private Listing', 'Approved']:
        dab = prop.dab
        if dab and dab.approved_at:
            return datetime.utcnow() >= (dab.approved_at + timedelta(hours=72))
    return False


def is_authorized_for_private_property(prop):
    """
    Phase 9 Private Listing Security Gate:
    Determines if the current request/session is authorized to access a property
    during its 72-hour Private Listing window.

    Access is granted ONLY for:
    1. Super Administrators
    2. The Property Owner (owner of prop.dab)
    3. Requests carrying a valid customized listing link token matching prop.dab_id (via query ?token= or session).
    """
    if not prop or not prop.dab_id:
        return False

    user_id = session.get('user_id')
    if user_id:
        if session.get('is_super_admin') or session.get('user_role') == 'super_admin':
            return True
        user = User.query.get(user_id)
        if user and user.is_super_admin:
            return True

        owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
        if owner_prof and prop.dab and prop.dab.owner_profile_id == owner_prof.owner_profile_id:
            return True

    v_case = VerificationCase.query.filter_by(dab_id=prop.dab_id).first()
    if v_case and v_case.result_details:
        try:
            parsed = json.loads(v_case.result_details)
            if isinstance(parsed, dict) and 'customized_listing_link' in parsed:
                link_info = parsed['customized_listing_link']
                valid_token = link_info.get('token')
                if valid_token and link_info.get('status') == 'active':
                    req_token = request.args.get('token')
                    if req_token and req_token == valid_token:
                        customized_tokens = session.get('customized_tokens', {})
                        customized_tokens[str(prop.dab_id)] = valid_token
                        session['customized_tokens'] = customized_tokens
                        return True

                    customized_tokens = session.get('customized_tokens', {})
                    if customized_tokens.get(str(prop.dab_id)) == valid_token:
                        return True

                    if session.get('customized_token') == valid_token:
                        return True
        except Exception:
            pass

    return False


# ==========================================
# PHASE 2 — INTENT-DRIVEN PUBLIC WEBSITE ROUTES
# ==========================================

@app.route('/')
def homepage():
    """
    Odacity Intent-Driven Homepage.
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=72)
    featured_props = Property.query.outerjoin(DirectAssetBrief, Property.dab_id == DirectAssetBrief.dab_id).filter(
        db.or_(
            Property.publication_status == 'Public Listing',
            Property.publication_status == 'Approved',
            db.and_(
                Property.publication_status == 'Private Listing',
                DirectAssetBrief.approved_at != None,
                DirectAssetBrief.approved_at <= cutoff_time
            )
        )
    ).order_by(Property.created_at.desc()).limit(6).all()
    return render_template('user/index.html', title='Odacity — Direct Asset Briefs & Verified Real Estate', properties=featured_props)


@app.route('/rent/')
def rent_entry():
    return redirect(url_for('properties', intent='rent'))


@app.route('/buy/')
def buy_entry():
    return redirect(url_for('properties', intent='buy'))


@app.route('/properties/')
def properties():
    raw_intent = request.args.get('intent', '').lower().strip()
    if raw_intent == 'sale':
        raw_intent = 'buy'
    elif raw_intent == 'lease':
        raw_intent = 'rent'

    # Section 6 Hard Rule: No mixed default search. If intent is missing or invalid, redirect to explicit 'buy' intent
    if raw_intent not in ['buy', 'rent']:
        args = request.args.to_dict()
        args['intent'] = 'buy'
        return redirect(url_for('properties', **args))

    intent = raw_intent
    state = request.args.get('state', '').strip()
    location_input = request.args.get('location', '').strip() or state
    property_type = request.args.get('property_type', '').strip()
    min_price = request.args.get('min_price', '').strip()
    max_price = request.args.get('max_price', '').strip()
    price_range = request.args.get('price_range', '').strip()

    if price_range:
        if price_range.endswith('+'):
            try:
                min_price = price_range.rstrip('+')
            except ValueError:
                pass
        elif '-' in price_range:
            parts = price_range.split('-')
            if len(parts) == 2:
                if parts[0] != '0':
                    min_price = parts[0]
                max_price = parts[1]

    # Enforce publication filtering for public marketplace discovery (72-hour Private Listing window enforcement)
    cutoff_time = datetime.utcnow() - timedelta(hours=72)
    query = Property.query.outerjoin(DirectAssetBrief, Property.dab_id == DirectAssetBrief.dab_id).filter(
        db.or_(
            Property.publication_status == 'Public Listing',
            Property.publication_status == 'Approved',
            db.and_(
                Property.publication_status == 'Private Listing',
                DirectAssetBrief.approved_at != None,
                DirectAssetBrief.approved_at <= cutoff_time
            )
        )
    )

    if location_input:
        pattern = f'%{location_input}%'
        query = query.filter(
            db.or_(
                Property.state.ilike(pattern),
                Property.city.ilike(pattern),
                Property.locality.ilike(pattern),
                Property.location.ilike(pattern),
                Property.address.ilike(pattern)
            )
        )
    if property_type:
        query = query.filter(Property.property_type.ilike(f'%{property_type}%'))
    if min_price:
        try:
            query = query.filter(Property.price >= float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            query = query.filter(Property.price <= float(max_price))
        except ValueError:
            pass

    if intent == 'rent':
        query = query.filter(DirectAssetBrief.service_type.in_(['rent', 'lease']))
        query = query.filter(Property.property_type.notin_(['Land', 'Plot']))
    elif intent == 'buy':
        query = query.filter(DirectAssetBrief.service_type == 'sale')

    results = query.all()

    # If user authenticated, fetch saved property IDs for UI badges
    saved_prop_ids = []
    user_id = session.get('user_id')
    if user_id:
        cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
        if cust_profile:
            saved_items = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id).all()
            saved_prop_ids = [s.property_id for s in saved_items]

    return render_template('user/properties.html', title='Verified Listings', properties=results, intent=intent, saved_prop_ids=saved_prop_ids)


@app.route('/properties/<int:property_id>/')
def property_detail(property_id):
    intent = request.args.get('intent', '').lower()
    prop = Property.query.get_or_404(property_id)

    if prop.publication_status and prop.publication_status not in ['Approved', 'Private Listing', 'Public Listing']:
        flash('This property is not currently available for public viewing.', 'danger')
        return redirect(url_for('properties'))

    # Phase 9 Private Listing Access Control Gate
    if not is_publicly_eligible(prop):
        if not is_authorized_for_private_property(prop):
            flash('This property is currently in a Private Listing period. Controlled customized-listing authorization is required for access.', 'warning')
            return redirect(url_for('properties'))

    is_saved = False
    is_current_goal = False
    active_application = None
    active_inspection = None
    active_offer = None
    user_id = session.get('user_id')
    if user_id:
        cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
        if cust_profile:
            saved_rec = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id, property_id=property_id).first()
            if saved_rec:
                is_saved = True

            active_application = Application.query.filter(
                Application.customer_id == cust_profile.customer_id,
                Application.property_id == property_id,
                Application.status.notin_(['Cancelled', 'Rejected'])
            ).first()

            active_inspection = Inspection.query.filter(
                Inspection.customer_id == cust_profile.customer_id,
                Inspection.property_id == property_id,
                Inspection.status.notin_(['Cancelled', 'Completed', 'Rejected'])
            ).first()

            active_offer = Offer.query.filter(
                Offer.customer_id == cust_profile.customer_id,
                Offer.property_id == property_id,
                Offer.status.notin_(['Cancelled', 'Rejected', 'Expired'])
            ).first()

            prefs = cust_profile.preferences or {}
            if isinstance(prefs, str):
                try:
                    prefs = json.loads(prefs)
                except Exception:
                    prefs = {}
            if isinstance(prefs, dict):
                g_data = prefs.get('property_goal', {})
                if isinstance(g_data, dict) and g_data.get('property_id') == property_id:
                    is_current_goal = True

    app_form = RentalApplicationForm()
    insp_form = ScheduleInspectionForm()
    offer_form = PurchaseOfferForm()

    return render_template(
        'user/property_detail.html',
        title=prop.title,
        property=prop,
        intent=intent,
        is_saved=is_saved,
        is_current_goal=is_current_goal,
        active_application=active_application,
        active_inspection=active_inspection,
        active_offer=active_offer,
        app_form=app_form,
        insp_form=insp_form,
        offer_form=offer_form
    )




@app.route('/how-it-works/')
def how_it_works():
    return render_template('user/how_it_works.html', title='How Odacity Works')


@app.route('/about/')
def about():
    return render_template('user/about.html', title='About Odacity')


@app.route('/contact/', methods=['GET', 'POST'])
def contact():
    """
    Phase 2 — General Enquiry Form Route with Controlled Persistence & Audit Trail.
    """
    form = GeneralEnquiryForm()

    if form.validate_on_submit():
        now = datetime.utcnow()
        user_id = session.get('user_id')

        # Build Structured JSON Payload (General Enquiry Information)
        payload = {
            "enquiry_type": "General Enquiry",
            "enquiry_stage": "Intent / Onboarding",
            "status": "Submitted",
            "applicant_particulars": {
                "name": form.general_name.data.strip(),
                "email": form.general_email.data.strip(),
                "phone": form.general_phone.data.strip(),
                "subject": form.general_subject.data.strip(),
                "message": form.general_message.data.strip()
            },
            "submitted_at": now.isoformat()
        }

        try:
            # 1. Create Controlled VerificationCase
            v_case = VerificationCase(
                entity_type='general_enquiry',
                verifier_type='owner',
                verification_type='General Enquiry',
                status='Submitted',
                notes=f"General Enquiry submitted by {form.general_name.data.strip()} - Subject: {form.general_subject.data.strip()}",
                created_at=now,
                updated_at=now
            )
            db.session.add(v_case)
            db.session.flush()

            # 2. Create VerificationEvent with Structured JSON Payload
            v_event = VerificationEvent(
                verification_case_id=v_case.verification_case_id,
                event_type='GENERAL_ENQUIRY_SUBMITTED',
                description=f"General Enquiry submitted by {form.general_name.data.strip()} ({form.general_email.data.strip()})",
                data=payload,
                status='Submitted',
                created_by_user_id=user_id,
                created_at=now
            )
            db.session.add(v_event)

            # 3. Create AuditLog Record
            audit_entry = AuditLog(
                user_id=user_id,
                action='GENERAL_ENQUIRY_SUBMITTED',
                entity_type='general_enquiry',
                entity_id=v_case.verification_case_id,
                resource_type='VerificationCase',
                resource_id=v_case.verification_case_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                new_values=payload,
                created_at=now
            )
            db.session.add(audit_entry)

            # 4. Create SecurityEvent Log
            sec_event = SecurityEvent(
                user_id=user_id,
                event_type='GENERAL_ENQUIRY_SUBMITTED',
                description=f'General Enquiry submitted by "{form.general_name.data.strip()}"',
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec_event)

            db.session.commit()

            # Dispatch Email 1 — Enquiry Submission Acknowledgement & In-App Notification
            try:
                send_enquiry_acknowledgement(form.general_email.data.strip(), form.general_name.data.strip(), "General Enquiry")
                if session.get('user_id'):
                    create_user_notification(
                        user_id=session.get('user_id'),
                        notification_type='ENQUIRY_SUBMITTED',
                        subject='General Enquiry Received',
                        message=f'Thank you, {form.general_name.data.strip()}! Your General Enquiry has been received.',
                        url='/dashboard/',
                        send_email=False
                    )
            except Exception:
                pass

            flash(f'Thank you, {form.general_name.data.strip()}! Your General Enquiry has been submitted successfully.', 'success')
            return redirect(url_for('contact'))

        except Exception as e:
            db.session.rollback()
            flash('An error occurred while saving your enquiry. Please try again or contact support.', 'danger')
            return render_template('user/contact.html', title='Contact Us — Odacity', form=form)

    return render_template('user/contact.html', title='Contact Us — Odacity', form=form)


@app.route('/onboarding/intent/')
@app.route('/intent/')
def intent_selection():
    """
    Odacity Intent & Onboarding Selection Hub.
    """
    return render_template('user/intent_selection.html', title='Select Your Intent & Onboarding Pathway — Odacity')


@app.route('/enquiry/individual/', methods=['GET', 'POST'])
def enquiry_individual():
    """
    Phase 2 — DAB Individual Onboarding Enquiry Form Route with Controlled Persistence & Audit Trail.
    """
    form = DabIndividualEnquiryForm()

    if form.validate_on_submit():
        file_id = form.dab_individual_id_document.data
        filename_id = getattr(file_id, 'filename', '') if file_id else ''
        ext_id = filename_id.rsplit('.', 1)[-1].lower() if '.' in filename_id else ''

        if ext_id != 'pdf':
            flash('Validation error: Valid Means of Identification must be in PDF format (.pdf only). Non-PDF files are rejected.', 'danger')
            return render_template('user/enquiry_individual.html', title='DAB Individual Enquiry', form=form)

        # Controlled Upload Directory Setup
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'dab_individual_documents')
        os.makedirs(upload_dir, exist_ok=True)

        now = datetime.utcnow()
        timestamp_str = now.strftime('%Y%m%d%H%M%S')

        safe_name_id = secure_filename(filename_id) or 'dab_individual_id.pdf'
        file_name_saved_id = f"dab_ind_{uuid.uuid4().hex[:8]}_{timestamp_str}_{safe_name_id}"
        full_path_id = os.path.join(upload_dir, file_name_saved_id)
        rel_path_id = f"uploads/dab_individual_documents/{file_name_saved_id}"

        created_files = []

        try:
            # 1. Save uploaded ID document file safely
            file_id.save(full_path_id)
            created_files.append(full_path_id)

            user_id = session.get('user_id')

            # 2. Build Structured JSON Payload (Individual Information)
            company_name_val = form.dab_individual_company_name.data.strip() if form.dab_individual_company_name.data else ''
            payload = {
                "enquiry_type": "DAB Individual",
                "enquiry_stage": "Intent / Onboarding",
                "status": "Submitted",
                "individual_particulars": {
                    "name": form.dab_individual_name.data.strip(),
                    "company_name": company_name_val,
                    "email": form.dab_individual_email.data.strip(),
                    "phone": form.dab_individual_phone.data.strip(),
                    "address": form.dab_individual_address.data.strip(),
                    "government_id_number": form.dab_individual_government_id.data.strip(),
                    "identification_document_reference": rel_path_id
                },
                "submitted_at": now.isoformat()
            }

            # 3. Create Controlled VerificationCase
            v_case = VerificationCase(
                entity_type='dab_individual',
                verifier_type='owner',
                verification_type='DAB Individual Onboarding',
                status='Submitted',
                notes=f"DAB Individual Enquiry submitted for {form.dab_individual_name.data.strip()}",
                created_at=now,
                updated_at=now
            )
            db.session.add(v_case)
            db.session.flush()

            # 4. Create VerificationEvent with Structured JSON Payload
            v_event = VerificationEvent(
                verification_case_id=v_case.verification_case_id,
                event_type='DAB_INDIVIDUAL_ENQUIRY_SUBMITTED',
                description=f"DAB Individual Enquiry submitted by {form.dab_individual_name.data.strip()}",
                data=payload,
                status='Submitted',
                created_by_user_id=user_id,
                created_at=now
            )
            db.session.add(v_event)

            # 5. Create AuditLog Record
            audit_entry = AuditLog(
                user_id=user_id,
                action='DAB_INDIVIDUAL_ENQUIRY_SUBMITTED',
                entity_type='dab_individual',
                entity_id=v_case.verification_case_id,
                resource_type='VerificationCase',
                resource_id=v_case.verification_case_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                new_values=payload,
                created_at=now
            )
            db.session.add(audit_entry)

            # 6. Create SecurityEvent Log
            sec_event = SecurityEvent(
                user_id=user_id,
                event_type='DAB_INDIVIDUAL_ENQUIRY_SUBMITTED',
                description=f'DAB Individual Enquiry submitted for "{form.dab_individual_name.data.strip()}"',
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec_event)

            db.session.commit()

            # Dispatch Email 1 — Enquiry Submission Acknowledgement & In-App Notification
            try:
                send_enquiry_acknowledgement(form.dab_individual_email.data.strip(), form.dab_individual_name.data.strip(), "DAB Individual")
                if user_id:
                    create_user_notification(
                        user_id=user_id,
                        notification_type='ENQUIRY_SUBMITTED',
                        subject='DAB Individual Enquiry Submitted',
                        message=f'Your DAB Individual Enquiry for "{form.dab_individual_name.data.strip()}" has been submitted.',
                        url='/dashboard/',
                        send_email=False
                    )
            except Exception:
                pass

            flash(f'Thank you! Your DAB Individual Enquiry for "{form.dab_individual_name.data.strip()}" has been submitted successfully.', 'success')
            return redirect(url_for('enquiry_individual'))

        except Exception as e:
            db.session.rollback()
            # Clean up newly created files on transaction failure
            for filepath in created_files:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
            flash('An error occurred while saving your enquiry. Please try again or contact support.', 'danger')
            return render_template('user/enquiry_individual.html', title='DAB Individual Enquiry', form=form)

    return render_template('user/enquiry_individual.html', title='DAB Individual Enquiry', form=form)


@app.route('/enquiry/institution/', methods=['GET', 'POST'])
def enquiry_institution():
    """
    Phase 2 — DAB Institution & Organization Enquiry Form Route with Controlled Persistence & Audit Trail.
    """
    form = DabInstitutionEnquiryForm()

    if form.validate_on_submit():
        file_a = form.inst_cac_cert.data
        filename_a = getattr(file_a, 'filename', '') if file_a else ''
        ext_a = filename_a.rsplit('.', 1)[-1].lower() if '.' in filename_a else ''

        if ext_a != 'pdf':
            flash('Validation error: CAC Registration Certificate must be in PDF format (.pdf only). Non-PDF files are rejected.', 'danger')
            return render_template('user/enquiry_institution.html', title='DAB Institution & Organization Enquiry', form=form)

        # Controlled Upload Directory Setup
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'cac_certificates')
        os.makedirs(upload_dir, exist_ok=True)

        now = datetime.utcnow()
        timestamp_str = now.strftime('%Y%m%d%H%M%S')

        safe_name_a = secure_filename(filename_a) or 'inst_cac_certificate.pdf'
        file_name_saved_a = f"inst_cac_{uuid.uuid4().hex[:8]}_{timestamp_str}_{safe_name_a}"
        full_path_a = os.path.join(upload_dir, file_name_saved_a)
        rel_path_a = f"uploads/cac_certificates/{file_name_saved_a}"

        created_files = []

        try:
            # 1. Save uploaded CAC Certificate file safely
            file_a.save(full_path_a)
            created_files.append(full_path_a)

            user_id = session.get('user_id')

            # 2. Build Structured JSON Payload (Section A Institution Information)
            payload = {
                "enquiry_type": "DAB Institution",
                "enquiry_stage": "Intent / Onboarding",
                "status": "Submitted",
                "institution_organization": {
                    "name": form.inst_name.data.strip(),
                    "contact_person": form.inst_contact_person.data.strip(),
                    "official_email": form.inst_official_email.data.strip(),
                    "phone": form.inst_phone.data.strip(),
                    "office_address": form.inst_office_address.data.strip(),
                    "organization_type": form.inst_org_type.data,
                    "cac_registration_number": form.inst_cac_reg_num.data.strip(),
                    "cac_certificate_reference": rel_path_a
                },
                "submitted_at": now.isoformat()
            }

            # 3. Create Controlled VerificationCase
            v_case = VerificationCase(
                entity_type='dab_institution',
                verifier_type='owner',
                verification_type='DAB Institution Onboarding',
                status='Submitted',
                notes=f"DAB Institution Enquiry submitted for {form.inst_name.data.strip()}",
                created_at=now,
                updated_at=now
            )
            db.session.add(v_case)
            db.session.flush()

            # 4. Create VerificationEvent with Structured JSON Payload
            v_event = VerificationEvent(
                verification_case_id=v_case.verification_case_id,
                event_type='DAB_INSTITUTION_ENQUIRY_SUBMITTED',
                description=f"DAB Institution & Organization Enquiry submitted by {form.inst_contact_person.data.strip()} ({form.inst_name.data.strip()})",
                data=payload,
                status='Submitted',
                created_by_user_id=user_id,
                created_at=now
            )
            db.session.add(v_event)

            # 5. Create AuditLog Record
            audit_entry = AuditLog(
                user_id=user_id,
                action='DAB_INSTITUTION_ENQUIRY_SUBMITTED',
                entity_type='dab_institution',
                entity_id=v_case.verification_case_id,
                resource_type='VerificationCase',
                resource_id=v_case.verification_case_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                new_values=payload,
                created_at=now
            )
            db.session.add(audit_entry)

            # 6. Create SecurityEvent Log
            sec_event = SecurityEvent(
                user_id=user_id,
                event_type='DAB_INSTITUTION_ENQUIRY_SUBMITTED',
                description=f'DAB Institution Enquiry submitted for "{form.inst_name.data.strip()}"',
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec_event)

            db.session.commit()

            # Dispatch Email 1 — Enquiry Submission Acknowledgement & In-App Notification
            try:
                send_enquiry_acknowledgement(form.inst_official_email.data.strip(), form.inst_contact_person.data.strip(), "DAB Institution")
                if user_id:
                    create_user_notification(
                        user_id=user_id,
                        notification_type='ENQUIRY_SUBMITTED',
                        subject='DAB Institution Enquiry Submitted',
                        message=f'Your DAB Institution Enquiry for "{form.inst_name.data.strip()}" has been submitted.',
                        url='/dashboard/',
                        send_email=False
                    )
            except Exception:
                pass

            flash(f'Thank you! Your DAB Institution & Organization Enquiry for "{form.inst_name.data.strip()}" has been submitted successfully.', 'success')
            return redirect(url_for('enquiry_institution'))

        except Exception as e:
            db.session.rollback()
            # Clean up newly created files on transaction failure
            for filepath in created_files:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
            flash('An error occurred while saving your enquiry. Please try again or contact support.', 'danger')
            return render_template('user/enquiry_institution.html', title='DAB Institution & Organization Enquiry', form=form)

    return render_template('user/enquiry_institution.html', title='DAB Institution & Organization Enquiry', form=form)


@app.route('/enquiry/agent/', methods=['GET', 'POST'])
def enquiry_agent():
    """
    Phase 2 — DAB Agent Onboarding Enquiry Form Route with Controlled Persistence & Audit Trail.
    """
    form = DabAgentEnquiryForm()

    if form.validate_on_submit():
        file_id = form.agent_id_document.data
        file_cac = form.agent_cac_certificate.data
        file_license = form.agent_license_proof.data

        allowed_exts = {'pdf', 'png', 'jpg', 'jpeg'}

        filename_id = getattr(file_id, 'filename', '') if file_id else ''
        filename_cac = getattr(file_cac, 'filename', '') if file_cac else ''
        filename_license = getattr(file_license, 'filename', '') if file_license else ''

        ext_id = filename_id.rsplit('.', 1)[-1].lower() if '.' in filename_id else ''
        ext_cac = filename_cac.rsplit('.', 1)[-1].lower() if '.' in filename_cac else ''
        ext_license = filename_license.rsplit('.', 1)[-1].lower() if '.' in filename_license else ''

        if ext_id not in allowed_exts or ext_cac not in allowed_exts or ext_license not in allowed_exts:
            flash('Validation error: All uploaded documents must be in PDF, PNG, JPG, or JPEG format. Unsupported files are rejected.', 'danger')
            return render_template('user/enquiry_agent.html', title='DAB Agent Enquiry', form=form)

        # Controlled Upload Directory Setup
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'agent_documents')
        os.makedirs(upload_dir, exist_ok=True)

        now = datetime.utcnow()
        timestamp_str = now.strftime('%Y%m%d%H%M%S')

        safe_name_id = secure_filename(filename_id) or 'agent_id_document.pdf'
        safe_name_cac = secure_filename(filename_cac) or 'agent_cac_certificate.pdf'
        safe_name_license = secure_filename(filename_license) or 'agent_license_proof.pdf'

        file_name_saved_id = f"agent_id_{uuid.uuid4().hex[:8]}_{timestamp_str}_{safe_name_id}"
        file_name_saved_cac = f"agent_cac_{uuid.uuid4().hex[:8]}_{timestamp_str}_{safe_name_cac}"
        file_name_saved_license = f"agent_license_{uuid.uuid4().hex[:8]}_{timestamp_str}_{safe_name_license}"

        full_path_id = os.path.join(upload_dir, file_name_saved_id)
        full_path_cac = os.path.join(upload_dir, file_name_saved_cac)
        full_path_license = os.path.join(upload_dir, file_name_saved_license)

        rel_path_id = f"uploads/agent_documents/{file_name_saved_id}"
        rel_path_cac = f"uploads/agent_documents/{file_name_saved_cac}"
        rel_path_license = f"uploads/agent_documents/{file_name_saved_license}"

        created_files = []

        try:
            # 1. Save uploaded document files safely
            file_id.save(full_path_id)
            created_files.append(full_path_id)

            file_cac.save(full_path_cac)
            created_files.append(full_path_cac)

            file_license.save(full_path_license)
            created_files.append(full_path_license)

            user_id = session.get('user_id')

            # 2. Build Structured JSON Payload (Agent Particulars)
            payload = {
                "enquiry_type": "DAB Agent",
                "enquiry_stage": "Intent / Onboarding",
                "status": "Submitted",
                "agent_particulars": {
                    "name": form.agent_name.data.strip(),
                    "company_name": form.agent_company_name.data.strip(),
                    "email": form.agent_email.data.strip(),
                    "phone": form.agent_phone.data.strip(),
                    "office_address": form.agent_office_address.data.strip(),
                    "cac_registration_number": form.agent_cac_reg_num.data.strip(),
                    "license_membership_number": form.agent_license_number.data.strip(),
                    "identification_type": form.agent_id_type.data,
                    "identification_number": form.agent_id_number.data.strip(),
                    "identification_document_reference": rel_path_id,
                    "cac_certificate_reference": rel_path_cac,
                    "license_membership_proof_reference": rel_path_license,
                    "declaration_accepted": form.agent_declaration.data
                },
                "submitted_at": now.isoformat()
            }

            # 3. Create Controlled VerificationCase
            v_case = VerificationCase(
                entity_type='dab_agent',
                verifier_type='owner',
                verification_type='DAB Agent Onboarding',
                status='Submitted',
                notes=f"DAB Agent Enquiry submitted for {form.agent_name.data.strip()} ({form.agent_company_name.data.strip()})",
                created_at=now,
                updated_at=now
            )
            db.session.add(v_case)
            db.session.flush()

            # 4. Create VerificationEvent with Structured JSON Payload
            v_event = VerificationEvent(
                verification_case_id=v_case.verification_case_id,
                event_type='DAB_AGENT_ENQUIRY_SUBMITTED',
                description=f"DAB Agent Enquiry submitted by {form.agent_name.data.strip()} ({form.agent_company_name.data.strip()})",
                data=payload,
                status='Submitted',
                created_by_user_id=user_id,
                created_at=now
            )
            db.session.add(v_event)

            # 5. Create AuditLog Record
            audit_entry = AuditLog(
                user_id=user_id,
                action='DAB_AGENT_ENQUIRY_SUBMITTED',
                entity_type='dab_agent',
                entity_id=v_case.verification_case_id,
                resource_type='VerificationCase',
                resource_id=v_case.verification_case_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                new_values=payload,
                created_at=now
            )
            db.session.add(audit_entry)

            # 6. Create SecurityEvent Log
            sec_event = SecurityEvent(
                user_id=user_id,
                event_type='DAB_AGENT_ENQUIRY_SUBMITTED',
                description=f'DAB Agent Enquiry submitted for "{form.agent_name.data.strip()}" ({form.agent_company_name.data.strip()})',
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec_event)

            db.session.commit()

            # Dispatch Email 1 — Enquiry Submission Acknowledgement & In-App Notification
            try:
                send_enquiry_acknowledgement(form.agent_email.data.strip(), form.agent_name.data.strip(), "DAB Agent")
                if user_id:
                    create_user_notification(
                        user_id=user_id,
                        notification_type='ENQUIRY_SUBMITTED',
                        subject='DAB Agent Enquiry Submitted',
                        message=f'Your DAB Agent Enquiry for "{form.agent_name.data.strip()}" has been submitted.',
                        url='/dashboard/',
                        send_email=False
                    )
            except Exception:
                pass

            flash(f'Thank you! Your DAB Agent Enquiry for "{form.agent_name.data.strip()}" ({form.agent_company_name.data.strip()}) has been submitted successfully.', 'success')
            return redirect(url_for('enquiry_agent'))

        except Exception as e:
            db.session.rollback()
            # Clean up newly created files on transaction failure
            for filepath in created_files:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
            flash('An error occurred while saving your enquiry. Please try again or contact support.', 'danger')
            return render_template('user/enquiry_agent.html', title='DAB Agent Enquiry', form=form)

    return render_template('user/enquiry_agent.html', title='DAB Agent Enquiry', form=form)


@app.route('/owners/')
def owners():
    return render_template('user/owners_landing.html', title='Property Owners')


# ==========================================
# PHASE 3 — CUSTOMER AUTHENTICATION ROUTES
# ==========================================

@app.route('/register/', methods=['GET', 'POST'])
def register():
    # Capture referral code from URL query string or session
    ref_param = request.args.get('ref', '').strip()
    if ref_param:
        session['referral_code'] = ref_param
    ref_code = session.get('referral_code', '')

    form = RegisterForm()
    if form.validate_on_submit():
        firstname = form.firstname.data.strip() if form.firstname.data else ''
        lastname = form.lastname.data.strip() if form.lastname.data else ''
        full_name = f"{firstname} {lastname}".strip()
        email = form.email.data.strip().lower() if form.email.data else ''
        phone = form.phone.data.strip() if form.phone.data else None
        password = form.password.data if form.password.data else ''
        confirm_pass = form.confirm_pass.data if form.confirm_pass.data else ''

        # Password mismatch check
        if password != confirm_pass:
            flash('Passwords do not match. Please re-enter your password.', 'danger')
            return render_template('user/register.html', title='Create an Account', form=form, ref_code=ref_code)

        # Application-level duplicate email check
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('An account with this email address already exists. Please log in.', 'danger')
            return render_template('user/register.html', title='Create an Account', form=form, ref_code=ref_code)

        try:
            pw_hash = generate_password_hash(password)
            now = datetime.utcnow()

            # Create User
            user = User(
                email=email,
                password_hash=pw_hash,
                full_name=full_name,
                phone=phone,
                is_active=True,
                is_super_admin=False,
                created_at=now,
                updated_at=now
            )
            db.session.add(user)
            db.session.flush()

            # Create CustomerProfile
            profile = CustomerProfile(
                user_id=user.user_id,
                created_at=now
            )
            db.session.add(profile)
            db.session.flush()

            # Process PRD Referral Attribution
            if ref_code:
                clean_code = ref_code.upper().replace('REF-OD-', '').replace('REF-', '').strip()
                try:
                    referrer_user_id = int(clean_code)
                    referrer_user = User.query.get(referrer_user_id)
                    if referrer_user and referrer_user.customer_profile:
                        referrer_profile = referrer_user.customer_profile
                        # Enforce PRD self-referral invalidation rule
                        if referrer_profile.customer_id != profile.customer_id:
                            existing_ref = Referral.query.filter_by(referred_customer_id=profile.customer_id).first()
                            if not existing_ref:
                                referral = Referral(
                                    referrer_customer_id=referrer_profile.customer_id,
                                    referred_customer_id=profile.customer_id,
                                    referral_code_used=ref_code,
                                    status='Attributed',
                                    relationship_created_at=now,
                                    created_at=now
                                )
                                db.session.add(referral)
                                db.session.flush()

                                ref_evt = ReferralEvent(
                                    referral_id=referral.referral_id,
                                    event_type='Registered',
                                    event_data={
                                        'referrer_customer_id': referrer_profile.customer_id,
                                        'referred_customer_id': profile.customer_id,
                                        'code': ref_code
                                    },
                                    occurred_at=now,
                                    created_at=now
                                )
                                db.session.add(ref_evt)

                                # Dispatch Referral Attributed Notification to Referrer
                                create_user_notification(
                                    user_id=referrer_profile.user_id,
                                    notification_type='REFERRAL_ATTRIBUTED',
                                    subject='New Referral Attributed',
                                    message=f'{user.full_name} has joined Odacity using your referral code.',
                                    url='/profile/',
                                    send_email=False
                                )
                                session.pop('referral_code', None)
                except ValueError:
                    pass

            # Log SecurityEvent
            sec_event = SecurityEvent(
                user_id=user.user_id,
                event_type='USER_REGISTER',
                description='Customer account registered successfully',
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec_event)

            db.session.commit()

            # Establish session
            session.clear()
            session['user_id'] = user.user_id

            flash('Account created successfully! Welcome to Odacity.', 'success')
            return redirect(url_for('homepage'))

        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating your account. Please try again.', 'danger')
            return render_template('user/register.html', title='Create an Account', form=form, ref_code=ref_code)

    return render_template('user/register.html', title='Create an Account', form=form, ref_code=ref_code)


@app.route('/login/', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower() if form.email.data else ''
        password = form.password.data if form.password.data else ''

        user = User.query.filter_by(email=email).first()

        # Generic authentication failure
        if not user or not check_password_hash(user.password_hash, password):
            if user:
                sec_event = SecurityEvent(
                    user_id=user.user_id,
                    event_type='USER_LOGIN_FAILED',
                    description='Failed login attempt (invalid password)',
                    ip_address=request.remote_addr,
                    created_at=datetime.utcnow()
                )
                db.session.add(sec_event)
                db.session.commit()
            flash('Invalid email or password.', 'danger')
            return render_template('user/login.html', title='Log In', form=form)

        # Active account check
        if not user.is_active:
            flash('Your account is currently inactive. Please contact support.', 'warning')
            return render_template('user/login.html', title='Log In', form=form)

        now = datetime.utcnow()
        user.last_login = now

        sec_event = SecurityEvent(
            user_id=user.user_id,
            event_type='USER_LOGIN_SUCCESS',
            description='Customer logged in successfully',
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)
        db.session.commit()

        # Clear and establish session
        session.clear()
        session['user_id'] = user.user_id

        flash(f'Welcome back, {user.full_name}!', 'success')

        next_page = request.args.get('next')
        if next_page and urlparse(next_page).netloc == '':
            return redirect(next_page)
        return redirect(url_for('dashboard'))

    return render_template('user/login.html', title='Log In', form=form)


@app.route('/logout/')
def logout():
    user_id = session.get('user_id')
    if user_id:
        try:
            now = datetime.utcnow()
            sec_event = SecurityEvent(
                user_id=user_id,
                event_type='USER_LOGOUT',
                description='Customer logged out successfully',
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec_event)
            db.session.commit()
        except Exception:
            db.session.rollback()

    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('homepage'))


# ==========================================
# PHASE 4 — CUSTOMER PROFILE & KYC ROUTES
# ==========================================

@app.route('/profile/', methods=['GET', 'POST'])
def profile():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to access your profile.', 'warning')
        return redirect(url_for('login', next=request.path))

    user = User.query.get_or_404(user_id)
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()

    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    form = CustomerProfileForm()

    if form.validate_on_submit():
        first_name = form.first_name.data.strip() if form.first_name.data else None
        last_name = form.last_name.data.strip() if form.last_name.data else None
        phone_number = form.phone_number.data.strip() if form.phone_number.data else None
        date_of_birth = form.date_of_birth.data
        gender = form.gender.data if form.gender.data else None
        address = form.address.data.strip() if form.address.data else None

        cust_profile.first_name = first_name
        cust_profile.last_name = last_name
        cust_profile.phone_number = phone_number
        cust_profile.date_of_birth = date_of_birth
        cust_profile.gender = gender
        cust_profile.address = address

        if first_name or last_name:
            full = f"{first_name or ''} {last_name or ''}".strip()
            if full:
                user.full_name = full
        if phone_number:
            user.phone = phone_number
        user.updated_at = datetime.utcnow()

        now = datetime.utcnow()
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='CUSTOMER_PROFILE_UPDATED',
            description='Customer profile updated successfully',
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)
        db.session.commit()

        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))

    elif request.method == 'GET':
        if cust_profile.first_name:
            form.first_name.data = cust_profile.first_name
        elif user.full_name:
            parts = user.full_name.split(' ', 1)
            form.first_name.data = parts[0]

        if cust_profile.last_name:
            form.last_name.data = cust_profile.last_name
        elif user.full_name:
            parts = user.full_name.split(' ', 1)
            if len(parts) > 1:
                form.last_name.data = parts[1]

        form.phone_number.data = cust_profile.phone_number or user.phone
        form.date_of_birth.data = cust_profile.date_of_birth
        form.gender.data = cust_profile.gender or ''
        form.address.data = cust_profile.address

    return render_template('user/profile.html', title='My Profile', form=form, user=user, profile=cust_profile)


@app.route('/kyc/', methods=['GET', 'POST'])
def kyc():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to complete identity verification.', 'warning')
        return redirect(url_for('login', next=request.path))

    user = User.query.get_or_404(user_id)
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()

    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    form = CustomerKycForm()

    if form.validate_on_submit():
        cust_profile.kyc_status = 'PENDING'
        cust_profile.verification_status = 'Pending'

        now = datetime.utcnow()
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='CUSTOMER_KYC_SUBMITTED',
            description='Customer submitted identity verification request',
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)
        db.session.commit()

        flash('Identity verification submitted successfully! Your status is now PENDING review.', 'success')
        return redirect(url_for('profile'))

    return render_template('user/kyc.html', title='Customer Identity Verification', form=form, user=user, profile=cust_profile)


# ==========================================
# PHASE 5 — SAVED PROPERTIES & SAVED SEARCHES ROUTES
# ==========================================

@app.route('/properties/<int:property_id>/save/', methods=['POST'])
def save_property(property_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to save properties to your favorites.', 'warning')
        return redirect(url_for('login', next=request.referrer or url_for('properties')))

    prop = Property.query.get_or_404(property_id)
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    # Application-side duplicate prevention
    existing = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id, property_id=property_id).first()
    if existing:
        flash(f'Property "{prop.title}" is already in your saved list.', 'info')
    else:
        saved = SavedProperty(
            customer_id=cust_profile.customer_id,
            property_id=property_id,
            saved_at=datetime.utcnow()
        )
        db.session.add(saved)

        now = datetime.utcnow()
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='PROPERTY_SAVED',
            description=f'Customer saved property #{property_id}',
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)
        db.session.commit()
        flash(f'Property "{prop.title}" saved to your favorites!', 'success')

    return redirect(request.referrer or url_for('saved_properties'))


@app.route('/properties/<int:property_id>/unsave/', methods=['POST'])
def unsave_property(property_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to manage saved properties.', 'warning')
        return redirect(url_for('login'))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        flash('Customer profile not found.', 'danger')
        return redirect(url_for('properties'))

    # Strict ownership filter (customer isolation)
    saved_item = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id, property_id=property_id).first()
    if saved_item:
        db.session.delete(saved_item)

        now = datetime.utcnow()
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='PROPERTY_UNSAVED',
            description=f'Customer removed property #{property_id} from saved list',
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)
        db.session.commit()
        flash('Property removed from your saved list.', 'info')
    else:
        flash('Saved property record not found.', 'warning')

    return redirect(request.referrer or url_for('saved_properties'))


@app.route('/saved-properties/')
def saved_properties():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view your saved properties.', 'warning')
        return redirect(url_for('login', next=request.path))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        saved_items = []
    else:
        saved_items = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id).order_by(SavedProperty.saved_at.desc()).all()

    return render_template('user/saved_properties.html', title='My Saved Properties', saved_items=saved_items)


@app.route('/save-search/', methods=['POST'])
def save_search():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to save search criteria.', 'warning')
        return redirect(url_for('login'))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    name = request.form.get('name', '').strip()
    if not name:
        flash('Please provide a name for your saved search.', 'warning')
        return redirect(request.referrer or url_for('properties'))

    intent = request.form.get('intent', '').strip()
    state = request.form.get('state', '').strip()
    property_type = request.form.get('property_type', '').strip()
    max_price = request.form.get('max_price', '').strip()

    criteria = {
        'intent': intent,
        'state': state,
        'property_type': property_type,
        'max_price': max_price
    }

    now = datetime.utcnow()
    saved = SavedSearch(
        customer_id=cust_profile.customer_id,
        name=name,
        search_criteria=criteria,
        created_at=now,
        saved_at=now
    )
    db.session.add(saved)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='SEARCH_SAVED',
        description=f'Customer saved search criteria "{name}"',
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)
    db.session.commit()

    flash(f'Search "{name}" saved successfully!', 'success')
    return redirect(url_for('saved_searches'))


@app.route('/saved-searches/')
def saved_searches():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view your saved searches.', 'warning')
        return redirect(url_for('login', next=request.path))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        searches = []
    else:
        searches = SavedSearch.query.filter_by(customer_id=cust_profile.customer_id).order_by(SavedSearch.saved_at.desc()).all()

    return render_template('user/saved_searches.html', title='My Saved Searches', saved_searches=searches)


@app.route('/saved-searches/<int:search_id>/delete/', methods=['POST'])
def delete_saved_search(search_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to manage saved searches.', 'warning')
        return redirect(url_for('login'))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        flash('Customer profile not found.', 'danger')
        return redirect(url_for('saved_searches'))

    # Customer isolation filter
    saved_search = SavedSearch.query.filter_by(saved_search_id=search_id, customer_id=cust_profile.customer_id).first()
    if saved_search:
        search_name = saved_search.name
        db.session.delete(saved_search)

        now = datetime.utcnow()
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='SEARCH_DELETED',
            description=f'Customer deleted saved search #{search_id}',
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)
        db.session.commit()

        flash(f'Saved search "{search_name or search_id}" deleted.', 'info')
    else:
        flash('Saved search record not found.', 'warning')

    return redirect(url_for('saved_searches'))


def get_customer_referral_context(user_id, cust_profile):
    ref_code = f"REF-OD-{user_id:05d}"
    ref_link = request.host_url.rstrip('/') + url_for('register', ref=ref_code)

    referrals_list = Referral.query.filter_by(referrer_customer_id=cust_profile.customer_id).order_by(Referral.created_at.desc()).all()
    referral_rewards = ReferralReward.query.filter_by(referrer_customer_id=cust_profile.customer_id).order_by(ReferralReward.created_at.desc()).all()
    gold_rewards = GoldReward.query.filter_by(customer_id=cust_profile.customer_id).order_by(GoldReward.created_at.desc()).all()
    gold_account = GoldAccount.query.filter_by(customer_id=cust_profile.customer_id).first()

    direct_referrals_count = len(referrals_list)
    qualified_referrals_count = len([r for r in referrals_list if r.status in ['Completed', 'Qualified']])
    pending_referrals_count = len([r for r in referrals_list if r.status not in ['Completed', 'Qualified']])

    gold_total = sum(float(r.amount) for r in gold_rewards if r.amount and r.reward_type != 'WITHDRAWAL')
    ref_total = sum(float(r.reward_amount) for r in referral_rewards if r.reward_amount)
    rewards_total = gold_total + ref_total

    gold_eligible = sum(float(r.amount) for r in gold_rewards if r.status in ['APPROVED', 'SETTLED', 'EARNED'] and r.reward_type != 'WITHDRAWAL' and r.amount)
    ref_eligible = sum(float(r.reward_amount) for r in referral_rewards if r.status in ['APPROVED', 'SETTLED'] and r.reward_amount)
    rewards_eligible = gold_eligible + ref_eligible

    return {
        'referral_code': ref_code,
        'referral_link': ref_link,
        'referrals_list': referrals_list,
        'referral_rewards': referral_rewards,
        'gold_rewards': gold_rewards,
        'gold_account': gold_account,
        'direct_referrals_count': direct_referrals_count,
        'qualified_referrals_count': qualified_referrals_count,
        'pending_referrals_count': pending_referrals_count,
        'rewards_total': rewards_total,
        'rewards_eligible': rewards_eligible,
        'rew_total': rewards_total,
        'rew_eligible': rewards_eligible
    }


def get_customer_property_goal_context(cust_profile):
    if not cust_profile:
        return {'property_goal': None}

    prefs = cust_profile.preferences or {}
    if not isinstance(prefs, dict):
        try:
            prefs = json.loads(prefs) if isinstance(prefs, str) else {}
        except Exception:
            prefs = {}

    goal_data = prefs.get('property_goal', {})
    if not isinstance(goal_data, dict) or not goal_data.get('property_id'):
        return {'property_goal': None}

    try:
        pid = int(goal_data.get('property_id'))
    except (ValueError, TypeError):
        return {'property_goal': None}

    prop = Property.query.get(pid)
    if not prop:
        return {'property_goal': None}

    service_type = 'sale'
    if prop.dab and prop.dab.service_type:
        service_type = prop.dab.service_type.lower()
    elif prop.property_type and 'rent' in prop.property_type.lower():
        service_type = 'rent'

    goal_type = goal_data.get('goal_type')
    if not goal_type:
        goal_type = 'Rental Property Goal' if service_type in ['rent', 'lease'] else 'Home Purchase Goal'

    target_amount = float(prop.price or 0.0)
    target_date_str = goal_data.get('target_date', '')

    # Derive Referral Rewards monetary contribution from Phase 20 ReferralReward records
    referral_rewards = ReferralReward.query.filter_by(
        referrer_customer_id=cust_profile.customer_id
    ).filter(ReferralReward.status.in_(['Approved', 'Settled', 'Earned', 'Paid'])).all()

    referral_rewards_total = sum(float(r.reward_amount or 0.0) for r in referral_rewards if r.reward_amount)

    # Gold Points & Account (Displayed SEPARATELY without monetary valuation)
    gold_acc = GoldAccount.query.filter_by(customer_id=cust_profile.customer_id).first()
    gold_points = gold_acc.current_points if gold_acc else 0

    # Remaining Opportunity calculation: Target Amount - Referral Rewards Contribution
    remaining_amount = max(0.0, target_amount - referral_rewards_total)

    # Progress percentage based on referral reward contribution towards target amount
    progress_percentage = min(100.0, round((referral_rewards_total / target_amount * 100.0), 2)) if target_amount > 0 else 0.0

    publication_status = prop.publication_status or prop.status or 'Available'
    is_available = publication_status not in ['Sold', 'Rented', 'Archived', 'Unavailable']

    # Get primary media image if exists
    primary_media = None
    if prop.media:
        primary_media = next((m for m in prop.media if m.is_primary and m.file_path), None)
        if not primary_media and prop.media:
            primary_media = prop.media[0]

    image_url = None
    if primary_media and primary_media.file_path:
        fp = primary_media.file_path
        image_url = fp if (fp.startswith('/') or fp.startswith('http')) else url_for('static', filename=fp)

    location_str = f"{prop.locality or prop.city or ''}, {prop.state or ''}".strip(', ') or prop.location or 'Lagos'

    # Dynamic Next Action recommendation based on customer's current lifecycle state
    active_tx = Transaction.query.filter_by(customer_id=cust_profile.customer_id).filter(Transaction.status != 'Completion').first()
    active_offer = Offer.query.filter_by(customer_id=cust_profile.customer_id).filter(Offer.status.in_(['Submitted', 'Under_Review', 'Counter_Offer'])).first()
    active_insp = Inspection.query.filter_by(customer_id=cust_profile.customer_id).filter(Inspection.status.in_(['Requested', 'Scheduled'])).first()

    if active_tx:
        next_action_title = f"Complete Transaction #{active_tx.transaction_id}"
        next_action_desc = f"Your transaction is currently at stage '{active_tx.status}'. Progress your transaction to move closer to your property goal."
        next_action_url = url_for('buyer_offers')
    elif active_offer:
        next_action_title = "Review Pending Offer"
        next_action_desc = f"Your offer of ₦{active_offer.offer_amount:,.2f} is under review. Check for owner responses."
        next_action_url = url_for('buyer_offers')
    elif active_insp:
        next_action_title = "Attend Inspection"
        next_action_desc = "An inspection is scheduled. Inspect your target property to proceed."
        next_action_url = url_for('renter_inspections')
    else:
        next_action_title = "Invite Referrals & Explore Properties"
        next_action_desc = "Share your referral link to earn referral rewards toward your property ambition."
        next_action_url = url_for('properties')

    days_remaining = None
    if target_date_str:
        try:
            t_date = datetime.strptime(target_date_str, '%Y-%m-%d')
            days_remaining = (t_date - datetime.utcnow()).days
            if days_remaining < 0:
                days_remaining = 0
        except ValueError:
            pass

    return {
        'property_goal': {
            'property_id': prop.property_id,
            'title': prop.title,
            'location': location_str,
            'image_url': image_url,
            'service_type': service_type,
            'goal_type': goal_type,
            'target_amount': target_amount,
            'target_date': target_date_str,
            'days_remaining': days_remaining,
            'referral_rewards_total': referral_rewards_total,
            'gold_points': gold_points,
            'remaining_amount': remaining_amount,
            'progress_percentage': progress_percentage,
            'is_available': is_available,
            'publication_status': publication_status,
            'next_action_title': next_action_title,
            'next_action_desc': next_action_desc,
            'next_action_url': next_action_url,
            'gold_valuation_status': 'Partnership valuation pending'
        }
    }


@app.route('/property-goal/set', methods=['POST'])
@app.route('/properties/<int:property_id>/set-goal/', methods=['POST'])
def set_property_goal(property_id=None):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to set your property goal.', 'warning')
        return redirect(url_for('login'))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        flash('Customer profile not found.', 'danger')
        return redirect(url_for('dashboard'))

    if property_id is None:
        raw_pid = request.form.get('property_id')
        try:
            property_id = int(raw_pid) if raw_pid else None
        except (ValueError, TypeError):
            property_id = None

    if not property_id:
        flash('Please select an existing Odacity property to set as your goal.', 'warning')
        return redirect(url_for('properties'))

    target_prop = Property.query.get(property_id)
    if not target_prop:
        flash('Selected property record was not found.', 'danger')
        return redirect(url_for('properties'))

    service_type = 'sale'
    if target_prop.dab and target_prop.dab.service_type:
        service_type = target_prop.dab.service_type.lower()
    elif target_prop.property_type and 'rent' in target_prop.property_type.lower():
        service_type = 'rent'

    goal_type = 'Rental Property Goal' if service_type in ['rent', 'lease'] else 'Home Purchase Goal'
    target_date_raw = request.form.get('target_date', '').strip()

    target_date = ''
    if target_date_raw:
        try:
            parsed_d = datetime.strptime(target_date_raw, '%Y-%m-%d')
            target_date = parsed_d.strftime('%Y-%m-%d')
        except ValueError:
            pass

    prefs = cust_profile.preferences or {}
    if not isinstance(prefs, dict):
        try:
            prefs = json.loads(prefs) if isinstance(prefs, str) else {}
        except Exception:
            prefs = {}

    prev_goal = prefs.get('property_goal', {})
    prefs['property_goal'] = {
        'property_id': target_prop.property_id,
        'goal_type': goal_type,
        'target_date': target_date,
        'updated_at': datetime.utcnow().isoformat()
    }

    cust_profile.preferences = prefs
    flag_modified(cust_profile, 'preferences')

    now = datetime.utcnow()
    audit_entry = AuditLog(
        user_id=user_id,
        action='PROPERTY_GOAL_UPDATED',
        entity_type='CustomerProfile',
        entity_id=cust_profile.customer_id,
        previous_values=prev_goal,
        new_values=prefs['property_goal'],
        ip_address=request.remote_addr if request else None,
        created_at=now
    )
    db.session.add(audit_entry)

    sec_entry = SecurityEvent(
        user_id=user_id,
        event_type='PROPERTY_GOAL_UPDATED',
        description=f"Property Goal set to: {target_prop.title} (#PROP-{target_prop.property_id})",
        ip_address=request.remote_addr if request else None,
        created_at=now
    )
    db.session.add(sec_entry)

    db.session.commit()
    flash(f'Property "{target_prop.title}" set as your Property Goal!', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/property-goal/remove', methods=['POST'])
def remove_property_goal():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to manage your property goal.', 'warning')
        return redirect(url_for('login'))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        flash('Customer profile not found.', 'danger')
        return redirect(url_for('dashboard'))

    prefs = cust_profile.preferences or {}
    if not isinstance(prefs, dict):
        try:
            prefs = json.loads(prefs) if isinstance(prefs, str) else {}
        except Exception:
            prefs = {}

    prev_goal = prefs.pop('property_goal', None)
    cust_profile.preferences = prefs
    flag_modified(cust_profile, 'preferences')

    now = datetime.utcnow()
    if prev_goal:
        audit_entry = AuditLog(
            user_id=user_id,
            action='PROPERTY_GOAL_REMOVED',
            entity_type='CustomerProfile',
            entity_id=cust_profile.customer_id,
            previous_values=prev_goal,
            new_values=None,
            ip_address=request.remote_addr if request else None,
            created_at=now
        )
        db.session.add(audit_entry)

        sec_entry = SecurityEvent(
            user_id=user_id,
            event_type='PROPERTY_GOAL_REMOVED',
            description="Property Goal removed",
            ip_address=request.remote_addr if request else None,
            created_at=now
        )
        db.session.add(sec_entry)

        db.session.commit()

    flash('Property Goal removed.', 'info')
    return redirect(request.referrer or url_for('dashboard'))


def process_referral_qualification(transaction):
    if not transaction or not transaction.customer_id:
        return None

    # Idempotency Guard: Avoid duplicate reward generation for the same qualifying transaction
    existing_reward = ReferralReward.query.filter_by(
        qualifying_transaction_id=transaction.transaction_id
    ).first()
    if existing_reward:
        return existing_reward

    referral = Referral.query.filter_by(
        referred_customer_id=transaction.customer_id
    ).filter(Referral.status != 'Completed').first()
    if not referral:
        return None

    now = datetime.utcnow()

    # Step 1: Explicit transition to Qualified
    referral.status = 'Qualified'
    referral.qualified_at = now

    trans_amount = float(transaction.total_amount or transaction.transaction_value or 0.0)
    odacity_earning = round(trans_amount * 0.10, 2)
    reward_amount = round(odacity_earning * 0.05, 2)  # Effective 0.5% of transaction value

    ref_evt_qual = ReferralEvent(
        referral_id=referral.referral_id,
        event_type='Qualifying_Transaction_Detected',
        event_data={'transaction_id': transaction.transaction_id, 'amount': trans_amount, 'reward_amount': reward_amount},
        occurred_at=now,
        created_at=now
    )
    db.session.add(ref_evt_qual)

    reward = ReferralReward(
        referral_id=referral.referral_id,
        qualifying_transaction_id=transaction.transaction_id,
        transaction_id=transaction.transaction_id,
        referrer_customer_id=referral.referrer_customer_id,
        status='Approved',
        transaction_value=trans_amount,
        odacity_earning=odacity_earning,
        reward_rate_percentage=5.00,
        reward_amount=reward_amount,
        calculated_at=now,
        approved_at=now,
        created_at=now
    )
    db.session.add(reward)

    gold_acc = GoldAccount.query.filter_by(customer_id=referral.referrer_customer_id).first()
    if not gold_acc:
        gold_acc = GoldAccount(customer_id=referral.referrer_customer_id, current_points=0, tier='Standard', created_at=now)
        db.session.add(gold_acc)
        db.session.flush()

    points_earned = int(trans_amount / 1000)
    gold_acc.current_points += points_earned
    gold_acc.last_activity_at = now

    gold_evt = GoldEvent(
        gold_account_id=gold_acc.gold_account_id,
        customer_profile_id=referral.referrer_customer_id,
        event_type='Referral_Reward',
        description=f'Earned {points_earned} Gold points for referred transaction #{transaction.transaction_id}',
        points_change=points_earned,
        amount=reward_amount,
        new_balance=gold_acc.current_points,
        balance_after=reward_amount,
        created_at=now
    )
    db.session.add(gold_evt)

    gold_reward = GoldReward(
        customer_id=referral.referrer_customer_id,
        reward_type='REFERRAL_BONUS',
        amount=reward_amount,
        status='APPROVED',
        created_at=now
    )
    db.session.add(gold_reward)

    # Step 2: Transition to Completed
    referral.status = 'Completed'

    referrer_user_id = referral.referrer.user_id if (referral.referrer and hasattr(referral.referrer, 'user_id')) else None
    if referrer_user_id:
        create_user_notification(
            user_id=referrer_user_id,
            notification_type='REFERRAL_QUALIFIED',
            subject='Referral Reward Earned!',
            message=f'Your referral has qualified! You earned a reward of ₦{reward_amount:,.2f} and {points_earned} Gold points.',
            url='/profile/',
            send_email=True
        )

    ref_evt_comp = ReferralEvent(
        referral_id=referral.referral_id,
        event_type='Reward_Settled',
        event_data={'reward_amount': reward_amount, 'status': 'Completed'},
        occurred_at=now,
        created_at=now
    )
    db.session.add(ref_evt_comp)

    # System-level Audit & Security logging
    referrer_user_id = referral.referrer.user_id if (referral.referrer and hasattr(referral.referrer, 'user_id')) else None
    ip_addr = request.remote_addr if request else None

    audit_entry = AuditLog(
        user_id=referrer_user_id,
        action='REFERRAL_QUALIFIED',
        entity_type='Referral',
        entity_id=referral.referral_id,
        previous_values={'status': 'Attributed'},
        new_values={'status': 'Completed', 'reward_amount': reward_amount, 'transaction_id': transaction.transaction_id},
        ip_address=ip_addr,
        created_at=now
    )
    db.session.add(audit_entry)

    sec_entry = SecurityEvent(
        user_id=referrer_user_id,
        event_type='REFERRAL_QUALIFIED',
        description=f"Referral #{referral.referral_id} qualified via transaction #{transaction.transaction_id}. Reward amount: NGN {reward_amount:.2f}",
        ip_address=ip_addr,
        created_at=now
    )
    db.session.add(sec_entry)

    audit_settle = AuditLog(
        user_id=referrer_user_id,
        action='REFERRAL_REWARD_SETTLED',
        entity_type='ReferralReward',
        entity_id=reward.referral_reward_id if hasattr(reward, 'referral_reward_id') else None,
        previous_values={'status': 'Pending'},
        new_values={'status': 'Approved', 'reward_amount': reward_amount},
        ip_address=ip_addr,
        created_at=now
    )
    db.session.add(audit_settle)

    db.session.commit()
    return reward


# ==========================================
# PHASE 6 — COMMON USER DASHBOARD ROUTE
# ==========================================

@app.route('/dashboard/')
def dashboard():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to access your dashboard.', 'warning')
        return redirect(url_for('login', next=request.path))

    user = User.query.get_or_404(user_id)
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()

    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    session['active_role'] = 'renter'

    saved_props_count = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id).count()
    saved_searches_count = SavedSearch.query.filter_by(customer_id=cust_profile.customer_id).count()
    applications_count = Application.query.filter_by(customer_id=cust_profile.customer_id).count()
    inspections_count = Inspection.query.filter_by(customer_id=cust_profile.customer_id).count()
    offers_count = Offer.query.filter_by(customer_id=cust_profile.customer_id).count()
    recent_events = SecurityEvent.query.filter_by(user_id=user_id).order_by(SecurityEvent.created_at.desc()).limit(5).all()

    # Seller metrics
    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    seller_props_count = 0
    received_offers_count = 0
    received_apps_count = 0
    if owner_prof:
        dabs = DirectAssetBrief.query.filter_by(owner_profile_id=owner_prof.owner_profile_id).all()
        seller_props_count = len(dabs)
        dab_ids = [d.dab_id for d in dabs]
        if dab_ids:
            props = Property.query.filter(Property.dab_id.in_(dab_ids)).all()
            prop_ids = [p.property_id for p in props]
            if prop_ids:
                received_offers_count = Offer.query.filter(Offer.property_id.in_(prop_ids)).count()
                received_apps_count = Application.query.filter(Application.property_id.in_(prop_ids)).count()

    ref_ctx = get_customer_referral_context(user_id, cust_profile)
    goal_ctx = get_customer_property_goal_context(cust_profile)

    return render_template(
        'user/dashboard.html',
        title='User Dashboard',
        user=user,
        profile=cust_profile,
        owner_profile=owner_prof,
        saved_props_count=saved_props_count,
        saved_searches_count=saved_searches_count,
        applications_count=applications_count,
        inspections_count=inspections_count,
        offers_count=offers_count,
        seller_props_count=seller_props_count,
        received_offers_count=received_offers_count,
        received_apps_count=received_apps_count,
        recent_events=recent_events,
        **ref_ctx,
        **goal_ctx
    )


# ==========================================
# DEDICATED BUYER DASHBOARD ROUTES
# ==========================================

@app.route('/buyer/dashboard/')
def buyer_dashboard():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to access your Buyer Dashboard.', 'warning')
        return redirect(url_for('login', next=request.path))

    user = User.query.get_or_404(user_id)
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()

    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    session['active_role'] = 'buyer'

    # Query Buyer Collections & Data
    saved_properties_list = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id).order_by(SavedProperty.saved_at.desc()).all()
    saved_searches_list = SavedSearch.query.filter_by(customer_id=cust_profile.customer_id).order_by(SavedSearch.created_at.desc()).all()
    inspections_list = Inspection.query.filter_by(customer_id=cust_profile.customer_id).order_by(Inspection.requested_at.desc()).all()
    offers_list = Offer.query.filter_by(customer_id=cust_profile.customer_id).order_by(Offer.submitted_at.desc()).all()
    transactions_list = Transaction.query.filter_by(customer_id=cust_profile.customer_id).order_by(Transaction.created_at.desc()).all()

    # Future Home retrieval from CustomerProfile.preferences
    preferences = cust_profile.preferences or {}
    future_home_id = preferences.get('future_home_property_id')
    future_home_property = Property.query.get(future_home_id) if future_home_id else None

    # Performance Guarantee & Cycle retrieval
    perf_guarantee = PerformanceGuarantee.query.filter_by(customer_id=cust_profile.customer_id).order_by(PerformanceGuarantee.created_at.desc()).first()
    guarantee_cycle = GuaranteeCycle.query.filter_by(performance_guarantee_id=perf_guarantee.guarantee_id).order_by(GuaranteeCycle.cycle_number.desc()).first() if perf_guarantee else None

    ref_ctx = get_customer_referral_context(user_id, cust_profile)
    goal_ctx = get_customer_property_goal_context(cust_profile)
    recent_events = SecurityEvent.query.filter_by(user_id=user_id).order_by(SecurityEvent.created_at.desc()).limit(5).all()

    return render_template(
        'user/buyer_dashboard.html',
        title='Buyer Dashboard — ODACITY',
        user=user,
        profile=cust_profile,
        saved_props_count=len(saved_properties_list),
        saved_searches_count=len(saved_searches_list),
        inspections_count=len(inspections_list),
        offers_count=len(offers_list),
        transactions_count=len(transactions_list),
        saved_properties_list=saved_properties_list,
        saved_searches_list=saved_searches_list,
        inspections_list=inspections_list,
        offers_list=offers_list,
        transactions_list=transactions_list,
        future_home_property=future_home_property,
        perf_guarantee=perf_guarantee,
        guarantee_cycle=guarantee_cycle,
        recent_events=recent_events,
        **ref_ctx,
        **goal_ctx
    )


@app.route('/buyer/future-home/set/<int:property_id>', methods=['POST'])
def set_future_home(property_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to set your Future Home.', 'warning')
        return redirect(url_for('login', next=url_for('buyer_dashboard')))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)

    prop = Property.query.get_or_404(property_id)
    preferences = dict(cust_profile.preferences or {})
    preferences['future_home_property_id'] = property_id
    preferences['future_home_set_at'] = datetime.utcnow().isoformat()
    cust_profile.preferences = preferences
    db.session.commit()

    flash(f'"{prop.title or "Property #" + str(property_id)}" has been selected as your Future Home!', 'success')
    return redirect(url_for('buyer_dashboard'))


@app.route('/buyer/future-home/remove', methods=['POST'])
def remove_future_home():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login', next=url_for('buyer_dashboard')))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if cust_profile and cust_profile.preferences:
        preferences = dict(cust_profile.preferences)
        preferences.pop('future_home_property_id', None)
        preferences.pop('future_home_set_at', None)
        cust_profile.preferences = preferences
        db.session.commit()
        flash('Future Home selection removed.', 'info')

    return redirect(url_for('buyer_dashboard'))



# ==========================================
# PHASE 7 — RENTER WORKFLOW ROUTES
# ==========================================

@app.route('/properties/<int:property_id>/apply/', methods=['POST'])
def apply_property(property_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to submit a rental application.', 'warning')
        return redirect(url_for('login', next=url_for('property_detail', property_id=property_id)))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    prop = Property.query.get_or_404(property_id)

    if prop.publication_status and prop.publication_status not in ['Approved', 'Private Listing', 'Public Listing']:
        flash('This property is not currently available for application.', 'danger')
        return redirect(url_for('properties'))

    if not is_publicly_eligible(prop):
        if not is_authorized_for_private_property(prop):
            flash('This property is currently in a Private Listing period. Controlled customized-listing authorization is required for access.', 'warning')
            return redirect(url_for('properties'))

    # Duplicate active application check per customer/property
    existing_app = Application.query.filter(
        Application.customer_id == cust_profile.customer_id,
        Application.property_id == property_id,
        Application.status.notin_(['Cancelled', 'Rejected'])
    ).first()

    if existing_app:
        flash('You already have an active rental application for this property.', 'warning')
        return redirect(url_for('renter_applications'))

    form = RentalApplicationForm()
    if form.validate_on_submit():
        notes = form.notes.data.strip() if form.notes.data else None
    else:
        notes = request.form.get('notes', '').strip() or None

    new_app = Application(
        customer_id=cust_profile.customer_id,
        property_id=property_id,
        status='Submitted',
        notes=notes,
        applied_at=datetime.utcnow()
    )
    db.session.add(new_app)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='RENTAL_APPLICATION_SUBMITTED',
        description=f'Customer submitted rental application for property #{property_id}',
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(sec_event)
    db.session.commit()

    flash('Rental application submitted successfully.', 'success')
    return redirect(url_for('renter_applications'))


@app.route('/renter/applications/')
def renter_applications():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view your applications.', 'warning')
        return redirect(url_for('login', next=request.path))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    # Scoped strictly to authenticated customer ID
    applications = Application.query.filter_by(customer_id=cust_profile.customer_id).order_by(Application.applied_at.desc()).all()
    cancel_form = CancelApplicationForm()

    return render_template(
        'user/renter_applications.html',
        title='My Rental Applications',
        applications=applications,
        cancel_form=cancel_form
    )


@app.route('/applications/<int:application_id>/cancel/', methods=['POST'])
def cancel_application(application_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to cancel an application.', 'warning')
        return redirect(url_for('login', next=request.path))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        flash('Customer profile not found.', 'danger')
        return redirect(url_for('renter_applications'))

    # Strict customer isolation (IDOR protection)
    app_rec = Application.query.filter_by(application_id=application_id, customer_id=cust_profile.customer_id).first()
    if not app_rec:
        flash('Rental application record not found or access denied.', 'danger')
        return redirect(url_for('renter_applications'))

    if app_rec.status in ['Cancelled', 'Rejected']:
        flash(f'Application is already in terminal status: {app_rec.status}.', 'warning')
        return redirect(url_for('renter_applications'))

    app_rec.status = 'Cancelled'

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='RENTAL_APPLICATION_CANCELLED',
        description=f'Customer cancelled rental application #{application_id}',
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(sec_event)
    db.session.commit()

    flash('Rental application cancelled successfully.', 'info')
    return redirect(url_for('renter_applications'))


@app.route('/properties/<int:property_id>/inspection/', methods=['POST'])
def request_inspection(property_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to request an inspection.', 'warning')
        return redirect(url_for('login', next=url_for('property_detail', property_id=property_id)))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    prop = Property.query.get_or_404(property_id)

    if prop.publication_status and prop.publication_status not in ['Approved', 'Private Listing', 'Public Listing']:
        flash('This property is not currently available for inspection.', 'danger')
        return redirect(url_for('properties'))

    if not is_publicly_eligible(prop):
        if not is_authorized_for_private_property(prop):
            flash('This property is currently in a Private Listing period. Controlled customized-listing authorization is required for access.', 'warning')
            return redirect(url_for('properties'))

    # Duplicate active inspection check per customer/property
    existing_insp = Inspection.query.filter(
        Inspection.customer_id == cust_profile.customer_id,
        Inspection.property_id == property_id,
        Inspection.status.notin_(['Cancelled', 'Completed', 'Rejected'])
    ).first()

    if existing_insp:
        flash('You already have an active inspection request for this property.', 'warning')
        return redirect(url_for('renter_inspections'))

    form = ScheduleInspectionForm()
    scheduled_for = None
    if form.validate_on_submit():
        notes = form.notes.data.strip() if form.notes.data else None
        if form.scheduled_for.data:
            scheduled_for = datetime.combine(form.scheduled_for.data, datetime.min.time())
    else:
        notes = request.form.get('notes', '').strip() or None
        date_str = request.form.get('scheduled_for', '').strip()
        if date_str:
            try:
                scheduled_for = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                scheduled_for = None

    new_insp = Inspection(
        customer_id=cust_profile.customer_id,
        property_id=property_id,
        requested_at=datetime.utcnow(),
        scheduled_for=scheduled_for,
        notes=notes,
        status='Requested',
        created_at=datetime.utcnow()
    )
    db.session.add(new_insp)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='INSPECTION_REQUESTED',
        description=f'Customer requested inspection for property #{property_id}',
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(sec_event)
    db.session.commit()

    create_user_notification(
        user_id=user_id,
        notification_type='INSPECTION_REQUESTED',
        subject='Inspection Requested',
        message=f'Your inspection request for "{prop.title}" has been received.',
        url='/renter/inspections/',
        send_email=True
    )

    flash('Inspection request submitted successfully.', 'success')
    return redirect(url_for('renter_inspections'))


@app.route('/renter/inspections/')
def renter_inspections():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view your inspection requests.', 'warning')
        return redirect(url_for('login', next=request.path))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    # Scoped strictly to authenticated customer ID
    inspections = Inspection.query.filter_by(customer_id=cust_profile.customer_id).order_by(Inspection.requested_at.desc()).all()
    cancel_form = CancelInspectionForm()

    return render_template(
        'user/renter_inspections.html',
        title='My Inspection Requests',
        inspections=inspections,
        cancel_form=cancel_form
    )


@app.route('/inspections/<int:inspection_id>/cancel/', methods=['POST'])
def cancel_inspection(inspection_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to cancel an inspection.', 'warning')
        return redirect(url_for('login', next=request.path))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        flash('Customer profile not found.', 'danger')
        return redirect(url_for('renter_inspections'))

    # Strict customer isolation (IDOR protection)
    insp_rec = Inspection.query.filter_by(inspection_id=inspection_id, customer_id=cust_profile.customer_id).first()
    if not insp_rec:
        flash('Inspection record not found or access denied.', 'danger')
        return redirect(url_for('renter_inspections'))

    if insp_rec.status in ['Cancelled', 'Completed', 'Rejected']:
        flash(f'Inspection request is already in terminal status: {insp_rec.status}.', 'warning')
        return redirect(url_for('renter_inspections'))

    insp_rec.status = 'Cancelled'

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='INSPECTION_CANCELLED',
        description=f'Customer cancelled inspection request #{inspection_id}',
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(sec_event)
    db.session.commit()

    flash('Inspection request cancelled successfully.', 'info')
    return redirect(url_for('renter_inspections'))


# ==========================================
# PHASE 8 — BUYER WORKFLOW ROUTES
# ==========================================

@app.route('/properties/<int:property_id>/offer/', methods=['POST'])
def submit_offer(property_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to submit a purchase offer.', 'warning')
        return redirect(url_for('login', next=url_for('property_detail', property_id=property_id)))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    prop = Property.query.get_or_404(property_id)

    if prop.dab and prop.dab.service_type != 'sale':
        flash('Purchase offers are only permitted for Sale properties.', 'danger')
        return redirect(url_for('property_detail', property_id=property_id))

    if prop.publication_status and prop.publication_status not in ['Approved', 'Private Listing', 'Public Listing']:
        flash('This property is not currently available for purchase offers.', 'danger')
        return redirect(url_for('properties'))

    if not is_publicly_eligible(prop):
        if not is_authorized_for_private_property(prop):
            flash('This property is currently in a Private Listing period. Controlled customized-listing authorization is required for access.', 'warning')
            return redirect(url_for('properties'))

    # Active duplicate offer check per customer/property
    existing_offer = Offer.query.filter(
        Offer.customer_id == cust_profile.customer_id,
        Offer.property_id == property_id,
        Offer.status.notin_(['Cancelled', 'Rejected', 'Expired'])
    ).first()

    if existing_offer:
        flash('You already have an active purchase offer for this property.', 'warning')
        return redirect(url_for('buyer_offers'))

    form = PurchaseOfferForm()
    raw_amount = request.form.get('offer_amount', '').strip()
    try:
        amount = float(raw_amount)
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        flash('Please enter a valid positive numeric offer amount.', 'danger')
        return redirect(url_for('property_detail', property_id=property_id))

    notes = form.notes.data.strip() if form.notes and form.notes.data else request.form.get('notes', '').strip() or None

    new_offer = Offer(
        customer_id=cust_profile.customer_id,
        property_id=property_id,
        offer_amount=amount,
        status='Submitted',
        submitted_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.session.add(new_offer)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='PURCHASE_OFFER_SUBMITTED',
        description=f'Customer submitted purchase offer of ₦{amount:,.2f} for property #{property_id}',
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(sec_event)
    db.session.commit()

    owner_user_id = prop.dab.owner.user_id if (prop.dab and prop.dab.owner) else None
    if owner_user_id:
        create_user_notification(
            user_id=owner_user_id,
            notification_type='OFFER_RECEIVED',
            subject='New Purchase Offer Received',
            message=f'You received a purchase offer of ₦{amount:,.2f} for property "{prop.title}".',
            url='/seller/offers/',
            send_email=True
        )

    flash('Purchase offer submitted successfully.', 'success')
    return redirect(url_for('buyer_offers'))


@app.route('/buyer/offers/')
def buyer_offers():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view your purchase offers.', 'warning')
        return redirect(url_for('login', next=request.path))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        cust_profile = CustomerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(cust_profile)
        db.session.commit()

    # Scoped strictly to authenticated customer ID
    offers = Offer.query.filter_by(customer_id=cust_profile.customer_id).order_by(Offer.submitted_at.desc()).all()
    cancel_form = CancelOfferForm()
    respond_form = BuyerRespondOfferForm()

    return render_template(
        'user/buyer_offers.html',
        title='My Purchase Offers',
        offers=offers,
        cancel_form=cancel_form,
        respond_form=respond_form
    )


@app.route('/offers/<int:offer_id>/cancel/', methods=['POST'])
def cancel_offer(offer_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to cancel an offer.', 'warning')
        return redirect(url_for('login', next=request.path))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        flash('Customer profile not found.', 'danger')
        return redirect(url_for('buyer_offers'))

    # Strict customer isolation (IDOR protection)
    offer_rec = Offer.query.filter_by(offer_id=offer_id, customer_id=cust_profile.customer_id).first()
    if not offer_rec:
        flash('Purchase offer record not found or access denied.', 'danger')
        return redirect(url_for('buyer_offers'))

    if offer_rec.status in ['Cancelled', 'Rejected', 'Expired']:
        flash(f'Offer is already in terminal status: {offer_rec.status}.', 'warning')
        return redirect(url_for('buyer_offers'))

    offer_rec.status = 'Cancelled'

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='PURCHASE_OFFER_CANCELLED',
        description=f'Customer cancelled purchase offer #{offer_id}',
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(sec_event)
    db.session.commit()

    flash('Purchase offer cancelled successfully.', 'info')
    return redirect(url_for('buyer_offers'))


# ==========================================
# PHASE 9 — INDIVIDUAL PROPERTY OWNER DASHBOARD & SELLER WORKFLOW ROUTES
# ==========================================

@app.route('/owner/dashboard/')
def owner_dashboard():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to access your Owner Dashboard.', 'warning')
        return redirect(url_for('login', next=request.path))

    user = User.query.get_or_404(user_id)
    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()

    if not owner_prof:
        owner_prof = PropertyOwnerProfile(user_id=user_id, owner_type='individual', created_at=datetime.utcnow())
        db.session.add(owner_prof)
        db.session.commit()

    session['active_role'] = 'owner'

    if owner_prof.owner_type and owner_prof.owner_type != 'individual':
        flash('This dashboard is designed for Individual Property Owners.', 'info')

    # Owner-scoped queries (User -> PropertyOwnerProfile -> DirectAssetBrief -> Property)
    dabs = DirectAssetBrief.query.filter_by(owner_profile_id=owner_prof.owner_profile_id).order_by(DirectAssetBrief.created_at.desc()).all()
    dab_ids = [d.dab_id for d in dabs]

    properties = Property.query.filter(Property.dab_id.in_(dab_ids)).all() if dab_ids else []
    prop_ids = [p.property_id for p in properties]

    offers = Offer.query.filter(Offer.property_id.in_(prop_ids)).order_by(Offer.submitted_at.desc()).all() if prop_ids else []
    applications = Application.query.filter(Application.property_id.in_(prop_ids)).order_by(Application.applied_at.desc()).all() if prop_ids else []
    inspections = Inspection.query.filter(Inspection.property_id.in_(prop_ids)).order_by(Inspection.requested_at.desc()).all() if prop_ids else []
    transactions = Transaction.query.filter(Transaction.property_id.in_(prop_ids)).order_by(Transaction.created_at.desc()).all() if prop_ids else []
    documents = PropertyDocument.query.filter(PropertyDocument.property_id.in_(prop_ids)).order_by(PropertyDocument.created_at.desc()).all() if prop_ids else []
    perf_guarantees = PerformanceGuarantee.query.filter_by(owner_profile_id=owner_prof.owner_profile_id).order_by(PerformanceGuarantee.created_at.desc()).all()

    now_dt = datetime.utcnow()
    for g in perf_guarantees:
        if g.start_at:
            elapsed = (now_dt - g.start_at).days
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
        g.has_redemption_initiated = 'Redemption_Initiated' in event_types
        g.has_settlement_completed = 'Settlement_Completed' in event_types


    # Portfolio Metrics
    total_properties_count = len(dabs)
    available_properties = [p for p in properties if p.publication_status in ['Available', 'Public Listing', 'Private Listing', 'Approved']]
    unavailable_properties = [p for p in properties if p.publication_status == 'Unavailable']
    pending_dabs = [d for d in dabs if d.status in ['Submitted', 'Under Verification', 'Draft']]
    approved_dabs = [d for d in dabs if d.status == 'Approved']
    sold_properties = [p for p in properties if p.publication_status == 'Sold']
    rented_properties = [p for p in properties if p.publication_status == 'Rented']

    available_count = len(available_properties)
    unavailable_count = len(unavailable_properties)
    pending_approval_count = len(pending_dabs)
    approved_count = len(approved_dabs)
    sold_count = len(sold_properties)
    rented_count = len(rented_properties)

    inspections_count = len(inspections)
    offers_count = len(offers)
    applications_count = len(applications)
    documents_count = len(documents)

    documents_pending = len([d for d in documents if d.review_status == 'Pending'])
    documents_verified = len([d for d in documents if d.review_status == 'Verified'])
    documents_rejected = len([d for d in documents if d.review_status == 'Rejected'])

    recent_events = SecurityEvent.query.filter_by(user_id=user_id).order_by(SecurityEvent.created_at.desc()).limit(5).all()

    return render_template(
        'user/owner_dashboard.html',
        title='Owner Dashboard — ODACITY',
        user=user,
        owner_profile=owner_prof,
        dabs=dabs,
        properties=properties,
        offers=offers,
        applications=applications,
        inspections=inspections,
        transactions=transactions,
        documents=documents,
        perf_guarantees=perf_guarantees,
        available_properties=available_properties,
        unavailable_properties=unavailable_properties,
        pending_dabs=pending_dabs,
        sold_properties=sold_properties,
        rented_properties=rented_properties,
        total_properties_count=total_properties_count,
        available_count=available_count,
        unavailable_count=unavailable_count,
        pending_approval_count=pending_approval_count,
        approved_count=approved_count,
        sold_count=sold_count,
        rented_count=rented_count,
        inspections_count=inspections_count,
        offers_count=offers_count,
        applications_count=applications_count,
        documents_count=documents_count,
        documents_pending=documents_pending,
        documents_verified=documents_verified,
        documents_rejected=documents_rejected,
        recent_events=recent_events
    )


@app.route('/owner/properties/<int:property_id>/toggle-availability/', methods=['POST'])
def owner_toggle_property_availability(property_id):
    """
    Phase 10 Owner Property Availability Control.
    Allows authenticated property owners to mark their own eligible property as:
    - 'make_unavailable': Transition publication_status to 'Unavailable'.
    - 'reactivate': Restore publication_status to 'Public Listing' or 'Private Listing' (based on 72h window).

    Security & Ownership Enforcement:
    - Requires authenticated user session.
    - Strictly verifies property ownership via PropertyOwnerProfile -> DirectAssetBrief -> Property.
    - Rejects attempts to modify properties owned by other users.
    - Rejects Sold properties (terminal state).
    - Rejects unapproved properties (Draft, Submitted, Under Verification, Verified).
    - Owners CANNOT mark properties as Sold.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to manage property availability.', 'warning')
        return redirect(url_for('login', next=request.path))

    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    if not owner_prof:
        flash('Unauthorized access: Property Owner profile required.', 'danger')
        return redirect(url_for('owner_dashboard'))

    prop = Property.query.get_or_404(property_id)
    dab = prop.dab

    # 1. Ownership Verification: Property MUST belong to authenticated owner
    if not dab or dab.owner_profile_id != owner_prof.owner_profile_id:
        flash('Unauthorized access: You do not own this property brief.', 'danger')
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='UNAUTHORIZED_PROPERTY_ACCESS_ATTEMPT',
            description=f"User #{user_id} attempted unauthorized availability modification on Property #{property_id}.",
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()
        return redirect(url_for('owner_dashboard'))

    action = request.form.get('action', '').lower().strip()
    now = datetime.utcnow()

    # 2. Terminal State Protection: Property is Sold
    if prop.publication_status == 'Sold' or prop.status == 'Sold':
        flash(f"Cannot modify availability for Property #{property_id}: Property is marked as SOLD (Terminal State).", 'danger')
        return redirect(url_for('owner_dashboard'))

    # 3. Prerequisite Gate: Property must be Approved / Listed stage
    if prop.status != 'Approved' and prop.publication_status not in ['Approved', 'Private Listing', 'Public Listing', 'Unavailable']:
        flash(f"Cannot update availability for Property #{property_id}: Property must be APPROVED before changing availability.", 'danger')
        return redirect(url_for('owner_dashboard'))

    # 4. Action: 'make_unavailable'
    if action == 'make_unavailable':
        if prop.publication_status == 'Unavailable':
            flash(f"Property '{prop.title}' is already marked as Unavailable.", 'info')
            return redirect(url_for('owner_dashboard'))

        previous_pub_status = prop.publication_status
        prop.publication_status = 'Unavailable'
        prop.availability_status = 'Unavailable'
        prop.updated_at = now

        db.session.flush()

        audit_entry = AuditLog(
            user_id=user_id,
            action='OWNER_PROPERTY_UNAVAILABLE',
            entity_type='Property',
            entity_id=prop.property_id,
            resource_type='Property',
            resource_id=prop.property_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            previous_values={"publication_status": previous_pub_status},
            new_values={"publication_status": "Unavailable", "availability_status": "Unavailable"},
            created_at=now
        )
        db.session.add(audit_entry)

        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='OWNER_PROPERTY_UNAVAILABLE',
            description=f"Property #{prop.property_id} ('{prop.title}') marked as UNAVAILABLE by owner user #{user_id}.",
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)

        db.session.commit()
        flash(f"Property '{prop.title}' has been marked as UNAVAILABLE.", 'warning')

    # 5. Action: 'reactivate'
    elif action == 'reactivate':
        if prop.publication_status != 'Unavailable':
            flash(f"Property '{prop.title}' is not currently marked as Unavailable.", 'info')
            return redirect(url_for('owner_dashboard'))

        # Determine prior legitimate listing state based on 72h window
        new_pub_status = 'Public Listing'
        if dab and dab.approved_at:
            cutoff_time = now - timedelta(hours=72)
            if dab.approved_at > cutoff_time:
                new_pub_status = 'Private Listing'

        previous_pub_status = prop.publication_status
        prop.publication_status = new_pub_status
        prop.availability_status = 'Available'
        prop.updated_at = now

        db.session.flush()

        audit_entry = AuditLog(
            user_id=user_id,
            action='OWNER_PROPERTY_REACTIVATED',
            entity_type='Property',
            entity_id=prop.property_id,
            resource_type='Property',
            resource_id=prop.property_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            previous_values={"publication_status": previous_pub_status},
            new_values={"publication_status": new_pub_status, "availability_status": "Available"},
            created_at=now
        )
        db.session.add(audit_entry)

        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='OWNER_PROPERTY_REACTIVATED',
            description=f"Property #{prop.property_id} ('{prop.title}') reactivated to {new_pub_status} by owner user #{user_id}.",
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)

        db.session.commit()
        flash(f"Property '{prop.title}' has been REACTIVATED as {new_pub_status}.", 'success')

    else:
        flash('Invalid action requested.', 'danger')

    return redirect(url_for('owner_dashboard'))



@app.route('/owner/profile/', methods=['GET', 'POST'])
def owner_profile():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to manage your property owner profile.', 'warning')
        return redirect(url_for('login', next=request.path))

    user = User.query.get_or_404(user_id)
    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()

    if not owner_prof:
        owner_prof = PropertyOwnerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(owner_prof)
        db.session.commit()

    form = PropertyOwnerProfileForm()

    if form.validate_on_submit():
        owner_prof.owner_type = form.owner_type.data
        owner_prof.company_name = form.company_name.data.strip() if form.company_name.data else None
        owner_prof.business_name = form.business_name.data.strip() if form.business_name.data else None
        owner_prof.tax_id = form.tax_id.data.strip() if form.tax_id.data else None
        owner_prof.tin_number = form.tin_number.data.strip() if form.tin_number.data else None
        owner_prof.address = form.address.data.strip() if form.address.data else None

        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='PROPERTY_OWNER_PROFILE_UPDATED',
            description='Property owner profile updated successfully',
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()

        flash('Property Owner Profile updated successfully!', 'success')
        return redirect(url_for('owner_profile'))

    elif request.method == 'GET':
        form.owner_type.data = owner_prof.owner_type or 'individual'
        form.company_name.data = owner_prof.company_name or ''
        form.business_name.data = owner_prof.business_name or ''
        form.tax_id.data = owner_prof.tax_id or ''
        form.tin_number.data = owner_prof.tin_number or ''
        form.address.data = owner_prof.address or ''

    return render_template('user/owner_profile.html', title='Property Owner Profile', form=form, user=user, owner_profile=owner_prof)


@app.route('/owner/dab/new/', methods=['GET', 'POST'])
def submit_dab():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to submit a property asset brief.', 'warning')
        return redirect(url_for('login', next=request.path))

    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    if not owner_prof:
        owner_prof = PropertyOwnerProfile(user_id=user_id, created_at=datetime.utcnow())
        db.session.add(owner_prof)
        db.session.commit()

    form = DirectAssetBriefForm()

    if form.validate_on_submit():
        title = form.title.data.strip()
        service_type = form.service_type.data
        property_type = form.property_type.data
        location = form.location.data.strip() if form.location.data else None
        budget_range = form.budget_range.data.strip() if form.budget_range.data else None
        brief_details = form.brief_details.data.strip() if form.brief_details.data else None

        now = datetime.utcnow()
        dab = DirectAssetBrief(
            owner_profile_id=owner_prof.owner_profile_id,
            title=title,
            service_type=service_type,
            property_type=property_type,
            location=location,
            budget_range=budget_range,
            brief_details=brief_details,
            status='Submitted',
            submitted_at=now,
            created_at=now
        )
        db.session.add(dab)

        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='SELLER_DAB_SUBMITTED',
            description=f'Seller submitted Direct Asset Brief: "{title}"',
            ip_address=request.remote_addr,
            created_at=now
        )
        db.session.add(sec_event)
        db.session.commit()

        flash('Direct Asset Brief submitted successfully! Platform admins will review and publish your property.', 'success')
        return redirect(url_for('seller_properties'))

    return render_template('user/dab_form.html', title='Submit Direct Asset Brief', form=form)


@app.route('/seller/properties/')
def seller_properties():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view your seller properties.', 'warning')
        return redirect(url_for('login', next=request.path))

    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    if not owner_prof:
        dabs = []
    else:
        dabs = DirectAssetBrief.query.filter_by(owner_profile_id=owner_prof.owner_profile_id).order_by(DirectAssetBrief.created_at.desc()).all()

    return render_template('user/seller_properties.html', title='My Listed Properties', dabs=dabs, owner_profile=owner_prof)


@app.route('/seller/offers/')
def seller_offers():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view received purchase offers.', 'warning')
        return redirect(url_for('login', next=request.path))

    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    offers = []
    if owner_prof:
        dabs = DirectAssetBrief.query.filter_by(owner_profile_id=owner_prof.owner_profile_id).all()
        dab_ids = [d.dab_id for d in dabs]
        if dab_ids:
            props = Property.query.filter(Property.dab_id.in_(dab_ids)).all()
            prop_ids = [p.property_id for p in props]
            if prop_ids:
                offers = Offer.query.filter(Offer.property_id.in_(prop_ids)).order_by(Offer.submitted_at.desc()).all()

    respond_form = RespondOfferForm()
    return render_template('user/seller_offers.html', title='Offers Received', offers=offers, respond_form=respond_form)


@app.route('/seller/offers/<int:offer_id>/respond/', methods=['POST'])
def respond_offer(offer_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to respond to purchase offers.', 'warning')
        return redirect(url_for('login', next=request.path))

    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    if not owner_prof:
        flash('Property owner profile not found or access denied.', 'danger')
        return redirect(url_for('seller_offers'))

    offer_rec = Offer.query.get_or_404(offer_id)

    # Mandatory IDOR Ownership Verification:
    # Offer -> Property -> DirectAssetBrief -> PropertyOwnerProfile -> User
    if not offer_rec.property or not offer_rec.property.dab or offer_rec.property.dab.owner_profile_id != owner_prof.owner_profile_id:
        flash('Offer record not found or access denied.', 'danger')
        return redirect(url_for('seller_offers'))

    if offer_rec.status in ['Cancelled', 'Rejected', 'Expired', 'Accepted']:
        flash(f'Offer is already in terminal/processed status: {offer_rec.status}.', 'warning')
        return redirect(url_for('seller_offers'))

    if offer_rec.valid_until and offer_rec.valid_until < datetime.utcnow():
        flash('Offer has expired and cannot be negotiated.', 'danger')
        return redirect(url_for('seller_offers'))

    action = request.form.get('action', '').strip()
    if action not in ['Accepted', 'Rejected', 'Counter_Offer']:
        flash('Invalid offer response action.', 'danger')
        return redirect(url_for('seller_offers'))

    old_status = offer_rec.status
    old_amount = float(offer_rec.offer_amount) if offer_rec.offer_amount else 0.0

    if action == 'Counter_Offer':
        counter_amount_raw = request.form.get('counter_amount', '').strip()
        message = request.form.get('notes', '').strip() or request.form.get('message', '').strip()

        try:
            counter_val = float(counter_amount_raw)
            if counter_val <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            flash('Please provide a valid counter-offer amount greater than 0.', 'danger')
            return redirect(url_for('seller_offers'))

        neg = Negotiation(
            offer_id=offer_rec.offer_id,
            counter_offer_amount=counter_val,
            proposed_amount=counter_val,
            message=message,
            direction='owner_to_buyer',
            created_by_user_id=user_id,
            created_at=datetime.utcnow()
        )
        db.session.add(neg)

        offer_rec.status = 'Counter_Offer'
        offer_rec.responded_at = datetime.utcnow()

        audit = AuditLog(
            user_id=user_id,
            action='OWNER_COUNTER_OFFER_SUBMITTED',
            entity_type='Offer',
            entity_id=offer_rec.offer_id,
            previous_values={'status': old_status},
            new_values={'status': 'Counter_Offer', 'counter_amount': counter_val},
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(audit)

        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='COUNTER_OFFER_SUBMITTED',
            description=f'Owner submitted counter-offer of ₦{counter_val:,.2f} for offer #{offer_id}',
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()

        flash(f'Counter-offer of ₦{counter_val:,.2f} submitted to buyer.', 'success')
        return redirect(url_for('seller_offers'))

    else:
        offer_rec.status = action
        offer_rec.responded_at = datetime.utcnow()

        audit = AuditLog(
            user_id=user_id,
            action=f'OWNER_OFFER_{action.upper()}',
            entity_type='Offer',
            entity_id=offer_rec.offer_id,
            previous_values={'status': old_status},
            new_values={'status': action},
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(audit)

        event_type = 'PURCHASE_OFFER_ACCEPTED' if action == 'Accepted' else 'PURCHASE_OFFER_REJECTED'
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type=event_type,
            description=f'Property owner {action.lower()} purchase offer #{offer_id} for property #{offer_rec.property_id}',
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()

        buyer_user_id = offer_rec.customer.user_id if offer_rec.customer else None
        if buyer_user_id:
            create_user_notification(
                user_id=buyer_user_id,
                notification_type='OFFER_RESPONSE',
                subject=f'Offer Status Update: {action}',
                message=f'The seller has responded to your offer for "{offer_rec.property.title if offer_rec.property else "property"}": {action}.',
                url='/buyer/offers/',
                send_email=True
            )

        flash(f'Purchase offer #{offer_id} marked as {action}.', 'success' if action == 'Accepted' else 'info')
        return redirect(url_for('seller_offers'))


@app.route('/offers/<int:offer_id>/respond/', methods=['POST'])
def buyer_respond_offer(offer_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to respond to a counter offer.', 'warning')
        return redirect(url_for('login', next=request.path))

    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile:
        flash('Customer profile not found.', 'danger')
        return redirect(url_for('buyer_offers'))

    # Strict customer isolation (IDOR protection)
    offer_rec = Offer.query.filter_by(offer_id=offer_id, customer_id=cust_profile.customer_id).first()
    if not offer_rec:
        flash('Purchase offer record not found or access denied.', 'danger')
        return redirect(url_for('buyer_offers'))

    if offer_rec.status in ['Accepted', 'Rejected', 'Cancelled', 'Expired']:
        flash(f'Offer is already in terminal status: {offer_rec.status}.', 'warning')
        return redirect(url_for('buyer_offers'))

    if offer_rec.valid_until and offer_rec.valid_until < datetime.utcnow():
        flash('Offer has expired and cannot be negotiated.', 'danger')
        return redirect(url_for('buyer_offers'))

    action = request.form.get('action', '').strip()
    if action not in ['Accepted', 'Rejected', 'Counter_Offer']:
        flash('Invalid counter offer response action.', 'danger')
        return redirect(url_for('buyer_offers'))

    old_status = offer_rec.status
    old_amount = float(offer_rec.offer_amount) if offer_rec.offer_amount else 0.0

    if action == 'Accepted':
        latest_neg = Negotiation.query.filter_by(offer_id=offer_rec.offer_id).order_by(Negotiation.created_at.desc(), Negotiation.negotiation_id.desc()).first()
        if latest_neg and (latest_neg.counter_offer_amount or latest_neg.proposed_amount):
            final_amount = float(latest_neg.counter_offer_amount or latest_neg.proposed_amount)
        else:
            final_amount = old_amount

        offer_rec.offer_amount = final_amount
        offer_rec.status = 'Accepted'
        offer_rec.responded_at = datetime.utcnow()

        audit = AuditLog(
            user_id=user_id,
            action='COUNTER_OFFER_ACCEPTED',
            entity_type='Offer',
            entity_id=offer_rec.offer_id,
            previous_values={'status': old_status, 'offer_amount': old_amount},
            new_values={'status': 'Accepted', 'offer_amount': final_amount},
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(audit)

        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='COUNTER_OFFER_ACCEPTED',
            description=f'Buyer accepted counter-offer of ₦{final_amount:,.2f} for offer #{offer_id}',
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()

        # CRITICAL: STOP HERE. DO NOT CREATE Transaction, Invoice, Payment, or TransactionDocument.
        flash(f'Counter-offer accepted! Purchase offer #{offer_id} is now Accepted at ₦{final_amount:,.2f}.', 'success')
        return redirect(url_for('buyer_offers'))

    elif action == 'Rejected':
        offer_rec.status = 'Rejected'
        offer_rec.responded_at = datetime.utcnow()

        audit = AuditLog(
            user_id=user_id,
            action='COUNTER_OFFER_REJECTED',
            entity_type='Offer',
            entity_id=offer_rec.offer_id,
            previous_values={'status': old_status},
            new_values={'status': 'Rejected'},
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(audit)

        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='COUNTER_OFFER_REJECTED',
            description=f'Buyer rejected counter-offer for offer #{offer_id}',
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()

        flash(f'Counter-offer rejected. Purchase offer #{offer_id} is marked as Rejected.', 'info')
        return redirect(url_for('buyer_offers'))

    elif action == 'Counter_Offer':
        counter_amount_raw = request.form.get('counter_amount', '').strip()
        message = request.form.get('notes', '').strip() or request.form.get('message', '').strip()

        try:
            counter_val = float(counter_amount_raw)
            if counter_val <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            flash('Please enter a valid numeric counter-offer amount greater than 0.', 'danger')
            return redirect(url_for('buyer_offers'))

        neg = Negotiation(
            offer_id=offer_rec.offer_id,
            proposed_amount=counter_val,
            counter_offer_amount=counter_val,
            message=message,
            direction='buyer_to_owner',
            created_by_user_id=user_id,
            created_at=datetime.utcnow()
        )
        db.session.add(neg)

        offer_rec.status = 'Counter_Offer'
        offer_rec.responded_at = datetime.utcnow()

        audit = AuditLog(
            user_id=user_id,
            action='BUYER_COUNTER_OFFER_SUBMITTED',
            entity_type='Offer',
            entity_id=offer_rec.offer_id,
            previous_values={'status': old_status},
            new_values={'status': 'Counter_Offer', 'counter_amount': counter_val},
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(audit)

        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='COUNTER_OFFER_SUBMITTED',
            description=f'Buyer submitted counter-offer of ₦{counter_val:,.2f} for offer #{offer_id}',
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()

        owner_user_id = offer_rec.property.dab.owner.user_id if (offer_rec.property and offer_rec.property.dab and offer_rec.property.dab.owner) else None
        if owner_user_id:
            create_user_notification(
                user_id=owner_user_id,
                notification_type='OFFER_RESPONSE',
                subject=f'Buyer Offer Response: {action}',
                message=f'The buyer has responded to your offer for "{offer_rec.property.title if offer_rec.property else "property"}": {action}.',
                url='/seller/offers/',
                send_email=True
            )

        flash(f'Counter-offer of ₦{counter_val:,.2f} submitted to property owner.', 'success')
        return redirect(url_for('buyer_offers'))


# ==========================================
# PHASE 15 — TRANSACTION LIFECYCLE ROUTES
# ==========================================

@app.route('/offers/<int:offer_id>/initiate-transaction/', methods=['POST'])
def initiate_transaction(offer_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to initiate a transaction.', 'warning')
        return redirect(url_for('login', next=request.path))

    offer_rec = Offer.query.get_or_404(offer_id)

    # Offer status MUST be exactly Accepted
    if offer_rec.status != 'Accepted':
        flash('Transactions can only be initiated from Accepted purchase offers.', 'danger')
        return redirect(url_for('buyer_offers'))

    # Authorization Check: User must be either the Buyer, Property Owner, or Admin
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    owner_profile = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()

    is_buyer = cust_profile and offer_rec.customer_id == cust_profile.customer_id
    is_owner = (
        owner_profile and
        offer_rec.property and
        offer_rec.property.dab and
        offer_rec.property.dab.owner_profile_id == owner_profile.owner_profile_id
    )
    user_rec = User.query.get(user_id)
    is_admin = user_rec and has_transaction_initiation_permission(user_rec)

    if not (is_buyer or is_owner or is_admin):
        flash('Purchase offer record not found or access denied.', 'danger')
        return redirect(url_for('buyer_offers'))

    # Duplicate Protection Check: Do not create duplicate Transaction
    existing_tx = Transaction.query.filter_by(offer_id=offer_rec.offer_id).first()
    if existing_tx:
        flash(f'Transaction #{existing_tx.transaction_id} is already initiated for this offer.', 'info')
        return redirect(url_for('transaction_detail', transaction_id=existing_tx.transaction_id))

    # Generate Unique Transaction Reference
    while True:
        ref_candidate = f"TX-{uuid.uuid4().hex[:8].upper()}"
        if not Transaction.query.filter_by(transaction_reference=ref_candidate).first():
            tx_ref = ref_candidate
            break

    # Monetary calculation using Decimal-safe arithmetic
    offer_amt_dec = Decimal(str(offer_rec.offer_amount or 0))
    comm_pct = Decimal('10.00')
    comm_amt = (offer_amt_dec * comm_pct / Decimal('100.00')).quantize(Decimal('0.01'))

    new_tx = Transaction(
        customer_id=offer_rec.customer_id,
        property_id=offer_rec.property_id,
        offer_id=offer_rec.offer_id,
        transaction_reference=tx_ref,
        transaction_type='sale',
        type='sale',
        status='Initiated',
        transaction_value=offer_amt_dec,
        total_amount=offer_amt_dec,
        odacity_commission_percentage=comm_pct,
        odacity_commission_amount=comm_amt,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.session.add(new_tx)
    db.session.flush()

    audit = AuditLog(
        user_id=user_id,
        action='TRANSACTION_INITIATED',
        entity_type='Transaction',
        entity_id=new_tx.transaction_id,
        previous_values=None,
        new_values={
            'transaction_reference': tx_ref,
            'status': 'Initiated',
            'transaction_value': float(offer_amt_dec),
            'commission_amount': float(comm_amt)
        },
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(audit)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='TRANSACTION_INITIATED',
        description=f'Transaction {tx_ref} initiated for Accepted Offer #{offer_rec.offer_id}',
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(sec_event)
    db.session.commit()

    flash(f'Transaction {tx_ref} successfully initiated!', 'success')
    return redirect(url_for('transaction_detail', transaction_id=new_tx.transaction_id))


@app.route('/transactions/<int:transaction_id>/')
def transaction_detail(transaction_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view transaction details.', 'warning')
        return redirect(url_for('login', next=request.path))

    tx = Transaction.query.get_or_404(transaction_id)

    # Object-level Authorization Check:
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    owner_profile = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    user_rec = User.query.get(user_id)

    is_buyer = cust_profile and tx.customer_id == cust_profile.customer_id
    is_owner = (
        owner_profile and
        tx.property and
        tx.property.dab and
        tx.property.dab.owner_profile_id == owner_profile.owner_profile_id
    )
    is_admin = user_rec and has_admin_permission(user_rec)
    is_operational_admin = user_rec and has_phase16_operational_permission(user_rec)

    if not (is_buyer or is_owner or is_admin):
        flash('Transaction record not found or access denied.', 'danger')
        return redirect(url_for('dashboard'))

    return render_template(
        'user/transactions.html',
        title=f'Transaction Detail — {tx.transaction_reference or tx.transaction_id}',
        tx=tx,
        is_buyer=is_buyer,
        is_owner=is_owner,
        is_admin=is_admin,
        is_operational_admin=is_operational_admin
    )


@app.route('/transactions/<int:transaction_id>/invoices/<int:invoice_id>/pay/', methods=['POST'])
def pay_invoice(transaction_id, invoice_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to make a payment.', 'warning')
        return redirect(url_for('login', next=request.path))

    tx = Transaction.query.get_or_404(transaction_id)
    inv = Invoice.query.get_or_404(invoice_id)

    # Object-level Authorization Check: Only Buyer can pay their invoice
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    if not cust_profile or tx.customer_id != cust_profile.customer_id:
        flash('Payment authorized only for the transaction buyer.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    if inv.transaction_id != tx.transaction_id:
        flash('Invoice does not belong to the specified transaction.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    raw_amount = request.form.get('amount', '').strip()
    raw_ref = request.form.get('payment_reference', '').strip()
    payment_method = request.form.get('payment_method', 'card').strip()

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
        flash(f'Payment amount (₦{pay_amt:,.2f}) exceeds outstanding invoice balance (₦{outstanding:,.2f}).', 'danger')
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
        reconciliation_note='Buyer online payment (Controlled MVP)',
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
        description=f"Payment {pay_ref} of ₦{pay_amt:,.2f} completed for Invoice {inv.invoice_number} by buyer #{user_id}",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)
    db.session.commit()

    flash(f'Payment {pay_ref} of ₦{pay_amt:,.2f} successfully processed.', 'success')
    return redirect(url_for('transaction_detail', transaction_id=transaction_id))


@app.route('/transactions/<int:transaction_id>/documents/upload/', methods=['POST'])
def upload_transaction_document(transaction_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to upload transaction documents.', 'warning')
        return redirect(url_for('login', next=url_for('transaction_detail', transaction_id=transaction_id)))

    tx = Transaction.query.get_or_404(transaction_id)
    user_rec = User.query.get(user_id)

    # Object-level Authorization Check: Buyer, Owner, or Admin
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    owner_profile = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()

    is_buyer = cust_profile and tx.customer_id == cust_profile.customer_id
    is_owner = (
        owner_profile and
        tx.property and
        tx.property.dab and
        tx.property.dab.owner_profile_id == owner_profile.owner_profile_id
    )
    is_admin = user_rec and has_admin_permission(user_rec)

    if not (is_buyer or is_owner or is_admin):
        flash('Access denied or transaction record not found.', 'danger')
        return redirect(url_for('dashboard'))

    if tx.status == 'Completion':
        flash('Cannot upload documents for a completed transaction.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    file = request.files.get('document_file')
    document_type = request.form.get('document_type', '').strip() or 'General Transaction Document'

    if not file or not file.filename:
        flash('Please select a valid document file to upload.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    filename = file.filename
    allowed_exts = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if ext not in allowed_exts:
        flash('Validation error: Uploaded document must be in PDF, PNG, JPG, JPEG, DOC, or DOCX format.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    safe_name = secure_filename(filename) or f'tx_doc.{ext}'
    unique_name = f"tx_doc_{transaction_id}_{uuid.uuid4().hex[:8]}_{safe_name}"

    upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'transaction_documents')
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, unique_name)
    file.save(save_path)

    rel_path = f"uploads/transaction_documents/{unique_name}"
    now = datetime.utcnow()

    new_doc = TransactionDocument(
        transaction_id=tx.transaction_id,
        document_type=document_type,
        file_path=rel_path,
        status='Submitted',
        uploaded_by_user_id=user_id,
        uploaded_at=now,
        created_at=now
    )
    db.session.add(new_doc)
    db.session.flush()

    audit = AuditLog(
        user_id=user_id,
        action='TRANSACTION_DOCUMENT_SUBMITTED',
        entity_type='TransactionDocument',
        entity_id=new_doc.transaction_document_id,
        previous_values=None,
        new_values={
            'transaction_id': tx.transaction_id,
            'document_type': document_type,
            'file_path': rel_path,
            'status': 'Submitted'
        },
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(audit)

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='TRANSACTION_DOCUMENT_SUBMITTED',
        description=f"Transaction document ({document_type}) uploaded for Transaction #{tx.transaction_id} by user #{user_id}",
        ip_address=request.remote_addr,
        created_at=now
    )
    db.session.add(sec_event)
    db.session.commit()

    flash(f'Transaction document "{document_type}" submitted successfully.', 'success')
    return redirect(url_for('transaction_detail', transaction_id=transaction_id))


@app.route('/transactions/<int:transaction_id>/documents/<int:document_id>/serve/')
def serve_transaction_document(transaction_id, document_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view transaction documents.', 'warning')
        return redirect(url_for('login', next=request.path))

    tx = Transaction.query.get_or_404(transaction_id)
    doc = TransactionDocument.query.get_or_404(document_id)

    # Document IDOR check: document MUST belong to the specified transaction
    if doc.transaction_id != tx.transaction_id:
        flash('Document record does not match the specified transaction.', 'danger')
        return redirect(url_for('transaction_detail', transaction_id=transaction_id))

    # Object-level Authorization Check: Buyer, Owner, or Admin
    cust_profile = CustomerProfile.query.filter_by(user_id=user_id).first()
    owner_profile = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    user_rec = User.query.get(user_id)

    is_buyer = cust_profile and tx.customer_id == cust_profile.customer_id
    is_owner = (
        owner_profile and
        tx.property and
        tx.property.dab and
        tx.property.dab.owner_profile_id == owner_profile.owner_profile_id
    )
    is_admin = user_rec and has_admin_permission(user_rec)

    if not (is_buyer or is_owner or is_admin):
        flash('Access denied to transaction document.', 'danger')
        return redirect(url_for('dashboard'))

    from flask import send_from_directory
    upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'transaction_documents')
    filename = os.path.basename(doc.file_path)
    return send_from_directory(upload_dir, filename)



@app.route('/seller/applications/')
def seller_applications():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view received rental applications.', 'warning')
        return redirect(url_for('login', next=request.path))

    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    applications = []
    if owner_prof:
        dabs = DirectAssetBrief.query.filter_by(owner_profile_id=owner_prof.owner_profile_id).all()
        dab_ids = [d.dab_id for d in dabs]
        if dab_ids:
            props = Property.query.filter(Property.dab_id.in_(dab_ids)).all()
            prop_ids = [p.property_id for p in props]
            if prop_ids:
                applications = Application.query.filter(Application.property_id.in_(prop_ids)).order_by(Application.applied_at.desc()).all()

    return render_template('user/seller_applications.html', title='Applications Received', applications=applications)


# ==========================================
# ACTIVE ROLE CONTEXT PROCESSOR & SWITCHER
# ==========================================

@app.context_processor
def inject_active_role():
    user_id = session.get('user_id')
    if not user_id:
        return {'active_role': None, 'qualified_roles': [], 'unread_notif_count': 0}

    user = User.query.get(user_id)
    if not user:
        return {'active_role': None, 'qualified_roles': [], 'unread_notif_count': 0}

    qualified_roles = []
    if user.customer_profile:
        qualified_roles.extend(['renter', 'buyer'])
    if user.property_owner_profile:
        qualified_roles.append('owner')

    active_role = session.get('active_role')
    if active_role not in qualified_roles:
        active_role = qualified_roles[0] if qualified_roles else 'renter'
        session['active_role'] = active_role

    unread_notif_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()

    return {
        'active_role': active_role,
        'qualified_roles': qualified_roles,
        'unread_notif_count': unread_notif_count
    }


@app.route('/switch-role/<role_name>')
def switch_role(role_name):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to switch roles.', 'warning')
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)
    target_role = role_name.lower().strip()

    # Verify existing backend qualification
    is_qualified = False
    if target_role in ['renter', 'buyer'] and user.customer_profile:
        is_qualified = True
    elif target_role == 'owner' and user.property_owner_profile:
        is_qualified = True

    if not is_qualified:
        flash(f'Access denied. You are not qualified for the {target_role.capitalize()} role.', 'danger')
        return redirect(request.referrer or url_for('homepage'))

    session['active_role'] = target_role
    flash(f'Switched to {target_role.capitalize()} View.', 'success')

    if target_role == 'buyer':
        return redirect(url_for('buyer_dashboard'))
    elif target_role == 'owner':
        return redirect(url_for('owner_dashboard'))
    else:
        return redirect(url_for('dashboard'))


@app.route('/notifications/')
def notifications():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view your notifications.', 'warning')
        return redirect(url_for('login', next=request.path))

    user = User.query.get_or_404(user_id)
    notifs = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()

    # Mark unread notifications as read
    unread_notifs = [n for n in notifs if not n.is_read]
    if unread_notifs:
        for n in unread_notifs:
            n.is_read = True
            n.read_at = datetime.utcnow()
        db.session.commit()

    return render_template('user/notifications.html', title='My Notifications — ODACITY', user=user, notifications=notifs)


@app.route('/onboarding/customized-listing/<token>/')
def customized_listing_entry(token):
    """
    Controlled Entry Endpoint for Phase 5:
    Receives an opaque token, resolves it against VerificationCase.result_details,
    confirms that the case exists and has status == 'Passed' (Intent Approved).
    Rejects invalid/unapproved tokens with 404/403.
    """
    if not token or len(token) < 10:
        abort(404)

    # Search for matching VerificationCase containing token in result_details
    all_cases = VerificationCase.query.all()
    target_case = None

    for c in all_cases:
        if c.result_details:
            try:
                parsed = json.loads(c.result_details)
                if isinstance(parsed, dict) and 'customized_listing_link' in parsed:
                    link_info = parsed['customized_listing_link']
                    if link_info.get('token') == token and link_info.get('status') == 'active':
                        target_case = c
                        break
            except Exception:
                pass

    if not target_case:
        flash('Invalid or expired Customized Listing Link.', 'danger')
        abort(404)

    # Confirm status is strictly Passed
    if target_case.status != 'Passed':
        flash('This Customized Listing Link is not authorized.', 'danger')
        abort(403)

    if target_case.dab_id:
        customized_tokens = session.get('customized_tokens', {})
        customized_tokens[str(target_case.dab_id)] = token
        session['customized_tokens'] = customized_tokens
    session['customized_token'] = token

    from pkg.routes.admin import extract_contact_info, get_entity_display_name
    email, full_name = extract_contact_info(target_case)

    return render_template(
        'user/customized_listing_entry.html',
        case=target_case,
        applicant_name=full_name,
        applicant_email=email,
        display_name=get_entity_display_name(target_case.entity_type),
        title='Customized Listing Access — Odacity'
    )


@app.route('/onboarding/customized-listing/<token>/submit/', methods=['GET', 'POST'])
def controlled_property_submission(token):
    """
    Controlled Property / DAB Submission Endpoint for Phase 6:
    Receives token, validates against VerificationCase (status == 'Passed').
    Provides a controlled multi-step submission workflow for property location, details, photos, and title deeds.
    Saves DirectAssetBrief (status='Submitted'), Property (publication_status='Submitted', status='Submitted'),
    PropertyMedia (review_status='Uploaded'), and PropertyDocument (review_status='Pending').
    STOPS CLEAN AT SUBMITTED.
    """
    if not token or len(token) < 10:
        abort(404)

    # Resolve VerificationCase containing token in result_details
    all_cases = VerificationCase.query.all()
    target_case = None

    for c in all_cases:
        if c.result_details:
            try:
                parsed = json.loads(c.result_details)
                if isinstance(parsed, dict) and 'customized_listing_link' in parsed:
                    link_info = parsed['customized_listing_link']
                    if link_info.get('token') == token and link_info.get('status') == 'active':
                        target_case = c
                        break
            except Exception:
                pass

    if not target_case:
        flash('Invalid or expired Customized Listing Link token.', 'danger')
        abort(404)

    if target_case.status != 'Passed':
        flash('This Customized Listing Link is not authorized for submission.', 'danger')
        abort(403)

    from pkg.routes.admin import extract_contact_info, get_entity_display_name
    email, full_name = extract_contact_info(target_case)

    # Check for existing submitted DAB to prevent duplicate submissions
    existing_dab = None
    if target_case.dab_id:
        existing_dab = DirectAssetBrief.query.get(target_case.dab_id)

    form = ControlledPropertySubmissionForm()

    if form.validate_on_submit():
        now = datetime.utcnow()
        user_id = session.get('user_id')

        # 1. Resolve or create PropertyOwnerProfile
        owner_prof = None
        if user_id:
            owner_prof = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
        
        if not owner_prof:
            if user_id:
                owner_prof = PropertyOwnerProfile(user_id=user_id, created_at=now)
                db.session.add(owner_prof)
                db.session.flush()
            else:
                u = User.query.filter_by(email=email).first() if email else None
                if u:
                    owner_prof = PropertyOwnerProfile.query.filter_by(user_id=u.user_id).first()
                    if not owner_prof:
                        owner_prof = PropertyOwnerProfile(user_id=u.user_id, created_at=now)
                        db.session.add(owner_prof)
                        db.session.flush()
                else:
                    fallback_user = User.query.first()
                    if fallback_user:
                        owner_prof = PropertyOwnerProfile.query.filter_by(user_id=fallback_user.user_id).first()
                        if not owner_prof:
                            owner_prof = PropertyOwnerProfile(user_id=fallback_user.user_id, created_at=now)
                            db.session.add(owner_prof)
                            db.session.flush()

        owner_profile_id = owner_prof.owner_profile_id if owner_prof else 1

        try:
            # 2. Resolve or create DirectAssetBrief (status = 'Submitted')
            if not existing_dab:
                dab = DirectAssetBrief(
                    owner_profile_id=owner_profile_id,
                    title=form.title.data.strip(),
                    service_type=form.service_type.data,
                    property_type=form.property_type.data,
                    location=f"{form.address.data.strip()}, {form.city.data.strip()}, {form.state.data.strip()}",
                    budget_range=str(form.price.data) if form.price.data else None,
                    brief_details=form.description.data.strip() if form.description.data else None,
                    status='Submitted',
                    submitted_at=now,
                    created_at=now
                )
                db.session.add(dab)
                db.session.flush()
                target_case.dab_id = dab.dab_id
            else:
                dab = existing_dab
                dab.title = form.title.data.strip()
                dab.service_type = form.service_type.data
                dab.property_type = form.property_type.data
                dab.location = f"{form.address.data.strip()}, {form.city.data.strip()}, {form.state.data.strip()}"
                dab.budget_range = str(form.price.data) if form.price.data else None
                dab.brief_details = form.description.data.strip() if form.description.data else None
                dab.status = 'Submitted'
                dab.submitted_at = now

            # 3. Resolve or create Property (publication_status = 'Submitted', status = 'Submitted')
            prop = Property.query.filter_by(dab_id=dab.dab_id).first()
            if not prop:
                prop = Property(
                    dab_id=dab.dab_id,
                    title=form.title.data.strip(),
                    description=form.description.data.strip() if form.description.data else None,
                    property_type=form.property_type.data,
                    price=form.price.data,
                    currency='NGN',
                    address=form.address.data.strip(),
                    city=form.city.data.strip(),
                    state=form.state.data.strip(),
                    locality=form.locality.data.strip() if form.locality.data else None,
                    location=f"{form.address.data.strip()}, {form.city.data.strip()}, {form.state.data.strip()}",
                    bedroom_count=int(form.bedroom_count.data) if form.bedroom_count.data else None,
                    bathroom_count=int(form.bathroom_count.data) if form.bathroom_count.data else None,
                    land_area_sq_m=form.land_area_sq_m.data if form.land_area_sq_m.data else None,
                    amenities=form.amenities.data.split(',') if form.amenities.data else [],
                    publication_status='Submitted',
                    status='Submitted',
                    created_at=now,
                    updated_at=now
                )
                db.session.add(prop)
                db.session.flush()
            else:
                prop.title = form.title.data.strip()
                prop.description = form.description.data.strip() if form.description.data else None
                prop.property_type = form.property_type.data
                prop.price = form.price.data
                prop.address = form.address.data.strip()
                prop.city = form.city.data.strip()
                prop.state = form.state.data.strip()
                prop.publication_status = 'Submitted'
                prop.status = 'Submitted'
                prop.updated_at = now

            # 4. Handle Property Photographs (PropertyMedia - review_status = 'Uploaded', Max 20 Limit, Server-Side Magic Byte Validation)
            media_upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'property_media')
            os.makedirs(media_upload_dir, exist_ok=True)

            existing_media_count = PropertyMedia.query.filter_by(property_id=prop.property_id, type='image').count()

            # Gather files from multi-file input 'property_photos' and legacy fields
            raw_photos = request.files.getlist('property_photos')
            primary_selected_idx = request.form.get('primary_photo_index', '0')
            try:
                primary_selected_idx = int(primary_selected_idx)
            except (ValueError, TypeError):
                primary_selected_idx = 0

            photos_to_process = []
            for idx, f in enumerate(raw_photos):
                if f and hasattr(f, 'filename') and f.filename:
                    is_p = (idx == primary_selected_idx)
                    photos_to_process.append((f, is_p))

            if not photos_to_process:
                legacy_fields = [
                    (form.primary_photo.data, True),
                    (form.photo_2.data, False),
                    (form.photo_3.data, False)
                ]
                for f_data, is_p in legacy_fields:
                    if f_data and hasattr(f_data, 'filename') and f_data.filename:
                        photos_to_process.append((f_data, is_p))

            if existing_media_count + len(photos_to_process) > 20:
                flash(f"A maximum of 20 property images is allowed. This property currently has {existing_media_count} images.", "danger")
                return render_template(
                    'user/controlled_property_submission.html',
                    title='Controlled Property Brief Submission',
                    case_token=target_case.case_token,
                    target_case=target_case,
                    contact_email=email,
                    contact_name=full_name,
                    existing_dab=existing_dab,
                    form=form
                )

            has_primary_existing = PropertyMedia.query.filter_by(property_id=prop.property_id, is_primary=True).first() is not None
            order_offset = existing_media_count + 1

            for idx, (file_obj, is_p) in enumerate(photos_to_process):
                rel_path, fmt_name, err = validate_and_save_property_image(file_obj, media_upload_dir)
                if err:
                    flash(f"Error processing photo '{file_obj.filename}': {err}", "warning")
                    continue

                make_primary = False
                if is_p and not has_primary_existing:
                    make_primary = True
                    has_primary_existing = True
                elif not has_primary_existing and idx == 0:
                    make_primary = True
                    has_primary_existing = True

                media_rec = PropertyMedia(
                    property_id=prop.property_id,
                    type='image',
                    media_type='image',
                    file_path=rel_path,
                    alt_text=f"Property Photo {order_offset}",
                    display_order=order_offset,
                    is_primary=make_primary,
                    review_status='Uploaded',
                    created_at=now
                )
                db.session.add(media_rec)
                order_offset += 1

            # 5. Handle Property Title Documents (PropertyDocument - review_status = 'Pending')
            doc_upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'property_documents')
            os.makedirs(doc_upload_dir, exist_ok=True)

            doc_fields = [
                (form.title_deed, 'title_deed'),
                (form.survey_plan, 'survey')
            ]

            for doc_field_obj, doc_type in doc_fields:
                if doc_field_obj.data and hasattr(doc_field_obj.data, 'filename') and doc_field_obj.data.filename:
                    ext = os.path.splitext(doc_field_obj.data.filename)[1].lower()
                    unique_name = f"{uuid.uuid4().hex}{ext}"
                    save_path = os.path.join(doc_upload_dir, unique_name)
                    doc_field_obj.data.save(save_path)
                    rel_path = f"pkg/static/uploads/property_documents/{unique_name}"

                    doc_rec = PropertyDocument(
                        property_id=prop.property_id,
                        document_type=doc_type,
                        file_path=rel_path,
                        review_status='Pending',
                        submitted_at=now,
                        created_at=now
                    )
                    db.session.add(doc_rec)

            # 6. Log SecurityEvent
            sec_event = SecurityEvent(
                user_id=user_id or (owner_prof.user_id if owner_prof else None),
                event_type='PROPERTY_SUBMISSION_RECEIVED',
                description=f'Property brief "{form.title.data.strip()}" submitted via Customized Listing Link (Case #{target_case.verification_case_id})',
                ip_address=request.remote_addr,
                created_at=now
            )
            db.session.add(sec_event)

            # 7. Commit Transaction
            db.session.commit()

            flash('Your property brief and submitted documents have been received. They are now pending administrative review.', 'success')
            return render_template(
                'user/controlled_property_submission.html',
                submission_complete=True,
                case=target_case,
                dab=dab,
                property=prop,
                applicant_name=full_name,
                display_name=get_entity_display_name(target_case.entity_type),
                title='Property Brief Submitted — Odacity'
            )

        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during submission: {str(e)}', 'danger')

    return render_template(
        'user/controlled_property_submission.html',
        form=form,
        case=target_case,
        existing_dab=existing_dab,
        applicant_name=full_name,
        applicant_email=email,
        display_name=get_entity_display_name(target_case.entity_type),
        title='Controlled Property Submission — Odacity'
    )


def validate_and_save_property_image(file_storage, upload_dir):
    """
    Validates uploaded property image format (JPG, JPEG, PNG) via server-side magic byte headers.
    Saves raw original file intact, then safely generates resized derivatives (card, hero, thumb) using Pillow.
    Returns (rel_path, format_name, error_message).
    """
    if not file_storage or not hasattr(file_storage, 'filename') or not file_storage.filename:
        return None, None, "No file provided"

    filename = file_storage.filename.strip()
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png']:
        return None, None, "Invalid image format. Please upload a JPG, JPEG, or PNG image."

    file_storage.seek(0)
    header = file_storage.read(8)
    file_storage.seek(0)

    is_jpeg = header.startswith(b'\xff\xd8\xff')
    is_png = header.startswith(b'\x89PNG\r\n\x1a\n') or header.startswith(b'\x89PNG')

    if not (is_jpeg or is_png):
        return None, None, "Unsupported or invalid image format. Please upload a JPG, JPEG, or PNG image."

    safe_ext = '.png' if is_png else '.jpg'
    unique_name = f"{uuid.uuid4().hex}{safe_ext}"
    save_path = os.path.join(upload_dir, unique_name)

    # 1. Save raw original file intact
    file_storage.save(save_path)
    rel_path = f"uploads/property_media/{unique_name}"

    # 2. Safely generate derivatives using Pillow
    try:
        Image.MAX_IMAGE_PIXELS = 25_000_000
        with Image.open(save_path) as img:
            resample_filter = getattr(Image.Resampling, 'LANCZOS', Image.LANCZOS)

            variants = [
                ('card', 600, 85),
                ('hero', 1200, 85),
                ('thumb', 250, 80)
            ]

            for var_name, max_w, quality in variants:
                var_dir = os.path.join(upload_dir, var_name)
                os.makedirs(var_dir, exist_ok=True)
                var_path = os.path.join(var_dir, unique_name)

                img_copy = img.copy()
                w, h = img_copy.size

                # Proportional resize without upscaling smaller source images
                if w > max_w:
                    new_h = int(h * (max_w / float(w)))
                    img_copy = img_copy.resize((max_w, new_h), resample_filter)

                if is_png:
                    img_copy.save(var_path, format='PNG', optimize=True)
                else:
                    if img_copy.mode in ('RGBA', 'LA', 'P'):
                        img_copy = img_copy.convert('RGB')
                    img_copy.save(var_path, format='JPEG', quality=quality, optimize=True)
    except Exception as e:
        print(f"Warning: Failed to generate image derivatives for '{unique_name}': {e}")

    return rel_path, ('png' if is_png else 'jpeg'), None


@app.route('/properties/<int:property_id>/media/upload/', methods=['POST'])
def upload_property_media(property_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to manage property media.', 'warning')
        return redirect(url_for('login'))

    prop = Property.query.get_or_404(property_id)

    user = User.query.get(user_id)
    is_admin = user and (user.is_super_admin or has_admin_permission(user))
    owner_profile = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    is_owner = (owner_profile and prop.dab and prop.dab.owner_profile_id == owner_profile.owner_profile_id)

    if not (is_admin or is_owner):
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='UNAUTHORIZED_MEDIA_UPLOAD_ATTEMPT',
            description=f"Unauthorized media upload attempt for property #{property_id}",
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()
        flash('Access denied. You are not authorized to modify media for this property.', 'danger')
        abort(403)

    existing_count = PropertyMedia.query.filter_by(property_id=property_id, type='image').count()
    uploaded_files = request.files.getlist('photos') or request.files.getlist('property_photos')

    if not uploaded_files or not any(f and f.filename for f in uploaded_files):
        flash('No image files were selected for upload.', 'warning')
        return redirect(request.referrer or url_for('property_detail', property_id=property_id))

    valid_files = [f for f in uploaded_files if f and hasattr(f, 'filename') and f.filename]
    if existing_count + len(valid_files) > 20:
        flash(f"A maximum of 20 property images is allowed. This property currently has {existing_count} images.", "danger")
        return redirect(request.referrer or url_for('property_detail', property_id=property_id))

    media_upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'property_media')
    os.makedirs(media_upload_dir, exist_ok=True)

    has_primary = PropertyMedia.query.filter_by(property_id=property_id, is_primary=True).first() is not None
    now = datetime.utcnow()
    saved_count = 0

    for idx, f in enumerate(valid_files):
        rel_path, fmt, err = validate_and_save_property_image(f, media_upload_dir)
        if err:
            flash(f"Error: {err} ({f.filename})", "warning")
            continue

        make_p = False
        if not has_primary and idx == 0:
            make_p = True
            has_primary = True

        media_rec = PropertyMedia(
            property_id=property_id,
            type='image',
            media_type='image',
            file_path=rel_path,
            alt_text=f"Property Photo {existing_count + saved_count + 1}",
            display_order=existing_count + saved_count + 1,
            is_primary=make_p,
            review_status='Uploaded',
            created_at=now
        )
        db.session.add(media_rec)
        saved_count += 1

    if saved_count > 0:
        db.session.commit()
        flash(f"Successfully uploaded {saved_count} property photo(s). They are currently under quality review.", "success")

    return redirect(request.referrer or url_for('property_detail', property_id=property_id))


@app.route('/properties/<int:property_id>/media/<int:media_id>/set-primary/', methods=['POST'])
def set_primary_property_media(property_id, media_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to manage property media.', 'warning')
        return redirect(url_for('login'))

    prop = Property.query.get_or_404(property_id)
    med = PropertyMedia.query.filter_by(media_id=media_id, property_id=property_id).first_or_404()

    user = User.query.get(user_id)
    is_admin = user and (user.is_super_admin or has_admin_permission(user))
    owner_profile = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    is_owner = (owner_profile and prop.dab and prop.dab.owner_profile_id == owner_profile.owner_profile_id)

    if not (is_admin or is_owner):
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='UNAUTHORIZED_MEDIA_ACCESS_ATTEMPT',
            description=f"Unauthorized media modification attempt for property #{property_id}",
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()
        flash('Access denied.', 'danger')
        abort(403)

    PropertyMedia.query.filter_by(property_id=property_id).update({'is_primary': False})
    med.is_primary = True
    db.session.commit()

    flash("Primary cover photo updated successfully.", "success")
    return redirect(request.referrer or url_for('property_detail', property_id=property_id))


@app.route('/properties/<int:property_id>/media/<int:media_id>/delete/', methods=['POST'])
def delete_property_media(property_id, media_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to manage property media.', 'warning')
        return redirect(url_for('login'))

    prop = Property.query.get_or_404(property_id)
    med = PropertyMedia.query.filter_by(media_id=media_id, property_id=property_id).first_or_404()

    user = User.query.get(user_id)
    is_admin = user and (user.is_super_admin or has_admin_permission(user))
    owner_profile = PropertyOwnerProfile.query.filter_by(user_id=user_id).first()
    is_owner = (owner_profile and prop.dab and prop.dab.owner_profile_id == owner_profile.owner_profile_id)

    if not (is_admin or is_owner):
        sec_event = SecurityEvent(
            user_id=user_id,
            event_type='UNAUTHORIZED_MEDIA_ACCESS_ATTEMPT',
            description=f"Unauthorized media modification attempt for property #{property_id}",
            ip_address=request.remote_addr,
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)
        db.session.commit()
        flash('Access denied.', 'danger')
        abort(403)

    # Clean up physical files (original + derivatives)
    if med.file_path and not (med.file_path.startswith('http') or med.file_path.startswith('/')):
        clean_p = med.file_path.lstrip('/')
        orig_abs = os.path.join(app.root_path, 'static', clean_p)
        if os.path.exists(orig_abs):
            try:
                os.remove(orig_abs)
            except Exception:
                pass

        filename = os.path.basename(clean_p)
        for var in ['card', 'hero', 'thumb']:
            var_abs = os.path.join(app.root_path, 'static', 'uploads', 'property_media', var, filename)
            if os.path.exists(var_abs):
                try:
                    os.remove(var_abs)
                except Exception:
                    pass

    was_primary = med.is_primary
    db.session.delete(med)
    db.session.commit()

    if was_primary:
        next_media = PropertyMedia.query.filter_by(property_id=property_id).order_by(PropertyMedia.display_order.asc()).first()
        if next_media:
            next_media.is_primary = True
            db.session.commit()

    flash("Property photo deleted.", "info")
    return redirect(request.referrer or url_for('property_detail', property_id=property_id))


from flask import render_template, request, redirect, url_for, flash, session, abort, has_request_context


def get_property_image_url(media_or_path, variant=None):
    """
    Jinja template helper/filter for resolving property image derivative URLs with automatic fallback to original.
    Supports media objects or file path strings.
    Variants: 'card', 'hero', 'thumb'.
    """
    if not media_or_path:
        if has_request_context():
            return url_for('static', filename='img/furniture.png')
        return '/static/img/furniture.png'

    if hasattr(media_or_path, 'file_path'):
        raw_path = media_or_path.file_path
    else:
        raw_path = str(media_or_path)

    if not raw_path:
        if has_request_context():
            return url_for('static', filename='img/furniture.png')
        return '/static/img/furniture.png'

    if raw_path.startswith('/') or raw_path.startswith('http://') or raw_path.startswith('https://'):
        return raw_path

    clean_path = raw_path.lstrip('/')

    if variant in ['card', 'hero', 'thumb']:
        parts = clean_path.split('/')
        if len(parts) >= 2 and parts[-2] == 'property_media':
            derived_rel = f"uploads/property_media/{variant}/{parts[-1]}"
            abs_derived = os.path.join(app.root_path, 'static', derived_rel)
            if os.path.exists(abs_derived):
                if has_request_context():
                    return url_for('static', filename=derived_rel)
                return f"/static/{derived_rel}"

    if has_request_context():
        return url_for('static', filename=clean_path)
    return f"/static/{clean_path}"

app.jinja_env.filters['property_image_url'] = get_property_image_url
app.jinja_env.globals['get_property_image_url'] = get_property_image_url










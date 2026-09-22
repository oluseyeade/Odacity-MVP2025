import os
import uuid
from datetime import datetime
from urllib.parse import urlparse
from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from pkg import app
from pkg.models import db, User, CustomerProfile, PropertyOwnerProfile, DirectAssetBrief, SecurityEvent, Property, PropertyMedia, PropertyDocument, PerformanceGuarantee, SavedProperty, SavedSearch, Application, Inspection, Offer, Transaction, GoldReward, GoldAccount, Referral, ReferralReward, ReferralEvent, GoldEvent, Mandate, GuaranteeCycle, Notification, VerificationCase, VerificationEvent, AuditLog
from pkg.forms import RegisterForm, LoginForm, CustomerProfileForm, CustomerKycForm, SavePropertyForm, SaveSearchForm, DeleteSavedSearchForm, RentalApplicationForm, ScheduleInspectionForm, CancelApplicationForm, CancelInspectionForm, PurchaseOfferForm, CancelOfferForm, PropertyOwnerProfileForm, DirectAssetBriefForm, RespondOfferForm, DabInstitutionEnquiryForm



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


# ==========================================
# PHASE 2 — INTENT-DRIVEN PUBLIC WEBSITE ROUTES
# ==========================================

@app.route('/')
def homepage():
    """
    Odacity Intent-Driven Homepage.
    """
    featured_props = Property.query.filter_by(publication_status='Approved').limit(6).all()
    if not featured_props:
        featured_props = Property.query.limit(6).all()
    return render_template('user/index.html', title='Odacity — Direct Asset Briefs & Verified Real Estate', properties=featured_props)


@app.route('/rent/')
def rent_entry():
    return redirect(url_for('properties', intent='rent'))


@app.route('/buy/')
def buy_entry():
    return redirect(url_for('properties', intent='buy'))


@app.route('/properties/')
def properties():
    intent = request.args.get('intent', '').lower()
    state = request.args.get('state', '').strip()
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

    # Enforce publication filtering for public discovery (fallback to query if no Approved properties yet)
    query = Property.query.filter_by(publication_status='Approved')
    if query.count() == 0:
        query = Property.query

    query = query.outerjoin(DirectAssetBrief, Property.dab_id == DirectAssetBrief.dab_id)

    if state:
        query = query.filter(Property.state.ilike(f'%{state}%'))
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

    is_saved = False
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

    app_form = RentalApplicationForm()
    insp_form = ScheduleInspectionForm()
    offer_form = PurchaseOfferForm()

    return render_template(
        'user/property_detail.html',
        title=prop.title,
        property=prop,
        intent=intent,
        is_saved=is_saved,
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


@app.route('/contact/')
def contact():
    return render_template('user/contact.html', title='Contact Us')


@app.route('/onboarding/intent/')
@app.route('/intent/')
def intent_selection():
    """
    Odacity Intent & Onboarding Selection Hub.
    """
    return render_template('user/intent_selection.html', title='Select Your Intent & Onboarding Pathway — Odacity')


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
                                    status='Registered',
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


def process_referral_qualification(transaction):
    if not transaction or not transaction.customer_id:
        return None

    referral = Referral.query.filter_by(referred_customer_id=transaction.customer_id).filter(Referral.status != 'Completed').first()
    if not referral:
        return None

    now = datetime.utcnow()
    referral.status = 'Completed'
    referral.qualified_at = now

    trans_amount = float(transaction.total_amount or transaction.transaction_value or 0.0)
    reward_amount = round(trans_amount * 0.05, 2)

    reward = ReferralReward(
        referral_id=referral.referral_id,
        qualifying_transaction_id=transaction.transaction_id,
        transaction_id=transaction.transaction_id,
        referrer_customer_id=referral.referrer_customer_id,
        status='Approved',
        transaction_value=trans_amount,
        odacity_earning=round(trans_amount * 0.10, 2),
        reward_rate_percentage=5.00,
        reward_amount=reward_amount,
        calculated_at=now,
        approved_at=now,
        created_at=now
    )
    db.session.add(reward)

    ref_evt = ReferralEvent(
        referral_id=referral.referral_id,
        event_type='Qualifying_Transaction_Detected',
        event_data={'transaction_id': transaction.transaction_id, 'amount': trans_amount, 'reward_amount': reward_amount},
        occurred_at=now,
        created_at=now
    )
    db.session.add(ref_evt)

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
        **ref_ctx
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
        **ref_ctx
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

    if prop.publication_status and prop.publication_status != 'Approved':
        flash('This property is not currently available for application.', 'danger')
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

    if prop.publication_status and prop.publication_status != 'Approved':
        flash('This property is not currently available for inspection.', 'danger')
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

    if prop.publication_status and prop.publication_status != 'Approved':
        flash('This property is not currently available for purchase offers.', 'danger')
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

    return render_template(
        'user/buyer_offers.html',
        title='My Purchase Offers',
        offers=offers,
        cancel_form=cancel_form
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

    # Portfolio Metrics
    total_properties_count = len(dabs)
    available_properties = [p for p in properties if p.publication_status == 'Available']
    pending_dabs = [d for d in dabs if d.status in ['Submitted', 'Under Verification', 'Draft']]
    approved_dabs = [d for d in dabs if d.status == 'Approved']
    sold_properties = [p for p in properties if p.publication_status == 'Sold']
    rented_properties = [p for p in properties if p.publication_status == 'Rented']

    available_count = len(available_properties)
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
        pending_dabs=pending_dabs,
        sold_properties=sold_properties,
        rented_properties=rented_properties,
        total_properties_count=total_properties_count,
        available_count=available_count,
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

    action = request.form.get('action', '').strip()
    if action not in ['Accepted', 'Rejected']:
        flash('Invalid offer response action.', 'danger')
        return redirect(url_for('seller_offers'))

    offer_rec.status = action
    offer_rec.responded_at = datetime.utcnow()

    sec_event = SecurityEvent(
        user_id=user_id,
        event_type='SELLER_OFFER_RESPONDED',
        description=f'Seller responded to purchase offer #{offer_id} with status: {action}',
        ip_address=request.remote_addr,
        created_at=datetime.utcnow()
    )
    db.session.add(sec_event)
    db.session.commit()

    flash(f'Purchase offer #{offer_id} marked as {action}.', 'success' if action == 'Accepted' else 'info')
    return redirect(url_for('seller_offers'))


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








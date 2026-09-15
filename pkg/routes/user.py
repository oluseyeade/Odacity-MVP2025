from datetime import datetime
from urllib.parse import urlparse
from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from pkg import app
from pkg.models import db, User, CustomerProfile, PropertyOwnerProfile, DirectAssetBrief, SecurityEvent, Property, PropertyMedia, PropertyDocument, PerformanceGuarantee, SavedProperty, SavedSearch, Application, Inspection, Offer
from pkg.forms import RegisterForm, LoginForm, CustomerProfileForm, CustomerKycForm, SavePropertyForm, SaveSearchForm, DeleteSavedSearchForm, RentalApplicationForm, ScheduleInspectionForm, CancelApplicationForm, CancelInspectionForm, PurchaseOfferForm, CancelOfferForm, PropertyOwnerProfileForm, DirectAssetBriefForm, RespondOfferForm



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
    max_price = request.args.get('max_price', '').strip()

    # Enforce publication filtering for public discovery (fallback to query if no Approved properties yet)
    query = Property.query.filter_by(publication_status='Approved')
    if query.count() == 0:
        query = Property.query

    if state:
        query = query.filter(Property.state.ilike(f'%{state}%'))
    if property_type:
        query = query.filter(Property.property_type.ilike(f'%{property_type}%'))
    if max_price:
        try:
            query = query.filter(Property.price <= float(max_price))
        except ValueError:
            pass

    if intent == 'rent':
        query = query.filter(Property.property_type.notin_(['Land', 'Plot']))
    elif intent == 'buy':
        pass

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


@app.route('/owners/')
def owners():
    return render_template('user/owners_landing.html', title='Property Owners')


# ==========================================
# PHASE 3 — CUSTOMER AUTHENTICATION ROUTES
# ==========================================

@app.route('/register/', methods=['GET', 'POST'])
def register():
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
            return render_template('user/register.html', title='Create an Account', form=form)

        # Application-level duplicate email check
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('An account with this email address already exists. Please log in.', 'danger')
            return render_template('user/register.html', title='Create an Account', form=form)

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
            return render_template('user/register.html', title='Create an Account', form=form)

    return render_template('user/register.html', title='Create an Account', form=form)


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
        recent_events=recent_events
    )



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
# PHASE 9 — SELLER WORKFLOW ROUTES
# ==========================================

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







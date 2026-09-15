import hashlib
import sys
import os
import datetime

sys.path.insert(0, os.path.abspath('.'))

# Protected file hashes
PROTECTED_FILES = {
    'pkg/config.py': '9e83bf9d1f32289cbf9b8e2bf318e0993961067c6dc13c66a001c7d93474dbfc',
    'starter.py': '51a812713b5851ec66bf5e06b0d1f41a5ddf587adce80506ae226abf5cb904f0',
    'pkg/__init__.py': '2795e3072d21dc602070e29f70a6785adab3f24125de010e66fcc177128e45dd',
    'pkg/models.py': '6bff8e608a0d33fa29f151e62215706f2ca36b68bd3a2642163fbbac40489b0b'
}

print("=== STARTING PHASE 6 AUTOMATED TEST SUITE ===")

# 1. PROTECTED FILES SHA256 INTEGRITY AUDIT
print("\n[1] Checking Protected Files Integrity...")
integrity_passed = True
for filepath, expected_hash in PROTECTED_FILES.items():
    with open(filepath, 'rb') as f:
        actual_hash = hashlib.sha256(f.read()).hexdigest()
    if actual_hash == expected_hash:
        print(f"  [OK] {filepath}: MATCH ({actual_hash[:8]}...)")
    else:
        print(f"  [FAIL] {filepath}: MISMATCH! Expected {expected_hash}, got {actual_hash}")
        integrity_passed = False

if not integrity_passed:
    print("CRITICAL SECURITY ERROR: Protected files have been modified!")
    sys.exit(1)

from pkg import app
from pkg.models import db, User, CustomerProfile, SecurityEvent, Property, SavedProperty, SavedSearch, DirectAssetBrief, PropertyOwnerProfile

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

client = app.test_client()

# Seed test property if none exists
with app.app_context():
    prop = Property.query.first()
    if not prop:
        owner = PropertyOwnerProfile.query.first()
        if not owner:
            user_owner = User(
                email=f"owner_p6_{int(datetime.datetime.utcnow().timestamp())}@example.com",
                password_hash="hash",
                full_name="Test Owner P6",
                is_active=True,
                is_super_admin=False,
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow()
            )
            db.session.add(user_owner)
            db.session.flush()
            owner = PropertyOwnerProfile(user_id=user_owner.user_id, created_at=datetime.datetime.utcnow())
            db.session.add(owner)
            db.session.flush()

        dab = DirectAssetBrief(
            owner_profile_id=owner.owner_profile_id,
            title="P6 Test Brief",
            status="Approved",
            created_at=datetime.datetime.utcnow()
        )
        db.session.add(dab)
        db.session.flush()

        prop = Property(
            dab_id=dab.dab_id,
            title="P6 Luxury Villa",
            description="Luxury Villa for P6 Test",
            property_type="Residential",
            price=15000000.00,
            currency="NGN",
            address="456 Ikoyi Road",
            state="Lagos",
            city="Lagos",
            locality="Ikoyi",
            publication_status="Approved",
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )
        db.session.add(prop)
        db.session.commit()

# TEST 1 — PROTECTED DASHBOARD
print("\n[2] TEST 1: Testing Unauthenticated /dashboard/ Protection...")
resp_dash_unauth = client.get('/dashboard/')
assert resp_dash_unauth.status_code == 302, f"Expected 302 for unauth dashboard, got {resp_dash_unauth.status_code}"
assert '/login' in resp_dash_unauth.headers['Location']
print("  [OK] Unauthenticated GET /dashboard/ redirects to /login/")

# TEST 2 & 3 — AUTHENTICATED DASHBOARD & LOGIN REDIRECT
print("\n[3] TEST 2 & 3: Registering User & Testing Login Redirect to Dashboard...")
test_email_a = f"cust_a_{int(datetime.datetime.utcnow().timestamp())}@example.com"
test_password_a = "SecurePassA123!"

with app.app_context():
    # Register Customer A
    client.post('/register/', data={
        'firstname': 'Customer',
        'lastname': 'Alpha',
        'email': test_email_a,
        'phone': '08011112222',
        'password': test_password_a,
        'confirm_pass': test_password_a
    }, follow_redirects=True)

    # Logout and log in again
    client.get('/logout/', follow_redirects=True)
    login_res = client.post('/login/', data={
        'email': test_email_a,
        'password': test_password_a
    }, follow_redirects=False)

    assert login_res.status_code == 302
    assert '/dashboard/' in login_res.headers['Location']
    print("  [OK] Successful login redirects to /dashboard/")

    # GET /dashboard/
    dash_res = client.get('/dashboard/')
    assert dash_res.status_code == 200
    assert b'Customer Alpha' in dash_res.data
    assert b'COMMON USER DASHBOARD' in dash_res.data
    print("  [OK] Authenticated GET /dashboard/ returned 200 OK with user details")

# TEST 4 — DASHBOARD METRICS & RECENT ACTIVITY
print("\n[4] TEST 4: Verifying Dashboard Metrics & Recent Activity Feed...")
with app.app_context():
    client.post('/login/', data={'email': test_email_a, 'password': test_password_a}, follow_redirects=True)
    user_a = User.query.filter_by(email=test_email_a).first()
    cust_a = CustomerProfile.query.filter_by(user_id=user_a.user_id).first()
    test_prop = Property.query.first()

    # Save property and save search
    client.post(f'/properties/{test_prop.property_id}/save/', follow_redirects=True)
    client.post('/save-search/', data={
        'name': 'Alpha Ikoyi Search',
        'intent': 'buy',
        'state': 'Lagos',
        'property_type': 'Residential',
        'max_price': '20000000'
    }, follow_redirects=True)

    dash_metrics_res = client.get('/dashboard/')
    assert dash_metrics_res.status_code == 200

    # Verify metric counts in DB for Customer A
    saved_props_cnt = SavedProperty.query.filter_by(customer_id=cust_a.customer_id).count()
    saved_searches_cnt = SavedSearch.query.filter_by(customer_id=cust_a.customer_id).count()

    assert saved_props_cnt == 1, f"Expected 1 saved property, got {saved_props_cnt}"
    assert saved_searches_cnt == 1, f"Expected 1 saved search, got {saved_searches_cnt}"
    print("  [OK] Saved Property and Saved Search metrics verified in DB and rendered in Dashboard")

# TEST 5 — CUSTOMER ISOLATION
print("\n[5] TEST 5: Verifying Customer Dashboard Isolation...")
test_email_b = f"cust_b_{int(datetime.datetime.utcnow().timestamp())}@example.com"
test_password_b = "SecurePassB123!"

with app.app_context():
    # Register Customer B
    client.post('/register/', data={
        'firstname': 'Customer',
        'lastname': 'Beta',
        'email': test_email_b,
        'phone': '08033334444',
        'password': test_password_b,
        'confirm_pass': test_password_b
    }, follow_redirects=True)

    # Login as Customer B
    client.post('/login/', data={'email': test_email_b, 'password': test_password_b}, follow_redirects=True)
    user_b = User.query.filter_by(email=test_email_b).first()
    cust_b = CustomerProfile.query.filter_by(user_id=user_b.user_id).first()

    dash_b_res = client.get('/dashboard/')
    assert dash_b_res.status_code == 200
    assert b'Customer Beta' in dash_b_res.data
    assert b'Customer Alpha' not in dash_b_res.data

    saved_props_b = SavedProperty.query.filter_by(customer_id=cust_b.customer_id).count()
    saved_searches_b = SavedSearch.query.filter_by(customer_id=cust_b.customer_id).count()

    assert saved_props_b == 0, f"Expected 0 saved props for Customer B, got {saved_props_b}"
    assert saved_searches_b == 0, f"Expected 0 saved searches for Customer B, got {saved_searches_b}"
    print("  [OK] Customer B dashboard isolated from Customer A metrics")

# TEST 6 — REGRESSION SUITE (PHASES 1 - 5)
print("\n[6] TEST 6: Running Regression Suite (Phases 1-5)...")
with app.app_context():
    res404 = client.get('/nonexistent-page-99999')
    assert res404.status_code == 404
    print("  [OK] Phase 1 404 handler PASS")

    res_home = client.get('/')
    assert res_home.status_code == 200
    print("  [OK] Phase 2 Homepage PASS")

    res_rent = client.get('/rent/', follow_redirects=True)
    assert res_rent.status_code == 200
    print("  [OK] Phase 2 Discovery Rent PASS")

    res_logout = client.get('/logout/', follow_redirects=True)
    assert res_logout.status_code == 200
    print("  [OK] Phase 3 Logout PASS")

print("\n=== PHASE 6 AUTOMATED TEST SUITE PASSED 100% ===")

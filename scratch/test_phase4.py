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

print("=== STARTING PHASE 4 CORRECTION AUTOMATED TEST SUITE ===")

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

# Import app & db & forms
from pkg import app
from pkg.models import db, User, CustomerProfile, SecurityEvent, Property
from pkg.forms import CustomerKycForm

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

client = app.test_client()

# 2. FORM INTEGRITY AUDIT
print("\n[2] Verifying CustomerKycForm Fields...")
with app.app_context():
    kyc_form = CustomerKycForm()
    assert not hasattr(kyc_form, 'id_type'), "[FAIL] CustomerKycForm still contains id_type!"
    assert not hasattr(kyc_form, 'id_number'), "[FAIL] CustomerKycForm still contains id_number!"
    print("  [OK] CustomerKycForm has no id_type or id_number fields")

# 3. UNAUTHENTICATED REDIRECT TESTS
print("\n[3] Testing Unauthenticated Protection for /profile/ and /kyc/...")
resp_prof = client.get('/profile/')
assert resp_prof.status_code == 302, f"Expected 302 for unauth /profile/, got {resp_prof.status_code}"
assert '/login' in resp_prof.headers['Location'], f"Expected redirect to login, got {resp_prof.headers['Location']}"
print("  [OK] Unauthenticated GET /profile/ redirects to /login/")

resp_kyc = client.get('/kyc/')
assert resp_kyc.status_code == 302, f"Expected 302 for unauth /kyc/, got {resp_kyc.status_code}"
assert '/login' in resp_kyc.headers['Location'], f"Expected redirect to login, got {resp_kyc.headers['Location']}"
print("  [OK] Unauthenticated GET /kyc/ redirects to /login/")

# 4. AUTHENTICATION & PROFILE CREATION
print("\n[4] Registering Test User & Creating Authenticated Session...")
test_email = f"phase4_corr_{int(datetime.datetime.utcnow().timestamp())}@example.com"
test_password = "SecurePassword123!"

with app.app_context():
    # Register user
    reg_resp = client.post('/register/', data={
        'firstname': 'Phase4Corr',
        'lastname': 'User',
        'email': test_email,
        'phone': '08012345678',
        'password': test_password,
        'confirm_pass': test_password
    }, follow_redirects=True)
    assert reg_resp.status_code == 200, f"Registration failed with code {reg_resp.status_code}"

    user = User.query.filter_by(email=test_email).first()
    assert user is not None, "User not found in DB after registration!"
    cust_profile = CustomerProfile.query.filter_by(user_id=user.user_id).first()
    assert cust_profile is not None, "CustomerProfile not automatically created!"
    print(f"  [OK] Account & CustomerProfile created for user_id={user.user_id}")

# 5. AUTHENTICATED PROFILE VIEW & EDIT
print("\n[5] Testing Authenticated GET & POST /profile/...")
with app.app_context():
    # Login as test user
    login_resp = client.post('/login/', data={
        'email': test_email,
        'password': test_password
    }, follow_redirects=True)
    assert login_resp.status_code == 200, f"Login failed with code {login_resp.status_code}"

    # GET /profile/
    get_prof = client.get('/profile/')
    assert get_prof.status_code == 200, f"GET /profile/ failed with code {get_prof.status_code}"
    print("  [OK] GET /profile/ returned 200 OK")

    # POST /profile/ (Update profile)
    post_prof = client.post('/profile/', data={
        'first_name': 'UpdatedFirst',
        'last_name': 'UpdatedLast',
        'phone_number': '09098765432',
        'date_of_birth': '1995-05-15',
        'gender': 'Male',
        'address': '123 Test Street, Victoria Island, Lagos'
    }, follow_redirects=True)
    assert post_prof.status_code == 200, f"POST /profile/ failed with code {post_prof.status_code}"

    # Verify DB updates
    db.session.expire_all()
    user = User.query.filter_by(email=test_email).first()
    cust_profile = CustomerProfile.query.filter_by(user_id=user.user_id).first()

    assert cust_profile.first_name == 'UpdatedFirst'
    assert cust_profile.last_name == 'UpdatedLast'
    assert cust_profile.phone_number == '09098765432'
    assert str(cust_profile.date_of_birth) == '1995-05-15'
    assert cust_profile.gender == 'Male'
    assert cust_profile.address == '123 Test Street, Victoria Island, Lagos'
    assert user.full_name == 'UpdatedFirst UpdatedLast'
    assert user.phone == '09098765432'
    print("  [OK] CustomerProfile attributes updated successfully in DB")

    # Check SecurityEvent
    sec_event = SecurityEvent.query.filter_by(user_id=user.user_id, event_type='CUSTOMER_PROFILE_UPDATED').first()
    assert sec_event is not None, "CUSTOMER_PROFILE_UPDATED SecurityEvent was not logged!"
    print("  [OK] SecurityEvent CUSTOMER_PROFILE_UPDATED logged")

# 6. AUTHENTICATED KYC SUBMISSION (CORRECTED)
print("\n[6] Testing Authenticated GET & POST /kyc/ (Corrected Flow)...")
with app.app_context():
    # GET /kyc/
    get_kyc = client.get('/kyc/')
    assert get_kyc.status_code == 200, f"GET /kyc/ failed with code {get_kyc.status_code}"
    assert b'id_type' not in get_kyc.data, "[FAIL] id_type found in rendered template!"
    assert b'id_number' not in get_kyc.data, "[FAIL] id_number found in rendered template!"
    print("  [OK] GET /kyc/ returned 200 OK without ID collection fields")

    # POST /kyc/ (without id_type/id_number)
    post_kyc = client.post('/kyc/', data={}, follow_redirects=True)
    assert post_kyc.status_code == 200, f"POST /kyc/ failed with code {post_kyc.status_code}"

    # Verify DB status
    db.session.expire_all()
    user = User.query.filter_by(email=test_email).first()
    cust_profile = CustomerProfile.query.filter_by(user_id=user.user_id).first()

    assert cust_profile.kyc_status == 'PENDING', f"Expected PENDING, got {cust_profile.kyc_status}"
    assert cust_profile.verification_status == 'Pending', f"Expected Pending, got {cust_profile.verification_status}"
    print("  [OK] CustomerProfile.kyc_status updated to 'PENDING'")
    print("  [OK] CustomerProfile.verification_status updated to 'Pending'")

    # Check SecurityEvent
    sec_event = SecurityEvent.query.filter_by(user_id=user.user_id, event_type='CUSTOMER_KYC_SUBMITTED').first()
    assert sec_event is not None, "CUSTOMER_KYC_SUBMITTED SecurityEvent was not logged!"
    assert 'id_type' not in sec_event.description, "id_type was logged in SecurityEvent!"
    assert 'id_number' not in sec_event.description, "id_number was logged in SecurityEvent!"
    print("  [OK] SecurityEvent CUSTOMER_KYC_SUBMITTED logged without sensitive ID details")

# 7. REGRESSION SUITE (PHASES 1, 2, 3)
print("\n[7] Running Regression Tests (Phases 1, 2, 3)...")
with app.app_context():
    res404 = client.get('/nonexistent-page-12345')
    assert res404.status_code == 404
    print("  [OK] 404 handler PASS")

    res_home = client.get('/')
    assert res_home.status_code == 200
    res_rent = client.get('/rent/', follow_redirects=True)
    assert res_rent.status_code == 200
    res_buy = client.get('/buy/', follow_redirects=True)
    assert res_buy.status_code == 200
    print("  [OK] Phase 2 intent routes PASS")

    res_logout = client.get('/logout/', follow_redirects=True)
    assert res_logout.status_code == 200
    print("  [OK] Logout PASS")

print("\n=== PHASE 4 CORRECTION SUITE PASSED 100% ===")

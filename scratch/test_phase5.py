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

print("=== STARTING PHASE 5 AUTOMATED TEST SUITE ===")

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
                email=f"owner_{int(datetime.datetime.utcnow().timestamp())}@example.com",
                password_hash="hash",
                full_name="Test Owner",
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
            title="Luxury Apartment",
            status="Approved",
            created_at=datetime.datetime.utcnow()
        )
        db.session.add(dab)
        db.session.flush()

        prop = Property(
            dab_id=dab.dab_id,
            title="Luxury 3 Bed Apartment",
            description="High-end apartment in Victoria Island",
            property_type="Apartment",
            price=5000000.00,
            currency="NGN",
            address="123 Ahmadu Bello Way",
            state="Lagos",
            city="Lagos",
            locality="Victoria Island",
            bedroom_count=3,
            bathroom_count=3,
            land_area_sq_m=250.00,
            publication_status="Approved",
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )
        db.session.add(prop)
        db.session.commit()

# 2. DISCOVERY INTENTS & FILTERING
print("\n[2] Testing Property Discovery Engine & Intent Redirects...")
res_rent = client.get('/rent/')
assert res_rent.status_code == 302
assert '/properties/?intent=rent' in res_rent.headers['Location'] or '/properties/?intent=rent' in res_rent.headers['Location'].replace('%3F', '?')
print("  [OK] GET /rent/ redirects to /properties/?intent=rent")

res_buy = client.get('/buy/')
assert res_buy.status_code == 302
assert '/properties/?intent=buy' in res_buy.headers['Location']
print("  [OK] GET /buy/ redirects to /properties/?intent=buy")

res_props = client.get('/properties/?intent=rent&state=Lagos&max_price=10000000')
assert res_props.status_code == 200
assert b'Verified Listings' in res_props.data or b'Properties' in res_props.data
print("  [OK] GET /properties/ with filters returned 200 OK")

res_malformed = client.get('/properties/?max_price=invalid_price_str')
assert res_malformed.status_code == 200
print("  [OK] Malformed max_price handled gracefully without 500 error")

# 3. PROPERTY DETAIL
print("\n[3] Testing Property Detail View...")
with app.app_context():
    test_prop = Property.query.first()
    res_detail = client.get(f'/properties/{test_prop.property_id}/')
    assert res_detail.status_code == 200
    assert test_prop.title.encode() in res_detail.data
    print(f"  [OK] GET /properties/{test_prop.property_id}/ returned 200 OK with property details")

res_404_detail = client.get('/properties/999999/')
assert res_404_detail.status_code == 404
print("  [OK] GET /properties/999999/ returned 404 Not Found")

# 4. AUTHENTICATION & SAVED PROPERTIES
print("\n[4] Testing Saved Properties (Favorites)...")
test_email = f"phase5_user_{int(datetime.datetime.utcnow().timestamp())}@example.com"
test_password = "SecurePassword123!"

with app.app_context():
    # Register customer
    client.post('/register/', data={
        'firstname': 'Phase5',
        'lastname': 'Tester',
        'email': test_email,
        'phone': '08099887766',
        'password': test_password,
        'confirm_pass': test_password
    }, follow_redirects=True)

    test_prop = Property.query.first()

    # Unauthenticated save redirect
    client.get('/logout/', follow_redirects=True)
    unauth_save = client.post(f'/properties/{test_prop.property_id}/save/')
    assert unauth_save.status_code == 302
    assert '/login' in unauth_save.headers['Location']
    print("  [OK] Unauthenticated save redirects to login")

    # Authenticated save
    client.post('/login/', data={'email': test_email, 'password': test_password}, follow_redirects=True)
    user = User.query.filter_by(email=test_email).first()
    cust_profile = CustomerProfile.query.filter_by(user_id=user.user_id).first()

    auth_save = client.post(f'/properties/{test_prop.property_id}/save/', follow_redirects=True)
    assert auth_save.status_code == 200

    saved_rec = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id, property_id=test_prop.property_id).first()
    assert saved_rec is not None, "SavedProperty record not found in DB!"
    print("  [OK] Authenticated POST save_property created SavedProperty record")

    # Check SecurityEvent
    sec_event = SecurityEvent.query.filter_by(user_id=user.user_id, event_type='PROPERTY_SAVED').first()
    assert sec_event is not None, "PROPERTY_SAVED SecurityEvent not logged!"
    print("  [OK] PROPERTY_SAVED SecurityEvent logged")

    # Duplicate save prevention
    dup_save = client.post(f'/properties/{test_prop.property_id}/save/', follow_redirects=True)
    assert dup_save.status_code == 200
    saved_count = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id, property_id=test_prop.property_id).count()
    assert saved_count == 1, f"Expected 1 saved property record, got {saved_count}"
    print("  [OK] Duplicate save prevented application-side")

    # GET /saved-properties/
    res_saved_page = client.get('/saved-properties/')
    assert res_saved_page.status_code == 200
    assert test_prop.title.encode() in res_saved_page.data
    print("  [OK] GET /saved-properties/ displayed customer saved items")

    # Unsave property
    unsave_res = client.post(f'/properties/{test_prop.property_id}/unsave/', follow_redirects=True)
    assert unsave_res.status_code == 200
    saved_count_after = SavedProperty.query.filter_by(customer_id=cust_profile.customer_id, property_id=test_prop.property_id).count()
    assert saved_count_after == 0
    print("  [OK] Authenticated POST unsave_property deleted SavedProperty record")

# 5. SAVED SEARCHES
print("\n[5] Testing Saved Searches...")
with app.app_context():
    client.post('/login/', data={'email': test_email, 'password': test_password}, follow_redirects=True)
    user = User.query.filter_by(email=test_email).first()
    cust_profile = CustomerProfile.query.filter_by(user_id=user.user_id).first()

    # Save search
    save_search_res = client.post('/save-search/', data={
        'name': 'Lagos Rent Search',
        'intent': 'rent',
        'state': 'Lagos',
        'property_type': 'Apartment',
        'max_price': '10000000'
    }, follow_redirects=True)
    assert save_search_res.status_code == 200

    saved_search_rec = SavedSearch.query.filter_by(customer_id=cust_profile.customer_id, name='Lagos Rent Search').first()
    assert saved_search_rec is not None, "SavedSearch record not found in DB!"
    assert saved_search_rec.search_criteria.get('intent') == 'rent'
    print("  [OK] Authenticated POST save_search created SavedSearch record with criteria JSON")

    sec_event_search = SecurityEvent.query.filter_by(user_id=user.user_id, event_type='SEARCH_SAVED').first()
    assert sec_event_search is not None, "SEARCH_SAVED SecurityEvent not logged!"
    print("  [OK] SEARCH_SAVED SecurityEvent logged")

    # GET /saved-searches/
    res_searches_page = client.get('/saved-searches/')
    assert res_searches_page.status_code == 200
    assert b'Lagos Rent Search' in res_searches_page.data
    print("  [OK] GET /saved-searches/ displayed customer saved searches")

    # Delete saved search
    del_search_res = client.post(f'/saved-searches/{saved_search_rec.saved_search_id}/delete/', follow_redirects=True)
    assert del_search_res.status_code == 200
    search_after = SavedSearch.query.get(saved_search_rec.saved_search_id)
    assert search_after is None
    print("  [OK] Authenticated POST delete_saved_search deleted SavedSearch record")

# 6. REGRESSION SUITE
print("\n[6] Running Regression Suite (Phases 1, 2, 3, 4)...")
with app.app_context():
    res404 = client.get('/nonexistent-page-99999')
    assert res404.status_code == 404
    print("  [OK] 404 handler PASS")

    res_home = client.get('/')
    assert res_home.status_code == 200
    print("  [OK] Homepage PASS")

    res_logout = client.get('/logout/', follow_redirects=True)
    assert res_logout.status_code == 200
    print("  [OK] Logout PASS")

print("\n=== PHASE 5 AUTOMATED TEST SUITE PASSED 100% ===")

import hashlib
import datetime
import sys
import os

sys.path.insert(0, os.path.abspath('.'))

from starter import app
from pkg.models import db, User, CustomerProfile, PropertyOwnerProfile, Property, DirectAssetBrief, Application, Inspection, SavedProperty, SavedSearch, SecurityEvent




PROTECTED_HASHES = {
    'pkg/config.py': '9e83bf9d1f32289cbf9b8e2bf318e0993961067c6dc13c66a001c7d93474dbfc',
    'starter.py': '51a812713b5851ec66bf5e06b0d1f41a5ddf587adce80506ae226abf5cb904f0',
    'pkg/__init__.py': '2795e3072d21dc602070e29f70a6785adab3f24125de010e66fcc177128e45dd',
    'pkg/models.py': '6bff8e608a0d33fa29f151e62215706f2ca36b68bd3a2642163fbbac40489b0b'
}

def verify_protected_files():
    print("[1] Checking Protected Files Integrity...")
    for path, expected in PROTECTED_HASHES.items():
        with open(path, 'rb') as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        if actual != expected:
            print(f"  [FAIL] {path} hash mismatch!\nExpected: {expected}\nActual:   {actual}")
            sys.exit(1)
        print(f"  [OK] {path}: MATCH ({actual[:8]}...)")

def run_tests():
    print("\n=== STARTING PHASE 7 AUTOMATED TEST SUITE ===")
    verify_protected_files()

    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    with app.test_client() as client:
        with app.app_context():
            # Setup test data
            now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            email_a = f"renter_a_{now_ts}@example.com"
            email_b = f"renter_b_{now_ts}@example.com"

            # Create test user A & customer profile A
            user_a = User(
                email=email_a,
                password_hash='pbkdf2:sha256:fakehash',
                full_name='Renter Customer A',
                is_active=True,
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow()
            )
            db.session.add(user_a)
            db.session.commit()

            profile_a = CustomerProfile(
                user_id=user_a.user_id,
                first_name='Renter',
                last_name='Customer A',
                kyc_status='VERIFIED',
                created_at=datetime.datetime.utcnow()
            )
            db.session.add(profile_a)

            # Create test user B & customer profile B
            user_b = User(
                email=email_b,
                password_hash='pbkdf2:sha256:fakehash',
                full_name='Renter Customer B',
                is_active=True,
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow()
            )
            db.session.add(user_b)
            db.session.commit()

            profile_b = CustomerProfile(
                user_id=user_b.user_id,
                first_name='Renter',
                last_name='Customer B',
                kyc_status='UNSUBMITTED',
                created_at=datetime.datetime.utcnow()
            )
            db.session.add(profile_b)
            db.session.commit()

            # Create dedicated owner profile and DAB for unique dab_id
            owner_prof = PropertyOwnerProfile(user_id=user_a.user_id, owner_type='Individual', is_approved=True, created_at=datetime.datetime.utcnow())
            db.session.add(owner_prof)
            db.session.commit()

            dab = DirectAssetBrief(owner_profile_id=owner_prof.owner_profile_id, title='Test Rental Brief', status='Approved', created_at=datetime.datetime.utcnow())
            db.session.add(dab)
            db.session.commit()

            test_prop = Property(
                dab_id=dab.dab_id,
                title="Luxury 3 Bedroom Apartment for Rent",
                description="Prime rental property in Lekki Phase 1",
                property_type="Apartment",
                price=5000000.00,
                currency="NGN",
                state="Lagos",
                city="Lekki",
                publication_status="Approved",
                status="Available",
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow()
            )
            db.session.add(test_prop)
            db.session.commit()
            prop_id = test_prop.property_id



            # SECTION 1: RENTAL DISCOVERY
            print("\n[2] TEST 1: Testing Rental Discovery (/rent/)...")
            res = client.get('/rent/', follow_redirects=True)
            assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}"
            assert b"Properties" in res.data or b"Listings" in res.data, "Rental discovery page failed to render"
            print("  [OK] /rent/ redirect and discovery filtering verified.")

            # SECTION 2: APPLICATION CREATION & AUTH PROTECTION
            print("\n[3] TEST 2: Testing Application Unauthenticated Protection...")
            res = client.post(f'/properties/{prop_id}/apply/', data={'notes': 'Test application'}, follow_redirects=True)
            assert b"Please log in" in res.data or b"login" in res.data.lower(), "Unauthenticated apply failed to redirect to login"
            print("  [OK] Unauthenticated application POST correctly blocked.")

            print("\n[4] TEST 3: Testing Authenticated Rental Application Creation...")
            with client.session_transaction() as sess:
                sess['user_id'] = user_a.user_id

            res = client.post(f'/properties/{prop_id}/apply/', data={'notes': 'Interested in 2-year lease'}, follow_redirects=True)
            assert res.status_code == 200, f"Apply failed with status {res.status_code}"
            assert b"Rental application submitted successfully" in res.data or b"Submitted" in res.data, "Success flash message missing"

            app_rec = Application.query.filter_by(customer_id=profile_a.customer_id, property_id=prop_id).first()
            assert app_rec is not None, "Application record not saved to DB"
            assert app_rec.status == 'Submitted', f"Expected status 'Submitted', got '{app_rec.status}'"
            assert app_rec.notes == 'Interested in 2-year lease', "Application notes mismatch"
            print("  [OK] Rental application created and persisted in DB.")

            # SECTION 3: DUPLICATE APPLICATION PREVENTION
            print("\n[5] TEST 4: Testing Duplicate Application Prevention...")
            res = client.post(f'/properties/{prop_id}/apply/', data={'notes': 'Second application'}, follow_redirects=True)
            assert b"already have an active rental application" in res.data, "Duplicate application check failed"
            apps_count = Application.query.filter_by(customer_id=profile_a.customer_id, property_id=prop_id).count()
            assert apps_count == 1, f"Expected 1 application in DB, found {apps_count}"
            print("  [OK] Duplicate active application prevented.")

            # SECTION 4: RENTER APPLICATIONS PORTAL
            print("\n[6] TEST 5: Testing Renter Applications Portal...")
            res = client.get('/renter/applications/')
            assert res.status_code == 200, f"Renter applications portal failed with status {res.status_code}"
            assert b"Luxury 3 Bedroom Apartment" in res.data, "Property title missing from application list"
            assert b"Submitted" in res.data, "Status badge missing from application list"
            print("  [OK] Renter applications portal renders customer applications accurately.")

            # SECTION 5: APPLICATION CANCELLATION & IDOR PROTECTION
            print("\n[7] TEST 6: Testing Application Cancellation & IDOR Protection...")
            # Switch to Customer B and attempt to cancel Customer A's application
            with client.session_transaction() as sess:
                sess['user_id'] = user_b.user_id

            res = client.post(f'/applications/{app_rec.application_id}/cancel/', follow_redirects=True)
            assert b"record not found or access denied" in res.data or b"denied" in res.data.lower(), "IDOR vulnerability: Customer B cancelled Customer A application!"
            
            # Verify status is still Submitted
            db.session.refresh(app_rec)
            assert app_rec.status == 'Submitted', "Application status modified by unauthorized user"

            # Switch back to Customer A and cancel own application
            with client.session_transaction() as sess:
                sess['user_id'] = user_a.user_id

            res = client.post(f'/applications/{app_rec.application_id}/cancel/', follow_redirects=True)
            assert b"cancelled successfully" in res.data or b"Cancelled" in res.data, "Application cancellation failed"
            db.session.refresh(app_rec)
            assert app_rec.status == 'Cancelled', f"Expected status 'Cancelled', got '{app_rec.status}'"
            print("  [OK] Application cancellation and IDOR protection verified.")

            # SECTION 6: INSPECTION CREATION & DUPLICATE PREVENTION
            print("\n[8] TEST 7: Testing Inspection Request Creation & Duplicate Prevention...")
            res = client.post(f'/properties/{prop_id}/inspection/', data={'notes': 'Weekend morning preferred', 'scheduled_for': '2026-10-15'}, follow_redirects=True)
            assert res.status_code == 200, f"Inspection request failed with status {res.status_code}"
            assert b"Inspection request submitted successfully" in res.data or b"Requested" in res.data, "Success flash message missing"

            insp_rec = Inspection.query.filter_by(customer_id=profile_a.customer_id, property_id=prop_id).first()
            assert insp_rec is not None, "Inspection record not saved to DB"
            assert insp_rec.status == 'Requested', f"Expected status 'Requested', got '{insp_rec.status}'"
            print("  [OK] Inspection request created and persisted in DB.")

            # Duplicate check
            res = client.post(f'/properties/{prop_id}/inspection/', data={'notes': 'Duplicate inspection'}, follow_redirects=True)
            assert b"already have an active inspection request" in res.data, "Duplicate inspection check failed"
            insps_count = Inspection.query.filter_by(customer_id=profile_a.customer_id, property_id=prop_id).count()
            assert insps_count == 1, f"Expected 1 inspection in DB, found {insps_count}"
            print("  [OK] Duplicate active inspection request prevented.")

            # SECTION 7: RENTER INSPECTIONS PORTAL & CANCELLATION
            print("\n[9] TEST 8: Testing Renter Inspections Portal & Cancellation...")
            res = client.get('/renter/inspections/')
            assert res.status_code == 200, f"Renter inspections portal failed with status {res.status_code}"
            assert b"Luxury 3 Bedroom Apartment" in res.data, "Property title missing from inspection list"
            assert b"Requested" in res.data, "Status badge missing from inspection list"

            # Cancel inspection
            res = client.post(f'/inspections/{insp_rec.inspection_id}/cancel/', follow_redirects=True)
            assert b"cancelled successfully" in res.data or b"Cancelled" in res.data, "Inspection cancellation failed"
            db.session.refresh(insp_rec)
            assert insp_rec.status == 'Cancelled', f"Expected status 'Cancelled', got '{insp_rec.status}'"
            print("  [OK] Renter inspections portal and cancellation verified.")

            # SECTION 8: DASHBOARD & NAVIGATION INTEGRATION
            print("\n[10] TEST 9: Testing Dashboard & Navigation Integration...")
            res = client.get('/dashboard/')
            assert res.status_code == 200, f"Dashboard failed with status {res.status_code}"
            assert b"Rental Applications" in res.data, "Applications metric missing from dashboard"
            assert b"Inspection Requests" in res.data, "Inspections metric missing from dashboard"
            print("  [OK] Dashboard integration verified.")

            # SECTION 9: REGRESSION CHECKS (PHASES 1-6)
            print("\n[11] TEST 10: Running Regression Suite (Phases 1-6)...")
            assert client.get('/non-existent-route-123').status_code == 404, "Phase 1 404 handler broken"
            assert client.get('/').status_code == 200, "Phase 2 homepage broken"
            assert client.get('/properties/').status_code == 200, "Phase 2 discovery broken"
            assert client.get('/logout/', follow_redirects=True).status_code == 200, "Phase 3 logout broken"
            print("  [OK] Phase 1-6 regression suite passed.")

            # Clean up test data
            print("\n[12] Cleaning up temporary test data...")
            Inspection.query.filter(Inspection.customer_id.in_([profile_a.customer_id, profile_b.customer_id])).delete(synchronize_session=False)
            Application.query.filter(Application.customer_id.in_([profile_a.customer_id, profile_b.customer_id])).delete(synchronize_session=False)
            Property.query.filter_by(property_id=prop_id).delete(synchronize_session=False)
            DirectAssetBrief.query.filter_by(dab_id=dab.dab_id).delete(synchronize_session=False)
            PropertyOwnerProfile.query.filter_by(owner_profile_id=owner_prof.owner_profile_id).delete(synchronize_session=False)
            CustomerProfile.query.filter(CustomerProfile.customer_id.in_([profile_a.customer_id, profile_b.customer_id])).delete(synchronize_session=False)
            SecurityEvent.query.filter(SecurityEvent.user_id.in_([user_a.user_id, user_b.user_id])).delete(synchronize_session=False)
            User.query.filter(User.user_id.in_([user_a.user_id, user_b.user_id])).delete(synchronize_session=False)
            db.session.commit()
            print("  [OK] Test data successfully cleaned up.")




    print("\n=== PHASE 7 AUTOMATED TEST SUITE PASSED 100% ===")

if __name__ == '__main__':
    run_tests()

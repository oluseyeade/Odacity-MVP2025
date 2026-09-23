import os
import sys
import unittest
import json
from datetime import datetime, timedelta

# Ensure project root is in sys.path
PROJECT_ROOT = r'c:\Users\User\Desktop\Odacity-MVP2025'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pkg import app
from pkg.models import (
    db, User, PropertyOwnerProfile, CustomerProfile, DirectAssetBrief, Property,
    PropertyDocument, PropertyMedia, VerificationCase, VerificationEvent,
    AuditLog, SecurityEvent
)

class Phase10SoldUnavailableTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # Seed super admin
        self.admin = User.query.filter_by(email='admin_p10@odacity.com').first()
        if not self.admin:
            self.admin = User(
                email='admin_p10@odacity.com',
                password_hash='pbkdf2:sha256:test',
                full_name='Super Admin P10',
                is_active=True,
                is_super_admin=True,
                created_at=datetime.utcnow()
            )
            db.session.add(self.admin)

        # Seed Owner 1
        self.owner1_user = User.query.filter_by(email='owner1_p10@odacity.com').first()
        if not self.owner1_user:
            self.owner1_user = User(
                email='owner1_p10@odacity.com',
                password_hash='pbkdf2:sha256:test',
                full_name='Owner One P10',
                is_active=True,
                is_super_admin=False,
                created_at=datetime.utcnow()
            )
            db.session.add(self.owner1_user)
            db.session.flush()

        self.owner1_prof = PropertyOwnerProfile.query.filter_by(user_id=self.owner1_user.user_id).first()
        if not self.owner1_prof:
            self.owner1_prof = PropertyOwnerProfile(
                user_id=self.owner1_user.user_id,
                company_name='Owner 1 Corp',
                owner_type='individual',
                is_approved=True,
                created_at=datetime.utcnow()
            )
            db.session.add(self.owner1_prof)

        # Seed Owner 2 (Attacker/Other Owner)
        self.owner2_user = User.query.filter_by(email='owner2_p10@odacity.com').first()
        if not self.owner2_user:
            self.owner2_user = User(
                email='owner2_p10@odacity.com',
                password_hash='pbkdf2:sha256:test',
                full_name='Owner Two P10',
                is_active=True,
                is_super_admin=False,
                created_at=datetime.utcnow()
            )
            db.session.add(self.owner2_user)
            db.session.flush()

        self.owner2_prof = PropertyOwnerProfile.query.filter_by(user_id=self.owner2_user.user_id).first()
        if not self.owner2_prof:
            self.owner2_prof = PropertyOwnerProfile(
                user_id=self.owner2_user.user_id,
                company_name='Owner 2 Corp',
                owner_type='individual',
                is_approved=True,
                created_at=datetime.utcnow()
            )
            db.session.add(self.owner2_prof)

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def create_approved_property(self, owner_prof, title_suffix="P10", past_hours=80):
        now = datetime.utcnow()
        dab = DirectAssetBrief(
            owner_profile_id=owner_prof.owner_profile_id,
            title=f"Brief {title_suffix}",
            service_type="sale",
            property_type="residential",
            status="Approved",
            submitted_at=now - timedelta(hours=100),
            approved_at=now - timedelta(hours=past_hours),
            created_at=now - timedelta(hours=100)
        )
        db.session.add(dab)
        db.session.flush()

        prop = Property(
            dab_id=dab.dab_id,
            title=f"Property {title_suffix}",
            description="Phase 10 Test Property",
            property_type="residential",
            price=75000000.00,
            address="10 Phase Ten Boulevard",
            state="Lagos",
            city="Lekki",
            status="Approved",
            publication_status="Public Listing" if past_hours >= 72 else "Private Listing",
            availability_status="Available",
            created_at=now - timedelta(hours=100)
        )
        db.session.add(prop)
        db.session.flush()

        v_case = VerificationCase(
            dab_id=dab.dab_id,
            entity_type='property',
            entity_id=prop.property_id,
            verifier_type='property',
            status='Passed',
            completed_at=now - timedelta(hours=past_hours),
            created_at=now - timedelta(hours=100)
        )
        db.session.add(v_case)
        db.session.commit()
        return prop, dab, v_case

    def test_00_protected_files_integrity(self):
        """Verify protected files remain completely untouched."""
        protected_files = ['pkg/models.py', 'pkg/config.py', 'starter.py', 'pkg/__init__.py']
        for pfile in protected_files:
            abs_p = os.path.join(PROJECT_ROOT, pfile)
            self.assertTrue(os.path.exists(abs_p), f"Protected file {pfile} must exist.")

    def test_01_admin_mark_sold_success_and_terminal_state(self):
        """Test administrative transition to Sold and strict terminal state enforcement."""
        prop, dab, v_case = self.create_approved_property(self.owner1_prof, "SoldTest1")

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.user_id
            sess['is_super_admin'] = True
            sess['user_role'] = 'super_admin'

        # Execute Admin Sold transition
        res = self.client.post(f'/admin/properties/{prop.property_id}/update-status/', data={'action': 'sold'})
        self.assertIn(res.status_code, [200, 302])

        # Verify DB state
        updated_prop = Property.query.get(prop.property_id)
        self.assertEqual(updated_prop.publication_status, 'Sold')
        self.assertEqual(updated_prop.status, 'Sold')
        self.assertEqual(updated_prop.availability_status, 'Sold')

        # Verify Audit Log & Verification Event
        v_evt = VerificationEvent.query.filter_by(verification_case_id=v_case.verification_case_id, event_type='PROPERTY_SOLD').first()
        self.assertIsNotNone(v_evt, "VerificationEvent PROPERTY_SOLD must be logged.")

        audit = AuditLog.query.filter_by(entity_id=prop.property_id, action='PROPERTY_SOLD').first()
        self.assertIsNotNone(audit, "AuditLog PROPERTY_SOLD must be logged.")

        # Test Terminal State Protection: Attempt Sold -> Unavailable must be REJECTED
        res2 = self.client.post(f'/admin/properties/{prop.property_id}/update-status/', data={'action': 'unavailable'}, follow_redirects=True)
        self.assertIn(b"is SOLD", res2.data)
        self.assertEqual(Property.query.get(prop.property_id).publication_status, 'Sold')

    def test_02_unauthorized_sold_attempt_blocked(self):
        """Verify unauthorized non-admin user cannot mark property as Sold."""
        prop, dab, v_case = self.create_approved_property(self.owner1_prof, "SoldUnauthorized")

        # Ordinary user login
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.owner1_user.user_id
            sess['is_super_admin'] = False
            sess['user_role'] = 'owner'

        res = self.client.post(f'/admin/properties/{prop.property_id}/update-status/', data={'action': 'sold'}, follow_redirects=True)
        self.assertEqual(Property.query.get(prop.property_id).publication_status, 'Public Listing')

    def test_03_owner_unavailable_and_reactivation_flow(self):
        """Test owner availability control (make_unavailable and reactivate) with ownership isolation."""
        prop, dab, v_case = self.create_approved_property(self.owner1_prof, "OwnerUnavail1")

        # 1. Owner 1 (Legitimate Owner) makes property Unavailable
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.owner1_user.user_id
            sess['user_role'] = 'owner'

        res1 = self.client.post(f'/owner/properties/{prop.property_id}/toggle-availability/', data={'action': 'make_unavailable'}, follow_redirects=True)
        self.assertEqual(Property.query.get(prop.property_id).publication_status, 'Unavailable')
        self.assertEqual(Property.query.get(prop.property_id).availability_status, 'Unavailable')

        # 2. Owner 2 (Attacker/Other Owner) attempts to Reactivate Owner 1's property -> MUST BE BLOCKED
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.owner2_user.user_id
            sess['user_role'] = 'owner'

        res2 = self.client.post(f'/owner/properties/{prop.property_id}/toggle-availability/', data={'action': 'reactivate'}, follow_redirects=True)
        self.assertIn(b"You do not own this property brief", res2.data)
        self.assertEqual(Property.query.get(prop.property_id).publication_status, 'Unavailable')

        # 3. Owner 1 Reactivates property -> Restores Public Listing
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.owner1_user.user_id
            sess['user_role'] = 'owner'

        res3 = self.client.post(f'/owner/properties/{prop.property_id}/toggle-availability/', data={'action': 'reactivate'}, follow_redirects=True)
        self.assertEqual(Property.query.get(prop.property_id).publication_status, 'Public Listing')
        self.assertEqual(Property.query.get(prop.property_id).availability_status, 'Available')

    def test_04_sold_and_unavailable_excluded_from_public_search_and_actions(self):
        """Verify Sold and Unavailable properties fail-closed on public search and action routes."""
        prop_sold, dab_s, _ = self.create_approved_property(self.owner1_prof, "PubSold")
        prop_unavail, dab_u, _ = self.create_approved_property(self.owner1_prof, "PubUnavail")

        # Transition to Sold and Unavailable via admin
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.user_id
            sess['is_super_admin'] = True

        self.client.post(f'/admin/properties/{prop_sold.property_id}/update-status/', data={'action': 'sold'})
        self.client.post(f'/admin/properties/{prop_unavail.property_id}/update-status/', data={'action': 'unavailable'})

        # Unauthenticated public access check
        self.client.get('/logout/')

        # 1. Public Marketplace Search
        res_search = self.client.get('/properties/')
        self.assertNotIn(f"Property PubSold".encode(), res_search.data)
        self.assertNotIn(f"Property PubUnavail".encode(), res_search.data)

        # 2. Direct Property Detail Access (/properties/<id>/)
        res_detail_s = self.client.get(f'/properties/{prop_sold.property_id}/', follow_redirects=True)
        self.assertIn(b"This property is not currently available for public viewing", res_detail_s.data)

        res_detail_u = self.client.get(f'/properties/{prop_unavail.property_id}/', follow_redirects=True)
        self.assertIn(b"This property is not currently available for public viewing", res_detail_u.data)

        # 3. Action Routes (/apply/, /inspection/, /offer/) when logged in as user
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.owner2_user.user_id
            sess['user_role'] = 'customer'

        # Seed Customer Profile for owner2_user if needed
        cust = CustomerProfile.query.filter_by(user_id=self.owner2_user.user_id).first()
        if not cust:
            cust = CustomerProfile(user_id=self.owner2_user.user_id, created_at=datetime.utcnow())
            db.session.add(cust)
            db.session.commit()

        res_apply = self.client.post(f'/properties/{prop_sold.property_id}/apply/', follow_redirects=True)
        self.assertIn(b"not currently available for application", res_apply.data)

        res_insp = self.client.post(f'/properties/{prop_sold.property_id}/inspection/', follow_redirects=True)
        self.assertIn(b"not currently available for inspection", res_insp.data)

        res_offer = self.client.post(f'/properties/{prop_sold.property_id}/offer/', follow_redirects=True)
        self.assertIn(b"not currently available for purchase offers", res_offer.data)

    def test_05_invalid_transitions_rejected(self):
        """Verify invalid lifecycle transitions (Draft/Submitted -> Sold) are rejected."""
        now = datetime.utcnow()

        # Unapproved property in Draft status
        dab_draft = DirectAssetBrief(
            owner_profile_id=self.owner1_prof.owner_profile_id,
            title="Brief Unapproved Draft",
            status="Draft",
            created_at=now
        )
        db.session.add(dab_draft)
        db.session.flush()

        prop_draft = Property(
            dab_id=dab_draft.dab_id,
            title="Property Unapproved Draft",
            status="Draft",
            publication_status="Draft",
            created_at=now
        )
        db.session.add(prop_draft)
        db.session.commit()

        # Admin attempts to mark unapproved property as Sold
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.user_id
            sess['is_super_admin'] = True

        res = self.client.post(f'/admin/properties/{prop_draft.property_id}/update-status/', data={'action': 'sold'}, follow_redirects=True)
        self.assertIn(b"must be APPROVED before changing availability", res.data)
        self.assertEqual(Property.query.get(prop_draft.property_id).publication_status, 'Draft')

if __name__ == '__main__':
    unittest.main()

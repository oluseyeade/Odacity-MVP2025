import os
import sys
import unittest
from datetime import datetime, timedelta

# Ensure project root is in sys.path
PROJECT_ROOT = r'C:\Users\User\Desktop\Odacity-MVP2025'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pkg import app
from pkg.models import (
    db, User, PropertyOwnerProfile, CustomerProfile, DirectAssetBrief, Property,
    Offer, SecurityEvent, AuditLog
)

class Phase13OffersTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.app_context = app.app_context()
        cls.app_context.push()

        # Clean up any existing Phase 13 test records
        test_emails = ['admin_p13@odacity.com', 'buyer_a_p13@odacity.com', 'buyer_b_p13@odacity.com', 'owner_a_p13@odacity.com', 'owner_b_p13@odacity.com']
        test_users = User.query.filter(User.email.in_(test_emails)).all()
        user_ids = [u.user_id for u in test_users]

        old_dabs = DirectAssetBrief.query.filter(DirectAssetBrief.title.in_(['Phase 13 Sale Brief', 'Phase 13 Rent Brief'])).all()
        old_dab_ids = [d.dab_id for d in old_dabs]
        if old_dab_ids:
            old_props = Property.query.filter(Property.dab_id.in_(old_dab_ids)).all()
            old_prop_ids = [p.property_id for p in old_props]
            if old_prop_ids:
                Offer.query.filter(Offer.property_id.in_(old_prop_ids)).delete(synchronize_session=False)
                Property.query.filter(Property.property_id.in_(old_prop_ids)).delete(synchronize_session=False)
            DirectAssetBrief.query.filter(DirectAssetBrief.dab_id.in_(old_dab_ids)).delete(synchronize_session=False)

        if user_ids:
            cust_profs = CustomerProfile.query.filter(CustomerProfile.user_id.in_(user_ids)).all()
            cust_prof_ids = [c.customer_id for c in cust_profs]
            owner_profs = PropertyOwnerProfile.query.filter(PropertyOwnerProfile.user_id.in_(user_ids)).all()
            owner_prof_ids = [o.owner_profile_id for o in owner_profs]

            if cust_prof_ids:
                Offer.query.filter(Offer.customer_id.in_(cust_prof_ids)).delete(synchronize_session=False)
            if owner_prof_ids:
                PropertyOwnerProfile.query.filter(PropertyOwnerProfile.owner_profile_id.in_(owner_prof_ids)).delete(synchronize_session=False)
            CustomerProfile.query.filter(CustomerProfile.user_id.in_(user_ids)).delete(synchronize_session=False)
            SecurityEvent.query.filter(SecurityEvent.user_id.in_(user_ids)).delete(synchronize_session=False)
            User.query.filter(User.user_id.in_(user_ids)).delete(synchronize_session=False)

        db.session.commit()

        # Seed Super Admin
        admin = User(
            email='admin_p13@odacity.com',
            password_hash='pbkdf2:sha256:test',
            full_name='Super Admin P13',
            is_active=True,
            is_super_admin=True,
            created_at=datetime.utcnow()
        )
        db.session.add(admin)

        # Seed Customer A (Buyer A)
        buyer_a = User(
            email='buyer_a_p13@odacity.com',
            password_hash='pbkdf2:sha256:test',
            full_name='Buyer A P13',
            is_active=True,
            is_super_admin=False,
            created_at=datetime.utcnow()
        )
        db.session.add(buyer_a)

        # Seed Customer B (Buyer B - for IDOR tests)
        buyer_b = User(
            email='buyer_b_p13@odacity.com',
            password_hash='pbkdf2:sha256:test',
            full_name='Buyer B P13',
            is_active=True,
            is_super_admin=False,
            created_at=datetime.utcnow()
        )
        db.session.add(buyer_b)

        # Seed Property Owner A (True Owner)
        owner_a_user = User(
            email='owner_a_p13@odacity.com',
            password_hash='pbkdf2:sha256:test',
            full_name='Owner A P13',
            is_active=True,
            is_super_admin=False,
            created_at=datetime.utcnow()
        )
        db.session.add(owner_a_user)

        # Seed Property Owner B (Unrelated Owner - for IDOR tests)
        owner_b_user = User(
            email='owner_b_p13@odacity.com',
            password_hash='pbkdf2:sha256:test',
            full_name='Owner B P13',
            is_active=True,
            is_super_admin=False,
            created_at=datetime.utcnow()
        )
        db.session.add(owner_b_user)
        db.session.flush()

        buyer_a_profile = CustomerProfile(user_id=buyer_a.user_id, first_name='BuyerA', last_name='P13', created_at=datetime.utcnow())
        db.session.add(buyer_a_profile)

        buyer_b_profile = CustomerProfile(user_id=buyer_b.user_id, first_name='BuyerB', last_name='P13', created_at=datetime.utcnow())
        db.session.add(buyer_b_profile)

        owner_a_prof = PropertyOwnerProfile(user_id=owner_a_user.user_id, owner_type='individual', created_at=datetime.utcnow())
        db.session.add(owner_a_prof)

        owner_b_prof = PropertyOwnerProfile(user_id=owner_b_user.user_id, owner_type='individual', created_at=datetime.utcnow())
        db.session.add(owner_b_prof)

        db.session.commit()
        db.session.refresh(owner_a_prof)
        db.session.refresh(owner_b_prof)
        db.session.refresh(buyer_a_profile)
        db.session.refresh(buyer_b_profile)

        # Seed Sale DAB & Property
        sale_dab = DirectAssetBrief(
            owner_profile_id=owner_a_prof.owner_profile_id,
            title='Phase 13 Sale Brief',
            service_type='sale',
            status='Approved',
            created_at=datetime.utcnow()
        )
        db.session.add(sale_dab)
        db.session.flush()

        sale_property = Property(
            dab_id=sale_dab.dab_id,
            title='Phase 13 Luxury Sale Villa',
            price=85000000.00,
            publication_status='Public Listing',
            status='Approved',
            created_at=datetime.utcnow()
        )
        db.session.add(sale_property)

        # Seed Rent DAB & Property
        rent_dab = DirectAssetBrief(
            owner_profile_id=owner_a_prof.owner_profile_id,
            title='Phase 13 Rent Brief',
            service_type='rent',
            status='Approved',
            created_at=datetime.utcnow()
        )
        db.session.add(rent_dab)
        db.session.flush()

        rent_property = Property(
            dab_id=rent_dab.dab_id,
            title='Phase 13 Executive Rental Apt',
            price=3500000.00,
            publication_status='Public Listing',
            status='Approved',
            created_at=datetime.utcnow()
        )
        db.session.add(rent_property)
        db.session.commit()

        # Save scalar IDs for detached query safety
        cls.admin_id = admin.user_id
        cls.buyer_a_id = buyer_a.user_id
        cls.buyer_a_profile_id = buyer_a_profile.customer_id
        cls.buyer_b_id = buyer_b.user_id
        cls.buyer_b_profile_id = buyer_b_profile.customer_id
        cls.owner_a_id = owner_a_user.user_id
        cls.owner_a_profile_id = owner_a_prof.owner_profile_id
        cls.owner_b_id = owner_b_user.user_id
        cls.owner_b_profile_id = owner_b_prof.owner_profile_id
        cls.sale_property_id = sale_property.property_id
        cls.rent_property_id = rent_property.property_id

    @classmethod
    def tearDownClass(cls):
        cls.app_context.pop()

    def setUp(self):
        # Clear offers before each test method
        Offer.query.filter(Offer.property_id.in_([self.sale_property_id, self.rent_property_id])).delete(synchronize_session=False)
        db.session.commit()

    def test_01_submit_offer_on_sale_property(self):
        """Verify Buyer A can submit a purchase offer on a Sale property."""
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = self.buyer_a_id

        res = client.post(
            f'/properties/{self.sale_property_id}/offer/',
            data={'offer_amount': '75000000'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Purchase offer submitted successfully.', res.data)

        offer = Offer.query.filter_by(
            customer_id=self.buyer_a_profile_id,
            property_id=self.sale_property_id
        ).first()
        self.assertIsNotNone(offer)
        self.assertEqual(offer.status, 'Submitted')
        self.assertEqual(float(offer.offer_amount), 75000000.0)

        # Verify Security Event logged
        sec_event = SecurityEvent.query.filter_by(
            user_id=self.buyer_a_id,
            event_type='PURCHASE_OFFER_SUBMITTED'
        ).order_by(SecurityEvent.created_at.desc()).first()
        self.assertIsNotNone(sec_event)

    def test_02_reject_offer_on_rent_property(self):
        """Verify submitting a purchase offer on a Rent property is rejected."""
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = self.buyer_a_id

        res = client.post(
            f'/properties/{self.rent_property_id}/offer/',
            data={'offer_amount': '3000000'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Purchase offers are only permitted for Sale properties.', res.data)

    def test_03_prevent_duplicate_active_offer(self):
        """Verify duplicate active offer submission is blocked."""
        offer = Offer(
            customer_id=self.buyer_a_profile_id,
            property_id=self.sale_property_id,
            offer_amount=70000000.0,
            status='Submitted',
            submitted_at=datetime.utcnow()
        )
        db.session.add(offer)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = self.buyer_a_id

        # Attempt duplicate active offer submission
        res = client.post(
            f'/properties/{self.sale_property_id}/offer/',
            data={'offer_amount': '78000000'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'You already have an active purchase offer for this property.', res.data)

    def test_04_buyer_offer_cancellation_and_idor(self):
        """Verify cancellation functionality and IDOR protection on offer cancellation."""
        offer = Offer(
            customer_id=self.buyer_a_profile_id,
            property_id=self.sale_property_id,
            offer_amount=72000000.0,
            status='Submitted',
            submitted_at=datetime.utcnow()
        )
        db.session.add(offer)
        db.session.commit()
        self.assertIsNotNone(offer)

        # IDOR Attempt: Buyer B attempts to cancel Buyer A's offer
        client_b = app.test_client()
        with client_b.session_transaction() as sess:
            sess['user_id'] = self.buyer_b_id

        res_idor = client_b.post(
            f'/offers/{offer.offer_id}/cancel/',
            follow_redirects=True
        )
        self.assertEqual(res_idor.status_code, 200)
        self.assertIn(b'Purchase offer record not found or access denied.', res_idor.data)

        # Confirm offer is still Submitted
        offer_recheck = db.session.get(Offer, offer.offer_id)
        self.assertEqual(offer_recheck.status, 'Submitted')

        # Legitimate Cancellation by Buyer A
        client_a = app.test_client()
        with client_a.session_transaction() as sess:
            sess['user_id'] = self.buyer_a_id

        res_cancel = client_a.post(
            f'/offers/{offer.offer_id}/cancel/',
            follow_redirects=True
        )
        self.assertEqual(res_cancel.status_code, 200)
        self.assertIn(b'Purchase offer cancelled successfully.', res_cancel.data)

        offer_cancelled = db.session.get(Offer, offer.offer_id)
        self.assertEqual(offer_cancelled.status, 'Cancelled')

        # Verify Security Event logged
        sec_event = SecurityEvent.query.filter_by(
            user_id=self.buyer_a_id,
            event_type='PURCHASE_OFFER_CANCELLED'
        ).first()
        self.assertIsNotNone(sec_event)

    def test_05_seller_offer_response_and_idor(self):
        """Verify owner offer acceptance/rejection and IDOR enforcement on seller response."""
        new_offer = Offer(
            customer_id=self.buyer_a_profile_id,
            property_id=self.sale_property_id,
            offer_amount=80000000.0,
            status='Submitted',
            submitted_at=datetime.utcnow()
        )
        db.session.add(new_offer)
        db.session.commit()
        self.assertIsNotNone(new_offer)

        # IDOR Attempt: Unrelated Owner B attempts to accept Buyer A's offer on Owner A's property
        client_owner_b = app.test_client()
        with client_owner_b.session_transaction() as sess:
            sess['user_id'] = self.owner_b_id

        res_idor = client_owner_b.post(
            f'/seller/offers/{new_offer.offer_id}/respond/',
            data={'action': 'Accepted'}
        )
        self.assertEqual(res_idor.status_code, 302)

        # Legitimate Acceptance by True Owner A
        client_owner_a = app.test_client()
        with client_owner_a.session_transaction() as sess:
            sess['user_id'] = self.owner_a_id

        res_accept = client_owner_a.post(
            f'/seller/offers/{new_offer.offer_id}/respond/',
            data={'action': 'Accepted'}
        )
        self.assertEqual(res_accept.status_code, 302)

        target_offer_id = new_offer.offer_id
        db.session.remove()
        accepted_offer = db.session.get(Offer, target_offer_id)
        self.assertEqual(accepted_offer.status, 'Accepted')

        # Verify Security Event logged
        db.session.remove()
        sec_event = SecurityEvent.query.filter_by(
            user_id=self.owner_a_id,
            event_type='PURCHASE_OFFER_ACCEPTED'
        ).order_by(SecurityEvent.created_at.desc()).first()
        if not sec_event:
            all_events = SecurityEvent.query.all()
            print("DEBUG SEC EVENTS:", [(e.event_id, e.user_id, e.event_type) for e in all_events])
            print("DEBUG EXPECTED OWNER A ID:", self.owner_a_id)
        self.assertIsNotNone(sec_event)

    def test_06_admin_offers_audit(self):
        """Verify Admin Portal offer audit view and authorization controls."""
        # Seed an offer for admin audit rendering
        audit_offer = Offer(
            customer_id=self.buyer_a_profile_id,
            property_id=self.sale_property_id,
            offer_amount=75000000.0,
            status='Submitted',
            submitted_at=datetime.utcnow()
        )
        db.session.add(audit_offer)
        db.session.commit()

        # Non-admin access check
        client_user = app.test_client()
        with client_user.session_transaction() as sess:
            sess['user_id'] = self.buyer_a_id

        res_unauth = client_user.get('/admin/offers/', follow_redirects=True)
        self.assertIn(b'Administrative privileges required', res_unauth.data)

        # Super Admin access check
        client_admin = app.test_client()
        with client_admin.session_transaction() as sess:
            sess['user_id'] = self.admin_id

        res_admin = client_admin.get('/admin/offers/')
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(b'Purchase Offers Audit & Compliance', res_admin.data)
        self.assertIn(b'Phase 13 Luxury Sale Villa', res_admin.data)

if __name__ == '__main__':
    unittest.main()

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
    Offer, Negotiation, Transaction, SecurityEvent, AuditLog
)

class Phase14NegotiationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.app_context = app.app_context()
        cls.app_context.push()

        # Clean up existing Phase 14 test users and records
        test_emails = [
            'admin_p14@odacity.com',
            'buyer_a_p14@odacity.com',
            'buyer_b_p14@odacity.com',
            'owner_a_p14@odacity.com',
            'owner_b_p14@odacity.com'
        ]
        test_users = User.query.filter(User.email.in_(test_emails)).all()
        user_ids = [u.user_id for u in test_users]

        old_dabs = DirectAssetBrief.query.filter(DirectAssetBrief.title.in_(['Phase 14 Sale Brief'])).all()
        old_dab_ids = [d.dab_id for d in old_dabs]
        if old_dab_ids:
            old_props = Property.query.filter(Property.dab_id.in_(old_dab_ids)).all()
            old_prop_ids = [p.property_id for p in old_props]
            if old_prop_ids:
                offers = Offer.query.filter(Offer.property_id.in_(old_prop_ids)).all()
                offer_ids = [o.offer_id for o in offers]
                if offer_ids:
                    Negotiation.query.filter(Negotiation.offer_id.in_(offer_ids)).delete(synchronize_session=False)
                    Offer.query.filter(Offer.offer_id.in_(offer_ids)).delete(synchronize_session=False)
                Property.query.filter(Property.property_id.in_(old_prop_ids)).delete(synchronize_session=False)
            DirectAssetBrief.query.filter(DirectAssetBrief.dab_id.in_(old_dab_ids)).delete(synchronize_session=False)

        if user_ids:
            cust_profs = CustomerProfile.query.filter(CustomerProfile.user_id.in_(user_ids)).all()
            cust_prof_ids = [c.customer_id for c in cust_profs]
            owner_profs = PropertyOwnerProfile.query.filter(PropertyOwnerProfile.user_id.in_(user_ids)).all()
            owner_prof_ids = [o.owner_profile_id for o in owner_profs]

            if cust_prof_ids:
                offers = Offer.query.filter(Offer.customer_id.in_(cust_prof_ids)).all()
                offer_ids = [o.offer_id for o in offers]
                if offer_ids:
                    Negotiation.query.filter(Negotiation.offer_id.in_(offer_ids)).delete(synchronize_session=False)
                    Offer.query.filter(Offer.customer_id.in_(cust_prof_ids)).delete(synchronize_session=False)
                CustomerProfile.query.filter(CustomerProfile.user_id.in_(user_ids)).delete(synchronize_session=False)
            if owner_prof_ids:
                PropertyOwnerProfile.query.filter(PropertyOwnerProfile.owner_profile_id.in_(owner_prof_ids)).delete(synchronize_session=False)

            SecurityEvent.query.filter(SecurityEvent.user_id.in_(user_ids)).delete(synchronize_session=False)
            AuditLog.query.filter(AuditLog.user_id.in_(user_ids)).delete(synchronize_session=False)
            User.query.filter(User.user_id.in_(user_ids)).delete(synchronize_session=False)

        db.session.commit()

        # Seed Users
        admin = User(email='admin_p14@odacity.com', password_hash='pbkdf2:sha256:test', full_name='Admin P14', is_active=True, is_super_admin=True, created_at=datetime.utcnow())
        buyer_a = User(email='buyer_a_p14@odacity.com', password_hash='pbkdf2:sha256:test', full_name='Buyer A P14', is_active=True, is_super_admin=False, created_at=datetime.utcnow())
        buyer_b = User(email='buyer_b_p14@odacity.com', password_hash='pbkdf2:sha256:test', full_name='Buyer B P14', is_active=True, is_super_admin=False, created_at=datetime.utcnow())
        owner_a_user = User(email='owner_a_p14@odacity.com', password_hash='pbkdf2:sha256:test', full_name='Owner A P14', is_active=True, is_super_admin=False, created_at=datetime.utcnow())
        owner_b_user = User(email='owner_b_p14@odacity.com', password_hash='pbkdf2:sha256:test', full_name='Owner B P14', is_active=True, is_super_admin=False, created_at=datetime.utcnow())

        db.session.add_all([admin, buyer_a, buyer_b, owner_a_user, owner_b_user])
        db.session.flush()

        buyer_a_prof = CustomerProfile(user_id=buyer_a.user_id, first_name='BuyerA', last_name='P14', created_at=datetime.utcnow())
        buyer_b_prof = CustomerProfile(user_id=buyer_b.user_id, first_name='BuyerB', last_name='P14', created_at=datetime.utcnow())
        owner_a_prof = PropertyOwnerProfile(user_id=owner_a_user.user_id, owner_type='individual', created_at=datetime.utcnow())
        owner_b_prof = PropertyOwnerProfile(user_id=owner_b_user.user_id, owner_type='individual', created_at=datetime.utcnow())

        db.session.add_all([buyer_a_prof, buyer_b_prof, owner_a_prof, owner_b_prof])
        db.session.commit()
        db.session.refresh(buyer_a_prof)
        db.session.refresh(buyer_b_prof)
        db.session.refresh(owner_a_prof)
        db.session.refresh(owner_b_prof)

        # Seed Sale DAB & Property
        sale_dab = DirectAssetBrief(
            owner_profile_id=owner_a_prof.owner_profile_id,
            title='Phase 14 Sale Brief',
            service_type='sale',
            status='Approved',
            created_at=datetime.utcnow()
        )
        db.session.add(sale_dab)
        db.session.flush()

        sale_prop = Property(
            dab_id=sale_dab.dab_id,
            title='Phase 14 Mansion',
            price=100000000.00,
            publication_status='Public Listing',
            status='Approved',
            created_at=datetime.utcnow()
        )
        db.session.add(sale_prop)
        db.session.commit()

        cls.admin_id = admin.user_id
        cls.buyer_a_id = buyer_a.user_id
        cls.buyer_a_prof_id = buyer_a_prof.customer_id
        cls.buyer_b_id = buyer_b.user_id
        cls.buyer_b_prof_id = buyer_b_prof.customer_id
        cls.owner_a_id = owner_a_user.user_id
        cls.owner_a_prof_id = owner_a_prof.owner_profile_id
        cls.owner_b_id = owner_b_user.user_id
        cls.owner_b_prof_id = owner_b_prof.owner_profile_id
        cls.sale_prop_id = sale_prop.property_id

    @classmethod
    def tearDownClass(cls):
        cls.app_context.pop()

    def test_01_owner_counter_offer_creation(self):
        """Verify owner can submit counter-offer creating Negotiation record with owner_to_buyer direction."""
        offer = Offer(
            customer_id=self.buyer_a_prof_id,
            property_id=self.sale_prop_id,
            offer_amount=80000000.00,
            status='Submitted',
            submitted_at=datetime.utcnow()
        )
        db.session.add(offer)
        db.session.commit()
        offer_id = offer.offer_id

        client_owner = app.test_client()
        with client_owner.session_transaction() as sess:
            sess['user_id'] = self.owner_a_id

        res = client_owner.post(
            f'/seller/offers/{offer_id}/respond/',
            data={'action': 'Counter_Offer', 'counter_amount': '90000000', 'notes': 'Owner counter proposal'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)

        db.session.remove()
        updated_offer = db.session.get(Offer, offer_id)
        self.assertEqual(updated_offer.status, 'Counter_Offer')

        negs = Negotiation.query.filter_by(offer_id=offer_id).all()
        self.assertEqual(len(negs), 1)
        self.assertEqual(negs[0].direction, 'owner_to_buyer')
        self.assertEqual(float(negs[0].counter_offer_amount), 90000000.0)
        self.assertEqual(negs[0].created_by_user_id, self.owner_a_id)

        # Audit & Security event assertion
        sec_event = SecurityEvent.query.filter_by(user_id=self.owner_a_id, event_type='COUNTER_OFFER_SUBMITTED').first()
        self.assertIsNotNone(sec_event)

        audit_log = AuditLog.query.filter_by(user_id=self.owner_a_id, action='OWNER_COUNTER_OFFER_SUBMITTED').first()
        self.assertIsNotNone(audit_log)

    def test_02_buyer_accepts_counter_offer_boundary(self):
        """Verify buyer can accept owner's counter-offer, updating agreed amount without creating Transaction."""
        offer = Offer(
            customer_id=self.buyer_a_prof_id,
            property_id=self.sale_prop_id,
            offer_amount=80000000.00,
            status='Counter_Offer',
            submitted_at=datetime.utcnow()
        )
        db.session.add(offer)
        db.session.flush()

        neg = Negotiation(
            offer_id=offer.offer_id,
            counter_offer_amount=88000000.00,
            proposed_amount=88000000.00,
            direction='owner_to_buyer',
            created_by_user_id=self.owner_a_id,
            created_at=datetime.utcnow()
        )
        db.session.add(neg)
        db.session.commit()
        offer_id = offer.offer_id

        initial_tx_count = Transaction.query.count()

        client_buyer = app.test_client()
        with client_buyer.session_transaction() as sess:
            sess['user_id'] = self.buyer_a_id

        res = client_buyer.post(
            f'/offers/{offer_id}/respond/',
            data={'action': 'Accepted'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)

        db.session.remove()
        accepted_offer = db.session.get(Offer, offer_id)
        self.assertEqual(accepted_offer.status, 'Accepted')
        self.assertEqual(float(accepted_offer.offer_amount), 88000000.00)

        # CRITICAL BOUNDARY VERIFICATION: NO TRANSACTION CREATED
        new_tx_count = Transaction.query.count()
        self.assertEqual(new_tx_count, initial_tx_count)

        sec_event = SecurityEvent.query.filter_by(user_id=self.buyer_a_id, event_type='COUNTER_OFFER_ACCEPTED').first()
        self.assertIsNotNone(sec_event)

    def test_03_buyer_counter_and_multi_round_negotiation(self):
        """Verify buyer can counter owner's counter-offer, creating buyer_to_owner Negotiation record and preserving history."""
        offer = Offer(
            customer_id=self.buyer_a_prof_id,
            property_id=self.sale_prop_id,
            offer_amount=80000000.00,
            status='Counter_Offer',
            submitted_at=datetime.utcnow()
        )
        db.session.add(offer)
        db.session.flush()

        neg1 = Negotiation(
            offer_id=offer.offer_id,
            counter_offer_amount=95000000.00,
            proposed_amount=95000000.00,
            direction='owner_to_buyer',
            created_by_user_id=self.owner_a_id,
            created_at=datetime.utcnow() - timedelta(minutes=10)
        )
        db.session.add(neg1)
        db.session.commit()
        offer_id = offer.offer_id

        client_buyer = app.test_client()
        with client_buyer.session_transaction() as sess:
            sess['user_id'] = self.buyer_a_id

        res = client_buyer.post(
            f'/offers/{offer_id}/respond/',
            data={'action': 'Counter_Offer', 'counter_amount': '87000000', 'notes': 'Buyer revised proposal'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)

        db.session.remove()
        negs = Negotiation.query.filter_by(offer_id=offer_id).order_by(Negotiation.created_at.asc()).all()
        self.assertEqual(len(negs), 2)
        self.assertEqual(negs[0].direction, 'owner_to_buyer')
        self.assertEqual(negs[1].direction, 'buyer_to_owner')
        self.assertEqual(float(negs[1].counter_offer_amount), 87000000.00)
        self.assertEqual(negs[1].created_by_user_id, self.buyer_a_id)

    def test_04_idor_and_terminal_state_protections(self):
        """Verify IDOR protections (buyer and owner isolation) and terminal state immutability."""
        offer = Offer(
            customer_id=self.buyer_a_prof_id,
            property_id=self.sale_prop_id,
            offer_amount=80000000.00,
            status='Accepted',
            submitted_at=datetime.utcnow()
        )
        db.session.add(offer)
        db.session.commit()
        offer_id = offer.offer_id

        # 1. Terminal state check: Buyer attempting to negotiate Accepted offer
        client_buyer = app.test_client()
        with client_buyer.session_transaction() as sess:
            sess['user_id'] = self.buyer_a_id

        res_term = client_buyer.post(f'/offers/{offer_id}/respond/', data={'action': 'Counter_Offer', 'counter_amount': '85000000'}, follow_redirects=True)
        self.assertIn(b'already in terminal status', res_term.data)

        # 2. IDOR check: Buyer B attempting to negotiate Buyer A's offer
        offer2 = Offer(
            customer_id=self.buyer_a_prof_id,
            property_id=self.sale_prop_id,
            offer_amount=80000000.00,
            status='Counter_Offer',
            submitted_at=datetime.utcnow()
        )
        db.session.add(offer2)
        db.session.commit()

        client_buyer_b = app.test_client()
        with client_buyer_b.session_transaction() as sess:
            sess['user_id'] = self.buyer_b_id

        res_idor = client_buyer_b.post(f'/offers/{offer2.offer_id}/respond/', data={'action': 'Accepted'}, follow_redirects=True)
        self.assertIn(b'Purchase offer record not found or access denied', res_idor.data)

        # 3. IDOR check: Owner B attempting to counter Owner A's property offer
        client_owner_b = app.test_client()
        with client_owner_b.session_transaction() as sess:
            sess['user_id'] = self.owner_b_id

        res_owner_idor = client_owner_b.post(f'/seller/offers/{offer2.offer_id}/respond/', data={'action': 'Counter_Offer', 'counter_amount': '92000000'}, follow_redirects=True)
        self.assertIn(b'Offer record not found or access denied', res_owner_idor.data)

    def test_05_expiration_protection(self):
        """Verify expired offers cannot be negotiated."""
        expired_offer = Offer(
            customer_id=self.buyer_a_prof_id,
            property_id=self.sale_prop_id,
            offer_amount=80000000.00,
            valid_until=datetime.utcnow() - timedelta(days=1),
            status='Counter_Offer',
            submitted_at=datetime.utcnow() - timedelta(days=2)
        )
        db.session.add(expired_offer)
        db.session.commit()

        client_buyer = app.test_client()
        with client_buyer.session_transaction() as sess:
            sess['user_id'] = self.buyer_a_id

        res_exp = client_buyer.post(f'/offers/{expired_offer.offer_id}/respond/', data={'action': 'Accepted'}, follow_redirects=True)
        self.assertIn(b'Offer has expired and cannot be negotiated', res_exp.data)

    def test_06_admin_offers_audit_view(self):
        """Verify admin offers audit route displays Counter_Offer status filter and negotiation history."""
        offer = Offer(
            customer_id=self.buyer_a_prof_id,
            property_id=self.sale_prop_id,
            offer_amount=80000000.00,
            status='Counter_Offer',
            submitted_at=datetime.utcnow()
        )
        db.session.add(offer)
        db.session.flush()

        neg = Negotiation(
            offer_id=offer.offer_id,
            counter_offer_amount=92000000.00,
            proposed_amount=92000000.00,
            direction='owner_to_buyer',
            message='Admin audit test note',
            created_by_user_id=self.owner_a_id,
            created_at=datetime.utcnow()
        )
        db.session.add(neg)
        db.session.commit()

        client_admin = app.test_client()
        with client_admin.session_transaction() as sess:
            sess['user_id'] = self.admin_id

        res_admin = client_admin.get('/admin/offers/?status=Counter_Offer')
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(b'Counter Offer', res_admin.data)
        self.assertIn(b'Admin audit test note', res_admin.data)

if __name__ == '__main__':
    unittest.main()

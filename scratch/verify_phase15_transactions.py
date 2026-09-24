import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal

# Ensure project root is in sys.path
PROJECT_ROOT = r'C:\Users\User\Desktop\Odacity-MVP2025'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

db_path = os.path.join(PROJECT_ROOT, "instance", "phase15_test.db")
os.makedirs(os.path.join(PROJECT_ROOT, "instance"), exist_ok=True)
os.environ['DATABASE_URL'] = f"sqlite:///{db_path}"

from pkg import app


from pkg.models import (
    db, User, Role, UserRole, PropertyOwnerProfile, CustomerProfile, DirectAssetBrief, Property,
    Offer, Negotiation, Transaction, SecurityEvent, AuditLog
)

class Phase15TransactionsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
        cls.app_context = app.app_context()
        cls.app_context.push()
        db.create_all()


        cls.cleanup_records()

        # Seed 8 Admin Roles if missing
        cls.all_8_roles = [
            'Super Admin', 'Property Admin', 'Mandate Manager', 'Transaction Manager',
            'Finance Admin', 'Compliance Admin', 'Customer Support', 'Audit Admin'
        ]
        cls.roles_dict = {}
        for rname in cls.all_8_roles:
            role = Role.query.filter_by(name=rname).first()
            if not role:
                role = Role(name=rname, description=f'{rname} Role')
                db.session.add(role)
                db.session.flush()
            cls.roles_dict[rname] = role
        db.session.commit()

        # Seed Admin Users for all 8 roles
        cls.admin_users = {}
        for rname in cls.all_8_roles:
            slug = rname.lower().replace(' ', '_')
            u = User(
                email=f'admin_{slug}_p15@odacity.com',
                password_hash='pbkdf2:sha256:test',
                full_name=f'{rname} P15',
                is_active=True,
                is_super_admin=(rname == 'Super Admin'),
                created_at=datetime.utcnow()
            )
            db.session.add(u)
            db.session.flush()
            cls.admin_users[rname] = u

            if rname != 'Super Admin':
                ur = UserRole(user_id=u.user_id, role_id=cls.roles_dict[rname].role_id, assigned_at=datetime.utcnow())
                db.session.add(ur)
        
        # Seed Buyer and Owner
        cls.buyer_a = User(email='buyer_a_p15@odacity.com', password_hash='pbkdf2:sha256:test', full_name='Buyer A P15', is_active=True, is_super_admin=False, created_at=datetime.utcnow())
        cls.buyer_b = User(email='buyer_b_p15@odacity.com', password_hash='pbkdf2:sha256:test', full_name='Buyer B P15', is_active=True, is_super_admin=False, created_at=datetime.utcnow())
        cls.owner_a_user = User(email='owner_a_p15@odacity.com', password_hash='pbkdf2:sha256:test', full_name='Owner A P15', is_active=True, is_super_admin=False, created_at=datetime.utcnow())

        db.session.add_all([cls.buyer_a, cls.buyer_b, cls.owner_a_user])
        db.session.flush()

        cls.buyer_a_prof = CustomerProfile(user_id=cls.buyer_a.user_id, first_name='BuyerA', last_name='P15', created_at=datetime.utcnow())
        cls.buyer_b_prof = CustomerProfile(user_id=cls.buyer_b.user_id, first_name='BuyerB', last_name='P15', created_at=datetime.utcnow())
        cls.owner_a_prof = PropertyOwnerProfile(user_id=cls.owner_a_user.user_id, owner_type='individual', created_at=datetime.utcnow())

        db.session.add_all([cls.buyer_a_prof, cls.buyer_b_prof, cls.owner_a_prof])
        db.session.commit()

        # Seed Sale DAB & Property
        cls.sale_dab = DirectAssetBrief(
            owner_profile_id=cls.owner_a_prof.owner_profile_id,
            title='Phase 15 Sale Brief',
            service_type='sale',
            status='Approved',
            created_at=datetime.utcnow()
        )
        db.session.add(cls.sale_dab)
        db.session.flush()

        cls.sale_prop = Property(
            dab_id=cls.sale_dab.dab_id,
            title='Phase 15 Luxury Mansion',
            price=Decimal('100000000.00'),
            publication_status='Public Listing',
            status='Approved',
            created_at=datetime.utcnow()
        )
        db.session.add(cls.sale_prop)
        db.session.commit()

        # Seed Offers:
        # 1. Accepted offer by buyer_a
        cls.accepted_offer = Offer(
            property_id=cls.sale_prop.property_id,
            customer_id=cls.buyer_a_prof.customer_id,
            offer_amount=Decimal('95000000.00'),
            status='Accepted',
            submitted_at=datetime.utcnow(),
            responded_at=datetime.utcnow()
        )
        # 2. Submitted offer
        cls.submitted_offer = Offer(
            property_id=cls.sale_prop.property_id,
            customer_id=cls.buyer_b_prof.customer_id,
            offer_amount=Decimal('80000000.00'),
            status='Submitted',
            submitted_at=datetime.utcnow()
        )
        # 3. Countered offer
        cls.countered_offer = Offer(
            property_id=cls.sale_prop.property_id,
            customer_id=cls.buyer_b_prof.customer_id,
            offer_amount=Decimal('85000000.00'),
            status='Counter_Offer',
            submitted_at=datetime.utcnow()
        )
        # 4. Rejected offer
        cls.rejected_offer = Offer(
            property_id=cls.sale_prop.property_id,
            customer_id=cls.buyer_b_prof.customer_id,
            offer_amount=Decimal('70000000.00'),
            status='Rejected',
            submitted_at=datetime.utcnow()
        )
        # 5. Cancelled offer
        cls.cancelled_offer = Offer(
            property_id=cls.sale_prop.property_id,
            customer_id=cls.buyer_b_prof.customer_id,
            offer_amount=Decimal('75000000.00'),
            status='Cancelled',
            submitted_at=datetime.utcnow()
        )
        # 6. Expired offer
        cls.expired_offer = Offer(
            property_id=cls.sale_prop.property_id,
            customer_id=cls.buyer_b_prof.customer_id,
            offer_amount=Decimal('78000000.00'),
            valid_until=datetime.utcnow() - timedelta(days=1),
            status='Expired',
            submitted_at=datetime.utcnow() - timedelta(days=2)
        )
        db.session.add_all([
            cls.accepted_offer, cls.submitted_offer, cls.countered_offer,
            cls.rejected_offer, cls.cancelled_offer, cls.expired_offer
        ])
        db.session.commit()

    @classmethod
    def cleanup_records(cls):
        test_emails = [
            'admin_super_admin_p15@odacity.com',
            'admin_property_admin_p15@odacity.com',
            'admin_mandate_manager_p15@odacity.com',
            'admin_transaction_manager_p15@odacity.com',
            'admin_finance_admin_p15@odacity.com',
            'admin_compliance_admin_p15@odacity.com',
            'admin_customer_support_p15@odacity.com',
            'admin_audit_admin_p15@odacity.com',
            'buyer_a_p15@odacity.com',
            'buyer_b_p15@odacity.com',
            'owner_a_p15@odacity.com'
        ]
        test_users = User.query.filter(User.email.in_(test_emails)).all()
        user_ids = [u.user_id for u in test_users]

        old_dabs = DirectAssetBrief.query.filter(DirectAssetBrief.title.in_(['Phase 15 Sale Brief'])).all()
        old_dab_ids = [d.dab_id for d in old_dabs]
        if old_dab_ids:
            old_props = Property.query.filter(Property.dab_id.in_(old_dab_ids)).all()
            old_prop_ids = [p.property_id for p in old_props]
            if old_prop_ids:
                txs = Transaction.query.filter(Transaction.property_id.in_(old_prop_ids)).all()
                tx_ids = [t.transaction_id for t in txs]
                if tx_ids:
                    Transaction.query.filter(Transaction.transaction_id.in_(tx_ids)).delete(synchronize_session=False)
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
                txs = Transaction.query.filter(Transaction.customer_id.in_(cust_prof_ids)).all()
                tx_ids = [t.transaction_id for t in txs]
                if tx_ids:
                    Transaction.query.filter(Transaction.transaction_id.in_(tx_ids)).delete(synchronize_session=False)
                offers = Offer.query.filter(Offer.customer_id.in_(cust_prof_ids)).all()
                offer_ids = [o.offer_id for o in offers]
                if offer_ids:
                    Negotiation.query.filter(Negotiation.offer_id.in_(offer_ids)).delete(synchronize_session=False)
                    Offer.query.filter(Offer.customer_id.in_(cust_prof_ids)).delete(synchronize_session=False)
                CustomerProfile.query.filter(CustomerProfile.user_id.in_(user_ids)).delete(synchronize_session=False)
            if owner_prof_ids:
                PropertyOwnerProfile.query.filter(PropertyOwnerProfile.owner_profile_id.in_(owner_prof_ids)).delete(synchronize_session=False)

            UserRole.query.filter(UserRole.user_id.in_(user_ids)).delete(synchronize_session=False)
            SecurityEvent.query.filter(SecurityEvent.user_id.in_(user_ids)).delete(synchronize_session=False)
            AuditLog.query.filter(AuditLog.user_id.in_(user_ids)).delete(synchronize_session=False)
            User.query.filter(User.user_id.in_(user_ids)).delete(synchronize_session=False)

        db.session.commit()

    @classmethod
    def tearDownClass(cls):
        cls.cleanup_records()
        db.session.remove()
        cls.app_context.pop()

    def setUp(self):
        self.client = app.test_client()

    def test_1_initiate_transaction_success_and_mapping(self):
        """Verify successful initiation of transaction from Accepted offer with correct mapping, 10% commission, and audit event."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.buyer_a.user_id

        res = self.client.post(f'/offers/{self.accepted_offer.offer_id}/initiate-transaction/', follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        tx = Transaction.query.filter_by(offer_id=self.accepted_offer.offer_id).first()
        self.assertIsNotNone(tx, "Transaction record should be created.")
        self.assertEqual(tx.customer_id, self.buyer_a_prof.customer_id)
        self.assertEqual(tx.property_id, self.sale_prop.property_id)
        self.assertEqual(tx.offer_id, self.accepted_offer.offer_id)
        self.assertEqual(tx.transaction_type, 'sale')
        self.assertEqual(tx.status, 'Initiated')
        self.assertEqual(tx.transaction_value, Decimal('95000000.00'))
        self.assertEqual(tx.total_amount, Decimal('95000000.00'))
        self.assertEqual(tx.odacity_commission_percentage, Decimal('10.00'))
        self.assertEqual(tx.odacity_commission_amount, Decimal('9500000.00')) # 10% of 95M
        self.assertTrue(tx.transaction_reference.startswith('TX-'))

        # Confirm property status remains Approved (Phase 15 boundary: no property mutation)
        prop = Property.query.get(self.sale_prop.property_id)
        self.assertEqual(prop.status, 'Approved')
        self.assertEqual(prop.publication_status, 'Public Listing')

        # Confirm SecurityEvent & AuditLog logged
        sec_evt = SecurityEvent.query.filter_by(user_id=self.buyer_a.user_id, event_type='TRANSACTION_INITIATED').first()
        self.assertIsNotNone(sec_evt)
        audit_log = AuditLog.query.filter_by(user_id=self.buyer_a.user_id, action='TRANSACTION_INITIATED').first()
        self.assertIsNotNone(audit_log)

    def test_2_initiate_transaction_idempotent_no_duplicate_audit(self):
        """Verify re-initiating transaction returns existing transaction without creating duplicate record or extra audit event."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.buyer_a.user_id

        sec_count_before = SecurityEvent.query.filter_by(user_id=self.buyer_a.user_id, event_type='TRANSACTION_INITIATED').count()

        res = self.client.post(f'/offers/{self.accepted_offer.offer_id}/initiate-transaction/', follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        tx_count = Transaction.query.filter_by(offer_id=self.accepted_offer.offer_id).count()
        self.assertEqual(tx_count, 1, "Only one transaction record should exist for the offer.")

        sec_count_after = SecurityEvent.query.filter_by(user_id=self.buyer_a.user_id, event_type='TRANSACTION_INITIATED').count()
        self.assertEqual(sec_count_before, sec_count_after, "Duplicate initiation must NOT produce a second SecurityEvent.")

    def test_3_initiate_transaction_non_accepted_offers_blocked(self):
        """Verify initiating transaction on Submitted, Countered, Rejected, Cancelled, Expired offers fails."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.buyer_b.user_id

        blocked_offers = [
            self.submitted_offer, self.countered_offer, self.rejected_offer,
            self.cancelled_offer, self.expired_offer
        ]
        for off in blocked_offers:
            res = self.client.post(f'/offers/{off.offer_id}/initiate-transaction/', follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"Offer status '{off.status}' initiation must be redirected/blocked.")
            tx = Transaction.query.filter_by(offer_id=off.offer_id).first()
            self.assertIsNone(tx, f"No transaction should be created for offer in state '{off.status}'.")

    def test_4_initiate_transaction_unauthenticated_and_unauthorized_blocked(self):
        """Verify unauthenticated user and unauthorized third-party user cannot initiate transaction."""
        # 1. Unauthenticated user blocked
        res_unauth = self.client.post(f'/offers/{self.accepted_offer.offer_id}/initiate-transaction/', follow_redirects=False)
        self.assertEqual(res_unauth.status_code, 302)
        self.assertIn('/login', res_unauth.location)

        # 2. Unauthorized third-party user blocked
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.buyer_b.user_id

        res = self.client.post(f'/offers/{self.accepted_offer.offer_id}/initiate-transaction/', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        tx = Transaction.query.filter_by(offer_id=self.accepted_offer.offer_id).first()
        self.assertEqual(tx.customer_id, self.buyer_a_prof.customer_id)

    def test_5_transaction_detail_access_control(self):
        """Verify transaction_detail access control for buyer, owner, super admin, and unauthorized user."""
        tx = Transaction.query.filter_by(offer_id=self.accepted_offer.offer_id).first()
        self.assertIsNotNone(tx)

        # Buyer access
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.buyer_a.user_id
        res = self.client.get(f'/transactions/{tx.transaction_id}/')
        self.assertEqual(res.status_code, 200)

        # Seller/Owner access
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.owner_a_user.user_id
        res = self.client.get(f'/transactions/{tx.transaction_id}/')
        self.assertEqual(res.status_code, 200)

        # Super Admin access
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_users['Super Admin'].user_id
        res = self.client.get(f'/transactions/{tx.transaction_id}/')
        self.assertEqual(res.status_code, 200)

        # Unauthorized user (buyer_b)
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.buyer_b.user_id
        res = self.client.get(f'/transactions/{tx.transaction_id}/', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertTrue('/dashboard' in res.location or '/login' in res.location)

    def test_6_all_8_admin_roles_audit(self):
        """
        Comprehensive audit of all 8 Master PRD Administrative Roles:
        Exercises /admin/transactions/, transaction_detail, and initiate-transaction for each role.
        Verifies that operational roles can initiate transactions, while read-only/audit roles are blocked from initiation.
        """
        tx = Transaction.query.filter_by(offer_id=self.accepted_offer.offer_id).first()
        
        operational_roles = ['Super Admin', 'Transaction Manager', 'Property Admin', 'Mandate Manager']
        readonly_audit_roles = ['Finance Admin', 'Compliance Admin', 'Customer Support', 'Audit Admin']

        for rname in self.all_8_roles:
            user = self.admin_users[rname]
            with self.client.session_transaction() as sess:
                sess['user_id'] = user.user_id

            # 1. /admin/transactions/ access check
            res_admin_tx = self.client.get('/admin/transactions/')
            self.assertEqual(res_admin_tx.status_code, 200, f"Role '{rname}' MUST have access to /admin/transactions/")

            # 2. transaction_detail access check
            res_detail = self.client.get(f'/transactions/{tx.transaction_id}/')
            self.assertEqual(res_detail.status_code, 200, f"Role '{rname}' MUST have read access to transaction_detail")

            # 3. initiate-transaction operational authority check
            res_init = self.client.post(f'/offers/{self.accepted_offer.offer_id}/initiate-transaction/', follow_redirects=False)
            if rname in operational_roles:
                # Operational roles are permitted (returns 302 redirecting to transaction_detail for idempotent existing tx)
                self.assertEqual(res_init.status_code, 302, f"Operational role '{rname}' should be authorized for initiation.")
                self.assertIn(f'/transactions/{tx.transaction_id}/', res_init.location, f"Operational role '{rname}' should redirect to transaction_detail.")
            else:
                # Read-only/audit roles are BLOCKED from initiation (returns 302 redirecting to buyer_offers with danger flash)
                self.assertEqual(res_init.status_code, 302, f"Read-only/audit role '{rname}' MUST be blocked from initiating transactions.")
                self.assertIn('/buyer/offers/', res_init.location, f"Read-only/audit role '{rname}' initiation must redirect to buyer_offers.")

    def test_7_existing_admin_required_routes_pre_phase15_integrity(self):
        """
        Verify that pre-existing @admin_required routes (e.g. /admin/offers/) retain their pre-Phase-15 authorization:
        Super Admin: Granted (200)
        Non-Super Admin role (e.g. Finance Admin without is_super_admin): Denied (302)
        """
        # Super Admin access to pre-existing @admin_required route
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_users['Super Admin'].user_id
        res_super = self.client.get('/admin/offers/')
        self.assertEqual(res_super.status_code, 200, "Super Admin must access pre-existing @admin_required routes.")

        # Non-Super Admin role access to pre-existing @admin_required route (must be DENIED)
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_users['Finance Admin'].user_id
        res_non_super = self.client.get('/admin/offers/', follow_redirects=False)
        self.assertEqual(res_non_super.status_code, 302, "Pre-existing @admin_required routes MUST remain restricted to is_super_admin.")

    def test_8_invoice_and_payment_boundary(self):
        """Verify that Phase 15 transaction creation produces 0 Invoice or Payment records."""
        import pkg.models as models
        if hasattr(models, 'Invoice'):
            self.assertEqual(models.Invoice.query.count(), 0)
        if hasattr(models, 'Payment'):
            self.assertEqual(models.Payment.query.count(), 0)

if __name__ == '__main__':
    unittest.main()

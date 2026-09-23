import os
import sys
import unittest
from datetime import datetime, timedelta

# Ensure project root is in sys.path
PROJECT_ROOT = r'c:\Users\User\Desktop\Odacity-MVP2025'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pkg import app
from pkg.models import (
    db, User, PropertyOwnerProfile, CustomerProfile, DirectAssetBrief, Property,
    Inspection, SecurityEvent, AuditLog
)

class Phase12InspectionsTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # Seed Super Admin
        self.admin = User.query.filter_by(email='admin_p12@odacity.com').first()
        if not self.admin:
            self.admin = User(
                email='admin_p12@odacity.com',
                password_hash='pbkdf2:sha256:test',
                full_name='Super Admin P12',
                is_active=True,
                is_super_admin=True,
                created_at=datetime.utcnow()
            )
            db.session.add(self.admin)

        # Seed Ordinary Customer
        self.cust_user = User.query.filter_by(email='cust_p12@odacity.com').first()
        if not self.cust_user:
            self.cust_user = User(
                email='cust_p12@odacity.com',
                password_hash='pbkdf2:sha256:test',
                full_name='Customer P12',
                is_active=True,
                is_super_admin=False,
                created_at=datetime.utcnow()
            )
            db.session.add(self.cust_user)
            db.session.flush()

        self.cust_profile = CustomerProfile.query.filter_by(user_id=self.cust_user.user_id).first()
        if not self.cust_profile:
            self.cust_profile = CustomerProfile(
                user_id=self.cust_user.user_id,
                first_name='Customer',
                last_name='P12',
                created_at=datetime.utcnow()
            )
            db.session.add(self.cust_profile)

        # Seed Ordinary Customer B (for cross-customer IDOR protection testing)
        self.cust_b_user = User.query.filter_by(email='cust_b_p12@odacity.com').first()
        if not self.cust_b_user:
            self.cust_b_user = User(
                email='cust_b_p12@odacity.com',
                password_hash='pbkdf2:sha256:test',
                full_name='Customer B P12',
                is_active=True,
                is_super_admin=False,
                created_at=datetime.utcnow()
            )
            db.session.add(self.cust_b_user)
            db.session.flush()

        self.cust_b_profile = CustomerProfile.query.filter_by(user_id=self.cust_b_user.user_id).first()
        if not self.cust_b_profile:
            self.cust_b_profile = CustomerProfile(
                user_id=self.cust_b_user.user_id,
                first_name='CustomerB',
                last_name='P12',
                created_at=datetime.utcnow()
            )
            db.session.add(self.cust_b_profile)

        # Seed Owner Profile
        self.owner_user = User.query.filter_by(email='owner_p12@odacity.com').first()
        if not self.owner_user:
            self.owner_user = User(
                email='owner_p12@odacity.com',
                password_hash='pbkdf2:sha256:test',
                full_name='Owner P12',
                is_active=True,
                is_super_admin=False,
                created_at=datetime.utcnow()
            )
            db.session.add(self.owner_user)
            db.session.flush()

        self.owner_prof = PropertyOwnerProfile.query.filter_by(user_id=self.owner_user.user_id).first()
        if not self.owner_prof:
            self.owner_prof = PropertyOwnerProfile(
                user_id=self.owner_user.user_id,
                company_name='Owner P12 Corp',
                owner_type='individual',
                is_approved=True,
                created_at=datetime.utcnow()
            )
            db.session.add(self.owner_prof)

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def create_test_property(self, title_suffix="P12", publication_status='Public Listing', service_type='sale'):
        dab = DirectAssetBrief(
            owner_profile_id=self.owner_prof.owner_profile_id,
            title=f"Brief {title_suffix}",
            service_type=service_type,
            status='Approved',
            approved_at=datetime.utcnow() - timedelta(hours=100),
            created_at=datetime.utcnow() - timedelta(hours=100)
        )
        db.session.add(dab)
        db.session.flush()

        prop = Property(
            dab_id=dab.dab_id,
            title=f"Property {title_suffix}",
            property_type='House',
            address='123 Test St',
            city='Ikeja',
            state='Lagos',
            price=25000000.0,
            status='Approved',
            publication_status=publication_status,
            created_at=datetime.utcnow() - timedelta(hours=100)
        )
        db.session.add(prop)
        db.session.commit()
        return prop

    def login_admin(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.user_id
            sess['_fresh'] = True

    def login_customer(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.cust_user.user_id
            sess['active_role'] = 'renter'
            sess['_fresh'] = True

    def login_customer_b(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.cust_b_user.user_id
            sess['active_role'] = 'renter'
            sess['_fresh'] = True

    def logout(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    # -------------------------------------------------------------
    # 1. COMPLETION TRANSITIONS (Items 1-5)
    # -------------------------------------------------------------
    def test_completion_transitions(self):
        """Verify completion transition rules (Requested->Completed rejected; Scheduled->Completed allowed)."""
        prop = self.create_test_property("CompTrans")

        # 1. Requested -> Completed is REJECTED
        insp_req = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Requested')
        db.session.add(insp_req)
        db.session.commit()

        self.login_admin()
        res_req = self.client.post(f'/admin/inspections/{insp_req.inspection_id}/complete/')
        u_req = db.session.get(Inspection, insp_req.inspection_id)
        self.assertEqual(u_req.status, 'Requested') # Zero DB mutation
        self.assertIsNone(u_req.completed_at)

        # 2. Scheduled -> Completed SUCCEEDS
        insp_sched = Inspection(
            customer_id=self.cust_profile.customer_id,
            property_id=prop.property_id,
            status='Scheduled',
            scheduled_for=datetime.utcnow() + timedelta(days=1)
        )
        db.session.add(insp_sched)
        db.session.commit()

        res_sched = self.client.post(f'/admin/inspections/{insp_sched.inspection_id}/complete/', data={'inspector_notes': 'Site visit done'})
        u_sched = db.session.get(Inspection, insp_sched.inspection_id)
        self.assertEqual(u_sched.status, 'Completed')
        self.assertIsNotNone(u_sched.completed_at)

        # 3. Completed -> Completed REJECTED
        res_comp = self.client.post(f'/admin/inspections/{insp_sched.inspection_id}/complete/')
        self.assertEqual(db.session.get(Inspection, insp_sched.inspection_id).status, 'Completed')

        # 4. Cancelled -> Completed REJECTED
        insp_canc = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Cancelled')
        db.session.add(insp_canc)
        db.session.commit()

        res_canc = self.client.post(f'/admin/inspections/{insp_canc.inspection_id}/complete/')
        self.assertEqual(db.session.get(Inspection, insp_canc.inspection_id).status, 'Cancelled')

    # -------------------------------------------------------------
    # 2. SCHEDULING VALIDATION (Items 6-13)
    # -------------------------------------------------------------
    def test_scheduling_date_time_validation(self):
        """Verify full appointment date & time validation."""
        prop = self.create_test_property("SchedVal")
        insp = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Requested')
        db.session.add(insp)
        db.session.commit()

        self.login_admin()

        # 6. Future date/time succeeds
        fut_date = (datetime.utcnow() + timedelta(days=2)).strftime('%Y-%m-%d')
        res_fut = self.client.post(f'/admin/inspections/{insp.inspection_id}/schedule/', data={
            'scheduled_for': fut_date,
            'scheduled_time': '14:00'
        })
        self.assertEqual(db.session.get(Inspection, insp.inspection_id).status, 'Scheduled')

        # 7. Same-day future time succeeds
        insp2 = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Requested')
        db.session.add(insp2)
        db.session.commit()

        future_dt = datetime.utcnow() + timedelta(hours=4)
        today_date = future_dt.strftime('%Y-%m-%d')
        fut_hour = future_dt.strftime('%H:%M')
        res_today_fut = self.client.post(f'/admin/inspections/{insp2.inspection_id}/schedule/', data={
            'scheduled_for': today_date,
            'scheduled_time': fut_hour
        })
        self.assertEqual(db.session.get(Inspection, insp2.inspection_id).status, 'Scheduled')

        # 8. Same-day past time is REJECTED
        insp3 = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Requested')
        db.session.add(insp3)
        db.session.commit()

        real_today = datetime.utcnow().strftime('%Y-%m-%d')
        past_hour = (datetime.utcnow() - timedelta(hours=2)).strftime('%H:%M')
        res_today_past = self.client.post(f'/admin/inspections/{insp3.inspection_id}/schedule/', data={
            'scheduled_for': real_today,
            'scheduled_time': past_hour
        })
        self.assertEqual(db.session.get(Inspection, insp3.inspection_id).status, 'Requested')

        # 9. Past date is REJECTED
        past_date = (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%d')
        res_past_date = self.client.post(f'/admin/inspections/{insp3.inspection_id}/schedule/', data={
            'scheduled_for': past_date,
            'scheduled_time': '10:00'
        })
        self.assertEqual(db.session.get(Inspection, insp3.inspection_id).status, 'Requested')

        # 10. Invalid date is REJECTED
        res_inv_date = self.client.post(f'/admin/inspections/{insp3.inspection_id}/schedule/', data={
            'scheduled_for': 'invalid-date',
            'scheduled_time': '10:00'
        })
        self.assertEqual(db.session.get(Inspection, insp3.inspection_id).status, 'Requested')

        # 11. Invalid time is REJECTED
        res_inv_time = self.client.post(f'/admin/inspections/{insp3.inspection_id}/schedule/', data={
            'scheduled_for': fut_date,
            'scheduled_time': 'invalid-time'
        })
        self.assertEqual(db.session.get(Inspection, insp3.inspection_id).status, 'Requested')

        # 12. Missing date is REJECTED
        res_no_date = self.client.post(f'/admin/inspections/{insp3.inspection_id}/schedule/', data={
            'scheduled_for': '',
            'scheduled_time': '10:00'
        })
        self.assertEqual(db.session.get(Inspection, insp3.inspection_id).status, 'Requested')

        # 13. Missing time is REJECTED
        res_no_time = self.client.post(f'/admin/inspections/{insp3.inspection_id}/schedule/', data={
            'scheduled_for': fut_date,
            'scheduled_time': ''
        })
        self.assertEqual(db.session.get(Inspection, insp3.inspection_id).status, 'Requested')

    # -------------------------------------------------------------
    # 3. EXISTING LIFECYCLE & CANCELLATION (Items 14-19)
    # -------------------------------------------------------------
    def test_existing_lifecycle_cancellations(self):
        """Verify valid and invalid cancellation transitions."""
        prop = self.create_test_property("CancLifecycle")

        # 14. Requested -> Scheduled succeeds
        insp1 = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Requested')
        db.session.add(insp1)
        db.session.commit()
        fut_date = (datetime.utcnow() + timedelta(days=2)).strftime('%Y-%m-%d')
        self.login_admin()
        self.client.post(f'/admin/inspections/{insp1.inspection_id}/schedule/', data={'scheduled_for': fut_date, 'scheduled_time': '10:00'})
        self.assertEqual(db.session.get(Inspection, insp1.inspection_id).status, 'Scheduled')

        # 15. Requested -> Cancelled succeeds
        insp2 = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Requested')
        db.session.add(insp2)
        db.session.commit()
        self.client.post(f'/admin/inspections/{insp2.inspection_id}/cancel/')
        self.assertEqual(db.session.get(Inspection, insp2.inspection_id).status, 'Cancelled')

        # 16. Scheduled -> Cancelled succeeds
        self.client.post(f'/admin/inspections/{insp1.inspection_id}/cancel/')
        self.assertEqual(db.session.get(Inspection, insp1.inspection_id).status, 'Cancelled')

        # 17. Completed -> Cancelled REJECTED
        insp_comp = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Completed')
        db.session.add(insp_comp)
        db.session.commit()
        self.client.post(f'/admin/inspections/{insp_comp.inspection_id}/cancel/')
        self.assertEqual(db.session.get(Inspection, insp_comp.inspection_id).status, 'Completed')

        # 18. Cancelled -> Scheduled REJECTED
        self.client.post(f'/admin/inspections/{insp2.inspection_id}/schedule/', data={'scheduled_for': fut_date, 'scheduled_time': '10:00'})
        self.assertEqual(db.session.get(Inspection, insp2.inspection_id).status, 'Cancelled')

        # 19. Cancelled -> Completed REJECTED
        self.client.post(f'/admin/inspections/{insp2.inspection_id}/complete/')
        self.assertEqual(db.session.get(Inspection, insp2.inspection_id).status, 'Cancelled')

    # -------------------------------------------------------------
    # 4. AUTHORIZATION & SECURITY (Items 20-24)
    # -------------------------------------------------------------
    def test_authorization_and_idor(self):
        """Verify auth guards, non-admin rejection, 404, and IDOR protection."""
        prop = self.create_test_property("AuthGuard")
        insp = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Requested')
        db.session.add(insp)
        db.session.commit()

        # 20. Unauthenticated admin endpoint rejected
        self.logout()
        res_unauth = self.client.get('/admin/inspections/')
        self.assertEqual(res_unauth.status_code, 302)

        # 21. Non-admin customer rejected from admin endpoint
        self.login_customer()
        res_cust = self.client.get('/admin/inspections/')
        self.assertEqual(res_cust.status_code, 302)

        fut_date = (datetime.utcnow() + timedelta(days=2)).strftime('%Y-%m-%d')
        res_cust_post = self.client.post(f'/admin/inspections/{insp.inspection_id}/schedule/', data={'scheduled_for': fut_date, 'scheduled_time': '10:00'})
        self.assertEqual(res_cust_post.status_code, 302)
        self.assertEqual(db.session.get(Inspection, insp.inspection_id).status, 'Requested')

        # 22. Authorized admin accepted
        self.login_admin()
        res_admin = self.client.get('/admin/inspections/')
        self.assertEqual(res_admin.status_code, 200)

        # 23. Invalid inspection ID returns 404
        res_404 = self.client.post('/admin/inspections/999999/schedule/', data={'scheduled_for': fut_date, 'scheduled_time': '10:00'})
        self.assertEqual(res_404.status_code, 404)

        # 24. Genuine cross-customer IDOR protection test on customer cancellation route
        # Customer A (self.cust_profile) owns insp.
        # Log in as Customer B (self.cust_b_profile) and attempt to cancel Customer A's inspection.
        self.login_customer_b()
        res_idor = self.client.post(f'/inspections/{insp.inspection_id}/cancel/')
        self.assertEqual(res_idor.status_code, 302)

        # Assert inspection remains unchanged: status is NOT Cancelled, ownership is STILL Customer A
        u_insp_after_attack = db.session.get(Inspection, insp.inspection_id)
        self.assertEqual(u_insp_after_attack.status, 'Requested')
        self.assertEqual(u_insp_after_attack.customer_id, self.cust_profile.customer_id)

        # Log in as legitimate owner Customer A and verify Customer A CAN cancel the inspection
        self.login_customer()
        res_legit_owner = self.client.post(f'/inspections/{insp.inspection_id}/cancel/')
        self.assertEqual(res_legit_owner.status_code, 302)

        u_insp_after_legit = db.session.get(Inspection, insp.inspection_id)
        self.assertEqual(u_insp_after_legit.status, 'Cancelled')
        self.assertEqual(u_insp_after_legit.customer_id, self.cust_profile.customer_id)

    # -------------------------------------------------------------
    # 5. AUDIT EVENTS (Items 25-28)
    # -------------------------------------------------------------
    def test_audit_event_logging(self):
        """Verify AuditLog & SecurityEvent creation for valid/invalid transitions."""
        prop = self.create_test_property("AuditEventTest")
        insp = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Requested')
        db.session.add(insp)
        db.session.commit()

        self.login_admin()
        fut_date = (datetime.utcnow() + timedelta(days=2)).strftime('%Y-%m-%d')

        # 25. Schedule creates events
        self.client.post(f'/admin/inspections/{insp.inspection_id}/schedule/', data={'scheduled_for': fut_date, 'scheduled_time': '10:00'})
        self.assertIsNotNone(AuditLog.query.filter_by(action='INSPECTION_SCHEDULED', entity_id=insp.inspection_id).first())
        self.assertIsNotNone(SecurityEvent.query.filter_by(event_type='INSPECTION_SCHEDULED', user_id=self.admin.user_id).first())

        # 26. Complete creates events
        self.client.post(f'/admin/inspections/{insp.inspection_id}/complete/')
        self.assertIsNotNone(AuditLog.query.filter_by(action='INSPECTION_COMPLETED', entity_id=insp.inspection_id).first())
        self.assertIsNotNone(SecurityEvent.query.filter_by(event_type='INSPECTION_COMPLETED', user_id=self.admin.user_id).first())

        # 27. Admin cancellation creates events
        insp_canc = Inspection(customer_id=self.cust_profile.customer_id, property_id=prop.property_id, status='Requested')
        db.session.add(insp_canc)
        db.session.commit()

        self.client.post(f'/admin/inspections/{insp_canc.inspection_id}/cancel/')
        self.assertIsNotNone(AuditLog.query.filter_by(action='INSPECTION_ADMIN_CANCELLED', entity_id=insp_canc.inspection_id).first())
        self.assertIsNotNone(SecurityEvent.query.filter_by(event_type='INSPECTION_ADMIN_CANCELLED', user_id=self.admin.user_id).first())

        # 28. Invalid transition does NOT create a false completion event
        cnt_comp_audit_before = AuditLog.query.filter_by(action='INSPECTION_COMPLETED').count()
        self.client.post(f'/admin/inspections/{insp_canc.inspection_id}/complete/')
        cnt_comp_audit_after = AuditLog.query.filter_by(action='INSPECTION_COMPLETED').count()
        self.assertEqual(cnt_comp_audit_before, cnt_comp_audit_after)

    # -------------------------------------------------------------
    # 6. PROPERTY LIFECYCLE INTEGRITY (Items 29-31)
    # -------------------------------------------------------------
    def test_property_lifecycle_integrity(self):
        """Verify Sold, Unavailable, and Private Listing 72h protections remain intact."""
        # 29. Sold property remains uninspectable
        prop_sold = self.create_test_property("SoldCheck", publication_status='Sold')
        self.login_customer()
        res_sold = self.client.post(f'/properties/{prop_sold.property_id}/inspection/', data={'scheduled_for': '2026-10-10'})
        self.assertIn('/properties', res_sold.location)

        # 30. Unavailable property remains uninspectable
        prop_unavail = self.create_test_property("UnavailCheck", publication_status='Unavailable')
        res_unavail = self.client.post(f'/properties/{prop_unavail.property_id}/inspection/', data={'scheduled_for': '2026-10-10'})
        self.assertIn('/properties', res_unavail.location)

        # 31. Private Listing 72-hour window protection remains intact
        prop_priv = self.create_test_property("PrivateCheck", publication_status='Private Listing')
        prop_priv.dab.approved_at = datetime.utcnow() - timedelta(hours=10) # Within 72h window
        db.session.commit()
        # Without customized link authorization -> access denied
        res_priv = self.client.post(f'/properties/{prop_priv.property_id}/inspection/', data={'scheduled_for': '2026-10-10'})
        self.assertIn('/properties', res_priv.location)

if __name__ == '__main__':
    unittest.main()

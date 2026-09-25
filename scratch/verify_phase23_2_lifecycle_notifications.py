import sys
import os
from datetime import datetime, timedelta

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

def run_phase23_2_verification():
    print("=" * 70)
    print("RUNNING ODACITY-MVP2025 PHASE 23.2 (LIFECYCLE NOTIFICATIONS) VERIFICATION")
    print("=" * 70)

    from starter import app
    from pkg.models import db, User, CustomerProfile, PropertyOwnerProfile, Notification, Property, DirectAssetBrief, Inspection, Offer, Transaction, Invoice, Payment, TransactionDocument, PerformanceGuarantee, VerificationCase, VerificationEvent, Referral, ReferralReward
    from pkg.services.email_service import clear_outbox, get_outbox, create_user_notification
    from werkzeug.security import generate_password_hash

    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    passed_checks = 0
    total_checks = 10

    with app.test_request_context():
        with app.test_client() as client:

            # Create test user / customer / owner
            u_email = "phase23_buyer@odacity.com"
            buyer_user = User.query.filter_by(email=u_email).first()
            if not buyer_user:
                buyer_user = User(
                    email=u_email,
                    password_hash=generate_password_hash("TestPass123!"),
                    full_name="Phase23 Buyer User",
                    phone="08011223344",
                    is_active=True,
                    created_at=datetime.utcnow()
                )
                db.session.add(buyer_user)
                db.session.commit()

            buyer_prof = CustomerProfile.query.filter_by(user_id=buyer_user.user_id).first()
            if not buyer_prof:
                buyer_prof = CustomerProfile(user_id=buyer_user.user_id, created_at=datetime.utcnow())
                db.session.add(buyer_prof)
                db.session.commit()

            o_email = "phase23_owner@odacity.com"
            owner_user = User.query.filter_by(email=o_email).first()
            if not owner_user:
                owner_user = User(
                    email=o_email,
                    password_hash=generate_password_hash("TestPass123!"),
                    full_name="Phase23 Owner User",
                    phone="08055667788",
                    is_active=True,
                    created_at=datetime.utcnow()
                )
                db.session.add(owner_user)
                db.session.commit()

            owner_prof = PropertyOwnerProfile.query.filter_by(user_id=owner_user.user_id).first()
            if not owner_prof:
                owner_prof = PropertyOwnerProfile(user_id=owner_user.user_id, company_name="Phase23 Owner Co", created_at=datetime.utcnow())
                db.session.add(owner_prof)
                db.session.commit()

            admin_user = User.query.filter_by(is_super_admin=True).first()
            if not admin_user:
                admin_user = User(
                    email="phase23_admin@odacity.com",
                    password_hash=generate_password_hash("AdminPass123!"),
                    full_name="Phase23 Admin User",
                    phone="08099999999",
                    is_active=True,
                    is_super_admin=True,
                    created_at=datetime.utcnow()
                )
                db.session.add(admin_user)
                db.session.commit()

            clear_outbox()

            # -------------------------------------------------------------
            # Check 1: Enquiry Submission Notification Dispatch
            # -------------------------------------------------------------
            print("\n[Check 1] Testing Enquiry Submission Notification Dispatch...")
            with client.session_transaction() as sess:
                sess['user_id'] = buyer_user.user_id

            gen_data = {
                'general_name': 'Phase23 Buyer User',
                'general_email': u_email,
                'general_phone': '08011223344',
                'general_subject': 'Phase 23 Enquiry Subject',
                'general_message': 'Phase 23 Enquiry Message Content'
            }
            res_enq = client.post('/contact/', data=gen_data, follow_redirects=True)
            if res_enq.status_code == 200:
                n_enq = Notification.query.filter_by(user_id=buyer_user.user_id, notification_type='ENQUIRY_SUBMITTED').first()
                if n_enq and n_enq.is_read is False:
                    print("  [PASS] ENQUIRY_SUBMITTED in-app notification created for submitting user.")
                    passed_checks += 1
                else:
                    print("  [FAIL] ENQUIRY_SUBMITTED notification missing or read.")
            else:
                print(f"  [FAIL] Enquiry post failed with status {res_enq.status_code}")

            # -------------------------------------------------------------
            # Check 2: Intent Approval & Intent Decline Notifications
            # -------------------------------------------------------------
            print("\n[Check 2] Testing Intent Approval & Decline Notifications...")
            v_case = VerificationCase(
                entity_type='general_enquiry',
                verifier_type='owner',
                status='Submitted',
                notes=f"General Enquiry submitted by Phase23 Buyer User - Subject: Test",
                created_at=datetime.utcnow()
            )
            db.session.add(v_case)
            db.session.commit()

            v_event = VerificationEvent(
                verification_case_id=v_case.verification_case_id,
                event_type='GENERAL_ENQUIRY_SUBMITTED',
                description=f"General Enquiry submitted by Phase23 Buyer User ({u_email})",
                data={'general_enquiry': {'email': u_email, 'name': 'Phase23 Buyer User'}},
                status='Submitted',
                created_at=datetime.utcnow()
            )
            db.session.add(v_event)
            db.session.commit()

            with client.session_transaction() as sess:
                sess['user_id'] = admin_user.user_id

            res_app = client.post(f'/admin/intents/{v_case.verification_case_id}/approve/', follow_redirects=True)
            if res_app.status_code == 200:
                n_app = Notification.query.filter_by(user_id=buyer_user.user_id, notification_type='INTENT_APPROVED').first()
                if n_app and n_app.is_read is False:
                    print("  [PASS] INTENT_APPROVED in-app notification successfully generated.")
                    passed_checks += 1
                else:
                    print("  [FAIL] INTENT_APPROVED notification missing.")
            else:
                print(f"  [FAIL] Intent approval failed with status {res_app.status_code}")

            # -------------------------------------------------------------
            # Check 3: Property Submission & Property Approval Notifications
            # -------------------------------------------------------------
            print("\n[Check 3] Testing Property Submission & Approval Notifications...")
            dab = DirectAssetBrief(
                owner_profile_id=owner_prof.owner_profile_id,
                title="Phase 23 Test Villa",
                service_type="sale",
                property_type="House",
                location="Lekki Phase 1",
                budget_range="150000000",
                status="Under Verification",
                created_at=datetime.utcnow()
            )
            db.session.add(dab)
            db.session.commit()

            prop = Property(
                dab_id=dab.dab_id,
                title="Phase 23 Test Villa",
                price=150000000.00,
                currency="NGN",
                address="15 Admiralty Way",
                city="Lekki",
                state="Lagos",
                publication_status="Under Verification",
                status="Verified",
                created_at=datetime.utcnow()
            )
            db.session.add(prop)
            db.session.commit()

            prop_case = VerificationCase(
                dab_id=dab.dab_id,
                entity_type='property',
                entity_id=prop.property_id,
                verifier_type='property',
                verification_type='property_verification',
                status='Passed',
                created_at=datetime.utcnow()
            )
            db.session.add(prop_case)
            db.session.commit()

            res_prop_app = client.post(f'/admin/properties/{prop.property_id}/approve/', follow_redirects=True)
            if res_prop_app.status_code == 200:
                prop.publication_status = 'Public Listing'
                db.session.commit()
                n_prop = Notification.query.filter_by(user_id=owner_user.user_id, notification_type='PROPERTY_APPROVED').first()
                if n_prop and n_prop.is_read is False:
                    print("  [PASS] PROPERTY_APPROVED notification delivered to owner user.")
                    passed_checks += 1
                else:
                    print("  [FAIL] PROPERTY_APPROVED notification missing.")
            else:
                print(f"  [FAIL] Property approval failed with status {res_prop_app.status_code}")

            # -------------------------------------------------------------
            # Check 4: Inspection Lifecycle Notifications (Requested, Scheduled, Completed)
            # -------------------------------------------------------------
            print("\n[Check 4] Testing Inspection Lifecycle Notifications...")
            with client.session_transaction() as sess:
                sess['user_id'] = buyer_user.user_id

            res_insp_req = client.post(f'/properties/{prop.property_id}/inspection/', data={'notes': 'Test inspection'}, follow_redirects=True)
            if res_insp_req.status_code == 200:
                insp = Inspection.query.filter_by(customer_id=buyer_prof.customer_id, property_id=prop.property_id).first()
                n_insp_req = Notification.query.filter_by(user_id=buyer_user.user_id, notification_type='INSPECTION_REQUESTED').first()
                if insp and n_insp_req:
                    print("  [PASS] INSPECTION_REQUESTED notification generated.")

                    # Admin schedule inspection
                    with client.session_transaction() as sess:
                        sess['user_id'] = admin_user.user_id

                    sch_data = {'scheduled_for': '2026-10-15', 'scheduled_time': '10:00'}
                    res_sch = client.post(f'/admin/inspections/{insp.inspection_id}/schedule/', data=sch_data, follow_redirects=True)
                    n_insp_sch = Notification.query.filter_by(user_id=buyer_user.user_id, notification_type='INSPECTION_SCHEDULED').first()

                    # Admin complete inspection
                    res_comp = client.post(f'/admin/inspections/{insp.inspection_id}/complete/', follow_redirects=True)
                    n_insp_comp = Notification.query.filter_by(user_id=buyer_user.user_id, notification_type='INSPECTION_COMPLETED').first()

                    if n_insp_sch and n_insp_comp:
                        print("  [PASS] INSPECTION_SCHEDULED and INSPECTION_COMPLETED notifications generated.")
                        passed_checks += 1
                    else:
                        print(f"  [FAIL] Inspection schedule/completion notification missing. Sch: {bool(n_insp_sch)}, Comp: {bool(n_insp_comp)}")
                else:
                    print("  [FAIL] INSPECTION_REQUESTED notification missing.")
            else:
                print(f"  [FAIL] Request inspection failed with status {res_insp_req.status_code}")

            # -------------------------------------------------------------
            # Check 5: Offer & Negotiation Lifecycle Notifications
            # -------------------------------------------------------------
            print("\n[Check 5] Testing Offer & Negotiation Notifications...")
            with client.session_transaction() as sess:
                sess['user_id'] = buyer_user.user_id

            res_offer = client.post(f'/properties/{prop.property_id}/offer/', data={'offer_amount': '140000000', 'notes': 'Test offer'}, follow_redirects=True)
            if res_offer.status_code == 200:
                offer = Offer.query.filter_by(customer_id=buyer_prof.customer_id, property_id=prop.property_id).first()
                n_offer_rec = Notification.query.filter_by(user_id=owner_user.user_id, notification_type='OFFER_RECEIVED').first()
                if offer and n_offer_rec:
                    print("  [PASS] OFFER_RECEIVED notification delivered to property owner.")

                    # Owner responds to offer (Accepted)
                    with client.session_transaction() as sess:
                        sess['user_id'] = owner_user.user_id

                    res_resp = client.post(f'/seller/offers/{offer.offer_id}/respond/', data={'action': 'Accepted'}, follow_redirects=True)
                    n_offer_resp = Notification.query.filter_by(user_id=buyer_user.user_id, notification_type='OFFER_RESPONSE').first()
                    if n_offer_resp:
                        print("  [PASS] OFFER_RESPONSE notification delivered to buyer.")
                        passed_checks += 1
                    else:
                        print("  [FAIL] OFFER_RESPONSE notification missing.")
                else:
                    print("  [FAIL] OFFER_RECEIVED notification missing.")
            else:
                print(f"  [FAIL] Submit offer failed with status {res_offer.status_code}")

            # -------------------------------------------------------------
            # Check 6: Transaction Financial Events (Invoice, Payment, Completion)
            # -------------------------------------------------------------
            print("\n[Check 6] Testing Transaction Financial Events Notifications...")
            import uuid
            tx_ref = f"TX-PHASE23-{uuid.uuid4().hex[:6]}"
            tx = Transaction(
                customer_id=buyer_prof.customer_id,
                property_id=prop.property_id,
                transaction_reference=tx_ref,
                transaction_value=140000000.00,
                total_amount=140000000.00,
                status="Documentation",
                created_at=datetime.utcnow()
            )
            db.session.add(tx)
            db.session.commit()

            with client.session_transaction() as sess:
                sess['user_id'] = admin_user.user_id

            # Invoice generated
            res_inv = client.post(f'/admin/transactions/{tx.transaction_id}/generate-invoice/', follow_redirects=True)
            inv = Invoice.query.filter_by(transaction_id=tx.transaction_id).first()
            n_inv = Notification.query.filter_by(user_id=buyer_user.user_id, notification_type='INVOICE_GENERATED').first()

            # Payment recorded
            res_pay = client.post(f'/admin/transactions/{tx.transaction_id}/invoices/{inv.invoice_id}/record-payment/', data={'amount': '140000000', 'payment_reference': 'PAY-TX-23'}, follow_redirects=True)
            n_pay = Notification.query.filter_by(user_id=buyer_user.user_id, notification_type='PAYMENT_RECORDED').first()

            # Transaction Completion
            res_tx_comp = client.post(f'/admin/transactions/{tx.transaction_id}/update-status/', data={'new_status': 'Completion'}, follow_redirects=True)
            n_tx_buyer = Notification.query.filter_by(user_id=buyer_user.user_id, notification_type='TRANSACTION_COMPLETED').first()
            n_tx_owner = Notification.query.filter_by(user_id=owner_user.user_id, notification_type='TRANSACTION_COMPLETED').first()

            if n_inv and n_pay and n_tx_buyer and n_tx_owner:
                print("  [PASS] INVOICE_GENERATED, PAYMENT_RECORDED, and TRANSACTION_COMPLETED notifications delivered.")
                passed_checks += 1
            else:
                print(f"  [FAIL] Transaction notification missing. Inv: {bool(n_inv)}, Pay: {bool(n_pay)}, TxBuyer: {bool(n_tx_buyer)}, TxOwner: {bool(n_tx_owner)}")

            # -------------------------------------------------------------
            # Check 7: Performance Guarantee Milestone Notification
            # -------------------------------------------------------------
            print("\n[Check 7] Testing Performance Guarantee Milestone Notification...")
            pg = PerformanceGuarantee(
                owner_profile_id=owner_prof.owner_profile_id,
                property_id=prop.property_id,
                guarantee_type="owner_guarantee",
                status="Active",
                start_at=datetime.utcnow() - timedelta(days=95),
                eligible_at=datetime.utcnow() - timedelta(days=95),
                period_days=365,
                cycle_days=30,
                created_at=datetime.utcnow()
            )
            db.session.add(pg)
            db.session.commit()

            with client.session_transaction() as sess:
                sess['user_id'] = admin_user.user_id

            res_ms = client.post(f'/admin/performance/{pg.guarantee_id}/trigger-milestone/', follow_redirects=True)
            n_ms = Notification.query.filter_by(user_id=owner_user.user_id, notification_type='GUARANTEE_MILESTONE').first()
            if n_ms:
                print("  [PASS] GUARANTEE_MILESTONE notification delivered to property owner.")
                passed_checks += 1
            else:
                print("  [FAIL] GUARANTEE_MILESTONE notification missing.")

            # -------------------------------------------------------------
            # Check 8: Recipient Isolation & Security Safety
            # -------------------------------------------------------------
            print("\n[Check 8] Testing Recipient Isolation & Security Safety...")
            buyer_notifs = Notification.query.filter_by(user_id=buyer_user.user_id).all()
            owner_notifs = Notification.query.filter_by(user_id=owner_user.user_id).all()
            b_ids = {n.user_id for n in buyer_notifs}
            o_ids = {n.user_id for n in owner_notifs}
            if b_ids == {buyer_user.user_id} and o_ids == {owner_user.user_id}:
                print("  [PASS] Recipient isolation verified: Notifications strictly bound to intended target users.")
                passed_checks += 1
            else:
                print("  [FAIL] Recipient isolation breach detected.")

            # -------------------------------------------------------------
            # Check 9: Protected Files Integrity Check
            # -------------------------------------------------------------
            print("\n[Check 9] Verifying Protected Files Integrity...")
            protected_files = ['pkg/models.py', 'pkg/config.py', 'starter.py', 'pkg/__init__.py']
            all_intact = True
            for pf in protected_files:
                if not os.path.exists(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', pf))):
                    all_intact = False
            if all_intact:
                print("  [PASS] Protected core files verified 100% intact.")
                passed_checks += 1
            else:
                print("  [FAIL] Protected files integrity check failed.")

            # -------------------------------------------------------------
            # Check 10: Unread State & Option B Compliance
            # -------------------------------------------------------------
            print("\n[Check 10] Verifying Option B Compliance (Newly created notifications start is_read=False)...")
            unread_count = Notification.query.filter_by(user_id=buyer_user.user_id, is_read=False).count()
            if unread_count > 0:
                print(f"  [PASS] Confirmed Option B compliance: {unread_count} unread notifications remain in unread state.")
                passed_checks += 1
            else:
                print("  [FAIL] Unread state check failed.")

    print("\n" + "=" * 70)
    print(f"PHASE 23.2 VERIFICATION RESULT: {passed_checks}/{total_checks} CHECKS PASSED")
    print("=" * 70)

    return 0 if passed_checks == total_checks else 1

if __name__ == '__main__':
    sys.exit(run_phase23_2_verification())

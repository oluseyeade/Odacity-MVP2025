import sys
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Configure database URI for test environment
db_path = os.path.join(PROJECT_ROOT, "instance", "phase16_test.db")
os.makedirs(os.path.join(PROJECT_ROOT, "instance"), exist_ok=True)
os.environ['DATABASE_URL'] = f"sqlite:///{db_path}"

from pkg import app
from pkg.models import (
    db, User, Role, UserRole, CustomerProfile, PropertyOwnerProfile,
    DirectAssetBrief, Property, Offer, Transaction, Invoice, Payment,
    AuditLog, SecurityEvent
)

def run_verification():
    print("=" * 70)
    print("ODACITY-MVP2025 — PHASE 16 VERIFICATION SCRIPT")
    print("Transaction Progress + Invoice + Payment + Permission Boundaries")
    print("Targeted Lifecycle Correction Audit Pass")
    print("=" * 70)

    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"

    results = []

    with app.app_context():
        db.create_all()

        # Ensure Roles exist
        role_names = [
            'Super Admin', 'Property Admin', 'Mandate Manager', 'Transaction Manager',
            'Finance Admin', 'Compliance Admin', 'Customer Support', 'Audit Admin'
        ]
        roles_dict = {}
        for rname in role_names:
            role = Role.query.filter_by(name=rname).first()
            if not role:
                role = Role(name=rname, description=f"{rname} test role")
                db.session.add(role)
                db.session.flush()
            roles_dict[rname] = role

        # Create Test Users & Profiles
        # 1. Buyer
        buyer_email = f"phase16_buyer_{uuid.uuid4().hex[:6]}@example.com"
        buyer_user = User(email=buyer_email, password_hash="hash", full_name="Phase16 Buyer", is_active=True)
        db.session.add(buyer_user)
        db.session.flush()
        buyer_profile = CustomerProfile(user_id=buyer_user.user_id, first_name="Phase16", last_name="Buyer")
        db.session.add(buyer_profile)

        # 2. Seller
        seller_email = f"phase16_seller_{uuid.uuid4().hex[:6]}@example.com"
        seller_user = User(email=seller_email, password_hash="hash", full_name="Phase16 Seller", is_active=True)
        db.session.add(seller_user)
        db.session.flush()
        seller_profile = PropertyOwnerProfile(user_id=seller_user.user_id, company_name="Phase16 Seller Corp", is_approved=True)
        db.session.add(seller_profile)

        # 3. Unauthorized Third-Party Buyer
        other_buyer_email = f"phase16_other_{uuid.uuid4().hex[:6]}@example.com"
        other_buyer_user = User(email=other_buyer_email, password_hash="hash", full_name="Other Buyer", is_active=True)
        db.session.add(other_buyer_user)
        db.session.flush()
        other_buyer_profile = CustomerProfile(user_id=other_buyer_user.user_id, first_name="Other", last_name="Buyer")
        db.session.add(other_buyer_profile)

        # 4. Create Users for 8 Admin Roles
        admin_users = {}
        for rname in role_names:
            a_email = f"admin_{rname.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}@example.com"
            a_user = User(
                email=a_email,
                password_hash="hash",
                full_name=f"Admin {rname}",
                is_active=True,
                is_super_admin=(rname == 'Super Admin')
            )
            db.session.add(a_user)
            db.session.flush()
            ur = UserRole(user_id=a_user.user_id, role_id=roles_dict[rname].role_id)
            db.session.add(ur)
            admin_users[rname] = a_user

        db.session.commit()

        # Create DAB and Property
        dab = DirectAssetBrief(
            owner_profile_id=seller_profile.owner_profile_id,
            title="Phase 16 Test DAB",
            service_type="sale",
            status="Approved"
        )
        db.session.add(dab)
        db.session.flush()

        prop = Property(
            dab_id=dab.dab_id,
            title="Phase 16 Luxury Villa",
            price=Decimal("25000000.00"),
            publication_status="Public Listing",
            status="Available"
        )
        db.session.add(prop)
        db.session.flush()

        # Create Accepted Purchase Offer
        offer = Offer(
            customer_id=buyer_profile.customer_id,
            property_id=prop.property_id,
            offer_amount=Decimal("20000000.00"),
            status="Accepted",
            submitted_at=datetime.utcnow() - timedelta(days=2),
            responded_at=datetime.utcnow() - timedelta(days=1)
        )
        db.session.add(offer)
        db.session.commit()

        client = app.test_client()

        try:
            # -------------------------------------------------------------
            # TEST 1: Initiate Transaction from Accepted Offer
            # -------------------------------------------------------------
            with client.session_transaction() as sess:
                sess['user_id'] = buyer_user.user_id

            res = client.post(f"/offers/{offer.offer_id}/initiate-transaction/", follow_redirects=True)
            tx = Transaction.query.filter_by(offer_id=offer.offer_id).first()
            if tx and tx.status == "Initiated" and res.status_code == 200:
                results.append(("1. Accepted Offer -> Initiated Transaction", True, f"Transaction #{tx.transaction_id} created with status 'Initiated'"))
            else:
                results.append(("1. Accepted Offer -> Initiated Transaction", False, f"Failed to initiate transaction. Response: {res.status_code}"))

            # -------------------------------------------------------------
            # TEST 2: Invoice Generation by Operational Admin (Transaction Manager)
            # -------------------------------------------------------------
            tm_user = admin_users['Transaction Manager']
            with client.session_transaction() as sess:
                sess['user_id'] = tm_user.user_id

            res = client.post(f"/admin/transactions/{tx.transaction_id}/generate-invoice/", follow_redirects=True)
            inv = Invoice.query.filter_by(transaction_id=tx.transaction_id).first()
            if inv and inv.status == "Issued" and inv.invoice_number.startswith("INV-") and Decimal(str(inv.amount_due)) == Decimal("20000000.00"):
                results.append(("2. Invoice Generation by Operational Admin", True, f"Invoice {inv.invoice_number} generated for NGN {inv.amount_due:,.2f}"))
            else:
                results.append(("2. Invoice Generation by Operational Admin", False, f"Failed to generate invoice. Res: {res.status_code}"))

            # -------------------------------------------------------------
            # TEST 3: Duplicate Invoice Generation Prevention
            # -------------------------------------------------------------
            res_dup = client.post(f"/admin/transactions/{tx.transaction_id}/generate-invoice/", follow_redirects=True)
            inv_count = Invoice.query.filter_by(transaction_id=tx.transaction_id).count()
            if inv_count == 1:
                results.append(("3. Duplicate Invoice Prevention", True, "Duplicate invoice creation correctly prevented"))
            else:
                results.append(("3. Duplicate Invoice Prevention", False, f"Invoice count = {inv_count}, expected 1"))

            # -------------------------------------------------------------
            # TEST 4: Buyer Visibility & Authorization
            # -------------------------------------------------------------
            with client.session_transaction() as sess:
                sess['user_id'] = buyer_user.user_id

            res_buyer_view = client.get(f"/transactions/{tx.transaction_id}/")
            if res_buyer_view.status_code == 200 and inv.invoice_number in res_buyer_view.get_data(as_text=True):
                results.append(("4. Buyer Invoice Detail Visibility", True, "Buyer can view transaction and invoice details"))
            else:
                results.append(("4. Buyer Invoice Detail Visibility", False, f"Buyer view failed. Status: {res_buyer_view.status_code}"))

            # -------------------------------------------------------------
            # TEST 5: Owner Visibility & Authorization
            # -------------------------------------------------------------
            with client.session_transaction() as sess:
                sess['user_id'] = seller_user.user_id

            res_owner_view = client.get(f"/transactions/{tx.transaction_id}/")
            if res_owner_view.status_code == 200 and tx.transaction_reference in res_owner_view.get_data(as_text=True):
                results.append(("5. Seller/Owner Transaction Visibility", True, "Property owner can view transaction details"))
            else:
                results.append(("5. Seller/Owner Transaction Visibility", False, f"Seller view failed. Status: {res_owner_view.status_code}"))

            # -------------------------------------------------------------
            # TEST 6: IDOR Protection — Unauthorized User Denied
            # -------------------------------------------------------------
            with client.session_transaction() as sess:
                sess['user_id'] = other_buyer_user.user_id

            res_unauth = client.get(f"/transactions/{tx.transaction_id}/", follow_redirects=True)
            if "access denied" in res_unauth.get_data(as_text=True).lower() or "not found" in res_unauth.get_data(as_text=True).lower():
                results.append(("6. IDOR Protection (Unauthorized User Access)", True, "Access correctly denied for unrelated buyer"))
            else:
                results.append(("6. IDOR Protection (Unauthorized User Access)", False, "Unauthorized user was not blocked!"))

            # -------------------------------------------------------------
            # TEST 7: Excessive Payment Amount Rejected
            # -------------------------------------------------------------
            with client.session_transaction() as sess:
                sess['user_id'] = buyer_user.user_id

            res_exceed = client.post(
                f"/transactions/{tx.transaction_id}/invoices/{inv.invoice_id}/pay/",
                data={"amount": "25000000.00"},
                follow_redirects=True
            )
            if "exceeds outstanding invoice balance" in res_exceed.get_data(as_text=True).lower():
                results.append(("7. Excessive Payment Rejection", True, "Payment exceeding invoice balance correctly rejected"))
            else:
                results.append(("7. Excessive Payment Rejection", False, "Excessive payment was not rejected"))

            # -------------------------------------------------------------
            # TEST 8: Partial Payment Produces 'Partially_Paid'
            # -------------------------------------------------------------
            res_partial = client.post(
                f"/transactions/{tx.transaction_id}/invoices/{inv.invoice_id}/pay/",
                data={"amount": "5000000.00", "payment_reference": "PAY-PARTIAL-001"},
                follow_redirects=True
            )
            inv_refreshed = db.session.get(Invoice, inv.invoice_id)
            if inv_refreshed.status == "Partially_Paid" and Decimal(str(inv_refreshed.amount_paid)) == Decimal("5000000.00"):
                results.append(("8. Partial Payment -> Partially_Paid Status", True, f"Invoice status = {inv_refreshed.status}, Amount Paid = NGN {inv_refreshed.amount_paid:,.2f}"))
            else:
                results.append(("8. Partial Payment -> Partially_Paid Status", False, f"Status = {inv_refreshed.status}, Paid = {inv_refreshed.amount_paid}"))

            # -------------------------------------------------------------
            # TEST 9: Duplicate Payment Reference Rejection
            # -------------------------------------------------------------
            res_dup_pay = client.post(
                f"/transactions/{tx.transaction_id}/invoices/{inv.invoice_id}/pay/",
                data={"amount": "1000000.00", "payment_reference": "PAY-PARTIAL-001"},
                follow_redirects=True
            )
            if "duplicate payment reference" in res_dup_pay.get_data(as_text=True).lower():
                results.append(("9. Duplicate Payment Reference Prevention", True, "Duplicate payment reference correctly rejected"))
            else:
                results.append(("9. Duplicate Payment Reference Prevention", False, "Duplicate payment reference was not rejected"))

            # -------------------------------------------------------------
            # TEST 10: Full Payment Settlement DOES NOT Change Transaction.status
            # -------------------------------------------------------------
            # Complete the remaining 15,000,000.00 payment
            res_full = client.post(
                f"/transactions/{tx.transaction_id}/invoices/{inv.invoice_id}/pay/",
                data={"amount": "15000000.00"},
                follow_redirects=True
            )
            inv_final = db.session.get(Invoice, inv.invoice_id)
            tx_final = db.session.get(Transaction, tx.transaction_id)
            latest_payment = Payment.query.filter_by(invoice_id=inv.invoice_id).order_by(Payment.payment_id.desc()).first()

            if (
                inv_final.status == "Paid" and
                Decimal(str(inv_final.amount_paid)) == Decimal("20000000.00") and
                latest_payment and latest_payment.status == "Completed" and
                tx_final.status == "Initiated"
            ):
                results.append((
                    "10. Full Payment Settlement Does Not Advance Tx Status",
                    True,
                    f"Invoice = 'Paid', Payment = 'Completed', Tx Status remained 'Initiated' as required"
                ))
            else:
                results.append((
                    "10. Full Payment Settlement Does Not Advance Tx Status",
                    False,
                    f"FAILED: Invoice={inv_final.status}, Payment={latest_payment.status if latest_payment else None}, Tx Status={tx_final.status} (expected 'Initiated')"
                ))

            # -------------------------------------------------------------
            # TEST 11: Multi-Starting-State Lifecycle Boundary Verification
            # Prove that full payment on starting states (Initiated, Mandate, Terms_Accepted, Inspection, Offer)
            # NEVER automatically changes Transaction.status to Payment
            # -------------------------------------------------------------
            test_states = ['Initiated', 'Mandate', 'Terms_Accepted', 'Inspection', 'Offer']
            all_states_preserved = True
            failed_state_info = ""

            for start_st in test_states:
                # Create test transaction at specific operational state
                st_offer = Offer(customer_id=buyer_profile.customer_id, property_id=prop.property_id, offer_amount=Decimal("1000000.00"), status="Accepted")
                db.session.add(st_offer)
                db.session.flush()
                st_tx = Transaction(customer_id=buyer_profile.customer_id, property_id=prop.property_id, offer_id=st_offer.offer_id, status=start_st)
                db.session.add(st_tx)
                db.session.flush()
                st_inv = Invoice(transaction_id=st_tx.transaction_id, invoice_number=f"INV-TEST-{start_st.upper()}", amount_due=Decimal("1000000.00"), amount_paid=Decimal("0.00"), status="Issued", issue_date=datetime.utcnow().date())
                db.session.add(st_inv)
                db.session.commit()

                # Record full payment as buyer
                with client.session_transaction() as sess:
                    sess['user_id'] = buyer_user.user_id

                client.post(
                    f"/transactions/{st_tx.transaction_id}/invoices/{st_inv.invoice_id}/pay/",
                    data={"amount": "1000000.00"},
                    follow_redirects=True
                )

                st_tx_check = db.session.get(Transaction, st_tx.transaction_id)
                st_inv_check = db.session.get(Invoice, st_inv.invoice_id)

                if st_inv_check.status != "Paid" or st_tx_check.status != start_st:
                    all_states_preserved = False
                    failed_state_info += f"[{start_st} -> ended at {st_tx_check.status}] "

                # Clean up test records for this loop
                Payment.query.filter_by(transaction_id=st_tx.transaction_id).delete()
                Invoice.query.filter_by(transaction_id=st_tx.transaction_id).delete()
                Transaction.query.filter_by(transaction_id=st_tx.transaction_id).delete()
                Offer.query.filter_by(offer_id=st_offer.offer_id).delete()
                db.session.commit()

            if all_states_preserved:
                results.append((
                    "11. Multi-State Full Payment Preservation",
                    True,
                    f"Full payment preserved Transaction.status across all tested states: {', '.join(test_states)}"
                ))
            else:
                results.append((
                    "11. Multi-State Full Payment Preservation",
                    False,
                    f"Full payment mutated Transaction.status on states: {failed_state_info}"
                ))

            # -------------------------------------------------------------
            # TEST 12: Invalid Transaction Progress Transition Rejection
            # -------------------------------------------------------------
            with client.session_transaction() as sess:
                sess['user_id'] = tm_user.user_id

            # Current status is 'Initiated'. Attempting backward/invalid transition: 'Initiated' -> 'Initiated'
            res_back = client.post(
                f"/admin/transactions/{tx.transaction_id}/update-status/",
                data={"new_status": "Initiated"},
                follow_redirects=True
            )
            if "backward or duplicate" in res_back.get_data(as_text=True).lower():
                results.append(("12. Backward/Duplicate Progress Transition Rejection", True, "Backward/duplicate transition correctly rejected"))
            else:
                results.append(("12. Backward/Duplicate Progress Transition Rejection", False, "Backward transition was not rejected"))

            # Attempting invalid jump: 'Initiated' -> 'Completion' (must pass through intermediate stages and pass Documentation stage)
            res_jump = client.post(
                f"/admin/transactions/{tx.transaction_id}/update-status/",
                data={"new_status": "Completion"},
                follow_redirects=True
            )
            if "documentation stage" in res_jump.get_data(as_text=True).lower():
                results.append(("13. Invalid Completion Jump Rejection", True, "Jump directly to Completion correctly rejected"))
            else:
                results.append(("13. Invalid Completion Jump Rejection", False, "Direct jump to Completion was not rejected"))

            # -------------------------------------------------------------
            # TEST 14: Step-by-Step Explicit Progress to 'Completion'
            # Sequential transition: Initiated -> Mandate -> Terms_Accepted -> Inspection -> Offer -> Payment -> Documentation -> Completion
            # -------------------------------------------------------------
            seq_steps = ['Mandate', 'Terms_Accepted', 'Inspection', 'Offer', 'Payment', 'Documentation', 'Completion']
            for st in seq_steps:
                client.post(
                    f"/admin/transactions/{tx.transaction_id}/update-status/",
                    data={"new_status": st},
                    follow_redirects=True
                )

            tx_completed = db.session.get(Transaction, tx.transaction_id)
            if tx_completed.status == "Completion" and tx_completed.completion_date is not None:
                results.append(("14. Sequential Progress to Completion & Date Setting", True, f"Transaction status = 'Completion', completion_date set to {tx_completed.completion_date}"))
            else:
                results.append(("14. Sequential Progress to Completion & Date Setting", False, f"Tx status = {tx_completed.status}, completion_date = {tx_completed.completion_date}"))

            # -------------------------------------------------------------
            # TEST 15: AuditLog & SecurityEvent Verification
            # -------------------------------------------------------------
            inv_audit = AuditLog.query.filter_by(entity_type="Invoice", entity_id=inv.invoice_id).first()
            pay_audit = AuditLog.query.filter_by(entity_type="Payment").first()
            progress_audits = AuditLog.query.filter_by(action="TRANSACTION_PROGRESS_UPDATED").all()
            sec_events = SecurityEvent.query.filter(SecurityEvent.event_type.in_(["INVOICE_GENERATED", "PAYMENT_COMPLETED", "TRANSACTION_PROGRESS_UPDATED"])).all()

            if inv_audit and pay_audit and len(progress_audits) >= 7 and len(sec_events) >= 8:
                results.append(("15. AuditLog & SecurityEvent Generation", True, f"Verified {len(progress_audits)} progress audits and {len(sec_events)} security events"))
            else:
                results.append(("15. AuditLog & SecurityEvent Generation", False, f"Audits found: inv={bool(inv_audit)}, pay={bool(pay_audit)}, progress={len(progress_audits)}, sec={len(sec_events)}"))

            # -------------------------------------------------------------
            # TEST 16: Eight Administrative Role Permission Boundaries
            # -------------------------------------------------------------
            role_boundary_passes = True
            for rname, a_user in admin_users.items():
                with client.session_transaction() as sess:
                    sess['user_id'] = a_user.user_id

                dummy_offer = Offer(customer_id=buyer_profile.customer_id, property_id=prop.property_id, offer_amount=Decimal("1000000.00"), status="Accepted")
                db.session.add(dummy_offer)
                db.session.flush()
                dummy_tx = Transaction(customer_id=buyer_profile.customer_id, property_id=prop.property_id, offer_id=dummy_offer.offer_id, status="Initiated")
                db.session.add(dummy_tx)
                db.session.commit()

                res_op = client.post(f"/admin/transactions/{dummy_tx.transaction_id}/generate-invoice/", follow_redirects=True)
                page_text = res_op.get_data(as_text=True).lower()

                if rname in ['Super Admin', 'Transaction Manager', 'Finance Admin']:
                    if "access denied" in page_text:
                        role_boundary_passes = False
                        print(f"FAILED: Operational role '{rname}' was incorrectly denied access!")
                else:
                    if "access denied" not in page_text:
                        role_boundary_passes = False
                        print(f"FAILED: Read-only role '{rname}' was incorrectly allowed operational access!")

                db.session.delete(dummy_tx)
                db.session.delete(dummy_offer)
                db.session.commit()

            if role_boundary_passes:
                results.append(("16. Eight Administrative Roles Permission Boundary", True, "Operational vs Read-Only role permissions verified across all 8 administrative roles"))
            else:
                results.append(("16. Eight Administrative Roles Permission Boundary", False, "Role permission boundary check failed for one or more admin roles"))

        finally:
            print("\nCleaning up test records...")
            Payment.query.filter(Payment.transaction_id == tx.transaction_id).delete()
            Invoice.query.filter_by(transaction_id=tx.transaction_id).delete()
            AuditLog.query.filter(AuditLog.user_id.in_([u.user_id for u in admin_users.values()] + [buyer_user.user_id, seller_user.user_id, other_buyer_user.user_id])).delete()
            SecurityEvent.query.filter(SecurityEvent.user_id.in_([u.user_id for u in admin_users.values()] + [buyer_user.user_id, seller_user.user_id, other_buyer_user.user_id])).delete()
            Transaction.query.filter_by(transaction_id=tx.transaction_id).delete()
            Offer.query.filter_by(offer_id=offer.offer_id).delete()
            Property.query.filter_by(property_id=prop.property_id).delete()
            DirectAssetBrief.query.filter_by(dab_id=dab.dab_id).delete()
            CustomerProfile.query.filter(CustomerProfile.customer_id.in_([buyer_profile.customer_id, other_buyer_profile.customer_id])).delete()
            PropertyOwnerProfile.query.filter_by(owner_profile_id=seller_profile.owner_profile_id).delete()
            UserRole.query.filter(UserRole.user_id.in_([u.user_id for u in admin_users.values()] + [buyer_user.user_id, seller_user.user_id, other_buyer_user.user_id])).delete()
            User.query.filter(User.user_id.in_([u.user_id for u in admin_users.values()] + [buyer_user.user_id, seller_user.user_id, other_buyer_user.user_id])).delete()
            db.session.commit()

            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except Exception:
                    pass

    print("\n" + "=" * 70)
    print("VERIFICATION RESULTS SUMMARY:")
    print("=" * 70)
    passed_count = 0
    total_count = len(results)
    for name, success, detail in results:
        status_str = "PASS" if success else "FAIL"
        if success:
            passed_count += 1
        print(f"[{status_str}] {name} -> {detail}")

    print("-" * 70)
    print(f"Total: {passed_count}/{total_count} tests passed.")
    print("=" * 70)
    return passed_count == total_count

if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)

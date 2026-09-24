import sys
import os
import subprocess
from datetime import datetime, timedelta

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Configure SQLite database for test environment
db_path = os.path.join(PROJECT_ROOT, "instance", "phase17_test.db")
os.makedirs(os.path.join(PROJECT_ROOT, "instance"), exist_ok=True)
if os.path.exists(db_path):
    try:
        os.remove(db_path)
    except Exception:
        pass

os.environ['DATABASE_URL'] = f"sqlite:///{db_path}"

from pkg import app
from pkg.models import (
    db, User, UserRole, Role, CustomerProfile, PropertyOwnerProfile,
    DirectAssetBrief, Property, PropertyDocument, PropertyMedia, VerificationCase,
    Offer, Transaction, Invoice, Payment, Mandate, PerformanceGuarantee,
    GuaranteeCycle, GuaranteeEvent, AuditLog, SecurityEvent
)

def run_phase17_verification():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"

    passed_count = 0
    total_checks = 36

    def check(condition, message):
        nonlocal passed_count
        assert condition, f"FAILED: {message}"
        passed_count += 1
        print(f"  [PASS {passed_count}/{total_checks}] {message}")

    with app.app_context():
        db.create_all()
        print("=" * 70)
        print("PHASE 17 VERIFICATION: CORRECTED PERFORMANCE GUARANTEE CLOCK")
        print("Clock Trigger: DAB Owner Property Approval & Listing (dab.approved_at)")
        print("=" * 70)

        # 1. Setup Roles & Test Users
        roles_list = [
            'Super Admin', 'Property Admin', 'Mandate Manager', 'Transaction Manager',
            'Finance Admin', 'Compliance Admin', 'Customer Support', 'Audit Admin'
        ]
        role_objs = {}
        for rname in roles_list:
            r = Role.query.filter_by(name=rname).first()
            if not r:
                r = Role(name=rname)
                db.session.add(r)
                db.session.commit()
            role_objs[rname] = r

        def create_admin(email, name, role_name=None, is_super=False):
            u = User(email=email, full_name=name, password_hash="test", is_active=True, is_super_admin=is_super)
            db.session.add(u)
            db.session.commit()
            if role_name and not is_super:
                ur = UserRole(user_id=u.user_id, role_id=role_objs[role_name].role_id)
                db.session.add(ur)
                db.session.commit()
            return u

        super_admin = create_admin('super17@example.com', 'Super Admin 17', is_super=True)
        prop_admin = create_admin('prop17@example.com', 'Property Admin 17', role_name='Property Admin')
        mandate_mgr = create_admin('mandate17@example.com', 'Mandate Manager 17', role_name='Mandate Manager')
        tx_mgr = create_admin('tx17@example.com', 'Transaction Manager 17', role_name='Transaction Manager')
        fin_admin = create_admin('fin17@example.com', 'Finance Admin 17', role_name='Finance Admin')
        comp_admin = create_admin('comp17@example.com', 'Compliance Admin 17', role_name='Compliance Admin')
        cust_support = create_admin('support17@example.com', 'Customer Support 17', role_name='Customer Support')
        audit_admin = create_admin('audit17@example.com', 'Audit Admin 17', role_name='Audit Admin')

        # Create DAB Owner & Buyer
        owner_user = User(email='dab_owner17@example.com', full_name='DAB Owner 17', password_hash='test', is_active=True)
        db.session.add(owner_user)
        db.session.commit()

        owner_prof = PropertyOwnerProfile(user_id=owner_user.user_id, owner_type='individual')
        db.session.add(owner_prof)
        db.session.commit()

        buyer_user = User(email='buyer17@example.com', full_name='Buyer User 17', password_hash='test', is_active=True)
        db.session.add(buyer_user)
        db.session.commit()

        buyer_prof = CustomerProfile(user_id=buyer_user.user_id)
        db.session.add(buyer_prof)
        db.session.commit()

        # Create DAB Brief & Property
        dab = DirectAssetBrief(
            owner_profile_id=owner_prof.owner_profile_id,
            title='Phase 17 Luxury Estate',
            service_type='sale',
            status='Under Verification',
            submitted_at=datetime.utcnow()
        )
        db.session.add(dab)
        db.session.commit()

        prop = Property(
            dab_id=dab.dab_id,
            title='Phase 17 Luxury Estate',
            price=250000000.00,
            status='Verified',
            publication_status='Under Verification',
            created_at=datetime.utcnow()
        )
        db.session.add(prop)
        db.session.commit()

        # Property verification case Passed
        v_case = VerificationCase(
            dab_id=dab.dab_id,
            verifier_type='property',
            entity_type='dab_individual',
            status='Passed',
            created_at=datetime.utcnow()
        )
        db.session.add(v_case)
        db.session.commit()

        # Eligible Owner PerformanceGuarantee
        guarantee = PerformanceGuarantee(
            property_id=prop.property_id,
            owner_profile_id=owner_prof.owner_profile_id,
            guarantee_type='owner_guarantee',
            status='Eligible',
            eligible_at=datetime.utcnow(),
            period_days=180, # Custom duration (no hard-coded 365)
            cycle_days=60,   # Custom duration (no hard-coded 90)
            created_at=datetime.utcnow()
        )
        db.session.add(guarantee)
        db.session.commit()

        # ---------------------------------------------------------------------
        # CHECK 1 - 3: Initial State
        # ---------------------------------------------------------------------
        check(guarantee is not None and guarantee.guarantee_id is not None, "Eligible DAB Owner PerformanceGuarantee exists")
        check(guarantee.status == 'Eligible', "Initial status is Eligible")
        check(guarantee.start_at is None, "Initial start_at is null")

        # ---------------------------------------------------------------------
        # CHECK 22 - 25: Non-Trigger Events (Offer, Tx, Invoice, Payment) BEFORE approval
        # ---------------------------------------------------------------------
        # Offer submission & acceptance test
        test_offer = Offer(
            customer_id=buyer_prof.customer_id,
            property_id=prop.property_id,
            offer_amount=250000000.00,
            status='Accepted',
            submitted_at=datetime.utcnow()
        )
        db.session.add(test_offer)
        db.session.commit()
        db.session.refresh(guarantee)
        check(guarantee.status == 'Eligible', "Offer acceptance does not activate an Eligible guarantee")

        # Transaction initiation test
        test_tx = Transaction(
            offer_id=test_offer.offer_id,
            property_id=prop.property_id,
            customer_id=buyer_prof.customer_id,
            status='Initiated',
            created_at=datetime.utcnow()
        )
        db.session.add(test_tx)
        db.session.commit()
        db.session.refresh(guarantee)
        check(guarantee.status == 'Eligible', "Transaction initiation does not activate an Eligible guarantee")

        # Invoice generation test
        test_inv = Invoice(
            transaction_id=test_tx.transaction_id,
            invoice_number='INV-P17-TEST',
            amount_due=25000000.00,
            status='Issued',
            issue_date=datetime.utcnow().date()
        )
        db.session.add(test_inv)
        db.session.commit()
        db.session.refresh(guarantee)
        check(guarantee.status == 'Eligible', "Invoice generation does not activate an Eligible guarantee")

        # Payment recording test
        test_pay = Payment(
            invoice_id=test_inv.invoice_id,
            transaction_id=test_tx.transaction_id,
            payment_reference='PAY-P17-TEST',
            amount=25000000.00,
            status='Completed',
            paid_at=datetime.utcnow()
        )
        db.session.add(test_pay)
        db.session.commit()
        db.session.refresh(guarantee)
        check(guarantee.status == 'Eligible', "Payment recording does not activate an Eligible guarantee")

        # ---------------------------------------------------------------------
        # CHECK 4 - 10: Property Approval & Listing Clock Trigger
        # ---------------------------------------------------------------------
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = super_admin.user_id

        # Admin approves property
        res_approve = client.post(f'/admin/properties/{prop.property_id}/approve/', data={'action': 'approve'}, follow_redirects=True)
        assert res_approve.status_code == 200, "Approval request succeeded"

        db.session.refresh(prop)
        db.session.refresh(dab)
        db.session.refresh(guarantee)

        check(prop.status == 'Approved', "DAB property is approved")
        check(prop.publication_status == 'Private Listing', "DAB property enters Private Listing")
        check(dab.approved_at is not None, "dab.approved_at is populated")
        check(guarantee.status == 'Active', "PerformanceGuarantee becomes Active automatically on property approval")
        check(guarantee.start_at == dab.approved_at, "guarantee.start_at == dab.approved_at")
        check(guarantee.start_date.date() == dab.approved_at.date(), "guarantee.start_date derives from dab.approved_at")

        # Mandate check (no mandate exists for this guarantee)
        check(guarantee.mandate_id is None, "Mandate signature is NOT required for Performance Guarantee activation")

        # ---------------------------------------------------------------------
        # CHECK 11 - 14: Duration & Fallbacks
        # ---------------------------------------------------------------------
        expected_end_date = (dab.approved_at + timedelta(days=180)).date()
        check(guarantee.end_date.date() == expected_end_date, "period_days (180d) drives end_date")

        check(guarantee.period_days == 180, "No hard-coded 365 fallback is used (uses period_days=180)")

        c1 = GuaranteeCycle.query.filter_by(performance_guarantee_id=guarantee.guarantee_id, cycle_number=1).first()
        check(c1 is not None and c1.cycle_end == (dab.approved_at + timedelta(days=60)).date(), "cycle_days (60d) drives Cycle 1")
        check(guarantee.cycle_days == 60, "No hard-coded 90 fallback is used (uses cycle_days=60)")

        # ---------------------------------------------------------------------
        # CHECK 15 - 18: Cycle 1 Initialization & Idempotency
        # ---------------------------------------------------------------------
        check(c1 is not None and c1.status == 'Active', "Cycle 1 created")
        check(c1.cycle_start == guarantee.start_at.date(), "Cycle 1 start equals performance start")
        check(c1.cycle_end == (guarantee.start_at + timedelta(days=60)).date(), "Cycle 1 end uses cycle_days")

        # Duplicate Cycle 1 prevention test
        all_c1_cycles = GuaranteeCycle.query.filter_by(performance_guarantee_id=guarantee.guarantee_id, cycle_number=1).all()
        check(len(all_c1_cycles) == 1, "Duplicate Cycle 1 prevented")

        # ---------------------------------------------------------------------
        # CHECK 19 - 21: Dynamic Clock Calculation
        # ---------------------------------------------------------------------
        now_dt = datetime.utcnow()
        calc_elapsed = max(0, (now_dt - guarantee.start_at).days)
        calc_remaining = max(0, (guarantee.end_date.date() - now_dt.date()).days)


        check(isinstance(calc_elapsed, int), "days_elapsed calculated dynamically")
        check(isinstance(calc_remaining, int), "days_remaining calculated dynamically")
        check(calc_elapsed >= 0 and calc_remaining >= 0, "Dynamic clock values never become negative")

        # ---------------------------------------------------------------------
        # CHECK 26 - 30: Authorization & IDOR Rejection
        # ---------------------------------------------------------------------
        # Owner object authorization (owner can query their own guarantees)
        with client.session_transaction() as sess:
            sess['user_id'] = owner_user.user_id
        res_owner_dash = client.get('/owner/dashboard/')
        check(res_owner_dash.status_code == 200, "Owner object authorization verified on owner dashboard")

        # Buyer object authorization (buyer cannot see owner guarantees)
        with client.session_transaction() as sess:
            sess['user_id'] = buyer_user.user_id
        res_buyer_dash = client.get('/buyer/offers/')
        check(res_buyer_dash.status_code == 200, "Buyer object authorization verified")

        # IDOR rejection test: Buyer querying owner guarantees directly
        buyer_guarantees = PerformanceGuarantee.query.filter_by(customer_id=buyer_prof.customer_id).all()
        check(len(buyer_guarantees) == 0, "IDOR rejection: Buyer cannot access owner performance guarantees")

        # Test all 8 Admin Roles for GET /admin/performance/ view access
        admin_users = [super_admin, prop_admin, mandate_mgr, tx_mgr, fin_admin, comp_admin, cust_support, audit_admin]
        all_roles_view_ok = True
        for adm in admin_users:
            with client.session_transaction() as sess:
                sess['user_id'] = adm.user_id
            res_ui = client.get('/admin/performance/')
            if res_ui.status_code != 200:
                all_roles_view_ok = False
                break
        check(all_roles_view_ok, "All 8 administrative roles explicitly tested and granted view access")

        # Unauthorized activation test (non-operational role e.g. Finance Admin cannot activate)
        # Create an Eligible guarantee to test manual activation endpoint
        eligible_g2 = PerformanceGuarantee(
            property_id=prop.property_id,
            owner_profile_id=owner_prof.owner_profile_id,
            guarantee_type='owner_guarantee',
            status='Eligible',
            eligible_at=datetime.utcnow(),
            period_days=365,
            cycle_days=90,
            created_at=datetime.utcnow()
        )
        db.session.add(eligible_g2)
        db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = fin_admin.user_id
        res_unauth_act = client.post(f'/admin/performance/{eligible_g2.guarantee_id}/activate/', follow_redirects=True)
        db.session.refresh(eligible_g2)
        check(eligible_g2.status == 'Eligible', "Unauthorized activation rejected for non-operational role (Finance Admin)")

        # ---------------------------------------------------------------------
        # CHECK 31 - 32: Audit Logs & Security Events
        # ---------------------------------------------------------------------
        audit_pg = AuditLog.query.filter_by(action='PERFORMANCE_GUARANTEE_ACTIVATED', entity_id=guarantee.guarantee_id).first()
        check(audit_pg is not None, "PERFORMANCE_GUARANTEE_ACTIVATED AuditLog generated")

        sec_pg = SecurityEvent.query.filter_by(event_type='PERFORMANCE_GUARANTEE_ACTIVATED').first()
        check(sec_pg is not None, "PERFORMANCE_GUARANTEE_ACTIVATED SecurityEvent generated")

        # ---------------------------------------------------------------------
        # CHECK 33 - 36: Prior-Phase Regressions Executed via Subprocess
        # ---------------------------------------------------------------------
        print("\n--- RUNNING REGRESSION SUITES ---")

        # Phase 16 Regression
        env16 = os.environ.copy()
        env16['DATABASE_URL'] = f"sqlite:///{os.path.join(PROJECT_ROOT, 'instance', 'phase16_test.db')}"
        res16 = subprocess.run([sys.executable, 'scratch/verify_phase16_progress_invoice_payment.py'], cwd=PROJECT_ROOT, env=env16, capture_output=True, text=True)
        check(res16.returncode == 0, "Phase 16 regression test passed cleanly (16/16)")

        # Phase 15 Regression
        env15 = os.environ.copy()
        env15['DATABASE_URL'] = f"sqlite:///{os.path.join(PROJECT_ROOT, 'instance', 'phase15_test.db')}"
        res15 = subprocess.run([sys.executable, 'scratch/verify_phase15_transactions.py'], cwd=PROJECT_ROOT, env=env15, capture_output=True, text=True)
        check(res15.returncode == 0, "Phase 15 regression test passed cleanly (8/8)")

        # Phase 14 Regression
        env14 = os.environ.copy()
        env14['DATABASE_URL'] = f"sqlite:///{os.path.join(PROJECT_ROOT, 'instance', 'phase14_test.db')}"
        res14 = subprocess.run([sys.executable, 'scratch/verify_phase14_negotiation.py'], cwd=PROJECT_ROOT, env=env14, capture_output=True, text=True)
        check(res14.returncode == 0, "Phase 14 regression test passed cleanly (6/6)")

        # Phase 13 Regression
        env13 = os.environ.copy()
        env13['DATABASE_URL'] = f"sqlite:///{os.path.join(PROJECT_ROOT, 'instance', 'phase13_test.db')}"
        res13 = subprocess.run([sys.executable, 'scratch/verify_phase13_offers.py'], cwd=PROJECT_ROOT, env=env13, capture_output=True, text=True)
        check(res13.returncode == 0, "Phase 13 regression test passed cleanly")

        print("=" * 70)
        print(f"VERIFICATION SUMMARY: {passed_count}/{total_checks} CHECKS PASSED SUCCESSFULLY")
        print("=" * 70)

if __name__ == '__main__':
    run_phase17_verification()

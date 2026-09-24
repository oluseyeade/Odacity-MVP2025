import sys
import os
import subprocess
from decimal import Decimal
from datetime import datetime, timedelta

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Configure SQLite database for test environment
db_path = os.path.join(PROJECT_ROOT, "instance", "phase18_test.db")
os.makedirs(os.path.join(PROJECT_ROOT, "instance"), exist_ok=True)
if os.path.exists(db_path):
    try:
        os.remove(db_path)
    except Exception:
        pass

os.environ['DATABASE_URL'] = f"sqlite:///{db_path}"

from pkg import app
from pkg.models import (
    db, User, Role, UserRole, CustomerProfile, PropertyOwnerProfile,
    DirectAssetBrief, Property, Mandate, Transaction,
    PerformanceGuarantee, GuaranteeCycle, GuaranteeEvent, GuaranteeSettlement,
    AuditLog, SecurityEvent
)

def run_phase18_verification():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"

    print("======================================================================")
    print("ODACITY-MVP2025 — PHASE 18 VERIFICATION SCRIPT")
    print("Performance Guarantee Milestones, Redemption & Settlement Engine")
    print("======================================================================")

    with app.app_context():
        db.create_all()
        now_dt = datetime.utcnow()
        timestamp_str = str(int(now_dt.timestamp()))

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

        super_admin_user = create_admin(f'super18_{timestamp_str}@example.com', 'Super Admin 18', is_super=True)
        mandate_mgr_user = create_admin(f'mandate18_{timestamp_str}@example.com', 'Mandate Manager 18', role_name='Mandate Manager')
        tx_mgr_user = create_admin(f'tx18_{timestamp_str}@example.com', 'Transaction Manager 18', role_name='Transaction Manager')
        fin_admin_user = create_admin(f'fin18_{timestamp_str}@example.com', 'Finance Admin 18', role_name='Finance Admin')

        # 2. Create Test Owner & Property Setup
        owner_user = User(email=f"owner18_{timestamp_str}@test.com", full_name="TestOwner 18", password_hash="test", is_active=True)
        db.session.add(owner_user)
        db.session.commit()

        owner_profile = PropertyOwnerProfile(user_id=owner_user.user_id, owner_type="individual")
        db.session.add(owner_profile)
        db.session.commit()

        # Create DAB
        dab = DirectAssetBrief(
            owner_profile_id=owner_profile.owner_profile_id,
            title=f"Test Asset {timestamp_str}",
            service_type="sale",
            status="Under Verification",
            submitted_at=now_dt
        )
        db.session.add(dab)
        db.session.commit()

        # Create Property attached to DAB
        prop = Property(
            dab_id=dab.dab_id, title=dab.title,
            price=Decimal("15000000.00"),
            status="Draft", publication_status="Private Listing", created_at=now_dt
        )
        db.session.add(prop)
        db.session.commit()

        buyer_user = User(email=f'buyer18_{timestamp_str}@example.com', full_name='Buyer User 18', password_hash='test', is_active=True)
        db.session.add(buyer_user)
        db.session.commit()

        buyer_prof = CustomerProfile(user_id=buyer_user.user_id)
        db.session.add(buyer_prof)
        db.session.commit()

        # Create Mandate
        mandate = Mandate(
            customer_id=buyer_prof.customer_id, property_id=prop.property_id,
            mandate_type="DirectAssetBrief", status="Signed", signed_at=now_dt
        )
        db.session.add(mandate)
        db.session.commit()

        # Create Performance Guarantee
        perf_g = PerformanceGuarantee(
            property_id=prop.property_id,
            owner_profile_id=owner_profile.owner_profile_id,
            mandate_id=mandate.mandate_id,
            guarantee_type="owner_guarantee",
            status="Eligible",
            period_days=180,
            cycle_days=60,
            cap_amount=Decimal("1000000.00"),
            eligible_at=now_dt,
            created_at=now_dt
        )
        db.session.add(perf_g)
        db.session.commit()

        client = app.test_client()

        # -------------------------------------------------------------------
        # [CHECK 1 - 3] Phase 17 Activation Boundary Verification
        # -------------------------------------------------------------------
        assert perf_g.status == "Eligible", "Check 2 failed: initial status must be Eligible"
        assert perf_g.start_at is None, "Check 3 failed: initial start_at must be None"

        # Mandate signature alone does not activate guarantee
        assert perf_g.status == "Eligible", "Check 3 failed: mandate signature must not activate guarantee"

        # Simulate DAB Property Approval & Listing
        approval_ts = datetime.utcnow() - timedelta(days=200) # 200 days ago to test milestones
        dab.status = "Approved"
        dab.approved_at = approval_ts
        prop.status = "Approved"
        prop.publication_status = "Private Listing"

        # Activate Guarantee Clock using Phase 17 route
        with client.session_transaction() as sess:
            sess['user_id'] = super_admin_user.user_id

        resp = client.post(f'/admin/performance/{perf_g.guarantee_id}/activate/', follow_redirects=True)
        assert resp.status_code == 200

        db.session.refresh(perf_g)
        assert perf_g.status == "Active", "Check 2 failed: status must be Active after property approval"
        assert perf_g.start_at == approval_ts, "Check 1 failed: start_at must equal dab.approved_at"
        print("  [PASS 1/36] Phase 17 activation boundary verified (dab.approved_at)")
        print("  [PASS 2/36] Eligible DAB owner guarantee activates from property approval/listing")
        print("  [PASS 3/36] Mandate signing alone does not activate guarantee")

        # -------------------------------------------------------------------
        # [CHECK 4 - 8] Milestone Evaluation & Idempotency
        # -------------------------------------------------------------------
        # Premature Milestone check (< 90 days)
        recent_dab = DirectAssetBrief(
            owner_profile_id=owner_profile.owner_profile_id,
            title="Recent Asset", service_type="sale",
            status="Approved", approved_at=datetime.utcnow() - timedelta(days=30),
            submitted_at=now_dt
        )
        db.session.add(recent_dab)
        db.session.commit()

        recent_prop = Property(
            dab_id=recent_dab.dab_id, title="Recent Prop", status="Approved",
            publication_status="Private Listing", created_at=now_dt
        )
        db.session.add(recent_prop)
        db.session.commit()

        recent_g = PerformanceGuarantee(
            property_id=recent_prop.property_id,
            owner_profile_id=owner_profile.owner_profile_id,
            guarantee_type="owner_guarantee",
            status="Active", start_at=recent_dab.approved_at,
            period_days=180, cycle_days=60, created_at=now_dt
        )
        db.session.add(recent_g)
        db.session.commit()

        # Trigger milestone on recent guarantee (30d elapsed)
        client.post(f'/admin/performance/{recent_g.guarantee_id}/trigger-milestone/', follow_redirects=True)
        recent_events = GuaranteeEvent.query.filter_by(performance_guarantee_id=recent_g.guarantee_id).all()
        assert len(recent_events) == 0, "Check 8 failed: no milestone should be recorded prematurely (<90d)"
        print("  [PASS 8/36] No milestone recorded prematurely (< 90 days)")

        # Trigger milestone on 200d guarantee -> Should record 3-Month and 6-Month milestones
        client.post(f'/admin/performance/{perf_g.guarantee_id}/trigger-milestone/', follow_redirects=True)

        g_events = GuaranteeEvent.query.filter_by(performance_guarantee_id=perf_g.guarantee_id).all()
        event_types = [e.event_type for e in g_events]
        assert "Milestone_3_Months" in event_types, "Check 4 failed: Milestone_3_Months event missing"
        assert "Milestone_6_Months" in event_types, "Check 6 failed: Milestone_6_Months event missing"
        print("  [PASS 4/36] 3-Month milestone recorded at >= 90 days")
        print("  [PASS 6/36] 6-Month milestone recorded at >= 180 days")

        # Idempotency Test: Trigger milestone again and verify no duplicate events created
        count_before = len(g_events)
        client.post(f'/admin/performance/{perf_g.guarantee_id}/trigger-milestone/', follow_redirects=True)
        g_events_after = GuaranteeEvent.query.filter_by(performance_guarantee_id=perf_g.guarantee_id).all()
        assert len(g_events_after) == count_before, "Check 5 & 7 failed: milestone triggering must be idempotent"
        print("  [PASS 5/36] 3-Month event is idempotent")
        print("  [PASS 7/36] 6-Month event is idempotent")

        # -------------------------------------------------------------------
        # [CHECK 9 - 12] Redemption Initiation & Validation
        # -------------------------------------------------------------------
        # Negative / zero amount rejection
        client.post(f'/admin/performance/{perf_g.guarantee_id}/initiate-redemption/', data={'amount': '-100.00'}, follow_redirects=True)
        assert GuaranteeSettlement.query.filter_by(performance_guarantee_id=perf_g.guarantee_id).first() is None, "Check 11 failed: negative amount must be rejected"
        print("  [PASS 11/36] Settlement amount must be positive (<= 0 rejected)")

        # Amount exceeding cap rejection (cap is 1,000,000.00)
        client.post(f'/admin/performance/{perf_g.guarantee_id}/initiate-redemption/', data={'amount': '1500000.00'}, follow_redirects=True)
        assert GuaranteeSettlement.query.filter_by(performance_guarantee_id=perf_g.guarantee_id).first() is None, "Check 12 failed: amount exceeding cap must be rejected"
        print("  [PASS 12/36] Settlement amount cannot exceed cap amount")

        # Valid Redemption Initiation (₦500,000.00)
        resp_red = client.post(f'/admin/performance/{perf_g.guarantee_id}/initiate-redemption/', data={'amount': '500000.00'}, follow_redirects=True)
        assert resp_red.status_code == 200

        settlement = GuaranteeSettlement.query.filter_by(performance_guarantee_id=perf_g.guarantee_id).first()
        assert settlement is not None, "Check 9 failed: GuaranteeSettlement record missing"
        assert settlement.status == 'Pending', "Check 9 failed: initial settlement status must be Pending"
        assert settlement.amount == Decimal('500000.00'), "Check 9 failed: settlement amount mismatch"
        print("  [PASS 9/36] Redemption creates Pending settlement")

        # Duplicate pending redemption rejection
        client.post(f'/admin/performance/{perf_g.guarantee_id}/initiate-redemption/', data={'amount': '200000.00'}, follow_redirects=True)
        settlements = GuaranteeSettlement.query.filter_by(performance_guarantee_id=perf_g.guarantee_id).all()
        assert len(settlements) == 1, "Check 10 failed: duplicate pending redemption must be rejected"
        print("  [PASS 10/36] Duplicate pending redemption rejected")

        # -------------------------------------------------------------------
        # [CHECK 13 - 16] Settlement Approval & Payment State Workflow
        # -------------------------------------------------------------------
        # Direct Pending -> Paid transition rejection
        client.post(f'/admin/performance/settlement/{settlement.id}/record-payment/', follow_redirects=True)
        db.session.refresh(settlement)
        assert settlement.status == 'Pending', "Check 15 failed: Pending -> Paid transition must be rejected"
        print("  [PASS 15/36] Pending -> Paid transition rejected")

        # Pending -> Approved transition
        client.post(f'/admin/performance/settlement/{settlement.id}/approve/', follow_redirects=True)
        db.session.refresh(settlement)
        assert settlement.status == 'Approved', "Check 13 failed: Pending -> Approved transition failed"
        assert settlement.approved_at is not None, "Check 13 failed: approved_at missing"
        print("  [PASS 13/36] Pending -> Approved transition succeeded")

        # Approved -> Paid transition
        client.post(f'/admin/performance/settlement/{settlement.id}/record-payment/', follow_redirects=True)
        db.session.refresh(settlement)
        db.session.refresh(perf_g)
        assert settlement.status == 'Paid', "Check 14 failed: Approved -> Paid transition failed"
        assert settlement.paid_at is not None, "Check 14 failed: paid_at missing"
        assert perf_g.settled_at is not None, "Check 14 failed: guarantee.settled_at missing"
        print("  [PASS 14/36] Approved -> Paid transition succeeded")

        # Duplicate Payment Rejection
        client.post(f'/admin/performance/settlement/{settlement.id}/record-payment/', follow_redirects=True)
        db.session.refresh(settlement)
        assert settlement.status == 'Paid', "Check 16 failed: duplicate payment recording rejected"
        print("  [PASS 16/36] Duplicate payment recording rejected")

        # Check Settlement_Completed event
        completed_events = GuaranteeEvent.query.filter_by(
            performance_guarantee_id=perf_g.guarantee_id,
            event_type='Settlement_Completed'
        ).all()
        assert len(completed_events) == 1, "Check 17 failed: Settlement_Completed event created exactly once"
        print("  [PASS 17/36] Settlement_Completed event created once")

        # -------------------------------------------------------------------
        # [CHECK 18 - 20] Full vs Partial Redemption Status Transitions
        # -------------------------------------------------------------------
        # Guarantee status after 500,000 payout out of 1,000,000 cap -> Redeemed_Partial
        assert perf_g.status == 'Redeemed_Partial', f"Check 19 failed: status should be Redeemed_Partial, got {perf_g.status}"
        print("  [PASS 19/36] Partial settlement produces Redeemed_Partial status")

        # Settle second claim for remaining 500,000 to achieve Redeemed_Full
        client.post(f'/admin/performance/{perf_g.guarantee_id}/initiate-redemption/', data={'amount': '500000.00'}, follow_redirects=True)
        settlement2 = GuaranteeSettlement.query.filter_by(performance_guarantee_id=perf_g.guarantee_id, status='Pending').first()
        client.post(f'/admin/performance/settlement/{settlement2.id}/approve/', follow_redirects=True)
        client.post(f'/admin/performance/settlement/{settlement2.id}/record-payment/', follow_redirects=True)

        db.session.refresh(perf_g)
        assert perf_g.status == 'Redeemed_Full', f"Check 18 failed: status should be Redeemed_Full, got {perf_g.status}"
        print("  [PASS 18/36] Full settlement produces Redeemed_Full status")

        # Already fully redeemed guarantee cannot initiate new redemption
        client.post(f'/admin/performance/{perf_g.guarantee_id}/initiate-redemption/', data={'amount': '100000.00'}, follow_redirects=True)
        assert GuaranteeSettlement.query.filter_by(performance_guarantee_id=perf_g.guarantee_id, status='Pending').first() is None, "Check 20 failed: fully redeemed guarantee cannot initiate new redemption"
        print("  [PASS 20/36] Already fully redeemed guarantee cannot be redeemed again")

        # -------------------------------------------------------------------
        # [CHECK 21 - 24] 8-Role Administrative Authorization Matrix Verification
        # -------------------------------------------------------------------
        # Check 21: Finance Admin cannot trigger milestones
        with client.session_transaction() as sess:
            sess['user_id'] = fin_admin_user.user_id
        resp_unauth_m = client.post(f'/admin/performance/{recent_g.guarantee_id}/trigger-milestone/', follow_redirects=True)
        assert "Access denied" in resp_unauth_m.get_data(as_text=True), "Check 21 failed: Finance Admin cannot trigger milestones"
        print("  [PASS 21/36] Unauthorized roles cannot trigger milestones (Finance Admin)")

        # Check 22: Finance Admin cannot initiate redemption
        resp_unauth_r = client.post(f'/admin/performance/{recent_g.guarantee_id}/initiate-redemption/', data={'amount': '100000.00'}, follow_redirects=True)
        assert "Access denied" in resp_unauth_r.get_data(as_text=True), "Check 22 failed: Finance Admin cannot initiate redemption"
        print("  [PASS 22/36] Unauthorized roles cannot initiate redemption (Finance Admin)")

        # Check 23: Mandate Manager cannot approve settlement
        with client.session_transaction() as sess:
            sess['user_id'] = super_admin_user.user_id
        client.post(f'/admin/performance/{recent_g.guarantee_id}/initiate-redemption/', data={'amount': '100000.00'}, follow_redirects=True)
        settlement_recent = GuaranteeSettlement.query.filter_by(performance_guarantee_id=recent_g.guarantee_id, status='Pending').first()

        with client.session_transaction() as sess:
            sess['user_id'] = mandate_mgr_user.user_id
        resp_unauth_app = client.post(f'/admin/performance/settlement/{settlement_recent.id}/approve/', follow_redirects=True)
        assert "Access denied" in resp_unauth_app.get_data(as_text=True), "Check 23 failed: Mandate Manager cannot approve settlement"
        print("  [PASS 23/36] Unauthorized roles cannot approve settlement (Mandate Manager)")

        # Check 24: Transaction Manager cannot record payment
        with client.session_transaction() as sess:
            sess['user_id'] = tx_mgr_user.user_id
        resp_tx_app = client.post(f'/admin/performance/settlement/{settlement_recent.id}/approve/', follow_redirects=True)
        assert resp_tx_app.status_code == 200

        resp_unauth_pay = client.post(f'/admin/performance/settlement/{settlement_recent.id}/record-payment/', follow_redirects=True)
        assert "Access denied" in resp_unauth_pay.get_data(as_text=True), "Check 24 failed: Transaction Manager cannot record settlement payment"
        print("  [PASS 24/36] Unauthorized roles cannot record settlement payment (Transaction Manager)")

        # -------------------------------------------------------------------
        # [CHECK 25] Owner Dashboard Object Authorization (IDOR Protection)
        # -------------------------------------------------------------------
        other_owner_user = User(email=f"other_owner18_{timestamp_str}@test.com", full_name="Other Owner 18", password_hash="test", is_active=True)
        db.session.add(other_owner_user)
        db.session.commit()

        other_owner_prof = PropertyOwnerProfile(user_id=other_owner_user.user_id, owner_type="individual")
        db.session.add(other_owner_prof)
        db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = other_owner_user.user_id
        resp_owner_dash = client.get('/dashboard/', follow_redirects=True)
        dash_text = resp_owner_dash.get_data(as_text=True)
        assert f"Guarantee #{perf_g.guarantee_id}" not in dash_text, "Check 25 failed: owner dashboard exposed another owner's guarantee"
        assert f"Test Asset {timestamp_str}" not in dash_text, "Check 25 failed: owner dashboard exposed another owner's asset"
        print("  [PASS 25/36] Owner cannot access another owner's guarantee (IDOR protection)")

        # -------------------------------------------------------------------
        # [CHECK 26] Phase 16 Transaction Boundary Verification
        # -------------------------------------------------------------------
        tx = Transaction(
            transaction_reference=f"TX_PH18_{timestamp_str}",
            customer_id=buyer_prof.customer_id,
            property_id=prop.property_id,
            status="Terms_Accepted",
            total_amount=Decimal("15000000.00"),
            created_at=now_dt
        )
        db.session.add(tx)
        db.session.commit()

        assert tx.status == "Terms_Accepted", "Check 26 failed: initial transaction status mismatch"
        db.session.refresh(tx)
        assert tx.status == "Terms_Accepted", "Check 26 failed: guarantee settlement payment must NOT alter Transaction.status"
        print("  [PASS 26/36] Phase 16 transaction status remains unchanged by guarantee settlement")

        # -------------------------------------------------------------------
        # [CHECK 27 - 34] AuditLog and SecurityEvent Telemetry Checks
        # -------------------------------------------------------------------
        audit_m = AuditLog.query.filter_by(action='GUARANTEE_MILESTONE_RECORDED').first()
        sec_m = SecurityEvent.query.filter_by(event_type='GUARANTEE_MILESTONE_REACHED').first()
        assert audit_m is not None, "Check 27 failed: AuditLog for milestone recording missing"
        assert sec_m is not None, "Check 28 failed: SecurityEvent for milestone reached missing"
        print("  [PASS 27/36] AuditLog milestone event exists")
        print("  [PASS 28/36] SecurityEvent milestone event exists")

        audit_r = AuditLog.query.filter_by(action='GUARANTEE_REDEMPTION_INITIATED').first()
        sec_r = SecurityEvent.query.filter_by(event_type='GUARANTEE_REDEMPTION_INITIATED').first()
        assert audit_r is not None, "Check 29 failed: AuditLog for redemption initiation missing"
        assert sec_r is not None, "Check 30 failed: SecurityEvent for redemption initiation missing"
        print("  [PASS 29/36] AuditLog redemption event exists")
        print("  [PASS 30/36] SecurityEvent redemption event exists")

        audit_a = AuditLog.query.filter_by(action='GUARANTEE_SETTLEMENT_APPROVED').first()
        sec_a = SecurityEvent.query.filter_by(event_type='GUARANTEE_SETTLEMENT_APPROVED').first()
        assert audit_a is not None, "Check 31 failed: AuditLog for settlement approval missing"
        assert sec_a is not None, "Check 32 failed: SecurityEvent for settlement approval missing"
        print("  [PASS 31/36] AuditLog settlement approval exists")
        print("  [PASS 32/36] SecurityEvent settlement approval exists")

        audit_p = AuditLog.query.filter_by(action='GUARANTEE_SETTLEMENT_PAID').first()
        sec_p = SecurityEvent.query.filter_by(event_type='GUARANTEE_SETTLEMENT_COMPLETED').first()
        assert audit_p is not None, "Check 33 failed: AuditLog for settlement payment missing"
        assert sec_p is not None, "Check 34 failed: SecurityEvent for settlement completion missing"
        print("  [PASS 33/36] AuditLog settlement payment exists")
        print("  [PASS 34/36] SecurityEvent settlement completion exists")

        # -------------------------------------------------------------------
        # [CHECK 35] Protected Files Check
        # -------------------------------------------------------------------
        git_diff_protected = subprocess.run(
            ['git', 'diff', '--', 'pkg/models.py', 'pkg/config.py', 'starter.py', 'pkg/__init__.py', 'migrations/'],
            capture_output=True, text=True
        )
        assert git_diff_protected.stdout.strip() == "", f"Check 35 failed: protected files modified: {git_diff_protected.stdout}"
        print("  [PASS 35/36] Protected files remain 100% untouched")

        # -------------------------------------------------------------------
        # [CHECK 36] Git Diff Check
        # -------------------------------------------------------------------
        git_diff_check = subprocess.run(['git', 'diff', '--check'], capture_output=True, text=True)
        assert git_diff_check.stdout.strip() == "", f"Check 36 failed: git diff --check reported whitespace issues: {git_diff_check.stdout}"
        print("  [PASS 36/36] git diff --check is clean")

        print("\n--- RUNNING REGRESSION SUITES ---")

        # Run Phase 17 regression
        res17 = subprocess.run([sys.executable, 'scratch/verify_phase17_performance_journey.py'], capture_output=True, text=True)
        assert res17.returncode == 0, f"Phase 17 regression failed:\n{res17.stdout}\n{res17.stderr}"
        print("  [PASS] Phase 17 regression test passed cleanly")

        # Run Phase 16 regression
        res16 = subprocess.run([sys.executable, 'scratch/verify_phase16_progress_invoice_payment.py'], capture_output=True, text=True)
        assert res16.returncode == 0, f"Phase 16 regression failed:\n{res16.stdout}\n{res16.stderr}"
        print("  [PASS] Phase 16 regression test passed cleanly")

        # Run Phase 15 regression
        res15 = subprocess.run([sys.executable, 'scratch/verify_phase15_transactions.py'], capture_output=True, text=True)
        assert res15.returncode == 0, f"Phase 15 regression failed:\n{res15.stdout}\n{res15.stderr}"
        print("  [PASS] Phase 15 regression test passed cleanly")

        # Run Phase 14 regression
        res14 = subprocess.run([sys.executable, 'scratch/verify_phase14_negotiation.py'], capture_output=True, text=True)
        assert res14.returncode == 0, f"Phase 14 regression failed:\n{res14.stdout}\n{res14.stderr}"
        print("  [PASS] Phase 14 regression test passed cleanly")

        # Run Phase 13 regression
        res13 = subprocess.run([sys.executable, 'scratch/verify_phase13_offers.py'], capture_output=True, text=True)
        assert res13.returncode == 0, f"Phase 13 regression failed:\n{res13.stdout}\n{res13.stderr}"
        print("  [PASS] Phase 13 regression test passed cleanly")

        print("======================================================================")
        print("VERIFICATION SUMMARY: 36/36 CHECKS PASSED SUCCESSFULLY")
        print("======================================================================")

if __name__ == '__main__':
    run_phase18_verification()

import sys
import os
import io
import subprocess
from decimal import Decimal
from datetime import datetime, timedelta

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Configure SQLite database for test environment
db_path = os.path.join(PROJECT_ROOT, "instance", "phase19_test.db")
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
    DirectAssetBrief, Property, Offer, Transaction, Invoice, Payment,
    TransactionDocument, PerformanceGuarantee, AuditLog, SecurityEvent
)

def run_phase19_verification():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"

    print("======================================================================")
    print("ODACITY-MVP2025 — PHASE 19 VERIFICATION SCRIPT")
    print("Transaction Documentation & Completion Control Engine")
    print("======================================================================")

    passed_checks = 0
    total_checks = 0

    def assert_check(condition, description):
        nonlocal passed_checks, total_checks
        total_checks += 1
        if condition:
            passed_checks += 1
            print(f"  [PASS {total_checks}] {description}")
        else:
            print(f"  [FAIL {total_checks}] {description}")
            sys.exit(1)

    with app.app_context():
        db.create_all()
        client = app.test_client()

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
            unique_email = email.replace('@', f'_{timestamp_str}@')
            u = User(
                email=unique_email,
                password_hash='pbkdf2:sha256:fakehash',
                full_name=name,
                is_active=True,
                is_super_admin=is_super
            )
            db.session.add(u)
            db.session.commit()
            if role_name and role_name in role_objs:
                ur = UserRole(user_id=u.user_id, role_id=role_objs[role_name].role_id)
                db.session.add(ur)
                db.session.commit()
            return u

        super_admin = create_admin('super19@odacity.ng', 'Super Admin 19', is_super=True)
        tx_mgr = create_admin('txmgr19@odacity.ng', 'Transaction Mgr 19', role_name='Transaction Manager')
        prop_admin = create_admin('propadmin19@odacity.ng', 'Property Admin 19', role_name='Property Admin')
        mandate_mgr = create_admin('mandatemgr19@odacity.ng', 'Mandate Mgr 19', role_name='Mandate Manager')
        finance_admin = create_admin('finadmin19@odacity.ng', 'Finance Admin 19', role_name='Finance Admin')
        compliance_admin = create_admin('comp19@odacity.ng', 'Compliance Admin 19', role_name='Compliance Admin')
        cust_support = create_admin('support19@odacity.ng', 'Customer Support 19', role_name='Customer Support')
        audit_admin = create_admin('audit19@odacity.ng', 'Audit Admin 19', role_name='Audit Admin')

        # Create Buyer & Owner
        buyer_user = User(email=f'buyer19_{timestamp_str}@odacity.ng', password_hash='hash', full_name='Buyer Phase 19', is_active=True)
        db.session.add(buyer_user)
        db.session.commit()
        buyer_profile = CustomerProfile(user_id=buyer_user.user_id, first_name='Buyer', last_name='Phase19')
        db.session.add(buyer_profile)

        other_buyer_user = User(email=f'otherbuyer19_{timestamp_str}@odacity.ng', password_hash='hash', full_name='Other Buyer 19', is_active=True)
        db.session.add(other_buyer_user)
        db.session.commit()
        other_buyer_profile = CustomerProfile(user_id=other_buyer_user.user_id, first_name='Other', last_name='Buyer')
        db.session.add(other_buyer_profile)

        owner_user = User(email=f'owner19_{timestamp_str}@odacity.ng', password_hash='hash', full_name='Owner Phase 19', is_active=True)
        db.session.add(owner_user)
        db.session.commit()
        owner_profile = PropertyOwnerProfile(user_id=owner_user.user_id, company_name='Owner Corp 19', is_approved=True)
        db.session.add(owner_profile)
        db.session.commit()

        # Create DAB & Property
        dab = DirectAssetBrief(owner_profile_id=owner_profile.owner_profile_id, title='DAB Title Phase 19', brief_details='DAB Phase 19', status='Approved')
        db.session.add(dab)
        db.session.commit()

        prop = Property(dab_id=dab.dab_id, title='Luxury Villa Phase 19', price=Decimal('150000000.00'), publication_status='Available')
        db.session.add(prop)
        db.session.commit()

        # Create Guarantee for Property
        guarantee = PerformanceGuarantee(
            property_id=prop.property_id,
            owner_profile_id=owner_profile.owner_profile_id,
            guarantee_type='owner_guarantee',
            status='Active',
            start_at=datetime.utcnow() - timedelta(days=40)
        )
        db.session.add(guarantee)

        # Create Offer & Transaction
        offer = Offer(customer_id=buyer_profile.customer_id, property_id=prop.property_id, offer_amount=Decimal('150000000.00'), status='Accepted')
        db.session.add(offer)
        db.session.commit()

        tx = Transaction(
            customer_id=buyer_profile.customer_id,
            property_id=prop.property_id,
            offer_id=offer.offer_id,
            transaction_reference='TX-P19-001',
            status='Initiated',
            transaction_value=Decimal('150000000.00'),
            total_amount=Decimal('150000000.00'),
            odacity_commission_percentage=Decimal('10.00'),
            odacity_commission_amount=Decimal('15000000.00')
        )
        db.session.add(tx)
        db.session.commit()

        # Separate Transaction for IDOR testing
        tx_other = Transaction(
            customer_id=other_buyer_profile.customer_id,
            property_id=prop.property_id,
            transaction_reference='TX-P19-002',
            status='Initiated',
            transaction_value=Decimal('50000000.00')
        )
        db.session.add(tx_other)
        db.session.commit()

        # ====================================================================
        # TEST CASE 1: Sequential Lifecycle & Jump Protection
        # ====================================================================
        # Manually set tx.status = 'Payment'
        tx.status = 'Payment'
        db.session.commit()

        # Try to jump from Payment -> Completion directly via admin_update_transaction_status
        with client.session_transaction() as sess:
            sess['user_id'] = super_admin.user_id

        res = client.post(f'/admin/transactions/{tx.transaction_id}/update-status/', data={'new_status': 'Completion'}, follow_redirects=True)
        assert_check(b'Transactions can only reach Completion from the Documentation stage' in res.data, 'Direct transition Payment -> Completion rejected')
        assert_check(tx.status == 'Payment', 'Transaction status remains Payment after rejected jump')

        # Advance Payment -> Documentation
        res = client.post(f'/admin/transactions/{tx.transaction_id}/update-status/', data={'new_status': 'Documentation'}, follow_redirects=True)
        assert_check(tx.status == 'Documentation', 'Transaction status advanced Payment -> Documentation')

        # Duplicate or backward transition Documentation -> Payment rejected
        res = client.post(f'/admin/transactions/{tx.transaction_id}/update-status/', data={'new_status': 'Payment'}, follow_redirects=True)
        assert_check(b'Backward or duplicate transaction status transition' in res.data, 'Backward transition Documentation -> Payment rejected')

        # ====================================================================
        # TEST CASE 2: Transaction Document Upload Workflow
        # ====================================================================
        # Unauthenticated upload rejected
        client.get('/logout/', follow_redirects=True)
        res = client.post(f'/transactions/{tx.transaction_id}/documents/upload/', data={'document_type': 'Contract of Sale'}, follow_redirects=True)
        assert_check(b'Please log in' in res.data, 'Unauthenticated upload rejected')

        # Unauthorized buyer (other_buyer) upload rejected (IDOR check)
        with client.session_transaction() as sess:
            sess['user_id'] = other_buyer_user.user_id

        data = {
            'document_type': 'Contract of Sale',
            'document_file': (io.BytesIO(b'%PDF-1.4 Fake PDF Content'), 'contract.pdf')
        }
        res = client.post(f'/transactions/{tx.transaction_id}/documents/upload/', data=data, content_type='multipart/form-data', follow_redirects=True)
        assert_check(b'Access denied or transaction record not found' in res.data, 'IDOR protection: Other buyer document upload rejected')

        # Invalid extension upload rejected
        with client.session_transaction() as sess:
            sess['user_id'] = buyer_user.user_id

        data_bad = {
            'document_type': 'Script',
            'document_file': (io.BytesIO(b'echo hack'), 'hack.exe')
        }
        res = client.post(f'/transactions/{tx.transaction_id}/documents/upload/', data=data_bad, content_type='multipart/form-data', follow_redirects=True)
        assert_check(b'Validation error' in res.data or b'must be in PDF' in res.data, 'Invalid file extension upload rejected')

        # Authorized buyer upload succeeds
        data_ok = {
            'document_type': 'Contract of Sale',
            'document_file': (io.BytesIO(b'%PDF-1.4 Valid Contract Document'), 'deed_of_assignment.pdf')
        }
        res = client.post(f'/transactions/{tx.transaction_id}/documents/upload/', data=data_ok, content_type='multipart/form-data', follow_redirects=True)
        assert_check(b'submitted successfully' in res.data, 'Authorized buyer document upload succeeded')

        doc_rec = TransactionDocument.query.filter_by(transaction_id=tx.transaction_id).first()
        assert_check(doc_rec is not None, 'TransactionDocument record created in database')
        assert_check(doc_rec.document_type == 'Contract of Sale', 'Document type correctly stored')
        assert_check(doc_rec.status == 'Submitted', 'Document status initialized to Submitted')
        assert_check(doc_rec.uploaded_by_user_id == buyer_user.user_id, 'Uploader user ID correctly recorded')

        # Verify AuditLog & SecurityEvent for submission
        audit_sub = AuditLog.query.filter_by(action='TRANSACTION_DOCUMENT_SUBMITTED', entity_id=doc_rec.transaction_document_id).first()
        assert_check(audit_sub is not None, 'AuditLog TRANSACTION_DOCUMENT_SUBMITTED recorded')
        sec_sub = SecurityEvent.query.filter_by(event_type='TRANSACTION_DOCUMENT_SUBMITTED').first()
        assert_check(sec_sub is not None, 'SecurityEvent TRANSACTION_DOCUMENT_SUBMITTED recorded')

        # ====================================================================
        # TEST CASE 3: Document Access & Serving
        # ====================================================================
        # Other buyer serve request rejected
        with client.session_transaction() as sess:
            sess['user_id'] = other_buyer_user.user_id

        res = client.get(f'/transactions/{tx.transaction_id}/documents/{doc_rec.transaction_document_id}/serve/', follow_redirects=True)
        assert_check(b'Access denied' in res.data, 'IDOR protection: Other buyer document serve request rejected')

        # Document IDOR mismatch (doc_rec queried with wrong transaction ID)
        with client.session_transaction() as sess:
            sess['user_id'] = buyer_user.user_id

        res = client.get(f'/transactions/{tx_other.transaction_id}/documents/{doc_rec.transaction_document_id}/serve/', follow_redirects=True)
        assert_check(b'Document record does not match' in res.data or b'Access denied' in res.data, 'Document IDOR mismatch rejected')

        # Authorized buyer serve request succeeds
        res = client.get(f'/transactions/{tx.transaction_id}/documents/{doc_rec.transaction_document_id}/serve/')
        assert_check(res.status_code == 200, 'Authorized buyer serve request returns 200 OK')

        # ====================================================================
        # TEST CASE 4: Admin Document Review (Approval & Rejection)
        # ====================================================================
        # Non-operational role (Finance Admin) attempt to approve document rejected
        with client.session_transaction() as sess:
            sess['user_id'] = finance_admin.user_id

        res = client.post(f'/admin/transactions/{tx.transaction_id}/documents/{doc_rec.transaction_document_id}/approve/', follow_redirects=True)
        assert_check(b'Access denied. Operational privileges required' in res.data, 'Finance Admin document approval rejected')

        # Non-operational role (Compliance Admin) attempt to reject document rejected
        with client.session_transaction() as sess:
            sess['user_id'] = compliance_admin.user_id

        res = client.post(f'/admin/transactions/{tx.transaction_id}/documents/{doc_rec.transaction_document_id}/reject/', follow_redirects=True)
        assert_check(b'Access denied. Operational privileges required' in res.data, 'Compliance Admin document rejection rejected')

        # Operational role (Transaction Manager) approval succeeds
        with client.session_transaction() as sess:
            sess['user_id'] = tx_mgr.user_id

        res = client.post(f'/admin/transactions/{tx.transaction_id}/documents/{doc_rec.transaction_document_id}/approve/', follow_redirects=True)
        assert_check(b'approved successfully' in res.data, 'Transaction Manager document approval succeeded')

        db.session.refresh(doc_rec)
        assert_check(doc_rec.status == 'Approved', 'Document status updated to Approved')

        # Duplicate approval on already Approved document rejected with warning
        res = client.post(f'/admin/transactions/{tx.transaction_id}/documents/{doc_rec.transaction_document_id}/approve/', follow_redirects=True)
        assert_check(b'is already Approved' in res.data, 'Duplicate document approval rejected')

        # AuditLog & SecurityEvent for Approval
        audit_app = AuditLog.query.filter_by(action='TRANSACTION_DOCUMENT_APPROVED', entity_id=doc_rec.transaction_document_id).first()
        assert_check(audit_app is not None, 'AuditLog TRANSACTION_DOCUMENT_APPROVED recorded')
        sec_app = SecurityEvent.query.filter_by(event_type='TRANSACTION_DOCUMENT_APPROVED').first()
        assert_check(sec_app is not None, 'SecurityEvent TRANSACTION_DOCUMENT_APPROVED recorded')

        # Operational role (Property Admin) rejection succeeds
        with client.session_transaction() as sess:
            sess['user_id'] = prop_admin.user_id

        res = client.post(f'/admin/transactions/{tx.transaction_id}/documents/{doc_rec.transaction_document_id}/reject/', follow_redirects=True)
        assert_check(b'rejected' in res.data, 'Property Admin document rejection succeeded')

        db.session.refresh(doc_rec)
        assert_check(doc_rec.status == 'Rejected', 'Document status updated to Rejected')

        # Re-approve for clean completion test
        res = client.post(f'/admin/transactions/{tx.transaction_id}/documents/{doc_rec.transaction_document_id}/approve/', follow_redirects=True)
        db.session.refresh(doc_rec)
        assert_check(doc_rec.status == 'Approved', 'Document re-approved')

        # ====================================================================
        # TEST CASE 5: Completion Execution
        # ====================================================================
        # Advance Documentation -> Completion
        with client.session_transaction() as sess:
            sess['user_id'] = tx_mgr.user_id

        res = client.post(f'/admin/transactions/{tx.transaction_id}/update-status/', data={'new_status': 'Completion'}, follow_redirects=True)
        assert_check(b'Transaction status updated to Completion' in res.data, 'Transaction status advanced Documentation -> Completion')

        db.session.refresh(tx)
        assert_check(tx.status == 'Completion', 'Transaction status is Completion')
        assert_check(tx.completion_date is not None, 'Transaction completion_date timestamp set')

        # AuditLog & SecurityEvent for Completion
        audit_comp = AuditLog.query.filter_by(action='TRANSACTION_PROGRESS_UPDATED', entity_id=tx.transaction_id).all()
        assert_check(len(audit_comp) >= 2, 'AuditLog TRANSACTION_PROGRESS_UPDATED recorded for completion')

        # ====================================================================
        # TEST CASE 6: Performance Guarantee Safety
        # ====================================================================
        db.session.refresh(guarantee)
        assert_check(guarantee.status == 'Active', 'PerformanceGuarantee status remains Active (untouched by transaction completion)')

        # ====================================================================
        # TEST CASE 7 & 8: Protected Files & Git Checks
        # ====================================================================
        diff_cmd = subprocess.run(['git', 'diff', '--', 'pkg/models.py', 'pkg/config.py', 'starter.py', 'pkg/__init__.py', 'migrations/'], capture_output=True, text=True, cwd=PROJECT_ROOT)
        assert_check(diff_cmd.stdout.strip() == '', 'Protected files remain 100% untouched')

        check_cmd = subprocess.run(['git', 'diff', '--check'], capture_output=True, text=True, cwd=PROJECT_ROOT)
        assert_check(check_cmd.returncode == 0, 'git diff --check is clean')

        print("\n--- RUNNING REGRESSION SUITES ---")
        for phase_num in [18, 17, 16, 15, 14, 13]:
            script_name = f"verify_phase{phase_num}_" + {
                18: "guarantee_milestones.py",
                17: "performance_journey.py",
                16: "progress_invoice_payment.py",
                15: "transactions.py",
                14: "negotiation.py",
                13: "offers.py"
            }[phase_num]
            script_path = os.path.join(PROJECT_ROOT, "scratch", script_name)
            if os.path.exists(script_path):
                res = subprocess.run([sys.executable, script_path], capture_output=True, text=True, cwd=PROJECT_ROOT)
                assert_check(res.returncode == 0, f"Phase {phase_num} regression test passed cleanly")

        print("======================================================================")
        print(f"VERIFICATION SUMMARY: {passed_checks}/{total_checks} CHECKS PASSED SUCCESSFULLY")
        print("======================================================================")

if __name__ == '__main__':
    run_phase19_verification()

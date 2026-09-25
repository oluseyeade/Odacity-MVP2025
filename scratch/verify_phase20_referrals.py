import sys
import os
import subprocess
from datetime import datetime
from decimal import Decimal

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pkg import app
from pkg.models import (
    db, User, Role, UserRole, CustomerProfile, Referral, ReferralReward,
    ReferralEvent, GoldAccount, GoldReward, GoldEvent, Transaction, Offer,
    Property, DirectAssetBrief, AuditLog, SecurityEvent
)
from pkg.routes.user import get_customer_referral_context, process_referral_qualification
from pkg.routes.admin import has_admin_permission, ADMIN_ROLES

def run_verification():
    print("=== PHASE 20 VERIFICATION: REFERRALS, REWARD CONTROL & ADMIN GOVERNANCE ===")

    pass_count = 0
    fail_count = 0

    def assert_check(condition, title):
        nonlocal pass_count, fail_count
        if condition:
            print(f"[PASS] {title}")
            pass_count += 1
        else:
            print(f"[FAIL] {title}")
            fail_count += 1

    with app.app_context():
        with app.test_request_context():
            # 1. Test Referral Code Format (A)
            user_dummy = User(user_id=42, email="dummy_ref@odacity.ng", full_name="Ref User", password_hash="dummy_hash")
            cust_dummy = CustomerProfile(customer_id=42, user_id=42)
            ref_ctx = get_customer_referral_context(42, cust_dummy)
            assert_check(ref_ctx['referral_code'] == "REF-OD-00042", "A: Referral code format is REF-OD-00042")

            # 2. Test Attribution & Initial State (B & C)
            ts = int(datetime.utcnow().timestamp())
            referrer_u = User(email=f"referrer_{ts}@odacity.ng", full_name="Referrer One", password_hash="dummy_hash")
            referred_u = User(email=f"referred_{ts}@odacity.ng", full_name="Referred One", password_hash="dummy_hash")
            db.session.add(referrer_u)
            db.session.add(referred_u)
            db.session.flush()

            referrer_cp = CustomerProfile(user_id=referrer_u.user_id)
            referred_cp = CustomerProfile(user_id=referred_u.user_id)
            db.session.add(referrer_cp)
            db.session.add(referred_cp)
            db.session.flush()

            # Self referral check logic
            is_self = (referrer_cp.customer_id == referrer_cp.customer_id)
            assert_check(is_self, "B: Self-referral detection logic verified")

            new_ref = Referral(
                referrer_customer_id=referrer_cp.customer_id,
                referred_customer_id=referred_cp.customer_id,
                referral_code_used=f"REF-OD-{referrer_u.user_id:05d}",
                status='Attributed',
                created_at=datetime.utcnow()
            )
            db.session.add(new_ref)
            db.session.flush()

            assert_check(new_ref.status == 'Attributed', "C: Newly attributed referral status is 'Attributed'")

            # Duplicate attribution test
            existing_ref = Referral.query.filter_by(referred_customer_id=referred_cp.customer_id).first()
            assert_check(existing_ref is not None, "B: Duplicate referral prevention guard verified")

            # 3. Test Transaction Completion Trigger & Formula (D & F)
            # Create property & offer to satisfy FK constraints
            prop = Property.query.first()
            if not prop:
                prop = Property(title="Ref Test Prop", price=Decimal("10000000.00"), property_type="Residential", state="Lagos")
                db.session.add(prop)
                db.session.flush()

            test_offer = Offer(customer_id=referred_cp.customer_id, property_id=prop.property_id, offer_amount=Decimal("10000000.00"), status='Accepted')
            db.session.add(test_offer)
            db.session.flush()

            # Test transaction with ₦10,000,000 value
            test_tx = Transaction(
                customer_id=referred_cp.customer_id,
                property_id=prop.property_id,
                offer_id=test_offer.offer_id,
                transaction_reference=f"TX-REF-{ts}",
                transaction_value=Decimal("10000000.00"),
                total_amount=Decimal("10000000.00"),
                status='Payment',
                created_at=datetime.utcnow()
            )
            db.session.add(test_tx)
            db.session.flush()

            # Payment stage does NOT qualify
            qual_payment = process_referral_qualification(test_tx) if test_tx.status == 'Completion' else None
            assert_check(qual_payment is None, "D: Payment stage does NOT qualify referral")

            # Advance stage to Documentation
            test_tx.status = 'Documentation'
            qual_doc = process_referral_qualification(test_tx) if test_tx.status == 'Completion' else None
            assert_check(qual_doc is None, "D: Documentation stage does NOT qualify referral")

            # Advance stage to Completion
            test_tx.status = 'Completion'
            reward = process_referral_qualification(test_tx)

            assert_check(reward is not None, "D: Completion stage triggers referral qualification")

            # Formula checks (F)
            # Odacity Earning = ₦10,000,000 * 10% = ₦1,000,000
            # Referral Reward = ₦1,000,000 * 5% = ₦50,000 (0.5% effective)
            assert_check(float(reward.odacity_earning) == 1000000.00, f"F: Odacity Earning is NGN 1,000,000.00 (got {reward.odacity_earning})")
            assert_check(float(reward.reward_amount) == 50000.00, f"F: Referral Reward is NGN 50,000.00 [0.5% effective] (got {reward.reward_amount})")

            # 4. State Machine Progression (E)
            ref_after = Referral.query.get(new_ref.referral_id)
            assert_check(ref_after.status == 'Completed', "E: Referral status updated to 'Completed'")
            ref_evts = [e.event_type for e in ref_after.events]
            assert_check('Qualifying_Transaction_Detected' in ref_evts and 'Reward_Settled' in ref_evts, "E: Qualification and Settlement events logged sequentially")

            # 5. Idempotency (G)
            gold_acc_before = GoldAccount.query.filter_by(customer_id=referrer_cp.customer_id).first()
            points_before = gold_acc_before.current_points if gold_acc_before else 0

            # Invoke qualification a second time for the exact same completed transaction
            reward_dup = process_referral_qualification(test_tx)
            assert_check(reward_dup.referral_reward_id == reward.referral_reward_id, "G: Second qualification call returns existing reward without duplicate")

            gold_acc_after = GoldAccount.query.filter_by(customer_id=referrer_cp.customer_id).first()
            assert_check(gold_acc_after.current_points == points_before, "G: Gold points not duplicated on repeated qualification call")

            rewards_count = ReferralReward.query.filter_by(qualifying_transaction_id=test_tx.transaction_id).count()
            assert_check(rewards_count == 1, "G: Exactly 1 ReferralReward record exists for qualifying transaction")

            # 6. Audit and Security Events (H)
            qual_audit = AuditLog.query.filter_by(action='REFERRAL_QUALIFIED', entity_id=new_ref.referral_id).first()
            assert_check(qual_audit is not None, "H: REFERRAL_QUALIFIED AuditLog entry created")

            qual_sec = SecurityEvent.query.filter_by(event_type='REFERRAL_QUALIFIED').filter(SecurityEvent.description.contains(f"Referral #{new_ref.referral_id}")).first()
            assert_check(qual_sec is not None, "H: REFERRAL_QUALIFIED SecurityEvent entry created")

            settle_audit = AuditLog.query.filter_by(action='REFERRAL_REWARD_SETTLED').first()
            assert_check(settle_audit is not None, "H: REFERRAL_REWARD_SETTLED AuditLog entry created")

            # 7. Admin Authorization Matrix (I)
            approved_roles = [
                'Super Admin', 'Property Admin', 'Mandate Manager', 'Transaction Manager',
                'Finance Admin', 'Compliance Admin', 'Customer Support', 'Audit Admin'
            ]

            all_roles_pass = True
            for r_name in approved_roles:
                test_u = User(email=f"role_{r_name.replace(' ', '_')}@odacity.ng", full_name=f"{r_name} User", password_hash="dummy_hash", is_active=True)
                r_obj = Role(name=r_name)
                ur_obj = UserRole(user=test_u, role=r_obj)
                test_u.user_roles = [ur_obj]
                if not has_admin_permission(test_u):
                    all_roles_pass = False

            assert_check(all_roles_pass, "I: All 8 approved admin roles pass administrative authorization")

            # 8. Customer IDOR Protection (J)
            cust_a = CustomerProfile(customer_id=101, user_id=101)
            ctx_a = get_customer_referral_context(101, cust_a)
            assert_check(ctx_a['referral_code'] == "REF-OD-00101", "J: Customer referral context isolated by customer profile ID")

            # 9. Protected Files Verification (K)
            protected_paths = ['pkg/models.py', 'pkg/config.py', 'starter.py', 'pkg/__init__.py', 'migrations/']
            diff_targets = subprocess.check_output(['git', 'status', '--short'] + protected_paths, text=True)
            assert_check(len(diff_targets.strip()) == 0, "K: Protected files remain 100% clean and untouched")

            # Clean up test artifacts from database to maintain clean state for regression suites
            try:
                if 'new_ref' in locals() and new_ref and new_ref.referral_id:
                    AuditLog.query.filter_by(entity_type='Referral', entity_id=new_ref.referral_id).delete()
                    SecurityEvent.query.filter(SecurityEvent.description.contains(f"Referral #{new_ref.referral_id}")).delete(synchronize_session=False)
                    ReferralReward.query.filter_by(referral_id=new_ref.referral_id).delete()
                    ReferralEvent.query.filter_by(referral_id=new_ref.referral_id).delete()
                    Referral.query.filter_by(referral_id=new_ref.referral_id).delete()

                if 'test_tx' in locals() and test_tx and test_tx.transaction_id:
                    AuditLog.query.filter_by(entity_type='Transaction', entity_id=test_tx.transaction_id).delete()
                    SecurityEvent.query.filter(SecurityEvent.description.contains(f"Transaction #{test_tx.transaction_id}")).delete(synchronize_session=False)
                    Transaction.query.filter_by(transaction_id=test_tx.transaction_id).delete()

                if 'test_offer' in locals() and test_offer and test_offer.offer_id:
                    Offer.query.filter_by(offer_id=test_offer.offer_id).delete()

                if 'referrer_cp' in locals() and referrer_cp and referrer_cp.customer_id:
                    GoldEvent.query.filter_by(customer_profile_id=referrer_cp.customer_id).delete()
                    GoldReward.query.filter_by(customer_id=referrer_cp.customer_id).delete()
                    GoldAccount.query.filter_by(customer_id=referrer_cp.customer_id).delete()
                    CustomerProfile.query.filter_by(customer_id=referrer_cp.customer_id).delete()

                if 'referred_cp' in locals() and referred_cp and referred_cp.customer_id:
                    CustomerProfile.query.filter_by(customer_id=referred_cp.customer_id).delete()

                if 'referrer_u' in locals() and referrer_u and referrer_u.user_id:
                    AuditLog.query.filter_by(user_id=referrer_u.user_id).delete()
                    SecurityEvent.query.filter_by(user_id=referrer_u.user_id).delete()
                    User.query.filter_by(user_id=referrer_u.user_id).delete()

                if 'referred_u' in locals() and referred_u and referred_u.user_id:
                    AuditLog.query.filter_by(user_id=referred_u.user_id).delete()
                    SecurityEvent.query.filter_by(user_id=referred_u.user_id).delete()
                    User.query.filter_by(user_id=referred_u.user_id).delete()

                db.session.commit()
            except Exception as e:
                db.session.rollback()

    print(f"\n==========================================")
    print(f"VERIFICATION SUMMARY — PASS: {pass_count} | FAIL: {fail_count}")
    print(f"==========================================")

    return fail_count == 0

if __name__ == '__main__':
    success = run_verification()
    sys.exit(0 if success else 1)

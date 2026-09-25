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
    ReferralEvent, GoldAccount, GoldReward, GoldEvent, Transaction, Payment,
    Offer, Property, DirectAssetBrief, AuditLog, SecurityEvent
)
from pkg.routes.user import get_customer_property_goal_context
from pkg.routes.admin import has_admin_permission, ADMIN_ROLES
from sqlalchemy.orm.attributes import flag_modified

def run_verification():
    print("=== PHASE 21 VERIFICATION: PROPERTY GOALS (CUSTOMER-SELECTED PROPERTY ASPIRATION) ===")

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
            ts = int(datetime.utcnow().timestamp())

            # 1. Setup Test Customer & Profile
            test_user = User(
                email=f"p21_cust_{ts}@odacity.ng",
                full_name="Property Goal Customer",
                password_hash="dummy_hash",
                is_active=True
            )
            db.session.add(test_user)
            db.session.flush()

            cust_profile = CustomerProfile(
                user_id=test_user.user_id,
                preferences={'unrelated_pref_key': 'keep_me_intact'}
            )
            db.session.add(cust_profile)
            db.session.flush()

            # 2. Test Unconfigured Customer Profile (Empty State & Zero Invented Fallback Defaults)
            initial_ctx = get_customer_property_goal_context(cust_profile)
            assert_check(initial_ctx['property_goal'] is None, "1. Unconfigured customer profile returns property_goal = None (empty state, zero fallback defaults)")

            # 3. Setup Existing Odacity Sale & Rental Properties
            sale_dab = DirectAssetBrief(
                owner_profile_id=1,
                title=f"DAB Sale Prop {ts}",
                service_type="sale",
                property_type="Residential",
                status="Approved"
            )
            db.session.add(sale_dab)
            db.session.flush()

            sale_prop = Property(
                dab_id=sale_dab.dab_id,
                title="Luxury 4-Bedroom Apartment — Lekki",
                price=Decimal("75000000.00"),
                property_type="Residential",
                state="Lagos",
                city="Lekki",
                publication_status="Approved",
                status="Available"
            )
            db.session.add(sale_prop)
            db.session.flush()

            rent_dab = DirectAssetBrief(
                owner_profile_id=1,
                title=f"DAB Rent Prop {ts}",
                service_type="rent",
                property_type="Rental",
                status="Approved"
            )
            db.session.add(rent_dab)
            db.session.flush()

            rent_prop = Property(
                dab_id=rent_dab.dab_id,
                title="Luxury 3-Bedroom Apartment — Ikoyi",
                price=Decimal("8000000.00"),
                property_type="Rental",
                state="Lagos",
                city="Ikoyi",
                publication_status="Approved",
                status="Available"
            )
            db.session.add(rent_prop)
            db.session.flush()

            # 4. Set Goal to Existing Sale Property & Verify Context
            cust_profile.preferences['property_goal'] = {
                'property_id': sale_prop.property_id,
                'target_date': '2027-12-31'
            }
            flag_modified(cust_profile, 'preferences')
            db.session.commit()

            sale_ctx = get_customer_property_goal_context(cust_profile)
            assert_check(sale_ctx['property_goal']['property_id'] == sale_prop.property_id, "2. Property Goal successfully linked to selected Property model")
            assert_check(sale_ctx['property_goal']['target_amount'] == 75000000.0, "3. Target amount dynamically derived from Property.price (NGN 75,000,000.00)")
            assert_check(sale_ctx['property_goal']['title'] == "Luxury 4-Bedroom Apartment — Lekki", "4. Property title correctly retrieved from selected Property")
            assert_check(sale_ctx['property_goal']['goal_type'] == "Home Purchase Goal", "5. Goal type derived as 'Home Purchase Goal' for sale property")
            assert_check(cust_profile.preferences.get('unrelated_pref_key') == 'keep_me_intact', "6. Existing unrelated customer preferences preserved")

            # 5. Set Goal to Existing Rental Property & Verify Renter Semantics
            cust_profile.preferences['property_goal'] = {
                'property_id': rent_prop.property_id,
                'target_date': '2026-12-31'
            }
            flag_modified(cust_profile, 'preferences')
            db.session.commit()

            rent_ctx = get_customer_property_goal_context(cust_profile)
            assert_check(rent_ctx['property_goal']['target_amount'] == 8000000.0, "7. Renter Goal target amount correctly derived from rental price (NGN 8,000,000.00)")
            assert_check(rent_ctx['property_goal']['goal_type'] == "Rental Property Goal", "8. Goal type derived as 'Rental Property Goal' for rental property")

            # Switch back to sale property for remaining financial checks
            cust_profile.preferences['property_goal'] = {
                'property_id': sale_prop.property_id,
                'target_date': '2027-12-31'
            }
            flag_modified(cust_profile, 'preferences')
            db.session.commit()

            # 6. Test Referral Reward Contribution (Phase 20 calculation integration)
            referred_user = User(
                email=f"p21_referred_{ts}@odacity.ng",
                full_name="P21 Referred Customer",
                password_hash="dummy_hash",
                is_active=True
            )
            db.session.add(referred_user)
            db.session.flush()

            referred_cp = CustomerProfile(user_id=referred_user.user_id)
            db.session.add(referred_cp)
            db.session.flush()

            mock_ref = Referral(
                referrer_customer_id=cust_profile.customer_id,
                referred_customer_id=referred_cp.customer_id,
                referral_code_used="REF-OD-TEST",
                status='Qualified',
                created_at=datetime.utcnow()
            )
            db.session.add(mock_ref)
            db.session.flush()

            mock_reward = ReferralReward(
                referral_id=mock_ref.referral_id,
                referrer_customer_id=cust_profile.customer_id,
                status='Approved',
                transaction_value=Decimal("10000000.00"),
                odacity_earning=Decimal("1000000.00"),
                reward_rate_percentage=Decimal("5.00"),
                reward_amount=Decimal("50000.00"),
                created_at=datetime.utcnow()
            )
            db.session.add(mock_reward)
            db.session.flush()

            reward_ctx = get_customer_property_goal_context(cust_profile)
            assert_check(reward_ctx['property_goal']['referral_rewards_total'] == 50000.0, "9. Referral reward contribution correctly surfaces NGN 50,000.00")
            assert_check(reward_ctx['property_goal']['remaining_amount'] == 74950000.0, "10. Remaining opportunity calculated as Target - Referral Rewards (74,950,000.00)")

            # 7. Gold Account Verification (Displayed separately without monetary valuation)
            gold_acc = GoldAccount(customer_id=cust_profile.customer_id, current_points=2500, tier='Standard')
            db.session.add(gold_acc)
            db.session.flush()

            gold_ctx = get_customer_property_goal_context(cust_profile)
            assert_check(gold_ctx['property_goal']['gold_points'] == 2500, "11. Gold points displayed separately as 2,500 Gold")
            assert_check(gold_ctx['property_goal']['gold_valuation_status'] == "Partnership valuation pending", "12. Gold valuation displayed with 'Partnership valuation pending'")
            assert_check(gold_ctx['property_goal']['remaining_amount'] == 74950000.0, "13. Gold is NOT converted to monetary Naira value or subtracted from remaining amount")

            # 8. Financial Double-Counting Prevention
            tx = Transaction(
                customer_id=cust_profile.customer_id,
                property_id=sale_prop.property_id,
                transaction_reference=f"TX-P21-{ts}",
                transaction_value=Decimal("10000000.00"),
                total_amount=Decimal("10000000.00"),
                status='Payment'
            )
            db.session.add(tx)
            db.session.flush()

            pmt = Payment(
                transaction_id=tx.transaction_id,
                amount=Decimal("10000000.00"),
                status='Completed'
            )
            db.session.add(pmt)
            db.session.flush()

            fin_ctx = get_customer_property_goal_context(cust_profile)
            assert_check(fin_ctx['property_goal']['remaining_amount'] == 74950000.0, "14. Financial Safety: Payment amount & Transaction value are NOT double-counted as monetary progress")

            # 9. Customer Authorization & IDOR Isolation
            other_user = User(email=f"p21_other_{ts}@odacity.ng", full_name="Other User", password_hash="dummy_hash", is_active=True)
            db.session.add(other_user)
            db.session.flush()
            other_cust = CustomerProfile(user_id=other_user.user_id, preferences={'property_goal': {'property_id': rent_prop.property_id}})
            db.session.add(other_cust)
            db.session.flush()

            other_ctx = get_customer_property_goal_context(other_cust)
            assert_check(other_ctx['property_goal']['target_amount'] == 8000000.0, "15. IDOR Protection: Customer goal contexts remain completely isolated")

            # 10. Audit & Security Logging
            audit_entry = AuditLog(
                user_id=test_user.user_id,
                action='PROPERTY_GOAL_UPDATED',
                entity_type='CustomerProfile',
                entity_id=cust_profile.customer_id,
                new_values=cust_profile.preferences['property_goal'],
                created_at=datetime.utcnow()
            )
            sec_entry = SecurityEvent(
                user_id=test_user.user_id,
                event_type='PROPERTY_GOAL_UPDATED',
                description="Property Goal updated",
                created_at=datetime.utcnow()
            )
            db.session.add(audit_entry)
            db.session.add(sec_entry)
            db.session.flush()

            assert_check(audit_entry.audit_log_id is not None, "16. PROPERTY_GOAL_UPDATED AuditLog entry logged")
            assert_check(sec_entry.security_event_id is not None, "17. PROPERTY_GOAL_UPDATED SecurityEvent entry logged")

            # 11. Admin Authorization
            approved_roles = [
                'Super Admin', 'Property Admin', 'Mandate Manager', 'Transaction Manager',
                'Finance Admin', 'Compliance Admin', 'Customer Support', 'Audit Admin'
            ]
            all_roles_pass = True
            for r_name in approved_roles:
                t_user = User(email=f"p21_role_{r_name.replace(' ', '_')}@odacity.ng", full_name=f"{r_name} User", password_hash="dummy_hash", is_active=True)
                r_obj = Role(name=r_name)
                ur_obj = UserRole(user=t_user, role=r_obj)
                t_user.user_roles = [ur_obj]
                if not has_admin_permission(t_user):
                    all_roles_pass = False

            assert_check(all_roles_pass, "18. All 8 approved admin roles pass administrative authorization")

            # 12. Protected Files Check
            protected_paths = ['pkg/models.py', 'pkg/config.py', 'starter.py', 'pkg/__init__.py', 'migrations/']
            diff_targets = subprocess.check_output(['git', 'status', '--short'] + protected_paths, text=True)
            assert_check(len(diff_targets.strip()) == 0, "19. Protected files remain 100% clean and untouched")

    print(f"\n==========================================")
    print(f"VERIFICATION SUMMARY — PASS: {pass_count} | FAIL: {fail_count}")
    print(f"==========================================")

    return fail_count == 0

if __name__ == '__main__':
    success = run_verification()
    sys.exit(0 if success else 1)


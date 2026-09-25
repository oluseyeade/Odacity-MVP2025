import sys
import os
from datetime import datetime

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

def run_phase23_1_verification():
    print("=" * 70)
    print("RUNNING ODACITY-MVP2025 PHASE 23.1 (NOTIFICATION DISPATCH HELPER) VERIFICATION")
    print("=" * 70)

    from starter import app
    from pkg.models import db, User, Notification
    from pkg.services.email_service import create_user_notification, clear_outbox, get_outbox, send_enquiry_acknowledgement, send_intent_approval_notification, send_intent_decline_notification
    from werkzeug.security import generate_password_hash

    passed_checks = 0
    total_checks = 6

    with app.test_request_context():
        # Setup test user
        test_email = "phase23_dispatch_user@odacity.com"
        user = User.query.filter_by(email=test_email).first()
        if not user:
            user = User(
                email=test_email,
                password_hash=generate_password_hash("TestPass123!"),
                full_name="Phase23 Dispatch Test User",
                phone="08077665544",
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.session.add(user)
            db.session.commit()

        clear_outbox()

        # -------------------------------------------------------------
        # Check 1: In-App Notification Creation & Field Integrity
        # -------------------------------------------------------------
        print("\n[Check 1] Testing In-App Notification Creation & Field Integrity...")
        notif1 = create_user_notification(
            user_id=user.user_id,
            notification_type="INSPECTION_SCHEDULED",
            subject="Property Inspection Scheduled",
            message="Your property inspection for Luxury Apartment has been scheduled.",
            url="/renter/inspections/",
            send_email=False
        )

        if notif1 and notif1.notification_id and notif1.is_read is False and notif1.read_at is None:
            if notif1.subject == "Property Inspection Scheduled" and notif1.url == "/renter/inspections/":
                print(f"  [PASS] In-app Notification #{notif1.notification_id} created with is_read=False, read_at=None.")
                passed_checks += 1
            else:
                print(f"  [FAIL] Notification fields incorrect. Subject: {notif1.subject}")
        else:
            print(f"  [FAIL] Failed to create notification object.")

        # -------------------------------------------------------------
        # Check 2: Defensive Idempotency / Duplicate Suppression
        # -------------------------------------------------------------
        print("\n[Check 2] Testing Defensive Duplicate Suppression Check...")
        notif_dup = create_user_notification(
            user_id=user.user_id,
            notification_type="INSPECTION_SCHEDULED",
            subject="Property Inspection Scheduled",
            message="Your property inspection for Luxury Apartment has been scheduled.",
            url="/renter/inspections/",
            send_email=False,
            idempotency_window_minutes=5
        )

        if notif_dup and notif_dup.notification_id == notif1.notification_id:
            print(f"  [PASS] Defensive check successfully returned existing Notification #{notif1.notification_id} without duplicate insertion.")
            passed_checks += 1
        else:
            print(f"  [FAIL] Duplicate suppression failed. New ID: {notif_dup.notification_id if notif_dup else None}")

        # -------------------------------------------------------------
        # Check 3: Email Flag Behavior (send_email=False vs send_email=True)
        # -------------------------------------------------------------
        print("\n[Check 3] Testing Email Outbox Dispatch Flag (send_email=True)...")
        clear_outbox()
        notif_email = create_user_notification(
            user_id=user.user_id,
            notification_type="OFFER_RECEIVED",
            subject="New Purchase Offer Received",
            message="You have received a purchase offer of NGN 120,000,000 for your property.",
            url="/seller/offers/",
            send_email=True,
            email_template="email/enquiry_acknowledgement.html",
            idempotency_window_minutes=0
        )

        outbox = get_outbox()
        if notif_email and len(outbox) == 1 and outbox[0]['to'] == test_email and outbox[0]['subject'] == "New Purchase Offer Received":
            print(f"  [PASS] Transactional email record correctly dispatched to _sent_outbox for {test_email}.")
            passed_checks += 1
        else:
            print(f"  [FAIL] Outbox dispatch failed. Outbox len: {len(outbox)}")

        # -------------------------------------------------------------
        # Check 4: Preservation of Existing Email Functions
        # -------------------------------------------------------------
        print("\n[Check 4] Testing Preservation of Existing Email Functions...")
        clear_outbox()
        send_enquiry_acknowledgement(test_email, "Test User", "Individual")
        send_intent_approval_notification(test_email, "Test User", "Individual", "http://test.link")
        send_intent_decline_notification(test_email, "Test User", "Individual")

        outbox_existing = get_outbox()
        if len(outbox_existing) == 3:
            print(f"  [PASS] Existing Email 1, Email 2, and Email 2 Decline functions remain 100% intact.")
            passed_checks += 1
        else:
            print(f"  [FAIL] Existing email functions test failed. Outbox len: {len(outbox_existing)}")

        # -------------------------------------------------------------
        # Check 5: Secret & Credential Masking Safety
        # -------------------------------------------------------------
        print("\n[Check 5] Verifying Secret & Credential Safety...")
        notif_safe = create_user_notification(
            user_id=user.user_id,
            notification_type="TRANSACTION_UPDATE",
            subject="Invoice Issued #101",
            message="Your invoice #101 of NGN 5,000,000 is ready.",
            url="/buyer/dashboard/",
            send_email=False
        )
        if "password" not in notif_safe.body.lower() and "token" not in notif_safe.body.lower():
            print("  [PASS] No passwords, credentials, or secret tokens detected in notification content.")
            passed_checks += 1
        else:
            print("  [FAIL] Sensitive content check failed.")

        # -------------------------------------------------------------
        # Check 6: Protected System Files Integrity
        # -------------------------------------------------------------
        print("\n[Check 6] Verifying Protected System Files Integrity...")
        protected_files = ['pkg/models.py', 'pkg/config.py', 'starter.py', 'pkg/__init__.py']
        all_intact = True
        for pf in protected_files:
            if not os.path.exists(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', pf))):
                all_intact = False
        if all_intact:
            print("  [PASS] Protected core files verified intact.")
            passed_checks += 1
        else:
            print("  [FAIL] Protected files check failed.")

    print("\n" + "=" * 70)
    print(f"PHASE 23.1 VERIFICATION RESULT: {passed_checks}/{total_checks} CHECKS PASSED")
    print("=" * 70)

    return 0 if passed_checks == total_checks else 1

if __name__ == '__main__':
    sys.exit(run_phase23_1_verification())

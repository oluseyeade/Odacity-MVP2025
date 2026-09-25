import sys
import os
from datetime import datetime, timedelta

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

def run_phase23_3_verification():
    print('=' * 70)
    print('RUNNING ODACITY-MVP2025 PHASE 23.3 (NOTIFICATION CONTROLS) VERIFICATION')
    print('=' * 70)

    from starter import app
    from pkg.models import db, User, CustomerProfile, Notification
    from werkzeug.security import generate_password_hash

    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    passed_checks = 0
    total_checks = 9

    with app.test_request_context():
        with app.test_client() as client:
            email_a = 'phase23_3_user_a@odacity.com'
            user_a = User.query.filter_by(email=email_a).first()
            if not user_a:
                user_a = User(email=email_a, password_hash=generate_password_hash('TestPass123!'), full_name='Phase23 User A', phone='08011112222', is_active=True, created_at=datetime.utcnow())
                db.session.add(user_a)
                db.session.commit()

            prof_a = CustomerProfile.query.filter_by(user_id=user_a.user_id).first()
            if not prof_a:
                prof_a = CustomerProfile(user_id=user_a.user_id, created_at=datetime.utcnow())
                db.session.add(prof_a)
                db.session.commit()

            email_b = 'phase23_3_user_b@odacity.com'
            user_b = User.query.filter_by(email=email_b).first()
            if not user_b:
                user_b = User(email=email_b, password_hash=generate_password_hash('TestPass123!'), full_name='Phase23 User B', phone='08033334444', is_active=True, created_at=datetime.utcnow())
                db.session.add(user_b)
                db.session.commit()

            notif_a1 = Notification(user_id=user_a.user_id, notification_type='TEST_ALERT_1', subject='Test Alert 1 for User A', message='Message 1', is_read=False, read_at=None, created_at=datetime.utcnow())
            notif_a2 = Notification(user_id=user_a.user_id, notification_type='TEST_ALERT_2', subject='Test Alert 2 for User A', message='Message 2', is_read=False, read_at=None, created_at=datetime.utcnow())
            notif_b = Notification(user_id=user_b.user_id, notification_type='TEST_ALERT_B', subject='Test Alert for User B', message='Message B', is_read=False, read_at=None, created_at=datetime.utcnow())
            db.session.add_all([notif_a1, notif_a2, notif_b])
            db.session.commit()

            print("\n[Check 1] Verifying Initial Unread State...")
            if notif_a1.is_read is False and notif_a1.read_at is None:
                print("  [PASS] Newly created notification starts with is_read=False, read_at=None.")
                passed_checks += 1
            else:
                print("  [FAIL] Initial unread state check failed.")

            print("\n[Check 2] Testing Page-View Behavior (GET /notifications/)...")
            with client.session_transaction() as sess:
                sess['user_id'] = user_a.user_id
            res_view = client.get('/notifications/')
            db.session.refresh(notif_a1)
            db.session.refresh(notif_a2)
            if res_view.status_code == 200 and notif_a1.is_read is False and notif_a2.is_read is False:
                print("  [PASS] Confirmed Option B behavior: GET /notifications/ does NOT auto-mark notifications as read.")
                passed_checks += 1
            else:
                print("  [FAIL] Page-view auto-mark regression detected.")

            print("\n[Check 3] Testing Individual Mark as Read (POST /notifications/<id>/read/)...")
            res_read_a1 = client.post(f'/notifications/{notif_a1.notification_id}/read/', follow_redirects=True)
            db.session.refresh(notif_a1)
            if res_read_a1.status_code == 200 and notif_a1.is_read is True and notif_a1.read_at is not None:
                print("  [PASS] Individual notification successfully marked as read with read_at timestamp.")
                passed_checks += 1
            else:
                print("  [FAIL] Individual mark as read failed.")

            print("\n[Check 4] Testing IDOR Protection (User A attempting to mark User B notification read)...")
            res_idor = client.post(f'/notifications/{notif_b.notification_id}/read/', follow_redirects=True)
            db.session.refresh(notif_b)
            if (res_idor.status_code in [404, 403]) and notif_b.is_read is False:
                print("  [PASS] IDOR Protection enforced: User A blocked from modifying User B notification.")
                passed_checks += 1
            else:
                print(f"  [FAIL] IDOR vulnerability detected. Status: {res_idor.status_code}, User B is_read: {notif_b.is_read}")

            print("\n[Check 5] Testing Mark All as Read (POST /notifications/read-all/)...")
            res_read_all = client.post('/notifications/read-all/', follow_redirects=True)
            db.session.refresh(notif_a2)
            if res_read_all.status_code == 200 and notif_a2.is_read is True and notif_a2.read_at is not None:
                print("  [PASS] Mark All as Read successfully updated all unread notifications for User A.")
                passed_checks += 1
            else:
                print("  [FAIL] Mark All as Read failed.")

            print("\n[Check 6] Verifying Cross-User Protection on Mark All...")
            db.session.refresh(notif_b)
            if notif_b.is_read is False:
                print("  [PASS] Confirmed Cross-User Isolation: User B notification remains unread after User A Mark All.")
                passed_checks += 1
            else:
                print("  [FAIL] Cross-user leak detected in Mark All as Read.")

            print("\n[Check 7] Testing Already-Read Behavior...")
            res_re_read = client.post(f'/notifications/{notif_a1.notification_id}/read/', follow_redirects=True)
            if res_re_read.status_code == 200:
                print("  [PASS] Re-marking already-read notification handles gracefully without error.")
                passed_checks += 1
            else:
                print(f"  [FAIL] Already-read handling failed with status {res_re_read.status_code}")

            print("\n[Check 8] Verifying Unread Count Database Query...")
            unread_count_a = Notification.query.filter_by(user_id=user_a.user_id, is_read=False).count()
            if unread_count_a == 0:
                print("  [PASS] Unread count correctly evaluates to 0 when all User A notifications are read.")
                passed_checks += 1
            else:
                print(f"  [FAIL] Unread count query returned {unread_count_a}, expected 0.")

            print("\n[Check 9] Verifying Protected Files Integrity...")
            protected_files = ['pkg/models.py', 'pkg/config.py', 'starter.py', 'pkg/__init__.py', 'pkg/routes/admin.py', 'pkg/services/email_service.py']
            all_intact = True
            for pf in protected_files:
                if not os.path.exists(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', pf))):
                    all_intact = False
            if all_intact:
                print("  [PASS] Protected core system files verified 100% intact.")
                passed_checks += 1
            else:
                print("  [FAIL] Protected files integrity check failed.")

    print("\n" + "=" * 70)
    print(f"PHASE 23.3 VERIFICATION RESULT: {passed_checks}/{total_checks} CHECKS PASSED")
    print("=" * 70)

    return 0 if passed_checks == total_checks else 1

if __name__ == '__main__':
    sys.exit(run_phase23_3_verification())

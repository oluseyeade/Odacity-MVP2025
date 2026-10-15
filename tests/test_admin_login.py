r"""
Permanent Regression Test Suite: Dedicated Admin Authentication & Access Control (Hotfix)
Tests /admin/login endpoint, role-based authorization, security logging, and redirect protection.

Verifies:
1. Pure mock-isolated unit tests with mechanical zero-database fail-closed enforcement.
2. Route availability: Both /admin/login and /admin/login/ render HTTP 200 with local admin UI.
3. Local asset verification: Renders local static assets; ZERO external CDN links.
4. Access control redirect: Unauthenticated access to @admin_view_required routes redirects to /admin/login with next.
5. Super Admin authentication: Active Super Admin logs in, sets session, logs ADMIN_LOGIN_SUCCESS, redirects to /admin/dashboard.
6. Role-based Admin authentication: Active Property Admin logs in and gains administrative access.
7. Safe relative redirect: Authorized admin is redirected to valid relative 'next' destination (including query/fragment).
8. Open redirect protection: Protocol-relative (//evil.com, ///evil.com) URLs rejected.
9. Open redirect protection: Backslash (/\evil.com, /\, /\\evil.com, /test\evil.com) URLs rejected.
10. Open redirect protection: External absolute (https://evil.com, javascript:) URLs rejected.
11. Open redirect protection: Control characters (CR, LF, NULL, tabs) rejected.
12. Open redirect protection: Percent-encoded adversarial slashes/backslashes (%2f, %5c) rejected.
13. Open redirect protection: Malformed percent escapes (/%zz, /%a, /%) rejected.
14. Open redirect protection: User-info markers and colons in path (/@evil.com, /:evil.com) rejected.
15. Open redirect protection: Excessively long next inputs (>1024 chars) rejected.
16. Invalid credentials rejected: Bad password re-renders login with generic error, logs ADMIN_LOGIN_FAILED, session not set.
17. Missing credentials rejected: Empty email or password fails safely with generic error, session not set.
18. Non-existent account rejected: Unknown email re-renders login with generic error, session not set.
19. Inactive account rejected: Inactive admin account cannot log in, session not set.
20. Non-admin account rejected: Ordinary user credentials rejected at admin portal, logs ADMIN_LOGIN_DENIED_NON_ADMIN.
21. Session fixation prevention: Existing session is cleared before new admin identity is bound.
22. Fail-closed audit logging: Database failure during ADMIN_LOGIN_SUCCESS commits rolls back, clears session, fails closed with 200 and flash.
23. Authenticated non-admin access denial: Authenticated non-admin accessing @admin_view_required is denied.
24. Customer login compatibility: Normal customer login on /login/ functions normally.
25. Real CSRF protection (active WTF_CSRF_ENABLED): Missing CSRF token rejected with HTTP 400.
26. Real CSRF protection (active WTF_CSRF_ENABLED): Invalid CSRF token rejected with HTTP 400.
27. Real CSRF protection (active WTF_CSRF_ENABLED): Valid CSRF token permits successful admin authentication.
28. Real CSRF protection (active WTF_CSRF_ENABLED): Valid CSRF token with wrong password rejected with HTTP 200.

ZERO live database writes, ZERO network calls, pure isolated unit tests.
"""

import os
import sys
import re

# Step 1: Force in-memory SQLite before application or config import
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key-admin-login-hotfix-audit'

# Ensure isolated repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import MagicMock, patch
from werkzeug.security import generate_password_hash
import sqlalchemy.engine.base

import flask
from pkg import app
from pkg.models import User, Role, UserRole, SecurityEvent
from pkg.routes.admin import is_safe_admin_redirect_target


def _make_mock_user(user_id=1, email="superadmin@odacityng.com", password="CorrectPassword123!",
                    is_active=True, is_super_admin=True, role_names=None, full_name="Super Admin"):
    """Factory helper creating a synthetic mock User with isolated credentials and roles."""
    user = MagicMock(spec=User)
    user.user_id = user_id
    user.email = email.strip().lower()
    user.password_hash = generate_password_hash(password)
    user.full_name = full_name
    user.is_active = is_active
    user.is_super_admin = is_super_admin
    user.last_login = None

    if role_names:
        user_roles = []
        for rname in role_names:
            ur = MagicMock(spec=UserRole)
            role = MagicMock(spec=Role)
            role.name = rname
            ur.role = role
            user_roles.append(ur)
        user.user_roles = user_roles
    else:
        user.user_roles = []
    return user


class TestAdminLoginHotfixRegression(unittest.TestCase):
    """Core regression test suite for dedicated admin login route and security controls."""

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.app_context = app.app_context()
        cls.app_context.push()

        # Mechanical fail-closed barrier on Engine.connect
        # Any attempt to connect to a physical or live database engine immediately fails closed.
        cls._engine_connect_patcher = patch.object(
            sqlalchemy.engine.base.Engine,
            'connect',
            side_effect=RuntimeError("MECHANICAL SAFETY GATE: Unmocked live database engine connection attempted!")
        )
        cls._engine_connect_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._engine_connect_patcher.stop()
        cls.app_context.pop()

    def setUp(self):
        self.client = app.test_client()

    # =========================================================================
    # TIER 1 & TIER 2 ISOLATION PROOF
    # =========================================================================

    def test_00_database_isolation_barrier_active(self):
        """Verify that Engine.connect is intercepted and fails closed if any live DB call occurs."""
        with self.assertRaises(RuntimeError) as ctx:
            from pkg.models import db
            db.engine.connect()
        self.assertIn("MECHANICAL SAFETY GATE", str(ctx.exception))

    # =========================================================================
    # ROUTE REGISTRATION & GET DISCOVERY
    # =========================================================================

    def test_01_admin_login_get_both_slashes_render_200(self):
        """Verify GET /admin/login and /admin/login/ both return HTTP 200 with admin UI."""
        res1 = self.client.get('/admin/login')
        self.assertEqual(res1.status_code, 200)
        self.assertIn(b"Odacity Admin", res1.data)
        self.assertIn(b"Command Centre", res1.data)
        self.assertIn(b"Administrative Email", res1.data)
        self.assertIn(b"Password", res1.data)

        res2 = self.client.get('/admin/login/')
        self.assertEqual(res2.status_code, 200)
        self.assertIn(b"Odacity Admin", res2.data)
        self.assertIn(b"Command Centre", res2.data)
        self.assertIn(b"Administrative Email", res2.data)

    def test_02_template_uses_local_static_assets_no_cdn(self):
        """Verify admin login page uses local Odacity static assets and zero external CDN links."""
        res = self.client.get('/admin/login')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Local static asset references
        self.assertIn("/static/bootstrap/css/bootstrap.min.css", html)
        self.assertIn("/static/bootstrap-icons/font/bootstrap-icons.min.css", html)
        self.assertIn("/static/bootstrap/js/bootstrap.bundle.min.js", html)

        # Zero external CDN links
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertNotIn("unpkg.com", html)
        self.assertNotIn("cdnjs.cloudflare.com", html)

    def test_03_unauthenticated_protected_route_redirects_to_admin_login(self):
        """Verify unauthenticated access to @admin_view_required redirects to /admin/login with next."""
        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/admin/login', res.headers['Location'])
        self.assertIn('next=', res.headers['Location'])

    # =========================================================================
    # SUCCESSFUL AUTHENTICATION & ROLE AUTHORIZATION
    # =========================================================================

    def test_04_super_admin_login_success(self):
        """Verify active Super Admin authenticates, logs ADMIN_LOGIN_SUCCESS, sets session, and redirects."""
        admin_user = _make_mock_user(
            user_id=1,
            email="superadmin@odacityng.com",
            password="CorrectPassword123!",
            is_active=True,
            is_super_admin=True,
            full_name="Super Administrator"
        )

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session') as mock_session:
            mock_query.filter_by.return_value.first.return_value = admin_user

            res = self.client.post('/admin/login', data={
                'email': 'superadmin@odacityng.com',
                'password': 'CorrectPassword123!'
            })

            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

            with self.client.session_transaction() as sess:
                self.assertEqual(sess.get('user_id'), 1)

            mock_session.add.assert_called()
            added_event = mock_session.add.call_args[0][0]
            self.assertEqual(added_event.event_type, 'ADMIN_LOGIN_SUCCESS')
            self.assertEqual(added_event.user_id, 1)
            mock_session.commit.assert_called()

    def test_05_property_admin_role_login_success(self):
        """Verify active Property Admin authenticates via assigned role in ADMIN_ROLES."""
        prop_admin = _make_mock_user(
            user_id=2,
            email="propertyadmin@odacityng.com",
            password="PropertyPass123!",
            is_active=True,
            is_super_admin=False,
            role_names=["Property Admin"],
            full_name="Property Administrator"
        )

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session') as mock_session:
            mock_query.filter_by.return_value.first.return_value = prop_admin

            res = self.client.post('/admin/login/', data={
                'email': 'propertyadmin@odacityng.com',
                'password': 'PropertyPass123!'
            })

            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

            with self.client.session_transaction() as sess:
                self.assertEqual(sess.get('user_id'), 2)

            mock_session.add.assert_called()
            added_event = mock_session.add.call_args[0][0]
            self.assertEqual(added_event.event_type, 'ADMIN_LOGIN_SUCCESS')
            self.assertEqual(added_event.user_id, 2)

    def test_06_session_cleared_before_login(self):
        """Verify session is cleared before new administrative credentials are bound (fixation defense)."""
        admin_user = _make_mock_user(user_id=10)

        with self.client.session_transaction() as sess:
            sess['stale_key'] = 'stale_value'
            sess['user_id'] = 999

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            res = self.client.post('/admin/login', data={
                'email': 'superadmin@odacityng.com',
                'password': 'CorrectPassword123!'
            })

            self.assertEqual(res.status_code, 302)
            with self.client.session_transaction() as sess:
                self.assertNotIn('stale_key', sess)
                self.assertEqual(sess.get('user_id'), 10)

    # =========================================================================
    # REDIRECT VALIDATION & ADVERSARIAL CATEGORIES
    # =========================================================================

    def test_07_valid_relative_next_redirect_with_query_parameters(self):
        """Verify authorized admin is redirected to safe relative 'next' destination including paths and queries."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            for valid_dest in [
                '/admin/properties',
                '/admin/intents?filter=active',
                '/admin/users?email=superadmin@odacityng.com',
                '/admin/transactions'
            ]:
                res = self.client.post(f'/admin/login?next={valid_dest}', data={
                    'email': 'superadmin@odacityng.com',
                    'password': 'CorrectPassword123!'
                })
                self.assertEqual(res.status_code, 302)
                self.assertEqual(res.headers['Location'], valid_dest)

    def test_08_missing_next_parameter_defaults_to_dashboard(self):
        """Verify missing or empty next parameter safely falls back to dashboard."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            res = self.client.post('/admin/login', data={
                'email': 'superadmin@odacityng.com',
                'password': 'CorrectPassword123!'
            })

            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

    def test_09_open_redirect_protocol_relative_rejected(self):
        """Verify protocol-relative URLs (//evil.com, ///evil.com) are rejected."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            for payload in ['//evil.com/phish', '///evil.com', '////evil.com/test']:
                res = self.client.post(f'/admin/login?next={payload}', data={
                    'email': 'superadmin@odacityng.com',
                    'password': 'CorrectPassword123!'
                })
                self.assertEqual(res.status_code, 302)
                self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

    def test_10_open_redirect_backslash_rejected(self):
        r"""Verify backslash-based authority confusion (/\evil.com, /\\evil.com, /test\evil.com) rejected."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            for payload in [r'/\evil.com', r'/\\evil.com', '/\\', r'/admin\evil.com']:
                res = self.client.post(f'/admin/login?next={payload}', data={
                    'email': 'superadmin@odacityng.com',
                    'password': 'CorrectPassword123!'
                })
                self.assertEqual(res.status_code, 302)
                self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

    def test_11_open_redirect_absolute_url_and_schemes_rejected(self):
        """Verify external absolute URLs and non-HTTP schemes are rejected."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            for payload in ['https://evil.com/admin', 'http://attacker.com', 'javascript:alert(1)', 'data:text/html,evil']:
                res = self.client.post(f'/admin/login?next={payload}', data={
                    'email': 'superadmin@odacityng.com',
                    'password': 'CorrectPassword123!'
                })
                self.assertEqual(res.status_code, 302)
                self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

    def test_12_open_redirect_control_characters_rejected(self):
        """Verify URLs with CR/LF or control characters are rejected."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            for payload in ['/admin%0d%0aLocation:http://evil.com', '/admin%00evil', '/admin%09secret']:
                res = self.client.post(f'/admin/login?next={payload}', data={
                    'email': 'superadmin@odacityng.com',
                    'password': 'CorrectPassword123!'
                })
                self.assertEqual(res.status_code, 302)
                self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

    def test_13_open_redirect_percent_encoded_and_normalization_rejected(self):
        """Verify percent-encoded slashes, backslashes, and repeated encoding are rejected."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            for payload in ['/%2fevil.com', '/%5cevil.com', '/admin%2f%2fevil.com', '/%%32%66evil.com']:
                res = self.client.post(f'/admin/login?next={payload}', data={
                    'email': 'superadmin@odacityng.com',
                    'password': 'CorrectPassword123!'
                })
                self.assertEqual(res.status_code, 302)
                self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

    def test_14_open_redirect_malformed_percent_escapes_rejected(self):
        """Verify malformed percent escapes (incomplete, non-hex) are rejected."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            for payload in ['/%', '/%a', '/%zz', '/%G1', '/%u002f', '/admin%2']:
                res = self.client.post(f'/admin/login?next={payload}', data={
                    'email': 'superadmin@odacityng.com',
                    'password': 'CorrectPassword123!'
                })
                self.assertEqual(res.status_code, 302)
                self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

    def test_15_open_redirect_userinfo_and_colons_rejected(self):
        """Verify user-info markers and colons in path are rejected."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            for payload in ['/@evil.com', '/:evil.com', '/admin@evil.com', '/admin:80']:
                res = self.client.post(f'/admin/login?next={payload}', data={
                    'email': 'superadmin@odacityng.com',
                    'password': 'CorrectPassword123!'
                })
                self.assertEqual(res.status_code, 302)
                self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

    def test_16_open_redirect_excessive_length_rejected(self):
        """Verify excessively long next parameters (>1024 chars) are rejected."""
        admin_user = _make_mock_user()
        long_payload = '/' + 'a' * 2000

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            res = self.client.post(f'/admin/login?next={long_payload}', data={
                'email': 'superadmin@odacityng.com',
                'password': 'CorrectPassword123!'
            })
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers['Location'].rstrip('/'), '/admin/dashboard')

    def test_17_redirect_validator_unit_matrix(self):
        """Unit test the is_safe_admin_redirect_target helper directly on edge cases."""
        # Valid relative targets
        self.assertTrue(is_safe_admin_redirect_target('/admin/dashboard'))
        self.assertTrue(is_safe_admin_redirect_target('/admin/intents?filter=active'))
        self.assertTrue(is_safe_admin_redirect_target('/admin/users?email=test@example.com'))
        self.assertTrue(is_safe_admin_redirect_target('/admin/dashboard#analytics'))

        # Empty / whitespace / None
        self.assertFalse(is_safe_admin_redirect_target(None))
        self.assertFalse(is_safe_admin_redirect_target(''))
        self.assertFalse(is_safe_admin_redirect_target('   '))
        self.assertFalse(is_safe_admin_redirect_target('/admin path with space'))

        # External / scheme / protocol-relative
        self.assertFalse(is_safe_admin_redirect_target('https://evil.com'))
        self.assertFalse(is_safe_admin_redirect_target('//evil.com'))
        self.assertFalse(is_safe_admin_redirect_target('///evil.com'))
        self.assertFalse(is_safe_admin_redirect_target('javascript:alert(1)'))

        # Backslashes
        self.assertFalse(is_safe_admin_redirect_target(r'/\evil.com'))
        self.assertFalse(is_safe_admin_redirect_target(r'/admin\path'))

        # Percent encoded hostile
        self.assertFalse(is_safe_admin_redirect_target('/admin%2fphish'))
        self.assertFalse(is_safe_admin_redirect_target('/admin%5cphish'))
        self.assertFalse(is_safe_admin_redirect_target('/admin%00evil'))

        # Malformed percent escapes
        self.assertFalse(is_safe_admin_redirect_target('/%'))
        self.assertFalse(is_safe_admin_redirect_target('/%a'))
        self.assertFalse(is_safe_admin_redirect_target('/%zz'))
        self.assertFalse(is_safe_admin_redirect_target('/%G1'))

        # Userinfo / colons in path
        self.assertFalse(is_safe_admin_redirect_target('/@evil.com'))
        self.assertFalse(is_safe_admin_redirect_target('/:evil.com'))
        self.assertFalse(is_safe_admin_redirect_target('/admin:80'))

        # Control characters and length
        self.assertFalse(is_safe_admin_redirect_target('/admin\r\nHeader: injection'))
        self.assertFalse(is_safe_admin_redirect_target('/' + 'b' * 1050))

    # =========================================================================
    # REJECTION INVARIANTS & SECURITY EVENT AUDITING
    # =========================================================================

    def test_18_invalid_password_rejected(self):
        """Verify wrong password returns error, logs ADMIN_LOGIN_FAILED, and creates no session."""
        admin_user = _make_mock_user(user_id=1, email="superadmin@odacityng.com", password="CorrectPassword123!")

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session') as mock_session:
            mock_query.filter_by.return_value.first.return_value = admin_user

            res = self.client.post('/admin/login', data={
                'email': 'superadmin@odacityng.com',
                'password': 'WrongPassword456!'
            })

            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Invalid email or password", res.data)

            with self.client.session_transaction() as sess:
                self.assertNotIn('user_id', sess)

            mock_session.add.assert_called()
            added_event = mock_session.add.call_args[0][0]
            self.assertEqual(added_event.event_type, 'ADMIN_LOGIN_FAILED')
            self.assertEqual(added_event.user_id, 1)

    def test_19_missing_credentials_rejected(self):
        """Verify missing email or password fails safely without crash."""
        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session') as mock_session:
            mock_query.filter_by.return_value.first.return_value = None

            res = self.client.post('/admin/login', data={
                'email': '',
                'password': ''
            })

            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Invalid email or password", res.data)
            with self.client.session_transaction() as sess:
                self.assertNotIn('user_id', sess)

    def test_20_nonexistent_user_rejected(self):
        """Verify non-existent email returns generic error and creates no session."""
        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session') as mock_session:
            mock_query.filter_by.return_value.first.return_value = None

            res = self.client.post('/admin/login', data={
                'email': 'ghost@odacityng.com',
                'password': 'SomePassword123!'
            })

            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Invalid email or password", res.data)

            with self.client.session_transaction() as sess:
                self.assertNotIn('user_id', sess)
            mock_session.add.assert_not_called()

    def test_21_inactive_admin_rejected(self):
        """Verify inactive admin account is rejected with warning and creates no session."""
        inactive_admin = _make_mock_user(
            user_id=3,
            email="inactive@odacityng.com",
            password="CorrectPassword123!",
            is_active=False,
            is_super_admin=True
        )

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session') as mock_session:
            mock_query.filter_by.return_value.first.return_value = inactive_admin

            res = self.client.post('/admin/login', data={
                'email': 'inactive@odacityng.com',
                'password': 'CorrectPassword123!'
            })

            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Your administrative account is currently inactive", res.data)

            with self.client.session_transaction() as sess:
                self.assertNotIn('user_id', sess)

    def test_22_non_admin_user_rejected(self):
        """Verify non-admin ordinary user is rejected, logs ADMIN_LOGIN_DENIED_NON_ADMIN, no session."""
        normal_user = _make_mock_user(
            user_id=4,
            email="customer@example.com",
            password="UserPassword123!",
            is_active=True,
            is_super_admin=False,
            role_names=[]  # No admin roles
        )

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session') as mock_session:
            mock_query.filter_by.return_value.first.return_value = normal_user

            res = self.client.post('/admin/login', data={
                'email': 'customer@example.com',
                'password': 'UserPassword123!'
            })

            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Administrative privileges are required to access this portal", res.data)

            with self.client.session_transaction() as sess:
                self.assertNotIn('user_id', sess)

            mock_session.add.assert_called()
            added_event = mock_session.add.call_args[0][0]
            self.assertEqual(added_event.event_type, 'ADMIN_LOGIN_DENIED_NON_ADMIN')
            self.assertEqual(added_event.user_id, 4)

    # =========================================================================
    # PERMISSION DENIED FOR AUTHENTICATED NON-ADMIN
    # =========================================================================

    def test_23_authenticated_non_admin_denied_dashboard_access(self):
        """Verify an authenticated customer attempting to access /admin/dashboard is denied."""
        normal_user = _make_mock_user(user_id=55, is_super_admin=False, role_names=[])

        with self.client.session_transaction() as sess:
            sess['user_id'] = 55

        with patch('pkg.routes.admin.User.query') as mock_query:
            mock_query.get.return_value = normal_user

            res = self.client.get('/admin/dashboard')
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers['Location'].rstrip('/'), '/dashboard')

    # =========================================================================
    # NORMAL USER LOGIN COMPATIBILITY
    # =========================================================================

    def test_24_normal_user_login_compatibility(self):
        """Verify normal customer login flow on /login/ remains functional."""
        res = self.client.get('/login/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Log In", res.data)

    # =========================================================================
    # FAIL-CLOSED AUDIT LOGGING POLICY ENFORCEMENT
    # =========================================================================

    def test_25_security_event_success_commit_failure_fails_closed(self):
        """Verify database commit failure during ADMIN_LOGIN_SUCCESS rolls back, clears session, and fails closed."""
        admin_user = _make_mock_user()

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session') as mock_session:
            mock_query.filter_by.return_value.first.return_value = admin_user
            mock_session.commit.side_effect = Exception("Simulated durable audit commit failure")

            res = self.client.post('/admin/login', data={
                'email': 'superadmin@odacityng.com',
                'password': 'CorrectPassword123!'
            })

            # Must return 200 re-rendering login, NOT redirect to dashboard
            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Authentication failed due to an internal audit logging error", res.data)

            # Rollback must be explicitly executed
            mock_session.rollback.assert_called()

            # Session MUST NOT contain user_id (Fail-Closed Enforcement)
            with self.client.session_transaction() as sess:
                self.assertNotIn('user_id', sess)


class TestAdminLoginCSRFProtection(unittest.TestCase):
    """
    Focused test suite verifying real CSRF token enforcement using Flask-WTF.
    Tests active WTF_CSRF_ENABLED with missing, invalid, and valid tokens.
    """

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = True
        cls.app_context = app.app_context()
        cls.app_context.push()

        # Mechanical fail-closed barrier on Engine.connect
        cls._engine_connect_patcher = patch.object(
            sqlalchemy.engine.base.Engine,
            'connect',
            side_effect=RuntimeError("MECHANICAL SAFETY GATE: Unmocked live database engine connection attempted!")
        )
        cls._engine_connect_patcher.start()

    @classmethod
    def tearDownClass(cls):
        app.config['WTF_CSRF_ENABLED'] = False
        cls._engine_connect_patcher.stop()
        cls.app_context.pop()

    def setUp(self):
        self.client = app.test_client()
        # Ensure fresh CSRF generation per test client by clearing any cached token on g
        if hasattr(flask.g, 'csrf_token'):
            del flask.g.csrf_token

    def _extract_csrf_token(self, response):
        """Extract CSRF token from HTML form response."""
        html = response.data.decode('utf-8')
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        self.assertIsNotNone(match, "CSRF token hidden input field not found in response HTML")
        return match.group(1)

    def test_26_csrf_missing_token_rejected_with_400(self):
        """Verify POST /admin/login without CSRF token is rejected with HTTP 400 Bad Request."""
        res = self.client.post('/admin/login', data={
            'email': 'superadmin@odacityng.com',
            'password': 'CorrectPassword123!'
        })
        self.assertEqual(res.status_code, 400)
        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)

    def test_27_csrf_invalid_token_rejected_with_400(self):
        """Verify POST /admin/login with invalid/tampered CSRF token is rejected with HTTP 400 Bad Request."""
        res = self.client.post('/admin/login', data={
            'email': 'superadmin@odacityng.com',
            'password': 'CorrectPassword123!',
            'csrf_token': 'adversarial-tampered-csrf-token-xyz'
        })
        self.assertEqual(res.status_code, 400)
        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)

    def test_28_csrf_valid_token_allows_successful_admin_auth(self):
        """Verify POST /admin/login with valid CSRF token successfully authenticates administrator."""
        # Step 1: GET /admin/login to obtain valid session-bound CSRF token
        get_res = self.client.get('/admin/login')
        self.assertEqual(get_res.status_code, 200)
        csrf_token = self._extract_csrf_token(get_res)

        admin_user = _make_mock_user(user_id=1, is_super_admin=True)

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session') as mock_session:
            mock_query.filter_by.return_value.first.return_value = admin_user

            # Step 2: POST with valid credentials and valid CSRF token
            post_res = self.client.post('/admin/login', data={
                'email': 'superadmin@odacityng.com',
                'password': 'CorrectPassword123!',
                'csrf_token': csrf_token
            })

            self.assertEqual(post_res.status_code, 302)
            self.assertEqual(post_res.headers['Location'].rstrip('/'), '/admin/dashboard')

            with self.client.session_transaction() as sess:
                self.assertEqual(sess.get('user_id'), 1)

            mock_session.commit.assert_called()

    def test_29_csrf_valid_token_with_invalid_credentials_rejected_with_200(self):
        """Verify POST /admin/login with valid CSRF token but bad credentials fails authentication."""
        get_res = self.client.get('/admin/login')
        self.assertEqual(get_res.status_code, 200)
        csrf_token = self._extract_csrf_token(get_res)

        admin_user = _make_mock_user(user_id=1, password="CorrectPassword123!")

        with patch('pkg.routes.admin.User.query') as mock_query, \
             patch('pkg.routes.admin.db.session'):
            mock_query.filter_by.return_value.first.return_value = admin_user

            post_res = self.client.post('/admin/login', data={
                'email': 'superadmin@odacityng.com',
                'password': 'WrongPassword999!',
                'csrf_token': csrf_token
            })

            self.assertEqual(post_res.status_code, 200)
            self.assertIn(b"Invalid email or password", post_res.data)

            with self.client.session_transaction() as sess:
                self.assertNotIn('user_id', sess)


if __name__ == '__main__':
    unittest.main()

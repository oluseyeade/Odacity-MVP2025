"""
Phase 26 Executive Control Centre & Task Centre Verification Script
Tests Operations view, Performance view, Task Centre feed, period selectors, and authorization safeguards.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))

from pkg import app
from pkg.models import User, Role, UserRole

def run_phase26_verification():
    print("==================================================")
    print("PHASE 26 — CONTROLLED IMPLEMENTATION VERIFICATION")
    print("==================================================")

    client = app.test_client()

    with app.app_context():
        # Identify superadmin and non-superadmin users
        super_user = User.query.filter_by(is_super_admin=True).first()
        non_admin_user = User.query.filter(User.is_super_admin == False, ~User.user_roles.any()).first()

        print(f"Superadmin User ID: {super_user.user_id} ({super_user.email})")
        print(f"Non-admin User ID: {non_admin_user.user_id} ({non_admin_user.email})")

    # 1. Test Operations View
    print("\n--- 1. Testing OPERATIONS View ---")
    with client.session_transaction() as sess:
        sess['user_id'] = super_user.user_id

    res_ops = client.get('/admin/?view=operations')
    assert res_ops.status_code == 200, f"Expected 200, got {res_ops.status_code}"
    assert b"SUPER ADMIN TASK CENTRE" in res_ops.data, "Missing Task Centre header in Operations view"
    assert b"Odacity Executive Control Centre" in res_ops.data, "Missing Executive Control Centre header"
    print("PASS: Operations View rendered HTTP 200 with Task Centre.")

    # 2. Test Performance View
    print("\n--- 2. Testing PERFORMANCE View ---")
    res_perf = client.get('/admin/?view=performance')
    assert res_perf.status_code == 200, f"Expected 200, got {res_perf.status_code}"
    assert b"ODACITY PERFORMANCE SNAPSHOT" in res_perf.data, "Missing Performance Snapshot header"
    assert b"Verification Coverage" in res_perf.data, "Missing Performance Indices section"
    print("PASS: Performance View rendered HTTP 200 with Investor Snapshot & Indices.")

    # 3. Test Timeframe Period Filtering
    print("\n--- 3. Testing Period Selection Filters ---")
    for p in ['7d', '30d', '90d', '12m', 'all']:
        res_p = client.get(f'/admin/?view=performance&period={p}')
        assert res_p.status_code == 200, f"Period {p} failed with status {res_p.status_code}"
        print(f"  Period '{p}': HTTP 200 OK")
    print("PASS: All period filters rendered successfully.")

    # 4. Test Task Centre JSON Endpoint
    print("\n--- 4. Testing Task Centre JSON Feed ---")
    res_tasks = client.get('/admin/task-centre/')
    assert res_tasks.status_code == 200, f"Task feed failed with status {res_tasks.status_code}"
    assert res_tasks.content_type == 'application/json', "Expected application/json response"
    json_data = res_tasks.get_json()
    assert 'tasks' in json_data and 'counts' in json_data, "Invalid task feed JSON payload structure"
    print(f"PASS: Task Centre API returned {json_data['counts']['total']} total tasks ({json_data['counts']['critical']} critical).")

    # 5. Test Authorization Safeguards for Non-Superadmin
    print("\n--- 5. Testing Non-Superadmin Authorization Safeguards ---")
    client_non_admin = app.test_client()
    with client_non_admin.session_transaction() as sess:
        sess['user_id'] = non_admin_user.user_id

    res_blocked_ops = client_non_admin.get('/admin/?view=operations')
    assert res_blocked_ops.status_code == 302, f"Expected 302 redirect for non-admin, got {res_blocked_ops.status_code}"

    res_blocked_tasks = client_non_admin.get('/admin/task-centre/')
    assert res_blocked_tasks.status_code == 302, f"Expected 302 redirect for non-admin task feed, got {res_blocked_tasks.status_code}"
    print("PASS: Non-superadmin access strictly denied with HTTP 302 redirect.")

    # 6. Verify Total Registered Routes Count
    print("\n--- 6. Testing Total Route Count & Protection ---")
    with app.app_context():
        routes_count = len(list(app.url_map.iter_rules()))
        print(f"Total Registered Flask Routes: {routes_count} (Expected 103)")
        assert routes_count == 103, f"Expected 103 routes, got {routes_count}"

    print("\n==================================================")
    print("ALL PHASE 26 VERIFICATION CHECKS PASSED PERFECTLY!")
    print("==================================================")

if __name__ == '__main__':
    run_phase26_verification()

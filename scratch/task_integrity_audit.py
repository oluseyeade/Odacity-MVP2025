"""
Task Integrity Audit Script for Super Admin Task Centre
"""
import sys
import os
sys.path.insert(0, os.path.abspath("."))

from pkg import app
from pkg.services.admin_overview import get_superadmin_tasks

def run_task_integrity_audit():
    with app.app_context():
        res = get_superadmin_tasks()
        tasks = res['tasks']
        counts = res['counts']

        print(f"Total Derived Tasks: {counts['total']}")
        print(f"Critical: {counts['critical']} | High: {counts['high']} | Normal: {counts['normal']} | Low: {counts['low']}\n")
        print(f"{'task_type':<25} | {'task_id':<18} | {'source_model':<18} | {'source_id':<10} | {'current_status':<15} | {'action_url':<45} | {'responsible_role'}")
        print("-" * 170)

        for t in tasks:
            print(f"{t['task_type']:<25} | {t['task_id']:<18} | {t['entity_type']:<18} | {str(t['entity_id']):<10} | {t['status']:<15} | {t['action_url']:<45} | {t['responsible_role']}")

if __name__ == '__main__':
    run_task_integrity_audit()

"""
Test GET URLs script
"""
import sys
import os
sys.path.insert(0, os.path.abspath("."))

from pkg import app
import pkg.routes.admin
from pkg.models import User, VerificationCase, Property, Inspection, Offer, Invoice, GoldReward, GuaranteeSettlement

def run_test():
    client = app.test_client()

    with app.app_context():
        super_user = User.query.filter_by(is_super_admin=True).first()
        first_vc = VerificationCase.query.filter(
            VerificationCase.status == 'Submitted',
            VerificationCase.entity_type.in_(['dab_institution', 'dab_agent', 'dab_individual', 'general_enquiry'])
        ).first()
        first_prop = Property.query.filter(Property.status.in_(['Under Verification', 'Submitted'])).first()
        first_insp = Inspection.query.filter_by(status='Requested').first()
        first_offer = Offer.query.filter_by(status='Submitted').first()
        first_inv = Invoice.query.first()
        first_wdraw = GoldReward.query.filter_by(reward_type='WITHDRAWAL', status='REQUESTED').first()
        first_settle = GuaranteeSettlement.query.filter_by(status='Pending').first()

        print("First VC ID:", first_vc.verification_case_id if first_vc else None)
        print("First Prop ID:", first_prop.property_id if first_prop else None)
        print("First Insp ID:", first_insp.inspection_id if first_insp else None)
        print("First Offer ID:", first_offer.offer_id if first_offer else None)
        print("First Inv ID:", first_inv.invoice_id if first_inv else None)
        print("First Withdrawal ID:", first_wdraw.gold_reward_id if first_wdraw else None)
        print("First Settlement ID:", first_settle.id if first_settle else None)

    with client.session_transaction() as sess:
        sess['user_id'] = super_user.user_id

    test_cases = []
    if first_vc:
        test_cases.append(("INTENT_REVIEW", f"/admin/intents/{first_vc.verification_case_id}/", str(first_vc.verification_case_id)))
    if first_prop:
        test_cases.append(("PROPERTY_VERIFICATION", f"/admin/intents/?property_id={first_prop.property_id}", str(first_prop.property_id)))
    if first_insp:
        test_cases.append(("INSPECTION_SCHEDULE", f"/admin/inspections/?inspection_id={first_insp.inspection_id}", str(first_insp.inspection_id)))
    if first_offer:
        test_cases.append(("OFFER_REVIEW", f"/admin/offers/?offer_id={first_offer.offer_id}", str(first_offer.offer_id)))
    if first_inv:
        test_cases.append(("INVOICE_ACTION", f"/admin/transactions/?invoice_id={first_inv.invoice_id}", str(first_inv.invoice_id)))
    if first_wdraw:
        test_cases.append(("WITHDRAWAL_PAYOUT", f"/admin/referrals/?reward_id={first_wdraw.gold_reward_id}", str(first_wdraw.gold_reward_id)))
    if first_settle:
        test_cases.append(("SETTLEMENT_APPROVAL", f"/admin/performance/?settlement_id={first_settle.id}", str(first_settle.id)))

    for cat, url, rec_id in test_cases:
        res = client.get(url)
        html = res.data.decode('utf-8', errors='ignore')
        print(f"\n=== {cat} GET {url} ===")
        print(f"Status Code: {res.status_code}")
        print(f"HTML contains record ID '{rec_id}': {rec_id in html}")

if __name__ == '__main__':
    run_test()

"""
Odacity MVP 2025 - Admin Overview & Executive Control Centre Service
Provides database-backed aggregation, metrics calculation, investor performance reporting,
and real-time auto-disappearing Super Admin task queue derivation.
"""

from datetime import datetime, timedelta
from sqlalchemy import func, or_, and_
from pkg.models import (
    db, User, Role, UserRole, CustomerProfile, PropertyOwnerProfile,
    Property, DirectAssetBrief, VerificationCase, PropertyDocument, PropertyMedia,
    Inspection, Offer, Negotiation, Transaction, TransactionDocument, Invoice, Payment,
    PerformanceGuarantee, GuaranteeSettlement, Referral, ReferralReward, GoldReward,
    AuditLog, SecurityEvent, Notification
)


def get_reporting_window(period_code='30d'):
    """
    Computes timeframe boundaries for reporting based on selected period code.
    Returns (start_date, prev_start_date, prev_end_date, insufficient_history_flag).
    """
    now = datetime.utcnow()
    period_code = (period_code or '30d').strip().lower()
    insufficient_history = False

    if period_code == '7d':
        days = 7
        start_date = now - timedelta(days=7)
    elif period_code == '90d':
        days = 90
        start_date = now - timedelta(days=90)
    elif period_code == '12m':
        days = 365
        start_date = now - timedelta(days=365)
        # Database history check: Earliest record is ~60 days old
        insufficient_history = True
    elif period_code == 'all':
        days = None
        start_date = None
    else:  # 30d default
        period_code = '30d'
        days = 30
        start_date = now - timedelta(days=30)

    if days and start_date:
        prev_end_date = start_date
        prev_start_date = start_date - timedelta(days=days)
    else:
        prev_start_date = None
        prev_end_date = None

    return {
        'code': period_code,
        'now': now,
        'start_date': start_date,
        'prev_start_date': prev_start_date,
        'prev_end_date': prev_end_date,
        'insufficient_history': insufficient_history
    }


def _calc_pct_change(curr, prev):
    """Safely calculates absolute and percentage change between two values."""
    abs_change = curr - prev
    if prev and prev > 0:
        pct_change = round(((curr - prev) / float(prev)) * 100.0, 1)
        pct_str = f"{'+' if pct_change > 0 else ''}{pct_change}%"
    else:
        pct_change = None
        pct_str = 'N/A'
    return {
        'abs_change': abs_change,
        'pct_change': pct_change,
        'pct_str': pct_str
    }


def get_business_snapshot(period_code='30d', user=None):
    """
    Computes lifetime and period-scoped business metrics from database models.
    Returns structured KPI dictionary.
    """
    win = get_reporting_window(period_code)
    start_date = win['start_date']
    prev_start = win['prev_start_date']
    prev_end = win['prev_end_date']

    # 1. USER METRICS
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    admin_users_count = User.query.filter((User.is_super_admin == True) | (User.user_roles.any())).count()
    owner_profiles_count = PropertyOwnerProfile.query.count()

    if start_date:
        new_users_curr = User.query.filter(User.created_at >= start_date).count()
    else:
        new_users_curr = total_users

    if prev_start and prev_end:
        new_users_prev = User.query.filter(and_(User.created_at >= prev_start, User.created_at < prev_end)).count()
    else:
        new_users_prev = 0

    user_growth_change = _calc_pct_change(new_users_curr, new_users_prev)

    # 2. ASSET & DAB METRICS
    total_dabs = DirectAssetBrief.query.count()
    pending_dabs = VerificationCase.query.filter_by(status='Submitted').count()
    approved_dabs = VerificationCase.query.filter_by(status='Passed').count()

    dab_q_curr = DirectAssetBrief.query.filter(DirectAssetBrief.submitted_at.isnot(None))
    if start_date:
        dab_q_curr = dab_q_curr.filter(DirectAssetBrief.submitted_at >= start_date)
    dabs_curr = dab_q_curr.count()

    if prev_start and prev_end:
        dabs_prev = DirectAssetBrief.query.filter(and_(DirectAssetBrief.submitted_at >= prev_start, DirectAssetBrief.submitted_at < prev_end)).count()
    else:
        dabs_prev = 0

    dab_growth_change = _calc_pct_change(dabs_curr, dabs_prev)

    total_props = Property.query.count()
    unverified_props = Property.query.filter_by(publication_status='Under Verification').count()
    published_props = Property.query.filter(Property.publication_status.in_(['Available', 'Approved', 'Public Listing', 'Private Listing'])).count()
    reserved_props = Property.query.filter_by(publication_status='Reserved').count()

    prop_q_curr = Property.query
    if start_date:
        prop_q_curr = prop_q_curr.filter(Property.created_at >= start_date)
    props_curr = prop_q_curr.count()

    if prev_start and prev_end:
        props_prev = Property.query.filter(and_(Property.created_at >= prev_start, Property.created_at < prev_end)).count()
    else:
        props_prev = 0

    prop_growth_change = _calc_pct_change(props_curr, props_prev)

    # 3. TRANSACTION METRICS (Authoritative terminal completed states: Completion, Completed)
    active_txs = Transaction.query.filter(~Transaction.status.in_(['Completion', 'Completed', 'Cancelled'])).count()

    completed_tx_curr_q = Transaction.query.filter(Transaction.status.in_(['Completion', 'Completed']))
    val_curr_q = db.session.query(func.sum(Transaction.transaction_value)).filter(Transaction.status.in_(['Completion', 'Completed']))
    comm_expr = func.sum(func.coalesce(Transaction.odacity_commission_amount, 0.0))
    comm_curr_q = db.session.query(comm_expr).filter(Transaction.status.in_(['Completion', 'Completed']))

    if start_date:
        completed_tx_curr_q = completed_tx_curr_q.filter(Transaction.created_at >= start_date)
        val_curr_q = val_curr_q.filter(Transaction.created_at >= start_date)
        comm_curr_q = comm_curr_q.filter(Transaction.created_at >= start_date)

    completed_txs_curr = completed_tx_curr_q.count()
    val_curr_sum = val_curr_q.scalar()
    tx_val_curr = float(val_curr_sum) if val_curr_sum else 0.0

    comm_curr_sum = comm_curr_q.scalar()
    commission_curr = float(comm_curr_sum) if comm_curr_sum else 0.0

    if prev_start and prev_end:
        completed_txs_prev = Transaction.query.filter(and_(Transaction.status.in_(['Completion', 'Completed']), Transaction.created_at >= prev_start, Transaction.created_at < prev_end)).count()
        val_prev_sum = db.session.query(func.sum(Transaction.transaction_value)).filter(and_(Transaction.status.in_(['Completion', 'Completed']), Transaction.created_at >= prev_start, Transaction.created_at < prev_end)).scalar()
        tx_val_prev = float(val_prev_sum) if val_prev_sum else 0.0
    else:
        completed_txs_prev = 0
        tx_val_prev = 0.0

    tx_count_change = _calc_pct_change(completed_txs_curr, completed_txs_prev)
    tx_val_change = _calc_pct_change(tx_val_curr, tx_val_prev)

    # 4. INSPECTIONS & OFFERS
    requested_inspections = Inspection.query.filter_by(status='Requested').count()
    scheduled_inspections = Inspection.query.filter_by(status='Scheduled').count()

    insp_q_curr = Inspection.query.filter(Inspection.requested_at.isnot(None))
    if start_date:
        insp_q_curr = insp_q_curr.filter(Inspection.requested_at >= start_date)
    inspections_curr = insp_q_curr.count()

    submitted_offers = Offer.query.filter(Offer.status.in_(['Submitted', 'Under_Review'])).count()

    offer_q_curr = Offer.query.filter(Offer.submitted_at.isnot(None))
    if start_date:
        offer_q_curr = offer_q_curr.filter(Offer.submitted_at >= start_date)
    offers_curr = offer_q_curr.count()

    # 5. FINANCIAL & REFERRAL METRICS
    active_guarantees = PerformanceGuarantee.query.filter_by(status='Active').count()

    rew_q = db.session.query(func.sum(ReferralReward.reward_amount)).filter_by(status='Earned')
    ref_q = Referral.query
    if start_date:
        rew_q = rew_q.filter(ReferralReward.created_at >= start_date)
        ref_q = ref_q.filter(Referral.created_at >= start_date)

    rew_sum = rew_q.scalar()
    total_earned_rewards = float(rew_sum) if rew_sum else 0.0
    referrals_curr = ref_q.count()

    # Cash Withdrawal Requests (GoldReward model: reward_type in ('WITHDRAWAL', 'Withdrawal_Cash'), status in ('REQUESTED', 'Pending'))
    w_sum = db.session.query(func.sum(GoldReward.amount)).filter(
        GoldReward.reward_type.in_(['WITHDRAWAL', 'Withdrawal_Cash']),
        GoldReward.status.in_(['REQUESTED', 'Pending'])
    ).scalar()
    pending_withdrawals_sum = float(w_sum) if w_sum else 0.0
    pending_withdrawals_count = GoldReward.query.filter(
        GoldReward.reward_type.in_(['WITHDRAWAL', 'Withdrawal_Cash']),
        GoldReward.status.in_(['REQUESTED', 'Pending'])
    ).count()

    # Actionable Overdue Invoices (Overdue status OR Issued invoices past due date)
    now_dt = datetime.utcnow()
    overdue_invoices_count = Invoice.query.filter(
        or_(
            Invoice.status.in_(['Overdue', 'Partially_Paid']),
            and_(Invoice.status == 'Issued', Invoice.due_date.isnot(None), Invoice.due_date < now_dt)
        )
    ).count()

    # Financial Exposure Calculations
    invoiced_sum = db.session.query(func.sum(Invoice.amount_due)).filter(Invoice.status.in_(['Issued', 'Partially_Paid', 'Overdue', 'Paid'])).scalar()
    total_invoiced = float(invoiced_sum) if invoiced_sum else 0.0

    collected_sum = db.session.query(func.sum(Payment.amount)).filter_by(status='Completed').scalar()
    total_collected = float(collected_sum) if collected_sum else 0.0

    outstanding_balance = max(0.0, total_invoiced - total_collected)

    return {
        'window': win,
        'total_users': total_users,
        'active_users': active_users,
        'admin_users_count': admin_users_count,
        'owner_profiles_count': owner_profiles_count,
        'new_users_curr': new_users_curr,
        'new_users_prev': new_users_prev,
        'user_growth_change': user_growth_change,
        'total_dabs': total_dabs,
        'pending_dabs': pending_dabs,
        'approved_dabs': approved_dabs,
        'dabs_curr': dabs_curr,
        'dab_growth_change': dab_growth_change,
        'total_props': total_props,
        'unverified_props': unverified_props,
        'published_props': published_props,
        'reserved_props': reserved_props,
        'props_curr': props_curr,
        'prop_growth_change': prop_growth_change,
        'active_txs': active_txs,
        'completed_txs_curr': completed_txs_curr,
        'completed_txs_prev': completed_txs_prev,
        'tx_count_change': tx_count_change,
        'tx_val_curr': tx_val_curr,
        'tx_val_prev': tx_val_prev,
        'tx_val_change': tx_val_change,
        'commission_curr': commission_curr,
        'requested_inspections': requested_inspections,
        'scheduled_inspections': scheduled_inspections,
        'inspections_curr': inspections_curr,
        'submitted_offers': submitted_offers,
        'offers_curr': offers_curr,
        'active_guarantees': active_guarantees,
        'total_earned_rewards': total_earned_rewards,
        'referrals_curr': referrals_curr,
        'pending_withdrawals_sum': pending_withdrawals_sum,
        'pending_withdrawals_count': pending_withdrawals_count,
        'overdue_invoices_count': overdue_invoices_count,
        'total_invoiced': total_invoiced,
        'total_collected': total_collected,
        'outstanding_balance': outstanding_balance
    }


def get_superadmin_tasks(user=None):
    """
    Derives real-time operational tasks strictly from current database entity states.
    Tasks auto-disappear when the underlying entity status changes to resolved.
    """
    tasks = []

    # Helper function to get intent detail URL for a DAB
    def get_intent_action_url(dab_id):
        if not dab_id:
            return None
        v_case = VerificationCase.query.filter_by(dab_id=dab_id).first()
        if v_case:
            return f"/admin/intents/{v_case.verification_case_id}/"
        return None

    # 1. Pending DAB / Intent Reviews (VerificationCase status == 'Submitted' AND entity_type IN approved four types) (HIGH)
    v_cases = VerificationCase.query.filter(
        VerificationCase.status == 'Submitted',
        VerificationCase.entity_type.in_(['dab_individual', 'dab_institution', 'dab_agent', 'general_enquiry'])
    ).all()
    for vc in v_cases:
        detail_url = f"/admin/intents/{vc.verification_case_id}/"
        tasks.append({
            'task_id': f"intent_{vc.verification_case_id}",
            'task_type': 'INTENT_REVIEW',
            'title': f"Review Intent Submission #{vc.verification_case_id} ({vc.entity_type or 'DAB'})",
            'description': f"Entity ID: #{vc.entity_id or 'N/A'} | Status: {vc.status}",
            'entity_type': 'VerificationCase',
            'entity_id': vc.verification_case_id,
            'status': vc.status,
            'priority': 'HIGH',
            'created_at': (vc.started_at or vc.created_at).isoformat() if (vc.started_at or vc.created_at) else '',
            'responsible_role': 'Property Admin / Mandate Manager',
            'detail_url': detail_url,
            'action_url': f"/admin/intents/{vc.verification_case_id}/approve/"
        })

    # 2. Unverified Properties (Authoritative Property.status IN ('Under Verification', 'Submitted') AND status != 'Verified') (CRITICAL)
    props = Property.query.filter(
        Property.status.in_(['Under Verification', 'Submitted']),
        Property.status != 'Verified'
    ).all()
    for p in props:
        intent_url = get_intent_action_url(p.dab_id) if p.dab_id else None
        detail_url = intent_url if intent_url else f"/admin/intents/?property_id={p.property_id}"
        tasks.append({
            'task_id': f"prop_{p.property_id}",
            'task_type': 'PROPERTY_VERIFICATION',
            'title': f"Verify Title & Compliance: {p.title}",
            'description': f"Location: {p.state or p.city or 'N/A'} | Price: NGN {p.price:,.2f}",
            'entity_type': 'Property',
            'entity_id': p.property_id,
            'status': p.status,
            'priority': 'CRITICAL',
            'created_at': p.created_at.isoformat() if p.created_at else '',
            'responsible_role': 'Property Admin / Mandate Manager',
            'detail_url': detail_url,
            'action_url': f"/admin/properties/{p.property_id}/verify/"
        })

    # 3. Pending Property Documents (review_status IN ('Pending', 'Submitted')) (HIGH)
    docs = PropertyDocument.query.filter(PropertyDocument.review_status.in_(['Pending', 'Submitted'])).all()
    for doc in docs:
        prop = doc.property
        intent_url = get_intent_action_url(prop.dab_id) if (prop and prop.dab_id) else None
        detail_url = (intent_url + f"#doc-{doc.document_id}") if intent_url else f"/admin/intents/?property_id={prop.property_id if prop else doc.property_id}#doc-{doc.document_id}"
        tasks.append({
            'task_id': f"doc_{doc.document_id}",
            'task_type': 'DOCUMENT_REVIEW',
            'title': f"Verify Document: {doc.document_type} (Property #{doc.property_id})",
            'description': f"Submitted: {doc.submitted_at or doc.created_at} | Status: {doc.review_status}",
            'entity_type': 'PropertyDocument',
            'entity_id': doc.document_id,
            'status': doc.review_status,
            'priority': 'HIGH',
            'created_at': (doc.submitted_at or doc.created_at).isoformat() if (doc.submitted_at or doc.created_at) else '',
            'responsible_role': 'Compliance Admin',
            'detail_url': detail_url,
            'action_url': f"/admin/documents/{doc.document_id}/verify/"
        })

    # 4. Pending Media Reviews (review_status IN ('Pending', 'Uploaded')) (NORMAL)
    medias = PropertyMedia.query.filter(PropertyMedia.review_status.in_(['Pending', 'Uploaded'])).all()
    for m in medias:
        prop = m.property
        intent_url = get_intent_action_url(prop.dab_id) if (prop and prop.dab_id) else None
        detail_url = (intent_url + f"#media-{m.media_id}") if intent_url else f"/admin/intents/?property_id={prop.property_id if prop else m.property_id}#media-{m.media_id}"
        tasks.append({
            'task_id': f"media_{m.media_id}",
            'task_type': 'MEDIA_REVIEW',
            'title': f"Review Property Media #{m.media_id} (Property #{m.property_id})",
            'description': f"Type: {m.media_type or m.type} | Primary: {m.is_primary}",
            'entity_type': 'PropertyMedia',
            'entity_id': m.media_id,
            'status': m.review_status,
            'priority': 'NORMAL',
            'created_at': m.created_at.isoformat() if m.created_at else '',
            'responsible_role': 'Property Admin',
            'detail_url': detail_url,
            'action_url': f"/admin/media/{m.media_id}/review/"
        })

    # 5. Requested Inspections (status == 'Requested') (NORMAL)
    insps = Inspection.query.filter_by(status='Requested').all()
    for i in insps:
        detail_url = f"/admin/inspections/?inspection_id={i.inspection_id}"
        tasks.append({
            'task_id': f"insp_{i.inspection_id}",
            'task_type': 'INSPECTION_SCHEDULE',
            'title': f"Schedule Inspection Booking #{i.inspection_id}",
            'description': f"Property #{i.property_id} | Customer #{i.customer_id} | Notes: {i.notes or 'None'}",
            'entity_type': 'Inspection',
            'entity_id': i.inspection_id,
            'status': i.status,
            'priority': 'NORMAL',
            'created_at': (i.requested_at or i.created_at).isoformat() if (i.requested_at or i.created_at) else '',
            'responsible_role': 'Customer Support / Property Admin',
            'detail_url': detail_url,
            'action_url': f"/admin/inspections/{i.inspection_id}/schedule/"
        })

    # 6. Submitted Buyer Offers (status == 'Submitted') (HIGH)
    offers = Offer.query.filter_by(status='Submitted').all()
    for o in offers:
        detail_url = f"/admin/offers/?offer_id={o.offer_id}"
        tasks.append({
            'task_id': f"offer_{o.offer_id}",
            'task_type': 'OFFER_REVIEW',
            'title': f"Evaluate Buyer Offer #{o.offer_id}: NGN {o.offer_amount:,.2f}",
            'description': f"Property #{o.property_id} | Customer #{o.customer_id} | Status: {o.status}",
            'entity_type': 'Offer',
            'entity_id': o.offer_id,
            'status': o.status,
            'priority': 'HIGH',
            'created_at': (o.submitted_at or o.created_at).isoformat() if (o.submitted_at or o.created_at) else '',
            'responsible_role': 'Mandate Manager / Transaction Manager',
            'detail_url': detail_url,
            'action_url': None
        })

    # 7. Actionable Overdue / Unpaid Invoices (status == 'Overdue' OR past due_date OR Partially_Paid) (CRITICAL)
    now_dt = datetime.utcnow()
    invoices = Invoice.query.filter(
        or_(
            Invoice.status.in_(['Overdue', 'Partially_Paid']),
            and_(Invoice.status == 'Issued', Invoice.due_date.isnot(None), Invoice.due_date < now_dt)
        )
    ).all()
    for inv in invoices:
        detail_url = f"/admin/transactions/?invoice_id={inv.invoice_id}"
        tasks.append({
            'task_id': f"inv_{inv.invoice_id}",
            'task_type': 'INVOICE_ACTION',
            'title': f"Overdue/Unpaid Invoice #{inv.invoice_number or inv.invoice_id}",
            'description': f"Amount Due: NGN {inv.amount_due:,.2f} | Status: {inv.status}",
            'entity_type': 'Invoice',
            'entity_id': inv.invoice_id,
            'status': inv.status,
            'priority': 'CRITICAL',
            'created_at': inv.created_at.isoformat() if inv.created_at else '',
            'responsible_role': 'Finance Admin',
            'detail_url': detail_url,
            'action_url': f"/admin/transactions/{inv.transaction_id}/invoices/{inv.invoice_id}/record-payment/" if inv.transaction_id else None
        })

    # 8. Pending Cash Withdrawals (reward_type == 'WITHDRAWAL' AND status == 'REQUESTED') (HIGH)
    withdrawals = GoldReward.query.filter_by(reward_type='WITHDRAWAL', status='REQUESTED').all()
    for w in withdrawals:
        detail_url = f"/admin/referrals/?reward_id={w.gold_reward_id}"
        tasks.append({
            'task_id': f"wdraw_{w.gold_reward_id}",
            'task_type': 'WITHDRAWAL_PAYOUT',
            'title': f"Process Cash Withdrawal #{w.gold_reward_id}: NGN {w.amount:,.2f}",
            'description': f"Customer #{w.customer_id} | Status: {w.status}",
            'entity_type': 'GoldReward',
            'entity_id': w.gold_reward_id,
            'status': w.status,
            'priority': 'HIGH',
            'created_at': (w.requested_at or w.created_at).isoformat() if (w.requested_at or w.created_at) else '',
            'responsible_role': 'Finance Admin',
            'detail_url': detail_url,
            'action_url': None
        })

    # 9. Guarantee Settlements Pending (status == 'Pending') (CRITICAL)
    settlements = GuaranteeSettlement.query.filter_by(status='Pending').all()
    for s in settlements:
        detail_url = f"/admin/performance/?settlement_id={s.id}"
        tasks.append({
            'task_id': f"settle_{s.id}",
            'task_type': 'SETTLEMENT_APPROVAL',
            'title': f"Approve Guarantee Settlement #{s.id}: NGN {s.amount:,.2f}",
            'description': f"Guarantee #{s.performance_guarantee_id} | Type: {s.settlement_type}",
            'entity_type': 'GuaranteeSettlement',
            'entity_id': s.id,
            'status': s.status,
            'priority': 'CRITICAL',
            'created_at': s.created_at.isoformat() if s.created_at else '',
            'responsible_role': 'Transaction Manager / Finance Admin',
            'detail_url': detail_url,
            'action_url': f"/admin/performance/settlement/{s.id}/approve/"
        })

    # Sort tasks: CRITICAL -> HIGH -> NORMAL -> LOW
    priority_order = {'CRITICAL': 0, 'HIGH': 1, 'NORMAL': 2, 'LOW': 3}
    tasks.sort(key=lambda t: (priority_order.get(t['priority'], 4), t.get('created_at') or '9999'), reverse=False)

    # Calculate summary counts
    counts = {
        'total': len(tasks),
        'critical': sum(1 for t in tasks if t['priority'] == 'CRITICAL'),
        'high': sum(1 for t in tasks if t['priority'] == 'HIGH'),
        'normal': sum(1 for t in tasks if t['priority'] == 'NORMAL'),
        'low': sum(1 for t in tasks if t['priority'] == 'LOW')
    }

    return {
        'tasks': tasks,
        'counts': counts
    }


def get_performance_indices(period_code='30d'):
    """Calculates corporate operational coverage and conversion rates."""
    total_props = Property.query.count()
    verified_props = Property.query.filter_by(status='Verified').count()

    verification_coverage = round((verified_props / float(total_props)) * 100.0, 1) if total_props > 0 else 0.0

    total_dabs = VerificationCase.query.count()
    approved_dabs = VerificationCase.query.filter_by(status='Passed').count()
    approval_rate = round((approved_dabs / float(total_dabs)) * 100.0, 1) if total_dabs > 0 else 0.0

    completed_txs = Transaction.query.filter(Transaction.status.in_(['Completion', 'Completed'])).count()
    cancelled_txs = Transaction.query.filter_by(status='Cancelled').count()
    terminal_txs = completed_txs + cancelled_txs
    tx_completion_rate = round((completed_txs / float(terminal_txs)) * 100.0, 1) if terminal_txs > 0 else 0.0

    total_refs = Referral.query.count()
    qualified_refs = Referral.query.filter_by(status='Qualified').count()
    referral_conversion_rate = round((qualified_refs / float(total_refs)) * 100.0, 1) if total_refs > 0 else 0.0

    invoiced_sum = db.session.query(func.sum(Invoice.amount_due)).scalar() or 0.0
    paid_sum = db.session.query(func.sum(Invoice.amount_paid)).scalar() or 0.0
    invoice_collection_rate = round((float(paid_sum) / float(invoiced_sum)) * 100.0, 1) if float(invoiced_sum) > 0 else 0.0

    return {
        'verification_coverage': verification_coverage,
        'approval_rate': approval_rate,
        'tx_completion_rate': tx_completion_rate,
        'referral_conversion_rate': referral_conversion_rate,
        'invoice_collection_rate': invoice_collection_rate
    }


def get_funnel_metrics(period_code='30d'):
    """Calculates lifecycle progression pipeline counts across existing database entities."""
    dabs_submitted = VerificationCase.query.count()
    dabs_approved = VerificationCase.query.filter_by(status='Passed').count()
    props_verified = Property.query.filter(Property.publication_status.in_(['Available', 'Approved', 'Public Listing'])).count()
    inspections_requested = Inspection.query.count()
    offers_submitted = Offer.query.count()
    txs_initiated = Transaction.query.count()
    txs_completed = Transaction.query.filter(Transaction.status.in_(['Completion', 'Completed'])).count()

    return [
        {'stage': 'Intent Submitted', 'count': dabs_submitted, 'icon': 'bi-file-earmark-plus'},
        {'stage': 'Intent Approved', 'count': dabs_approved, 'icon': 'bi-check-circle'},
        {'stage': 'Property Verified', 'count': props_verified, 'icon': 'bi-shield-check'},
        {'stage': 'Inspection Requested', 'count': inspections_requested, 'icon': 'bi-calendar-event'},
        {'stage': 'Offer Submitted', 'count': offers_submitted, 'icon': 'bi-tag'},
        {'stage': 'Transaction Initiated', 'count': txs_initiated, 'icon': 'bi-arrow-repeat'},
        {'stage': 'Transaction Completed', 'count': txs_completed, 'icon': 'bi-check-all'}
    ]


def get_activity_feed(limit=15):
    """Retrieves live recent activity records from AuditLog, SecurityEvent, Property, and Transaction tables."""
    feed = []

    # Audit logs
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    for l in logs:
        feed.append({
            'timestamp': l.created_at,
            'category': 'AUDIT',
            'title': f"Action: {l.action or 'System Action'}",
            'description': f"Entity: {l.entity_type or 'General'} #{l.entity_id or 'N/A'}",
            'badge': 'bg-dark'
        })

    # Security events
    sec_events = SecurityEvent.query.order_by(SecurityEvent.created_at.desc()).limit(limit).all()
    for s in sec_events:
        feed.append({
            'timestamp': s.created_at,
            'category': 'SECURITY',
            'title': f"Security Event: {s.event_type}",
            'description': s.description or f"IP: {s.ip_address or 'N/A'}",
            'badge': 'bg-danger'
        })

    # Recent Properties
    recent_props = Property.query.order_by(Property.created_at.desc()).limit(5).all()
    for p in recent_props:
        feed.append({
            'timestamp': p.created_at,
            'category': 'PROPERTY',
            'title': f"Property Listing Added: {p.title}",
            'description': f"Status: {p.publication_status} | Price: NGN {p.price:,.2f}",
            'badge': 'bg-success'
        })

    # Recent Transactions
    recent_txs = Transaction.query.order_by(Transaction.created_at.desc()).limit(5).all()
    for t in recent_txs:
        feed.append({
            'timestamp': t.created_at,
            'category': 'TRANSACTION',
            'title': f"Transaction Record: #{t.transaction_reference or t.transaction_id}",
            'description': f"Status: {t.status} | Value: NGN {t.transaction_value:,.2f}",
            'badge': 'bg-primary'
        })

    feed.sort(key=lambda x: x['timestamp'] or datetime.min, reverse=True)
    return feed[:limit]


def get_metric_catalogue():
    """Returns authoritative transparent metric definitions."""
    return [
        {
            'name': 'Customer Base',
            'category': 'Scale',
            'source': 'User',
            'calculation': 'COUNT(user_id)',
            'period': 'Lifetime / Period filterable',
            'meaning': 'Total registered users across all roles',
            'limitations': 'Includes superadmin & admin accounts',
            'visibility': 'All Admin Roles',
            'route': '/admin/users/'
        },
        {
            'name': 'Active Supply',
            'category': 'Asset Supply',
            'source': 'Property',
            'calculation': "COUNT(property_id) WHERE publication_status='Available'",
            'period': 'Current State',
            'meaning': 'Verified properties currently open for public discovery',
            'limitations': 'Excludes unverified and reserved properties',
            'visibility': 'Property Admin, Mandate Manager, Super Admin',
            'route': '/admin/intents/'
        },
        {
            'name': 'Completed Deal Volume',
            'category': 'Commercial',
            'source': 'Transaction',
            'calculation': "SUM(transaction_value) WHERE status IN ('Completion', 'Completed')",
            'period': 'Period filterable',
            'meaning': 'Gross commercial property value of completed transactions',
            'limitations': 'Calculates closed transactions only',
            'visibility': 'Transaction Manager, Finance Admin, Super Admin',
            'route': '/admin/transactions/'
        },
        {
            'name': 'Platform Commission',
            'category': 'Commercial / Revenue',
            'source': 'Transaction',
            'calculation': "SUM(odacity_commission_amount) WHERE status IN ('Completion', 'Completed')",
            'period': 'Period filterable',
            'meaning': 'Odacity commission revenue earned on completed transactions',
            'limitations': 'Does not represent corporate net profit or EBITDA',
            'visibility': 'Finance Admin, Super Admin',
            'route': '/admin/transactions/'
        },
        {
            'name': 'Verification Coverage',
            'category': 'Operations',
            'source': 'Property',
            'calculation': '(Verified Properties / Total Properties) * 100',
            'period': 'Current State',
            'meaning': 'Percentage of total inventory verified for market listing',
            'limitations': 'Measures status ratio, not processing latency SLA',
            'visibility': 'Property Admin, Compliance Admin, Super Admin',
            'route': '/admin/intents/'
        }
    ]

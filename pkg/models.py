from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# ---------------------------------------------------------------------------
# 1. USERS & IDENTITY
# ---------------------------------------------------------------------------

class User(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    customer_profile = db.relationship("CustomerProfile", back_populates="user", uselist=False)
    property_owner_profile = db.relationship("PropertyOwnerProfile", back_populates="user", uselist=False)
    user_roles = db.relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    notifications = db.relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    audit_logs = db.relationship("AuditLog", back_populates="user")
    security_events = db.relationship("SecurityEvent", back_populates="user")


class Role(db.Model):
    __tablename__ = "roles"

    role_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    user_roles = db.relationship("UserRole", back_populates="role", cascade="all, delete-orphan")


class Permission(db.Model):
    __tablename__ = "permissions"

    permission_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)


class UserRole(db.Model):
    __tablename__ = "user_roles"

    user_role_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.role_id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="user_roles")
    role = db.relationship("Role", back_populates="user_roles")


class Notification(db.Model):
    __tablename__ = "notifications"

    notification_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    notification_type = db.Column(db.String(100), nullable=True)
    subject = db.Column(db.String(255), nullable=True)
    body = db.Column(db.Text, nullable=True)
    type = db.Column(db.String(100), nullable=True)
    message = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(500), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="notifications")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    audit_log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    action = db.Column(db.String(150), nullable=False)
    entity_type = db.Column(db.String(100), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    resource_type = db.Column(db.String(100), nullable=True)
    resource_id = db.Column(db.Integer, nullable=True)
    ip_address = db.Column(db.String(100), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    previous_values = db.Column(db.JSON, nullable=True)
    new_values = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="audit_logs")


class SecurityEvent(db.Model):
    __tablename__ = "security_events"

    security_event_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    event_type = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="security_events")


# ---------------------------------------------------------------------------
# 2. USER PROFILES & ONBOARDING
# ---------------------------------------------------------------------------

class CustomerProfile(db.Model):
    __tablename__ = "customer_profiles"

    customer_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    phone_number = db.Column(db.String(30), nullable=True)
    profile_picture_url = db.Column(db.String(500), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(50), nullable=True)
    address = db.Column(db.Text, nullable=True)
    preferences = db.Column(db.JSON, nullable=True)
    kyc_status = db.Column(db.String(50), default="Not Started", nullable=True)
    verification_status = db.Column(db.String(50), default="Pending", nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="customer_profile")
    saved_properties = db.relationship("SavedProperty", back_populates="customer", cascade="all, delete-orphan")
    saved_searches = db.relationship("SavedSearch", back_populates="customer", cascade="all, delete-orphan")
    applications = db.relationship("Application", back_populates="customer")
    mandates = db.relationship("Mandate", back_populates="customer")
    inspections = db.relationship("Inspection", back_populates="customer")
    offers = db.relationship("Offer", back_populates="customer")
    transactions = db.relationship("Transaction", back_populates="customer")
    referrals_made = db.relationship("Referral", foreign_keys="Referral.referrer_customer_id", back_populates="referrer")
    referrals_received = db.relationship("Referral", foreign_keys="Referral.referred_customer_id", back_populates="referred")
    gold_account = db.relationship("GoldAccount", back_populates="customer", uselist=False)
    gold_rewards = db.relationship("GoldReward", back_populates="customer")
    performance_guarantees = db.relationship("PerformanceGuarantee", back_populates="customer")


class PropertyOwnerProfile(db.Model):
    __tablename__ = "property_owner_profiles"

    owner_profile_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), unique=True, nullable=False)
    company_name = db.Column(db.String(255), nullable=True)
    business_name = db.Column(db.String(255), nullable=True)
    owner_type = db.Column(db.String(50), default="individual", nullable=False) # individual | corporate
    tax_id = db.Column(db.String(100), nullable=True)
    tin_number = db.Column(db.String(100), nullable=True)
    address = db.Column(db.Text, nullable=True)
    kyc_status = db.Column(db.String(50), default="Not Started", nullable=True)
    verification_status = db.Column(db.String(50), default="Pending", nullable=True)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="property_owner_profile")
    authorization_codes = db.relationship("AuthorizationCode", back_populates="owner", cascade="all, delete-orphan")
    kyc_cases = db.relationship("KycCase", back_populates="owner", cascade="all, delete-orphan")
    dabs = db.relationship("DirectAssetBrief", back_populates="owner")
    global_service_agreements = db.relationship("GlobalServiceAgreement", back_populates="owner")
    transaction_codes = db.relationship("TransactionCode", back_populates="owner")
    performance_guarantees = db.relationship("PerformanceGuarantee", back_populates="owner")


class AuthorizationCode(db.Model):
    __tablename__ = "authorization_codes"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_profile_id = db.Column(db.Integer, db.ForeignKey("property_owner_profiles.owner_profile_id"), nullable=False)
    code = db.Column(db.String(100), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owner = db.relationship("PropertyOwnerProfile", back_populates="authorization_codes")


class KycCase(db.Model):
    __tablename__ = "kyc_cases"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_profile_id = db.Column(db.Integer, db.ForeignKey("property_owner_profiles.owner_profile_id"), nullable=False)
    status = db.Column(db.String(50), default="Not Started", nullable=False) # Not Started | Submitted | Under Review | Approved | Rejected | Resubmission Required
    government_id_data = db.Column(db.Text, nullable=True)
    additional_info = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owner = db.relationship("PropertyOwnerProfile", back_populates="kyc_cases")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_user_id])


# ---------------------------------------------------------------------------
# 3. DIRECT ASSET BRIEF & PROPERTY SUPPLY
# ---------------------------------------------------------------------------

class DirectAssetBrief(db.Model):
    __tablename__ = "direct_asset_briefs"

    dab_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_profile_id = db.Column(db.Integer, db.ForeignKey("property_owner_profiles.owner_profile_id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    service_type = db.Column(db.String(50), default="sale", nullable=True) # sale | lease | rent | management
    property_type = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    budget_range = db.Column(db.String(150), nullable=True)
    brief_details = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(100), default="Draft", nullable=False) # Draft | Submitted | Under Verification | Approved | Rejected
    submitted_at = db.Column(db.DateTime, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owner = db.relationship("PropertyOwnerProfile", back_populates="dabs")
    property = db.relationship("Property", back_populates="dab", uselist=False)
    verification_cases = db.relationship("VerificationCase", back_populates="dab")


class Property(db.Model):
    __tablename__ = "properties"

    property_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    dab_id = db.Column(db.Integer, db.ForeignKey("direct_asset_briefs.dab_id"), unique=True, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    property_type = db.Column(db.String(100), nullable=True)
    price = db.Column(db.Numeric(18, 2), nullable=True)
    currency = db.Column(db.String(10), default="NGN", nullable=False)
    address = db.Column(db.String(255), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    locality = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    bedroom_count = db.Column(db.Integer, nullable=True)
    bathroom_count = db.Column(db.Integer, nullable=True)
    land_area_sq_m = db.Column(db.Numeric(12, 2), nullable=True)
    amenities = db.Column(db.JSON, nullable=True)
    availability_status = db.Column(db.String(100), nullable=True)
    publication_status = db.Column(db.String(100), default="Draft", nullable=False) # Draft | Submitted | Under Verification | Approved | Available | Reserved | Sold | Rented | Archived
    status = db.Column(db.String(100), default="Draft", nullable=False)
    available_from = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    dab = db.relationship("DirectAssetBrief", back_populates="property")
    media = db.relationship("PropertyMedia", back_populates="property", cascade="all, delete-orphan")
    documents = db.relationship("PropertyDocument", back_populates="property", cascade="all, delete-orphan")
    saved_by = db.relationship("SavedProperty", back_populates="property")
    applications = db.relationship("Application", back_populates="property")
    mandates = db.relationship("Mandate", back_populates="property")
    inspections = db.relationship("Inspection", back_populates="property")
    offers = db.relationship("Offer", back_populates="property")
    transactions = db.relationship("Transaction", back_populates="property")
    performance_guarantees = db.relationship("PerformanceGuarantee", back_populates="property")


class PropertyMedia(db.Model):
    __tablename__ = "property_media"

    media_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=False)
    type = db.Column(db.String(50), default="image", nullable=False) # image | video | document
    media_type = db.Column(db.String(50), default="image", nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    alt_text = db.Column(db.String(255), nullable=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    review_status = db.Column(db.String(50), default="Uploaded", nullable=False) # Uploaded | Under Review | Approved | Rejected
    rejection_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    property = db.relationship("Property", back_populates="media")


class PropertyDocument(db.Model):
    __tablename__ = "property_documents"

    document_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=False)
    document_type = db.Column(db.String(100), nullable=False) # title_deed | survey | land_use_permit | etc
    file_path = db.Column(db.String(500), nullable=False)
    review_status = db.Column(db.String(50), default="Pending", nullable=False) # Pending | Verified | Rejected
    owner_confirmation = db.Column(db.Boolean, default=False, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    verified_by_user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    locked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    property = db.relationship("Property", back_populates="documents")
    verifier = db.relationship("User", foreign_keys=[verified_by_user_id])


# ---------------------------------------------------------------------------
# 4. VERIFICATION ENGINE
# ---------------------------------------------------------------------------

class VerificationCase(db.Model):
    __tablename__ = "verification_cases"

    verification_case_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    dab_id = db.Column(db.Integer, db.ForeignKey("direct_asset_briefs.dab_id"), nullable=True)
    entity_type = db.Column(db.String(100), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    verifier_type = db.Column(db.String(50), nullable=True) # owner | property | document
    verification_type = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), default="Not Started", nullable=False) # Not Started | In Progress | Passed | Failed
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    result_details = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    dab = db.relationship("DirectAssetBrief", back_populates="verification_cases")
    assignee = db.relationship("User", foreign_keys=[assigned_to])
    events = db.relationship("VerificationEvent", back_populates="verification_case", cascade="all, delete-orphan")


class VerificationEvent(db.Model):
    __tablename__ = "verification_events"

    verification_event_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    verification_case_id = db.Column(db.Integer, db.ForeignKey("verification_cases.verification_case_id"), nullable=False)
    event_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    data = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    performed_by_user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    verification_case = db.relationship("VerificationCase", back_populates="events")
    creator = db.relationship("User", foreign_keys=[created_by_user_id])
    performer = db.relationship("User", foreign_keys=[performed_by_user_id])


# ---------------------------------------------------------------------------
# 5. CUSTOMER JOURNEY (Demand Side)
# ---------------------------------------------------------------------------

class SavedProperty(db.Model):
    __tablename__ = "saved_properties"

    saved_property_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=False)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    customer = db.relationship("CustomerProfile", back_populates="saved_properties")
    property = db.relationship("Property", back_populates="saved_by")


class SavedSearch(db.Model):
    __tablename__ = "saved_searches"

    saved_search_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    name = db.Column(db.String(150), nullable=True)
    search_criteria = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    customer = db.relationship("CustomerProfile", back_populates="saved_searches")


class Application(db.Model):
    __tablename__ = "applications"

    application_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=False)
    status = db.Column(db.String(100), default="Submitted", nullable=False)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    customer = db.relationship("CustomerProfile", back_populates="applications")
    property = db.relationship("Property", back_populates="applications")
    letter_of_intent = db.relationship("LetterOfIntent", back_populates="application", uselist=False)


class LetterOfIntent(db.Model):
    __tablename__ = "letters_of_intent"

    letter_of_intent_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.application_id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=False)
    offer_amount = db.Column(db.Numeric(18, 2), nullable=True)
    valid_until = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(100), default="Draft", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    application = db.relationship("Application", back_populates="letter_of_intent")


class Mandate(db.Model):
    __tablename__ = "mandates"

    mandate_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=False)
    mandate_type = db.Column(db.String(100), nullable=True)
    mandate_value = db.Column(db.Numeric(18, 2), nullable=True)
    status = db.Column(db.String(100), default="Active", nullable=False)
    signed_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    customer = db.relationship("CustomerProfile", back_populates="mandates")
    property = db.relationship("Property", back_populates="mandates")
    performance_guarantees = db.relationship("PerformanceGuarantee", back_populates="mandate")


class Inspection(db.Model):
    __tablename__ = "inspections"

    inspection_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    scheduled_for = db.Column(db.DateTime, nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    inspector_notes = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(100), default="Requested", nullable=False) # Requested | Scheduled | Completed | Cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    customer = db.relationship("CustomerProfile", back_populates="inspections")
    property = db.relationship("Property", back_populates="inspections")


class Offer(db.Model):
    __tablename__ = "offers"

    offer_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=False)
    offer_amount = db.Column(db.Numeric(18, 2), nullable=False)
    valid_until = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    responded_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(100), default="Submitted", nullable=False) # Draft | Submitted | Under_Review | Accepted | Rejected | Counter_Offer | Withdrawn
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    customer = db.relationship("CustomerProfile", back_populates="offers")
    property = db.relationship("Property", back_populates="offers")
    negotiations = db.relationship("Negotiation", back_populates="offer", cascade="all, delete-orphan")


class Negotiation(db.Model):
    __tablename__ = "negotiations"

    negotiation_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    offer_id = db.Column(db.Integer, db.ForeignKey("offers.offer_id"), nullable=False)
    counter_offer_amount = db.Column(db.Numeric(18, 2), nullable=True)
    proposed_amount = db.Column(db.Numeric(18, 2), nullable=True)
    message = db.Column(db.Text, nullable=True)
    direction = db.Column(db.String(50), nullable=True) # buyer_to_owner | owner_to_buyer
    notes = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    offer = db.relationship("Offer", back_populates="negotiations")
    creator = db.relationship("User", foreign_keys=[created_by_user_id])


# ---------------------------------------------------------------------------
# 6. TRANSACTIONS & PAYMENTS
# ---------------------------------------------------------------------------

class Transaction(db.Model):
    __tablename__ = "transactions"

    transaction_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=False)
    offer_id = db.Column(db.Integer, db.ForeignKey("offers.offer_id"), nullable=True)
    transaction_reference = db.Column(db.String(100), unique=True, nullable=True)
    transaction_type = db.Column(db.String(100), nullable=True) # sale | lease | rent
    type = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(100), default="Initiated", nullable=False) # Initiated | Mandate | Terms_Accepted | Inspection | Offer | Payment | Documentation | Completion
    total_amount = db.Column(db.Numeric(18, 2), nullable=True)
    transaction_value = db.Column(db.Numeric(18, 2), nullable=True)
    odacity_commission_percentage = db.Column(db.Numeric(5, 2), default=10.00, nullable=False)
    odacity_commission_amount = db.Column(db.Numeric(18, 2), nullable=True)
    completion_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer = db.relationship("CustomerProfile", back_populates="transactions")
    property = db.relationship("Property", back_populates="transactions")
    offer = db.relationship("Offer")
    invoices = db.relationship("Invoice", back_populates="transaction", cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="transaction")
    documents = db.relationship("TransactionDocument", back_populates="transaction")
    referral_rewards = db.relationship("ReferralReward", foreign_keys="ReferralReward.transaction_id", back_populates="transaction")


class Invoice(db.Model):
    __tablename__ = "invoices"

    invoice_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.transaction_id"), nullable=False)
    invoice_number = db.Column(db.String(100), unique=True, nullable=True)
    amount_due = db.Column(db.Numeric(18, 2), nullable=False)
    amount_paid = db.Column(db.Numeric(18, 2), default=0.00, nullable=False)
    issue_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(100), default="Issued", nullable=False) # Issued | Paid | Partially_Paid | Overdue | Cancelled
    payment_instructions = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    transaction = db.relationship("Transaction", back_populates="invoices")
    payments = db.relationship("Payment", back_populates="invoice")


class Payment(db.Model):
    __tablename__ = "payments"

    payment_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.invoice_id"), nullable=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.transaction_id"), nullable=False)
    payment_reference = db.Column(db.String(255), nullable=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    method = db.Column(db.String(100), nullable=True) # bank_transfer | card | etc
    payment_method = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(100), default="Pending", nullable=False) # Pending | Completed | Failed | Reversed
    transaction_ref = db.Column(db.String(255), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    payment_date = db.Column(db.DateTime, nullable=True)
    reconciliation_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    invoice = db.relationship("Invoice", back_populates="payments")
    transaction = db.relationship("Transaction", back_populates="payments")


class TransactionDocument(db.Model):
    __tablename__ = "transaction_documents"

    transaction_document_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.transaction_id"), nullable=False)
    document_type = db.Column(db.String(100), nullable=False) # contract | receipt | memo
    file_path = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(100), nullable=True)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    transaction = db.relationship("Transaction", back_populates="documents")
    uploader = db.relationship("User", foreign_keys=[uploaded_by_user_id])


# ---------------------------------------------------------------------------
# 7. REFERRALS & REWARDS
# ---------------------------------------------------------------------------

class Referral(db.Model):
    __tablename__ = "referrals"

    referral_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    referrer_customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    referred_customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    referral_code_used = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(100), default="Referred", nullable=False) # Referred | Registered | Searching | Property_Selected | Inspection | Transaction | Completed
    relationship_created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    qualified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    referrer = db.relationship("CustomerProfile", foreign_keys=[referrer_customer_id], back_populates="referrals_made")
    referred = db.relationship("CustomerProfile", foreign_keys=[referred_customer_id], back_populates="referrals_received")
    events = db.relationship("ReferralEvent", back_populates="referral", cascade="all, delete-orphan")
    rewards = db.relationship("ReferralReward", back_populates="referral")


class ReferralEvent(db.Model):
    __tablename__ = "referral_events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    referral_id = db.Column(db.Integer, db.ForeignKey("referrals.referral_id"), nullable=False)
    event_type = db.Column(db.String(100), nullable=False) # Link_Clicked | Registered | Qualifying_Transaction_Detected | Reward_Calculated
    event_data = db.Column(db.JSON, nullable=True)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    referral = db.relationship("Referral", back_populates="events")


class ReferralReward(db.Model):
    __tablename__ = "referral_rewards"

    referral_reward_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    referral_id = db.Column(db.Integer, db.ForeignKey("referrals.referral_id"), nullable=False)
    qualifying_transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.transaction_id"), nullable=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.transaction_id"), nullable=True)
    referrer_customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=True)
    status = db.Column(db.String(100), default="Pending", nullable=False) # Pending | Earned | Approved | Payable | Paid | Rejected | Disqualified
    transaction_value = db.Column(db.Numeric(18, 2), nullable=True)
    odacity_earning = db.Column(db.Numeric(18, 2), nullable=True)
    reward_rate_percentage = db.Column(db.Numeric(5, 2), default=5.00, nullable=False)
    reward_amount = db.Column(db.Numeric(18, 2), nullable=True)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    settled_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    referral = db.relationship("Referral", back_populates="rewards")
    transaction = db.relationship("Transaction", foreign_keys=[transaction_id], back_populates="referral_rewards")
    qualifying_transaction = db.relationship("Transaction", foreign_keys=[qualifying_transaction_id])


class GoldAccount(db.Model):
    __tablename__ = "gold_accounts"

    gold_account_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), unique=True, nullable=False)
    current_points = db.Column(db.Integer, default=0, nullable=False)
    tier = db.Column(db.String(50), default="Standard", nullable=False) # Standard | Gold | Platinum
    last_activity_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    customer = db.relationship("CustomerProfile", back_populates="gold_account")
    events = db.relationship("GoldEvent", back_populates="gold_account", cascade="all, delete-orphan")


class GoldEvent(db.Model):
    __tablename__ = "gold_events"

    gold_event_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    gold_account_id = db.Column(db.Integer, db.ForeignKey("gold_accounts.gold_account_id"), nullable=False)
    customer_profile_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=True)
    event_type = db.Column(db.String(100), nullable=False) # First_Transaction | Referral_Reward | Bonus | Withdrawal
    description = db.Column(db.Text, nullable=True)
    points_change = db.Column(db.Integer, nullable=True)
    amount = db.Column(db.Numeric(18, 2), nullable=True)
    new_balance = db.Column(db.Integer, nullable=True)
    balance_after = db.Column(db.Numeric(18, 2), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    gold_account = db.relationship("GoldAccount", back_populates="events")


class GoldReward(db.Model):
    __tablename__ = "gold_rewards"

    gold_reward_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=False)
    reward_type = db.Column(db.String(100), nullable=False) # Withdrawal_Cash | Reinvest_Gold
    amount = db.Column(db.Numeric(18, 2), nullable=True)
    status = db.Column(db.String(100), default="Pending", nullable=False) # Pending | Approved | Processed
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    customer = db.relationship("CustomerProfile", back_populates="gold_rewards")


# ---------------------------------------------------------------------------
# 8. PERFORMANCE GUARANTEE ENGINE
# ---------------------------------------------------------------------------

class PerformanceGuarantee(db.Model):
    __tablename__ = "performance_guarantees"

    guarantee_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=True)
    owner_profile_id = db.Column(db.Integer, db.ForeignKey("property_owner_profiles.owner_profile_id"), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=True)
    mandate_id = db.Column(db.Integer, db.ForeignKey("mandates.mandate_id"), nullable=True)
    guarantee_type = db.Column(db.String(50), nullable=False) # owner_guarantee | buyer_guarantee
    status = db.Column(db.String(50), default="Eligible", nullable=False) # Eligible | Active | Completed | Redeemed_Partial | Redeemed_Full
    eligible_at = db.Column(db.DateTime, nullable=True)
    start_at = db.Column(db.DateTime, nullable=True)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    period_days = db.Column(db.Integer, nullable=True)
    cycle_days = db.Column(db.Integer, nullable=True)
    benefit_rate = db.Column(db.Numeric(10, 4), nullable=True)
    cap_amount = db.Column(db.Numeric(18, 2), nullable=True)
    triggered_at = db.Column(db.DateTime, nullable=True)
    settled_at = db.Column(db.DateTime, nullable=True)
    terms_version = db.Column(db.String(50), nullable=True)
    coverage_details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    property = db.relationship("Property", back_populates="performance_guarantees")
    owner = db.relationship("PropertyOwnerProfile", back_populates="performance_guarantees")
    customer = db.relationship("CustomerProfile", back_populates="performance_guarantees")
    mandate = db.relationship("Mandate", back_populates="performance_guarantees")
    cycles = db.relationship("GuaranteeCycle", back_populates="performance_guarantee", cascade="all, delete-orphan")
    events = db.relationship("GuaranteeEvent", back_populates="performance_guarantee", cascade="all, delete-orphan")
    settlements = db.relationship("GuaranteeSettlement", back_populates="performance_guarantee", cascade="all, delete-orphan")
    bank_reference = db.relationship("BankGuaranteeReference", back_populates="performance_guarantee", uselist=False, cascade="all, delete-orphan")


class GuaranteeCycle(db.Model):
    __tablename__ = "guarantee_cycles"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    performance_guarantee_id = db.Column(db.Integer, db.ForeignKey("performance_guarantees.guarantee_id"), nullable=False)
    cycle_number = db.Column(db.Integer, nullable=False)
    cycle_start = db.Column(db.Date, nullable=True)
    cycle_end = db.Column(db.Date, nullable=True)
    days_elapsed = db.Column(db.Integer, default=0, nullable=False)
    days_remaining = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(50), default="Active", nullable=False) # Active | Completed | Redeemed
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    performance_guarantee = db.relationship("PerformanceGuarantee", back_populates="cycles")


class GuaranteeEvent(db.Model):
    __tablename__ = "guarantee_events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    performance_guarantee_id = db.Column(db.Integer, db.ForeignKey("performance_guarantees.guarantee_id"), nullable=False)
    event_type = db.Column(db.String(100), nullable=False) # Milestone_3_Months | Milestone_6_Months | Redemption_Initiated | Settlement_Completed
    details = db.Column(db.Text, nullable=True)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    performance_guarantee = db.relationship("PerformanceGuarantee", back_populates="events")


class GuaranteeSettlement(db.Model):
    __tablename__ = "guarantee_settlements"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    performance_guarantee_id = db.Column(db.Integer, db.ForeignKey("performance_guarantees.guarantee_id"), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    settlement_type = db.Column(db.String(50), nullable=False) # penalty | redemption
    status = db.Column(db.String(50), default="Pending", nullable=False) # Pending | Approved | Paid
    approved_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    reference = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    performance_guarantee = db.relationship("PerformanceGuarantee", back_populates="settlements")


class BankGuaranteeReference(db.Model):
    __tablename__ = "bank_guarantee_references"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    performance_guarantee_id = db.Column(db.Integer, db.ForeignKey("performance_guarantees.guarantee_id"), unique=True, nullable=False)
    bank_name = db.Column(db.String(255), nullable=False)
    reference_number = db.Column(db.String(100), nullable=False)
    face_value = db.Column(db.Numeric(18, 2), nullable=False)
    issue_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    performance_guarantee = db.relationship("PerformanceGuarantee", back_populates="bank_reference")


# ---------------------------------------------------------------------------
# 9. OPERATIONS & LEGAL
# ---------------------------------------------------------------------------

class GlobalServiceAgreement(db.Model):
    __tablename__ = "global_service_agreements"

    agreement_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_profile_id = db.Column(db.Integer, db.ForeignKey("property_owner_profiles.owner_profile_id"), nullable=False)
    version = db.Column(db.String(50), default="1.0", nullable=True)
    terms_reference = db.Column(db.String(255), nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owner = db.relationship("PropertyOwnerProfile", back_populates="global_service_agreements")


class TransactionCode(db.Model):
    __tablename__ = "transaction_codes"

    transaction_code_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_profile_id = db.Column(db.Integer, db.ForeignKey("property_owner_profiles.owner_profile_id"), nullable=False)
    code = db.Column(db.String(255), nullable=False)
    code_hash = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owner = db.relationship("PropertyOwnerProfile", back_populates="transaction_codes")


# ---------------------------------------------------------------------------
# 10. ADMINISTRATION & AUDIT
# ---------------------------------------------------------------------------

class DisputeCase(db.Model):
    __tablename__ = "dispute_cases"

    dispute_case_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.transaction_id"), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer_profiles.customer_id"), nullable=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.property_id"), nullable=True)
    issue_type = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(100), default="Open", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class CommunicationRecord(db.Model):
    __tablename__ = "communication_records"

    communication_record_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    related_entity_type = db.Column(db.String(100), nullable=True)
    related_entity_id = db.Column(db.Integer, nullable=True)
    message_type = db.Column(db.String(100), nullable=True)
    message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    system_setting_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(150), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, PasswordField, EmailField, SubmitField, DateField, SelectField, TextAreaField, DecimalField, BooleanField
from wtforms.validators import DataRequired, Email, Optional

class RegisterForm(FlaskForm):
    firstname = StringField("First Name", validators=[DataRequired()])
    lastname = StringField("Last Name", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired()])
    phone = StringField("Phone", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    confirm_pass = PasswordField("Confirm Password", validators=[DataRequired()])

class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[Email(message='Are you sure this email is correct?')])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField('Login')

class CustomerProfileForm(FlaskForm):
    first_name = StringField("First Name", validators=[Optional()])
    last_name = StringField("Last Name", validators=[Optional()])
    phone_number = StringField("Phone Number", validators=[Optional()])
    date_of_birth = DateField("Date of Birth", validators=[Optional()], format='%Y-%m-%d')
    gender = SelectField("Gender", choices=[('', 'Select Gender'), ('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other'), ('Prefer not to say', 'Prefer not to say')], validators=[Optional()])
    address = TextAreaField("Address", validators=[Optional()])
    submit = SubmitField("Save Profile")

class CustomerKycForm(FlaskForm):
    submit = SubmitField("Submit Verification Request")

class SavePropertyForm(FlaskForm):
    submit = SubmitField("Save Property")

class SaveSearchForm(FlaskForm):
    name = StringField("Search Name", validators=[DataRequired(message="Please provide a name for this search.")])
    intent = StringField("Intent", validators=[Optional()])
    state = StringField("State", validators=[Optional()])
    property_type = StringField("Property Type", validators=[Optional()])
    max_price = StringField("Max Price", validators=[Optional()])
    submit = SubmitField("Save Search")

class DeleteSavedSearchForm(FlaskForm):
    submit = SubmitField("Delete Search")

class RentalApplicationForm(FlaskForm):
    notes = TextAreaField("Additional Notes / Information", validators=[Optional()])
    submit = SubmitField("Submit Application")

class ScheduleInspectionForm(FlaskForm):
    notes = TextAreaField("Preferred Time / Additional Notes", validators=[Optional()])
    scheduled_for = DateField("Preferred Inspection Date", validators=[Optional()], format='%Y-%m-%d')
    submit = SubmitField("Request Inspection")

class CancelApplicationForm(FlaskForm):
    submit = SubmitField("Cancel Application")

class CancelInspectionForm(FlaskForm):
    submit = SubmitField("Cancel Inspection")

class PurchaseOfferForm(FlaskForm):
    offer_amount = DecimalField("Offer Amount (NGN)", validators=[DataRequired(message="Please enter a valid numeric offer amount.")])
    notes = TextAreaField("Additional Terms / Notes", validators=[Optional()])
    submit = SubmitField("Submit Purchase Offer")

class CancelOfferForm(FlaskForm):
    submit = SubmitField("Cancel Offer")

class PropertyOwnerProfileForm(FlaskForm):
    owner_type = SelectField("Owner Type", choices=[('individual', 'Individual Owner'), ('corporate', 'Corporate / Business Entity')], validators=[DataRequired()])
    company_name = StringField("Company / Organization Name", validators=[Optional()])
    business_name = StringField("Business Trading Name", validators=[Optional()])
    tax_id = StringField("Tax Identification Number (TIN)", validators=[Optional()])
    tin_number = StringField("RC / Registration Number", validators=[Optional()])
    address = TextAreaField("Registered Office / Contact Address", validators=[Optional()])
    submit = SubmitField("Save Owner Profile")

class DirectAssetBriefForm(FlaskForm):
    title = StringField("Property Listing Title", validators=[DataRequired(message="Please provide a title for your property listing.")])
    service_type = SelectField("Listing Intent", choices=[('sale', 'Outright Sale'), ('lease', 'Leasehold'), ('rent', 'Rental Listing')], validators=[DataRequired()])
    property_type = SelectField("Property Type", choices=[('House', 'House / Detached'), ('Flat', 'Flat / Apartment'), ('Commercial', 'Commercial / Office'), ('Land', 'Land / Plot'), ('Industrial', 'Industrial / Warehouse'), ('Other', 'Other Property Type')], validators=[Optional()])
    location = StringField("Location / Address / City", validators=[Optional()])
    budget_range = StringField("Asking Price / Budget Range (NGN)", validators=[Optional()])
    brief_details = TextAreaField("Property Details & Features", validators=[Optional()])
    submit = SubmitField("Submit Direct Asset Brief")

class RespondOfferForm(FlaskForm):
    action = SelectField("Response Action", choices=[('Accepted', 'Accept Offer'), ('Rejected', 'Reject Offer'), ('Counter_Offer', 'Counter Offer')], validators=[DataRequired()])
    counter_amount = DecimalField("Counter Offer Amount (NGN)", validators=[Optional()])
    notes = TextAreaField("Response Notes (Optional)", validators=[Optional()])
    submit = SubmitField("Submit Response")

class BuyerRespondOfferForm(FlaskForm):
    action = SelectField("Response Action", choices=[('Accepted', 'Accept Counter Offer'), ('Rejected', 'Reject Counter Offer'), ('Counter_Offer', 'Propose Counter Offer')], validators=[DataRequired()])
    counter_amount = DecimalField("Counter Offer Amount (NGN)", validators=[Optional()])
    notes = TextAreaField("Message / Notes (Optional)", validators=[Optional()])
    submit = SubmitField("Submit Response")



class DabInstitutionEnquiryForm(FlaskForm):
    # INSTITUTION / ORGANIZATION INFORMATION
    inst_name = StringField("Institution / Organization Name", validators=[DataRequired(message="Institution / Organization Name is required.")])
    inst_contact_person = StringField("Contact Person", validators=[DataRequired(message="Contact Person is required.")])
    inst_official_email = EmailField("Official Email", validators=[DataRequired(message="Official Email is required."), Email(message="Please provide a valid official email address.")])
    inst_phone = StringField("Phone", validators=[DataRequired(message="Phone number is required.")])
    inst_office_address = TextAreaField("Office Address", validators=[DataRequired(message="Office Address is required.")])
    inst_org_type = SelectField("Organization Type", choices=[('Real Estate', 'Real Estate')], validators=[DataRequired(message="Organization Type is required.")])
    inst_cac_reg_num = StringField("CAC Registration Number", validators=[DataRequired(message="CAC Registration Number is required.")])
    inst_cac_cert = FileField("CAC Registration Certificate", validators=[FileRequired(message="CAC Registration Certificate is required."), FileAllowed(['pdf'], message="Accepted format: PDF only. (.pdf)")])

    submit = SubmitField("Submit DAB Institution Enquiry")


class DabAgentEnquiryForm(FlaskForm):
    # SECTION A — AGENT INFORMATION
    agent_name = StringField("Full Name", validators=[DataRequired(message="Full Name is required.")])
    agent_company_name = StringField("Company / Organization Name", validators=[DataRequired(message="Company / Organization Name is required.")])
    agent_email = EmailField("Official Email", validators=[DataRequired(message="Official Email is required."), Email(message="Please provide a valid official email address.")])
    agent_phone = StringField("Phone Number", validators=[DataRequired(message="Phone number is required.")])
    agent_office_address = TextAreaField("Office Address", validators=[DataRequired(message="Office Address is required.")])

    # SECTION B — PROFESSIONAL REGISTRATION
    agent_cac_reg_num = StringField("CAC Registration Number", validators=[DataRequired(message="CAC Registration Number is required.")])
    agent_license_number = StringField("AEAN / LASRERA License / Membership Number", validators=[DataRequired(message="AEAN / LASRERA License / Membership Number is required.")])

    # SECTION C — IDENTIFICATION
    agent_id_type = SelectField("Identification Type", choices=[
        ('NIN', 'NIN'),
        ('Drivers License', "Driver's License"),
        ('Permanent Voters Card', "Permanent Voter's Card"),
        ('International Passport', 'International Passport')
    ], validators=[DataRequired(message="Identification Type is required.")])
    agent_id_number = StringField("Identification Number", validators=[DataRequired(message="Identification Number is required.")])
    agent_id_document = FileField("Identification Document", validators=[
        FileRequired(message="Identification Document is required."),
        FileAllowed(['pdf', 'png', 'jpg', 'jpeg'], message="Accepted formats: PDF, PNG, JPG, JPEG")
    ])

    # SECTION D — SUPPORTING DOCUMENTS
    agent_cac_certificate = FileField("CAC Registration Certificate", validators=[
        FileRequired(message="CAC Registration Certificate is required."),
        FileAllowed(['pdf', 'png', 'jpg', 'jpeg'], message="Accepted formats: PDF, PNG, JPG, JPEG")
    ])
    agent_license_proof = FileField("AEAN / LASRERA Membership / License Evidence", validators=[
        FileRequired(message="AEAN / LASRERA Membership / License Evidence is required."),
        FileAllowed(['pdf', 'png', 'jpg', 'jpeg'], message="Accepted formats: PDF, PNG, JPG, JPEG")
    ])

    # SECTION E — DECLARATION
    agent_declaration = BooleanField("I confirm that the information supplied is accurate, the submitted documents belong to the applicant/company, I have authority to act as an agent/practitioner, and Odacity may verify the supplied information and documents.", validators=[DataRequired(message="You must accept the declaration to submit your enquiry.")])

    submit = SubmitField("Submit DAB Agent Enquiry")


class DabIndividualEnquiryForm(FlaskForm):
    # SECTION A — INDIVIDUAL INFORMATION
    dab_individual_name = StringField("Full Name", validators=[DataRequired(message="Full Name is required.")])
    dab_individual_company_name = StringField("Company Name (Optional)", validators=[Optional()])
    dab_individual_email = EmailField("Email Address", validators=[DataRequired(message="Email Address is required."), Email(message="Please provide a valid email address.")])
    dab_individual_phone = StringField("Phone Number", validators=[DataRequired(message="Phone number is required.")])
    dab_individual_address = TextAreaField("Office/Home Address", validators=[DataRequired(message="Office/Home Address is required.")])
    dab_individual_government_id = StringField("Government ID Number", validators=[DataRequired(message="Government ID Number is required.")])
    dab_individual_id_document = FileField("Valid Means of Identification", validators=[
        FileRequired(message="Valid Means of Identification is required."),
        FileAllowed(['pdf'], message="Accepted format: PDF only. (.pdf)")
    ])

    submit = SubmitField("Submit DAB Individual Enquiry")


class GeneralEnquiryForm(FlaskForm):
    # SECTION A — APPLICANT IDENTITY
    general_name = StringField("Full Name", validators=[DataRequired(message="Full Name is required.")])
    general_email = EmailField("Email Address", validators=[DataRequired(message="Email Address is required."), Email(message="Please provide a valid email address.")])
    general_phone = StringField("Phone Number", validators=[DataRequired(message="Phone number is required.")])

    # SECTION B — ENQUIRY DETAILS
    general_subject = StringField("Subject", validators=[DataRequired(message="Subject is required.")])
    general_message = TextAreaField("Message", validators=[DataRequired(message="Message is required.")])

    submit = SubmitField("Send Enquiry")


class ControlledPropertySubmissionForm(FlaskForm):
    # SECTION A — PROPERTY LOCATION
    title = StringField("Property Listing Title", validators=[DataRequired(message="Property title is required.")])
    address = StringField("Street Address / Location", validators=[DataRequired(message="Address is required.")])
    city = StringField("City", validators=[DataRequired(message="City is required.")])
    state = StringField("State", validators=[DataRequired(message="State is required.")])
    locality = StringField("Locality / Neighborhood", validators=[Optional()])

    # SECTION B — PROPERTY DETAILS
    property_type = SelectField("Property Type", choices=[
        ('House', 'House / Detached'),
        ('Flat', 'Flat / Apartment'),
        ('Commercial', 'Commercial / Office'),
        ('Land', 'Land / Plot'),
        ('Industrial', 'Industrial / Warehouse'),
        ('Other', 'Other Property Type')
    ], validators=[DataRequired(message="Property type is required.")])
    bedroom_count = DecimalField("Bedrooms", validators=[Optional()])
    bathroom_count = DecimalField("Bathrooms", validators=[Optional()])
    land_area_sq_m = DecimalField("Land Area (sqm)", validators=[Optional()])
    amenities = StringField("Amenities / Key Features (comma-separated)", validators=[Optional()])
    description = TextAreaField("Description & Brief Details", validators=[Optional()])

    # SECTION C — TRANSACTION / PRICING
    service_type = SelectField("Transaction Intent", choices=[
        ('sale', 'Outright Sale'),
        ('lease', 'Leasehold'),
        ('rent', 'Rental Listing')
    ], validators=[DataRequired(message="Transaction intent is required.")])
    price = DecimalField("Asking Price / Budget (NGN)", validators=[DataRequired(message="Asking price is required.")])

    # SECTION D — PROPERTY PHOTOS / MEDIA
    primary_photo = FileField("Primary Property Photograph", validators=[
        FileAllowed(['jpg', 'png', 'jpeg'], message="Accepted image formats: JPG, PNG, JPEG")
    ])
    photo_2 = FileField("Additional Photograph 2", validators=[
        FileAllowed(['jpg', 'png', 'jpeg'], message="Accepted image formats: JPG, PNG, JPEG")
    ])
    photo_3 = FileField("Additional Photograph 3", validators=[
        FileAllowed(['jpg', 'png', 'jpeg'], message="Accepted image formats: JPG, PNG, JPEG")
    ])

    # SECTION E — PROPERTY DOCUMENTS
    title_deed = FileField("Property Title Deed / Certificate of Occupancy", validators=[
        FileAllowed(['pdf', 'png', 'jpg', 'jpeg'], message="Accepted document formats: PDF, PNG, JPG, JPEG")
    ])
    survey_plan = FileField("Survey Plan / Land Use Document", validators=[
        FileAllowed(['pdf', 'png', 'jpg', 'jpeg'], message="Accepted document formats: PDF, PNG, JPG, JPEG")
    ])

    submit = SubmitField("Submit Property Brief")












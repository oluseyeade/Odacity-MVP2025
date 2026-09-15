from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, EmailField, SubmitField, DateField, SelectField, TextAreaField, DecimalField
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
    action = SelectField("Response Action", choices=[('Accepted', 'Accept Offer'), ('Rejected', 'Reject Offer')], validators=[DataRequired()])
    notes = TextAreaField("Response Notes (Optional)", validators=[Optional()])
    submit = SubmitField("Submit Response")







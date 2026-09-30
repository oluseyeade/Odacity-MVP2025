import os
import sys
import json
import click
from datetime import datetime
from werkzeug.security import generate_password_hash

from pkg import app
from pkg.models import db, User, Role, UserRole, AuditLog, SecurityEvent


# Authoritative Odacity Administrative Roles and Descriptions
AUTHORITATIVE_ROLES = {
    'Super Admin': 'Super Administrator with global governance and user management privileges',
    'Property Admin': 'Property Administrator for property submissions, DAB overrides, and catalog management',
    'Mandate Manager': 'Mandate Manager for owner mandates, direct asset briefs, and guarantee performance',
    'Transaction Manager': 'Transaction Manager for offer approvals, transaction processing, and document execution',
    'Finance Admin': 'Finance Administrator for invoicing, payment recording, and guarantee settlements',
    'Compliance Admin': 'Compliance Administrator for intent approvals, KYC verification, and regulatory audits',
    'Customer Support': 'Customer Support Representative for buyer/renter support and enquiry management',
    'Audit Admin': 'Audit Administrator for audit logs, security event monitoring, and compliance logs'
}


def init_roles_logic():
    """
    Idempotently provisions the eight authoritative Odacity administrative roles.
    Inspects existing roles by exact name, inserts missing roles in a single transaction,
    and leaves existing records/descriptions untouched.
    Does NOT modify user records or create UserRole assignments.
    """
    existing_count = 0
    created_count = 0

    try:
        for role_name, description in AUTHORITATIVE_ROLES.items():
            existing_role = Role.query.filter_by(name=role_name).first()
            if existing_role:
                click.echo(f"Existing: {role_name}")
                existing_count += 1
            else:
                new_role = Role(name=role_name, description=description)
                db.session.add(new_role)
                click.echo(f"Created: {role_name}")
                created_count += 1

        db.session.commit()

        click.echo("ROLE INITIALIZATION COMPLETE")
        click.echo(f"Existing: {existing_count}")
        click.echo(f"Created: {created_count}")
        click.echo(f"Total required roles: {len(AUTHORITATIVE_ROLES)}")
        return True

    except Exception as e:
        db.session.rollback()
        click.echo(f"ABORT: Failed to initialize roles due to database transaction error: {str(e)}", err=True)
        return False


def create_superadmin_logic(email, password, full_name, phone=None):
    """
    Core function for provisioning the initial Super Admin account.
    Performs pre-flight checks, input validation, transaction management, and audit logging.
    """
    if not email or not email.strip():
        click.echo("ABORT: Email address is required.", err=True)
        return False

    clean_email = email.strip().lower()
    if '@' not in clean_email:
        click.echo(f"ABORT: Invalid email address '{clean_email}'.", err=True)
        return False

    if not full_name or not full_name.strip():
        click.echo("ABORT: Full name is required.", err=True)
        return False

    clean_name = full_name.strip()
    clean_phone = phone.strip() if phone and phone.strip() else None

    if not password or len(password) < 12:
        click.echo("ABORT: Password is required and must be at least 12 characters long.", err=True)
        return False

    # Check 1: Pre-flight check — Existing Super Admin user
    super_admin_exists = User.query.filter(
        (User.is_super_admin == True) |
        (User.user_roles.any(UserRole.role.has(Role.name.in_(['Super Admin', 'super_admin']))))
    ).first()

    if super_admin_exists:
        click.echo(
            f"ABORT: A Super Admin account already exists in the database (User ID: {super_admin_exists.user_id}, Email: {super_admin_exists.email}). Bootstrap operation halted.",
            err=True
        )
        return False

    # Check 2: Pre-flight check — Super Admin Role existence
    super_admin_role = Role.query.filter(
        Role.name.in_(['Super Admin', 'super_admin'])
    ).first()

    if not super_admin_role:
        click.echo(
            "ABORT: The 'Super Admin' role does not exist in the roles table. Please seed roles first.",
            err=True
        )
        return False

    # Check 3: Pre-flight check — Target email uniqueness
    existing_user = User.query.filter_by(email=clean_email).first()
    if existing_user:
        click.echo(
            f"ABORT: A user with email '{clean_email}' already exists in the database (User ID: {existing_user.user_id}).",
            err=True
        )
        return False

    # Execute Provisioning Transaction
    try:
        pw_hash = generate_password_hash(password)

        new_user = User(
            email=clean_email,
            password_hash=pw_hash,
            full_name=clean_name,
            phone=clean_phone,
            is_active=True,
            is_super_admin=True,
            created_at=datetime.utcnow()
        )
        db.session.add(new_user)
        db.session.flush()

        user_role = UserRole(
            user_id=new_user.user_id,
            role_id=super_admin_role.role_id,
            assigned_at=datetime.utcnow()
        )
        db.session.add(user_role)

        audit = AuditLog(
            user_id=new_user.user_id,
            action='SUPERADMIN_BOOTSTRAP',
            entity_type='User',
            entity_id=new_user.user_id,
            new_values=json.dumps({
                'full_name': clean_name,
                'email': clean_email,
                'role': super_admin_role.name,
                'is_super_admin': True,
                'bootstrap_method': 'CLI'
            }),
            created_at=datetime.utcnow()
        )
        db.session.add(audit)

        sec_event = SecurityEvent(
            user_id=new_user.user_id,
            event_type='SUPERADMIN_BOOTSTRAP_SUCCESS',
            description=f'Initial Super Admin account ({clean_email}) provisioned via CLI bootstrap',
            ip_address='127.0.0.1',
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)

        db.session.commit()

        click.echo("SUCCESS: Initial Super Admin account created successfully.")
        click.echo(f"User ID: {new_user.user_id}")
        click.echo(f"Email: {clean_email}")
        click.echo(f"Full Name: {clean_name}")
        click.echo(f"Role: {super_admin_role.name}")
        return True

    except Exception as e:
        db.session.rollback()
        click.echo(f"ABORT: An error occurred during database transaction: {str(e)}", err=True)
        return False


def reset_superadmin_logic(new_password, target_email='superadmin@odacityng.com'):
    """
    Core function for updating credentials and email of the existing Super Admin account.
    Validates account state, updates email and password hash, and records audit/security events.
    """
    if not new_password or not new_password.strip() or len(new_password) < 12:
        click.echo("ABORT: Password is required and must be at least 12 characters long.", err=True)
        return False

    clean_target_email = target_email.strip().lower()

    # Pre-flight Check 1: Unambiguous Super Admin User Identification
    super_admin_users = User.query.filter(
        (User.is_super_admin == True) |
        (User.user_roles.any(UserRole.role.has(Role.name.in_(['Super Admin', 'super_admin']))))
    ).all()

    if len(super_admin_users) == 0:
        click.echo("ABORT: No Super Admin account exists in the database to recover.", err=True)
        return False

    if len(super_admin_users) > 1:
        click.echo(
            f"ABORT: Multiple Super Admin accounts detected ({len(super_admin_users)} accounts). Recovery aborted to prevent ambiguity.",
            err=True
        )
        return False

    target_user = super_admin_users[0]

    # Pre-flight Check 2: Account Active Status
    if not target_user.is_active:
        click.echo(
            f"ABORT: Target Super Admin account (User ID: {target_user.user_id}) is inactive. Recovery aborted.",
            err=True
        )
        return False

    # Pre-flight Check 3: Target Email Assignment Check
    email_user = User.query.filter_by(email=clean_target_email).first()
    if email_user and email_user.user_id != target_user.user_id:
        click.echo(
            f"ABORT: Target email '{clean_target_email}' is already assigned to a different user (User ID: {email_user.user_id}). Recovery aborted.",
            err=True
        )
        return False

    # Execute Recovery Transaction
    try:
        old_email = target_user.email
        pw_hash = generate_password_hash(new_password)

        target_user.email = clean_target_email
        target_user.password_hash = pw_hash
        target_user.updated_at = datetime.utcnow()

        audit = AuditLog(
            user_id=target_user.user_id,
            action='SUPERADMIN_CREDENTIAL_RECOVERY',
            entity_type='User',
            entity_id=target_user.user_id,
            previous_values=json.dumps({'email': old_email}),
            new_values=json.dumps({
                'email': clean_target_email,
                'action': 'email_and_password_recovery',
                'recovery_method': 'CLI'
            }),
            created_at=datetime.utcnow()
        )
        db.session.add(audit)

        sec_event = SecurityEvent(
            user_id=target_user.user_id,
            event_type='SUPERADMIN_CREDENTIAL_RECOVERY_SUCCESS',
            description=f'Super Admin credentials updated successfully (Email: {clean_target_email})',
            ip_address='127.0.0.1',
            created_at=datetime.utcnow()
        )
        db.session.add(sec_event)

        db.session.commit()

        click.echo("SUCCESS: Super Admin credentials updated successfully.")
        click.echo(f"User ID: {target_user.user_id}")
        click.echo(f"Updated Email: {clean_target_email}")
        click.echo(f"Full Name: {target_user.full_name}")
        return True

    except Exception as e:
        db.session.rollback()
        click.echo(f"ABORT: Failed to reset Super Admin credentials due to database transaction error: {str(e)}", err=True)
        return False


@app.cli.command('init-roles')
def init_roles_cmd():
    """CLI Command to initialize the 8 authoritative Odacity administrative roles."""
    with app.app_context():
        success = init_roles_logic()
        if not success:
            sys.exit(1)


@app.cli.command('create-superadmin')
@click.option('--email', envvar='SUPERADMIN_EMAIL', prompt=False, help='Super Admin email address')
@click.option('--password', envvar='SUPERADMIN_PASSWORD', prompt=False, help='Super Admin password (min 12 chars)')
@click.option('--full-name', envvar='SUPERADMIN_NAME', prompt=False, help='Super Admin full name')
@click.option('--phone', envvar='SUPERADMIN_PHONE', default=None, help='Super Admin phone number (optional)')
def create_superadmin_cmd(email, password, full_name, phone):
    """CLI Command to provision the initial Super Admin account."""
    if not email:
        email = click.prompt("Super Admin Email")
    if not full_name:
        full_name = click.prompt("Super Admin Full Name")
    if not password:
        password = click.prompt("Super Admin Password", hide_input=True, confirmation_prompt=True)

    with app.app_context():
        success = create_superadmin_logic(email, password, full_name, phone)
        if not success:
            sys.exit(1)


@app.cli.command('reset-superadmin')
def reset_superadmin_cmd():
    """CLI Command to recover and update credentials for the existing Super Admin account."""
    new_password = click.prompt("New Super Admin Password (min 12 chars)", hide_input=True, confirmation_prompt=True)
    if not new_password or not new_password.strip() or len(new_password) < 12:
        click.echo("ABORT: Password must be non-empty and at least 12 characters long.", err=True)
        sys.exit(1)

    with app.app_context():
        success = reset_superadmin_logic(new_password)
        if not success:
            sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'init-roles':
        with app.app_context():
            success = init_roles_logic()
            sys.exit(0 if success else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == 'reset-superadmin':
        reset_superadmin_cmd()
    else:
        email_env = os.environ.get('SUPERADMIN_EMAIL')
        pass_env = os.environ.get('SUPERADMIN_PASSWORD')
        name_env = os.environ.get('SUPERADMIN_NAME')
        phone_env = os.environ.get('SUPERADMIN_PHONE')

        with app.app_context():
            if email_env and pass_env and name_env:
                success = create_superadmin_logic(email_env, pass_env, name_env, phone_env)
                sys.exit(0 if success else 1)
            else:
                create_superadmin_cmd()

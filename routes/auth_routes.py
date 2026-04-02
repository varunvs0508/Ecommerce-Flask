from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from models.models import User, OTPVerification, Address
from extensions import db, mail, limiter
import uuid
import random
import re
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Message
from flask_jwt_extended import (create_access_token,jwt_required,get_jwt_identity,set_access_cookies,unset_jwt_cookies)
from twilio.rest import Client
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_jwt_extended.exceptions import NoAuthorizationError

auth = Blueprint('auth', __name__)

def to_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def clean_expired_otps():
    OTPVerification.query.filter(OTPVerification.expires_at < datetime.utcnow()).delete()
    try:
        db.session.commit()
    except:
        db.session.rollback()
        flash("Something went wrong")

def get_current_user():
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        return User.query.get(user_id)
    except NoAuthorizationError:
        return None

def generate_otp():
    return str(random.randint(100000, 999999))

def validate_password(password):
    errors = []
    if len(password) < 8:
        errors.append("At least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("One uppercase letter")
    if not re.search(r"[0-9]", password):
        errors.append("One number")
    if not re.search(r"[a-z]", password):
        errors.append("One lowercase letter")
    if not re.search(r"[!@#$%^&*]", password):
        errors.append("One special character")
    if errors:
        return "Password must contain: " + ", ".join(errors)
    return None

def save_otp(user_id, otp, otp_type):
    clean_expired_otps()
    recent_count = OTPVerification.query.filter(
        OTPVerification.user_id == user_id,
        OTPVerification.created_at > datetime.now(timezone.utc) - timedelta(minutes=1)
    ).count()
    if recent_count >= 5:
        raise Exception("Too many OTP requests. Try again later.")
    existing = OTPVerification.query.filter_by(
        user_id=user_id,
        otp_type=otp_type
    ).order_by(OTPVerification.created_at.desc()).first()
    if existing and existing.locked_until and datetime.now(timezone.utc) < to_utc(existing.locked_until):
        raise Exception("Too many attempts. Try again later.")
    if existing and (datetime.now(timezone.utc) - to_utc(existing.created_at)).total_seconds() < 30:
        raise Exception("Please wait 30 seconds before requesting another OTP")
    OTPVerification.query.filter_by(user_id=user_id,otp_type=otp_type).delete()
    otp_record = OTPVerification(
        user_id=user_id,
        otp_code=otp,
        otp_type=otp_type,
        attempts=0,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    try:
        db.session.add(otp_record)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def validate_otp(user_id, otp_type, entered_otp):
    otp_record = OTPVerification.query.filter_by(
        user_id=user_id,
        otp_type=otp_type
    ).order_by(OTPVerification.created_at.desc()).first()
    if not otp_record:
        return False, "OTP not found"
    if otp_record.locked_until and datetime.now(timezone.utc) < to_utc(otp_record.locked_until):
        return False, "Too many attempts. Try again later."
    if otp_record.attempts >= 5:
        otp_record.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        db.session.commit()
        return False, "Too many attempts. Try again in 5 minutes."
    if datetime.now(timezone.utc) > to_utc(otp_record.expires_at):
        db.session.delete(otp_record)
        db.session.commit()
        return False, "OTP expired"
    if otp_record.user_id != user_id or entered_otp != otp_record.otp_code:
        otp_record.attempts += 1
        db.session.commit()
        remaining = 5 - otp_record.attempts
        return False, f"Invalid OTP. {remaining} attempts remaining."
    db.session.delete(otp_record)
    try:
        db.session.commit()
    except:
        db.session.rollback()
        flash("Something went wrong")
    return True, "OTP verified"

def send_otp_email(user_email, otp, subject="OTP Verification"):
    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[user_email]
    )
    msg.body = f"""
        Hello,

            Your OTP for verification is: {otp}

            This OTP will expire in 5 minutes.

        Regards,
        CopVIZ
        """
    mail.send(msg)

def send_sms_otp(phone, otp):
    client = Client(
        current_app.config['TWILIO_ACCOUNT_SID'],
        current_app.config['TWILIO_AUTH_TOKEN']
    )
    client.messages.create(
        body=f"CopVIZ: Your verification code is {otp}. Do not share this code with anyone. Code will expire in 5minutes.",
        from_=current_app.config['TWILIO_PHONE_NUMBER'],
        to=phone
    )

@auth.route('/profile')
@jwt_required()
def profile():
    user_id = get_jwt_identity()
    # get user
    user = User.query.filter_by(id=user_id).first()
    if not user:
        flash("User not found")
        return redirect(url_for('auth.login'))
    # get default address
    default_address = Address.query.filter_by(user_id=user_id,is_default=True).first()
    return render_template(
        "profile.html",
        user=user,
        default_address=default_address
    )

@auth.route('/address/delete/<int:id>')
@jwt_required()
def delete_address(id):
    user_id = get_jwt_identity()
    address = Address.query.filter_by(id=id,user_id=user_id).first()
    if not address:
        flash("Address not found")
        return redirect(url_for('auth.manage_addresses'))
    try:
        db.session.delete(address)
        db.session.commit()
        flash("Address deleted successfully")
    except:
        db.session.rollback()
        flash("Something went wrong")
    return redirect(url_for('auth.manage_addresses'))

@limiter.limit("5 per minute")
@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email', '').strip().lower()
        phone_input = request.form.get('phone', '').strip()
        phone = "+91" + phone_input
        password = request.form.get('password')
        address_line = request.form.get("address")
        city = request.form.get("city")
        state = request.form.get("state")
        pincode = request.form.get("pincode", "").strip()
        # Validate pincode only if provided (optional field)
        if pincode and (not pincode.isdigit() or len(pincode) != 6):
            flash("Pincode must be 6 digits")
            return render_template(
                "register.html",
                name=name,
                email=email,
                phone=request.form['phone']
            )    
        error = validate_password(password)
        if error:
            flash(error)
            return render_template(
                "register.html",
                name=name,
                email=email,
                phone=request.form['phone']
            )
        if User.query.filter_by(email=email).first():
            flash("Email already registered")
            return redirect(url_for('auth.register'))
        if User.query.filter_by(phone=phone).first():
            flash("Phone number already registered")
            return redirect(url_for('auth.register'))
        session['temp_user'] = {
            'id': uuid.uuid4().hex[:10],
            'name': name,
            'email': email,
            'phone': phone,
            'password': generate_password_hash(password),
            'address_line': address_line,
            'city': city,
            'state': state,
            'pincode': pincode
        }
        otp = generate_otp()
        save_otp(session['temp_user']['id'], otp, "email")
        send_otp_email(email, otp)
        flash("OTP sent to your email")
        return redirect(url_for('auth.verify_otp'))
    return render_template("register.html")

@limiter.limit("10 per minute")
@auth.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    temp_user = session.get('temp_user')
    if not temp_user:
        flash("No registration in progress")
        return redirect(url_for('auth.register'))
    # default flag
    email_verified = session.get('email_verified', False)
    if request.method == 'POST' and not email_verified:
        entered_otp = request.form['otp']
        success, message = validate_otp(temp_user['id'],"email",entered_otp)
        if not success:
            flash(message)
            if message in ["OTP expired", "Too many attempts"]:
                return redirect(url_for('auth.resend_email_otp'))
            return redirect(url_for('auth.verify_otp'))
        # EMAIL VERIFIED
        session['email_verified'] = True
        flash("Email verified successfully")
        return render_template(
            "verify_otp.html",
            email_verified=True,
            is_logged_in=False,
            is_admin=False
        )
    return render_template(
        "verify_otp.html",
        email_verified=email_verified,
        is_logged_in=False,
        is_admin=False
    )

@auth.route('/start-phone-verification')
def start_phone_verification():
    temp_user = session.get('temp_user')
    if not temp_user:
        flash("Session expired")
        return redirect(url_for('auth.register'))
    user_id = temp_user['id']
    phone = temp_user['phone']
    phone_otp = generate_otp()
    save_otp(user_id, phone_otp, "phone")
    try:
        send_sms_otp(phone, phone_otp)
    except Exception:
        flash("Failed to send SMS OTP")
        return redirect(url_for('auth.verify_otp'))
    session['phone_verify_user'] = user_id
    return redirect(url_for('auth.verify_phone_otp'))

@auth.route('/verify-phone-otp', methods=['GET', 'POST'])
def verify_phone_otp():
    user_id = session.get('phone_verify_user')
    if not user_id:
        flash("Phone verification session expired")
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        entered_otp = request.form['otp']
        success, message = validate_otp(user_id,"phone",entered_otp)
        if not success:
            flash(message)
            return redirect(url_for('auth.verify_phone_otp'))
        temp_user = session.get('temp_user')
        # CREATE USER (PHONE VERIFIED)
        new_user = User(
            id=temp_user['id'],
            name=temp_user['name'],
            email=temp_user['email'],
            phone=temp_user['phone'],
            password=temp_user['password'],
            is_email_verified=True,
            is_phone_verified=True
        )
        db.session.add(new_user)
        try:
            db.session.commit()
        except:
            db.session.rollback()
            flash("Something went wrong")
            return redirect(url_for('auth.verify_phone_otp'))
        # ADDRESS
        address_line = temp_user.get("address_line")
        if address_line:
            address = Address(
                user_id=new_user.id,
                full_name=new_user.name,
                phone=new_user.phone,
                address_line=address_line,
                city=temp_user.get("city"),
                state=temp_user.get("state"),
                pincode=temp_user.get("pincode"),
                is_default=True
            )
            db.session.add(address)
            db.session.commit()
        # CLEAN SESSION
        session.pop('temp_user', None)
        session.pop('phone_verify_user', None)
        session.pop('email_verified', None)
        flash("Account created & phone verified 🎉")
        return redirect(url_for('auth.login'))
    return render_template(
        "verify_phone_otp.html",
        is_logged_in=False,
        is_admin=False
    )

@auth.route('/complete-registration')
def complete_registration():
    temp_user = session.get('temp_user')
    if not temp_user:
        flash("Session expired")
        return redirect(url_for('auth.register'))
    # CREATE USER (PHONE NOT VERIFIED)
    new_user = User(
        id=temp_user['id'],
        name=temp_user['name'],
        email=temp_user['email'],
        phone=temp_user['phone'],
        password=temp_user['password'],
        is_email_verified=True,
        is_phone_verified=False  
    )
    db.session.add(new_user)
    try:
        db.session.commit()
    except:
        db.session.rollback()
        flash("Something went wrong")
        return redirect(url_for('auth.verify_otp'))
    # ADDRESS
    address_line = temp_user.get("address_line")
    if address_line:
        address = Address(
            user_id=new_user.id,
            full_name=new_user.name,
            phone=new_user.phone,
            address_line=address_line,
            city=temp_user.get("city"),
            state=temp_user.get("state"),
            pincode=temp_user.get("pincode"),
            is_default=True
        )
        db.session.add(address)
        db.session.commit()
    # CLEAN SESSION
    session.pop('temp_user', None)
    session.pop('email_verified', None)
    flash("Account created successfully 🎉")
    return redirect(url_for('auth.login'))

@limiter.limit("3 per minute")
@auth.route('/resend-phone-otp')
def resend_phone_otp():
    user_id = session.get('phone_verify_user')
    if not user_id:
        flash("Session expired")
        return redirect(url_for('auth.login'))
    user = db.session.get(User, user_id)
    otp = generate_otp()
    try:
        save_otp(user.id, otp, "phone")
    except Exception as e:
        flash(str(e))
        return redirect(url_for('auth.verify_phone_otp'))
    try:
        send_sms_otp(user.phone, otp)
    except Exception:
        flash("Failed to send OTP. Please try again.")
        return redirect(url_for('auth.verify_phone_otp'))
    flash("New OTP sent to your phone")
    return redirect(url_for('auth.verify_phone_otp'))

@limiter.limit("3 per minute") 
@auth.route('/resend-email-otp')
def resend_email_otp():
    temp_user = session.get('temp_user')
    if not temp_user:
        flash("Session expired. Please register again.")
        return redirect(url_for('auth.register'))
    otp = generate_otp()
    try:
        save_otp(temp_user['id'], otp, "email")
    except Exception as e:
        flash(str(e))
        return redirect(url_for('auth.verify_otp'))
    send_otp_email(temp_user['email'], otp)
    flash("New OTP sent to your email")
    return redirect(url_for('auth.verify_otp'))

@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        # Check if account is locked
        if user and user.account_locked_until:
            if datetime.now(timezone.utc) < user.account_locked_until:
                remaining = user.account_locked_until - datetime.now(timezone.utc)
                minutes = int(remaining.total_seconds() / 60) + 1
                flash(f"Account locked. Try again in {minutes} minutes.")
                return redirect(url_for('auth.login'))
        # LOGIN FAILED
        if not user or not check_password_hash(user.password, password):
            if user:
                user.failed_login_attempts += 1
                user.last_failed_login = datetime.now(timezone.utc)
                if user.failed_login_attempts >= 5:
                    user.account_locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                    flash("Too many failed attempts. Account locked for 15 minutes.")
                else:
                    remaining = 5 - user.failed_login_attempts
                    flash(f"Invalid email or password. {remaining} attempts remaining.")
                try:
                    db.session.commit()
                except:
                    db.session.rollback()
            else:
                flash("Invalid email or password")
            return redirect(url_for('auth.login'))
        # PASSWORD CORRECT → NOW CHECK VERIFICATION
        # Skip verification for admin
        if user.role != "admin":
            if user.status == "blocked":
                flash("Your account has been blocked. Please contact support.")
                return redirect(url_for('auth.login'))
            if not user.is_email_verified:
                flash("Please verify your email before logging in")
                return redirect(url_for('auth.login'))
            if not user.is_phone_verified:
                flash("Please verify your phone number later..")
                # return redirect(url_for('auth.login'))
        # LOGIN SUCCESS
        user.failed_login_attempts = 0
        user.account_locked_until = None
        user.last_failed_login = None
        user.last_login = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except:
            db.session.rollback()
        access_token = create_access_token(identity=user.id)
        # ROLE BASED REDIRECT
        next_url = request.args.get("next")
        if user.role == "admin":
            response = redirect(url_for('admin.admin_dashboard'))
        else:
            response = redirect(next_url or url_for('main.home'))
        set_access_cookies(response, access_token)
        session.clear()
        session['is_logged_in'] = True 
        session['user_id'] = user.id 
        session['is_admin'] = (user.role == "admin")
        flash("Login successful")
        return response
    return render_template("login.html")

@auth.route('/logout')
def logout():
    response = redirect(url_for('auth.login'))
    try:
        unset_jwt_cookies(response)
    except:
        pass  # ignore if no cookie
    flash("Logged out successfully")
    return response

@limiter.limit("3 per minute")
@auth.route('/password-reset', methods=['GET', 'POST'])
def password_reset_request():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("If this email exists, an OTP has been sent")
            return redirect(url_for('auth.password_reset_request'))
        otp = generate_otp()
        session['reset_user_id'] = user.id
        try:
            save_otp(user.id, otp, "password_reset")
        except Exception as e:
            flash(str(e))
            return redirect(url_for('auth.password_reset_request'))
        send_otp_email(email, otp, subject="Password Reset OTP")
        flash("OTP sent to your email")
        return redirect(url_for('auth.password_reset_verify'))
    return render_template("password/password_reset_request.html")

@auth.route('/password-reset-verify', methods=['GET', 'POST'])
def password_reset_verify():
    user_id = session.get('reset_user_id')
    if not user_id:
        flash("No reset request in progress")
        return redirect(url_for('auth.password_reset_request'))
    if request.method == 'POST':
        entered_otp = request.form['otp']
        # Use OTP validation helper
        success, message = validate_otp(user_id,"password_reset",entered_otp)
        if not success:
            flash(message)
            return redirect(url_for('auth.password_reset_verify'))
        # OTP verified
        flash("OTP verified. Enter new password.")
        return redirect(url_for('auth.password_reset_new'))
    return render_template("password/password_reset_verify.html")

@auth.route('/password-reset-new', methods=['GET', 'POST'])
def password_reset_new():
    user_id = session.get('reset_user_id')
    if not user_id:
        flash("No user to reset password for")
        return redirect(url_for('auth.password_reset_request'))
    if request.method == 'POST':
        new_password = request.form['password']
        # Password validation
        error = validate_password(new_password)
        if error:
            flash(error)
            return redirect(url_for('auth.password_reset_new'))
        user = db.session.get(User, user_id)
        if not user:
            flash("User not found")
            return redirect(url_for('auth.login'))
        user.password = generate_password_hash(new_password)
        db.session.commit()
        session.pop('reset_user_id')
        session.clear()
        flash("Password updated successfully")
        return redirect(url_for('auth.login'))
    return render_template("password/password_reset_new.html")

@auth.route('/update-profile', methods=['GET', 'POST'])
@jwt_required()
def update_profile():
    current_user_id = get_jwt_identity()
    user = User.query.filter_by(id=current_user_id).first()
    if request.method == 'POST':
        new_name = request.form.get('name','').strip()
        phone = request.form.get('phone','').strip()
        # VALIDATE PHONE
        if not phone.isdigit() or len(phone) != 10:
            flash("Phone number must be 10 digits", "error")
            return redirect(url_for('auth.update_profile'))
        new_phone = "+91" + phone
        # CHECK DUPLICATE PHONE
        existing_user = User.query.filter_by(phone=new_phone).first()
        if existing_user and existing_user.id != user.id:
            flash("Phone number already registered", "error")
            return redirect(url_for('auth.update_profile'))
        # PHONE CHANGE → OTP FLOW
        if new_phone != user.phone:
            otp = generate_otp()
            try:
                save_otp(user.id, otp, "phone_update")
            except Exception as e:
                flash("OTP error: " + str(e), "error")
                return redirect(url_for('auth.update_profile'))
            try:
                send_sms_otp(new_phone, otp)
            except Exception:
                flash("Failed to send OTP. Try again.", "error")
                return redirect(url_for('auth.update_profile'))
            session['new_phone'] = new_phone
            session['new_name'] = new_name
            flash("OTP sent to your new phone number", "success")
            return redirect(url_for('auth.verify_phone_update'))

        # -----------------------
        # NAME CHANGE ONLY
        # -----------------------
        if new_name != user.name:

            user.name = new_name

            try:
                db.session.commit()
                flash("Profile updated successfully", "success")
            except:
                db.session.rollback()
                flash("Update failed. Try again.", "error")

            return redirect(url_for('auth.profile'))

        # -----------------------
        # NO CHANGE
        # -----------------------
        flash("No changes detected", "error")
        return redirect(url_for('auth.update_profile'))

    return render_template("update_profile.html", user=user)

@auth.route('/addresses')
@jwt_required()
def manage_addresses():
    user_id = get_jwt_identity()
    # always use SAME type
    addresses = Address.query.filter_by(user_id=user_id).all()
    print("FETCH USER:", user_id)
    print("TOTAL ADDRESSES:", len(addresses))
    return render_template("addresses.html", addresses=addresses)

@auth.route('/add-address', methods=['POST'])
@jwt_required()
def add_address():
    user_id = get_jwt_identity()
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address_line = request.form.get("address", "").strip()
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip()
    pincode = request.form.get("pincode", "").strip()
    count = Address.query.filter_by(user_id=user_id).count()
    new_address = Address(
            user_id=user_id,
            full_name=name,
            phone="+91" + phone,
            address_line=address_line,
            city=city,
            state=state,
            pincode=pincode,
            is_default=True if count == 0 else False
        )
    db.session.add(new_address)
    db.session.commit()
    flash("Address added successfully")
    return redirect(url_for('auth.manage_addresses'))

@auth.route('/set-default-address/<int:id>')
@jwt_required()
def set_default_address(id):
    user_id = get_jwt_identity()
    # 1. Set all addresses to False
    Address.query.filter_by(user_id=user_id).update({"is_default": False})
    db.session.commit()
    # 2. Set selected address to True
    address = Address.query.filter_by(id=id, user_id=user_id).first()
    if address and address.user_id == user_id:
        address.is_default = True
        db.session.commit()
        flash("Default address updated")
    return redirect(url_for('auth.manage_addresses'))

@auth.route('/verify-phone-update', methods=['GET', 'POST'])
@jwt_required()
def verify_phone_update():
    current_user_id = get_jwt_identity()
    user = User.query.filter_by(id=current_user_id).first()
    if not user:
        flash("User not found")
        return redirect(url_for('auth.login'))
    new_phone = session.get('new_phone')
    new_name = session.get('new_name')
    if not new_phone:
        flash("Phone update session expired")
        return redirect(url_for('auth.update_profile'))
    if request.method == 'POST':
        entered_otp = request.form.get('otp')
        # Use OTP helper
        success, message = validate_otp(user.id,"phone_update",entered_otp)
        if not success:
            flash(message)
            return redirect(url_for('auth.verify_phone_update'))
        # OTP verified → update profile
        user.phone = new_phone
        if new_name:
            user.name = new_name
        db.session.commit()
        session.pop('new_phone', None)
        session.pop('new_name', None)
        flash("Profile updated successfully")
        return redirect(url_for('auth.dashboard'))
    return render_template("verify_phone_otp.html")

@auth.route('/change-password', methods=['GET', 'POST'])
@jwt_required()
def change_password():
    current_user_id = get_jwt_identity()
    user = User.query.filter_by(id=current_user_id).first()
    if not user:
        flash("User not found")
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        error = validate_password(new_password)
        if error:
            flash(error)
            return redirect(url_for('auth.change_password'))
        if not check_password_hash(user.password, current_password):
            flash("Current password incorrect")
            return redirect(url_for('auth.change_password'))
        user.password = generate_password_hash(new_password)
        db.session.commit()
        flash("Password updated successfully")
        return redirect(url_for('auth.dashboard'))
    return render_template("change_password.html")
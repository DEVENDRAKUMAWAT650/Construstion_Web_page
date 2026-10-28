import base64
import os
import random
import re
import smtplib
import time
import uuid
from decimal import Decimal, InvalidOperation
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

from PIL import Image
import pymysql
from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, redirect, render_template, request,
    session, url_for
)
from openai import OpenAI
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads", "projects")
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except Exception:
    UPLOAD_FOLDER = "/tmp"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_image(file_storage):
    if not file_storage or not file_storage.filename:
        return ""
    if not allowed_file(file_storage.filename):
        return None
    try:
        import io
        img = Image.open(file_storage)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        max_size = (1200, 1200)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=82, optimize=True)
        img_bytes = buffer.getvalue()
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        app.logger.warning(f"Error processing uploaded image to base64: {e}")
        try:
            ext = file_storage.filename.rsplit(".", 1)[1].lower()
            filename = f"proj_{int(time.time())}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file_storage.seek(0)
            file_storage.save(filepath)
            return f"/static/uploads/projects/{filename}"
        except Exception:
            return ""


def send_otp_email(to_email, otp_code, user_name="Valued Customer"):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        smtp_port = 587
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()

    # Log clearly in backend terminal for testing/debugging
    print("\n" + "=" * 55)
    print(f"[EMAIL SERVICE] Target Email : {to_email}")
    print(f"[EMAIL SERVICE] 6-Digit OTP  : {otp_code}")
    print("=" * 55 + "\n", flush=True)

    if not smtp_user or not smtp_pass:
        # Development mode simulation: OTP is logged in terminal, not shown on webpage
        return True, "DEV_SIMULATION"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{otp_code} is your Shree Khadapati Balaji Construction OTP"
        msg["From"] = f"Shree Khadapati Balaji Construction <{smtp_user}>"
        msg["To"] = to_email

        html_body = f"""
        <div style="font-family:Arial,sans-serif; max-width:540px; margin:auto; padding:25px; border:2px solid #ffbd08; border-radius:12px; background:#fff;">
            <div style="text-align:center; padding-bottom:15px; border-bottom:1px solid #eee;">
                <h2 style="margin:0; color:#111; font-size:22px;">Shree Khadapati Balaji Construction</h2>
                <p style="margin:5px 0 0; color:#c9933e; font-weight:700; font-size:12px; text-transform:uppercase;">Password Reset Verification</p>
            </div>
            <div style="padding:25px 5px;">
                <p style="font-size:15px; color:#222; margin:0 0 12px;">Namaste <b>{user_name}</b>,</p>
                <p style="font-size:14px; color:#555; line-height:1.5; margin:0 0 20px;">
                    We received a request to reset your password. Use the verification OTP below to complete your password update:
                </p>
                <div style="text-align:center; margin:25px 0;">
                    <div style="display:inline-block; font-size:34px; font-weight:900; letter-spacing:8px; color:#111; background:#fff6db; border:2px dashed #ffbd08; padding:12px 30px; border-radius:10px; font-family:monospace;">
                        {otp_code}
                    </div>
                </div>
                <p style="font-size:13px; color:#666; line-height:1.4; margin:0 0 10px;">
                    ⏱️ This OTP is valid for <b>10 minutes</b> only.
                </p>
                <p style="font-size:12px; color:#999; margin:0;">
                    If you did not request this password reset, please ignore this email. Your account is completely secure.
                </p>
            </div>
            <div style="border-top:1px solid #eee; padding-top:15px; text-align:center; font-size:11px; color:#aaa;">
                &copy; Shree Khadapati Balaji Construction &bull; Jaipur, Rajasthan
            </div>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_email, msg.as_string())
        server.quit()
        return True, "REAL_EMAIL_SENT"
    except Exception as e:
        app.logger.warning(f"SMTP send failed: {e}")
        return False, str(e)


def db_connection():
    ssl_config = None
    use_ssl = os.getenv("DB_SSL", "").strip().lower()
    host = os.getenv("DB_HOST", "localhost").strip()

    # Enable SSL if DB_SSL is explicitly true, or automatically for any remote host (e.g. TiDB, Aiven, RDS)
    # unless DB_SSL is explicitly false.
    if use_ssl in ("true", "1", "yes"):
        ssl_config = {"check_hostname": False, "verify_mode": False}
    elif use_ssl not in ("false", "0", "no") and host not in ("localhost", "127.0.0.1", ""):
        ssl_config = {"check_hostname": False, "verify_mode": False}

    conn_params = {
        "host": host,
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "root"),
        "database": os.getenv("DB_NAME", "construction_db"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
        "connect_timeout": 5,
    }
    if ssl_config:
        conn_params["ssl"] = ssl_config

    return pymysql.connect(**conn_params)


def query_all(sql, params=()):
    try:
        conn = db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.warning(f"Database query error: {e}")
        return []


def query_one(sql, params=()):
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = cur.lastrowid
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def current_user():
    if not session.get("user_id"):
        return None
    return query_one(
        "SELECT id, name, email, role FROM users WHERE id=%s",
        (session["user_id"],)
    )


def get_admin_emails():
    configured = os.getenv("ADMIN_EMAIL", "shreekhadapaticontruction@gamil.com").strip().lower()
    return {
        configured,
        "shreekhadapaticontruction@gmail.com",
        "shreekhadapaticontruction@gamil.com",
    }


def is_admin():
    if not session.get("user_id"):
        return False
    user_email = session.get("email", "").strip().lower()
    return (
        user_email in get_admin_emails()
        or session.get("role") == "admin"
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_user():
    return {"nav_user": current_user(), "nav_is_admin": is_admin()}


DEFAULT_PROJECTS = [
    {
        "id": 8,
        "title": "3 BHK",
        "category": "Residential",
        "description": "Contemporary 3 BHK luxury home construction in Jaipur, Rajasthan.",
        "image_url": "/static/uploads/projects/proj_1793187564_1ee76e1c.jpeg"
    },
    {
        "id": 1,
        "title": "Residential Villa",
        "category": "Residential",
        "description": "Contemporary family home in Jaipur, Rajasthan.",
        "image_url": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&q=80"
    },
    {
        "id": 2,
        "title": "Commercial Complex",
        "category": "Commercial",
        "description": "Modern commercial space for offices and retail.",
        "image_url": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80"
    },
    {
        "id": 3,
        "title": "Office Building",
        "category": "Commercial",
        "description": "Contemporary office building concept.",
        "image_url": "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1200&q=80"
    },
    {
        "id": 4,
        "title": "Infrastructure Project",
        "category": "Infrastructure",
        "description": "Infrastructure and civil engineering project concept.",
        "image_url": "https://images.unsplash.com/photo-1519501025264-65ba15a82390?auto=format&fit=crop&w=1200&q=80"
    },
    {
        "id": 5,
        "title": "Renovation Project",
        "category": "Renovation",
        "description": "Interior renovation with modern finishes.",
        "image_url": "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1200&q=80"
    },
    {
        "id": 6,
        "title": "Industrial Building",
        "category": "Industrial",
        "description": "Functional industrial building concept.",
        "image_url": "https://images.unsplash.com/photo-1565008447742-97f6f38c985c?auto=format&fit=crop&w=1200&q=80"
    }
]


_db_initialized = False


def init_db():
    global _db_initialized
    if _db_initialized:
        return
    try:
        conn = db_connection()
        try:
            with conn.cursor() as cur:
                # 1. Create tables if they do not exist
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    email VARCHAR(190) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'customer',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(160) NOT NULL,
                    category VARCHAR(80) NOT NULL,
                    description TEXT NOT NULL,
                    image_url LONGTEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS customer_projects (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    building_type VARCHAR(100) NOT NULL DEFAULT 'Residential Villa',
                    location VARCHAR(255) DEFAULT '',
                    stage VARCHAR(100) NOT NULL DEFAULT 'Planning & Foundation',
                    progress INT NOT NULL DEFAULT 15,
                    start_date VARCHAR(50) DEFAULT '',
                    expected_completion VARCHAR(50) DEFAULT '',
                    total_area VARCHAR(100) DEFAULT '',
                    supervisor_name VARCHAR(120) DEFAULT '',
                    supervisor_phone VARCHAR(30) DEFAULT '',
                    image_url LONGTEXT DEFAULT NULL,
                    latest_update TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT fk_cp_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS customer_project_photos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    project_id INT NOT NULL,
                    image_url LONGTEXT NOT NULL,
                    caption VARCHAR(255) DEFAULT '',
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_cpp_project FOREIGN KEY (project_id) REFERENCES customer_projects(id) ON DELETE CASCADE
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS enquiries (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    email VARCHAR(190) NOT NULL,
                    phone VARCHAR(30) NOT NULL,
                    project_type VARCHAR(100) NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
                """)

                # 2. Upgrade existing tables if image_url was VARCHAR(500)
                for tbl in ("projects", "customer_projects", "customer_project_photos"):
                    try:
                        cur.execute(f"ALTER TABLE {tbl} MODIFY COLUMN image_url LONGTEXT")
                    except Exception:
                        pass

                # 3. Ensure Default Admin Account exists
                admin_email = "shreekhadapaticontruction@gamil.com"
                cur.execute("SELECT id FROM users WHERE LOWER(email)=%s", (admin_email,))
                admin_user = cur.fetchone()
                if not admin_user:
                    cur.execute(
                        """INSERT INTO users (name, email, password_hash, role)
                           VALUES (%s, %s, %s, %s)""",
                        (
                            "Shree Khadapati Balaji Admin",
                            admin_email,
                            generate_password_hash("Ram@123"),
                            "admin"
                        )
                    )

                # 4. Insert Default Projects if table is empty
                cur.execute("SELECT COUNT(*) AS cnt FROM projects")
                res = cur.fetchone()
                cnt = res["cnt"] if isinstance(res, dict) else res[0]
                if cnt == 0:
                    for dp in DEFAULT_PROJECTS:
                        cur.execute(
                            """INSERT INTO projects (title, category, description, image_url)
                               VALUES (%s, %s, %s, %s)""",
                            (dp["title"], dp["category"], dp["description"], dp["image_url"])
                        )

            conn.commit()
            _db_initialized = True
        finally:
            conn.close()
    except Exception as e:
        app.logger.warning(f"Database auto-init note: {e}")


@app.before_request
def ensure_db_initialized():
    global _db_initialized
    if not _db_initialized:
        init_db()


try:
    init_db()
except Exception:
    pass


@app.route("/")
def home():
    projects = query_all(
        "SELECT * FROM projects ORDER BY created_at DESC LIMIT 3"
    )
    if not projects:
        projects = DEFAULT_PROJECTS[:3]
    return render_template("index.html", projects=projects)


@app.route("/projects")
def projects():
    rows = query_all("SELECT * FROM projects ORDER BY created_at DESC")
    if not rows:
        rows = DEFAULT_PROJECTS
    return render_template("projects.html", projects=rows)


@app.route("/calculator", methods=["GET", "POST"])
def calculator():
    result = None
    if request.method == "POST":
        try:
            area = Decimal(request.form.get("area", "0"))
            floors = int(request.form.get("floors", "1"))
            rate = Decimal(request.form.get("rate", "0"))
            if area <= 0 or rate <= 0 or floors < 1 or floors > 10:
                raise ValueError
            total_area = area * floors
            estimated_cost = total_area * rate
            result = {
                "area": total_area,
                "rate": rate,
                "cost": estimated_cost,
            }
        except (InvalidOperation, ValueError, TypeError):
            flash("Enter a valid area, rate, and floor count.", "error")
    return render_template("calculator.html", result=result)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        project_type = request.form.get("project_type", "").strip()
        message = request.form.get("message", "").strip()

        if not all([name, email, phone, project_type, message]):
            flash("Please fill in every field.", "error")
        elif len(name) > 120 or len(email) > 190 or len(message) > 5000:
            flash("Some fields are too long. Please shorten them.", "error")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Please enter a valid email address.", "error")
        else:
            execute(
                """INSERT INTO enquiries
                   (name, email, phone, project_type, message)
                   VALUES (%s, %s, %s, %s, %s)""",
                (name, email, phone[:30], project_type, message)
            )
            flash("Thanks! Your enquiry has been submitted.", "success")
            return redirect(url_for("contact"))
    return render_template("contact.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please complete all fields.", "error")
        elif len(name) > 120 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Enter a valid name and email address.", "error")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif email in get_admin_emails():
            flash("That email is reserved for the administrator.", "error")
        else:
            try:
                user_id = execute(
                    "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'customer')",
                    (name, email, generate_password_hash(password))
                )
                session.clear()
                session["user_id"] = user_id
                session["email"] = email
                session["name"] = name
                session["role"] = "customer"
                flash("Your account has been created. Welcome to your building project portal!", "success")
                return redirect(url_for("customer_dashboard"))
            except pymysql.err.IntegrityError:
                flash("An account with that email already exists.", "error")
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if email.endswith("@gamil.com"):
            email = email[:-10] + "@gmail.com"
        password = request.form.get("password", "")
        user = query_one(
            "SELECT id, name, email, password_hash, role FROM users WHERE email=%s",
            (email,)
        )
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["name"] = user["name"]
            session["role"] = user.get("role", "customer")
            flash(f"Welcome back, {user['name']}!", "success")
            next_url = session.pop("next_url", None)
            if is_admin():
                return redirect(next_url or url_for("admin"))
            return redirect(next_url or url_for("customer_dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
@app.route("/reset-password", methods=["GET", "POST"])
def forgot_password():
    if session.get("user_id"):
        return redirect(url_for("customer_dashboard" if not is_admin() else "admin"))

    if request.args.get("action") == "change_email":
        session.pop("reset_email", None)
        session.pop("reset_otp", None)
        session.pop("reset_otp_expiry", None)
        return redirect(url_for("forgot_password"))

    step = 2 if (session.get("reset_email") and session.get("reset_otp")) else 1

    if request.method == "POST":
        action = request.form.get("action", "send_otp")

        if action in ("send_otp", "resend_otp"):
            email = request.form.get("email", "").strip().lower()
            if not email and session.get("reset_email"):
                email = session.get("reset_email")
            if email.endswith("@gamil.com"):
                email = email[:-10] + "@gmail.com"

            if not email:
                flash("Please enter your registered email address.", "error")
                return render_template("forgot_password.html", step=1, email="")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                flash("Please enter a valid email address.", "error")
                return render_template("forgot_password.html", step=1, email=email)
            elif email in get_admin_emails():
                flash("Administrator account password is protected and cannot be reset from this form.", "error")
                return render_template("forgot_password.html", step=1, email=email)

            user = query_one(
                "SELECT id, name, email FROM users WHERE email=%s",
                (email,)
            )
            if not user:
                flash("No account found with this email address. Please check your email or create an account.", "error")
                return render_template("forgot_password.html", step=1, email=email)

            # Generate secure 6-digit OTP
            otp_code = f"{random.randint(100000, 999999)}"
            session["reset_email"] = email
            session["reset_otp"] = otp_code
            session["reset_otp_expiry"] = time.time() + 600  # 10 minutes

            # Send OTP email
            success, result_type = send_otp_email(email, otp_code, user["name"])
            if not success:
                app.logger.warning(f"Failed to send OTP to {email}: {result_type}")
                flash(f"Email server error: {result_type}. Kripya thodi der baad dobara koshish karein.", "error")
                return render_template("forgot_password.html", step=1, email=email)

            if result_type == "REAL_EMAIL_SENT":
                flash(f"✅ 6-Digit OTP aapke registered email ({email}) par bhej diya gaya hai! Kripya apna Inbox ya Spam folder check karein.", "success")
            else:
                flash(f"✅ 6-Digit OTP send ho gaya hai! (Dev mode: OTP server terminal mein log hua hai, screen par confidential hai).", "success")

            return render_template("forgot_password.html", step=2, email=email)

        elif action == "verify_and_reset":
            email = session.get("reset_email")
            saved_otp = session.get("reset_otp")
            expiry = session.get("reset_otp_expiry", 0)

            entered_otp = request.form.get("otp", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")

            if not email or not saved_otp:
                flash("Session expired. Please enter your email again.", "error")
                return redirect(url_for("forgot_password"))

            if time.time() > expiry:
                flash("OTP has expired. Please click 'Resend OTP' to get a new code.", "error")
                return render_template("forgot_password.html", step=2, email=email)

            if not entered_otp:
                flash("Please enter the 6-digit OTP code sent to your email.", "error")
                return render_template("forgot_password.html", step=2, email=email)

            if entered_otp != saved_otp:
                flash("❌ Incorrect OTP! Please enter the valid 6-digit code sent to your email.", "error")
                return render_template("forgot_password.html", step=2, email=email)

            if not password or not confirm:
                flash("Please complete both password fields.", "error")
                return render_template("forgot_password.html", step=2, email=email)

            if len(password) < 8:
                flash("Password must contain at least 8 characters.", "error")
                return render_template("forgot_password.html", step=2, email=email)

            if password != confirm:
                flash("Passwords do not match. Please verify both fields.", "error")
                return render_template("forgot_password.html", step=2, email=email)

            try:
                new_hash = generate_password_hash(password)
                execute(
                    "UPDATE users SET password_hash=%s WHERE email=%s",
                    (new_hash, email)
                )
                session.pop("reset_email", None)
                session.pop("reset_otp", None)
                session.pop("reset_otp_expiry", None)
                flash("🎉 Password has been reset successfully! Please log in with your new password.", "success")
                return redirect(url_for("login"))
            except Exception as e:
                app.logger.exception("Failed to update password after OTP verification")
                flash("An error occurred while updating your password. Please try again.", "error")
                return render_template("forgot_password.html", step=2, email=email)

    return render_template("forgot_password.html", step=step, email=session.get("reset_email", ""))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/dashboard")
@app.route("/my-project")
@login_required
def customer_dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    user_projects = query_all(
        """SELECT * FROM customer_projects
           WHERE user_id=%s
           ORDER BY updated_at DESC""",
        (user["id"],)
    )
    for p in user_projects:
        p["photos"] = query_all(
            """SELECT * FROM customer_project_photos
               WHERE project_id=%s
               ORDER BY uploaded_at DESC, id DESC""",
            (p["id"],)
        )
    return render_template(
        "customer_dashboard.html",
        user=user,
        user_projects=user_projects
    )


@app.route("/admin")
@admin_required
def admin():
    projects = query_all("SELECT * FROM projects ORDER BY created_at DESC")
    enquiries = query_all("SELECT * FROM enquiries ORDER BY created_at DESC")
    users = query_all(
        "SELECT id, name, email, role, created_at FROM users ORDER BY created_at DESC"
    )
    customer_projects = query_all(
        """SELECT cp.*, u.name as customer_name, u.email as customer_email
           FROM customer_projects cp
           JOIN users u ON cp.user_id = u.id
           ORDER BY cp.updated_at DESC"""
    )
    for cp in customer_projects:
        cp["photos"] = query_all(
            """SELECT * FROM customer_project_photos
               WHERE project_id=%s
               ORDER BY uploaded_at DESC, id DESC""",
            (cp["id"],)
        )
    admin_emails = get_admin_emails()
    registered_customers = [
        u for u in users if u["email"].lower() not in admin_emails
    ]
    return render_template(
        "admin.html",
        projects=projects,
        enquiries=enquiries,
        users=users,
        customer_projects=customer_projects,
        registered_customers=registered_customers
    )


@app.route("/admin/projects/add", methods=["POST"])
@admin_required
def add_project():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    image_url = request.form.get("image_url", "").strip()
    image_file = request.files.get("image_file")

    if not title or not category:
        flash("Project title and category are required.", "error")
        return redirect(request.referrer or url_for("add_project_page"))

    uploaded_url = ""
    if image_file and image_file.filename:
        uploaded_url = save_uploaded_image(image_file)
        if uploaded_url is None:
            flash("Invalid image format. Supported: JPG, PNG, WEBP, GIF.", "error")
            return redirect(request.referrer or url_for("add_project_page"))

    final_image_url = uploaded_url or image_url

    execute(
        """INSERT INTO projects (title, category, description, image_url)
           VALUES (%s, %s, %s, %s)""",
        (title, category, description, final_image_url)
    )
    flash(f"Project '{title}' added successfully!", "success")
    return redirect(request.form.get("next") or url_for("projects"))


@app.route("/add-project", methods=["GET", "POST"])
def add_project_page():
    if not is_admin():
        session["next_url"] = url_for("add_project_page")
        flash("Please log in as Administrator to add projects.", "info")
        return redirect(url_for("login"))
    if request.method == "POST":
        return add_project()
    return render_template("add_project.html")


@app.route("/admin/projects/<int:project_id>/delete", methods=["POST"])
@admin_required
def delete_project(project_id):
    execute("DELETE FROM projects WHERE id=%s", (project_id,))
    flash("Project deleted.", "info")
    return redirect(request.referrer or url_for("projects"))


@app.route("/admin/customer-projects/add", methods=["POST"])
@admin_required
def add_customer_project():
    user_id = request.form.get("user_id", "").strip()
    title = request.form.get("title", "").strip()
    building_type = request.form.get("building_type", "Residential Villa").strip()
    location = request.form.get("location", "").strip()
    stage = request.form.get("stage", "Planning & Approvals").strip()
    try:
        progress = max(0, min(100, int(request.form.get("progress", "15"))))
    except (ValueError, TypeError):
        progress = 15
    start_date = request.form.get("start_date", "").strip()
    expected_completion = request.form.get("expected_completion", "").strip()
    total_area = request.form.get("total_area", "").strip()
    supervisor_name = request.form.get("supervisor_name", "").strip()
    supervisor_phone = request.form.get("supervisor_phone", "").strip()
    latest_update = request.form.get("latest_update", "").strip()
    image_url = request.form.get("image_url", "").strip()
    image_files = request.files.getlist("image_files")
    single_file = request.files.get("image_file")
    if single_file and single_file.filename and single_file not in image_files:
        image_files.append(single_file)

    if not user_id or not title:
        flash("Customer selection and Project title are required.", "error")
        return redirect(url_for("admin") + "#customer-projects")

    project_id = execute(
        """INSERT INTO customer_projects 
           (user_id, title, building_type, location, stage, progress, start_date, expected_completion, total_area, supervisor_name, supervisor_phone, image_url, latest_update)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, title, building_type, location, stage, progress, start_date, expected_completion, total_area, supervisor_name, supervisor_phone, image_url, latest_update)
    )

    first_image = ""
    photos_added = 0
    for f in image_files:
        if f and f.filename:
            uploaded_url = save_uploaded_image(f)
            if uploaded_url:
                if not first_image:
                    first_image = uploaded_url
                execute(
                    "INSERT INTO customer_project_photos (project_id, image_url, caption) VALUES (%s, %s, %s)",
                    (project_id, uploaded_url, stage)
                )
                photos_added += 1

    if image_url:
        if not first_image:
            first_image = image_url
        execute(
            "INSERT INTO customer_project_photos (project_id, image_url, caption) VALUES (%s, %s, %s)",
            (project_id, image_url, stage)
        )
        photos_added += 1

    if first_image:
        execute("UPDATE customer_projects SET image_url=%s WHERE id=%s", (first_image, project_id))

    flash(f"Building project '{title}' assigned to customer successfully with {photos_added} photo(s)!", "success")
    return redirect(url_for("admin") + "#customer-projects")


@app.route("/admin/customer-projects/<int:project_id>/update", methods=["POST"])
@admin_required
def update_customer_project(project_id):
    stage = request.form.get("stage", "").strip()
    try:
        progress = max(0, min(100, int(request.form.get("progress", "0"))))
    except (ValueError, TypeError):
        progress = 0
    latest_update = request.form.get("latest_update", "").strip()
    photo_caption = request.form.get("photo_caption", "").strip() or stage
    image_url = request.form.get("image_url", "").strip()
    image_files = request.files.getlist("image_files")
    single_file = request.files.get("image_file")
    if single_file and single_file.filename and single_file not in image_files:
        image_files.append(single_file)

    execute(
        """UPDATE customer_projects 
           SET stage=%s, progress=%s, latest_update=%s, updated_at=CURRENT_TIMESTAMP
           WHERE id=%s""",
        (stage, progress, latest_update, project_id)
    )

    new_photos_count = 0
    latest_img = ""
    for f in image_files:
        if f and f.filename:
            uploaded_url = save_uploaded_image(f)
            if uploaded_url:
                latest_img = uploaded_url
                execute(
                    "INSERT INTO customer_project_photos (project_id, image_url, caption) VALUES (%s, %s, %s)",
                    (project_id, uploaded_url, photo_caption)
                )
                new_photos_count += 1

    if image_url:
        latest_img = image_url
        execute(
            "INSERT INTO customer_project_photos (project_id, image_url, caption) VALUES (%s, %s, %s)",
            (project_id, image_url, photo_caption)
        )
        new_photos_count += 1

    if latest_img:
        execute("UPDATE customer_projects SET image_url=%s WHERE id=%s", (latest_img, project_id))

    if new_photos_count > 0:
        flash(f"Project status updated and {new_photos_count} new photo(s) added to gallery!", "success")
    else:
        flash("Customer project status and progress updated successfully!", "success")
    return redirect(url_for("admin") + "#customer-projects")


@app.route("/admin/customer-projects/photos/<int:photo_id>/delete", methods=["POST"])
@admin_required
def delete_customer_project_photo(photo_id):
    execute("DELETE FROM customer_project_photos WHERE id=%s", (photo_id,))
    flash("Photo removed from gallery.", "info")
    return redirect(url_for("admin") + "#customer-projects")


@app.route("/admin/customer-projects/<int:project_id>/delete", methods=["POST"])
@admin_required
def delete_customer_project(project_id):
    execute("DELETE FROM customer_projects WHERE id=%s", (project_id,))
    flash("Customer project deleted successfully.", "info")
    return redirect(url_for("admin") + "#customer-projects")


@app.route("/admin/users/<int:target_user_id>/reset-password", methods=["POST"])
@admin_required
def admin_reset_user_password(target_user_id):
    new_password = request.form.get("new_password", "").strip()
    if not new_password or len(new_password) < 8:
        flash("Password must be at least 8 characters long.", "error")
        return redirect(url_for("admin") + "#registered-users")

    target_user = query_one("SELECT id, name, email FROM users WHERE id=%s", (target_user_id,))
    if not target_user:
        flash("User not found.", "error")
        return redirect(url_for("admin") + "#registered-users")

    if target_user["email"].lower() in get_admin_emails():
        flash("Cannot reset admin password from here.", "error")
        return redirect(url_for("admin") + "#registered-users")

    execute("UPDATE users SET password_hash=%s WHERE id=%s", (generate_password_hash(new_password), target_user_id))
    flash(f"Password for {target_user['name']} has been reset successfully.", "success")
    return redirect(url_for("admin") + "#registered-users")


@app.route("/ai-design", methods=["GET", "POST"])
def ai_design():
    image_data = None
    prompt_used = ""
    if request.method == "POST":
        prompt_used = request.form.get("prompt", "").strip()
        if not prompt_used:
            flash("Describe the house design first.", "error")
        elif len(prompt_used) > 1000:
            flash("Please keep the prompt under 1000 characters.", "error")
        elif not os.getenv("OPENAI_API_KEY"):
            flash("AI design is not configured yet. Add OPENAI_API_KEY to your .env file.", "error")
        else:
            try:
                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                response = client.images.generate(
                    model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
                    prompt=(
                        "Create a high-quality architectural concept visualization "
                        "of a house. This is an inspirational concept, not a construction "
                        "blueprint. Include no text or watermark. User brief: " + prompt_used
                    ),
                    size="1024x1024",
                )
                image_data = response.data[0].b64_json
                if not image_data:
                    flash("The image service returned no image. Please try again.", "error")
            except Exception:
                app.logger.exception("AI image generation failed")
                flash("Image generation failed. Check your API key, account access, and API billing, then try again.", "error")
    return render_template("ai_design.html", image_data=image_data, prompt_used=prompt_used)


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403,
                           message="This page is for the administrator only."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404,
                           message="The page you requested could not be found."), 404


if __name__ == "__main__":
    app.run(debug=True, port=9002)

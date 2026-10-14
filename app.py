import base64
import os
import re
import time
import uuid
from decimal import Decimal, InvalidOperation
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
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_image(file_storage):
    if not file_storage or not file_storage.filename:
        return ""
    if not allowed_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"proj_{int(time.time())}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try:
        img = Image.open(file_storage)
        if ext in ("jpg", "jpeg") and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > 1920:
            ratio = 1920 / img.width
            new_height = int(img.height * ratio)
            img = img.resize((1920, new_height), Image.Resampling.LANCZOS)
        img.save(filepath, optimize=True, quality=88)
    except Exception:
        file_storage.seek(0)
        file_storage.save(filepath)
    return f"/static/uploads/projects/{filename}"


def db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root"),
        database=os.getenv("DB_NAME", "construction_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def query_all(sql, params=()):
    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


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


def is_admin():
    if not session.get("user_id"):
        return False
    admin_email = os.getenv("ADMIN_EMAIL", "shreekhadapaticontruction@gamil.com").lower()
    return (
        session.get("email", "").lower() == admin_email
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


@app.route("/")
def home():
    projects = query_all(
        "SELECT * FROM projects ORDER BY created_at DESC LIMIT 3"
    )
    return render_template("index.html", projects=projects)


@app.route("/projects")
def projects():
    rows = query_all("SELECT * FROM projects ORDER BY created_at DESC")
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
        elif email == os.getenv("ADMIN_EMAIL", "shreekhadapaticontruction@gamil.com").lower():
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
    admin_email = os.getenv("ADMIN_EMAIL", "shreekhadapaticontruction@gamil.com").lower()
    registered_customers = [
        u for u in users if u["email"].lower() != admin_email
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

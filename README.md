# Shree Khadapati Balaji Construction Website (Flask + MySQL)

A starter construction company website with:
- Home page and project portfolio
- Construction cost estimator
- Customer signup/login using hashed passwords
- Contact enquiry form stored in MySQL
- Admin dashboard (add/delete projects, view enquiries and users)
- Optional AI house concept image generation through the OpenAI API

## 1. Requirements
- Python 3.10+
- MySQL Server 8+
- VS Code

## 2. Create a virtual environment
Open this folder in VS Code. In the terminal:

### Windows PowerShell
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use Command Prompt:
```bat
.venv\Scripts\activate.bat
```

## 3. Configure MySQL
Start MySQL Server. Open MySQL Workbench or MySQL command line and run the contents of `schema.sql`.

If using the command line:
```sql
SOURCE C:/full/path/to/construction_company_website/schema.sql;
```
Replace the path with the real path on your computer.

## 4. Configure environment variables
Copy `.env.example` to a new file named `.env`. Fill in your actual MySQL password and create a long random `SECRET_KEY`.
Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` to values you control.

**Important:** The admin account is not created by `schema.sql`. First start the app, then create a user using the normal Sign Up page with the exact same email as `ADMIN_EMAIL` and a password matching `ADMIN_PASSWORD`. That signup email is reserved, so this direct approach is blocked by design. Instead, create the admin record once using the helper below, then log in.

### Create the admin account (one time)
With your `.env` completed, run:
```powershell
python
```
Then paste:
```python
from app import execute
from werkzeug.security import generate_password_hash
import os
email = os.getenv("ADMIN_EMAIL", "admin@example.com").lower()
password = os.getenv("ADMIN_PASSWORD", "ChangeThisAdminPassword123!")
name = "Site Admin"
execute(
    "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
    (name, email, generate_password_hash(password))
)
print("Admin created. Log in using ADMIN_EMAIL and ADMIN_PASSWORD.")
exit()
```
If it says the email already exists, the admin record has already been created. Use the password stored for that record or update its hash intentionally.

## 5. Run the website
```powershell
python app.py
```
Open http://127.0.0.1:9000 in your browser.

## 6. Enable AI House Design (optional)
1. Obtain an API key from your AI provider account and ensure image generation is enabled for it.
2. Add the key to `.env` as `OPENAI_API_KEY=...`.
3. Keep `OPENAI_IMAGE_MODEL=gpt-image-1` unless your account's available image model differs.
4. Restart Flask and open `/ai-design`.

API use may incur charges. Never commit `.env` or expose the API key in frontend code.

## Important production notes
This is a learning starter, not a production-ready service. Before public deployment, add CSRF protection, rate limiting, email verification/password reset, secure cookie settings, a proper admin role stored in the database, logging, backups and HTTPS. Do not deploy Flask debug mode publicly. AI outputs are conceptual images, not construction-ready engineering drawings. Cost estimates are indicative only.

from flask import Flask, render_template, request, redirect, session, send_from_directory
from flask_mail import Mail, Message
import sqlite3
import os
import sys
from werkzeug.utils import secure_filename
from config import SECRET_KEY, DATABASE, MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER

# ---------------- APP SETUP ----------------
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Email Configuration
app.config['MAIL_SERVER'] = MAIL_SERVER
app.config['MAIL_PORT'] = MAIL_PORT
app.config['MAIL_USE_TLS'] = MAIL_USE_TLS
app.config['MAIL_USERNAME'] = MAIL_USERNAME
app.config['MAIL_PASSWORD'] = MAIL_PASSWORD
app.config['MAIL_DEFAULT_SENDER'] = MAIL_DEFAULT_SENDER

mail = Mail(app)

# ---------------- EMAIL HELPER ----------------
def get_all_admin_emails():
    """Get all admin email addresses from the database"""
    conn = get_db()
    admins = conn.execute("SELECT email FROM users WHERE role='admin'").fetchall()
    conn.close()
    return [admin['email'] for admin in admins]

def send_email(subject, recipients, body):
    """Send email notification"""
    try:
        msg = Message(subject, recipients=recipients, body=body)
        mail.send(msg)
        print(f"✓ Email sent: {subject} to {recipients}", file=sys.stdout)
        sys.stdout.flush()
    except Exception as e:
        print(f"✗ EMAIL FAILED: {subject} | Error: {str(e)}", file=sys.stderr)
        sys.stderr.flush()

# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            author TEXT,
            semester TEXT,
            category TEXT,
            status TEXT DEFAULT 'available'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            book_id INTEGER,
            status TEXT
        )
    """)

    # Ensure 'semester' column exists for older databases
    cursor.execute("PRAGMA table_info(books)")
    cols = [row[1] for row in cursor.fetchall()]
    if 'semester' not in cols:
        cursor.execute("ALTER TABLE books ADD COLUMN semester TEXT")
    if 'filename' in cols:
        # Drop old columns if they exist (SQLite doesn't support DROP, so just note it)
        pass

    conn.commit()
    conn.close()

# ---------------- AUTH ----------------
@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/admin" if session["role"] == "admin" else "/student")
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = get_db()
        cursor = conn.cursor()
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]
        try:
            cursor.execute(
                "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
                (name, email, password, role)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return "User already exists"
        conn.close()
        
        # Send welcome email to new user
        send_email(
            subject="🎉 Welcome to Greenfield Library!",
            recipients=[email],
            body=f"Hello {name},\n\nYour account has been created successfully!\n\nRole: {role}\nEmail: {email}\n\nYou can now log in and start using the library system.\n\nHappy learning!"
        )
        
        # Notify all admins about new registration
        admin_emails = get_all_admin_emails()
        if admin_emails:
            send_email(
                subject="👤 New User Registration",
                recipients=admin_emails,
                body=f"A new {role} has registered in the system.\n\nName: {name}\nEmail: {email}\nRole: {role}"
            )
        
        return redirect("/login")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (request.form["email"], request.form["password"])
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            
            # Send login notification email
            if user["role"] == "student":
                send_email(
                    subject="🔐 Login Notification",
                    recipients=["kushucon@gmail.com"],
                    body=f"Student Login Alert:\n\nName: {user['name']}\nEmail: {user['email']}\nTime: Login successful\n\nThis is an automated notification."
                )
            
            return redirect("/admin" if user["role"] == "admin" else "/student")

        return "Invalid credentials"
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/about")
def about():
    return render_template("about.html")

# ---------------- DASHBOARDS ----------------
@app.route("/student")
def student_dashboard():
    if session.get("role") != "student":
        return redirect("/login")
    
    conn = get_db()
    categories = conn.execute("SELECT DISTINCT category FROM books WHERE status='available' ORDER BY category").fetchall()
    conn.close()
    
    return render_template("student_dashboard.html", categories=categories)


@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect("/login")
    
    conn = get_db()
    categories = conn.execute("SELECT DISTINCT category FROM books ORDER BY category").fetchall()

    # Metrics for dashboard
    total_books = conn.execute("SELECT COUNT(*) as count FROM books").fetchone()["count"]
    books_approved = conn.execute("SELECT COUNT(*) as count FROM requests WHERE status='approved'").fetchone()["count"]
    books_lended = conn.execute("SELECT COUNT(DISTINCT book_id) as count FROM requests WHERE status='approved'").fetchone()["count"]
    total_requests = conn.execute("SELECT COUNT(*) as count FROM requests").fetchone()["count"]

    conn.close()
    
    return render_template(
        "admin_dashboard.html",
        categories=categories,
        total_books=total_books,
        books_approved=books_approved,
        books_lended=books_lended,
        total_requests=total_requests
    )

# ---------------- ADMIN: ALL BOOKS ----------------
@app.route("/admin-books")
def admin_books():
    if session.get("role") != "admin":
        return redirect("/login")

    category = request.args.get("category")
    search = request.args.get("search", "").lower()

    conn = get_db()
    if category:
        books = conn.execute("SELECT * FROM books WHERE category=?", (category,)).fetchall()
    else:
        books = conn.execute("SELECT * FROM books").fetchall()
    
    categories = conn.execute("SELECT DISTINCT category FROM books ORDER BY category").fetchall()
    conn.close()

    # Filter by search
    if search:
        books = [b for b in books if search in b["title"].lower() or search in b["author"].lower()]

    return render_template("admin_books.html", books=books, categories=categories, current_category=category, search=search)

# ---------------- BOOKS ----------------
@app.route("/upload", methods=["GET", "POST"])
def upload_book():
    if session.get("role") != "admin":
        return redirect("/login")

    if request.method == "POST":
        title = request.form["title"]
        author = request.form["author"]
        semester = request.form["semester"]
        category = request.form["category"]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO books (title,author,semester,category,status) VALUES (?,?,?,?,?)",
            (title, author, semester, category, "available")
        )
        conn.commit()
        conn.close()
        
        # Notify all admins about the new book upload
        admin_emails = get_all_admin_emails()
        if admin_emails:
            send_email(
                subject="📚 New Book Added",
                recipients=admin_emails,
                body=f"A new book has been added to the library system.\n\nTitle: {title}\nAuthor: {author}\nSemester: {semester}\nCategory: {category}\n\nYou can manage it from the admin panel."
            )
        
        return redirect("/admin")

    return render_template("upload_book.html")


# ---------------- BOOKS ----------------
@app.route("/books")
def books():
    if session.get("role") != "student":
        return redirect("/login")

    category = request.args.get("category")
    search = request.args.get("search", "").lower()

    conn = get_db()
    if category:
        books_list = conn.execute("SELECT * FROM books WHERE category=? ORDER BY status DESC, title ASC", (category,)).fetchall()
    else:
        books_list = conn.execute("SELECT * FROM books ORDER BY status DESC, title ASC").fetchall()
    
    categories = conn.execute("SELECT DISTINCT category FROM books ORDER BY category").fetchall()
    
    # Get student's requested books with status
    user_requests = conn.execute(
        "SELECT book_id, status FROM requests WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()
    
    conn.close()

    # Create a dict of book_id -> request_status for easy lookup
    request_status = {req["book_id"]: req["status"] for req in user_requests}

    # Filter by search
    if search:
        books_list = [b for b in books_list if search in b["title"].lower() or search in b["author"].lower()]

    return render_template("books.html", books=books_list, categories=categories, current_category=category, search=search, request_status=request_status)


@app.route("/download/<filename>")
def download(filename):
    if "user_id" not in session:
        return redirect("/login")
    return redirect("/books")

# -------- TOGGLE BOOK STATUS (Admin) --------
@app.route("/toggle-status/<int:book_id>")
def toggle_status(book_id):
    if session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    book = conn.execute("SELECT status FROM books WHERE id=?", (book_id,)).fetchone()
    
    if book:
        new_status = "unavailable" if book["status"] == "available" else "available"
        conn.execute("UPDATE books SET status=? WHERE id=?", (new_status, book_id))
        conn.commit()
    
    conn.close()
    return redirect("/admin-books")

# ---------------- REQUEST SYSTEM ----------------
@app.route("/request/<int:book_id>")
def request_book(book_id):
    if session.get("role") != "student":
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()
    
    # Check if already requested
    cursor.execute(
        "SELECT * FROM requests WHERE user_id=? AND book_id=?",
        (session["user_id"], book_id)
    )
    existing_request = cursor.fetchone()
    
    if not existing_request:
        # Get book info
        book = conn.execute("SELECT title FROM books WHERE id=?", (book_id,)).fetchone()
        
        # Insert request
        cursor.execute(
            "INSERT INTO requests (user_id,book_id,status) VALUES (?,?,?)",
            (session["user_id"], book_id, "pending")
        )
        conn.commit()
        
        # Send email to all admins
        if book:
            admin_emails = get_all_admin_emails()
            if admin_emails:
                send_email(
                    subject="📚 New Book Request",
                    recipients=admin_emails,
                    body=f"Student {session['user_name']} ({session['user_email']}) has requested the book: {book['title']}\n\nPlease review and approve the request."
                )
    
    conn.close()
    return redirect("/books")


@app.route("/requests")
def view_requests():
    if session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    data = conn.execute("""
        SELECT requests.id, users.name, users.email, books.title, requests.status
        FROM requests
        JOIN users ON users.id=requests.user_id
        JOIN books ON books.id=requests.book_id
    """).fetchall()
    conn.close()
    return render_template("requests.html", requests=data)


@app.route("/approve/<int:req_id>")
def approve(req_id):
    if session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    
    # Get request info for email
    request_info = conn.execute("""
        SELECT users.email, users.name, books.title
        FROM requests
        JOIN users ON users.id=requests.user_id
        JOIN books ON books.id=requests.book_id
        WHERE requests.id=?
    """, (req_id,)).fetchone()
    
    # Update status
    conn.execute("UPDATE requests SET status='approved' WHERE id=?", (req_id,))
    conn.commit()
    conn.close()
    
    # Send email to student
    if request_info:
        send_email(
            subject="✅ Book Request Approved!",
            recipients=[request_info["email"]],
            body=f"Hello {request_info['name']},\n\nYour request for the book '{request_info['title']}' has been approved!\n\nYou can now download it from your dashboard.\n\nHappy reading!"
        )
    
    return redirect("/requests")

# ---------------- STUDENT: MY BOOKS ----------------
@app.route("/my-books")
def my_books():
    if session.get("role") != "student":
        return redirect("/login")

    conn = get_db()
    requests_data = conn.execute("""
        SELECT books.id, books.title, books.author, books.category, books.semester, books.status, requests.status as request_status
        FROM books
        JOIN requests ON books.id=requests.book_id
        WHERE requests.user_id=? AND requests.status='approved'
        ORDER BY books.title ASC
    """, (session["user_id"],)).fetchall()
    conn.close()
    
    return render_template("my_books.html", books=requests_data)

# -------- ADMIN: STUDENT MANAGEMENT --------
@app.route("/students")
def students():
    if session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    search = request.args.get("search", "").lower()
    
    # Get all students with their stats
    all_students = conn.execute("SELECT id, name, email FROM users WHERE role='student' ORDER BY name").fetchall()
    
    students_data = []
    for student in all_students:
        # Count requests
        total_requests = conn.execute(
            "SELECT COUNT(*) as count FROM requests WHERE user_id=?",
            (student["id"],)
        ).fetchone()["count"]
        
        # Count approved
        approved_count = conn.execute(
            "SELECT COUNT(*) as count FROM requests WHERE user_id=? AND status='approved'",
            (student["id"],)
        ).fetchone()["count"]
        
        # Count pending
        pending_count = conn.execute(
            "SELECT COUNT(*) as count FROM requests WHERE user_id=? AND status='pending'",
            (student["id"],)
        ).fetchone()["count"]
        
        students_data.append({
            "id": student["id"],
            "name": student["name"],
            "email": student["email"],
            "total_requests": total_requests,
            "approved": approved_count,
            "pending": pending_count
        })
    
    # Filter by search
    if search:
        students_data = [s for s in students_data if search in s["name"].lower() or search in s["email"].lower()]
    
    conn.close()
    return render_template("students.html", students=students_data, search=search)

@app.route("/student/<int:student_id>")
def student_detail(student_id):
    if session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    
    # Get student info
    student = conn.execute("SELECT * FROM users WHERE id=? AND role='student'", (student_id,)).fetchone()
    
    if not student:
        conn.close()
        return "Student not found", 404
    
    # Get all student's requests with book details
    requests_data = conn.execute("""
        SELECT requests.id, requests.status, books.title, books.author, books.category, requests.user_id
        FROM requests
        JOIN books ON books.id=requests.book_id
        WHERE requests.user_id=?
        ORDER BY requests.id DESC
    """, (student_id,)).fetchall()
    
    # Get stats
    total_requests = len(requests_data)
    approved_count = sum(1 for r in requests_data if r["status"] == "approved")
    pending_count = sum(1 for r in requests_data if r["status"] == "pending")
    
    conn.close()
    
    return render_template("student_detail.html", 
                         student=student, 
                         requests=requests_data,
                         total_requests=total_requests,
                         approved_count=approved_count,
                         pending_count=pending_count)

# ---------------- MAIN ----------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)

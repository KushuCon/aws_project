from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import boto3
import uuid
from botocore.exceptions import ClientError
from functools import wraps
from datetime import datetime

# APP SETUP
app = Flask(__name__)
REGION = 'us-east-1'

# AWS Services
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns = boto3.client('sns', region_name=REGION)

# Config
app.secret_key = 'any-secret-key-for-sessions'
SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:050752651673:sns_aws_capstone' # TEACHER: Paste your SNS Topic ARN here

# DynamoDB Tables
users_table = dynamodb.Table('LibraryUsers')
books_table = dynamodb.Table('LibraryBooks')
requests_table = dynamodb.Table('LibraryRequests')


# SNS HELPER
def notify(subject, msg):
    """Send SNS notification"""
    try:
        if SNS_TOPIC_ARN:
            sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject[:100], Message=msg)
            print(f"✓ {subject}")
    except ClientError as e:
        print(f"✗ Notification error: {e}")

# DECORATORS
def auth_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# HELPERS
def get_books_with_filters(category=None):
    """Get books, optionally filtered by category"""
    try:
        if category:
            resp = books_table.query(IndexName='CategoryStatusIndex',
                KeyConditionExpression='category = :cat',
                ExpressionAttributeValues={':cat': category})
        else:
            resp = books_table.scan()
        return resp.get('Items', [])
    except ClientError as e:
        print(f"Books error: {e}")
        return []

def get_categories():
    """Get all unique categories"""
    try:
        resp = books_table.scan(ProjectionExpression='category')
        cats = set(b.get('category') for b in resp.get('Items', []) if 'category' in b)
        return sorted(list(cats))
    except ClientError as e:
        print(f"Categories error: {e}")
        return []

def get_student_requests(user_id):
    """Get student's requests with status dict"""
    try:
        resp = requests_table.query(IndexName='UserIdIndex',
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': user_id})
        return {r['book_id']: r['status'] for r in resp.get('Items', [])}
    except ClientError as e:
        print(f"Requests error: {e}")
        return {}

# AUTH
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for('admin_dashboard' if session["role"] == "admin" else 'student_dashboard'))
    return redirect(url_for('login'))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name, email, pwd, role = request.form["name"], request.form["email"], request.form["password"], request.form["role"]
        
        try:
            if 'Item' in users_table.get_item(Key={'email': email}):
                return "User already exists"
            
            users_table.put_item(Item={'email': email, 'id': str(uuid.uuid4()), 'name': name, 'password': generate_password_hash(pwd), 'role': role})
            notify("New Registration", f"New {role}: {name} ({email})")
            return redirect(url_for('login'))
        except ClientError as e:
            print(f"Register error: {e}")
            return "Registration failed", 500
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email, pwd = request.form["email"], request.form["password"]
        try:
            resp = users_table.get_item(Key={'email': email})
            if 'Item' in resp:
                user = resp['Item']
                if check_password_hash(user['password'], pwd):
                    session.update(user_id=user["id"], role=user["role"], user_name=user["name"], user_email=user["email"])
                    notify("Login", f"{user['name']} logged in")
                    return redirect(url_for('admin_dashboard' if user["role"] == "admin" else 'student_dashboard'))
            return "Invalid credentials"
        except ClientError as e:
            print(f"Login error: {e}")
            return "Login failed", 500
    return render_template("login.html")

@app.route("/logout")
@auth_required()
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/about")
def about():
    return render_template("about.html")

# DASHBOARDS
@app.route("/student")
@auth_required('student')
def student_dashboard():
    try:
        resp = books_table.query(IndexName='StatusIndex', KeyConditionExpression='#s = :avail',
            ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':avail': 'available'})
        cats = sorted(set(b.get('category') for b in resp.get('Items', []) if 'category' in b))
    except ClientError as e:
        print(f"Dashboard error: {e}")
        cats = []
    return render_template("student_dashboard.html", categories=cats)

@app.route("/admin")
@auth_required('admin')
def admin_dashboard():
    try:
        books_resp = books_table.scan(ProjectionExpression='category')
        cats = sorted(set(b.get('category') for b in books_resp.get('Items', []) if 'category' in b))
        
        appr_resp = requests_table.query(IndexName='StatusIndex',
            KeyConditionExpression='#s = :appr',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':appr': 'approved'})
        appr_items = appr_resp.get('Items', [])
        
        total_reqs = requests_table.scan(Select='COUNT').get('Count', 0)
    except ClientError as e:
        print(f"Admin dashboard error: {e}")
        cats, appr_items, total_reqs = [], [], 0
    
    return render_template("admin_dashboard.html", categories=cats, total_books=books_resp['Count'],
                         books_approved=len(appr_items), books_lended=len(set(r['book_id'] for r in appr_items)),
                         total_requests=total_reqs)

# BOOKS
@app.route("/admin-books")
@auth_required('admin')
def admin_books():
    cat = request.args.get("category")
    search = request.args.get("search", "").lower()
    books_list = get_books_with_filters(cat)
    if search:
        books_list = [b for b in books_list if search in b.get("title", "").lower() or search in b.get("author", "").lower()]
    return render_template("admin_books.html", books=books_list, categories=get_categories(), current_category=cat, search=search)

@app.route("/upload", methods=["GET", "POST"])
@auth_required('admin')
def upload_book():
    if request.method == "POST":
        try:
            books_table.put_item(Item={'id': str(uuid.uuid4()), 'title': request.form["title"],
                'author': request.form["author"], 'semester': request.form["semester"],
                'category': request.form["category"], 'status': 'available'})
            notify("New Book", f"{request.form['title']} by {request.form['author']}")
            return redirect(url_for('admin_dashboard'))
        except ClientError as e:
            print(f"Upload error: {e}")
            return "Upload failed", 500
    return render_template("upload_book.html")

@app.route("/books")
@auth_required('student')
def books():
    cat = request.args.get("category")
    search = request.args.get("search", "").lower()
    books_list = get_books_with_filters(cat)
    req_status = get_student_requests(session["user_id"])
    if search:
        books_list = [b for b in books_list if search in b.get("title", "").lower() or search in b.get("author", "").lower()]
    books_list.sort(key=lambda x: (x.get('status') != 'available', x.get('title', '')))
    return render_template("books.html", books=books_list, categories=get_categories(), current_category=cat, search=search, request_status=req_status)

@app.route("/toggle-status/<book_id>")
@auth_required('admin')
def toggle_status(book_id):
    try:
        resp = books_table.get_item(Key={'id': book_id})
        if 'Item' in resp:
            book = resp['Item']
            new_status = "unavailable" if book.get("status") == "available" else "available"
            books_table.update_item(Key={'id': book_id}, UpdateExpression='SET #s = :st',
                ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':st': new_status})
    except ClientError as e:
        print(f"Toggle error: {e}")
    return redirect(url_for('admin_books'))

# REQUESTS
@app.route("/request/<book_id>")
@auth_required('student')
def request_book(book_id):
    try:
        existing = requests_table.query(IndexName='UserIdIndex',
            KeyConditionExpression='user_id = :uid', FilterExpression='book_id = :bid',
            ExpressionAttributeValues={':uid': session["user_id"], ':bid': book_id})
        
        if not existing.get('Items'):
            book_resp = books_table.get_item(Key={'id': book_id})
            requests_table.put_item(Item={'id': str(uuid.uuid4()), 'user_id': session["user_id"],
                'user_email': session["user_email"], 'book_id': book_id, 'status': 'pending',
                'created_at': datetime.utcnow().isoformat()})
            if 'Item' in book_resp:
                notify("New Request", f"{session['user_name']} requested '{book_resp['Item'].get('title')}'")
    except ClientError as e:
        print(f"Request error: {e}")
    return redirect(url_for('books'))

@app.route("/requests")
@auth_required('admin')
def view_requests():
    try:
        all_reqs = requests_table.scan().get('Items', [])
        enriched = []
        for r in all_reqs:
            u = users_table.get_item(Key={'email': r.get('user_email', '')}).get('Item', {})
            b = books_table.get_item(Key={'id': r.get('book_id', '')}).get('Item', {})
            enriched.append({'id': r.get('id'), 'name': u.get('name', 'Unknown'),
                'email': u.get('email', 'Unknown'), 'title': b.get('title', 'Unknown'), 'status': r.get('status')})
    except ClientError as e:
        print(f"View requests error: {e}")
        enriched = []
    return render_template("requests.html", requests=enriched)

@app.route("/approve/<req_id>")
@auth_required('admin')
def approve(req_id):
    try:
        req_resp = requests_table.get_item(Key={'id': req_id})
        if 'Item' in req_resp:
            req = req_resp['Item']
            u = users_table.get_item(Key={'email': req.get('user_email', '')}).get('Item', {})
            b = books_table.get_item(Key={'id': req.get('book_id')}).get('Item', {})
            requests_table.update_item(Key={'id': req_id}, UpdateExpression='SET #s = :st',
                ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':st': 'approved'})
            if u and b:
                notify("Request Approved", f"{u.get('name')}: Your request for '{b.get('title')}' approved!")
    except ClientError as e:
        print(f"Approve error: {e}")
    return redirect(url_for('view_requests'))

# MY BOOKS
@app.route("/my-books")
@auth_required('student')
def my_books():
    try:
        resp = requests_table.query(IndexName='UserIdIndex',
            KeyConditionExpression='user_id = :uid AND #s = :appr',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':uid': session["user_id"], ':appr': 'approved'})
        my_books_list = []
        for r in resp.get('Items', []):
            b_resp = books_table.get_item(Key={'id': r.get('book_id')})
            if 'Item' in b_resp:
                b = b_resp['Item']
                b['request_status'] = r.get('status')
                my_books_list.append(b)
        my_books_list.sort(key=lambda x: x.get('title', ''))
    except ClientError as e:
        print(f"My books error: {e}")
        my_books_list = []
    return render_template("my_books.html", books=my_books_list)

# STUDENT MANAGEMENT
@app.route("/students")
@auth_required('admin')
def students():
    search = request.args.get("search", "").lower()
    try:
        stud_resp = users_table.query(IndexName='RoleIndex', KeyConditionExpression='#r = :st',
            ExpressionAttributeNames={'#r': 'role'}, ExpressionAttributeValues={':st': 'student'})
        all_students = stud_resp.get('Items', [])
        all_reqs = requests_table.scan().get('Items', [])
        
        stud_data = []
        for s in all_students:
            s_reqs = [r for r in all_reqs if r.get('user_id') == s.get('id')]
            stud_data.append({'id': s.get('id'), 'name': s.get('name', 'Unknown'),
                'email': s.get('email', 'Unknown'), 'total_requests': len(s_reqs),
                'approved': sum(1 for r in s_reqs if r.get('status') == 'approved'),
                'pending': sum(1 for r in s_reqs if r.get('status') == 'pending')})
        
        if search:
            stud_data = [s for s in stud_data if search in s["name"].lower() or search in s["email"].lower()]
        stud_data.sort(key=lambda x: x["name"])
    except ClientError as e:
        print(f"Students error: {e}")
        stud_data = []
    return render_template("students.html", students=stud_data, search=search)

@app.route("/student/<student_id>")
@auth_required('admin')
def student_detail(student_id):
    try:
        stud_resp = users_table.query(IndexName='RoleIndex', KeyConditionExpression='#r = :st',
            FilterExpression='id = :sid', ExpressionAttributeNames={'#r': 'role'},
            ExpressionAttributeValues={':st': 'student', ':sid': student_id})
        students_list = stud_resp.get('Items', [])
        if not students_list:
            return "Student not found", 404
        student = students_list[0]
        
        reqs_resp = requests_table.query(IndexName='UserIdIndex', KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': student_id})
        reqs_data = []
        for r in reqs_resp.get('Items', []):
            b_resp = books_table.get_item(Key={'id': r.get('book_id')})
            if 'Item' in b_resp:
                b = b_resp['Item']
                reqs_data.append({'id': r.get('id'), 'status': r.get('status'), 'title': b.get('title', 'Unknown'),
                    'author': b.get('author', 'Unknown'), 'category': b.get('category', 'Unknown'),
                    'user_id': r.get('user_id'), 'created_at': r.get('created_at', '')})
        reqs_data.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    except ClientError as e:
        print(f"Student detail error: {e}")
        return "Error loading student", 500
    
    return render_template("student_detail.html", student=student, requests=reqs_data,
                         total_requests=len(reqs_data), approved_count=sum(1 for r in reqs_data if r.get('status') == 'approved'),
                         pending_count=sum(1 for r in reqs_data if r.get('status') == 'pending'))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
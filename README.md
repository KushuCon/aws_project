# 📚 Library Management System

A cloud-based library management system built with Flask and AWS services, enabling students to browse and request books while admins manage the library inventory and approve requests. This project demonstrates serverless architecture using AWS DynamoDB for data persistence and SNS for real-time notifications.

## 🎯 Project Overview

The Library Management System is a full-stack web application designed to digitize and streamline library operations. It provides role-based access control with separate interfaces for students and administrators, real-time notifications for important events, and efficient book request management.

## 🎥 Demo Video

Watch the complete project demonstration: [View Demo on Google Drive](https://drive.google.com/file/d/1FNfhSWkTDp8vHJSvTZPeStmSxIRAJ2ZO/view?usp=sharing)

## 🚀 Tech Stack

### Backend
- **Flask 3.1.2** - Lightweight Python web framework
- **Boto3 1.36.3** - AWS SDK for Python
- **Werkzeug 3.1.3** - WSGI utilities and password hashing

### AWS Services
- **DynamoDB** - NoSQL database for scalable data storage
- **SNS (Simple Notification Service)** - Real-time email notifications
- **EC2** - Application hosting and deployment
- **IAM** - Role-based access management

### Security
- Password hashing using Werkzeug's `generate_password_hash`
- Session-based authentication
- Role-based access control (RBAC)

## ✨ Features

### 👨‍🎓 Student Features:
- **User Registration & Login** - Secure account creation with hashed passwords
- **Browse Books** - View all available books with real-time availability status
- **Category Filtering** - Filter books by categories (Fiction, Science, Technology, etc.)
- **Search Functionality** - Search books by title or author name
- **Book Requests** - Request books for borrowing with one click
- **Request Tracking** - Monitor request status (pending/approved)
- **My Books** - View all approved book requests in one place
- **Dashboard** - Personalized student dashboard with quick access to features

### 👨‍💼 Admin Features:
- **Admin Dashboard** - Comprehensive overview with statistics
  - Total books count
  - Approved requests count
  - Books currently lent out
  - Total requests received
- **Book Management**
  - Add new books with details (title, author, semester, category)
  - Toggle book availability (available/unavailable)
  - Search and filter books
  - Category-based organization
- **Request Management**
  - View all student requests
  - Approve/reject book requests
  - Track request history
- **Student Management**
  - View all registered students
  - Monitor student activity (total requests, approved, pending)
  - Detailed student profiles with request history
  - Search students by name or email

### 🔔 Notification System:
- **Real-time SNS Notifications** for:
  - New user registrations
  - User logins
  - New book additions
  - Book requests submitted
  - Request approvals

## 🏗️ Architecture

### Application Architecture
```
Client (Browser)
    ↓
Flask Application (EC2)
    ↓
├── DynamoDB (Data Storage)
│   ├── LibraryUsers
│   ├── LibraryBooks
│   └── LibraryRequests
│
└── SNS (Notifications)
    └── Email Subscribers
```

### DynamoDB Schema

**LibraryUsers Table:**
- **Primary Key**: `email` (String)
- **Attributes**: `id`, `name`, `password` (hashed), `role`
- **GSI**: `RoleIndex` on `role` - Query users by role (student/admin)

**LibraryBooks Table:**
- **Primary Key**: `id` (String, UUID)
- **Attributes**: `title`, `author`, `semester`, `category`, `status`
- **GSIs**:
  - `CategoryStatusIndex` on `category` - Filter books by category
  - `StatusIndex` on `status` - Query available/unavailable books

**LibraryRequests Table:**
- **Primary Key**: `id` (String, UUID)
- **Attributes**: `user_id`, `user_email`, `book_id`, `status`, `created_at`
- **GSIs**:
  - `UserIdIndex` on `user_id` - Get all requests by a specific user
  - `StatusIndex` on `status` - Query pending/approved requests

## 🔐 Security Features

- **Password Security**: All passwords are hashed using Werkzeug's SHA-256 algorithm
- **Session Management**: Flask sessions with secure secret key
- **Role-Based Access Control**: Decorator-based authentication (`@auth_required`)
- **IAM Roles**: EC2 instance uses IAM roles (no hardcoded credentials)
- **Error Handling**: Comprehensive exception handling for all AWS operations

## 🛠️ Setup & Deployment

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/greenfield_library.git
   cd greenfield_library
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure AWS**
   - Create DynamoDB tables with required GSIs
   - Create SNS topic and update ARN in `app_aws.py`
   - Set up IAM role with DynamoDB and SNS permissions

4. **Run the application**
   ```bash
   python app_aws.py
   ```

## 📸 Screenshots

![Screenshot 1](Screenshot%202026-02-06%20192501.png)
![Screenshot 2](Screenshot%202026-02-06%20200533.png)
![Screenshot 3](Screenshot%202026-02-06%20200600.png)
![Screenshot 4](Screenshot%202026-02-06%20200613.png)
![Screenshot 5](Screenshot%202026-02-06%20200635.png)
![Screenshot 6](Screenshot%202026-02-06%20200652.png)
![Screenshot 7](Screenshot%202026-02-06%20200709.png)
![Screenshot 8](Screenshot%202026-02-06%20200805.png)

## 📝 License

This project is for educational purposes.

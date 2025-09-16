# LegacyVerse User API Documentation

## Overview
This API provides comprehensive user authentication and profile management functionality for the LegacyVerse application.

## Base URL
```
http://localhost:8000/api/user/
```

## Authentication
The API uses JWT (JSON Web Tokens) for authentication. Include the access token in the Authorization header:
```
Authorization: Bearer <your_access_token>
```

## API Endpoints

### Authentication APIs

#### 1. User Registration
**POST** `/auth/register/`

Register a new user account.

**Request Body:**
```json
{
    "fullname": "John Doe",
    "email": "john@example.com",
    "password": "securepassword123",
    "confirm_password": "securepassword123"
}
```

**Response:**
```json
{
    "message": "User registered successfully",
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "user": {
        "id": "uuid-here",
        "email": "john@example.com",
        "fullname": "John Doe",
        "username": "johndoe",
        "is_verified": false,
        "created_at": "2024-01-01T00:00:00Z"
    }
}
```

#### 2. User Login
**POST** `/auth/login/`

Authenticate user and get JWT tokens.

**Request Body:**
```json
{
    "email": "john@example.com",
    "password": "securepassword123"
}
```

**Response:**
```json
{
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "user": {
        "id": "uuid-here",
        "email": "john@example.com",
        "fullname": "John Doe",
        "username": "johndoe",
        "is_verified": false,
        "created_at": "2024-01-01T00:00:00Z"
    }
}
```

#### 3. User Logout
**POST** `/auth/logout/`

Logout user and blacklist refresh token.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response:**
```json
{
    "message": "Logout successful"
}
```

#### 4. Refresh Token
**POST** `/auth/refresh/`

Get new access token using refresh token.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response:**
```json
{
    "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

#### 5. Forgot Password
**POST** `/auth/forgot-password/`

Request password reset token.

**Request Body:**
```json
{
    "email": "john@example.com"
}
```

**Response:**
```json
{
    "message": "Password reset token sent to your email",
    "token": "uuid-token-here"
}
```

#### 6. Reset Password
**POST** `/auth/reset-password/`

Reset password using token.

**Request Body:**
```json
{
    "token": "uuid-token-here",
    "new_password": "newpassword123",
    "confirm_password": "newpassword123"
}
```

**Response:**
```json
{
    "message": "Password reset successful"
}
```

#### 7. Change Password
**POST** `/auth/change-password/`

Change password for authenticated user.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
    "old_password": "currentpassword123",
    "new_password": "newpassword123",
    "confirm_password": "newpassword123"
}
```

**Response:**
```json
{
    "message": "Password changed successfully"
}
```

### Profile APIs

#### 1. Get/Update Profile
**GET/PUT** `/profile/`

Get or update authenticated user's profile.

**Headers:**
```
Authorization: Bearer <access_token>
```

**GET Response:**
```json
{
    "username": "johndoe",
    "email": "john@example.com",
    "fullname": "John Doe",
    "image": "http://localhost:8000/media/profile_images/image.jpg",
    "bio": "Software developer passionate about technology",
    "location": "New York, USA",
    "website": "https://johndoe.com",
    "education": "Computer Science, MIT",
    "hobbies": "Reading, Hiking, Photography",
    "early_childhood": "Born and raised in a small town...",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
}
```

**PUT Request Body:**
```json
{
    "bio": "Updated bio text",
    "location": "San Francisco, USA",
    "website": "https://newwebsite.com",
    "education": "Updated education info",
    "hobbies": "Updated hobbies",
    "early_childhood": "Updated childhood story"
}
```

#### 2. Get Profile by Username
**GET** `/profile/<username>/`

Get public profile by username.

**Response:**
```json
{
    "username": "johndoe",
    "email": "john@example.com",
    "fullname": "John Doe",
    "image": "http://localhost:8000/media/profile_images/image.jpg",
    "bio": "Software developer passionate about technology",
    "location": "New York, USA",
    "website": "https://johndoe.com",
    "education": "Computer Science, MIT",
    "hobbies": "Reading, Hiking, Photography",
    "early_childhood": "Born and raised in a small town...",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
}
```

#### 3. Update Profile Image
**POST** `/profile/image/`

Upload or update profile image.

**Headers:**
```
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**Request Body:**
```
image: <file>
```

**Response:**
```json
{
    "image": "http://localhost:8000/media/profile_images/new_image.jpg"
}
```

#### 4. Delete Profile Image
**DELETE** `/profile/image/delete/`

Delete profile image.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
{
    "message": "Profile image deleted successfully"
}
```

## Error Responses

### 400 Bad Request
```json
{
    "field_name": ["Error message"]
}
```

### 401 Unauthorized
```json
{
    "detail": "Authentication credentials were not provided."
}
```

### 404 Not Found
```json
{
    "error": "User not found"
}
```

### 500 Internal Server Error
```json
{
    "error": "Internal server error"
}
```

## Features

### User Model Features
- **Custom User Model**: Extends Django's AbstractUser
- **UUID Primary Key**: Uses UUID instead of integer IDs
- **Auto-generated Username**: Username is automatically generated from fullname (non-editable)
- **Email Authentication**: Uses email as the primary authentication field
- **User Verification**: Built-in user verification system

### Profile Model Features
- **One-to-One Relationship**: Each user has one profile
- **Image Upload**: Profile image upload with automatic file handling
- **Rich Profile Fields**: Bio, location, website, education, hobbies, early childhood
- **Auto-creation**: Profile is automatically created when user registers

### Security Features
- **JWT Authentication**: Secure token-based authentication
- **Password Validation**: Django's built-in password validation
- **Token Blacklisting**: Refresh tokens are blacklisted on logout
- **Password Reset**: Secure password reset with time-limited tokens
- **CORS Support**: Configured for cross-origin requests

### Username Generation
The username is automatically generated from the user's fullname:
- Removes special characters and spaces
- Converts to lowercase
- Takes first 8 characters
- Adds numbers if username already exists
- Examples: "John Doe" → "johndoe", "John Smith" → "johnsmit1"

## Installation & Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

3. Create superuser:
```bash
python manage.py createsuperuser
```

4. Run development server:
```bash
python manage.py runserver
```

## Environment Variables

Create a `.env` file with the following variables:
```
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=legacyverse_db
DB_USER=postgres
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@legacyverse.com
```

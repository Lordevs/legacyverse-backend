# LegacyVerse - User Authentication & Profile Management API

A comprehensive Django REST API for user authentication and profile management with JWT-based authentication.

## Features

### Authentication
- ✅ User registration with email and password
- ✅ User login with JWT tokens
- ✅ Password reset functionality
- ✅ Password change for authenticated users
- ✅ Token refresh mechanism
- ✅ Secure logout with token blacklisting

### Profile Management
- ✅ Auto-generated usernames (non-editable)
- ✅ Rich profile fields (bio, location, website, education, hobbies, early childhood)
- ✅ Profile image upload/update/delete
- ✅ Public profile access by username
- ✅ Profile update functionality

### Security Features
- ✅ JWT-based authentication
- ✅ Password validation
- ✅ CORS support
- ✅ Secure file uploads
- ✅ UUID-based user IDs

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Database Setup
Make sure PostgreSQL is running and create a database named `legacyverse_db`.

### 3. Environment Variables
Create a `.env` file in the project root:
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=legacyverse_db
DB_USER=postgres
DB_PASSWORD=your-postgres-password
DB_HOST=localhost
DB_PORT=5432
```

### 4. Run Migrations
```bash
python manage.py migrate
```

### 5. Create Superuser
```bash
python manage.py createsuperuser
```

### 6. Start Development Server
```bash
python manage.py runserver
```

## API Endpoints

### Authentication
- `POST /api/user/auth/register/` - User registration
- `POST /api/user/auth/login/` - User login
- `POST /api/user/auth/logout/` - User logout
- `POST /api/user/auth/refresh/` - Refresh JWT token
- `POST /api/user/auth/forgot-password/` - Request password reset
- `POST /api/user/auth/reset-password/` - Reset password with token
- `POST /api/user/auth/change-password/` - Change password

### Profile Management
- `GET/PUT /api/user/profile/` - Get/update own profile
- `GET /api/user/profile/<username>/` - Get profile by username
- `POST /api/user/profile/image/` - Upload/update profile image
- `DELETE /api/user/profile/image/delete/` - Delete profile image

## API Documentation

For detailed API documentation with request/response examples, see [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

## Username Generation

Usernames are automatically generated from the user's fullname:
- Removes special characters and spaces
- Converts to lowercase
- Takes first 8 characters
- Adds numbers if username already exists

Examples:
- "John Doe" → "johndoe"
- "Jane Smith" → "janesmit"
- "John Doe" (second user) → "johndoe1"

## Project Structure

```
legacyverse/
├── user/                    # User app
│   ├── models.py           # User, Profile, PasswordResetToken models
│   ├── views.py            # API views
│   ├── serializers.py      # DRF serializers
│   ├── urls.py             # URL routing
│   ├── admin.py            # Admin configuration
│   ├── signals.py          # Django signals
│   └── apps.py             # App configuration
├── legacyverse/            # Main project
│   ├── settings.py         # Django settings
│   └── urls.py             # Main URL configuration
├── requirements.txt        # Python dependencies
├── API_DOCUMENTATION.md    # Detailed API docs
└── README.md              # This file
```

## Testing

You can test the API using tools like:
- Postman
- curl
- HTTPie
- Any REST client

Example registration request:
```bash
curl -X POST http://localhost:8000/api/user/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "fullname": "John Doe",
    "email": "john@example.com",
    "password": "securepassword123",
    "confirm_password": "securepassword123"
  }'
```

## Admin Panel

Access the Django admin panel at `http://localhost:8000/admin/` to manage users and profiles.

## Development

### Adding New Features
1. Create models in `user/models.py`
2. Create serializers in `user/serializers.py`
3. Create views in `user/views.py`
4. Add URLs in `user/urls.py`
5. Run migrations: `python manage.py makemigrations && python manage.py migrate`

### Database Management
- Create migrations: `python manage.py makemigrations`
- Apply migrations: `python manage.py migrate`
- Reset database: Delete migration files and run migrations again

## Production Deployment

For production deployment:
1. Set `DEBUG=False` in settings
2. Configure proper email settings
3. Use a production database
4. Set up proper static file serving
5. Configure HTTPS
6. Set up proper logging

## License

This project is part of the LegacyVerse application.

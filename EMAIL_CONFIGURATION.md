# Email Configuration Guide

This document explains how to configure email functionality for the LegacyVerse application.

## Environment Variables

Create a `.env` file in your project root with the following variables:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration
DB_NAME=legacyverse_db
DB_USER=postgres
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432

# Email Configuration
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@legacyverse.com

# Frontend URL (for email links)
FRONTEND_URL=http://localhost:3000
```

## Email Backend Configuration

### Development (Console Backend)
For development, emails are printed to the console:
```python
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

### Production (SMTP Backend)
For production, use SMTP:
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
```

## Gmail Configuration

1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App Password:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a password for "Mail"
   - Use this password in `EMAIL_HOST_PASSWORD`

## Email Templates

The application includes the following email templates:

- **Password Reset**: `user/templates/emails/password_reset.html`
- **Welcome Email**: `user/templates/emails/welcome.html`
- **Password Change Confirmation**: `user/templates/emails/password_change_confirmation.html`

Each template has both HTML and plain text versions.

## Email Functions

The following email functions are available in `user/email_utils.py`:

- `send_password_reset_email(user, reset_token)`
- `send_welcome_email(user)`
- `send_password_change_confirmation(user)`
- `send_email_verification(user, verification_token)`

## Testing Email Functionality

1. Set up your email configuration in `.env`
2. Run the Django development server
3. Test the forgot password endpoint:
   ```bash
   curl -X POST http://localhost:8000/api/user/forgot-password/ \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com"}'
   ```

## Security Notes

- Never commit your `.env` file to version control
- Use strong, unique passwords for email accounts
- Consider using environment-specific email backends
- The forgot password endpoint doesn't reveal whether an email exists for security

## Troubleshooting

### Common Issues

1. **Authentication Error**: Check your email credentials and app password
2. **Connection Error**: Verify SMTP settings and network connectivity
3. **Template Not Found**: Ensure email templates are in the correct directory
4. **Frontend URL**: Make sure `FRONTEND_URL` matches your frontend application URL

### Debug Mode

To debug email issues, check the Django console output when using the console backend, or check your email service provider's logs for SMTP issues.

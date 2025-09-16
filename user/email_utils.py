"""
Email utility functions for user authentication and notifications
"""
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


def send_password_reset_email(user, reset_token):
    """
    Send password reset email to user
    
    Args:
        user: User instance
        reset_token: PasswordResetToken instance
    """
    try:
        # Create reset URL (you'll need to adjust this based on your frontend URL)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token.token}"
        
        # Email subject
        subject = 'Password Reset Request - LegacyVerse'
        
        # Email context
        context = {
            'user': user,
            'reset_url': reset_url,
            'expires_in_hours': 1,  # Token expires in 1 hour
            'site_name': 'LegacyVerse',
            'support_email': settings.DEFAULT_FROM_EMAIL,
        }
        
        # Render HTML email template
        html_message = render_to_string('emails/password_reset.html', context)
        
        # Render plain text version
        plain_message = render_to_string('emails/password_reset.txt', context)
        
        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Password reset email sent to {user.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send password reset email to {user.email}: {str(e)}")
        return False


def send_welcome_email(user):
    """
    Send welcome email to newly registered user
    
    Args:
        user: User instance
    """
    try:
        subject = 'Welcome to LegacyVerse!'
        
        context = {
            'user': user,
            'site_name': 'LegacyVerse',
            'support_email': settings.DEFAULT_FROM_EMAIL,
        }
        
        html_message = render_to_string('emails/welcome.html', context)
        plain_message = render_to_string('emails/welcome.txt', context)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Welcome email sent to {user.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user.email}: {str(e)}")
        return False


def send_email_verification(user, verification_token):
    """
    Send email verification to user
    
    Args:
        user: User instance
        verification_token: Email verification token
    """
    try:
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        
        subject = 'Verify Your Email - LegacyVerse'
        
        context = {
            'user': user,
            'verification_url': verification_url,
            'site_name': 'LegacyVerse',
            'support_email': settings.DEFAULT_FROM_EMAIL,
        }
        
        html_message = render_to_string('emails/email_verification.html', context)
        plain_message = render_to_string('emails/email_verification.txt', context)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Email verification sent to {user.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email verification to {user.email}: {str(e)}")
        return False


def send_password_change_confirmation(user):
    """
    Send password change confirmation email
    
    Args:
        user: User instance
    """
    try:
        subject = 'Password Changed - LegacyVerse'
        
        context = {
            'user': user,
            'site_name': 'LegacyVerse',
            'support_email': settings.DEFAULT_FROM_EMAIL,
            'change_time': timezone.now(),
        }
        
        html_message = render_to_string('emails/password_change_confirmation.html', context)
        plain_message = render_to_string('emails/password_change_confirmation.txt', context)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Password change confirmation sent to {user.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send password change confirmation to {user.email}: {str(e)}")
        return False

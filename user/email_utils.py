"""
Email utility functions for user authentication and notifications
"""

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
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
        subject = "Password Reset Request - LegacyVerse"

        # Email context
        context = {
            "user": user,
            "reset_url": reset_url,
            "expires_in_hours": 1,  # Token expires in 1 hour
            "site_name": "LegacyVerse",
            "support_email": settings.DEFAULT_FROM_EMAIL,
        }

        # Render HTML email template
        html_message = render_to_string("emails/password_reset.html", context)

        # Render plain text version
        plain_message = render_to_string("emails/password_reset.txt", context)

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
        subject = "Welcome to LegacyVerse!"

        context = {
            "user": user,
            "site_name": "LegacyVerse",
            "support_email": settings.DEFAULT_FROM_EMAIL,
        }

        html_message = render_to_string("emails/welcome.html", context)
        plain_message = render_to_string("emails/welcome.txt", context)

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
        verification_url = (
            f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        )

        subject = "Verify Your Email - LegacyVerse"

        context = {
            "user": user,
            "verification_url": verification_url,
            "site_name": "LegacyVerse",
            "support_email": settings.DEFAULT_FROM_EMAIL,
        }

        html_message = render_to_string("emails/email_verification.html", context)
        plain_message = render_to_string("emails/email_verification.txt", context)

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
        subject = "Password Changed - LegacyVerse"

        context = {
            "user": user,
            "site_name": "LegacyVerse",
            "support_email": settings.DEFAULT_FROM_EMAIL,
            "change_time": timezone.now(),
        }

        html_message = render_to_string(
            "emails/password_change_confirmation.html", context
        )
        plain_message = render_to_string(
            "emails/password_change_confirmation.txt", context
        )

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
        logger.error(
            f"Failed to send password change confirmation to {user.email}: {str(e)}"
        )
        return False


def send_family_invitation_email(sender, receiver_email, receiver_name, relationship_type, is_new_user):
    """
    Send family invitation/notification email

    Args:
        sender: User instance who sent the request
        receiver_email: String email address of the receiver
        receiver_name: String name of the receiver
        relationship_type: String representation of relationship (e.g. 'Father')
        is_new_user: Boolean indicating if they need to register (True) or just accept request (False)
    """
    try:
        if is_new_user:
            subject = f"{sender.fullname} invited you to join their Family Tree on LegacyVerse"
            action_url = f"{settings.FRONTEND_URL}/?action=register&email={receiver_email}"
        else:
            subject = f"New Family Relationship Request from {sender.fullname}"
            action_url = f"{settings.FRONTEND_URL}/family/requests"

        context = {
            "sender": sender,
            "receiver_name": receiver_name,
            "relationship_type": relationship_type,
            "is_new_user": is_new_user,
            "action_url": action_url,
            "site_name": "LegacyVerse",
            "support_email": settings.DEFAULT_FROM_EMAIL,
        }

        html_message = render_to_string("emails/family_invitation.html", context)
        plain_message = render_to_string("emails/family_invitation.txt", context)

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[receiver_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Family invitation email sent to {receiver_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send family invitation email to {receiver_email}: {str(e)}")
        return False

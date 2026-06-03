from django.core.mail.backends.base import BaseEmailBackend
import resend
from django.conf import settings

class ResendEmailBackend(BaseEmailBackend):
    """
    A Django email backend that sends email using the Resend API SDK.
    """
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        resend.api_key = getattr(settings, 'RESEND_API_KEY', '')

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        
        num_sent = 0
        for message in email_messages:
            try:
                # Ensure the api key is fresh
                if not resend.api_key:
                    resend.api_key = getattr(settings, 'RESEND_API_KEY', '')
                
                # Build recipients list
                to_emails = list(message.to)
                
                # Retrieve html content if it exists
                html_content = None
                text_content = message.body
                
                if hasattr(message, 'alternatives') and message.alternatives:
                    for alt in message.alternatives:
                        if alt[1] == 'text/html':
                            html_content = alt[0]
                            break
                
                if not html_content and message.content_type == 'text/html':
                    html_content = message.body
                
                params = {
                    "from": message.from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'onboarding@resend.dev'),
                    "to": to_emails,
                    "subject": message.subject,
                }
                
                if html_content:
                    params["html"] = html_content
                if text_content:
                    params["text"] = text_content
                
                # Send email via Resend SDK
                resend.Emails.send(params)
                num_sent += 1
            except Exception as e:
                if not self.fail_silently:
                    raise e
        return num_sent

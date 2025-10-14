from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, Profile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create a profile with default sections when a user is created
    """
    if created:
        profile = Profile.objects.create(user=instance)
        # Create default sections for new users
        profile.create_default_sections()


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Automatically save the profile when the user is saved
    """
    if hasattr(instance, 'profile'):
        instance.profile.save()

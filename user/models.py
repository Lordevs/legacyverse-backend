from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
import uuid
import re


class UserManager(BaseUserManager):
    """
    Custom user manager for email-based authentication
    """
    def create_user(self, email, password=None, **extra_fields):
        """
        Create and return a regular user with the given email and password.
        """
        if not email:
            raise ValueError('The Email field must be set')
        
        email = self.normalize_email(email)
        
        # Generate username if not provided
        if 'username' not in extra_fields or not extra_fields['username']:
            extra_fields['username'] = self._generate_username(extra_fields.get('fullname', ''))
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and return a superuser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)
    
    def _generate_username(self, fullname):
        """
        Generate username from fullname
        """
        if not fullname:
            return f"user{uuid.uuid4().hex[:8]}"
        
        # Clean the fullname
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', str(fullname).lower())
        
        # Take first 8 characters
        base_username = clean_name[:8] if clean_name else "user"
        
        # Add random numbers if username exists
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
            
        return username


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    fullname = models.CharField(max_length=255)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Override username to make it non-editable and auto-generated
    username = models.CharField(max_length=150, unique=True, editable=False)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['fullname']
    
    def save(self, *args, **kwargs):
        if not self.username:
            self.username = UserManager()._generate_username(self.fullname)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.email


class Profile(models.Model):
    """
    User Profile model with additional information
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    image = models.ImageField(upload_to='profile_images/', null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    education = models.TextField(max_length=500, blank=True)
    hobbies = models.TextField(max_length=500, blank=True)
    early_childhood = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.fullname}'s Profile"
    
    @property
    def username(self):
        """Non-editable username from user model"""
        return self.user.username


class PasswordResetToken(models.Model):
    """
    Model to store password reset tokens
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at
    
    def __str__(self):
        return f"Password reset token for {self.user.email}"

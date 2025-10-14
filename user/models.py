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
    User Profile model with dynamic sections
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    image = models.ImageField(upload_to='profile_images/', null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    joined_date = models.DateField(null=True, blank=True, help_text="User-provided joined date")
    
    # Dynamic sections as JSON array - super simple!
    sections = models.JSONField(default=list, blank=True, help_text="Array of profile sections")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.fullname}'s Profile"
    
    @property
    def username(self):
        """Non-editable username from user model"""
        return self.user.username
    
    def add_section(self, title, content):
        """Helper method to add a new section"""
        if not self.sections:
            self.sections = []
        
        new_section = {
            'id': str(uuid.uuid4()),
            'title': title,
            'content': content,
            'images': [],
            'created_at': timezone.now().isoformat(),
            'updated_at': timezone.now().isoformat()
        }
        self.sections.append(new_section)
        self.save()
        return new_section
    
    def get_section_by_id(self, section_id):
        """Get a specific section by ID"""
        for section in self.sections:
            if section.get('id') == section_id:
                return section
        return None
    
    def update_section(self, section_id, **kwargs):
        """Update a specific section"""
        for i, section in enumerate(self.sections):
            if section.get('id') == section_id:
                self.sections[i].update(kwargs)
                self.sections[i]['updated_at'] = timezone.now().isoformat()
                self.save()
                return self.sections[i]
        return None
    
    def delete_section(self, section_id):
        """Delete a section"""
        self.sections = [s for s in self.sections if s.get('id') != section_id]
        self.save()
    
    def reorder_sections(self, new_order):
        """Reorder sections - new_order is array of section IDs in desired order"""
        # Create a mapping of section_id to new index
        order_map = {section_id: i for i, section_id in enumerate(new_order)}
        
        # Sort sections based on the new order
        self.sections.sort(key=lambda x: order_map.get(x.get('id'), 999))
        self.save()
    
    def create_default_sections(self):
        """Create default sections for new users"""
        default_sections = [
            {
                'title': 'Early Childhood',
                'content': 'Share your early childhood memories, experiences, and stories that shaped who you are today.'
            },
            {
                'title': 'Family',
                'content': 'Tell us about your family - parents, siblings, relatives, and the special moments you\'ve shared together.'
            },
            {
                'title': 'Education',
                'content': 'Describe your educational journey - schools, teachers, subjects you loved, and how education shaped your life.'
            },
            {
                'title': 'Society & Community',
                'content': 'Share your involvement in community activities, volunteer work, social causes, and how you\'ve contributed to society.'
            },
            {
                'title': 'Professional Experience',
                'content': 'Document your career journey, achievements, challenges overcome, and lessons learned in your professional life.'
            },
            {
                'title': 'Story Telling',
                'content': 'Share your personal stories, anecdotes, life lessons, and experiences that others might find inspiring or valuable.'
            }
        ]
        
        self.sections = []
        for i, section_data in enumerate(default_sections):
            section = {
                'id': str(uuid.uuid4()),
                'title': section_data['title'],
                'content': section_data['content'],
                'images': [],
                'created_at': timezone.now().isoformat(),
                'updated_at': timezone.now().isoformat()
            }
            self.sections.append(section)
        
        self.save()
        return self.sections
    
    def reset_to_default_sections(self):
        """Reset sections to default for existing users"""
        return self.create_default_sections()


class SectionImage(models.Model):
    """
    Images for profile sections - stored separately for better management
    """
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='section_images')
    section_id = models.CharField(max_length=100, help_text="ID of the section this image belongs to")
    image = models.ImageField(upload_to='section_images/')
    caption = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['profile', 'section_id']),
        ]
    
    def __str__(self):
        return f"Image for section {self.section_id}"




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

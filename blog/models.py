from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid

User = get_user_model()


class Blog(models.Model):
    """
    Blog model with title, content, and various modes
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('public', 'Public'),
    ]
    
    CONTENT_SOURCE_CHOICES = [
        ('user_written', 'User Written'),
        ('ai_generated', 'AI Generated'),
        ('ai_rewritten', 'AI Rewritten'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blogs')
    title = models.CharField(max_length=200)
    content = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    content_source = models.CharField(max_length=20, choices=CONTENT_SOURCE_CHOICES, default='user_written')
    ai_prompt = models.TextField(blank=True, null=True, help_text="Prompt used for AI generation/rewriting")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # SEO and metadata
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    excerpt = models.TextField(blank=True, help_text="Brief description of the blog")
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['author', '-created_at']),
            models.Index(fields=['slug']),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_slug()
        if self.status == 'public' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)
    
    def _generate_slug(self):
        """Generate a unique slug from the title"""
        from django.utils.text import slugify
        base_slug = slugify(self.title)
        slug = base_slug
        counter = 1
        while Blog.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug
    
    
    @property
    def is_published(self):
        """Check if the blog is published"""
        return self.status == 'public'


class Comment(models.Model):
    """
    Comment model for blog posts
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blog_comments')
    content = models.TextField()
    parent_comment = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Moderation
    is_approved = models.BooleanField(default=True)
    is_edited = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['blog', '-created_at']),
            models.Index(fields=['author', '-created_at']),
        ]
    
    def __str__(self):
        return f"Comment by {self.author.fullname} on {self.blog.title}"
    
    @property
    def is_reply(self):
        """Check if this comment is a reply to another comment"""
        return self.parent_comment is not None


class Like(models.Model):
    """
    Like model for blog posts
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blog_likes')
    is_liked = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['blog', 'user']
        indexes = [
            models.Index(fields=['blog', 'is_liked']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        status = "liked" if self.is_liked else "unliked"
        return f"{self.user.fullname} {status} {self.blog.title}"


class SavedBlog(models.Model):
    """
    Model for users to save blogs for later reading
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, related_name='saved_by_users')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_blogs')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['blog', 'user']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.fullname} saved {self.blog.title}"


class BlogView(models.Model):
    """
    Model to track blog views for analytics
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, related_name='views')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='blog_views')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['blog', '-created_at']),
        ]
    
    def __str__(self):
        viewer = self.user.fullname if self.user else self.ip_address
        return f"{viewer} viewed {self.blog.title}"

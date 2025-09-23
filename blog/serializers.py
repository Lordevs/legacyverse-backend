from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Blog, Comment, Like, SavedBlog, BlogView

User = get_user_model()



class UserSerializer(serializers.ModelSerializer):
    """Serializer for user information in blog contexts, with profile image"""
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'fullname', 'email', 'username', 'profile_image']
        read_only_fields = ['id', 'username']

    def get_profile_image(self, obj):
        # Assumes User has a related Profile with an image field
        profile = getattr(obj, 'profile', None)
        if profile and profile.image:
            request = self.context.get('request')
            image_url = profile.image.url
            if request is not None:
                return request.build_absolute_uri(image_url)
            return image_url
        return None


class CommentSerializer(serializers.ModelSerializer):
    """Serializer for blog comments"""
    author = UserSerializer(read_only=True)
    replies_count = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id', 'content', 'author', 'parent_comment',
            'created_at', 'updated_at', 'is_approved',
            'is_edited', 'replies_count', 'replies'
        ]
        read_only_fields = ['id', 'author', 'created_at', 'updated_at']

    def get_replies_count(self, obj):
        return obj.replies.count()

    def get_replies(self, obj):
        # Only direct replies, not recursive
        replies_qs = obj.replies.all().select_related('author')
        return CommentSerializer(replies_qs, many=True, context=self.context).data


class CommentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating comments"""
    class Meta:
        model = Comment
        fields = ['content', 'parent_comment']
    
    def validate_parent_comment(self, value):
        if value:
            # Check if parent comment belongs to the same blog
            blog_id = self.context.get('blog_id')
            if value.blog_id != blog_id:
                raise serializers.ValidationError("Parent comment must belong to the same blog")
        return value


class LikeSerializer(serializers.ModelSerializer):
    """Serializer for blog likes"""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Like
        fields = ['id', 'user', 'is_liked', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class BlogSerializer(serializers.ModelSerializer):
    """Serializer for blog posts"""
    author = UserSerializer(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    likes_count = serializers.IntegerField(read_only=True)
    views_count = serializers.IntegerField(read_only=True)
    is_liked_by_user = serializers.SerializerMethodField()
    is_saved_by_user = serializers.SerializerMethodField()
    comments = CommentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Blog
        fields = [
            'id', 'title', 'content', 'author', 'status', 'content_source',
            'ai_prompt', 'created_at', 'updated_at', 'published_at', 'slug',
            'excerpt', 'tags', 'comments_count', 'likes_count', 'views_count',
            'is_liked_by_user', 'is_saved_by_user', 'comments'
        ]
        read_only_fields = [
            'id', 'author', 'created_at', 'updated_at', 'published_at', 
            'slug', 'comments_count', 'likes_count', 'views_count'
        ]
    
    def get_is_liked_by_user(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            like = obj.likes.filter(user=request.user, is_liked=True).first()
            return like is not None
        return False
    
    def get_is_saved_by_user(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.saved_by_users.filter(user=request.user).exists()
        return False


class BlogCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating blog posts"""
    class Meta:
        model = Blog
        fields = [
            'id', 'title', 'content', 'status', 'content_source', 'ai_prompt',
            'excerpt', 'tags'
        ]
    
    def validate_title(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Title must be at least 3 characters long")
        return value.strip()
    
    def validate_content(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Content must be at least 10 characters long")
        return value.strip()
    
    def validate_tags(self, value):
        if value:
            # Clean and validate tags
            tags = [tag.strip() for tag in value.split(',') if tag.strip()]
            if len(tags) > 10:
                raise serializers.ValidationError("Maximum 10 tags allowed")
            return ','.join(tags)
        return value


class BlogUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating blog posts"""
    class Meta:
        model = Blog
        fields = [
            'title', 'content', 'status', 'excerpt', 'tags'
        ]
    
    def validate_title(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Title must be at least 3 characters long")
        return value.strip()
    
    def validate_content(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Content must be at least 10 characters long")
        return value.strip()
    
    def validate_tags(self, value):
        if value:
            # Clean and validate tags
            tags = [tag.strip() for tag in value.split(',') if tag.strip()]
            if len(tags) > 10:
                raise serializers.ValidationError("Maximum 10 tags allowed")
            return ','.join(tags)
        return value


class SavedBlogSerializer(serializers.ModelSerializer):
    """Serializer for saved blogs"""
    blog = BlogSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = SavedBlog
        fields = ['id', 'blog', 'user', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class BlogViewSerializer(serializers.ModelSerializer):
    """Serializer for blog views (for analytics)"""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = BlogView
        fields = ['id', 'blog', 'user', 'ip_address', 'created_at']
        read_only_fields = ['id', 'created_at']



class BlogListSerializer(serializers.ModelSerializer):
    """Simplified serializer for blog lists, with user like/save status"""
    author = UserSerializer(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    likes_count = serializers.IntegerField(read_only=True)
    views_count = serializers.IntegerField(read_only=True)
    is_liked_by_user = serializers.SerializerMethodField()
    is_saved_by_user = serializers.SerializerMethodField()

    class Meta:
        model = Blog
        fields = [
            'id', 'title', 'excerpt', 'author', 'status', 'content_source',
            'created_at', 'updated_at', 'published_at', 'slug', 'tags',
            'comments_count', 'likes_count', 'views_count',
            'is_liked_by_user', 'is_saved_by_user'
        ]

    def get_is_liked_by_user(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            like = obj.likes.filter(user=request.user, is_liked=True).first()
            return like is not None
        return False

    def get_is_saved_by_user(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.saved_by_users.filter(user=request.user).exists()
        return False


class AIBlogGenerationSerializer(serializers.Serializer):
    """Serializer for AI blog generation requests"""
    prompt = serializers.CharField(max_length=1000, min_length=10)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    content_source = serializers.ChoiceField(
        choices=[('ai_generated', 'AI Generated'), ('ai_rewritten', 'AI Rewritten')],
        default='ai_generated'
    )
    
    def validate_prompt(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Prompt must be at least 10 characters long")
        return value.strip()


class AITitleGenerationSerializer(serializers.Serializer):
    """Serializer for AI title generation requests"""
    prompt = serializers.CharField(max_length=1000, min_length=5)
    content = serializers.CharField(max_length=10000, required=False, allow_blank=True)
    tone = serializers.ChoiceField(
        choices=[
            ('professional', 'Professional'),
            ('casual', 'Casual'),
            ('creative', 'Creative'),
            ('informative', 'Informative'),
            ('engaging', 'Engaging')
        ],
        default='professional',
        required=False
    )
    
    def validate_prompt(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Prompt must be at least 5 characters long")
        return value.strip()


class AIContentGenerationSerializer(serializers.Serializer):
    """Serializer for AI content generation requests"""
    prompt = serializers.CharField(max_length=1000, min_length=10)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    tone = serializers.ChoiceField(
        choices=[
            ('professional', 'Professional'),
            ('casual', 'Casual'),
            ('creative', 'Creative'),
            ('informative', 'Informative'),
            ('engaging', 'Engaging')
        ],
        default='professional',
        required=False
    )
    length = serializers.ChoiceField(
        choices=[
            ('short', 'Short (300-500 words)'),
            ('medium', 'Medium (500-1000 words)'),
            ('long', 'Long (1000+ words)')
        ],
        default='medium',
        required=False
    )
    
    def validate_prompt(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Prompt must be at least 10 characters long")
        return value.strip()


class AIContentRewriteSerializer(serializers.Serializer):
    """Serializer for AI content rewriting requests"""
    content = serializers.CharField(max_length=10000, min_length=20)
    instruction = serializers.CharField(max_length=500, required=False, allow_blank=True)
    tone = serializers.ChoiceField(
        choices=[
            ('professional', 'Professional'),
            ('casual', 'Casual'),
            ('creative', 'Creative'),
            ('informative', 'Informative'),
            ('engaging', 'Engaging')
        ],
        default='professional',
        required=False
    )
    style = serializers.ChoiceField(
        choices=[
            ('improve_clarity', 'Improve Clarity'),
            ('make_engaging', 'Make More Engaging'),
            ('simplify', 'Simplify Language'),
            ('professional', 'Make More Professional'),
            ('casual', 'Make More Casual')
        ],
        default='improve_clarity',
        required=False
    )
    
    def validate_content(self, value):
        if len(value.strip()) < 20:
            raise serializers.ValidationError("Content must be at least 20 characters long")
        return value.strip()
    

# Blog stats serializer
class BlogStatsSerializer(serializers.Serializer):
    total_blogs = serializers.IntegerField()
    status_counts = serializers.DictField(child=serializers.IntegerField())
    views_per_blog = serializers.DictField(child=serializers.IntegerField())
    total_views = serializers.IntegerField()
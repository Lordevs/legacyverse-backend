from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Case, When, IntegerField, Value
from django.utils import timezone
from django.http import Http404
from django.conf import settings
from openai import OpenAI
import logging

from .models import Blog, Comment, Like, SavedBlog, BlogView
from .serializers import (
    BlogSerializer, BlogCreateSerializer, BlogUpdateSerializer, 
    BlogListSerializer, CommentSerializer, CommentCreateSerializer,
    LikeSerializer, SavedBlogSerializer, BlogViewSerializer,
    AIBlogGenerationSerializer, AITitleGenerationSerializer,
    AIContentGenerationSerializer, AIContentRewriteSerializer
)

logger = logging.getLogger(__name__)

client = OpenAI(api_key=settings.OPENAI_API_KEY)


class BlogViewSet(ModelViewSet):
    """
    ViewSet for blog CRUD operations
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return BlogCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return BlogUpdateSerializer
        elif self.action == 'list':
            return BlogListSerializer
        return BlogSerializer
    
    def get_queryset(self):
        queryset = Blog.objects.select_related('author').prefetch_related(
            'likes', 'comments', 'saved_by_users'
        ).annotate(
            likes_count=Count('likes', filter=Q(likes__is_liked=True), distinct=True),
            comments_count=Count('comments', distinct=True),
            views_count=Count('views', distinct=True)
        )

        # Filter by status for public access
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(status='public')
        elif self.action == 'list':
            # For authenticated users, show their own drafts and all public blogs
            queryset = queryset.filter(
                Q(status='public') | Q(author=self.request.user)
            )

        # Filter by author if specified
        author_id = self.request.query_params.get('author')
        if author_id:
            queryset = queryset.filter(author_id=author_id)

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by tags
        tags = self.request.query_params.get('tags')
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',')]
            for tag in tag_list:
                queryset = queryset.filter(tags__icontains=tag)

        # Search functionality
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(content__icontains=search) |
                Q(excerpt__icontains=search) |
                Q(tags__icontains=search) |
                Q(author__fullname__icontains=search) |
                Q(author__username__icontains=search)
            )

        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
    
    def perform_update(self, serializer):
        # Only allow authors to update their own blogs
        if serializer.instance.author != self.request.user:
            raise PermissionError("You can only update your own blogs")
        serializer.save()
    
    def perform_destroy(self, instance):
        # Only allow authors to delete their own blogs
        if instance.author != self.request.user:
            raise PermissionError("You can only delete your own blogs")
        instance.delete()
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def search(self, request):
        """Partial search across title and content with simple relevance ranking.
        Ranking priority: exact title > partial title > partial content.
        Optional query params:
        - q: search string (required)
        - limit: max results (default 20)
        """
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({'detail': 'Missing q parameter'}, status=status.HTTP_400_BAD_REQUEST)

        limit = request.query_params.get('limit')
        try:
            limit = int(limit) if limit else 20
        except ValueError:
            limit = 20

        base_qs = Blog.objects.select_related('author').annotate(
            likes_count=Count('likes', filter=Q(likes__is_liked=True), distinct=True),
            comments_count=Count('comments', distinct=True),
            views_count=Count('views', distinct=True)
        )

        # Public-only for anonymous users; authors can see their drafts via list(),
        # but search endpoint exposes only public for simplicity/security.
        base_qs = base_qs.filter(status='public')

        # Basic matching filters
        filters = Q(title__icontains=query) | Q(content__icontains=query)

        # Relevance scoring using Case/When
        ranked_qs = base_qs.filter(filters).annotate(
            relevance=Case(
                When(title__iexact=query, then=Value(100)),
                When(title__istartswith=query, then=Value(90)),
                When(title__icontains=query, then=Value(80)),
                When(content__icontains=query, then=Value(50)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).order_by('-relevance', '-created_at')

        results = ranked_qs[:limit]

        # Use list serializer for compact results
        serializer = BlogListSerializer(results, many=True, context={'request': request})
        return Response({
            'count': ranked_qs.count(),
            'results': serializer.data
        })
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, pk=None):
        """Toggle like for a blog"""
        blog = self.get_object()
        like, created = Like.objects.get_or_create(
            blog=blog, 
            user=request.user,
            defaults={'is_liked': True}
        )
        
        if not created:
            like.is_liked = not like.is_liked
            like.save()
        
        return Response({
            'is_liked': like.is_liked,
            'likes_count': blog.likes.filter(is_liked=True).count()
        })
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def save(self, request, pk=None):
        """Save or unsave a blog"""
        blog = self.get_object()
        saved_blog, created = SavedBlog.objects.get_or_create(
            blog=blog,
            user=request.user
        )
        
        if not created:
            saved_blog.delete()
            is_saved = False
        else:
            is_saved = True
        
        return Response({'is_saved': is_saved})
    
    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def track_view(self, request, pk=None):
        """Track blog view for analytics"""
        blog = self.get_object()
        
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        
        # Create view record (only if not already viewed recently)
        view, created = BlogView.objects.get_or_create(
            blog=blog,
            user=request.user if request.user.is_authenticated else None,
            defaults={'ip_address': ip_address}
        )
        
        return Response({'viewed': created})


class CommentViewSet(ModelViewSet):
    """
    ViewSet for comment CRUD operations
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CommentCreateSerializer
        return CommentSerializer
    
    def get_queryset(self):
        blog_id = self.kwargs.get('blog_pk')
        if blog_id:
            # If 'pk' is present, retrieve the specific comment (parent or child)
            comment_pk = self.kwargs.get('pk')
            if comment_pk:
                return Comment.objects.filter(blog_id=blog_id, pk=comment_pk).select_related('author').prefetch_related('replies__author')
            # Otherwise, list all comments for the blog (top-level only for list action)
            if self.action == 'list':
                return Comment.objects.filter(
                    blog_id=blog_id,
                    parent_comment__isnull=True
                ).select_related('author').prefetch_related('replies__author').order_by('-created_at')
            # For retrieve/update/destroy, allow any comment (parent or child)
            return Comment.objects.filter(blog_id=blog_id).select_related('author').prefetch_related('replies__author')
        return Comment.objects.none()
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['blog_id'] = self.kwargs.get('blog_pk')
        return context
    
    def perform_create(self, serializer):
        blog_id = self.kwargs.get('blog_pk')
        blog = get_object_or_404(Blog, id=blog_id)
        serializer.save(blog=blog, author=self.request.user)
    
    def perform_update(self, serializer):
        # Only allow authors to update their own comments
        if serializer.instance.author != self.request.user:
            raise PermissionError("You can only update your own comments")
        serializer.save(is_edited=True)
    
    def perform_destroy(self, instance):
        # Only allow authors to delete their own comments
        if instance.author != self.request.user:
            raise PermissionError("You can only delete your own comments")
        instance.delete()


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_ai_blog(request):
    """
    Generate or rewrite blog content using OpenAI
    """
    serializer = AIBlogGenerationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        if not client:
            return Response(
                {'error': 'OpenAI API key not configured'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        prompt = serializer.validated_data['prompt']
        content_source = serializer.validated_data['content_source']
        title = serializer.validated_data.get('title', '')
        
        # Create different prompts based on content source
        if content_source == 'ai_generated':
            system_prompt = """You are a professional blog writer. Create an engaging, well-structured blog post based on the user's prompt. 
            The blog should be informative, well-organized with clear headings, and written in a professional yet accessible tone."""
            user_prompt = f"Write a blog post about: {prompt}"
        else:  # ai_rewritten
            system_prompt = """You are a professional blog editor. Rewrite the provided content to make it more engaging, clear, and well-structured. 
            Improve the flow, clarity, and overall quality while maintaining the original meaning and key points."""
            user_prompt = f"Rewrite this content to make it better: {prompt}"
        
        # Generate content using OpenAI
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )
        
        generated_content = response.choices[0].message.content.strip() if response.choices[0].message.content else ''
        
        # Extract title if not provided
        if not title and content_source == 'ai_generated':
            # Try to extract title from generated content
            lines = generated_content.split('\n') if generated_content else []
            for line in lines:
                if line.strip() and not line.startswith('#') and len(line.strip()) < 100:
                    title = line.strip()
                    break
        
        return Response({
            'title': title,
            'content': generated_content,
            'content_source': content_source,
            'ai_prompt': prompt
        })
        
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        return Response(
            {'error': 'Failed to generate content. Please try again.'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_ai_title(request):
    """
    Generate blog title using OpenAI
    """
    serializer = AITitleGenerationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        if not client:
            return Response(
                {'error': 'OpenAI API key not configured'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        prompt = serializer.validated_data['prompt']
        content = serializer.validated_data.get('content', '')
        tone = serializer.validated_data.get('tone', 'professional')
        
        # Create system prompt based on tone
        tone_instructions = {
            'professional': 'professional and authoritative',
            'casual': 'casual and friendly',
            'creative': 'creative and engaging',
            'informative': 'informative and educational',
            'engaging': 'engaging and compelling'
        }
        
        system_prompt = f"""You are a professional blog title generator. Create a {tone_instructions.get(tone, 'professional')} blog title based on the user's prompt. 
        The title should be:
        - Catchy and attention-grabbing
        - SEO-friendly
        - Between 40-60 characters
        - Clear and descriptive
        - Appropriate for the {tone} tone
        
        Return only the title, no additional text."""
        
        user_prompt = f"Generate a blog title for: {prompt}"
        if content:
            user_prompt += f"\n\nContent context: {content[:500]}..."
        
        # Generate title using OpenAI
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=100,
            temperature=0.8
        )
        
        generated_title = response.choices[0].message.content.strip() if response.choices[0].message.content else ''
        
        return Response({
            'title': generated_title,
            'tone': tone,
            'original_prompt': prompt
        })
        
    except Exception as e:
        logger.error(f"OpenAI API error for title generation: {str(e)}")
        return Response(
            {'error': 'Failed to generate title. Please try again.'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_ai_content(request):
    """
    Generate blog content using OpenAI
    """
    serializer = AIContentGenerationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        if not client:
            return Response(
                {'error': 'OpenAI API key not configured'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        prompt = serializer.validated_data['prompt']
        title = serializer.validated_data.get('title', '')
        tone = serializer.validated_data.get('tone', 'professional')
        length = serializer.validated_data.get('length', 'medium')
        
        # Create system prompt based on tone and length
        tone_instructions = {
            'professional': 'professional and authoritative',
            'casual': 'casual and friendly',
            'creative': 'creative and engaging',
            'informative': 'informative and educational',
            'engaging': 'engaging and compelling'
        }
        
        length_instructions = {
            'short': '300-500 words',
            'medium': '500-1000 words',
            'long': '1000+ words'
        }
        
        system_prompt = f"""You are a professional blog writer. Create an engaging, well-structured blog post based on the user's prompt. 
        The blog should be:
        - {tone_instructions.get(tone, 'professional')} in tone
        - Approximately {length_instructions.get(length, '500-1000 words')} in length
        - Well-organized with clear headings and subheadings
        - Informative and valuable to readers
        - Written in a {tone} style
        
        Structure the content with proper headings (use ## for main headings, ### for subheadings) and make it engaging and easy to read."""
        
        user_prompt = f"Write a blog post about: {prompt}"
        if title:
            user_prompt += f"\n\nTitle: {title}"
        
        # Adjust max_tokens based on length
        max_tokens_map = {
            'short': 1000,
            'medium': 2000,
            'long': 3000
        }
        
        # Generate content using OpenAI
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens_map.get(length, 2000),
            temperature=0.7
        )
        
        generated_content = response.choices[0].message.content.strip() if response.choices[0].message.content else ''
        
        return Response({
            'content': generated_content,
            'title': title,
            'tone': tone,
            'length': length,
            'original_prompt': prompt
        })
        
    except Exception as e:
        logger.error(f"OpenAI API error for content generation: {str(e)}")
        return Response(
            {'error': 'Failed to generate content. Please try again.'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def rewrite_ai_content(request):
    """
    Rewrite existing content using OpenAI
    """
    serializer = AIContentRewriteSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        if not client:
            return Response(
                {'error': 'OpenAI API key not configured'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        content = serializer.validated_data['content']
        instruction = serializer.validated_data.get('instruction', '')
        tone = serializer.validated_data.get('tone', 'professional')
        style = serializer.validated_data.get('style', 'improve_clarity')
        
        # Create system prompt based on style and tone
        tone_instructions = {
            'professional': 'professional and authoritative',
            'casual': 'casual and friendly',
            'creative': 'creative and engaging',
            'informative': 'informative and educational',
            'engaging': 'engaging and compelling'
        }
        
        style_instructions = {
            'improve_clarity': 'improve clarity and readability while maintaining the original meaning',
            'make_engaging': 'make it more engaging and compelling to read',
            'simplify': 'simplify the language and make it more accessible',
            'professional': 'make it more professional and formal',
            'casual': 'make it more casual and conversational'
        }
        
        system_prompt = f"""You are a professional content editor. Rewrite the provided content to {style_instructions.get(style, 'improve clarity')}. 
        The rewritten content should be:
        - {tone_instructions.get(tone, 'professional')} in tone
        - Well-structured and easy to read
        - Maintain the original meaning and key points
        - Improved in terms of {style}
        - Engaging and valuable to readers
        
        Preserve the original structure and formatting where appropriate, but improve the overall quality."""
        
        user_prompt = f"Rewrite this content:\n\n{content}"
        if instruction:
            user_prompt += f"\n\nAdditional instruction: {instruction}"
        
        # Generate rewritten content using OpenAI
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=3000,
            temperature=0.6
        )
        
        rewritten_content = response.choices[0].message.content.strip() if response.choices[0].message.content else ''
        
        return Response({
            'rewritten_content': rewritten_content,
            'original_content': content,
            'tone': tone,
            'style': style,
            'instruction': instruction
        })
        
    except Exception as e:
        logger.error(f"OpenAI API error for content rewriting: {str(e)}")
        return Response(
            {'error': 'Failed to rewrite content. Please try again.'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_saved_blogs(request):
    """
    Get all blogs saved by the authenticated user
    """
    saved_blogs = SavedBlog.objects.filter(user=request.user).select_related(
        'blog__author'
    ).order_by('-created_at')
    
    serializer = SavedBlogSerializer(saved_blogs, many=True, context={'request': request})
    return Response(serializer.data)



@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_blogs(request):
    """
    Get all blogs by the authenticated user
    """
    blogs = Blog.objects.filter(author=request.user).annotate(
        likes_count=Count('likes', filter=Q(likes__is_liked=True)),
        comments_count=Count('comments')
    ).order_by('-created_at')
    serializer = BlogSerializer(blogs, many=True, context={'request': request})
    return Response(serializer.data)


# Blog stats endpoint
from .serializers import BlogStatsSerializer

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_blog_stats(request):
    """
    Get blog stats for the authenticated user
    """
    blogs = Blog.objects.filter(author=request.user)
    total_blogs = blogs.count()
    # Status-wise count
    status_counts = blogs.values('status').annotate(count=Count('id'))
    status_dict = {item['status']: item['count'] for item in status_counts}
    # Views per blog
    views_per_blog = {}
    for blog in blogs:
        views_per_blog[str(blog.id)] = blog.views.count()
    # Total views
    total_views = sum(views_per_blog.values())
    data = {
        'total_blogs': total_blogs,
        'status_counts': status_dict,
        'views_per_blog': views_per_blog,
        'total_views': total_views
    }
    serializer = BlogStatsSerializer(data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def blog_detail_by_slug(request, slug):
    """
    Get blog detail by slug (for SEO-friendly URLs)
    """
    try:
        blog = Blog.objects.select_related('author').prefetch_related(
            'likes', 'comments__author', 'saved_by_users'
        ).annotate(
            likes_count=Count('likes', filter=Q(likes__is_liked=True)),
            comments_count=Count('comments')
        ).get(slug=slug)
    except Blog.DoesNotExist:
        raise Http404("Blog not found")

    # Check if user can view this blog
    if blog.status != 'public' and (
        not request.user.is_authenticated or 
        blog.author != request.user
    ):
        raise Http404("Blog not found")

    # Track view
    if request.user.is_authenticated:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        BlogView.objects.get_or_create(
            blog=blog,
            user=request.user,
            defaults={'ip_address': ip_address}
        )

    from .serializers import BlogDetailSerializer
    # Use BlogDetailSerializer to exclude comments and include views_count
    blog.views_count = blog.views.count()
    serializer = BlogDetailSerializer(blog, context={'request': request})
    return Response(serializer.data)

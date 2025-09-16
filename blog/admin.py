from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Blog, Comment, Like, SavedBlog, BlogView


@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'author', 'status', 'content_source', 'created_at', 
        'published_at', 'likes_count', 'comments_count', 'slug'
    ]
    list_filter = ['status', 'content_source', 'created_at', 'published_at']
    search_fields = ['title', 'content', 'author__fullname', 'author__email', 'tags']
    readonly_fields = ['id', 'slug', 'created_at', 'updated_at', 'published_at']
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'content', 'excerpt', 'tags')
        }),
        ('Author & Status', {
            'fields': ('author', 'status', 'published_at')
        }),
        ('Content Source', {
            'fields': ('content_source', 'ai_prompt')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def likes_count(self, obj):
        return obj.likes_count
    likes_count.short_description = 'Likes'
    
    def comments_count(self, obj):
        return obj.comments_count
    comments_count.short_description = 'Comments'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = [
        'content_preview', 'author', 'blog_title', 'parent_comment', 
        'is_approved', 'is_edited', 'created_at'
    ]
    list_filter = ['is_approved', 'is_edited', 'created_at']
    search_fields = ['content', 'author__fullname', 'author__email', 'blog__title']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = (
        ('Comment Content', {
            'fields': ('content', 'author', 'blog')
        }),
        ('Threading', {
            'fields': ('parent_comment',)
        }),
        ('Moderation', {
            'fields': ('is_approved', 'is_edited')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content Preview'
    
    def blog_title(self, obj):
        return obj.blog.title
    blog_title.short_description = 'Blog'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author', 'blog')


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ['user', 'blog_title', 'is_liked', 'created_at', 'updated_at']
    list_filter = ['is_liked', 'created_at']
    search_fields = ['user__fullname', 'user__email', 'blog__title']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    def blog_title(self, obj):
        return obj.blog.title
    blog_title.short_description = 'Blog'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'blog')


@admin.register(SavedBlog)
class SavedBlogAdmin(admin.ModelAdmin):
    list_display = ['user', 'blog_title', 'created_at']
    search_fields = ['user__fullname', 'user__email', 'blog__title']
    readonly_fields = ['id', 'created_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    def blog_title(self, obj):
        return obj.blog.title
    blog_title.short_description = 'Blog'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'blog')


@admin.register(BlogView)
class BlogViewAdmin(admin.ModelAdmin):
    list_display = ['blog_title', 'user', 'ip_address', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__fullname', 'user__email', 'blog__title', 'ip_address']
    readonly_fields = ['id', 'created_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    def blog_title(self, obj):
        return obj.blog.title
    blog_title.short_description = 'Blog'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'blog')

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'blog'

# Create a router for ViewSets
router = DefaultRouter()
router.register(r'blogs', views.BlogViewSet, basename='blog')

# URL patterns
urlpatterns = [
    # Include router URLs for ViewSets
    path('api/', include(router.urls)),
    
    # Comments nested under blogs
    path('api/blogs/<uuid:blog_pk>/comments/', views.CommentViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='blog-comments'),
    
    path('api/blogs/<uuid:blog_pk>/comments/<uuid:pk>/', views.CommentViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='blog-comment-detail'),
    
    # AI Blog Generation
    path('api/ai/generate-blog/', views.generate_ai_blog, name='generate-ai-blog'),
    path('api/ai/generate-title/', views.generate_ai_title, name='generate-ai-title'),
    path('api/ai/generate-content/', views.generate_ai_content, name='generate-ai-content'),
    path('api/ai/rewrite-content/', views.rewrite_ai_content, name='rewrite-ai-content'),
    
    # User-specific endpoints
    path('api/user/saved-blogs/', views.user_saved_blogs, name='user-saved-blogs'),
    path('api/user/blogs/', views.user_blogs, name='user-blogs'),
    
    # SEO-friendly blog URLs
    path('blog/<slug:slug>/', views.blog_detail_by_slug, name='blog-detail-slug'),
]

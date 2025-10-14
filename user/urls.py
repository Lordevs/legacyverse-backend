from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .google_auth import google_auth_view, google_oauth_url, google_oauth_callback

urlpatterns = [
    # Authentication URLs
    path('auth/register/', views.register_view, name='register'),
    path('auth/login/', views.CustomTokenObtainPairView.as_view(), name='login'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('auth/refresh/', views.refresh_token_view, name='refresh_token'),
    path('auth/forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('auth/reset-password/', views.reset_password_view, name='reset_password'),
    path('auth/change-password/', views.change_password_view, name='change_password'),
    path('auth/google/', google_auth_view, name='google_auth'),
    path('auth/google/url/', google_oauth_url, name='google_oauth_url'),
    path('auth/google/callback/', google_oauth_callback, name='google_oauth_callback'),
    
    # Profile URLs
    path('profile/', views.ProfileDetailView.as_view(), name='profile_detail'),
    path('profile/image/', views.update_profile_image, name='update_profile_image'),
    path('profile/image/delete/', views.delete_profile_image, name='delete_profile_image'),
    
    # Complete profile update (unified endpoint)
    path('profile/update-complete/', views.update_profile_complete, name='update_profile_complete'),
    
    # Profile sections management
    path('profile/sections/', views.profile_sections_view, name='profile_sections'),
    path('profile/sections/reorder/', views.reorder_sections, name='reorder_sections'),
    path('profile/sections/reset-default/', views.reset_sections_to_default, name='reset_sections_to_default'),
    path('profile/sections/<str:section_id>/', views.profile_section_detail, name='profile_section_detail'),
    
    # Section images
    path('profile/sections/<str:section_id>/images/', views.upload_section_images, name='upload_section_images'),
    path('profile/sections/images/<uuid:image_id>/', views.section_image_detail, name='section_image_detail'),
    
    
    # Username pattern should be last to avoid conflicts
    path('profile/<str:username>/', views.get_profile_by_username, name='profile_by_username'),

    # User details by username
    path('by-username/<str:username>/', views.get_user_by_username, name='get-user-by-username'),

]

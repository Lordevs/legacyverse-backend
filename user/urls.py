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
    
    # Profile URLs (works for both user and admin based on permissions)
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
    path('profile/sections/images/<int:image_id>/', views.section_image_detail, name='section_image_detail'),
    
    # Admin-specific endpoints (same functionality, different target user)
    path('admin/users/', views.admin_list_users, name='admin_list_users'),
    path('admin/users/create/', views.admin_create_user, name='admin_create_user'),
    path('admin/users/<uuid:user_id>/', views.admin_user_detail, name='admin_user_detail'),
    path('admin/users/<uuid:user_id>/profile/', views.admin_get_user_profile, name='admin_user_profile'),
    path('admin/users/<uuid:user_id>/profile/update/', views.admin_update_user_profile, name='admin_update_user_profile'),
    path('admin/users/<uuid:user_id>/profile/image/', views.admin_upload_user_profile_image, name='admin_upload_user_profile_image'),
    path('admin/users/<uuid:user_id>/profile/image/delete/', views.admin_delete_user_profile_image, name='admin_delete_user_profile_image'),
    path('admin/users/<uuid:user_id>/profile/sections/', views.admin_user_profile_sections, name='admin_user_profile_sections'),
    path('admin/users/<uuid:user_id>/profile/sections/reorder/', views.admin_reorder_user_sections, name='admin_reorder_user_sections'),
    path('admin/users/<uuid:user_id>/profile/sections/reset-default/', views.admin_reset_user_sections, name='admin_reset_user_sections'),
    path('admin/users/<uuid:user_id>/profile/sections/<str:section_id>/', views.admin_user_profile_section_detail, name='admin_user_profile_section_detail'),
    path('admin/users/<uuid:user_id>/profile/sections/<str:section_id>/images/', views.admin_upload_user_section_images, name='admin_upload_user_section_images'),
    path('admin/users/<uuid:user_id>/profile/sections/<str:section_id>/images/<int:image_id>/', views.admin_user_section_image_detail, name='admin_user_section_image_detail'),
    
    # Username pattern should be last to avoid conflicts
    path('profile/<str:username>/', views.get_profile_by_username, name='profile_by_username'),

    # User details by username
    path('by-username/<str:username>/', views.get_user_by_username, name='get-user-by-username'),
    
    # Public user profiles listing
    path('profiles/', views.list_user_profiles, name='list-user-profiles'),

]

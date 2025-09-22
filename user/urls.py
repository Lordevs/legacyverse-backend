from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Authentication URLs
    path('auth/register/', views.register_view, name='register'),
    path('auth/login/', views.CustomTokenObtainPairView.as_view(), name='login'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('auth/refresh/', views.refresh_token_view, name='refresh_token'),
    path('auth/forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('auth/reset-password/', views.reset_password_view, name='reset_password'),
    path('auth/change-password/', views.change_password_view, name='change_password'),
    
    # Profile URLs
    path('profile/', views.ProfileDetailView.as_view(), name='profile_detail'),
    path('profile/image/', views.update_profile_image, name='update_profile_image'),
    path('profile/image/delete/', views.delete_profile_image, name='delete_profile_image'),
    
    # Childhood Images URLs (put before username pattern to avoid conflicts)
    path('profile/childhood-images/', views.childhood_images_view, name='childhood_images'),
    path('profile/childhood-images/<int:image_id>/', views.update_childhood_image, name='update_childhood_image'),
    path('profile/childhood-images/<int:image_id>/delete/', views.delete_childhood_image, name='delete_childhood_image'),
    path('profile/childhood-images/delete-all/', views.delete_all_childhood_images, name='delete_all_childhood_images'),
    
    # Username pattern should be last to avoid conflicts
    path('profile/<str:username>/', views.get_profile_by_username, name='profile_by_username'),
]

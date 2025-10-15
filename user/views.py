from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import login, logout
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db import models
from datetime import timedelta
import uuid

from .models import User, Profile, PasswordResetToken, SectionImage
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserSerializer,
    ProfileSerializer, ProfileImageSerializer, PasswordChangeSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer, SectionImageSerializer
)
from .email_utils import send_password_reset_email, send_welcome_email, send_password_change_confirmation


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom JWT token view for login - Enhanced with admin detection
    """
    def post(self, request, *args, **kwargs):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)
            
            # Enhanced user data with admin info for frontend routing
            user_data = UserSerializer(user).data
            user_data.update({
                'is_admin': user.is_staff or user.is_superuser,
                # 'is_staff': user.is_staff,
                # 'is_superuser': user.is_superuser,
                # 'permissions': {
                #     'can_manage_users': user.is_staff or user.is_superuser,
                #     'can_manage_profiles': user.is_staff or user.is_superuser,
                #     'can_view_admin': user.is_staff or user.is_superuser,
                # }
            })
            
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': user_data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_view(request):
    """
    User registration endpoint
    """
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        
        # Send welcome email
        send_welcome_email(user)
        
        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'User registered successfully',
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    """
    User logout endpoint
    """
    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return Response({'error': 'Refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
    except Exception as e:
        # Provide more details for debugging
        return Response({'error': f'Invalid refresh token: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def forgot_password_view(request):
    """
    Forgot password endpoint
    """
    serializer = ForgotPasswordSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
            
            # Invalidate any existing reset tokens for this user
            PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)
            
            # Create new password reset token
            reset_token = PasswordResetToken.objects.create(
                user=user,
                expires_at=timezone.now() + timedelta(hours=1)
            )
            
            # Send password reset email
            email_sent = send_password_reset_email(user, reset_token)
            
            if email_sent:
                return Response({
                    'message': 'Password reset instructions have been sent to your email address'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': 'Failed to send email. Please try again later.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except User.DoesNotExist:
            # For security, don't reveal if email exists or not
            return Response({
                'message': 'If an account with that email exists, password reset instructions have been sent.'
            }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def reset_password_view(request):
    """
    Reset password endpoint
    """
    serializer = ResetPasswordSerializer(data=request.data)
    if serializer.is_valid():
        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']
        
        try:
            reset_token = PasswordResetToken.objects.get(token=token)
            if reset_token.is_valid():
                user = reset_token.user
                user.set_password(new_password)
                user.save()
                reset_token.is_used = True
                reset_token.save()
                return Response({'message': 'Password reset successful'}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)
        except PasswordResetToken.DoesNotExist:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password_view(request):
    """
    Change password endpoint
    """
    serializer = PasswordChangeSerializer(data=request.data)
    if serializer.is_valid():
        old_password = serializer.validated_data['old_password']
        new_password = serializer.validated_data['new_password']
        
        if not request.user.check_password(old_password):
            return Response({'error': 'Old password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)
        
        request.user.set_password(new_password)
        request.user.save()
        
        # Send password change confirmation email
        send_password_change_confirmation(request.user)
        
        return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def refresh_token_view(request):
    """
    Refresh JWT token endpoint
    """
    try:
        refresh_token = request.data["refresh"]
        token = RefreshToken(refresh_token)
        # Rotate refresh token: create a new one
        new_refresh = str(token)
        new_access = str(token.access_token)
        return Response({
            'access': new_access,
            'refresh': new_refresh
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': 'Invalid refresh token'}, status=status.HTTP_400_BAD_REQUEST)


# Profile Views
class ProfileDetailView(generics.RetrieveUpdateAPIView):
    """
    Get and update user profile
    """
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        profile, created = Profile.objects.get_or_create(user=self.request.user)
        return profile


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def get_profile_by_username(request, username):
    """
    Get profile by username (public endpoint)
    """
    try:
        user = User.objects.get(username=username)
        profile, created = Profile.objects.get_or_create(user=user)
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_profile_image(request):
    """
    Update profile image
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    serializer = ProfileImageSerializer(profile, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_profile_image(request):
    """
    Delete profile image
    """
    try:
        profile = Profile.objects.get(user=request.user)
        if profile.image:
            profile.image.delete()
            profile.image = None
            profile.save()
            return Response({'message': 'Profile image deleted successfully'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'No profile image to delete'}, status=status.HTTP_400_BAD_REQUEST)
    except Profile.DoesNotExist:
        return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)


# Section Management Views


# Get user details by username
from .serializers import UserSerializer

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def get_user_by_username(request, username):
    """
    Get user details by username (public endpoint)
    """
    from .models import User
    try:
        user = User.objects.get(username=username)
        serializer = UserSerializer(user, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


# New unified profile update views
@api_view(['PUT', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def update_profile_complete(request):
    """
    Update complete profile - handles both JSON and file uploads
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    try:
        # Handle form data
        if request.content_type.startswith('multipart/form-data'):
            # Extract sections data from form
            sections_data = request.data.get('sections')
            if sections_data:
                if isinstance(sections_data, str):
                    import json
                    sections_data = json.loads(sections_data)
                
                # Update sections
                profile.sections = sections_data
                profile.save()
                
                # Handle images for each section
                for section in sections_data:
                    section_id = section.get('id')
                    if section_id:
                        # Get images for this section from form data
                        section_images = request.FILES.getlist(f'section_{section_id}_images')
                        section_captions = request.data.getlist(f'section_{section_id}_captions', [])
                        
                        # Delete existing images for this section
                        SectionImage.objects.filter(
                            profile=profile,
                            section_id=section_id
                        ).delete()
                        
                        # Upload new images
                        for i, image in enumerate(section_images):
                            caption = section_captions[i] if i < len(section_captions) else ''
                            SectionImage.objects.create(
                                profile=profile,
                                section_id=section_id,
                                image=image,
                                caption=caption
                            )
            
            # Update basic profile fields
            if 'bio' in request.data:
                profile.bio = request.data['bio']
            if 'location' in request.data:
                profile.location = request.data['location']
            if 'website' in request.data:
                profile.website = request.data['website']
            if 'joined_date' in request.data:
                profile.joined_date = request.data['joined_date']
            if 'image' in request.FILES:
                profile.image = request.FILES['image']
            
            profile.save()
            
        else:
            # Handle JSON data
            sections_data = request.data.get('sections', [])
            if sections_data:
                profile.sections = sections_data
                profile.save()
            
            # Update other fields
            if 'bio' in request.data:
                profile.bio = request.data['bio']
            if 'location' in request.data:
                profile.location = request.data['location']
            if 'website' in request.data:
                profile.website = request.data['website']
            if 'joined_date' in request.data:
                profile.joined_date = request.data['joined_date']
        
        # Return updated profile
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def profile_sections_view(request):
    """
    GET: Get all sections for authenticated user
    POST: Create new section
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == 'GET':
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response({
            'sections': serializer.data.get('sections', [])
        })
    
    elif request.method == 'POST':
        title = request.data.get('title')
        content = request.data.get('content')
        
        if not title or not content:
            return Response(
                {'error': 'Title and content are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        new_section = profile.add_section(title, content)
        return Response(new_section, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def profile_section_detail(request, section_id):
    """
    Manage individual profile sections
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    section = profile.get_section_by_id(section_id)
    
    if not section:
        return Response({'error': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        return Response(section)
    
    elif request.method in ['PUT', 'PATCH']:
        # Update section data
        update_data = {}
        if 'title' in request.data:
            update_data['title'] = request.data['title']
        if 'content' in request.data:
            update_data['content'] = request.data['content']
        
        updated_section = profile.update_section(section_id, **update_data)
        if updated_section:
            return Response(updated_section)
        return Response({'error': 'Failed to update section'}, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        profile.delete_section(section_id)
        return Response({'message': 'Section deleted successfully'}, status=status.HTTP_200_OK)


@api_view(['POST', 'PUT'])
@permission_classes([permissions.IsAuthenticated])
def reorder_sections(request):
    """
    Reorder profile sections - just pass array of section IDs in desired order
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    new_order = request.data.get('section_ids', [])
    
    if not new_order:
        return Response({'error': 'section_ids array is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        profile.reorder_sections(new_order)
        return Response({'message': 'Sections reordered successfully'})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def upload_section_images(request, section_id):
    """
    Upload multiple images for a section
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    # Check if section exists
    section = profile.get_section_by_id(section_id)
    if not section:
        return Response({'error': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)
    
    images = request.FILES.getlist('images')
    captions = request.data.getlist('captions', [])
    
    if not images:
        return Response({'error': 'No images provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Delete existing images for this section
    SectionImage.objects.filter(
        profile=profile,
        section_id=section_id
    ).delete()
    
    created_images = []
    for i, image in enumerate(images):
        caption = captions[i] if i < len(captions) else ''
        section_image = SectionImage.objects.create(
            profile=profile,
            section_id=section_id,
            image=image,
            caption=caption
        )
        created_images.append(section_image)
    
    serializer = SectionImageSerializer(created_images, many=True, context={'request': request})
    return Response({
        'message': f'{len(created_images)} images uploaded successfully',
        'images': serializer.data
    }, status=status.HTTP_201_CREATED)


@api_view(['PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def section_image_detail(request, image_id):
    """
    Update or delete a section image
    """
    try:
        image = SectionImage.objects.get(
            id=image_id,
            profile__user=request.user
        )
    except SectionImage.DoesNotExist:
        return Response({'error': 'Image not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'PUT':
        # Update image caption
        caption = request.data.get('caption', '')
        image.caption = caption
        image.save()
        
        serializer = SectionImageSerializer(image, context={'request': request})
        return Response(serializer.data)
    
    elif request.method == 'DELETE':
        image.image.delete()  # Delete the actual file
        image.delete()
        return Response({'message': 'Image deleted successfully'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def reset_sections_to_default(request):
    """
    Reset user's sections to default sections
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    try:
        default_sections = profile.reset_to_default_sections()
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response({
            'message': 'Sections reset to default successfully',
            'sections': serializer.data.get('sections', [])
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# Admin-specific views (same logic, different target user)

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_list_users(request):
    """
    List all users (admin only)
    """
    users = User.objects.all().order_by('-created_at')
    
    # Add search functionality
    search = request.GET.get('search')
    if search:
        users = users.filter(
            models.Q(email__icontains=search) |
            models.Q(fullname__icontains=search) |
            models.Q(username__icontains=search)
        )
    
    # Add filtering
    is_active = request.GET.get('is_active')
    if is_active is not None:
        users = users.filter(is_active=is_active.lower() == 'true')
        
    is_staff = request.GET.get('is_staff')
    if is_staff is not None:
        users = users.filter(is_staff=is_staff.lower() == 'true')
    
    serializer = UserSerializer(users, many=True, context={'request': request})
    return Response({
        'users': serializer.data,
        'count': users.count()
    })


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_create_user(request):
    """
    Create new user with profile data (admin only)
    """
    # Extract password from request data
    password = request.data.get('password')
    if not password:
        return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Extract profile fields from request data
    profile_data = {
        'bio': request.data.get('bio', ''),
        'location': request.data.get('location', ''),
        'website': request.data.get('website', '')
    }
    
    # Create user data without password and profile fields for serializer
    user_data = request.data.copy()
    user_data.pop('password', None)
    user_data.pop('bio', None)
    user_data.pop('location', None)
    user_data.pop('website', None)
    
    # Validate user data
    serializer = UserSerializer(data=user_data)
    if serializer.is_valid():
        # Create user with password
        user = User.objects.create_user(
            password=password,
            **serializer.validated_data
        )
        
        # Create or update profile with provided data
        profile, created = Profile.objects.get_or_create(user=user)
        for field, value in profile_data.items():
            if value is not None and value != '':
                setattr(profile, field, value)
        
        # Set joined_date to user's created_at date
        profile.joined_date = user.created_at
        profile.save()
        
        # Return created user data with profile
        response_serializer = UserSerializer(user, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAdminUser])
def admin_user_detail(request, user_id):
    """
    Get, update, or delete user (admin only)
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = UserSerializer(user, context={'request': request})
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        # Extract profile fields from request data
        profile_data = {
            'bio': request.data.get('bio'),
            'location': request.data.get('location'),
            'website': request.data.get('website')
        }
        
        # Create user data without profile fields for serializer
        user_data = request.data.copy()
        user_data.pop('bio', None)
        user_data.pop('location', None)
        user_data.pop('website', None)
        
        # Update user fields
        serializer = UserSerializer(user, data=user_data, partial=True)
        if serializer.is_valid():
            serializer.save()
            
            # Update profile fields if provided
            profile, created = Profile.objects.get_or_create(user=user)
            for field, value in profile_data.items():
                if value is not None:
                    setattr(profile, field, value)
            profile.save()
            
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        user.delete()
        return Response({'message': 'User deleted successfully'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_get_user_profile(request, user_id):
    """
    Get user profile (admin version - same as user profile but for any user)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['PUT', 'PATCH'])
@permission_classes([permissions.IsAdminUser])
def admin_update_user_profile(request, user_id):
    """
    Update user profile (admin version - same logic as update_profile_complete)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Use the same logic as update_profile_complete but for target user
    try:
        # Update user fields first (email, fullname)
        if 'email' in request.data:
            user.email = request.data['email']
        if 'fullname' in request.data:
            user.fullname = request.data['fullname']
        user.save()
        
        # Handle form data
        if request.content_type and request.content_type.startswith('multipart/form-data'):
            # Extract sections data from form
            sections_data = request.data.get('sections')
            if sections_data:
                if isinstance(sections_data, str):
                    import json
                    sections_data = json.loads(sections_data)
                
                # Update sections
                profile.sections = sections_data
                profile.save()
                
                # Handle images for each section
                for section in sections_data:
                    section_id = section.get('id')
                    if section_id:
                        # Get images for this section from form data
                        section_images = request.FILES.getlist(f'section_{section_id}_images')
                        section_captions = request.data.getlist(f'section_{section_id}_captions', [])
                        
                        # Delete existing images for this section
                        SectionImage.objects.filter(
                            profile=profile,
                            section_id=section_id
                        ).delete()
                        
                        # Upload new images
                        for i, image in enumerate(section_images):
                            caption = section_captions[i] if i < len(section_captions) else ''
                            SectionImage.objects.create(
                                profile=profile,
                                section_id=section_id,
                                image=image,
                                caption=caption
                            )
            
            # Update basic profile fields
            if 'bio' in request.data:
                profile.bio = request.data['bio']
            if 'location' in request.data:
                profile.location = request.data['location']
            if 'website' in request.data:
                profile.website = request.data['website']
            if 'joined_date' in request.data:
                profile.joined_date = request.data['joined_date']
            if 'image' in request.FILES:
                profile.image = request.FILES['image']
            
            profile.save()
            
        else:
            # Handle JSON data
            sections_data = request.data.get('sections', [])
            if sections_data:
                profile.sections = sections_data
                profile.save()
            
            # Update other fields
            if 'bio' in request.data:
                profile.bio = request.data['bio']
            if 'location' in request.data:
                profile.location = request.data['location']
            if 'website' in request.data:
                profile.website = request.data['website']
            if 'joined_date' in request.data:
                profile.joined_date = request.data['joined_date']
        
        # Return updated profile
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_upload_user_profile_image(request, user_id):
    """
    Upload profile image for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if 'image' not in request.FILES:
        return Response({'error': 'No image provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    profile.image = request.FILES['image']
    profile.save()
    
    serializer = ProfileSerializer(profile, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([permissions.IsAdminUser])
def admin_delete_user_profile_image(request, user_id):
    """
    Delete profile image for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile = Profile.objects.get(user=user)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Profile.DoesNotExist:
        return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if profile.image:
        profile.image.delete()
        profile.image = None
        profile.save()
        return Response({'message': 'Profile image deleted successfully'}, status=status.HTTP_200_OK)
    else:
        return Response({'error': 'No profile image to delete'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAdminUser])
def admin_user_profile_sections(request, user_id):
    """
    Get or create profile sections for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response({
            'sections': serializer.data.get('sections', [])
        })
    
    elif request.method == 'POST':
        title = request.data.get('title')
        content = request.data.get('content')
        
        if not title or not content:
            return Response(
                {'error': 'Title and content are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        new_section = profile.add_section(title, content)
        return Response(new_section, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAdminUser])
def admin_user_profile_section_detail(request, user_id, section_id):
    """
    Manage individual profile sections for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    section = profile.get_section_by_id(section_id)
    
    if not section:
        return Response({'error': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        return Response(section)
    
    elif request.method in ['PUT', 'PATCH']:
        # Update section data
        update_data = {}
        if 'title' in request.data:
            update_data['title'] = request.data['title']
        if 'content' in request.data:
            update_data['content'] = request.data['content']
        
        updated_section = profile.update_section(section_id, **update_data)
        if updated_section:
            return Response(updated_section)
        return Response({'error': 'Failed to update section'}, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        profile.delete_section(section_id)
        return Response({'message': 'Section deleted successfully'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_reorder_user_sections(request, user_id):
    """
    Reorder profile sections for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    new_order = request.data.get('section_ids', [])
    
    if not new_order:
        return Response({'error': 'section_ids array is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        profile.reorder_sections(new_order)
        return Response({'message': 'Sections reordered successfully'})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_reset_user_sections(request, user_id):
    """
    Reset user's sections to default sections (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        default_sections = profile.reset_to_default_sections()
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response({
            'message': 'Sections reset to default successfully',
            'sections': serializer.data.get('sections', [])
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_upload_user_section_images(request, user_id, section_id):
    """
    Upload multiple images for a section (admin version) - adds to existing images
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if section exists
    section = profile.get_section_by_id(section_id)
    if not section:
        return Response({'error': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)
    
    images = request.FILES.getlist('images')
    captions = request.data.getlist('captions', [])
    
    if not images:
        return Response({'error': 'No images provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Add new images to existing ones (don't delete existing images)
    created_images = []
    for i, image in enumerate(images):
        caption = captions[i] if i < len(captions) else ''
        section_image = SectionImage.objects.create(
            profile=profile,
            section_id=section_id,
            image=image,
            caption=caption
        )
        created_images.append(section_image)
    
    # Get all images for this section (including newly added ones)
    all_images = SectionImage.objects.filter(
        profile=profile,
        section_id=section_id
    ).order_by('created_at')
    
    serializer = SectionImageSerializer(all_images, many=True, context={'request': request})
    return Response({
        'message': f'{len(created_images)} new images added successfully. Total images in section: {all_images.count()}',
        'images': serializer.data
    }, status=status.HTTP_201_CREATED)


@api_view(['PUT', 'DELETE'])
@permission_classes([permissions.IsAdminUser])
def admin_user_section_image_detail(request, user_id, section_id, image_id):
    """
    Update or delete a section image (admin version)
    """
    try:
        image = SectionImage.objects.get(
            id=image_id,
            profile__user__id=user_id,
            section_id=section_id
        )
    except SectionImage.DoesNotExist:
        return Response({'error': 'Image not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'PUT':
        # Update image caption
        caption = request.data.get('caption', '')
        image.caption = caption
        image.save()
        
        serializer = SectionImageSerializer(image, context={'request': request})
        return Response(serializer.data)
    
    elif request.method == 'DELETE':
        image.image.delete()  # Delete the actual file
        image.delete()
        return Response({'message': 'Image deleted successfully'}, status=status.HTTP_200_OK)
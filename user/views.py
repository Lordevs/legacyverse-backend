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
from datetime import timedelta
import uuid

from .models import User, Profile, PasswordResetToken, ChildhoodImage
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserSerializer,
    ProfileSerializer, ProfileImageSerializer, PasswordChangeSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer, ChildhoodImageSerializer,
    ChildhoodImageUploadSerializer, BulkChildhoodImageUploadSerializer
)
from .email_utils import send_password_reset_email, send_welcome_email, send_password_change_confirmation


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom JWT token view for login
    """
    def post(self, request, *args, **kwargs):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
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
    try:
        refresh_token = request.data["refresh"]
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)


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
@permission_classes([permissions.IsAuthenticated])
def refresh_token_view(request):
    """
    Refresh JWT token endpoint
    """
    try:
        refresh_token = request.data["refresh"]
        token = RefreshToken(refresh_token)
        return Response({
            'access': str(token.access_token)
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
        serializer = ProfileSerializer(profile)
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


# Childhood Image Views
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def childhood_images_view(request):
    """
    GET: Get all childhood images for the authenticated user
    POST: Upload multiple childhood images
    """
    if request.method == 'GET':
        try:
            profile = Profile.objects.get(user=request.user)
            childhood_images = profile.childhood_images.all()
            serializer = ChildhoodImageSerializer(childhood_images, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Profile.DoesNotExist:
            # Create profile if it doesn't exist
            profile = Profile.objects.create(user=request.user)
            return Response([], status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        profile, created = Profile.objects.get_or_create(user=request.user)
        serializer = BulkChildhoodImageUploadSerializer(data=request.data)
        
        if serializer.is_valid():
            images = serializer.validated_data['images']
            captions = serializer.validated_data.get('captions', [])
            
            childhood_images = []
            for i, image in enumerate(images):
                caption = captions[i] if i < len(captions) else ''
                childhood_image = ChildhoodImage.objects.create(
                    profile=profile,
                    image=image,
                    caption=caption
                )
                childhood_images.append(childhood_image)
            
            response_serializer = ChildhoodImageSerializer(childhood_images, many=True)
            return Response({
                'message': f'{len(childhood_images)} childhood images uploaded successfully',
                'images': response_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer = ChildhoodImageSerializer(childhood_images, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
def update_childhood_image(request, image_id):
    """
    Update a specific childhood image (caption only)
    """
    try:
        profile = Profile.objects.get(user=request.user)
        childhood_image = ChildhoodImage.objects.get(id=image_id, profile=profile)
        
        serializer = ChildhoodImageUploadSerializer(childhood_image, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    except (Profile.DoesNotExist, ChildhoodImage.DoesNotExist):
        return Response({'error': 'Childhood image not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_childhood_image(request, image_id):
    """
    Delete a specific childhood image
    """
    try:
        profile = Profile.objects.get(user=request.user)
        childhood_image = ChildhoodImage.objects.get(id=image_id, profile=profile)
        childhood_image.image.delete()  # Delete the actual image file
        childhood_image.delete()
        return Response({'message': 'Childhood image deleted successfully'}, status=status.HTTP_200_OK)
    
    except (Profile.DoesNotExist, ChildhoodImage.DoesNotExist):
        return Response({'error': 'Childhood image not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_all_childhood_images(request):
    """
    Delete all childhood images for the authenticated user
    """
    try:
        profile = Profile.objects.get(user=request.user)
        childhood_images = profile.childhood_images.all()
        
        # Delete all image files
        for img in childhood_images:
            img.image.delete()
        
        # Delete all database records
        count = childhood_images.count()
        childhood_images.delete()
        
        return Response({'message': f'{count} childhood images deleted successfully'}, status=status.HTTP_200_OK)
    
    except Profile.DoesNotExist:
        return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

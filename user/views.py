from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils import timezone
from django.db import models
from datetime import timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers as rf_serializers

from .models import User, Profile, PasswordResetToken, SectionImage, FamilyRelationship
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserSerializer,
    ProfileSerializer,
    ProfileImageSerializer,
    PasswordChangeSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    SectionImageSerializer,
    ProfileListSerializer,
    FamilyMemberAddSerializer,
    FamilyRelationshipRequestSerializer,
    FamilyRequestRespondSerializer,
    FamilyTreeMemberSerializer,
    FamilyTreeResponseSerializer,
    FamilyRelationshipUpdateSerializer,
)
from .email_utils import (
    send_password_reset_email,
    send_welcome_email,
    send_password_change_confirmation,
    send_family_invitation_email,
)


# ── Inline response serializers (for Swagger/ReDoc schema) ────────────────────
class _TokenResponseSerializer(rf_serializers.Serializer):
    refresh = rf_serializers.CharField()
    access = rf_serializers.CharField()
    user = UserSerializer()


class _RegisterResponseSerializer(rf_serializers.Serializer):
    message = rf_serializers.CharField()
    refresh = rf_serializers.CharField()
    access = rf_serializers.CharField()
    user = UserSerializer()


class _MessageSerializer(rf_serializers.Serializer):
    message = rf_serializers.CharField()


class _ErrorSerializer(rf_serializers.Serializer):
    error = rf_serializers.CharField()


class _RefreshResponseSerializer(rf_serializers.Serializer):
    access = rf_serializers.CharField()
    refresh = rf_serializers.CharField()


class _SectionsResponseSerializer(rf_serializers.Serializer):
    sections = rf_serializers.ListField(child=rf_serializers.DictField())


class _ReorderRequestSerializer(rf_serializers.Serializer):
    section_ids = rf_serializers.ListField(
        child=rf_serializers.CharField(),
        help_text="Array of section IDs in desired order",
    )


class _SectionImagesResponseSerializer(rf_serializers.Serializer):
    message = rf_serializers.CharField()
    images = SectionImageSerializer(many=True)


class _AdminUsersResponseSerializer(rf_serializers.Serializer):
    users = UserSerializer(many=True)
    count = rf_serializers.IntegerField()


class _ProfilesListResponseSerializer(rf_serializers.Serializer):
    profiles = ProfileListSerializer(many=True)
    count = rf_serializers.IntegerField()
    page = rf_serializers.IntegerField()
    page_size = rf_serializers.IntegerField()
    total_pages = rf_serializers.IntegerField()


class _GoogleAuthRequestSerializer(rf_serializers.Serializer):
    id_token = rf_serializers.CharField(
        help_text="Google OAuth2 id_token obtained from the frontend"
    )


class _GoogleUrlResponseSerializer(rf_serializers.Serializer):
    auth_url = rf_serializers.CharField()


class _LogoutRequestSerializer(rf_serializers.Serializer):
    refresh = rf_serializers.CharField(help_text="Refresh token to blacklist")


class _ChangePasswordRequestSerializer(rf_serializers.Serializer):
    old_password = rf_serializers.CharField()
    new_password = rf_serializers.CharField()
    confirm_password = rf_serializers.CharField()


class _GoogleTokenResponseSerializer(rf_serializers.Serializer):
    refresh = rf_serializers.CharField()
    access = rf_serializers.CharField()
    user = UserSerializer()
    created = rf_serializers.BooleanField(
        help_text="True if this is a newly registered account"
    )


# ─────────────────────────────────────────────────────────────────────────────


@extend_schema(
    tags=["Auth"],
    request=UserLoginSerializer,
    responses={200: _TokenResponseSerializer, 400: _ErrorSerializer},
    summary="Login – obtain JWT access and refresh tokens",
)
class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom JWT token view for login - Enhanced with admin detection
    """

    def post(self, request, *args, **kwargs):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            refresh = RefreshToken.for_user(user)

            # Enhanced user data with admin info for frontend routing
            user_data = UserSerializer(user).data
            user_data.update(
                {
                    "is_admin": user.is_staff or user.is_superuser,
                    # 'is_staff': user.is_staff,
                    # 'is_superuser': user.is_superuser,
                    # 'permissions': {
                    #     'can_manage_users': user.is_staff or user.is_superuser,
                    #     'can_manage_profiles': user.is_staff or user.is_superuser,
                    #     'can_view_admin': user.is_staff or user.is_superuser,
                    # }
                }
            )

            return Response(
                {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                    "user": user_data,
                }
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Auth"],
    request=UserRegistrationSerializer,
    responses={201: _RegisterResponseSerializer, 400: _ErrorSerializer},
    summary="Register a new user",
)
@api_view(["POST"])
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
        return Response(
            {
                "message": "User registered successfully",
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Auth"],
    request=_LogoutRequestSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer},
    summary="Logout – blacklist refresh token",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    """
    User logout endpoint
    """
    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return Response(
            {"error": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({"message": "Logout successful"}, status=status.HTTP_200_OK)
    except Exception as e:
        # Provide more details for debugging
        return Response(
            {"error": f"Invalid refresh token: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(
    tags=["Auth"],
    request=ForgotPasswordSerializer,
    responses={200: _MessageSerializer, 500: _ErrorSerializer},
    summary="Request a password reset email",
)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def forgot_password_view(request):
    """
    Forgot password endpoint
    """
    serializer = ForgotPasswordSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data["email"]
        try:
            user = User.objects.get(email=email)

            # Invalidate any existing reset tokens for this user
            PasswordResetToken.objects.filter(user=user, is_used=False).update(
                is_used=True
            )

            # Create new password reset token
            reset_token = PasswordResetToken.objects.create(
                user=user, expires_at=timezone.now() + timedelta(hours=1)
            )

            # Send password reset email
            email_sent = send_password_reset_email(user, reset_token)

            if email_sent:
                return Response(
                    {
                        "message": "Password reset instructions have been sent to your email address"
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {"error": "Failed to send email. Please try again later."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except User.DoesNotExist:
            # For security, don't reveal if email exists or not
            return Response(
                {
                    "message": "If an account with that email exists, password reset instructions have been sent."
                },
                status=status.HTTP_200_OK,
            )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Auth"],
    request=ResetPasswordSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer},
    summary="Reset password using emailed token",
)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def reset_password_view(request):
    """
    Reset password endpoint
    """
    serializer = ResetPasswordSerializer(data=request.data)
    if serializer.is_valid():
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        try:
            reset_token = PasswordResetToken.objects.get(token=token)
            if reset_token.is_valid():
                user = reset_token.user
                user.set_password(new_password)
                user.save()
                reset_token.is_used = True
                reset_token.save()
                return Response(
                    {"message": "Password reset successful"}, status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {"error": "Invalid or expired token"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except PasswordResetToken.DoesNotExist:
            return Response(
                {"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST
            )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Auth"],
    request=_ChangePasswordRequestSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer},
    summary="Change password while authenticated",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def change_password_view(request):
    """
    Change password endpoint
    """
    serializer = PasswordChangeSerializer(data=request.data)
    if serializer.is_valid():
        old_password = serializer.validated_data["old_password"]
        new_password = serializer.validated_data["new_password"]

        if not request.user.check_password(old_password):
            return Response(
                {"error": "Old password is incorrect"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save()

        # Send password change confirmation email
        send_password_change_confirmation(request.user)

        return Response(
            {"message": "Password changed successfully"}, status=status.HTTP_200_OK
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Auth"],
    request=_LogoutRequestSerializer,
    responses={200: _RefreshResponseSerializer, 400: _ErrorSerializer},
    summary="Refresh JWT access token",
)
@api_view(["POST"])
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
        return Response(
            {"access": new_access, "refresh": new_refresh}, status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST
        )


# Profile Views
@extend_schema(
    tags=["Profile"],
    responses={200: ProfileSerializer},
    summary="Get or update the authenticated user profile",
)
class ProfileDetailView(generics.RetrieveUpdateAPIView):
    """
    Get and update user profile
    """

    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, created = Profile.objects.get_or_create(user=self.request.user)
        return profile


@extend_schema(
    tags=["Public"],
    responses={200: ProfileSerializer, 404: _ErrorSerializer},
    summary="Get a public profile by username",
)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def get_profile_by_username(request, username):
    """
    Get profile by username (public endpoint)
    """
    try:
        user = User.objects.get(username=username)
        profile, created = Profile.objects.get_or_create(user=user)
        serializer = ProfileSerializer(profile, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    tags=["Profile"],
    request=ProfileImageSerializer,
    responses={200: ProfileSerializer, 400: _ErrorSerializer},
    summary="Upload or replace profile image",
)
@api_view(["POST"])
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


@extend_schema(
    tags=["Profile"],
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Delete profile image",
)
@api_view(["DELETE"])
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
            return Response(
                {"message": "Profile image deleted successfully"},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": "No profile image to delete"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except Profile.DoesNotExist:
        return Response(
            {"error": "Profile not found"}, status=status.HTTP_404_NOT_FOUND
        )


# Section Management Views


# Get user details by username
@extend_schema(
    tags=["Public"],
    responses={200: UserSerializer, 404: _ErrorSerializer},
    summary="Get public user info by username",
)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def get_user_by_username(request, username):
    """
    Get user details by username (public endpoint)
    """
    from .models import User

    try:
        user = User.objects.get(username=username)
        serializer = UserSerializer(user, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    tags=["Public"],
    responses={200: _ProfilesListResponseSerializer},
    summary="Paginated list of all public user profiles",
    parameters=[
        OpenApiParameter(
            "search", str, description="Filter by name, username, bio or location"
        ),
        OpenApiParameter("location", str, description="Filter by location"),
        OpenApiParameter("page", int, description="Page number (default 1)"),
        OpenApiParameter("page_size", int, description="Results per page (default 20)"),
    ],
)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def list_user_profiles(request):
    """
    List all user profiles for public display (public endpoint)
    """
    # Get all active profiles with their users (exclude admin users)
    profiles = (
        Profile.objects.filter(
            user__is_active=True, user__is_staff=False, user__is_superuser=False
        )
        .select_related("user")
        .order_by("-created_at")
    )

    # Add search functionality
    search = request.GET.get("search")
    if search:
        profiles = profiles.filter(
            models.Q(user__fullname__icontains=search)
            | models.Q(user__username__icontains=search)
            | models.Q(bio__icontains=search)
            | models.Q(location__icontains=search)
        )

    # Add filtering by location
    location = request.GET.get("location")
    if location:
        profiles = profiles.filter(location__icontains=location)

    # Pagination
    page_size = int(request.GET.get("page_size", 20))
    page = int(request.GET.get("page", 1))

    start = (page - 1) * page_size
    end = start + page_size

    profiles_page = profiles[start:end]

    # Serialize with ProfileListSerializer (excludes sections to reduce data)
    from .serializers import ProfileListSerializer

    serializer = ProfileListSerializer(
        profiles_page, many=True, context={"request": request}
    )

    return Response(
        {
            "profiles": serializer.data,
            "count": profiles.count(),
            "page": page,
            "page_size": page_size,
            "total_pages": (profiles.count() + page_size - 1) // page_size,
        }
    )


# New unified profile update views
@extend_schema(
    tags=["Profile"],
    request=ProfileSerializer,
    responses={200: ProfileSerializer, 400: _ErrorSerializer},
    summary="Unified profile update (JSON or multipart)",
)
@api_view(["PUT", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def update_profile_complete(request):
    """
    Update complete profile - handles both JSON and file uploads
    """
    profile, created = Profile.objects.get_or_create(user=request.user)

    try:
        # Handle form data
        if request.content_type.startswith("multipart/form-data"):
            # Extract sections data from form
            sections_data = request.data.get("sections")
            if sections_data:
                if isinstance(sections_data, str):
                    import json

                    sections_data = json.loads(sections_data)

                # Update sections
                profile.sections = sections_data
                profile.save()

                # Handle images for each section
                for section in sections_data:
                    section_id = section.get("id")
                    if section_id:
                        # Get images for this section from form data
                        section_images = request.FILES.getlist(
                            f"section_{section_id}_images"
                        )
                        section_captions = request.data.getlist(
                            f"section_{section_id}_captions", []
                        )

                        # Delete existing images for this section
                        SectionImage.objects.filter(
                            profile=profile, section_id=section_id
                        ).delete()

                        # Upload new images
                        for i, image in enumerate(section_images):
                            caption = (
                                section_captions[i] if i < len(section_captions) else ""
                            )
                            SectionImage.objects.create(
                                profile=profile,
                                section_id=section_id,
                                image=image,
                                caption=caption,
                            )

            # Update basic profile fields
            if "bio" in request.data:
                profile.bio = request.data["bio"]
            if "location" in request.data:
                profile.location = request.data["location"]
            if "website" in request.data:
                profile.website = request.data["website"]
            if "joined_date" in request.data:
                profile.joined_date = request.data["joined_date"]
            if "image" in request.FILES:
                profile.image = request.FILES["image"]

            profile.save()

        else:
            # Handle JSON data
            sections_data = request.data.get("sections", [])
            if sections_data:
                profile.sections = sections_data
                profile.save()

            # Update other fields
            if "bio" in request.data:
                profile.bio = request.data["bio"]
            if "location" in request.data:
                profile.location = request.data["location"]
            if "website" in request.data:
                profile.website = request.data["website"]
            if "joined_date" in request.data:
                profile.joined_date = request.data["joined_date"]

        # Return updated profile
        serializer = ProfileSerializer(profile, context={"request": request})
        return Response(serializer.data)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Profile"],
    responses={200: _SectionsResponseSerializer},
    summary="List all sections (GET) or create a new section (POST)",
)
@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def profile_sections_view(request):
    """
    GET: Get all sections for authenticated user
    POST: Create new section
    """
    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == "GET":
        serializer = ProfileSerializer(profile, context={"request": request})
        return Response({"sections": serializer.data.get("sections", [])})

    elif request.method == "POST":
        title = request.data.get("title")
        content = request.data.get("content")

        if not title or not content:
            return Response(
                {"error": "Title and content are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_section = profile.add_section(title, content)
        return Response(new_section, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Profile"],
    responses={200: rf_serializers.DictField(), 404: _ErrorSerializer},
    summary="Get, update or delete a single profile section",
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def profile_section_detail(request, section_id):
    """
    Manage individual profile sections
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    section = profile.get_section_by_id(section_id)

    if not section:
        return Response(
            {"error": "Section not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        return Response(section)

    elif request.method in ["PUT", "PATCH"]:
        # Update section data
        update_data = {}
        if "title" in request.data:
            update_data["title"] = request.data["title"]
        if "content" in request.data:
            update_data["content"] = request.data["content"]

        updated_section = profile.update_section(section_id, **update_data)
        if updated_section:
            return Response(updated_section)
        return Response(
            {"error": "Failed to update section"}, status=status.HTTP_400_BAD_REQUEST
        )

    elif request.method == "DELETE":
        profile.delete_section(section_id)
        return Response(
            {"message": "Section deleted successfully"}, status=status.HTTP_200_OK
        )


@extend_schema(
    tags=["Profile"],
    request=_ReorderRequestSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer},
    summary="Reorder profile sections by providing ordered section IDs",
)
@api_view(["POST", "PUT"])
@permission_classes([permissions.IsAuthenticated])
def reorder_sections(request):
    """
    Reorder profile sections - just pass array of section IDs in desired order
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    new_order = request.data.get("section_ids", [])

    if not new_order:
        return Response(
            {"error": "section_ids array is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        profile.reorder_sections(new_order)
        return Response({"message": "Sections reordered successfully"})
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Profile"],
    responses={
        201: _SectionImagesResponseSerializer,
        400: _ErrorSerializer,
        404: _ErrorSerializer,
    },
    summary="Upload images for a profile section",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def upload_section_images(request, section_id):
    """
    Upload multiple images for a section
    """
    profile, created = Profile.objects.get_or_create(user=request.user)

    # Check if section exists
    section = profile.get_section_by_id(section_id)
    if not section:
        return Response(
            {"error": "Section not found"}, status=status.HTTP_404_NOT_FOUND
        )

    images = request.FILES.getlist("images")
    captions = request.data.getlist("captions", [])

    if not images:
        return Response(
            {"error": "No images provided"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Delete existing images for this section
    SectionImage.objects.filter(profile=profile, section_id=section_id).delete()

    created_images = []
    for i, image in enumerate(images):
        caption = captions[i] if i < len(captions) else ""
        section_image = SectionImage.objects.create(
            profile=profile, section_id=section_id, image=image, caption=caption
        )
        created_images.append(section_image)

    serializer = SectionImageSerializer(
        created_images, many=True, context={"request": request}
    )
    return Response(
        {
            "message": f"{len(created_images)} images uploaded successfully",
            "images": serializer.data,
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    tags=["Profile"],
    responses={200: SectionImageSerializer, 404: _ErrorSerializer},
    summary="Update caption or delete a section image",
)
@api_view(["PUT", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def section_image_detail(request, image_id):
    """
    Update or delete a section image
    """
    try:
        image = SectionImage.objects.get(id=image_id, profile__user=request.user)
    except SectionImage.DoesNotExist:
        return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PUT":
        # Update image caption
        caption = request.data.get("caption", "")
        image.caption = caption
        image.save()

        serializer = SectionImageSerializer(image, context={"request": request})
        return Response(serializer.data)

    elif request.method == "DELETE":
        image.image.delete()  # Delete the actual file
        image.delete()
        return Response(
            {"message": "Image deleted successfully"}, status=status.HTTP_200_OK
        )


@extend_schema(
    tags=["Profile"],
    responses={200: _SectionsResponseSerializer, 400: _ErrorSerializer},
    summary="Reset profile sections to the 6 defaults",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def reset_sections_to_default(request):
    """
    Reset user's sections to default sections
    """
    profile, created = Profile.objects.get_or_create(user=request.user)

    try:
        default_sections = profile.reset_to_default_sections()
        serializer = ProfileSerializer(profile, context={"request": request})
        return Response(
            {
                "message": "Sections reset to default successfully",
                "sections": serializer.data.get("sections", []),
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# Admin-specific views (same logic, different target user)


@extend_schema(
    tags=["Admin – Users"],
    responses={200: _AdminUsersResponseSerializer},
    summary="List all users (admin only)",
    parameters=[
        OpenApiParameter(
            "search", str, description="Search by email, fullname or username"
        ),
        OpenApiParameter("is_active", bool, description="Filter by active status"),
        OpenApiParameter("is_staff", bool, description="Filter by staff status"),
    ],
)
@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def admin_list_users(request):
    """
    List all users (admin only)
    """
    users = User.objects.all().order_by("-created_at")

    # Add search functionality
    search = request.GET.get("search")
    if search:
        users = users.filter(
            models.Q(email__icontains=search)
            | models.Q(fullname__icontains=search)
            | models.Q(username__icontains=search)
        )

    # Add filtering
    is_active = request.GET.get("is_active")
    if is_active is not None:
        users = users.filter(is_active=is_active.lower() == "true")

    is_staff = request.GET.get("is_staff")
    if is_staff is not None:
        users = users.filter(is_staff=is_staff.lower() == "true")

    serializer = UserSerializer(users, many=True, context={"request": request})
    return Response({"users": serializer.data, "count": users.count()})


@extend_schema(
    tags=["Admin – Users"],
    request=UserSerializer,
    responses={201: UserSerializer, 400: _ErrorSerializer},
    summary="Create a new user with profile data (admin only)",
)
@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def admin_create_user(request):
    """
    Create new user with profile data (admin only)
    """
    # Extract password from request data
    password = request.data.get("password")
    if not password:
        return Response(
            {"error": "Password is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Extract profile fields from request data
    profile_data = {
        "bio": request.data.get("bio", ""),
        "location": request.data.get("location", ""),
        "website": request.data.get("website", ""),
    }

    # Create user data without password and profile fields for serializer
    user_data = request.data.copy()
    user_data.pop("password", None)
    user_data.pop("bio", None)
    user_data.pop("location", None)
    user_data.pop("website", None)

    # Validate user data
    serializer = UserSerializer(data=user_data)
    if serializer.is_valid():
        # Create user with password
        user = User.objects.create_user(password=password, **serializer.validated_data)

        # Create or update profile with provided data
        profile, created = Profile.objects.get_or_create(user=user)
        for field, value in profile_data.items():
            if value is not None and value != "":
                setattr(profile, field, value)

        # Set joined_date to user's created_at date
        profile.joined_date = user.created_at
        profile.save()

        # Return created user data with profile
        response_serializer = UserSerializer(user, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Admin – Users"],
    request=UserSerializer,
    responses={200: UserSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Get, update or delete any user (admin only)",
)
@api_view(["GET", "PUT", "DELETE"])
@permission_classes([permissions.IsAdminUser])
def admin_user_detail(request, user_id):
    """
    Get, update, or delete user (admin only)
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        serializer = UserSerializer(user, context={"request": request})
        return Response(serializer.data)

    elif request.method == "PUT":
        # Extract profile fields from request data
        profile_data = {
            "bio": request.data.get("bio"),
            "location": request.data.get("location"),
            "website": request.data.get("website"),
        }

        # Create user data without profile fields for serializer
        user_data = request.data.copy()
        user_data.pop("bio", None)
        user_data.pop("location", None)
        user_data.pop("website", None)

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

    elif request.method == "DELETE":
        user.delete()
        return Response(
            {"message": "User deleted successfully"}, status=status.HTTP_200_OK
        )


@extend_schema(
    tags=["Admin – Users"],
    responses={200: ProfileSerializer, 404: _ErrorSerializer},
    summary="Get any user profile (admin only)",
)
@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def admin_get_user_profile(request, user_id):
    """
    Get user profile (admin version - same as user profile but for any user)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
        serializer = ProfileSerializer(profile, context={"request": request})
        return Response(serializer.data)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    tags=["Admin – Users"],
    request=ProfileSerializer,
    responses={200: ProfileSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Update any user profile (admin only)",
)
@api_view(["PUT", "PATCH"])
@permission_classes([permissions.IsAdminUser])
def admin_update_user_profile(request, user_id):
    """
    Update user profile (admin version - same logic as update_profile_complete)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    # Use the same logic as update_profile_complete but for target user
    try:
        # Update user fields first (email, fullname)
        if "email" in request.data:
            user.email = request.data["email"]
        if "fullname" in request.data:
            user.fullname = request.data["fullname"]
        user.save()

        # Handle form data
        if request.content_type and request.content_type.startswith(
            "multipart/form-data"
        ):
            # Extract sections data from form
            sections_data = request.data.get("sections")
            if sections_data:
                if isinstance(sections_data, str):
                    import json

                    sections_data = json.loads(sections_data)

                # Update sections
                profile.sections = sections_data
                profile.save()

                # Handle images for each section
                for section in sections_data:
                    section_id = section.get("id")
                    if section_id:
                        # Get images for this section from form data
                        section_images = request.FILES.getlist(
                            f"section_{section_id}_images"
                        )
                        section_captions = request.data.getlist(
                            f"section_{section_id}_captions", []
                        )

                        # Delete existing images for this section
                        SectionImage.objects.filter(
                            profile=profile, section_id=section_id
                        ).delete()

                        # Upload new images
                        for i, image in enumerate(section_images):
                            caption = (
                                section_captions[i] if i < len(section_captions) else ""
                            )
                            SectionImage.objects.create(
                                profile=profile,
                                section_id=section_id,
                                image=image,
                                caption=caption,
                            )

            # Update basic profile fields
            if "bio" in request.data:
                profile.bio = request.data["bio"]
            if "location" in request.data:
                profile.location = request.data["location"]
            if "website" in request.data:
                profile.website = request.data["website"]
            if "joined_date" in request.data:
                profile.joined_date = request.data["joined_date"]
            if "image" in request.FILES:
                profile.image = request.FILES["image"]

            profile.save()

        else:
            # Handle JSON data
            sections_data = request.data.get("sections", [])
            if sections_data:
                profile.sections = sections_data
                profile.save()

            # Update other fields
            if "bio" in request.data:
                profile.bio = request.data["bio"]
            if "location" in request.data:
                profile.location = request.data["location"]
            if "website" in request.data:
                profile.website = request.data["website"]
            if "joined_date" in request.data:
                profile.joined_date = request.data["joined_date"]

        # Return updated profile
        serializer = ProfileSerializer(profile, context={"request": request})
        return Response(serializer.data)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Admin – Users"],
    request=ProfileImageSerializer,
    responses={200: ProfileSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Upload profile image for any user (admin only)",
)
@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def admin_upload_user_profile_image(request, user_id):
    """
    Upload profile image for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    if "image" not in request.FILES:
        return Response(
            {"error": "No image provided"}, status=status.HTTP_400_BAD_REQUEST
        )

    profile.image = request.FILES["image"]
    profile.save()

    serializer = ProfileSerializer(profile, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Admin – Users"],
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Delete profile image for any user (admin only)",
)
@api_view(["DELETE"])
@permission_classes([permissions.IsAdminUser])
def admin_delete_user_profile_image(request, user_id):
    """
    Delete profile image for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile = Profile.objects.get(user=user)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except Profile.DoesNotExist:
        return Response(
            {"error": "Profile not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if profile.image:
        profile.image.delete()
        profile.image = None
        profile.save()
        return Response(
            {"message": "Profile image deleted successfully"}, status=status.HTTP_200_OK
        )
    else:
        return Response(
            {"error": "No profile image to delete"}, status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    tags=["Admin – Users"],
    responses={
        200: _SectionsResponseSerializer,
        201: rf_serializers.DictField(),
        404: _ErrorSerializer,
    },
    summary="Get or create profile sections for any user (admin only)",
)
@api_view(["GET", "POST"])
@permission_classes([permissions.IsAdminUser])
def admin_user_profile_sections(request, user_id):
    """
    Get or create profile sections for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        serializer = ProfileSerializer(profile, context={"request": request})
        return Response({"sections": serializer.data.get("sections", [])})

    elif request.method == "POST":
        title = request.data.get("title")
        content = request.data.get("content")

        if not title or not content:
            return Response(
                {"error": "Title and content are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_section = profile.add_section(title, content)
        return Response(new_section, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Admin – Users"],
    responses={200: rf_serializers.DictField(), 404: _ErrorSerializer},
    summary="Get, update or delete a section for any user (admin only)",
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([permissions.IsAdminUser])
def admin_user_profile_section_detail(request, user_id, section_id):
    """
    Manage individual profile sections for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    section = profile.get_section_by_id(section_id)

    if not section:
        return Response(
            {"error": "Section not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        return Response(section)

    elif request.method in ["PUT", "PATCH"]:
        # Update section data
        update_data = {}
        if "title" in request.data:
            update_data["title"] = request.data["title"]
        if "content" in request.data:
            update_data["content"] = request.data["content"]

        updated_section = profile.update_section(section_id, **update_data)
        if updated_section:
            return Response(updated_section)
        return Response(
            {"error": "Failed to update section"}, status=status.HTTP_400_BAD_REQUEST
        )

    elif request.method == "DELETE":
        profile.delete_section(section_id)
        return Response(
            {"message": "Section deleted successfully"}, status=status.HTTP_200_OK
        )


@extend_schema(
    tags=["Admin – Users"],
    request=_ReorderRequestSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Reorder sections for any user (admin only)",
)
@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def admin_reorder_user_sections(request, user_id):
    """
    Reorder profile sections for user (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    new_order = request.data.get("section_ids", [])

    if not new_order:
        return Response(
            {"error": "section_ids array is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        profile.reorder_sections(new_order)
        return Response({"message": "Sections reordered successfully"})
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Admin – Users"],
    responses={
        200: _SectionsResponseSerializer,
        400: _ErrorSerializer,
        404: _ErrorSerializer,
    },
    summary="Reset sections to defaults for any user (admin only)",
)
@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def admin_reset_user_sections(request, user_id):
    """
    Reset user's sections to default sections (admin version)
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        default_sections = profile.reset_to_default_sections()
        serializer = ProfileSerializer(profile, context={"request": request})
        return Response(
            {
                "message": "Sections reset to default successfully",
                "sections": serializer.data.get("sections", []),
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Admin – Users"],
    responses={
        201: _SectionImagesResponseSerializer,
        400: _ErrorSerializer,
        404: _ErrorSerializer,
    },
    summary="Upload section images for any user (admin only)",
)
@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def admin_upload_user_section_images(request, user_id, section_id):
    """
    Upload multiple images for a section (admin version) - adds to existing images
    """
    try:
        user = User.objects.get(id=user_id)
        profile, created = Profile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check if section exists
    section = profile.get_section_by_id(section_id)
    if not section:
        return Response(
            {"error": "Section not found"}, status=status.HTTP_404_NOT_FOUND
        )

    images = request.FILES.getlist("images")
    captions = request.data.getlist("captions", [])

    if not images:
        return Response(
            {"error": "No images provided"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Add new images to existing ones (don't delete existing images)
    created_images = []
    for i, image in enumerate(images):
        caption = captions[i] if i < len(captions) else ""
        section_image = SectionImage.objects.create(
            profile=profile, section_id=section_id, image=image, caption=caption
        )
        created_images.append(section_image)

    # Get all images for this section (including newly added ones)
    all_images = SectionImage.objects.filter(
        profile=profile, section_id=section_id
    ).order_by("created_at")

    serializer = SectionImageSerializer(
        all_images, many=True, context={"request": request}
    )
    return Response(
        {
            "message": f"{len(created_images)} new images added successfully. Total images in section: {all_images.count()}",
            "images": serializer.data,
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    tags=["Admin – Users"],
    responses={200: SectionImageSerializer, 404: _ErrorSerializer},
    summary="Update or delete a section image for any user (admin only)",
)
@api_view(["PUT", "DELETE"])
@permission_classes([permissions.IsAdminUser])
def admin_user_section_image_detail(request, user_id, section_id, image_id):
    """
    Update or delete a section image (admin version)
    """
    try:
        image = SectionImage.objects.get(
            id=image_id, profile__user__id=user_id, section_id=section_id
        )
    except SectionImage.DoesNotExist:
        return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PUT":
        # Update image caption
        caption = request.data.get("caption", "")
        image.caption = caption
        image.save()

        serializer = SectionImageSerializer(image, context={"request": request})
        return Response(serializer.data)

    elif request.method == "DELETE":
        image.image.delete()  # Delete the actual file
        image.delete()
        return Response(
            {"message": "Image deleted successfully"}, status=status.HTTP_200_OK
        )


# ── Family Tree Views ────────────────────────────────────────────────────────


@extend_schema(
    tags=["Family Tree"],
    request=FamilyMemberAddSerializer,
    responses={201: _MessageSerializer, 400: _ErrorSerializer},
    summary="Add an immediate family member",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def add_family_member(request):
    """
    Add an immediate family member (Father, Mother, Son, Daughter, Spouse).
    If the relative does not exist, a placeholder user is created.
    """
    serializer = FamilyMemberAddSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"].lower()
    fullname = serializer.validated_data["fullname"]
    relationship_type = serializer.validated_data["relationship_type"]
    date_of_birth = serializer.validated_data.get("date_of_birth")

    if email == request.user.email.lower():
        return Response(
            {"error": "You cannot add yourself as a family member."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_email = User.objects.normalize_email(email)

    # Check if user already exists
    relative = User.objects.filter(email__iexact=normalized_email).first()
    is_new_user = False

    if not relative:
        # Create invited placeholder user
        is_new_user = True
        relative = User.objects.create(
            email=normalized_email,
            fullname=fullname,
            is_invited=True,
            is_active=True,
        )
        relative.set_unusable_password()
        relative.save()

        # Inferred profile gender
        profile, _ = Profile.objects.get_or_create(user=relative)
        if relationship_type in ["father", "son"]:
            profile.gender = "male"
        elif relationship_type in ["mother", "daughter"]:
            profile.gender = "female"
        if date_of_birth:
            profile.date_of_birth = date_of_birth
        profile.save()

    # Check if a relationship already exists in either direction
    existing_relationship = FamilyRelationship.objects.filter(
        (models.Q(user=request.user) & models.Q(relative=relative))
        | (models.Q(user=relative) & models.Q(relative=request.user))
    ).first()

    if existing_relationship:
        return Response(
            {
                "error": "A relationship request between you and this user already exists."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create relationship record
    relationship = FamilyRelationship.objects.create(
        user=request.user,
        relative=relative,
        relationship_type=relationship_type,
        status="pending",
    )

    # If the relative is an invited/placeholder account, automatically accept the relationship
    if relative.is_invited:
        relationship.status = "accepted"
        relationship.save()

    # Send email notification
    send_family_invitation_email(
        sender=request.user,
        receiver_email=normalized_email,
        receiver_name=fullname,
        relationship_type=relationship.get_relationship_type_display(),
        is_new_user=is_new_user,
    )

    msg = (
        "Invitation email sent and placeholder created."
        if is_new_user
        else "Family relationship request sent."
    )
    if relative.is_invited:
        msg = "Family member added and invitation email sent."

    return Response({"message": msg}, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilyRelationshipRequestSerializer(many=True)},
    summary="List pending family requests received",
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_family_requests(request):
    """
    List all pending family relationship requests received by the current user.
    """
    requests = FamilyRelationship.objects.filter(
        relative=request.user, status="pending"
    ).select_related("user")
    serializer = FamilyRelationshipRequestSerializer(requests, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Family Tree"],
    request=FamilyRequestRespondSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Respond to a family request",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def respond_to_family_request(request, request_id):
    """
    Accept or reject a pending family relationship request.
    """
    try:
        relationship = FamilyRelationship.objects.get(
            id=request_id, relative=request.user, status="pending"
        )
    except FamilyRelationship.DoesNotExist:
        return Response(
            {"error": "Pending request not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = FamilyRequestRespondSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    action = serializer.validated_data["action"]
    if action == "accept":
        relationship.status = "accepted"
        relationship.save()

        # If the user accepts a relationship, check if we need to update their own gender
        # if it is 'prefer_not_to_say' and we can infer it.
        # e.g. A added current user B as "Mother". This means B is female.
        # Let's set B's gender to 'female' if it is currently 'prefer_not_to_say'.
        profile, _ = Profile.objects.get_or_create(user=request.user)
        if profile.gender == "prefer_not_to_say":
            if relationship.relationship_type in ["mother", "daughter"]:
                profile.gender = "female"
                profile.save()
            elif relationship.relationship_type in ["father", "son"]:
                profile.gender = "male"
                profile.save()

        return Response(
            {"message": "Relationship request accepted."},
            status=status.HTTP_200_OK,
        )
    elif action == "reject":
        relationship.status = "rejected"
        relationship.save()
        return Response(
            {"message": "Relationship request rejected."},
            status=status.HTTP_200_OK,
        )


def _get_inverted_relationship(relationship_type, initiator_gender):
    if relationship_type in ["father", "mother"]:
        if initiator_gender == "male":
            return "Son"
        elif initiator_gender == "female":
            return "Daughter"
        else:
            return "Child"
    elif relationship_type in ["son", "daughter"]:
        if initiator_gender == "male":
            return "Father"
        elif initiator_gender == "female":
            return "Mother"
        else:
            return "Parent"
    elif relationship_type == "spouse":
        return "Spouse"
    return "Relative"


@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilyTreeMemberSerializer(many=True)},
    summary="List all accepted family members",
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_family_members(request):
    """
    List all accepted family members with relationship labels.
    """
    relationships = FamilyRelationship.objects.filter(
        (models.Q(user=request.user) | models.Q(relative=request.user)),
        status="accepted",
    ).select_related("user__profile", "relative__profile")

    members_data = []
    for rel in relationships:
        if rel.user == request.user:
            member = rel.relative
            relationship_label = rel.get_relationship_type_display()
        else:
            member = rel.user
            relationship_label = _get_inverted_relationship(
                rel.relationship_type, rel.user.profile.gender
            )

        serialized_member = FamilyTreeMemberSerializer(
            member, context={"request": request}
        ).data
        serialized_member["relationship"] = relationship_label
        serialized_member["relationship_id"] = rel.id
        serialized_member["is_initiator"] = rel.user == request.user
        members_data.append(serialized_member)

    return Response(members_data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilyTreeResponseSerializer},
    summary="Get full family tree (graph)",
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_family_tree(request):
    """
    Retrieve the entire connected family tree using BFS traversal.
    """
    visited_nodes = {request.user.id}
    nodes = [request.user]
    edges = []
    added_edges = set()
    queue = [request.user]

    while queue:
        current_user = queue.pop(0)

        # Get all accepted relationships for current_user
        relations = FamilyRelationship.objects.filter(
            (models.Q(user=current_user) | models.Q(relative=current_user)),
            status="accepted",
        ).select_related("user__profile", "relative__profile")

        for rel in relations:
            neighbor = rel.relative if rel.user == current_user else rel.user

            # Record the edge uniquely
            edge_id = f"{rel.user.id}-{rel.relative.id}"
            if edge_id not in added_edges:
                added_edges.add(edge_id)
                edges.append(
                    {
                        "id": rel.id,
                        "source": rel.user.id,
                        "target": rel.relative.id,
                        "relationship": rel.relationship_type,
                    }
                )

            if neighbor.id not in visited_nodes:
                visited_nodes.add(neighbor.id)
                nodes.append(neighbor)
                queue.append(neighbor)

    # Serialize nodes
    nodes_serializer = FamilyTreeMemberSerializer(
        nodes, many=True, context={"request": request}
    )

    return Response(
        {
            "nodes": nodes_serializer.data,
            "edges": edges,
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Family Tree"],
    responses={200: _MessageSerializer, 404: _ErrorSerializer},
    summary="Revoke or delete a family relationship",
)
@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def revoke_family_relationship(request, relationship_id):
    """
    Revoke/delete an existing family relationship. Either the initiator or recipient can do this.
    """
    try:
        relationship = FamilyRelationship.objects.get(
            models.Q(id=relationship_id) & (models.Q(user=request.user) | models.Q(relative=request.user))
        )
    except FamilyRelationship.DoesNotExist:
        return Response(
            {"error": "Relationship not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    relationship.delete()
    return Response(
        {"message": "Family relationship revoked successfully."},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Family Tree"],
    request=FamilyRelationshipUpdateSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 403: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Edit an initiated family relationship type",
)
@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def edit_family_relationship(request, relationship_id):
    """
    Edit the relationship type of a connection. Only the initiator can edit it.
    If the relative is a registered user, the status resets to pending.
    If the relative is a placeholder, their inferred gender is updated on their profile.
    """
    try:
        relationship = FamilyRelationship.objects.get(id=relationship_id)
    except FamilyRelationship.DoesNotExist:
        return Response(
            {"error": "Relationship not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if relationship.user != request.user:
        return Response(
            {"error": "Only the initiator can edit this relationship."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = FamilyRelationshipUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    new_type = serializer.validated_data["relationship_type"]
    if new_type == relationship.relationship_type:
        return Response(
            {"message": "Relationship type is already set to this value."},
            status=status.HTTP_200_OK,
        )

    relationship.relationship_type = new_type

    # Handle status resets and gender inferences
    relative = relationship.relative
    if not relative.is_invited:
        # Reset to pending for registered users
        relationship.status = "pending"
    else:
        # If relative is invited/placeholder, update their profile gender if inferred
        profile, _ = Profile.objects.get_or_create(user=relative)
        if new_type in ["father", "son"]:
            profile.gender = "male"
            profile.save()
        elif new_type in ["mother", "daughter"]:
            profile.gender = "female"
            profile.save()

    relationship.save()

    return Response(
        {"message": "Relationship type updated successfully."},
        status=status.HTTP_200_OK,
    )

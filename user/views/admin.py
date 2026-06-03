"""
Admin-only views: user management, profile management, sections management,
and section image management for any user.
"""
import json

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, serializers as rf_serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Profile, SectionImage, User
from ..serializers import (
    ProfileImageSerializer,
    ProfileSerializer,
    SectionImageSerializer,
    UserSerializer,
)
from ._serializers import (
    _AdminUsersResponseSerializer,
    _ErrorSerializer,
    _MessageSerializer,
    _ReorderRequestSerializer,
    _SectionImagesResponseSerializer,
    _SectionsResponseSerializer,
)


# ── User CRUD ─────────────────────────────────────────────────────────────────


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
    from django.db import models as db_models

    users = User.objects.all().order_by("-created_at")

    search = request.GET.get("search")
    if search:
        users = users.filter(
            db_models.Q(email__icontains=search)
            | db_models.Q(fullname__icontains=search)
            | db_models.Q(username__icontains=search)
        )

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
    password = request.data.get("password")
    if not password:
        return Response(
            {"error": "Password is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    profile_data = {
        "bio": request.data.get("bio", ""),
        "location": request.data.get("location", ""),
        "website": request.data.get("website", ""),
    }

    user_data = request.data.copy()
    user_data.pop("password", None)
    user_data.pop("bio", None)
    user_data.pop("location", None)
    user_data.pop("website", None)

    serializer = UserSerializer(data=user_data)
    if serializer.is_valid():
        user = User.objects.create_user(password=password, **serializer.validated_data)

        profile, created = Profile.objects.get_or_create(user=user)
        for field, value in profile_data.items():
            if value is not None and value != "":
                setattr(profile, field, value)
        profile.joined_date = user.created_at
        profile.save()

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
        profile_data = {
            "bio": request.data.get("bio"),
            "location": request.data.get("location"),
            "website": request.data.get("website"),
        }

        user_data = request.data.copy()
        user_data.pop("bio", None)
        user_data.pop("location", None)
        user_data.pop("website", None)

        serializer = UserSerializer(user, data=user_data, partial=True)
        if serializer.is_valid():
            serializer.save()

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


# ── Profile management ────────────────────────────────────────────────────────


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

    try:
        if "email" in request.data:
            user.email = request.data["email"]
        if "fullname" in request.data:
            user.fullname = request.data["fullname"]
        user.save()

        if request.content_type and request.content_type.startswith(
            "multipart/form-data"
        ):
            sections_data = request.data.get("sections")
            if sections_data:
                if isinstance(sections_data, str):
                    sections_data = json.loads(sections_data)

                profile.sections = sections_data
                profile.save()

                for section in sections_data:
                    section_id = section.get("id")
                    if section_id:
                        section_images = request.FILES.getlist(
                            f"section_{section_id}_images"
                        )
                        section_captions = request.data.getlist(
                            f"section_{section_id}_captions", []
                        )

                        SectionImage.objects.filter(
                            profile=profile, section_id=section_id
                        ).delete()

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
            sections_data = request.data.get("sections", [])
            if sections_data:
                profile.sections = sections_data
                profile.save()

            if "bio" in request.data:
                profile.bio = request.data["bio"]
            if "location" in request.data:
                profile.location = request.data["location"]
            if "website" in request.data:
                profile.website = request.data["website"]
            if "joined_date" in request.data:
                profile.joined_date = request.data["joined_date"]

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


# ── Section management ────────────────────────────────────────────────────────


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
        profile.reset_to_default_sections()
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


# ── Section image management ──────────────────────────────────────────────────


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

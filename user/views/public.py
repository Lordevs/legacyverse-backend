"""
Public (unauthenticated) views: profile by username, user by username,
and paginated profile listing.
"""
from django.db import models as db_models
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Profile, User
from ..serializers import ProfileListSerializer, ProfileSerializer, UserSerializer
from ._serializers import _ErrorSerializer, _ProfilesListResponseSerializer


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
            db_models.Q(user__fullname__icontains=search)
            | db_models.Q(user__username__icontains=search)
            | db_models.Q(bio__icontains=search)
            | db_models.Q(location__icontains=search)
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

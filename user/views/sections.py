"""
Profile sections and section images views.
"""
from rest_framework import permissions, serializers as rf_serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from ..models import Profile, SectionImage
from ..serializers import ProfileSerializer, SectionImageSerializer
from ._serializers import (
    _ErrorSerializer,
    _MessageSerializer,
    _ReorderRequestSerializer,
    _SectionImagesResponseSerializer,
    _SectionsResponseSerializer,
)


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

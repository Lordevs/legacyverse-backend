"""
Profile views: get/update authenticated user's profile and profile image.
"""

import json

from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Profile, SectionImage
from ..serializers import ProfileImageSerializer, ProfileSerializer
from ._serializers import _ErrorSerializer, _MessageSerializer


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
                    sections_data = json.loads(sections_data)

                # Update sections
                profile.sections = sections_data
                profile.save()

                # Handle images for each section
                for section in sections_data:
                    section_id = section.get("id")
                    if section_id:
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

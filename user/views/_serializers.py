"""
Inline Swagger/ReDoc response serializers.
These are NOT model serializers — they only exist to generate accurate OpenAPI schemas.
"""
from rest_framework import serializers as rf_serializers

from ..serializers import (
    UserSerializer,
    ProfileListSerializer,
    SectionImageSerializer,
)


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

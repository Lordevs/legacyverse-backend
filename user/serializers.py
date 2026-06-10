from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User, Profile, SectionImage, FamilyRelationship, FamilyRelationshipSuggestion


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration
    """

    confirm_password = serializers.CharField(write_only=True)
    email = serializers.EmailField()

    class Meta:
        model = User
        fields = ("fullname", "email", "password", "confirm_password")
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("Passwords don't match")
        return attrs

    def validate_email(self, value):
        normalized_email = User.objects.normalize_email(value)
        existing_user = User.objects.filter(email__iexact=normalized_email).first()
        if existing_user and not existing_user.is_invited:
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized_email

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        # Remove username if it exists since it's auto-generated
        validated_data.pop("username", None)
        email = validated_data.get("email")
        password = validated_data.get("password")
        fullname = validated_data.get("fullname")

        normalized_email = User.objects.normalize_email(email)
        invited_user = User.objects.filter(
            email__iexact=normalized_email, is_invited=True
        ).first()

        if invited_user:
            invited_user.fullname = fullname
            invited_user.set_password(password)
            invited_user.is_invited = False
            invited_user.save()

            # Ensure profile exists
            if not hasattr(invited_user, "profile"):
                Profile.objects.create(user=invited_user)
            return invited_user
        else:
            user = User.objects.create_user(**validated_data)
            return user


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login
    """

    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        if email and password:
            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError("Invalid credentials")
            if not user.is_active:
                raise serializers.ValidationError("User account is disabled")
            attrs["user"] = user
        else:
            raise serializers.ValidationError("Must include email and password")

        return attrs


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for user data
    """

    is_admin = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "fullname",
            "username",
            "is_verified",
            "is_admin",
            "image",
            "created_at",
        )
        read_only_fields = ("id", "username", "is_verified", "created_at")

    def get_is_admin(self, obj):
        """Get admin status for the user"""
        return obj.is_staff or obj.is_superuser

    def get_image(self, obj):
        """Get user's profile image URL"""
        try:
            profile = obj.profile
            if profile and profile.image:
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(profile.image.url)
                return profile.image.url
        except:
            # If profile doesn't exist, return None
            pass
        return None


class SectionImageSerializer(serializers.ModelSerializer):
    """Serializer for section images"""

    image = serializers.SerializerMethodField()

    class Meta:
        model = SectionImage
        fields = ("id", "image", "caption", "created_at")
        read_only_fields = ("id", "created_at")

    def get_image(self, obj):
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ProfileSerializer(serializers.ModelSerializer):
    """Updated profile serializer with dynamic sections"""

    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    fullname = serializers.CharField(source="user.fullname", read_only=True)
    id = serializers.UUIDField(source="user.id", read_only=True)
    is_admin = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = (
            "id",
            "username",
            "email",
            "fullname",
            "is_admin",
            "image",
            "bio",
            "location",
            "website",
            "joined_date",
            "gender",
            "date_of_birth",
            "sections",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_is_admin(self, obj):
        """Get admin status for the user"""
        return obj.user.is_staff or obj.user.is_superuser

    def get_image(self, obj):
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_sections(self, obj):
        """Get sections with their images - array order is the natural order"""
        if not obj.sections:
            return []

        # Add images to each section
        for section in obj.sections:
            section_id = section.get("id")
            if section_id:
                images = SectionImage.objects.filter(
                    profile=obj, section_id=section_id
                ).order_by("created_at")

                section["images"] = SectionImageSerializer(
                    images, many=True, context=self.context
                ).data

        return obj.sections  # Array order is the natural order!


class ProfileListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for profile lists (includes only first section to reduce data)
    """

    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    fullname = serializers.CharField(source="user.fullname", read_only=True)
    id = serializers.UUIDField(source="user.id", read_only=True)
    is_admin = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    first_section = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = (
            "id",
            "username",
            "email",
            "fullname",
            "is_admin",
            "image",
            "bio",
            "location",
            "website",
            "joined_date",
            "first_section",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_is_admin(self, obj):
        """Get admin status for the user"""
        return obj.user.is_staff or obj.user.is_superuser

    def get_image(self, obj):
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_first_section(self, obj):
        """Get the first section with its images if available"""
        if not obj.sections or len(obj.sections) == 0:
            return None

        first_section = obj.sections[0]
        section_id = first_section.get("id")

        if section_id:
            from .models import SectionImage

            images = SectionImage.objects.filter(
                profile=obj, section_id=section_id
            ).order_by("created_at")

            first_section["images"] = SectionImageSerializer(
                images, many=True, context=self.context
            ).data

        return first_section


class ProfileImageSerializer(serializers.ModelSerializer):
    """
    Serializer for profile image updates
    """

    class Meta:
        model = Profile
        fields = ("image",)

    def to_internal_value(self, data):
        # Handle captions when sent as JSON string in form data
        import json

        if "captions" in data and isinstance(data["captions"], str):
            try:
                data = data.copy()  # Make data mutable
                data["captions"] = json.loads(data["captions"])
            except (json.JSONDecodeError, ValueError):
                # If it's not valid JSON, treat it as a single caption
                data = data.copy()
                data["captions"] = [data["captions"]]

        return super().to_internal_value(data)

    def validate(self, data):
        images = data.get("images", [])
        captions = data.get("captions", [])

        if captions and len(captions) != len(images):
            raise serializers.ValidationError(
                "If captions are provided, the number of captions must match the number of images"
            )

        return data


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer for password change
    """

    old_password = serializers.CharField()
    new_password = serializers.CharField()
    confirm_password = serializers.CharField()

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("New passwords don't match")
        return attrs

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value


class ForgotPasswordSerializer(serializers.Serializer):
    """
    Serializer for forgot password
    """

    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    """
    Serializer for password reset
    """

    token = serializers.UUIDField()
    new_password = serializers.CharField()
    confirm_password = serializers.CharField()

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("Passwords don't match")
        return attrs

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value


# ── Family Tree Serializers ───────────────────────────────────────────────────

# User-facing relationship input types (what the person means in plain English)
RELATIONSHIP_INPUT_CHOICES = [
    ("father",   "Father"),
    ("mother",   "Mother"),
    ("son",      "Son"),
    ("daughter", "Daughter"),
    ("brother",  "Brother"),
    ("sister",   "Sister"),
    ("spouse",   "Spouse"),
]

GENDER_CHOICES = [
    ("male",           "Male"),
    ("female",         "Female"),
    ("other",          "Other"),
    ("prefer_not_to_say", "Prefer not to say"),
]


class FamilyMemberAddSerializer(serializers.Serializer):
    """Input serializer for adding a family member."""

    # What is this person to the subject (requester or anchor)?
    relationship_to_me = serializers.ChoiceField(choices=RELATIONSHIP_INPUT_CHOICES)
    fullname = serializers.CharField(max_length=255)

    # Required for living members; omitted for deceased placeholders
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)

    # Optional personal details
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    # Deceased placeholder — no email required, gender required
    is_deceased = serializers.BooleanField(required=False, default=False)
    gender = serializers.ChoiceField(choices=GENDER_CHOICES, required=False, allow_null=True)
    date_of_death = serializers.DateField(required=False, allow_null=True)

    # Anchor: add this person as a relative of anchor_user_id, not the requester
    anchor_user_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        is_deceased = attrs.get("is_deceased", False)
        if not is_deceased and not attrs.get("email"):
            raise serializers.ValidationError(
                {"email": "Email is required when adding a living family member."}
            )
        if is_deceased and not attrs.get("gender"):
            raise serializers.ValidationError(
                {"gender": "Gender is required when adding a deceased family member."}
            )
        return attrs


class FamilyRelationshipRequestSerializer(serializers.ModelSerializer):
    """Serializer for incoming pending relationship requests."""

    # added_by is always the initiator in the new model (canonical ordering means
    # user/relative fields don't identify initiator vs. recipient).
    from_user_id = serializers.SerializerMethodField()
    from_user_fullname = serializers.SerializerMethodField()
    relationship_type = serializers.CharField(read_only=True)

    class Meta:
        model = FamilyRelationship
        fields = (
            "id",
            "from_user_id",
            "from_user_fullname",
            "relationship_type",
            "status",
            "created_at",
        )

    def get_from_user_id(self, obj):
        return str(obj.added_by_id) if obj.added_by_id else str(obj.user_id)

    def get_from_user_fullname(self, obj):
        if obj.added_by:
            return obj.added_by.fullname
        return obj.user.fullname


class FamilySentRequestSerializer(serializers.ModelSerializer):
    """Serializer for outgoing pending relationship requests (sent by the current user)."""

    to_user_id = serializers.SerializerMethodField()
    to_user_fullname = serializers.SerializerMethodField()
    to_user_email = serializers.SerializerMethodField()
    relationship_type = serializers.CharField(read_only=True)

    class Meta:
        model = FamilyRelationship
        fields = (
            "id",
            "to_user_id",
            "to_user_fullname",
            "to_user_email",
            "relationship_type",
            "status",
            "created_at",
        )

    def _get_to_user(self, obj):
        if obj.added_by_id and str(obj.user_id) == str(obj.added_by_id):
            return obj.relative
        return obj.user

    def get_to_user_id(self, obj):
        return str(self._get_to_user(obj).id)

    def get_to_user_fullname(self, obj):
        return self._get_to_user(obj).fullname

    def get_to_user_email(self, obj):
        to_user = self._get_to_user(obj)
        if getattr(to_user, "is_invited", False) or getattr(to_user, "is_placeholder", False):
            return None
        return to_user.email


class FamilyRequestRespondSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=[("accept", "Accept"), ("reject", "Reject")])


class FamilyTreeMemberSerializer(serializers.ModelSerializer):
    """
    Serializes a User node for the family tree.
    Internal placeholder emails are hidden (returned as null).
    """

    fullname = serializers.CharField()
    # email is intentionally nullable — placeholder/deceased users have internal emails
    email = serializers.SerializerMethodField()
    username = serializers.CharField(read_only=True)
    gender = serializers.SerializerMethodField()
    date_of_birth = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    is_deceased = serializers.SerializerMethodField()
    is_placeholder = serializers.SerializerMethodField()
    date_of_death = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "fullname",
            "email",
            "username",
            "gender",
            "date_of_birth",
            "image",
            "is_deceased",
            "is_placeholder",
            "date_of_death",
        )

    def get_email(self, obj):
        # Don't expose internal placeholder / deceased emails
        if obj.is_invited or obj.is_deceased:
            return None
        return obj.email

    def get_gender(self, obj):
        try:
            return obj.profile.gender
        except Exception:
            return "prefer_not_to_say"

    def get_date_of_birth(self, obj):
        try:
            return obj.profile.date_of_birth
        except Exception:
            return None

    def get_is_deceased(self, obj):
        if obj.is_deceased:
            return True
        try:
            return obj.profile.is_deceased
        except Exception:
            return False

    def get_is_placeholder(self, obj):
        """True for invited (not-yet-registered) and deceased placeholder users."""
        return obj.is_invited or obj.is_deceased

    def get_date_of_death(self, obj):
        try:
            return obj.profile.date_of_death
        except Exception:
            return None

    def get_image(self, obj):
        try:
            profile = obj.profile
            if profile and profile.image:
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(profile.image.url)
                return profile.image.url
        except Exception:
            pass
        return None


class FamilyTreeEdgeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    source = serializers.UUIDField()
    target = serializers.UUIDField()
    relationship_type = serializers.CharField()
    label_from_source = serializers.CharField()
    label_for_viewer = serializers.CharField(allow_null=True)
    added_by_id = serializers.CharField(allow_null=True)
    added_by_name = serializers.CharField(allow_null=True)
    is_editable = serializers.BooleanField(default=False)


class FamilyTreeResponseSerializer(serializers.Serializer):
    nodes = FamilyTreeMemberSerializer(many=True)
    edges = FamilyTreeEdgeSerializer(many=True)


class FamilyRelationshipUpdateSerializer(serializers.Serializer):
    """Input for editing an existing edge — expressed in the same user-friendly vocabulary."""
    relationship_to_me = serializers.ChoiceField(choices=RELATIONSHIP_INPUT_CHOICES)


class FamilyRelationshipSuggestionSerializer(serializers.ModelSerializer):
    """Serializer for system-generated relationship suggestions."""

    suggested_person = FamilyTreeMemberSerializer(read_only=True)
    edge_type = serializers.CharField(read_only=True)
    role = serializers.CharField(allow_null=True, read_only=True)
    reason = serializers.CharField(read_only=True)

    class Meta:
        model = FamilyRelationshipSuggestion
        fields = ("id", "suggested_person", "edge_type", "role", "reason", "created_at")


class MarkDeceasedSerializer(serializers.Serializer):
    """Input for marking a person as deceased or living."""
    is_deceased = serializers.BooleanField()
    date_of_death = serializers.DateField(required=False, allow_null=True)

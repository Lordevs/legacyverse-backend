from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User, Profile, SectionImage, FamilyRelationship


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


class FamilyMemberAddSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    fullname = serializers.CharField(max_length=255)
    relationship_type = serializers.ChoiceField(
        choices=FamilyRelationship.RELATIONSHIP_CHOICES
    )
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    # Deceased placeholder fields
    is_deceased = serializers.BooleanField(required=False, default=False)
    gender = serializers.ChoiceField(
        choices=[("male", "Male"), ("female", "Female"), ("other", "Other"), ("prefer_not_to_say", "Prefer not to say")],
        required=False,
        allow_null=True,
    )
    date_of_death = serializers.DateField(required=False, allow_null=True)
    # Anchor: if set, the relationship is created relative to this user, not the requester
    anchor_user_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        is_deceased = attrs.get("is_deceased", False)
        email = attrs.get("email")

        if not is_deceased and not email:
            raise serializers.ValidationError(
                {"email": "Email is required when adding a living family member."}
            )
        if is_deceased and not attrs.get("gender"):
            raise serializers.ValidationError(
                {"gender": "Gender is required when adding a deceased family member."}
            )
        return attrs


class FamilyRelationshipRequestSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    user_fullname = serializers.CharField(source="user.fullname", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    relationship_type = serializers.CharField(read_only=True)

    class Meta:
        model = FamilyRelationship
        fields = (
            "id",
            "user_id",
            "user_fullname",
            "user_email",
            "relationship_type",
            "status",
            "created_at",
        )


class FamilyRequestRespondSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=[("accept", "Accept"), ("reject", "Reject")]
    )


class FamilyTreeMemberSerializer(serializers.ModelSerializer):
    fullname = serializers.CharField()
    email = serializers.EmailField()
    username = serializers.CharField(read_only=True)
    gender = serializers.SerializerMethodField()
    date_of_birth = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    is_deceased = serializers.SerializerMethodField()
    date_of_death = serializers.SerializerMethodField()
    # is_initiator and initiator_name are injected dynamically in the view

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
            "date_of_death",
        )

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
        """Deceased if User.is_deceased (placeholder) OR Profile.is_deceased (registered)"""
        if obj.is_deceased:
            return True
        try:
            return obj.profile.is_deceased
        except Exception:
            return False

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
    relationship = serializers.CharField()
    is_editable = serializers.BooleanField(required=False, default=False)


class FamilyTreeResponseSerializer(serializers.Serializer):
    nodes = FamilyTreeMemberSerializer(many=True)
    edges = FamilyTreeEdgeSerializer(many=True)


class FamilyRelationshipUpdateSerializer(serializers.Serializer):
    relationship_type = serializers.ChoiceField(
        choices=FamilyRelationship.RELATIONSHIP_CHOICES
    )

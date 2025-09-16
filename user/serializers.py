from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User, Profile, PasswordResetToken


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration
    """
    confirm_password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ('fullname', 'email', 'password', 'confirm_password')
        extra_kwargs = {
            'password': {'write_only': True},
        }
    
    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value
    
    def create(self, validated_data):
        validated_data.pop('confirm_password')
        # Remove username if it exists since it's auto-generated
        validated_data.pop('username', None)
        user = User.objects.create_user(**validated_data)
        # Profile will be created automatically by signals
        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login
    """
    email = serializers.EmailField()
    password = serializers.CharField()
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError('Invalid credentials')
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled')
            attrs['user'] = user
        else:
            raise serializers.ValidationError('Must include email and password')
        
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for user data
    """
    class Meta:
        model = User
        fields = ('id', 'email', 'fullname', 'username', 'is_verified', 'created_at')
        read_only_fields = ('id', 'username', 'is_verified', 'created_at')


class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile
    """
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    fullname = serializers.CharField(source='user.fullname', read_only=True)
    
    class Meta:
        model = Profile
        fields = (
            'username', 'email', 'fullname', 'image', 'bio', 'location', 
            'website', 'education', 'hobbies', 'early_childhood', 
            'created_at', 'updated_at'
        )
        read_only_fields = ('created_at', 'updated_at')
    
    def update(self, instance, validated_data):
        # Update user fullname if provided
        if 'user' in validated_data:
            user_data = validated_data.pop('user')
            if 'fullname' in user_data:
                instance.user.fullname = user_data['fullname']
                instance.user.save()
        
        return super().update(instance, validated_data)


class ProfileImageSerializer(serializers.ModelSerializer):
    """
    Serializer for profile image updates
    """
    class Meta:
        model = Profile
        fields = ('image',)


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer for password change
    """
    old_password = serializers.CharField()
    new_password = serializers.CharField()
    confirm_password = serializers.CharField()
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
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
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def validate_new_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

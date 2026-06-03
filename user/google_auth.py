
from rest_framework import status, serializers as rf_serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
import google.auth.transport.requests
import google.oauth2.id_token
from urllib.parse import urlencode
from django.http import JsonResponse
import requests
from drf_spectacular.utils import extend_schema
from .serializers import UserSerializer as _GUserSerializer


# ── Inline response serializers ───────────────────────────────────────────────
class _GoogleTokenResponseSerializer(rf_serializers.Serializer):
    refresh = rf_serializers.CharField()
    access = rf_serializers.CharField()
    user = _GUserSerializer()
    created = rf_serializers.BooleanField(
        help_text='True if this is a newly registered account'
    )


class _GoogleAuthRequestSerializer(rf_serializers.Serializer):
    id_token = rf_serializers.CharField(
        help_text='Google OAuth2 id_token obtained from the frontend'
    )


class _GoogleUrlResponseSerializer(rf_serializers.Serializer):
    auth_url = rf_serializers.CharField()


class _GErrorSerializer(rf_serializers.Serializer):
    error = rf_serializers.CharField()
# ─────────────────────────────────────────────────────────────────────────────


User = get_user_model()


def google_authenticate_and_respond(id_token_str):
    """
    Helper function to verify Google id_token, create/authenticate user, and return JWT tokens.
    """
    try:
        idinfo = google.oauth2.id_token.verify_oauth2_token(
            id_token_str,
            google.auth.transport.requests.Request(),
            settings.GOOGLE_OAUTH_CLIENT_ID
        )
        email = idinfo.get('email')
        fullname = idinfo.get('name')
        if not email:
            return Response({'error': 'Google account has no email.'}, status=status.HTTP_400_BAD_REQUEST)
        user, created = User.objects.get_or_create(email=email, defaults={'fullname': fullname, 'is_verified': True})
        if created:
            user.is_verified = True
            user.save()
        refresh = RefreshToken.for_user(user)
        from .serializers import UserSerializer
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data,
            'created': created
        }, status=status.HTTP_200_OK)
    except ValueError:
        return Response({'error': 'Invalid Google token.'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Auth"],
    request=_GoogleAuthRequestSerializer,
    responses={200: _GoogleTokenResponseSerializer, 400: _GErrorSerializer},
    summary="Google OAuth2 – verify id_token and return JWT tokens (SPA/mobile flow)",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def google_auth_view(request):
    """
    Google OAuth2 login/signup endpoint. Accepts id_token from frontend, verifies with Google,
    creates or authenticates user, and returns JWT tokens.
    """
    id_token_str = request.data.get('id_token')
    if not id_token_str:
        return Response({'error': 'id_token is required.'}, status=status.HTTP_400_BAD_REQUEST)
    return google_authenticate_and_respond(id_token_str)


@extend_schema(
    tags=["Auth"],
    responses={200: _GoogleUrlResponseSerializer},
    summary="Google OAuth2 – get the authorization URL to redirect the user to",
)
@api_view(['GET'])
@permission_classes([AllowAny])
def google_oauth_url(request):
    """
    Returns the Google OAuth2 authorization URL for user to start login/signup.
    """
    params = {
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'offline',
        'prompt': 'consent',
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return JsonResponse({'auth_url': url})


@extend_schema(
    tags=["Auth"],
    responses={200: _GoogleTokenResponseSerializer, 400: _GErrorSerializer},
    summary="Google OAuth2 callback – exchange code for JWT tokens (server-side flow)",
)
@api_view(['GET'])
@permission_classes([AllowAny])
def google_oauth_callback(request):
    """
    Handles Google redirect, exchanges code for id_token, and logs in/registers user.
    """
    code = request.GET.get('code')
    if not code:
        return Response({'error': 'Missing code in callback.'}, status=status.HTTP_400_BAD_REQUEST)
    data = {
        'code': code,
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }
    token_url = 'https://oauth2.googleapis.com/token'
    token_resp = requests.post(token_url, data=data)
    if not token_resp.ok:
        return Response({'error': 'Failed to exchange code for token.', 'details': token_resp.text}, status=token_resp.status_code)
    token_data = token_resp.json()
    id_token_str = token_data.get('id_token')
    if not id_token_str:
        return Response({'error': 'No id_token in response.'}, status=status.HTTP_400_BAD_REQUEST)
    return google_authenticate_and_respond(id_token_str)


from rest_framework import status
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

User = get_user_model()

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


@api_view(['GET'])
@permission_classes([AllowAny])
def google_oauth_callback(request):
    """
    Handles Google's redirect, exchanges code for id_token, and logs in/registers user.
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
    # Use helper directly
    return google_authenticate_and_respond(id_token_str)

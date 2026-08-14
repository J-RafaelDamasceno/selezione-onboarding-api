# backend/api/v1/auth.py
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.conf import settings
from rest_framework.permissions import AllowAny

COOKIE_NAME = "refresh_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 dias, igual ao SIMPLE_JWT

# Em dev (http://localhost) o navegador recusa cookies "Secure".
# Em produção (Render, HTTPS) precisa ser Secure + SameSite=None pro cross-domain funcionar.
COOKIE_SECURE = not settings.DEBUG
COOKIE_SAMESITE = "None" if not settings.DEBUG else "Lax"


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, username=email, password=password)

        if user is not None:
            refresh = RefreshToken.for_user(user)
            response = Response({
                "access": str(refresh.access_token),
                "username": user.username,
                "user_name": user.get_full_name(),
            })
            response.set_cookie(
                key=COOKIE_NAME,
                value=str(refresh),
                httponly=True,
                secure=COOKIE_SECURE,
                samesite=COOKIE_SAMESITE,
                max_age=COOKIE_MAX_AGE,
                path="/api/v1/auth/",
            )
            return response
        else:
            return Response(
                {"detail": "Credenciais inválidas"},
                status=status.HTTP_401_UNAUTHORIZED
            )


class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        raw_token = request.COOKIES.get(COOKIE_NAME)
        if not raw_token:
            return Response({"detail": "Sem sessão ativa"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            refresh = RefreshToken(raw_token)
            new_access = str(refresh.access_token)
        except Exception:
            return Response({"detail": "Sessão expirada"}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({"access": new_access})


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        raw_token = request.COOKIES.get(COOKIE_NAME)
        if raw_token:
            try:
                refresh = RefreshToken(raw_token)
                refresh.blacklist()
            except Exception:
                # Token já inválido/expirado ou malformado — segue o logout normalmente
                pass

        response = Response({"detail": "Logout realizado"})
        response.delete_cookie(COOKIE_NAME, path="/api/v1/auth/")
        return response
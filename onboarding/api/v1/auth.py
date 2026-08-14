# backend/api/v1/auth.py
import time
import logging
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny

logger = logging.getLogger("login_debug")

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        t0 = time.perf_counter()

        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, username=email, password=password)
        t1 = time.perf_counter()
        logger.warning(f"[LOGIN] authenticate() levou {t1 - t0:.3f}s")

        if user is not None:
            refresh = RefreshToken.for_user(user)
            t2 = time.perf_counter()
            logger.warning(f"[LOGIN] geração do token levou {t2 - t1:.3f}s")
            logger.warning(f"[LOGIN] TOTAL: {t2 - t0:.3f}s")

            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "username": user.username,
                "user_name": user.get_full_name()
            })
        else:
            t2 = time.perf_counter()
            logger.warning(f"[LOGIN] TOTAL (falhou): {t2 - t0:.3f}s")
            return Response(
                {"detail": "Credenciais inválidas"},
                status=status.HTTP_401_UNAUTHORIZED
            )
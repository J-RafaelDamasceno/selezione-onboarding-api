# backend/api/v1/auth.py
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny  # 👈 importante

class LoginView(APIView):
    permission_classes = [AllowAny]  # 👈 permite acessar sem estar logado

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        # autentica usando email
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "username": user.username,         # para mostrar "Olá, username"
                "user_name": user.get_full_name()  # opcional, se tiver nome completo
            })
        else:
            return Response(
                {"detail": "Credenciais inválidas"},
                status=status.HTTP_401_UNAUTHORIZED
            )
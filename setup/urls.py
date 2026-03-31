from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from onboarding.api.v1.views import FormSubmissionViewSet
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import home
from onboarding.api.v1.auth import LoginView

router = DefaultRouter()
router.register(r'onboarding', FormSubmissionViewSet, basename='onboarding')

urlpatterns = [
    path('', home), 
    path('admin/', admin.site.urls),

    path('api/token/', TokenObtainPairView.as_view()),
    path('api/token/refresh/', TokenRefreshView.as_view()),
    path('api/v1/auth/login/', LoginView.as_view(), name='login'),

    path('api/', include(router.urls)),
]

# 👇 ADICIONE ESTAS LINHAS NO FINAL
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
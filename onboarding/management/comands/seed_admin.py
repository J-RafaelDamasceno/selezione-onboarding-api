from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        User = get_user_model()

        if not User.objects.filter(email="miguel@selezioneinvest.com.br").exists():
            User.objects.create_superuser(
                username="Miguel Damasceno",
                email="miguel@selezioneinvest.com.br",
                password="Miguel.2biselezione"
            )
            self.stdout.write("Superuser criado")
        else:
            self.stdout.write("Superuser já existe")
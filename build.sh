#!/usr/bin/env bash
set -o errexit

# Instala dependências do sistema para WeasyPrint
apt-get install -y \
  libpango-1.0-0 \
  libpangocairo-1.0-0 \
  libcairo2 \
  libffi-dev \
  libgdk-pixbuf2.0-0 \
  shared-mime-info \
  fonts-liberation \
  fonts-dejavu-core

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
```

No painel do Render, em **Settings → Build Command**, coloque:
```
./build.sh
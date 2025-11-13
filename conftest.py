import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "application.settings")

import django
from django.core.management import call_command

django.setup()
call_command("migrate", run_syncdb=True, verbosity=0)

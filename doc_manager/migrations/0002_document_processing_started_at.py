from __future__ import annotations

from django.db import migrations, models


def set_processing_started(apps, schema_editor):
    Document = apps.get_model("doc_manager", "Document")
    for document in Document.objects.filter(processing_started_at__isnull=True):
        document.processing_started_at = document.created_at
        document.save(update_fields=["processing_started_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("doc_manager", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="processing_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(set_processing_started, migrations.RunPython.noop),
    ]

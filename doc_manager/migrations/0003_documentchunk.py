from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("doc_manager", "0002_document_processing_started_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chunk_index", models.PositiveIntegerField()),
                ("text", models.TextField()),
                ("metadata", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(on_delete=models.CASCADE, related_name="chunks", to="doc_manager.document"),
                ),
            ],
            options={
                "ordering": ["chunk_index"],
                "unique_together": {("document", "chunk_index")},
            },
        ),
    ]

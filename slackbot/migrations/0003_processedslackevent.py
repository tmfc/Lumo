from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("slackbot", "0002_alter_conversationsummary_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessedSlackEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.CharField(max_length=100, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]

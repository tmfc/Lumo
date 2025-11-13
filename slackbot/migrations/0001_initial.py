from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ConversationSummary",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_type", models.CharField(choices=[("channel", "Channel"), ("thread", "Thread")], max_length=20)),
                ("target_id", models.CharField(max_length=255)),
                ("summary_text", models.TextField()),
                ("generated_for", models.DateField(blank=True, null=True)),
                ("model_used", models.CharField(default="", max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="conversationsummary",
            index=models.Index(fields=["target_type", "target_id"], name="slackbot_c_target__3a780b_idx"),
        ),
    ]

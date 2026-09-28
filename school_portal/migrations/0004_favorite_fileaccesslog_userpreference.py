from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("school_portal", "0003_ousharemapping_smb_credentials"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("materials_view", models.CharField(default="tiles", max_length=20)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Favorite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("root_index", models.PositiveIntegerField()),
                ("relative_path", models.CharField(max_length=1000)),
                ("is_directory", models.BooleanField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="material_favorites", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-is_directory", "relative_path"]},
        ),
        migrations.CreateModel(
            name="FileAccessLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("root_index", models.PositiveIntegerField(blank=True, null=True)),
                ("relative_path", models.CharField(max_length=1000)),
                ("extension", models.CharField(blank=True, max_length=20)),
                ("action", models.CharField(choices=[("open", "Open"), ("denied", "Denied")], max_length=10)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("client_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-timestamp"]},
        ),
        migrations.AddConstraint(model_name="favorite", constraint=models.UniqueConstraint(fields=("user", "root_index", "relative_path"), name="unique_user_material_favorite")),
        migrations.AddIndex(model_name="fileaccesslog", index=models.Index(fields=["timestamp"], name="school_port_timestamp_9df11d_idx")),
        migrations.AddIndex(model_name="fileaccesslog", index=models.Index(fields=["action", "timestamp"], name="school_port_action_2e328d_idx")),
    ]

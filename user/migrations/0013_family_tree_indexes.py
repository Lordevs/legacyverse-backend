"""
Migration 0013: Add indexes for family tree hot query paths.
Separated from 0012 because PostgreSQL cannot CREATE INDEX in the same
transaction as a RunPython data migration (pending trigger events error).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0012_refactor_family_tree"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="familyrelationship",
            index=models.Index(fields=["user", "status"], name="family_rel_user_status_idx"),
        ),
        migrations.AddIndex(
            model_name="familyrelationship",
            index=models.Index(fields=["relative", "status"], name="family_rel_rel_status_idx"),
        ),
        migrations.AddIndex(
            model_name="familyrelationship",
            index=models.Index(fields=["added_by"], name="family_rel_added_by_idx"),
        ),
        migrations.AddIndex(
            model_name="familyrelationship",
            index=models.Index(fields=["status"], name="family_rel_status_idx"),
        ),
    ]

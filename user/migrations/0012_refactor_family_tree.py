"""
Migration 0012: Refactor family tree to 3 structural edge types.

Schema changes:
  - FamilyRelationship.relationship_type choices → parent_child / sibling / spouse
  - FamilyRelationship.status choices → pending / accepted  (removes 'rejected')
  - New composite indexes on FamilyRelationship
  - New FamilyRelationshipSuggestion model

Data migration:
  - Delete all rejected relationship records
  - Remap old directional types to structural types:
      father/mother → parent_child  (swap user/relative so user=parent, relative=child)
      son/daughter  → parent_child  (direction already correct)
      spouse        → spouse        (apply canonical ordering: user.id < relative.id)
  - Deduplicate any pairs that end up with the same (user_id, relative_id) after remapping
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def remap_relationship_types(apps, schema_editor):
    FamilyRelationship = apps.get_model("user", "FamilyRelationship")

    # 1. Delete all rejected records — they are permanently gone by design.
    FamilyRelationship.objects.filter(status="rejected").delete()

    # 2. Collect all remaining records for processing in Python memory.
    records = list(
        FamilyRelationship.objects.all().values(
            "id", "user_id", "relative_id", "relationship_type", "status", "added_by_id"
        )
    )

    # 3. Delete everything so we can re-insert with corrected directions.
    FamilyRelationship.objects.all().delete()

    # 4. Re-insert with canonical form, skipping duplicates that arise from remapping.
    seen = set()  # (user_id_str, relative_id_str) pairs already committed
    to_create = []

    for rec in records:
        old_type = rec["relationship_type"]
        uid = str(rec["user_id"])
        rid = str(rec["relative_id"])

        if old_type in ("father", "mother"):
            # Semantics: user=A added relative=B as A's father/mother → B is the parent, A is the child.
            # New direction: user=parent(B), relative=child(A)
            new_uid, new_rid = rid, uid
            new_type = "parent_child"

        elif old_type in ("son", "daughter"):
            # Semantics: user=A added relative=B as A's son/daughter → A is the parent, B is the child.
            # Direction already correct.
            new_uid, new_rid = uid, rid
            new_type = "parent_child"

        elif old_type == "spouse":
            # Undirected — enforce canonical ordering.
            if uid > rid:
                new_uid, new_rid = rid, uid
            else:
                new_uid, new_rid = uid, rid
            new_type = "spouse"

        else:
            # Unknown / already-migrated type — skip.
            continue

        key = (new_uid, new_rid)
        if key in seen:
            # This canonical pair already exists (e.g. both (A→B, father) and (B→A, son)
            # represented the same relationship). Keep the first, drop this duplicate.
            continue

        seen.add(key)
        to_create.append(
            FamilyRelationship(
                user_id=new_uid,
                relative_id=new_rid,
                relationship_type=new_type,
                status=rec["status"],
                added_by_id=rec["added_by_id"],
            )
        )

    if to_create:
        FamilyRelationship.objects.bulk_create(to_create)


def reverse_remap(apps, schema_editor):
    # Reversal is lossy (original IDs and exact types are gone).
    # We leave the data as-is; the migration cannot be cleanly reversed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0011_familyrelationship_added_by"),
    ]

    operations = [
        # ── 1. Update relationship_type choices (Python-level; DB stores a varchar) ──
        migrations.AlterField(
            model_name="familyrelationship",
            name="relationship_type",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("parent_child", "Parent-Child"),
                    ("sibling", "Sibling"),
                    ("spouse", "Spouse"),
                ],
            ),
        ),
        # ── 2. Update status choices (removes 'rejected') ────────────────────────────
        migrations.AlterField(
            model_name="familyrelationship",
            name="status",
            field=models.CharField(
                max_length=20,
                default="pending",
                choices=[
                    ("pending", "Pending"),
                    ("accepted", "Accepted"),
                ],
            ),
        ),
        # ── 3. Data migration ─────────────────────────────────────────────────────────
        migrations.RunPython(remap_relationship_types, reverse_remap),
        # ── 4. FamilyRelationshipSuggestion model ─────────────────────────────────────
        migrations.CreateModel(
            name="FamilyRelationshipSuggestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "suggested_to",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="family_suggestions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "suggested_person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="suggested_in_family",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "edge_type",
                    models.CharField(
                        max_length=20,
                        choices=[
                            ("parent_child", "Parent-Child"),
                            ("sibling", "Sibling"),
                            ("spouse", "Spouse"),
                        ],
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        max_length=20,
                        choices=[("as_parent", "As Parent"), ("as_child", "As Child")],
                        null=True,
                        blank=True,
                    ),
                ),
                ("reason", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        max_length=20,
                        default="pending",
                        choices=[("pending", "Pending"), ("dismissed", "Dismissed")],
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["suggested_to", "status"], name="family_sugg_to_status_idx"),
                ],
            },
        ),
        migrations.AlterUniqueTogether(
            name="familyrelationshipsuggestion",
            unique_together={("suggested_to", "suggested_person")},
        ),
    ]

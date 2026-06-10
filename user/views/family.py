"""
Family Tree views.

Relationship model uses three structural edge types:
  parent_child  — user=parent, relative=child (directed)
  sibling       — undirected, canonical user.id < relative.id
  spouse        — undirected, canonical user.id < relative.id

Human labels (Father/Brother/Husband/etc.) are derived at read time from
edge type + viewer position + gender. They are never stored.
"""
import uuid as uuid_lib
from django.db import IntegrityError, models as db_models, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..email_utils import send_family_invitation_email
from ..models import FamilyRelationship, FamilyRelationshipSuggestion, Profile, User
from ..serializers import (
    FamilyMemberAddSerializer,
    FamilyRelationshipRequestSerializer,
    FamilySentRequestSerializer,
    FamilyRelationshipUpdateSerializer,
    FamilyRequestRespondSerializer,
    FamilyRelationshipSuggestionSerializer,
    FamilyTreeMemberSerializer,
    FamilyTreeResponseSerializer,
    MarkDeceasedSerializer,
)
from ._family_helpers import (
    GENDER_FROM_RELATIONSHIP,
    RELATIONSHIP_INPUT_MAP,
    build_edge_direction,
    dismiss_stale_suggestions,
    generate_suggestions_for_new_edge,
    get_all_tree_member_ids,
    get_profile_gender,
    get_relationship_label,
    get_tree_data,
    _get_descendants,
)
from ._serializers import _ErrorSerializer, _MessageSerializer


# ── Helpers ───────────────────────────────────────────────────────────────────

def _existing_edge(user_a, user_b):
    """Return any relationship record between user_a and user_b (either direction)."""
    return FamilyRelationship.objects.filter(
        db_models.Q(user=user_a, relative=user_b)
        | db_models.Q(user=user_b, relative=user_a)
    ).first()


def _has_parent_of_gender(subject, gender):
    """
    Return True if subject already has an accepted parent with the given gender.
    Used to enforce the one-father / one-mother constraint.
    """
    parent_edges = FamilyRelationship.objects.filter(
        relative=subject,
        relationship_type="parent_child",
        status="accepted",
    ).select_related("user__profile")
    for edge in parent_edges:
        if get_profile_gender(edge.user) == gender:
            return True
    return False


def _has_spouse(subject):
    """Return True if subject already has an accepted spouse."""
    return FamilyRelationship.objects.filter(
        db_models.Q(user=subject) | db_models.Q(relative=subject),
        relationship_type="spouse",
        status="accepted",
    ).exists()


def _cleanup_orphaned_placeholder(user):
    """Delete a placeholder user that has no remaining relationships."""
    if not (user.is_invited or user.is_deceased):
        return
    has_edges = FamilyRelationship.objects.filter(
        db_models.Q(user=user) | db_models.Q(relative=user)
    ).exists()
    if not has_edges:
        user.delete()


def _infer_placeholder_gender(relationship_to_me, subject_gender, gender_override):
    """Return the gender to set on a newly created placeholder."""
    if gender_override:
        return gender_override
    direct = GENDER_FROM_RELATIONSHIP.get(relationship_to_me)
    if direct:
        return direct
    # For spouse: infer opposite gender
    if relationship_to_me == "spouse":
        if subject_gender == "male":
            return "female"
        if subject_gender == "female":
            return "male"
    return None


# ── Views ─────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Family Tree"],
    request=FamilyMemberAddSerializer,
    responses={201: _MessageSerializer, 400: _ErrorSerializer},
    summary="Add an immediate family member",
    description=(
        "Add a family member using a natural relationship type "
        "(father/mother/son/daughter/brother/sister/spouse). "
        "For living members an invitation email is sent and a request is created. "
        "For deceased placeholders the relationship is accepted immediately."
    ),
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def add_family_member(request):
    serializer = FamilyMemberAddSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    relationship_to_me = data["relationship_to_me"]
    fullname = data["fullname"]
    is_deceased = data.get("is_deceased", False)
    gender_override = data.get("gender")
    date_of_birth = data.get("date_of_birth")
    date_of_death = data.get("date_of_death")
    anchor_user_id = data.get("anchor_user_id")
    email = (data.get("email") or "").strip().lower() or None

    mapping = RELATIONSHIP_INPUT_MAP[relationship_to_me]
    edge_type = mapping["edge_type"]
    requester_role = mapping["requester_role"]

    # ── Anchor resolution ──────────────────────────────────────────────────────
    # When anchor_user_id is supplied the new person is added as a relative of the
    # anchor, not the requester. The requester must already be in the anchor's tree.
    subject = request.user  # The person the new relative is linked to
    if anchor_user_id:
        try:
            anchor = User.objects.get(id=anchor_user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "The selected family member does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )
        tree_ids = get_all_tree_member_ids(request.user.id)
        if anchor.id not in tree_ids:
            return Response(
                {"error": "You can only add relatives to people in your own family tree."},
                status=status.HTTP_403_FORBIDDEN,
            )
        subject = anchor

    subject_gender = get_profile_gender(subject)

    # ── Self-check ─────────────────────────────────────────────────────────────
    if email and email == subject.email.lower():
        return Response(
            {"error": "You cannot add a person to themselves."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Deceased placeholder flow ──────────────────────────────────────────────
    if is_deceased:
        inferred_gender = _infer_placeholder_gender(
            relationship_to_me, subject_gender, gender_override
        )
        try:
            with transaction.atomic():
                internal_email = f"deceased-{uuid_lib.uuid4().hex}@legacyverse.internal"
                relative = User.objects.create(
                    email=internal_email,
                    fullname=fullname,
                    is_invited=True,
                    is_deceased=True,
                    is_active=False,
                )
                relative.set_unusable_password()
                relative.save()

                profile, _ = Profile.objects.get_or_create(user=relative)
                if inferred_gender:
                    profile.gender = inferred_gender
                if date_of_birth:
                    profile.date_of_birth = date_of_birth
                if date_of_death:
                    profile.date_of_death = date_of_death
                profile.is_deceased = True
                profile.save()

                # Determine edge direction and create accepted edge immediately
                parent_or_a, child_or_b = build_edge_direction(
                    subject, relative, edge_type, requester_role
                )
                edge = FamilyRelationship.objects.create(
                    user=parent_or_a,
                    relative=child_or_b,
                    relationship_type=edge_type,
                    status="accepted",
                    added_by=request.user,
                )
        except IntegrityError:
            return Response(
                {"error": "This relationship already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        generate_suggestions_for_new_edge(edge)
        return Response(
            {"message": f"Deceased family member '{fullname}' added to the tree."},
            status=status.HTTP_201_CREATED,
        )

    # ── Living member flow ─────────────────────────────────────────────────────
    if not email:
        return Response(
            {"error": "Email is required for living family members."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_email = User.objects.normalize_email(email)

    if normalized_email.lower() == request.user.email.lower():
        return Response(
            {"error": "You cannot add yourself as a family member."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    relative = User.objects.filter(email__iexact=normalized_email).first()
    is_new_user = relative is None

    # ── Validate before any writes ─────────────────────────────────────────────
    if relative:
        # Check existing edge in either direction
        existing = _existing_edge(subject, relative)
        if existing:
            return Response(
                {"error": "A relationship between these people already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Cycle detection — only relevant for parent_child
        if edge_type == "parent_child":
            if requester_role == "child":
                # relative becomes parent of subject → check relative is not a descendant of subject
                if relative.id in _get_descendants(subject.id):
                    return Response(
                        {"error": "This person is already a descendant and cannot be added as a parent."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                # relative becomes child of subject → check subject is not a descendant of relative
                if subject.id in _get_descendants(relative.id):
                    return Response(
                        {"error": "This person is already an ancestor and cannot be added as a child."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Duplicate parent check
        if relationship_to_me in ("father", "mother"):
            gender_to_check = GENDER_FROM_RELATIONSHIP[relationship_to_me]
            if _has_parent_of_gender(subject, gender_to_check):
                label = relationship_to_me
                return Response(
                    {"error": f"{subject.fullname} already has a {label} in the family tree."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

    # ── Create placeholder if new user ─────────────────────────────────────────
    inferred_gender = _infer_placeholder_gender(
        relationship_to_me, subject_gender, gender_override
    )

    try:
        with transaction.atomic():
            if is_new_user:
                relative = User.objects.create(
                    email=normalized_email,
                    fullname=fullname,
                    is_invited=True,
                    is_active=True,
                )
                relative.set_unusable_password()
                relative.save()

                profile, _ = Profile.objects.get_or_create(user=relative)
                if inferred_gender:
                    profile.gender = inferred_gender
                if date_of_birth:
                    profile.date_of_birth = date_of_birth
                profile.save()

            parent_or_a, child_or_b = build_edge_direction(
                subject, relative, edge_type, requester_role
            )

            rel_status = "accepted" if relative.is_invited else "pending"
            edge = FamilyRelationship.objects.create(
                user=parent_or_a,
                relative=child_or_b,
                relationship_type=edge_type,
                status=rel_status,
                added_by=request.user,
            )
    except IntegrityError:
        return Response(
            {"error": "This relationship already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Send invitation email (outside transaction — network call)
    if not relative.is_deceased:
        try:
            send_family_invitation_email(
                sender=request.user,
                receiver_email=normalized_email,
                receiver_name=fullname,
                relationship_type=relationship_to_me.capitalize(),
                is_new_user=is_new_user,
            )
        except Exception:
            pass  # Email failure should not fail the request

    if edge.status == "accepted":
        generate_suggestions_for_new_edge(edge)
        dismiss_stale_suggestions(subject, relative)

    if is_new_user:
        msg = "Family member added and invitation sent."
    elif edge.status == "accepted":
        msg = "Family member added."
    else:
        msg = "Family relationship request sent."

    return Response({"message": msg}, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilyRelationshipRequestSerializer(many=True)},
    summary="List pending family requests received",
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_family_requests(request):
    """
    List pending relationship requests where the current user is the recipient.
    In the new model, canonical ordering means the accepting user could be in
    either the `user` or `relative` field — so we find all pending edges where
    the user is involved but did NOT initiate (added_by != request.user).
    """
    reqs = FamilyRelationship.objects.filter(
        db_models.Q(user=request.user) | db_models.Q(relative=request.user),
        status="pending",
    ).exclude(added_by=request.user).select_related("user__profile", "relative__profile", "added_by")
    serializer = FamilyRelationshipRequestSerializer(reqs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilySentRequestSerializer(many=True)},
    summary="List pending family requests sent by the current user",
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_sent_family_requests(request):
    """
    List pending relationship requests that the current user initiated.
    """
    reqs = FamilyRelationship.objects.filter(
        added_by=request.user,
        status="pending",
    ).select_related("user__profile", "relative__profile", "added_by")
    serializer = FamilySentRequestSerializer(reqs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Family Tree"],
    request=FamilyRequestRespondSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Accept or reject a family request",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def respond_to_family_request(request, request_id):
    """
    Accept or reject a pending family relationship request.
    Rejection deletes the record so either party can re-request in the future.
    """
    try:
        relationship = FamilyRelationship.objects.get(id=request_id, status="pending")
    except FamilyRelationship.DoesNotExist:
        return Response(
            {"error": "Pending request not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Verify the requester is a party in this edge but not the one who initiated it.
    # (Canonical ordering means the accepting user may be in `user` or `relative`.)
    if request.user.id not in {relationship.user_id, relationship.relative_id}:
        return Response(
            {"error": "Pending request not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if relationship.added_by_id == request.user.id:
        return Response(
            {"error": "You cannot respond to your own request."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = FamilyRequestRespondSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    action = serializer.validated_data["action"]

    if action == "reject":
        relationship.delete()
        return Response(
            {"message": "Relationship request declined."},
            status=status.HTTP_200_OK,
        )

    # ── Accept: re-run cycle check in case tree changed while request was pending ─
    if relationship.relationship_type == "parent_child":
        parent = relationship.user
        child = relationship.relative
        if parent.id in _get_descendants(child.id):
            relationship.delete()
            return Response(
                {
                    "error": (
                        "Accepting this request would create a cycle in the family tree. "
                        "The request has been removed."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    relationship.status = "accepted"
    relationship.save()

    # Infer gender for the accepting user if not yet set
    try:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        if profile.gender == "prefer_not_to_say":
            rel_type = relationship.relationship_type
            initiator_gender = get_profile_gender(relationship.user)
            if rel_type == "parent_child":
                # request.user is the child (relative field) — infer nothing special from this
                pass
            elif rel_type == "spouse" and initiator_gender in ("male", "female"):
                profile.gender = "female" if initiator_gender == "male" else "male"
                profile.save()
    except Exception:
        pass

    generate_suggestions_for_new_edge(relationship)
    dismiss_stale_suggestions(relationship.user, relationship.relative)

    return Response(
        {"message": "Relationship request accepted."},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilyTreeMemberSerializer(many=True)},
    summary="List all accepted family members",
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_family_members(request):
    """
    Return all accepted family members with their relationship label, attribution,
    and deceased status — from the current user's perspective.
    """
    edges = FamilyRelationship.objects.filter(
        db_models.Q(user=request.user) | db_models.Q(relative=request.user),
        status="accepted",
    ).select_related("user__profile", "relative__profile", "added_by__profile")

    members_data = []
    viewer_id = request.user.id

    for edge in edges:
        member = edge.relative if edge.user == request.user else edge.user
        label = get_relationship_label(edge, viewer_id)
        # Every edge returned already includes the viewer — both parties can edit/revoke
        is_initiator = True
        added_by = edge.added_by
        if added_by and added_by.id == request.user.id:
            initiator_name = "you"
        elif added_by:
            initiator_name = added_by.fullname
        else:
            initiator_name = edge.user.fullname if edge.user != request.user else "you"

        serialized = FamilyTreeMemberSerializer(member, context={"request": request}).data
        serialized["relationship"] = label
        serialized["relationship_id"] = edge.id
        serialized["relationship_type"] = edge.relationship_type
        serialized["is_initiator"] = is_initiator
        serialized["initiator_name"] = initiator_name
        members_data.append(serialized)

    return Response(members_data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilyTreeResponseSerializer},
    summary="Get full family tree graph",
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_family_tree(request):
    """
    Return the entire connected family tree as a graph (nodes + edges).
    Uses frontier-batched BFS (~O(depth) queries, not O(nodes)).
    Edge labels are computed server-side from the viewer's perspective.
    """
    users_map, all_edges = get_tree_data(request.user.id)
    viewer_id = request.user.id

    nodes_serializer = FamilyTreeMemberSerializer(
        list(users_map.values()), many=True, context={"request": request}
    )

    edges_data = []
    for edge in all_edges:
        is_editable = request.user.id in {edge.added_by_id, edge.user_id, edge.relative_id}
        edges_data.append(
            {
                "id": edge.id,
                "source": edge.user_id,
                "target": edge.relative_id,
                "relationship_type": edge.relationship_type,
                # Label from source's perspective
                "label_from_source": get_relationship_label(edge, edge.user_id),
                # Label from viewer's perspective (only if viewer is in this edge)
                "label_for_viewer": (
                    get_relationship_label(edge, viewer_id)
                    if viewer_id in {edge.user_id, edge.relative_id}
                    else None
                ),
                "added_by_id": str(edge.added_by_id) if edge.added_by_id else None,
                "added_by_name": edge.added_by.fullname if edge.added_by_id else None,
                "is_editable": is_editable,
            }
        )

    return Response(
        {"nodes": nodes_serializer.data, "edges": edges_data},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Family Tree"],
    responses={200: _MessageSerializer, 403: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Revoke a family relationship",
)
@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def revoke_family_relationship(request, relationship_id):
    """
    Delete a family relationship edge.
    Only the person who added it, or either person in the edge, can revoke it.
    Placeholder users with no remaining relationships are cleaned up automatically.
    """
    try:
        relationship = FamilyRelationship.objects.get(id=relationship_id)
    except FamilyRelationship.DoesNotExist:
        return Response(
            {"error": "Relationship not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    allowed = {relationship.added_by_id, relationship.user_id, relationship.relative_id}
    if request.user.id not in allowed:
        return Response(
            {"error": "You do not have permission to revoke this relationship."},
            status=status.HTTP_403_FORBIDDEN,
        )

    user_node = relationship.user
    relative_node = relationship.relative

    relationship.delete()

    # Clean up orphaned placeholder users
    _cleanup_orphaned_placeholder(user_node)
    _cleanup_orphaned_placeholder(relative_node)

    return Response(
        {"message": "Family relationship removed."},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Family Tree"],
    request=FamilyRelationshipUpdateSerializer,
    responses={
        200: _MessageSerializer,
        400: _ErrorSerializer,
        403: _ErrorSerializer,
        404: _ErrorSerializer,
    },
    summary="Edit a family relationship type",
)
@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def edit_family_relationship(request, relationship_id):
    """
    Change the relationship type of an existing edge.
    The new type is interpreted from the request.user's perspective.
    Changing to a parent_child type triggers a re-confirmation for registered users.
    """
    try:
        relationship = FamilyRelationship.objects.get(id=relationship_id)
    except FamilyRelationship.DoesNotExist:
        return Response({"error": "Relationship not found."}, status=status.HTTP_404_NOT_FOUND)

    allowed = {relationship.added_by_id, relationship.user_id, relationship.relative_id}
    if request.user.id not in allowed:
        return Response(
            {"error": "You do not have permission to edit this relationship."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = FamilyRelationshipUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    new_relationship_to_me = serializer.validated_data["relationship_to_me"]
    new_mapping = RELATIONSHIP_INPUT_MAP[new_relationship_to_me]
    new_edge_type = new_mapping["edge_type"]
    new_requester_role = new_mapping["requester_role"]

    # Determine which person is the "subject" from the requester's perspective
    if request.user.id == relationship.user_id:
        subject = relationship.user
        other = relationship.relative
    elif request.user.id == relationship.relative_id:
        subject = relationship.relative
        other = relationship.user
    else:
        # added_by who is not in the edge — use the user side as subject
        subject = relationship.user
        other = relationship.relative

    # No change needed
    new_parent_or_a, new_child_or_b = build_edge_direction(
        subject, other, new_edge_type, new_requester_role
    )
    same_type = new_edge_type == relationship.relationship_type
    same_direction = (
        new_parent_or_a.id == relationship.user_id
        and new_child_or_b.id == relationship.relative_id
    )
    if same_type and same_direction:
        return Response(
            {"message": "No change — relationship type is already set to this value."},
            status=status.HTTP_200_OK,
        )

    # Cycle detection for new type
    if new_edge_type == "parent_child":
        new_parent, new_child = new_parent_or_a, new_child_or_b
        if new_parent.id in _get_descendants(new_child.id, exclude_edge_id=relationship.id):
            return Response(
                {"error": "This change would create a cycle in the family tree."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Duplicate parent check for new type
    if new_relationship_to_me in ("father", "mother"):
        from ._family_helpers import GENDER_FROM_RELATIONSHIP
        gender_to_check = GENDER_FROM_RELATIONSHIP[new_relationship_to_me]
        # Check subject's parents, excluding the current relationship
        parent_edges = FamilyRelationship.objects.filter(
            relative=new_child_or_b,
            relationship_type="parent_child",
            status="accepted",
        ).exclude(id=relationship.id).select_related("user__profile")
        for pedge in parent_edges:
            if get_profile_gender(pedge.user) == gender_to_check:
                return Response(
                    {"error": f"{new_child_or_b.fullname} already has a {new_relationship_to_me}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

    # Apply changes
    relationship.relationship_type = new_edge_type
    relationship.user = new_parent_or_a
    relationship.relative = new_child_or_b

    # Update inferred gender for invited placeholders
    if other.is_invited:
        inferred = GENDER_FROM_RELATIONSHIP.get(new_relationship_to_me)
        if not inferred and new_edge_type == "spouse":
            sg = get_profile_gender(subject)
            inferred = "female" if sg == "male" else ("male" if sg == "female" else None)
        if inferred:
            try:
                profile, _ = Profile.objects.get_or_create(user=other)
                profile.gender = inferred
                profile.save()
            except Exception:
                pass

    if not other.is_invited:
        # Require re-confirmation from the registered user
        relationship.status = "pending"

    relationship.save()
    return Response(
        {"message": "Relationship updated. The other person may need to re-confirm."}
        if not other.is_invited
        else {"message": "Relationship updated successfully."},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Family Tree"],
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Mark a family member as deceased (or living)",
)
@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def mark_member_deceased(request, user_id):
    """
    Toggle the deceased status of a confirmed family member (or self / admin).
    Body: { "is_deceased": bool, "date_of_death": "YYYY-MM-DD" (optional) }
    """
    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

    requester = request.user
    is_self = requester.id == target_user.id
    is_admin = requester.is_staff or requester.is_superuser

    # Permission: self, admin, or a direct (1-hop) family member
    is_direct_family = FamilyRelationship.objects.filter(
        db_models.Q(user=requester, relative=target_user)
        | db_models.Q(user=target_user, relative=requester),
        status="accepted",
    ).exists()

    if not (is_self or is_admin or is_direct_family):
        return Response(
            {"error": "You do not have permission to mark this person as deceased."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = MarkDeceasedSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    is_deceased = serializer.validated_data["is_deceased"]
    date_of_death = serializer.validated_data.get("date_of_death")

    if target_user.is_deceased:
        # Deceased placeholder — update User-level flag
        target_user.is_deceased = is_deceased
        if not is_deceased:
            # Un-marking a placeholder as deceased: make it a live invited placeholder
            target_user.is_active = True
        target_user.save()
    else:
        # Registered user — update their Profile
        profile, _ = Profile.objects.get_or_create(user=target_user)
        profile.is_deceased = is_deceased
        if is_deceased and date_of_death:
            profile.date_of_death = date_of_death
        elif not is_deceased:
            profile.date_of_death = None
        profile.save()

    action = "marked as deceased" if is_deceased else "marked as living"
    return Response(
        {"message": f"{target_user.fullname} has been {action}."},
        status=status.HTTP_200_OK,
    )


# ── Suggestions ───────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilyRelationshipSuggestionSerializer(many=True)},
    summary="List pending family relationship suggestions",
    description=(
        "Returns system-generated suggestions derived from the connected family graph. "
        "E.g. 'Alice is your sibling's parent and may also be yours.' "
        "Accept a suggestion to create the real relationship edge."
    ),
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_suggestions(request):
    suggestions = FamilyRelationshipSuggestion.objects.filter(
        suggested_to=request.user, status="pending"
    ).select_related("suggested_person__profile")
    serializer = FamilyRelationshipSuggestionSerializer(
        suggestions, many=True, context={"request": request}
    )
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Family Tree"],
    request=FamilyRequestRespondSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Accept or dismiss a family suggestion",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def respond_to_suggestion(request, suggestion_id):
    """
    Accept or dismiss a pending family relationship suggestion.
    Accepting creates the real FamilyRelationship edge and triggers further suggestions.
    """
    try:
        suggestion = FamilyRelationshipSuggestion.objects.get(
            id=suggestion_id, suggested_to=request.user, status="pending"
        )
    except FamilyRelationshipSuggestion.DoesNotExist:
        return Response(
            {"error": "Suggestion not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = FamilyRequestRespondSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if serializer.validated_data["action"] == "dismiss":
        suggestion.status = "dismissed"
        suggestion.save()
        return Response({"message": "Suggestion dismissed."}, status=status.HTTP_200_OK)

    # ── Accept: create the real edge ───────────────────────────────────────────
    suggested_person = suggestion.suggested_person
    subject = request.user

    # Check no relationship already exists
    existing = _existing_edge(subject, suggested_person)
    if existing:
        suggestion.status = "dismissed"
        suggestion.save()
        return Response(
            {"error": "A relationship with this person already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    edge_type = suggestion.edge_type
    role = suggestion.role  # 'as_parent' or 'as_child' for parent_child

    # Determine direction
    if edge_type == "parent_child":
        if role == "as_child":
            # subject is the child, suggested_person is the parent
            parent_node, child_node = suggested_person, subject
        else:
            parent_node, child_node = subject, suggested_person

        # Cycle check
        if parent_node.id in _get_descendants(child_node.id):
            suggestion.status = "dismissed"
            suggestion.save()
            return Response(
                {"error": "Accepting this would create a cycle in the family tree."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_node, relative_node = parent_node, child_node

    else:
        # Sibling / spouse: canonical ordering
        a, b = subject, suggested_person
        if str(a.id) > str(b.id):
            a, b = b, a
        user_node, relative_node = a, b

    try:
        with transaction.atomic():
            # For registered suggested_person → pending; for placeholder → accepted
            new_status = "accepted" if suggested_person.is_invited else "pending"
            edge = FamilyRelationship.objects.create(
                user=user_node,
                relative=relative_node,
                relationship_type=edge_type,
                status=new_status,
                added_by=request.user,
            )
    except IntegrityError:
        suggestion.status = "dismissed"
        suggestion.save()
        return Response(
            {"error": "This relationship already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    suggestion.status = "dismissed"
    suggestion.save()

    if edge.status == "accepted":
        generate_suggestions_for_new_edge(edge)
        dismiss_stale_suggestions(user_node, relative_node)
        return Response({"message": "Relationship added successfully."}, status=status.HTTP_201_CREATED)
    else:
        return Response(
            {"message": "Relationship request sent — waiting for confirmation."},
            status=status.HTTP_201_CREATED,
        )

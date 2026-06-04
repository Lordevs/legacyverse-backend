"""
Family Tree views: add, list, respond to requests, get tree, revoke, and edit relationships.
"""
import uuid as uuid_lib
from django.db import models as db_models
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..email_utils import send_family_invitation_email
from ..models import FamilyRelationship, Profile, User
from ..serializers import (
    FamilyMemberAddSerializer,
    FamilyRelationshipRequestSerializer,
    FamilyRelationshipUpdateSerializer,
    FamilyRequestRespondSerializer,
    FamilyTreeMemberSerializer,
    FamilyTreeResponseSerializer,
)
from ._family_helpers import _get_all_tree_members, _get_descendants, _get_inverted_relationship
from ._serializers import _ErrorSerializer, _MessageSerializer


@extend_schema(
    tags=["Family Tree"],
    request=FamilyMemberAddSerializer,
    responses={201: _MessageSerializer, 400: _ErrorSerializer},
    summary="Add an immediate family member",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def add_family_member(request):
    """
    Add an immediate family member (Father, Mother, Son, Daughter, Spouse).
    For living members, an invitation email is sent.
    For deceased placeholders (is_deceased=True), no email is sent and the
    relationship is immediately accepted.
    """
    serializer = FamilyMemberAddSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    fullname = serializer.validated_data["fullname"]
    relationship_type = serializer.validated_data["relationship_type"]
    date_of_birth = serializer.validated_data.get("date_of_birth")
    is_deceased = serializer.validated_data.get("is_deceased", False)
    gender_override = serializer.validated_data.get("gender")
    date_of_death = serializer.validated_data.get("date_of_death")
    email = serializer.validated_data.get("email", "").lower() if serializer.validated_data.get("email") else None
    anchor_user_id = serializer.validated_data.get("anchor_user_id")

    # ── Anchor validation ─────────────────────────────────────────────────────
    # When anchor_user_id is provided, the new person is added as a relative of
    # the anchor user (not the requester). Requester must be in the same tree.
    anchor_user = None
    if anchor_user_id:
        try:
            anchor_user = User.objects.get(id=anchor_user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "The selected family member does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Verify requester is in the same tree as the anchor
        tree_members = _get_all_tree_members(request.user)
        if anchor_user.id not in tree_members:
            return Response(
                {"error": "You can only add relatives to people in your own family tree."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Prevent adding more than one father or one mother to the anchor node
        if relationship_type in ["father", "mother"]:
            already_has = FamilyRelationship.objects.filter(
                (db_models.Q(user=anchor_user) & db_models.Q(relationship_type=relationship_type))
                | (db_models.Q(relative=anchor_user) & db_models.Q(relationship_type="son" if relationship_type == "father" else "daughter")),
                status="accepted",
            ).exists()
            # Also check via the inverted direction (anchor added their own parent)
            already_has_2 = FamilyRelationship.objects.filter(
                db_models.Q(relative=anchor_user, relationship_type=relationship_type),
                status="accepted",
            ).exists()
            if already_has or already_has_2:
                label = "father" if relationship_type == "father" else "mother"
                return Response(
                    {"error": f"{anchor_user.fullname} already has a {label} in the family tree."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Cycle detection relative to the anchor
        if relationship_type in ["father", "mother"]:
            if anchor_user.id in _get_descendants(anchor_user):
                return Response(
                    {"error": "This would create a circular relationship in the family tree."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

    # ── Deceased placeholder flow ─────────────────────────────────────────────
    if is_deceased:
        # Generate a unique internal email so the User model stays consistent
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
        # Gender is required for deceased placeholders (validated in serializer)
        profile.gender = gender_override
        if date_of_birth:
            profile.date_of_birth = date_of_birth
        if date_of_death:
            profile.date_of_death = date_of_death
        profile.is_deceased = True
        profile.save()

        # The initiator of the relationship is the anchor user (if provided) or the requester
        initiator = anchor_user if anchor_user else request.user

        # Auto-accept — no confirmation needed for a deceased person
        FamilyRelationship.objects.create(
            user=initiator,
            relative=relative,
            relationship_type=relationship_type,
            status="accepted",
            added_by=request.user,
        )

        return Response(
            {"message": f"Deceased family member '{fullname}' added to your tree."},
            status=status.HTTP_201_CREATED,
        )

    # ── Living member flow ────────────────────────────────────────────────────
    if email == request.user.email.lower():
        return Response(
            {"error": "You cannot add yourself as a family member."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_email = User.objects.normalize_email(email)

    # Check if user already exists
    relative = User.objects.filter(email__iexact=normalized_email).first()
    is_new_user = False

    initiator = anchor_user if anchor_user else request.user

    if not relative:
        # Create invited placeholder user
        is_new_user = True
        relative = User.objects.create(
            email=normalized_email,
            fullname=fullname,
            is_invited=True,
            is_active=True,
        )
        relative.set_unusable_password()
        relative.save()

        # Infer profile gender from relationship type
        profile, _ = Profile.objects.get_or_create(user=relative)
        if gender_override:
            profile.gender = gender_override
        elif relationship_type in ["father", "son"]:
            profile.gender = "male"
        elif relationship_type in ["mother", "daughter"]:
            profile.gender = "female"
        elif relationship_type == "spouse":
            # Spouse implies opposite gender — infer from the initiator's gender
            initiator_profile, _ = Profile.objects.get_or_create(user=initiator)
            if initiator_profile.gender == "male":
                profile.gender = "female"
            elif initiator_profile.gender == "female":
                profile.gender = "male"
        if date_of_birth:
            profile.date_of_birth = date_of_birth
        profile.save()

    # Check if a relationship already exists in either direction
    existing_relationship = FamilyRelationship.objects.filter(
        (db_models.Q(user=initiator) & db_models.Q(relative=relative))
        | (db_models.Q(user=relative) & db_models.Q(relative=initiator))
    ).first()

    if existing_relationship:
        return Response(
            {
                "error": "A relationship request between these users already exists."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Cycle detection ───────────────────────────────────────────────────────
    if relationship_type in ["father", "mother"]:
        if relative.id in _get_descendants(initiator):
            return Response(
                {
                    "error": (
                        "This person is already a descendant in your family tree "
                        "and cannot be added as a parent."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    elif relationship_type in ["son", "daughter"]:
        if initiator.id in _get_descendants(relative):
            return Response(
                {
                    "error": (
                        "This person is already an ancestor in your family tree "
                        "and cannot be added as a child."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Create relationship record
    relationship = FamilyRelationship.objects.create(
        user=initiator,
        relative=relative,
        relationship_type=relationship_type,
        status="pending",
        added_by=request.user,
    )

    # If the relative is an invited/placeholder account, automatically accept the relationship
    if relative.is_invited:
        relationship.status = "accepted"
        relationship.save()

    # Send email notification
    send_family_invitation_email(
        sender=request.user,
        receiver_email=normalized_email,
        receiver_name=fullname,
        relationship_type=relationship.get_relationship_type_display(),
        is_new_user=is_new_user,
    )

    msg = (
        "Invitation email sent and placeholder created."
        if is_new_user
        else "Family relationship request sent."
    )
    if relative.is_invited:
        msg = "Family member added and invitation email sent."

    return Response({"message": msg}, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Family Tree"],
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Mark a family member as deceased (or undo)",
)
@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def mark_member_deceased(request, user_id):
    """
    Mark a confirmed family member (or self) as deceased.
    Can be called by: the person themselves, any confirmed family member, or an admin.
    Body: { "is_deceased": true/false, "date_of_death": "YYYY-MM-DD" (optional) }
    """
    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

    requester = request.user

    # Permission check: self, admin, or confirmed family member
    is_self = requester.id == target_user.id
    is_admin = requester.is_staff or requester.is_superuser
    is_family_member = FamilyRelationship.objects.filter(
        (db_models.Q(user=requester) & db_models.Q(relative=target_user))
        | (db_models.Q(user=target_user) & db_models.Q(relative=requester)),
        status="accepted",
    ).exists()

    if not (is_self or is_admin or is_family_member):
        return Response(
            {"error": "You do not have permission to mark this person as deceased."},
            status=status.HTTP_403_FORBIDDEN,
        )

    is_deceased = request.data.get("is_deceased", True)
    date_of_death = request.data.get("date_of_death", None)

    if target_user.is_deceased:
        # Deceased placeholder — update User model flag
        target_user.is_deceased = is_deceased
        target_user.save()
    else:
        # Registered user — update Profile
        profile, _ = Profile.objects.get_or_create(user=target_user)
        profile.is_deceased = is_deceased
        if date_of_death:
            profile.date_of_death = date_of_death
        elif not is_deceased:
            profile.date_of_death = None
        profile.save()

    action = "marked as deceased" if is_deceased else "marked as living"
    return Response(
        {"message": f"{target_user.fullname} has been {action}."},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilyRelationshipRequestSerializer(many=True)},
    summary="List pending family requests received",
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_family_requests(request):
    """
    List all pending family relationship requests received by the current user.
    """
    requests = FamilyRelationship.objects.filter(
        relative=request.user, status="pending"
    ).select_related("user")
    serializer = FamilyRelationshipRequestSerializer(requests, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Family Tree"],
    request=FamilyRequestRespondSerializer,
    responses={200: _MessageSerializer, 400: _ErrorSerializer, 404: _ErrorSerializer},
    summary="Respond to a family request",
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def respond_to_family_request(request, request_id):
    """
    Accept or reject a pending family relationship request.
    """
    try:
        relationship = FamilyRelationship.objects.get(
            id=request_id, relative=request.user, status="pending"
        )
    except FamilyRelationship.DoesNotExist:
        return Response(
            {"error": "Pending request not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = FamilyRequestRespondSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    action = serializer.validated_data["action"]
    if action == "accept":
        relationship.status = "accepted"
        relationship.save()

        # If the user accepts a relationship, check if we need to update their own gender
        # if it is 'prefer_not_to_say' and we can infer it.
        profile, _ = Profile.objects.get_or_create(user=request.user)
        if profile.gender == "prefer_not_to_say":
            rel_type = relationship.relationship_type
            if rel_type in ["mother", "daughter"]:
                profile.gender = "female"
                profile.save()
            elif rel_type in ["father", "son"]:
                profile.gender = "male"
                profile.save()
            elif rel_type == "spouse":
                # Infer opposite gender from the initiator's profile
                initiator_profile, _ = Profile.objects.get_or_create(user=relationship.user)
                if initiator_profile.gender == "male":
                    profile.gender = "female"
                    profile.save()
                elif initiator_profile.gender == "female":
                    profile.gender = "male"
                    profile.save()

        return Response(
            {"message": "Relationship request accepted."},
            status=status.HTTP_200_OK,
        )
    elif action == "reject":
        relationship.status = "rejected"
        relationship.save()
        return Response(
            {"message": "Relationship request rejected."},
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
    List all accepted family members with relationship labels, attribution info,
    and deceased status.
    """
    relationships = FamilyRelationship.objects.filter(
        (db_models.Q(user=request.user) | db_models.Q(relative=request.user)),
        status="accepted",
    ).select_related("user__profile", "relative__profile")

    members_data = []
    for rel in relationships:
        if rel.user == request.user:
            member = rel.relative
            relationship_label = rel.get_relationship_type_display()
            is_initiator = True
            initiator_name = "you"
        else:
            member = rel.user
            relationship_label = _get_inverted_relationship(
                rel.relationship_type, rel.user.profile.gender
            )
            is_initiator = False
            initiator_name = rel.user.fullname

        serialized_member = FamilyTreeMemberSerializer(
            member, context={"request": request}
        ).data
        serialized_member["relationship"] = relationship_label
        serialized_member["relationship_id"] = rel.id
        serialized_member["is_initiator"] = is_initiator
        serialized_member["initiator_name"] = initiator_name
        members_data.append(serialized_member)

    return Response(members_data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Family Tree"],
    responses={200: FamilyTreeResponseSerializer},
    summary="Get full family tree (graph)",
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_family_tree(request):
    """
    Retrieve the entire connected family tree using BFS traversal.
    Edges include initiator_id and initiator_name for attribution display.
    """
    visited_nodes = {request.user.id}
    nodes = [request.user]
    edges = []
    added_edges = set()
    queue = [request.user]

    while queue:
        current_user = queue.pop(0)

        # Get all accepted relationships for current_user
        relations = FamilyRelationship.objects.filter(
            (db_models.Q(user=current_user) | db_models.Q(relative=current_user)),
            status="accepted",
        ).select_related("user__profile", "relative__profile")

        for rel in relations:
            neighbor = rel.relative if rel.user == current_user else rel.user

            # Record the edge uniquely
            edge_id = f"{rel.user.id}-{rel.relative.id}"
            if edge_id not in added_edges:
                added_edges.add(edge_id)
                is_editable = request.user.id in [rel.added_by_id, rel.user_id, rel.relative_id]
                edges.append(
                    {
                        "id": rel.id,
                        "source": rel.user.id,
                        "target": rel.relative.id,
                        "relationship": rel.relationship_type,
                        "initiator_id": str(rel.user.id),
                        "initiator_name": rel.user.fullname,
                        "is_editable": is_editable,
                    }
                )

            if neighbor.id not in visited_nodes:
                visited_nodes.add(neighbor.id)
                nodes.append(neighbor)
                queue.append(neighbor)

    # Serialize nodes
    nodes_serializer = FamilyTreeMemberSerializer(
        nodes, many=True, context={"request": request}
    )

    return Response(
        {
            "nodes": nodes_serializer.data,
            "edges": edges,
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Family Tree"],
    responses={200: _MessageSerializer, 404: _ErrorSerializer},
    summary="Revoke or delete a family relationship",
)
@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def revoke_family_relationship(request, relationship_id):
    """
    Revoke/delete an existing family relationship. Only the creator, anchor, or target can do this.
    """
    try:
        relationship = FamilyRelationship.objects.get(id=relationship_id)
    except FamilyRelationship.DoesNotExist:
        return Response(
            {"error": "Relationship not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    allowed_users = {relationship.added_by_id, relationship.user_id, relationship.relative_id}
    if request.user.id not in allowed_users:
        return Response(
            {"error": "You do not have permission to revoke this relationship."},
            status=status.HTTP_403_FORBIDDEN,
        )

    relationship.delete()
    return Response(
        {"message": "Family relationship revoked successfully."},
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
    summary="Edit an initiated family relationship type",
)
@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def edit_family_relationship(request, relationship_id):
    """
    Edit the relationship type of a connection. Only the creator, anchor, or target can edit it.
    If the relative is a registered user, the status resets to pending.
    If the relative is a placeholder, their inferred gender is updated on their profile.
    """
    try:
        relationship = FamilyRelationship.objects.get(id=relationship_id)
    except FamilyRelationship.DoesNotExist:
        return Response(
            {"error": "Relationship not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    allowed_users = {relationship.added_by_id, relationship.user_id, relationship.relative_id}
    if request.user.id not in allowed_users:
        return Response(
            {"error": "You do not have permission to edit this relationship."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = FamilyRelationshipUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    new_type = serializer.validated_data["relationship_type"]
    if new_type == relationship.relationship_type:
        return Response(
            {"message": "Relationship type is already set to this value."},
            status=status.HTTP_200_OK,
        )

    # ── Cycle detection for the new type ─────────────────────────────────────
    relative = relationship.relative
    anchor = relationship.user
    if new_type in ["father", "mother"]:
        if relative.id in _get_descendants(anchor, exclude_relationship_id=relationship.id):
            return Response(
                {
                    "error": (
                        "This person is already a descendant in your family tree "
                        "and cannot be changed to a parent role."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    elif new_type in ["son", "daughter"]:
        if anchor.id in _get_descendants(relative, exclude_relationship_id=relationship.id):
            return Response(
                {
                    "error": (
                        "This person is already an ancestor in your family tree "
                        "and cannot be changed to a child role."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    relationship.relationship_type = new_type

    # Handle status resets and gender inferences
    if not relative.is_invited:
        # Reset to pending for registered users
        relationship.status = "pending"
    else:
        # If relative is invited/placeholder, update their profile gender if inferred
        profile, _ = Profile.objects.get_or_create(user=relative)
        if new_type in ["father", "son"]:
            profile.gender = "male"
            profile.save()
        elif new_type in ["mother", "daughter"]:
            profile.gender = "female"
            profile.save()
        elif new_type == "spouse":
            # Infer placeholder's gender as opposite of the initiator's (anchor's) gender
            initiator_profile, _ = Profile.objects.get_or_create(user=anchor)
            if initiator_profile.gender == "male":
                profile.gender = "female"
                profile.save()
            elif initiator_profile.gender == "female":
                profile.gender = "male"
                profile.save()

    relationship.save()

    return Response(
        {"message": "Relationship type updated successfully."},
        status=status.HTTP_200_OK,
    )

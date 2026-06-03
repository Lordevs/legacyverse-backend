"""
Family Tree views: add, list, respond to requests, get tree, revoke, and edit relationships.
"""
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
from ._family_helpers import _get_descendants, _get_inverted_relationship
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
    If the relative does not exist, a placeholder user is created.
    """
    serializer = FamilyMemberAddSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"].lower()
    fullname = serializer.validated_data["fullname"]
    relationship_type = serializer.validated_data["relationship_type"]
    date_of_birth = serializer.validated_data.get("date_of_birth")

    if email == request.user.email.lower():
        return Response(
            {"error": "You cannot add yourself as a family member."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_email = User.objects.normalize_email(email)

    # Check if user already exists
    relative = User.objects.filter(email__iexact=normalized_email).first()
    is_new_user = False

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
        if relationship_type in ["father", "son"]:
            profile.gender = "male"
        elif relationship_type in ["mother", "daughter"]:
            profile.gender = "female"
        elif relationship_type == "spouse":
            # Spouse implies opposite gender — infer from the current user's gender
            initiator_profile, _ = Profile.objects.get_or_create(user=request.user)
            if initiator_profile.gender == "male":
                profile.gender = "female"
            elif initiator_profile.gender == "female":
                profile.gender = "male"
            # If initiator gender is unknown we leave the placeholder gender unset
        if date_of_birth:
            profile.date_of_birth = date_of_birth
        profile.save()

    # Check if a relationship already exists in either direction
    existing_relationship = FamilyRelationship.objects.filter(
        (db_models.Q(user=request.user) & db_models.Q(relative=relative))
        | (db_models.Q(user=relative) & db_models.Q(relative=request.user))
    ).first()

    if existing_relationship:
        return Response(
            {
                "error": "A relationship request between you and this user already exists."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Cycle detection ───────────────────────────────────────────────────────
    # parent types: the relative would become an ancestor of the current user.
    # child  types: the relative would become a descendant of the current user.
    # Spouse links carry no parent-child hierarchy, so no cycle is possible.
    if relationship_type in ["father", "mother"]:
        # B becomes A's parent → B must NOT already be a descendant of A
        if relative.id in _get_descendants(request.user):
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
        # B becomes A's child → A must NOT already be a descendant of B
        if request.user.id in _get_descendants(relative):
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
        user=request.user,
        relative=relative,
        relationship_type=relationship_type,
        status="pending",
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
    List all accepted family members with relationship labels.
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
        else:
            member = rel.user
            relationship_label = _get_inverted_relationship(
                rel.relationship_type, rel.user.profile.gender
            )

        serialized_member = FamilyTreeMemberSerializer(
            member, context={"request": request}
        ).data
        serialized_member["relationship"] = relationship_label
        serialized_member["relationship_id"] = rel.id
        serialized_member["is_initiator"] = rel.user == request.user
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
                edges.append(
                    {
                        "id": rel.id,
                        "source": rel.user.id,
                        "target": rel.relative.id,
                        "relationship": rel.relationship_type,
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
    Revoke/delete an existing family relationship. Either the initiator or recipient can do this.
    """
    try:
        relationship = FamilyRelationship.objects.get(
            db_models.Q(id=relationship_id)
            & (
                db_models.Q(user=request.user)
                | db_models.Q(relative=request.user)
            )
        )
    except FamilyRelationship.DoesNotExist:
        return Response(
            {"error": "Relationship not found."},
            status=status.HTTP_404_NOT_FOUND,
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
    Edit the relationship type of a connection. Only the initiator can edit it.
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

    if relationship.user != request.user:
        return Response(
            {"error": "Only the initiator can edit this relationship."},
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
    # Exclude the existing record so the check isn't polluted by its current type.
    relative = relationship.relative
    if new_type in ["father", "mother"]:
        if relative.id in _get_descendants(request.user, exclude_relationship_id=relationship.id):
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
        if request.user.id in _get_descendants(relative, exclude_relationship_id=relationship.id):
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
            # Infer placeholder's gender as opposite of the current user's gender
            initiator_profile, _ = Profile.objects.get_or_create(user=request.user)
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

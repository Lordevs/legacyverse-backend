"""
Pure helper functions for the Family Tree feature.
No HTTP logic — only tree traversal, label computation, and suggestion generation.
"""
from collections import deque

from django.db import models as db_models

from ..models import FamilyRelationship, FamilyRelationshipSuggestion, User


# ── Relationship input mapping ────────────────────────────────────────────────
# Maps the user-facing input type to internal edge semantics.
# requester_role: 'parent'  → requester is the parent in the parent_child edge
#                 'child'   → requester is the child
#                 None      → symmetric (sibling / spouse)
RELATIONSHIP_INPUT_MAP = {
    "father":  {"edge_type": "parent_child", "requester_role": "child"},
    "mother":  {"edge_type": "parent_child", "requester_role": "child"},
    "son":     {"edge_type": "parent_child", "requester_role": "parent"},
    "daughter":{"edge_type": "parent_child", "requester_role": "parent"},
    "brother": {"edge_type": "sibling",      "requester_role": None},
    "sister":  {"edge_type": "sibling",      "requester_role": None},
    "spouse":  {"edge_type": "spouse",       "requester_role": None},
}

# Gender to infer for a new placeholder based on the relationship type the user chose.
GENDER_FROM_RELATIONSHIP = {
    "father": "male",
    "mother": "female",
    "son":    "male",
    "daughter": "female",
    "brother": "male",
    "sister":  "female",
    # spouse: inferred from opposite of subject gender (handled in view)
}


def build_edge_direction(subject, relative, edge_type, requester_role):
    """
    Return (parent_or_a, child_or_b) correctly ordered for DB insertion.

    For parent_child: returns (parent, child).
    For sibling/spouse: returns (canonical_a, canonical_b) with a.id < b.id.
    """
    if edge_type == "parent_child":
        if requester_role == "child":
            # Subject is child, relative is parent
            return (relative, subject)
        else:
            # Subject is parent, relative is child
            return (subject, relative)
    else:
        # Undirected — canonical ordering enforced in model.save(), but we pre-sort here too
        a, b = subject, relative
        if str(a.id) > str(b.id):
            a, b = b, a
        return (a, b)


def get_profile_gender(user):
    """Safe profile gender access, returns None if profile doesn't exist."""
    try:
        return user.profile.gender
    except Exception:
        return None


# ── Label computation ─────────────────────────────────────────────────────────

def get_relationship_label(edge, viewer_id):
    """
    Compute the human-readable relationship label for an edge from the viewer's perspective.
    viewer_id must be one of edge.user_id or edge.relative_id.
    """
    viewer_id = str(viewer_id)

    if edge.relationship_type == "parent_child":
        # user=parent, relative=child — always
        if str(edge.user_id) == viewer_id:
            # Viewer is the parent, looking at their child
            gender = get_profile_gender(edge.relative)
            return {"male": "Son", "female": "Daughter"}.get(gender, "Child")
        else:
            # Viewer is the child, looking at their parent
            gender = get_profile_gender(edge.user)
            return {"male": "Father", "female": "Mother"}.get(gender, "Parent")

    elif edge.relationship_type == "sibling":
        other = edge.relative if str(edge.user_id) == viewer_id else edge.user
        gender = get_profile_gender(other)
        return {"male": "Brother", "female": "Sister"}.get(gender, "Sibling")

    elif edge.relationship_type == "spouse":
        other = edge.relative if str(edge.user_id) == viewer_id else edge.user
        gender = get_profile_gender(other)
        return {"male": "Husband", "female": "Wife"}.get(gender, "Spouse")

    return "Relative"


# ── Efficient BFS helpers ─────────────────────────────────────────────────────

def get_tree_data(start_user_id):
    """
    BFS traversal from start_user outward across all accepted edges.
    Uses frontier-batched DB queries (~O(tree_depth) queries, not O(nodes)).

    Returns:
        users_map  — dict[uuid → User] for every node in the connected component
        all_edges  — list[FamilyRelationship] for every edge in the component
    """
    visited = {start_user_id}
    frontier = {start_user_id}
    all_edges = []
    seen_edge_ids = set()

    while frontier:
        qs = FamilyRelationship.objects.filter(
            db_models.Q(user_id__in=frontier) | db_models.Q(relative_id__in=frontier),
            status="accepted",
        ).select_related("user__profile", "relative__profile")

        next_frontier = set()
        for edge in qs:
            if edge.id not in seen_edge_ids:
                seen_edge_ids.add(edge.id)
                all_edges.append(edge)
            for nid in (edge.user_id, edge.relative_id):
                if nid not in visited:
                    visited.add(nid)
                    next_frontier.add(nid)
        frontier = next_frontier

    users_map = {
        u.id: u
        for u in User.objects.filter(id__in=visited).select_related("profile")
    }
    return users_map, all_edges


def get_all_tree_member_ids(start_user_id):
    """
    BFS to collect every user ID reachable from start_user via accepted edges.
    Used for anchor validation (check anchor is in requester's tree).
    Lighter than get_tree_data — only loads IDs, not full User objects.
    """
    visited = {start_user_id}
    frontier = {start_user_id}

    while frontier:
        qs = FamilyRelationship.objects.filter(
            db_models.Q(user_id__in=frontier) | db_models.Q(relative_id__in=frontier),
            status="accepted",
        ).values("user_id", "relative_id")

        next_frontier = set()
        for row in qs:
            for nid in (row["user_id"], row["relative_id"]):
                if nid not in visited:
                    visited.add(nid)
                    next_frontier.add(nid)
        frontier = next_frontier

    return visited


def _get_descendants(user_id, exclude_edge_id=None):
    """
    BFS down the parent_child chain to collect all descendant user IDs of user_id.
    A descendant is anyone reachable by following: user=X → relative=Y (X is parent of Y).

    Used for cycle detection: before adding C as parent of A, ensure C is not in
    _get_descendants(A) — otherwise adding C→A would form a loop.
    """
    visited = {user_id}
    descendants = set()
    frontier = {user_id}

    while frontier:
        qs = FamilyRelationship.objects.filter(
            user_id__in=frontier,
            relationship_type="parent_child",
            status="accepted",
        ).values("id", "relative_id")
        if exclude_edge_id:
            qs = qs.exclude(id=exclude_edge_id)

        next_frontier = set()
        for row in qs:
            cid = row["relative_id"]
            if cid not in visited:
                visited.add(cid)
                descendants.add(cid)
                next_frontier.add(cid)
        frontier = next_frontier

    return descendants


# ── Suggestion generation ─────────────────────────────────────────────────────

def generate_suggestions_for_new_edge(edge):
    """
    After a new relationship edge is accepted, derive and store suggestions for
    other tree members who are likely to share the same relationship.

    sibling edge  → surface each person's parents to the other sibling
                  → surface new sibling to each other's existing siblings
    parent_child  → surface the new parent to the child's existing siblings
    """
    if edge.relationship_type == "sibling":
        _suggest_parents_to_sibling(edge.user, edge.relative)
        _suggest_parents_to_sibling(edge.relative, edge.user)
        _suggest_sibling_to_existing_siblings(edge.user, edge.relative)
        _suggest_sibling_to_existing_siblings(edge.relative, edge.user)
    elif edge.relationship_type == "parent_child":
        parent = edge.user
        child = edge.relative
        _suggest_parent_to_siblings(parent, child)


def _suggest_parents_to_sibling(person_with_known_parents, new_sibling):
    """
    For each accepted parent of person_with_known_parents, create a pending
    suggestion for new_sibling to also add that person as a parent.
    """
    parent_edges = FamilyRelationship.objects.filter(
        relative=person_with_known_parents,
        relationship_type="parent_child",
        status="accepted",
    ).select_related("user__profile")

    for pedge in parent_edges:
        parent = pedge.user
        if parent.id == new_sibling.id:
            continue  # Safety: don't suggest someone to themselves

        # Skip if a real relationship already exists (either direction)
        already_linked = FamilyRelationship.objects.filter(
            db_models.Q(user=parent, relative=new_sibling)
            | db_models.Q(user=new_sibling, relative=parent)
        ).exists()
        if already_linked:
            continue

        gender = get_profile_gender(parent)
        label = {"male": "father", "female": "mother"}.get(gender, "parent")
        reason = (
            f"{parent.fullname} is {person_with_known_parents.fullname}'s "
            f"{label} and may also be yours"
        )
        FamilyRelationshipSuggestion.objects.get_or_create(
            suggested_to=new_sibling,
            suggested_person=parent,
            defaults={
                "edge_type": "parent_child",
                "role": "as_child",
                "reason": reason,
                "status": "pending",
            },
        )


def _suggest_parent_to_siblings(parent, child):
    """
    When parent is linked as parent of child, suggest parent to each of child's
    existing accepted siblings.
    """
    sibling_edges = FamilyRelationship.objects.filter(
        db_models.Q(user=child) | db_models.Q(relative=child),
        relationship_type="sibling",
        status="accepted",
    ).select_related("user__profile", "relative__profile")

    for sedge in sibling_edges:
        sibling = sedge.relative if sedge.user == child else sedge.user
        if sibling.id == parent.id:
            continue

        already_linked = FamilyRelationship.objects.filter(
            db_models.Q(user=parent, relative=sibling)
            | db_models.Q(user=sibling, relative=parent)
        ).exists()
        if already_linked:
            continue

        gender = get_profile_gender(parent)
        label = {"male": "father", "female": "mother"}.get(gender, "parent")
        reason = (
            f"{parent.fullname} is {child.fullname}'s {label} and may also be yours"
        )
        FamilyRelationshipSuggestion.objects.get_or_create(
            suggested_to=sibling,
            suggested_person=parent,
            defaults={
                "edge_type": "parent_child",
                "role": "as_child",
                "reason": reason,
                "status": "pending",
            },
        )


def _suggest_sibling_to_existing_siblings(new_sibling, sibling_of):
    """
    When new_sibling becomes a sibling of sibling_of, suggest new_sibling to
    each of sibling_of's other existing accepted siblings (and vice-versa).

    This ensures: if A and B are brothers and B adds a new sister S, then A
    also sees S as a suggested sister.
    """
    existing_sibling_edges = FamilyRelationship.objects.filter(
        db_models.Q(user=sibling_of) | db_models.Q(relative=sibling_of),
        relationship_type="sibling",
        status="accepted",
    ).select_related("user__profile", "relative__profile")

    for sedge in existing_sibling_edges:
        existing_sibling = sedge.relative if sedge.user == sibling_of else sedge.user
        if existing_sibling.id == new_sibling.id:
            continue  # This is the edge we just created

        already_linked = FamilyRelationship.objects.filter(
            db_models.Q(user=new_sibling, relative=existing_sibling)
            | db_models.Q(user=existing_sibling, relative=new_sibling)
        ).exists()
        if already_linked:
            continue

        # Suggest new_sibling to existing_sibling
        gender = get_profile_gender(new_sibling)
        label = {"male": "brother", "female": "sister"}.get(gender, "sibling")
        reason = (
            f"{new_sibling.fullname} is {sibling_of.fullname}'s "
            f"{label} and may also be yours"
        )
        FamilyRelationshipSuggestion.objects.get_or_create(
            suggested_to=existing_sibling,
            suggested_person=new_sibling,
            defaults={"edge_type": "sibling", "role": None, "reason": reason, "status": "pending"},
        )

        # Also suggest existing_sibling to new_sibling
        gender2 = get_profile_gender(existing_sibling)
        label2 = {"male": "brother", "female": "sister"}.get(gender2, "sibling")
        reason2 = (
            f"{existing_sibling.fullname} is {sibling_of.fullname}'s "
            f"{label2} and may also be yours"
        )
        FamilyRelationshipSuggestion.objects.get_or_create(
            suggested_to=new_sibling,
            suggested_person=existing_sibling,
            defaults={"edge_type": "sibling", "role": None, "reason": reason2, "status": "pending"},
        )


def dismiss_stale_suggestions(user_a, user_b):
    """
    When a real edge is created between user_a and user_b, dismiss any pending
    suggestions that proposed the same connection.
    """
    FamilyRelationshipSuggestion.objects.filter(
        db_models.Q(suggested_to=user_a, suggested_person=user_b)
        | db_models.Q(suggested_to=user_b, suggested_person=user_a),
        status="pending",
    ).update(status="dismissed")

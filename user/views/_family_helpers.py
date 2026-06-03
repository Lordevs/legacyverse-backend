"""
Pure helper functions for the Family Tree feature.
No HTTP logic — only tree traversal and label utilities.
"""
from ..models import FamilyRelationship


def _get_descendants(user, exclude_relationship_id=None):
    """
    BFS traversal to collect all descendant user IDs of `user`.
    A "descendant" is any person reachable by following child links:
      - FamilyRelationship(user=X, relative=Y, type in [son, daughter])  → Y is X's child
      - FamilyRelationship(user=X, relative=Y, type in [father, mother]) → X is Y's child

    `exclude_relationship_id` lets us ignore a specific relationship record
    (used during edits so we don't count the old type of the relationship being changed).
    """
    visited = {user.id}
    descendants = set()
    queue = [user]

    while queue:
        current = queue.pop(0)

        # Pattern 1: current is the initiator and added someone as their child
        qs1 = FamilyRelationship.objects.filter(
            user=current,
            relationship_type__in=["son", "daughter"],
            status="accepted",
        ).select_related("relative")
        if exclude_relationship_id:
            qs1 = qs1.exclude(id=exclude_relationship_id)

        for rel in qs1:
            if rel.relative.id not in visited:
                visited.add(rel.relative.id)
                descendants.add(rel.relative.id)
                queue.append(rel.relative)

        # Pattern 2: current is the relative and someone added current as their parent
        qs2 = FamilyRelationship.objects.filter(
            relative=current,
            relationship_type__in=["father", "mother"],
            status="accepted",
        ).select_related("user")
        if exclude_relationship_id:
            qs2 = qs2.exclude(id=exclude_relationship_id)

        for rel in qs2:
            if rel.user.id not in visited:
                visited.add(rel.user.id)
                descendants.add(rel.user.id)
                queue.append(rel.user)

    return descendants


def _get_inverted_relationship(relationship_type, initiator_gender):
    """
    Given the relationship type as stored (from the initiator's perspective) and the
    initiator's gender, return the label as seen from the relative's perspective.
    """
    if relationship_type in ["father", "mother"]:
        if initiator_gender == "male":
            return "Son"
        elif initiator_gender == "female":
            return "Daughter"
        else:
            return "Child"
    elif relationship_type in ["son", "daughter"]:
        if initiator_gender == "male":
            return "Father"
        elif initiator_gender == "female":
            return "Mother"
        else:
            return "Parent"
    elif relationship_type == "spouse":
        return "Spouse"
    return "Relative"

from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from user.models import User, FamilyRelationship, FamilyRelationshipSuggestion

from django.test.signals import template_rendered
from django.test.client import store_rendered_templates


class FamilyTreeTestCase(APITestCase):
    def setUp(self):
        # Disconnect template rendered signal to bypass Python 3.14 / Django copy context bug
        template_rendered.disconnect(store_rendered_templates)

        self.user_a = User.objects.create_user(
            email="usera@example.com", password="Password123!", fullname="User A"
        )
        self.profile_a = self.user_a.profile
        self.profile_a.gender = "male"
        self.profile_a.save()

        self.user_b = User.objects.create_user(
            email="userb@example.com", password="Password123!", fullname="User B"
        )
        self.profile_b = self.user_b.profile
        self.profile_b.gender = "female"
        self.profile_b.save()

        self.add_url = reverse("add_family_member")
        self.requests_url = reverse("list_family_requests")
        self.members_url = reverse("list_family_members")
        self.tree_url = reverse("get_family_tree")

    # ── Adding members ──────────────────────────────────────────────────────────

    def test_add_existing_user_as_family_member(self):
        """
        Adding an existing registered user as a mother creates a pending parent_child edge.
        user_b is the parent (mother), user_a is the child.
        """
        self.client.force_authenticate(user=self.user_a)
        data = {
            "email": "userb@example.com",
            "fullname": "User B",
            "relationship_to_me": "mother",
        }
        response = self.client.post(self.add_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # New model: user=parent(B), relative=child(A)
        rel = FamilyRelationship.objects.get(
            user=self.user_b, relative=self.user_a, relationship_type="parent_child"
        )
        self.assertEqual(rel.status, "pending")

    def test_add_non_existing_user_as_family_member(self):
        """
        Adding a new user as son creates a placeholder (is_invited=True) and an
        accepted parent_child edge. user_a is the parent, invited_user is the child.
        """
        self.client.force_authenticate(user=self.user_a)
        data = {
            "email": "invited@example.com",
            "fullname": "Invited User",
            "relationship_to_me": "son",
            "date_of_birth": "2000-01-01",
        }
        response = self.client.post(self.add_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        invited_user = User.objects.get(email="invited@example.com")
        self.assertTrue(invited_user.is_invited)
        self.assertEqual(invited_user.fullname, "Invited User")
        self.assertEqual(invited_user.profile.gender, "male")
        self.assertEqual(str(invited_user.profile.date_of_birth), "2000-01-01")

        # user_a = parent, invited_user = child
        rel = FamilyRelationship.objects.get(
            user=self.user_a, relative=invited_user, relationship_type="parent_child"
        )
        self.assertEqual(rel.status, "accepted")

    def test_registration_claims_invited_account(self):
        """
        Registering with an invited email claims the placeholder, clears is_invited,
        sets the password, and preserves the relationship.
        """
        self.client.force_authenticate(user=self.user_a)
        self.client.post(self.add_url, {
            "email": "invited@example.com",
            "fullname": "Invited User",
            "relationship_to_me": "son",
        })

        self.client.logout()
        register_url = reverse("register")
        response = self.client.post(register_url, {
            "fullname": "Registered Claimed User",
            "email": "invited@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        claimed_user = User.objects.get(email="invited@example.com")
        self.assertFalse(claimed_user.is_invited)
        self.assertEqual(claimed_user.fullname, "Registered Claimed User")
        self.assertTrue(claimed_user.check_password("Password123!"))

        rel = FamilyRelationship.objects.get(user=self.user_a, relative=claimed_user)
        self.assertEqual(rel.status, "accepted")

    # ── Requests ────────────────────────────────────────────────────────────────

    def test_accept_reject_family_requests(self):
        """
        Accepting a request sets status=accepted.
        Rejecting a request DELETES the record (so either party can re-request).
        """
        # Direct DB create with new model: B is parent of A
        rel = FamilyRelationship.objects.create(
            user=self.user_b,
            relative=self.user_a,
            relationship_type="parent_child",
            status="pending",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(self.requests_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], rel.id)

        # Accept
        respond_url = reverse("respond_to_family_request", args=[rel.id])
        response = self.client.post(respond_url, {"action": "accept"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rel.refresh_from_db()
        self.assertEqual(rel.status, "accepted")

        # Reset to pending and reject — record should be deleted
        rel.status = "pending"
        rel.save()
        response = self.client.post(respond_url, {"action": "reject"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(FamilyRelationship.objects.filter(id=rel.id).exists())

    # ── Labels ───────────────────────────────────────────────────────────────────

    def test_inverted_relationship_labels(self):
        """
        parent_child edge: user=B (female parent), relative=A (male child).
        A sees B as "Mother".  B sees A as "Son".
        """
        FamilyRelationship.objects.create(
            user=self.user_b,   # B = parent (female → Mother)
            relative=self.user_a,  # A = child (male → Son)
            relationship_type="parent_child",
            status="accepted",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(self.members_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["fullname"], "User B")
        self.assertEqual(response.data[0]["relationship"], "Mother")

        self.client.force_authenticate(user=self.user_b)
        response = self.client.get(self.members_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["fullname"], "User A")
        self.assertEqual(response.data[0]["relationship"], "Son")

    def test_sibling_labels(self):
        """
        sibling edge: user_a (male) ↔ user_b (female).
        A sees B as "Sister".  B sees A as "Brother".
        """
        # Canonical ordering: min(a,b).id first
        a, b = self.user_a, self.user_b
        if str(a.id) > str(b.id):
            a, b = b, a
        FamilyRelationship.objects.create(
            user=a, relative=b,
            relationship_type="sibling",
            status="accepted",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(self.members_url)
        sibling_label = response.data[0]["relationship"]
        # A is male, so B (female) should appear as Sister to A
        # B is female, so A (male) should appear as Brother to B
        self.assertEqual(sibling_label, "Sister")

        self.client.force_authenticate(user=self.user_b)
        response = self.client.get(self.members_url)
        self.assertEqual(response.data[0]["relationship"], "Brother")

    # ── Tree ────────────────────────────────────────────────────────────────────

    def test_build_and_fetch_family_tree(self):
        """
        BFS traversal returns all nodes and edges in the connected component.
        Tree: A ↔ B (spouse), B → C (parent_child).
        """
        user_c = User.objects.create_user(
            email="userc@example.com", password="Password123!", fullname="User C"
        )
        user_c.profile.gender = "male"
        user_c.profile.save()

        # A ↔ B spouse — canonical order
        a, b = self.user_a, self.user_b
        if str(a.id) > str(b.id):
            a, b = b, a
        FamilyRelationship.objects.create(user=a, relative=b, relationship_type="spouse", status="accepted")

        # B is parent of C
        FamilyRelationship.objects.create(
            user=self.user_b, relative=user_c, relationship_type="parent_child", status="accepted"
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(self.tree_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        nodes = response.data["nodes"]
        self.assertEqual(len(nodes), 3)
        # Registered users have real emails; filter out None (placeholders)
        node_emails = {node["email"] for node in nodes if node["email"]}
        self.assertEqual(node_emails, {"usera@example.com", "userb@example.com", "userc@example.com"})

        edges = response.data["edges"]
        self.assertEqual(len(edges), 2)

    # ── Revoke ───────────────────────────────────────────────────────────────────

    def test_revoke_family_relationship(self):
        """Revoking a relationship deletes the record."""
        rel = FamilyRelationship.objects.create(
            user=self.user_a, relative=self.user_b,
            relationship_type="spouse", status="accepted",
        )
        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(reverse("revoke_family_relationship", args=[rel.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(FamilyRelationship.objects.filter(id=rel.id).exists())

    # ── Edit ─────────────────────────────────────────────────────────────────────

    def test_edit_family_relationship(self):
        """
        Editing a spouse relationship to 'mother' converts it to parent_child and
        resets to pending (since user_b is a registered user).
        """
        # A ↔ B spouse
        a, b = self.user_a, self.user_b
        if str(a.id) > str(b.id):
            a, b = b, a
        rel = FamilyRelationship.objects.create(
            user=a, relative=b, relationship_type="spouse", status="accepted",
        )

        # A edits: "B is my mother now"
        self.client.force_authenticate(user=self.user_a)
        response = self.client.patch(
            reverse("edit_family_relationship", args=[rel.id]),
            {"relationship_to_me": "mother"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        rel.refresh_from_db()
        self.assertEqual(rel.relationship_type, "parent_child")
        self.assertEqual(rel.status, "pending")

    # ── Cycle detection ──────────────────────────────────────────────────────────

    def test_cycle_detection_blocks_invalid_ancestor(self):
        """
        Chain A → B → C (A is grandparent of C).
        C tries to add A as son (C=parent, A=child) → A is C's ancestor → 400.
        """
        user_c = User.objects.create_user(
            email="userc_cycle@example.com", password="Password123!", fullname="User C"
        )
        # A is parent of B, B is parent of C
        FamilyRelationship.objects.create(
            user=self.user_a, relative=self.user_b,
            relationship_type="parent_child", status="accepted",
        )
        FamilyRelationship.objects.create(
            user=self.user_b, relative=user_c,
            relationship_type="parent_child", status="accepted",
        )

        # C tries to add A as child (C=parent, A=child) — cycle
        self.client.force_authenticate(user=user_c)
        response = self.client.post(self.add_url, {
            "email": self.user_a.email,
            "fullname": self.user_a.fullname,
            "relationship_to_me": "son",  # C is parent, A is son — cycle!
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ancestor", response.data["error"])

    def test_cycle_detection_allows_valid_tree(self):
        """
        Chain A → B already exists. B adding C as son is valid (A is grandparent of C).
        """
        user_c = User.objects.create_user(
            email="userc_valid@example.com", password="Password123!", fullname="User C"
        )
        FamilyRelationship.objects.create(
            user=self.user_a, relative=self.user_b,
            relationship_type="parent_child", status="accepted",
        )
        self.client.force_authenticate(user=self.user_b)
        response = self.client.post(self.add_url, {
            "email": user_c.email,
            "fullname": user_c.fullname,
            "relationship_to_me": "son",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # ── Deceased & anchor ────────────────────────────────────────────────────────

    def test_add_deceased_relative_to_anchor_member(self):
        """
        A is a child of B (parent_child: user=B, relative=A).
        A adds a deceased person as B's father via anchor.
        Result: parent_child edge where deceased_person is parent of B.
        """
        FamilyRelationship.objects.create(
            user=self.user_b, relative=self.user_a,
            relationship_type="parent_child", status="accepted",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(self.add_url, {
            "fullname": "Great Grandfather",
            "relationship_to_me": "father",
            "is_deceased": True,
            "gender": "male",
            "anchor_user_id": str(self.user_b.id),
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # new deceased user is parent (user field), user_b is child (relative field)
        new_relation = FamilyRelationship.objects.filter(
            relative=self.user_b, relationship_type="parent_child"
        ).first()
        self.assertIsNotNone(new_relation)
        self.assertEqual(new_relation.user.fullname, "Great Grandfather")
        self.assertTrue(new_relation.user.is_deceased)
        self.assertEqual(new_relation.status, "accepted")

    def test_add_deceased_relative_to_invalid_anchor_member(self):
        """
        Trying to add a relative to an anchor who is not in the requester's tree
        returns 403.
        """
        user_c = User.objects.create_user(
            email="userc_independent@example.com", password="Password123!", fullname="User C"
        )
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(self.add_url, {
            "fullname": "Great Grandfather",
            "relationship_to_me": "father",
            "is_deceased": True,
            "gender": "male",
            "anchor_user_id": str(user_c.id),
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("own family tree", response.data["error"])

    def test_add_living_relative_to_anchor_member_success(self):
        """
        A is a child of B. A uses anchor=B to add a new living person as B's son.
        Result: parent_child edge with user=B (parent), relative=living_rel (child).
        added_by should be user_a (the requester who triggered it).
        """
        FamilyRelationship.objects.create(
            user=self.user_b, relative=self.user_a,
            relationship_type="parent_child", status="accepted",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(self.add_url, {
            "email": "living_relative@example.com",
            "fullname": "Uncle Bob",
            "relationship_to_me": "son",
            "anchor_user_id": str(self.user_b.id),
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        living_rel = User.objects.get(email="living_relative@example.com")
        rel = FamilyRelationship.objects.get(
            user=self.user_b, relative=living_rel, relationship_type="parent_child"
        )
        self.assertEqual(rel.status, "accepted")
        self.assertEqual(rel.added_by, self.user_a)

    # ── Suggestions ──────────────────────────────────────────────────────────────

    def test_sibling_connection_generates_parent_suggestions(self):
        """
        When A and B become siblings, and A already has an accepted parent C,
        the system should suggest C to B as a potential parent.
        """
        user_c = User.objects.create_user(
            email="userc_parent@example.com", password="Password123!", fullname="User C"
        )
        # C is parent of A
        FamilyRelationship.objects.create(
            user=user_c, relative=self.user_a,
            relationship_type="parent_child", status="accepted",
            added_by=user_c,
        )

        # A adds B as sibling
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(self.add_url, {
            "email": self.user_b.email,
            "fullname": self.user_b.fullname,
            "relationship_to_me": "brother",
        })
        # B is a registered user → pending
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Now accept the sibling request as B
        rel = FamilyRelationship.objects.get(relationship_type="sibling")
        self.client.force_authenticate(user=self.user_b)
        self.client.post(reverse("respond_to_family_request", args=[rel.id]), {"action": "accept"})

        # B should now have a suggestion for C as a potential parent
        suggestion = FamilyRelationshipSuggestion.objects.filter(
            suggested_to=self.user_b, suggested_person=user_c, status="pending"
        ).first()
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.edge_type, "parent_child")
        self.assertEqual(suggestion.role, "as_child")

    def test_reject_re_request(self):
        """
        After A's request to B is rejected (record deleted), A can send a new request.
        """
        self.client.force_authenticate(user=self.user_a)
        # First request
        response = self.client.post(self.add_url, {
            "email": self.user_b.email,
            "fullname": self.user_b.fullname,
            "relationship_to_me": "spouse",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        rel = FamilyRelationship.objects.filter(relationship_type="spouse").first()

        # B rejects
        self.client.force_authenticate(user=self.user_b)
        self.client.post(reverse("respond_to_family_request", args=[rel.id]), {"action": "reject"})
        self.assertFalse(FamilyRelationship.objects.filter(id=rel.id).exists())

        # A can re-request
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(self.add_url, {
            "email": self.user_b.email,
            "fullname": self.user_b.fullname,
            "relationship_to_me": "spouse",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

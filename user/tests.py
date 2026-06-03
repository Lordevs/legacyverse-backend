from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from user.models import User, FamilyRelationship

from django.test.signals import template_rendered
from django.test.client import store_rendered_templates


class FamilyTreeTestCase(APITestCase):
    def setUp(self):
        # Disconnect template rendered signal to bypass Python 3.14 / Django copy context bug
        template_rendered.disconnect(store_rendered_templates)
        # Create a few users
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

        # URLs
        self.add_url = reverse("add_family_member")
        self.requests_url = reverse("list_family_requests")
        self.members_url = reverse("list_family_members")
        self.tree_url = reverse("get_family_tree")

    def test_add_existing_user_as_family_member(self):
        """
        Adding an existing user as a family member should create a pending request.
        """
        self.client.force_authenticate(user=self.user_a)

        data = {
            "email": "userb@example.com",
            "fullname": "User B",
            "relationship_type": "mother",
        }
        response = self.client.post(self.add_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify pending relationship exists
        rel = FamilyRelationship.objects.get(user=self.user_a, relative=self.user_b)
        self.assertEqual(rel.relationship_type, "mother")
        self.assertEqual(rel.status, "pending")

    def test_add_non_existing_user_as_family_member(self):
        """
        Adding a non-existing user should create a placeholder user with is_invited=True
        and an accepted relationship.
        """
        self.client.force_authenticate(user=self.user_a)

        data = {
            "email": "invited@example.com",
            "fullname": "Invited User",
            "relationship_type": "son",
            "date_of_birth": "2000-01-01"
        }
        response = self.client.post(self.add_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify placeholder user exists
        invited_user = User.objects.get(email="invited@example.com")
        self.assertTrue(invited_user.is_invited)
        self.assertEqual(invited_user.fullname, "Invited User")

        # Check inferred gender and date of birth on the profile
        self.assertEqual(invited_user.profile.gender, "male")
        self.assertEqual(str(invited_user.profile.date_of_birth), "2000-01-01")

        # Verify accepted relationship (since they are invited/placeholder)
        rel = FamilyRelationship.objects.get(user=self.user_a, relative=invited_user)
        self.assertEqual(rel.relationship_type, "son")
        self.assertEqual(rel.status, "accepted")

    def test_registration_claims_invited_account(self):
        """
        Registering with an invited email should successfully claim the account,
        clear is_invited, set the password, and preserve relationships.
        """
        # First, add the invited member
        self.client.force_authenticate(user=self.user_a)
        add_data = {
            "email": "invited@example.com",
            "fullname": "Invited User",
            "relationship_type": "son",
        }
        self.client.post(self.add_url, add_data)

        # Register the claimed account
        self.client.logout()
        register_url = reverse("register")
        register_data = {
            "fullname": "Registered Claimed User",
            "email": "invited@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        response = self.client.post(register_url, register_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify account is claimed
        claimed_user = User.objects.get(email="invited@example.com")
        self.assertFalse(claimed_user.is_invited)
        self.assertEqual(claimed_user.fullname, "Registered Claimed User")
        self.assertTrue(claimed_user.check_password("Password123!"))

        # Verify relationship remains accepted and preserved
        rel = FamilyRelationship.objects.get(user=self.user_a, relative=claimed_user)
        self.assertEqual(rel.status, "accepted")

    def test_accept_reject_family_requests(self):
        """
        Accepting or rejecting a family request should update the status appropriately.
        """
        # Create a pending relationship (User B -> User A as Father)
        rel = FamilyRelationship.objects.create(
            user=self.user_b,
            relative=self.user_a,
            relationship_type="father",
            status="pending",
        )

        self.client.force_authenticate(user=self.user_a)

        # View pending requests for User A
        response = self.client.get(self.requests_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], rel.id)

        # Respond to request: Accept
        respond_url = reverse("respond_to_family_request", args=[rel.id])
        response = self.client.post(respond_url, {"action": "accept"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        rel.refresh_from_db()
        self.assertEqual(rel.status, "accepted")

        # Re-create and reject
        rel.status = "pending"
        rel.save()

        response = self.client.post(respond_url, {"action": "reject"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        rel.refresh_from_db()
        self.assertEqual(rel.status, "rejected")

    def test_inverted_relationship_labels(self):
        """
        Tests that relationship labels are inverted correctly from the perspective of the relative.
        A (male) added B (female) as Mother.
        B should see A as Son.
        """
        # A -> B (Mother) [Accepted]
        FamilyRelationship.objects.create(
            user=self.user_a,
            relative=self.user_b,
            relationship_type="mother",
            status="accepted",
        )

        # User A views family members -> sees User B as Mother
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(self.members_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.data = response.data[0]
        self.assertEqual(self.data["fullname"], "User B")
        self.assertEqual(self.data["relationship"], "Mother")

        # User B views family members -> sees User A as Son (because A's gender is male)
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get(self.members_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.data = response.data[0]
        self.assertEqual(self.data["fullname"], "User A")
        self.assertEqual(self.data["relationship"], "Son")

    def test_build_and_fetch_family_tree(self):
        """
        A BFS traversal should build a graph of connected nodes and edges.
        """
        # Setup tree: User A (Male) <-> User B (Female, Spouse) <-> User C (Male, Son of B)
        user_c = User.objects.create_user(
            email="userc@example.com", password="Password123!", fullname="User C"
        )
        profile_c = user_c.profile
        profile_c.gender = "male"
        profile_c.save()

        # A <-> B (Spouse)
        FamilyRelationship.objects.create(
            user=self.user_a,
            relative=self.user_b,
            relationship_type="spouse",
            status="accepted",
        )
        # B <-> C (Son)
        FamilyRelationship.objects.create(
            user=self.user_b,
            relative=user_c,
            relationship_type="son",
            status="accepted",
        )

        # Fetch family tree for User A
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(self.tree_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify nodes count (should contain A, B, and C)
        nodes = response.data["nodes"]
        self.assertEqual(len(nodes), 3)
        node_emails = {node["email"] for node in nodes}
        self.assertEqual(
            node_emails, {"usera@example.com", "userb@example.com", "userc@example.com"}
        )

        # Verify edges count
        edges = response.data["edges"]
        self.assertEqual(len(edges), 2)

    def test_revoke_family_relationship(self):
        """
        Revoking a relationship should successfully delete the relationship record.
        """
        # Create an accepted relationship
        rel = FamilyRelationship.objects.create(
            user=self.user_a,
            relative=self.user_b,
            relationship_type="spouse",
            status="accepted"
        )
        
        # Revoke the relationship using User A
        self.client.force_authenticate(user=self.user_a)
        revoke_url = reverse("revoke_family_relationship", args=[rel.id])
        response = self.client.delete(revoke_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify it is deleted
        self.assertFalse(FamilyRelationship.objects.filter(id=rel.id).exists())

    def test_edit_family_relationship(self):
        """
        Editing a relationship type should update it and reset status to pending for registered users.
        """
        # Create an accepted relationship (User A -> User B as Spouse)
        rel = FamilyRelationship.objects.create(
            user=self.user_a,
            relative=self.user_b,
            relationship_type="spouse",
            status="accepted"
        )
        
        # Edit the relationship type (from Spouse to Mother)
        self.client.force_authenticate(user=self.user_a)
        edit_url = reverse("edit_family_relationship", args=[rel.id])
        response = self.client.patch(edit_url, {"relationship_type": "mother"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify it updated and reset to pending
        rel.refresh_from_db()
        self.assertEqual(rel.relationship_type, "mother")
        self.assertEqual(rel.status, "pending")

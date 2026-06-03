"""
user.views package — backwards-compatible entry point.

All view logic lives in the sub-modules.
This __init__.py re-exports everything so that user/urls.py needs zero changes.
"""

from user.views.auth import (
    CustomTokenObtainPairView,
    change_password_view,
    forgot_password_view,
    logout_view,
    refresh_token_view,
    register_view,
    reset_password_view,
)
from user.views.profile import (
    ProfileDetailView,
    delete_profile_image,
    update_profile_complete,
    update_profile_image,
)
from user.views.sections import (
    profile_section_detail,
    profile_sections_view,
    reorder_sections,
    reset_sections_to_default,
    section_image_detail,
    upload_section_images,
)
from user.views.public import (
    get_profile_by_username,
    get_user_by_username,
    list_user_profiles,
)
from user.views.admin import (
    admin_create_user,
    admin_delete_user_profile_image,
    admin_get_user_profile,
    admin_list_users,
    admin_reset_user_sections,
    admin_reorder_user_sections,
    admin_update_user_profile,
    admin_upload_user_profile_image,
    admin_upload_user_section_images,
    admin_user_detail,
    admin_user_profile_section_detail,
    admin_user_profile_sections,
    admin_user_section_image_detail,
)
from user.views.family import (
    add_family_member,
    edit_family_relationship,
    get_family_tree,
    list_family_members,
    list_family_requests,
    respond_to_family_request,
    revoke_family_relationship,
)

__all__ = [
    # auth
    "CustomTokenObtainPairView",
    "change_password_view",
    "forgot_password_view",
    "logout_view",
    "refresh_token_view",
    "register_view",
    "reset_password_view",
    
    # profile
    "ProfileDetailView",
    "delete_profile_image",
    "update_profile_complete",
    "update_profile_image",
    
    # sections
    "profile_section_detail",
    "profile_sections_view",
    "reorder_sections",
    "reset_sections_to_default",
    "section_image_detail",
    "upload_section_images",
    
    # public
    "get_profile_by_username",
    "get_user_by_username",
    "list_user_profiles",
    
    # admin
    "admin_create_user",
    "admin_delete_user_profile_image",
    "admin_get_user_profile",
    "admin_list_users",
    "admin_reset_user_sections",
    "admin_reorder_user_sections",
    "admin_update_user_profile",
    "admin_upload_user_profile_image",
    "admin_upload_user_section_images",
    "admin_user_detail",
    "admin_user_profile_section_detail",
    "admin_user_profile_sections",
    "admin_user_section_image_detail",
    
    # family
    "add_family_member",
    "edit_family_relationship",
    "get_family_tree",
    "list_family_members",
    "list_family_requests",
    "respond_to_family_request",
    "revoke_family_relationship",
]


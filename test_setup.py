#!/usr/bin/env python
"""
Simple test script to verify the user model setup
"""
import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legacyverse.settings')
django.setup()

from user.models import User, Profile

def test_user_creation():
    """Test user creation and username generation"""
    print("Testing user creation...")
    
    # Test data
    test_users = [
        {"fullname": "John Doe", "email": "john@example.com"},
        {"fullname": "Jane Smith", "email": "jane@example.com"},
        {"fullname": "John Doe", "email": "john2@example.com"},  # Same name, different email
    ]
    
    for user_data in test_users:
        try:
            user = User.objects.create_user(
                fullname=user_data["fullname"],
                email=user_data["email"],
                password="testpassword123"
            )
            print(f"✓ Created user: {user.fullname} -> Username: {user.username}")
            
            # Check if profile was created
            if hasattr(user, 'profile'):
                print(f"  ✓ Profile created automatically")
            else:
                print(f"  ✗ Profile not created")
                
        except Exception as e:
            print(f"✗ Error creating user {user_data['fullname']}: {e}")
    
    print("\nAll users in database:")
    for user in User.objects.all():
        print(f"  - {user.fullname} ({user.email}) -> @{user.username}")

if __name__ == "__main__":
    test_user_creation()

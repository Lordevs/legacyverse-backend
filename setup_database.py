#!/usr/bin/env python
"""
Database setup script for LegacyVerse
"""
import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legacyverse.settings')
django.setup()

from django.core.management import execute_from_command_line

def setup_database():
    """Set up the database with migrations"""
    print("Setting up database...")
    
    try:
        # Run migrations
        print("Running migrations...")
        execute_from_command_line(['manage.py', 'migrate'])
        print("✓ Migrations completed successfully")
        
        # Create superuser
        print("\nCreating superuser...")
        print("Please enter the following information for the superuser:")
        execute_from_command_line(['manage.py', 'createsuperuser'])
        print("✓ Superuser created successfully")
        
        print("\n🎉 Database setup completed!")
        print("\nYou can now:")
        print("1. Run the development server: python manage.py runserver")
        print("2. Access the admin panel at: http://localhost:8000/admin/")
        print("3. Test the API endpoints using the documentation in API_DOCUMENTATION.md")
        
    except Exception as e:
        print(f"❌ Error during setup: {e}")
        print("\nPlease make sure:")
        print("1. PostgreSQL is running")
        print("2. Database credentials in settings.py are correct")
        print("3. Database 'legacyverse_db' exists")

if __name__ == "__main__":
    setup_database()

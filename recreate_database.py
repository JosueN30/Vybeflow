"""
Recreate database with correct schema
WARNING: This will delete all existing data!
"""
import os
import sys

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from __init__ import db

def recreate_database():
    """Drop all tables and recreate with current schema"""
    app, _ = create_app()
    with app.app_context():
        print("⚠️  Dropping all existing tables...")
        db.drop_all()
        print("✓ Dropped all tables")
        
        print("\n📋 Creating tables with new schema...")
        db.create_all()
        print("✓ Created all tables")
        
        # Verify tables were created
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        print(f"\n✅ Database recreated successfully!")
        print(f"📊 Tables created: {', '.join(tables)}")
        
        # Show user table columns
        if 'user' in tables:
            columns = inspector.get_columns('user')
            print(f"\n👤 User table columns:")
            for col in columns:
                print(f"   - {col['name']} ({col['type']})")
        
        # Show post table columns
        if 'post' in tables:
            columns = inspector.get_columns('post')
            print(f"\n📝 Post table columns:")
            for col in columns:
                print(f"   - {col['name']} ({col['type']})")

if __name__ == '__main__':
    print("=" * 60)
    print("DATABASE RECREATION SCRIPT")
    print("=" * 60)
    print("\n⚠️  WARNING: This will DELETE ALL EXISTING DATA!")
    print("The database will be recreated with the correct schema.")
    print("=" * 60)
    
    recreate_database()
    
    print("\n" + "=" * 60)
    print("✅ NEXT STEPS:")
    print("Run: python create_test_data.py")
    print("=" * 60)

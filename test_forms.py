#!/usr/bin/env python3
"""Test script to verify form classes are properly defined"""

try:
    from VybeFlowapp import RegistrationForm, LoginForm
    print("✅ RegistrationForm imported successfully")
    print("✅ LoginForm imported successfully")
    
    # Test form creation
    reg_form = RegistrationForm()
    login_form = LoginForm()
    print("✅ Forms created successfully")
    
    print("Form fields:")
    print(f"Registration fields: {[field.name for field in reg_form]}")
    print(f"Login fields: {[field.name for field in login_form]}")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")

"""Script to create test accounts (admin + client) in Supabase Auth using regular sign-up."""
import sys
sys.path.insert(0, ".")

from app.services.supabase import get_supabase_anon_client

# Use anon key client (regular sign-up)
client = get_supabase_anon_client()

ACCOUNTS = [
    {"email": "admin@example.com", "password": "admin123456"},
    {"email": "client@example.com", "password": "client123456"},
]

for acc in ACCOUNTS:
    try:
        result = client.auth.sign_up({
            "email": acc["email"],
            "password": acc["password"],
        })
        if result.user:
            user_id = result.user.id
            confirmed = result.user.email_confirmed_at is not None
            print(f"Created: {acc['email']} (password: {acc['password']}) - User ID: {user_id}")
            if not confirmed:
                print(f"  NOTE: Email confirmation may be required. Check Supabase dashboard Auth settings.")
        else:
            print(f"Sign-up returned no user for {acc['email']} - may already exist")
    except Exception as e:
        err_str = str(e)
        if "already" in err_str.lower() or "registered" in err_str.lower():
            print(f"Already exists: {acc['email']} - try logging in with password: {acc['password']}")
        else:
            print(f"Error for {acc['email']}: {e}")

print("")
print("Test accounts:")
print("  Admin:  admin@example.com / admin123456")
print("  Client: client@example.com / client123456")
print("")
print("IMPORTANT: If your Supabase project requires email confirmation,")
print("go to Supabase Dashboard > Authentication > Providers > Email")
print("and disable 'Confirm email' for testing.")

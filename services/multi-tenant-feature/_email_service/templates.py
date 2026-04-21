WELCOME_EMAIL_SUBJECT = "Welcome to AI4I"

WELCOME_EMAIL_BODY = """
Welcome to AI4I!

Your tenant has been successfully activated.

Tenant Id: {tenant_id}
Email: {email}
Set your password using the secure setup link below:
{set_password_url}

This setup link is valid for 48 hours and can be used only once.

Login URL:
{login_url}

""".strip()



USER_WELCOME_EMAIL_BODY = """
Welcome to AI4I!

User has been successfully activated.

Email: {email}
Set your password using the secure setup link below:
{set_password_url}

This setup link is valid for 48 hours and can be used only once.


""".strip()

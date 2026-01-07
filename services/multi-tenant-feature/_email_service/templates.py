WELCOME_EMAIL_SUBJECT = "Welcome to AI4I"

WELCOME_EMAIL_BODY = """
Welcome to AI4I!

Your tenant has been successfully activated.

Tenant Id: {tenant_id}
Admin Username: {username}
Temporary Password: {password}

Login here:
{login_url}


copy and paste the link in your browser to verify your email address

Please change your password after first login.
""".strip()



USER_WELCOME_EMAIL_BODY = """
Welcome to AI4I!

User has been successfully activated.

User id: {user_id}
Username: {username}
Password: {password}

Login here:
{login_url}

Please change your password after first login.
""".strip()

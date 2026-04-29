"""Role-name constants.

The role names here MUST match the rows in the ``roles`` table seeded by
``auth_service_t_default_role_seeder.py``. Two of them have spaces in the
name (e.g. ``"TENANT ADMIN"``) which is easy to typo as an underscore —
using these constants instead of bare string literals catches that at
import time, not at runtime when an assign_role call silently fails.

Add a new entry here if a new role is seeded into the DB.
"""


class Roles:
    ADMIN = "ADMIN"
    MODERATOR = "MODERATOR"
    USER = "USER"
    GUEST = "GUEST"
    TENANT_ADMIN = "TENANT ADMIN"

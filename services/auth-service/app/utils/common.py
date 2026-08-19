from app.core.constants import RoleName


def role_name_to_str(name: RoleName | str) -> str:
    """Normalize ORM enum members or API strings to plain str."""
    return name.value if isinstance(name, RoleName) else name

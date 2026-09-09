import enum


class TierStatus(str, enum.Enum):
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"
    DELETED = "DELETED"

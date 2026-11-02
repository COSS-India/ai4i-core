"""Range check for the int4 primary keys the routes take as path params.

tenants.id, applications.id and api_keys.id are Postgres ``integer`` (int4).
asyncpg refuses to encode a larger bind value at all (DataError: value out
of int32 range) instead of just matching no rows, so an out-of-range id from
a path param would surface as a 500 rather than the route's 404. No such row
can exist, so lookups by these ids short-circuit to None without querying.
"""

from typing import Optional

INT4_MAX = 2**31 - 1


def is_int4_id(value: Optional[int]) -> bool:
    return value is not None and 0 < value <= INT4_MAX

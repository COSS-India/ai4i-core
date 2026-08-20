"""Unit tests — no broker, no database, no Redis.

This is the whole of the testing scope for this service.  Everything runs
against mocks, hand-written fakes and the deliberately unreachable
`KAFKA_SERVER=localhost:1` set in tests/conftest.py, which is what makes the
suite fast enough to run on every commit and safe to run anywhere.

It is also the boundary worth being honest about: librdkafka connects in the
background, so construction and `subscribe()` succeed without a broker, and the
rebalance callbacks are exercised by being CALLED FROM A TEST rather than by a
coordinator.  What lives on the other side of that line — cooperative-sticky
assignment, revoke-versus-lost, offset durability across a restart — is
documented as uncovered in README.md's Testing section rather than approximated
here.
"""

"""Throwaway file to verify that the SonarQube quality gate fails. DO NOT MERGE."""
import hashlib
PASSWORD = "hunter2"  # hardcoded credential (deliberate)
def probe(value):
    unused = 1
    try:
        return hashlib.md5(value.encode()).hexdigest()  # weak hash (deliberate)
    except:  # bare except (deliberate)
        pass

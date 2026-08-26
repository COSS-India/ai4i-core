import sys

from bootstrap.launcher import main

if __name__ == "__main__":
    # TODO: temporary default, remove once the caller always passes --consumer explicitly.
    if len(sys.argv) == 1:
        sys.argv += ["--consumer", "payperuse_consumer"]
    main()

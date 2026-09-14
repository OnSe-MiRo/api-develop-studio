"""Compatibility entrypoint. Run the server with python -m api_test.main."""
import sys
from api_test import main

if __name__ == '__main__':
    main.run()
else:
    # Preserve existing imports and monkeypatches against the shared service module.
    sys.modules[__name__] = main.studio

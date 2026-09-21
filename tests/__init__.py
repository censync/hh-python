"""The test suite: ``python -m unittest discover -s tests -t .`` from the repository root.

The tests run against the source tree. Set ``HH_TEST_INSTALLED=1`` to test the installed
package instead.
"""

import os
import sys

_SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

if not os.environ.get("HH_TEST_INSTALLED") and _SOURCE not in sys.path:
    sys.path.insert(0, _SOURCE)

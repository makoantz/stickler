#!/bin/sh
# Tags a release and pushes it. Maintainers only.
set -e
version=$(python3 -c "import sys; sys.path.insert(0, 'src'); import shelfkeep; print(shelfkeep.__version__)")
git tag "v$version"
git push origin "v$version"

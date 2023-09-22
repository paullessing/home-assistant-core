# `name` is the name of the package as used for `pip install package`
name = "samknows-whitebox"
# `path` is the name of the package for `import package`
path = name.lower().replace("-", "_").replace(" ", "_")
# Your version number should follow https://python.org/dev/peps/pep-0440 and
# https://semver.org
version = "0.1.dev0"
author = "Paul Lessing"
author_email = "paul@paullessing.com"
description = "API for SamKnows Whitebox Data"  # One-liner
url = "https://github.com/paullessing/samknows-whitebox-api"  # your project homepage
license = "MIT"  # See https://choosealicense.com

uv build
pipx uninstall ember
pipx install --python 3.13 "dist/$(command ls -1 dist/ | grep whl)"

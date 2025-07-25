# If environments empty, say this
# If not, prompt environment selection
    # If no lock file, say this, exit with code 1
    # If no pyproject, say this
        # Offer to initialize
        # If no, exit with code 2
        # If yes, check for legacy, check for requirements.txt
            # If either is missing, exit with code 2
            # If not
                # uv init --bare
                # uv add -r ./<env>/legacy/requirements.txt
                # prompt for QOP version, add to pyproject.toml as
                    # [metadata]
                    # QOP_version = "<version>"
                # prompt for overrides, prompt for constraints, add to pyproject.toml as
                    # [tool.uv]
                    # override-dependencies = ["<override1>","<override2>"]
                    # constraint-dependencies = ["<constraint1>","<constraint2>"]
    # Ask user if they'd like to check out save/store the current environment
        # test ./<prev-metadata.environment_name>
            # If doesn't exist, warn the user it couldn't store the old environment, exit with code 1
            # If it does, proceed to store
                # If any error is detected, graceful backout
                    # mv -f ./<prev-metadata.environment_name>/pyproject.toml ..
                    # mv -f ./<prev-metadata.environment_name>/uv.lock ..
                # mv -f ../pyproject.toml ./<prev-metadata.environment_name>/pyproject.toml
                # mv -f ../uv.lock ./<prev-metadata.environment_name>/uv.lock
                # cp ./<new-metadata.environment_name>/pyproject.toml ..
                # cp ./<new-metadata.environment_name>/uv.lock
                # uv sync




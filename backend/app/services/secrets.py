from __future__ import annotations

import os


class SecretResolutionError(LookupError):
    pass


class SecretResolver:
    def resolve(self, secret_ref: str) -> str:
        if not secret_ref.strip():
            raise SecretResolutionError("Secret reference is empty")

        if secret_ref.startswith("env:"):
            env_name = secret_ref.removeprefix("env:").strip()
            value = os.environ.get(env_name)
            if value:
                return value
            raise SecretResolutionError("Secret reference did not resolve")

        raise SecretResolutionError("Unsupported secret reference")

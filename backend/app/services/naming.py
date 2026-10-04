"""Kubernetes resource naming.

Every function version gets its own Deployment/Service named ``fn-<owner_id>-<name>-<version>``.
The owner id keeps two users' functions with the same name apart; the version lets old versions
keep serving their own code. All versions of one function share the label
``faas-function=<owner_id>-<name>`` so they can be listed, scaled and deleted together.
"""

def function_key(owner_id: int, name: str) -> str:
    return f"{owner_id}-{name}"

def resource_name(owner_id: int, name: str, version_tag: str) -> str:
    return f"{owner_id}-{name}-{version_tag}"

def summarize_version(version) -> int:
    """
    Summarize a version string into a single monotonically increasing integer for pypi.
    """
    components = list(map(int, version.split('.')))
    return sum(component * (100 ** i) for i, component in enumerate(reversed(components)))
"""Required[...] -- the inverse: force one field back to mandatory inside a
total=False class. Mirrors NotRequired, useful when most fields are optional
but one or two truly cannot be missing.
"""

from typing import Required, TypedDict


class ApiRequestConfig(TypedDict, total=False):  # everything optional by default...
    user_id: Required[str]                       # ...except this one:
    debug: bool
    timeout_seconds: int


def build_request(config: ApiRequestConfig) -> str:
    timeout = config.get("timeout_seconds", 30)
    debug = config.get("debug", False)
    return f"user={config['user_id']} timeout={timeout} debug={debug}"


if __name__ == "__main__":
    # a type checker accepts this: user_id present, everything else optional
    print(build_request({"user_id": "abc-123"}))
    print(build_request({"user_id": "abc-123", "debug": True}))

    # a type checker would flag this call as missing required key "user_id" --
    # at runtime it still just raises a plain KeyError once build_request
    # reads config["user_id"]
    try:
        build_request({"debug": True})  # type: ignore[typeddict-item]
    except KeyError as e:
        print(f"missing required field only fails at read time: {e}")

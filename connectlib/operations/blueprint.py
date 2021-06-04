import json

from typing import Callable, TypeVar, Generic

CLS = TypeVar("CLS")


class Blueprint(Generic[CLS]):
    def __init__(self, cls: CLS, parameters: str):
        self.cls = cls
        self.parameters = parameters

    def __eq__(self, other: "Blueprint") -> bool:
        return self.cls == other.cls and self.parameters == other.parameters

    def __hash__(self):
        return hash((self.cls, self.parameters))


def blueprint(cls: CLS) -> Callable[..., Blueprint[CLS]]:
    def blueprint_cls(*args, **kwargs) -> Blueprint[CLS]:
        # TypeError if types are not [str, int, float, bool, None]
        parameters = json.dumps({"args": args, "kwargs": kwargs})

        return Blueprint(cls, parameters)

    return blueprint_cls

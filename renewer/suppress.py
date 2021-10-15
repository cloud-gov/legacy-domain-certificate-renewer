import sys
from contextlib import contextmanager


def squelch(*args, print_name: bool = False):
    hook = sys.excepthook

    def f(type_, value, traceback):
        types = [arg for arg in args if isinstance(arg, type)]
        names = [arg for arg in args if isinstance(arg, str)]
        print(types)
        if (
            any([issubclass(type_, t) for t in types])
            or type_.__qualname__ in names
            or type_.__name__ in names
        ):
            if print_name:
                print(type_.__qualname__, file=sys.stderr)
        else:
            hook(type_, value, traceback)
        sys.excepthook = hook

    return f


@contextmanager
def suppress(*args, print_name: bool = False):
    sys.excepthook = squelch(*args, print_name=print_name)
    yield

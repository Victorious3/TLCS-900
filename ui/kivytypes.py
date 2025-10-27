from typing import Protocol, Any, TYPE_CHECKING, Callable
from kivy.graphics import Canvas

class HasWidget(Protocol):
    canvas: Canvas = ...

    def bind(self, **kwargs: Callable[..., Any]) -> Any: pass
    def unbind(self, **kwargs: Callable[..., Any]) -> Any: pass
    def register_event_type(self, *args): pass

if TYPE_CHECKING:
    class KWidget(HasWidget): ...
else:
    class KWidget: pass
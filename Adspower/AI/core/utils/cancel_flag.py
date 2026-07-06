# -*- coding: utf-8 -*-
import sys
import contextvars

class CancelState:
    def __init__(self):
        self.val = False

# This context var will hold a CancelState instance per request context.
_cancel_context_var = contextvars.ContextVar("google_fx_cancel_context", default=None)

class CancelFlag:
    @property
    def is_cancelled(self) -> bool:
        import builtins
        global_cancelled = getattr(builtins, "google_fx_cancelled", False)
        if global_cancelled:
            return True
        state = _cancel_context_var.get()
        if state is not None:
            return state.val
        return False
        
    @is_cancelled.setter
    def is_cancelled(self, value: bool):
        state = _cancel_context_var.get()
        if state is not None:
            state.val = value
        else:
            import builtins
            builtins.google_fx_cancelled = value

    def init_context(self):
        """Initialize context-local cancel state for the current request context."""
        state = CancelState()
        _cancel_context_var.set(state)
        return state

sys.modules[__name__] = CancelFlag()


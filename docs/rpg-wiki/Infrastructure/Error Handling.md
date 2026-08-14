# Error Handling

`events/error_handler.py` centralizes friendly error messages for both prefix and slash
commands (`on_command_error` / `on_app_command_error`), covering bad bet strings, invalid
Literal choices (with the valid options listed), cooldowns, missing permissions, and the
custom [[Admin & Settings/Server Settings|gamble-channel/game-disabled]] checks.

Also resilient to the error-notification *itself* failing to send (e.g. a network blip) —
wrapped in a try/except so that doesn't cascade into an unhandled exception in the event loop.

See [[Infrastructure Overview]].

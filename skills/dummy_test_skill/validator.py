def validate(action: str, context: dict) -> None:
    # Phase 56 Test Scenario 1 & 2:
    # Only allow "read" action to pass validation. Reject others.
    if action != "read":
        from nanobot.utils.exceptions import ToolValidationFailure
        raise ToolValidationFailure("Only 'read' action is allowed.", "dummy_test_skill")

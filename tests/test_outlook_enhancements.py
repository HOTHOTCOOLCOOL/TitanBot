"""Tests for OutlookTool enhancements: read_email, to_email filter, sent folder."""

import pytest

from nanobot.agent.tools.outlook import OutlookTool


@pytest.fixture
def outlook_tool():
    """Create an OutlookTool instance (without Outlook connection)."""
    return OutlookTool()


class TestReadEmail:
    """Test the read_email action."""

    @pytest.mark.asyncio
    async def test_read_email_no_results(self, outlook_tool: OutlookTool):
        """read_email returns error when no search results exist."""
        result = await outlook_tool._read_email(0)
        assert "Error" in result
        assert "No search results" in result

    @pytest.mark.asyncio
    async def test_read_email_invalid_index(self, outlook_tool: OutlookTool):
        """read_email returns error for out-of-range index."""
        outlook_tool._last_search_results = [
            {"index": 0, "items_index": 1, "folder": "inbox",
             "subject": "Test", "sender": "a@b.com", "received": "2026-01-01"}
        ]
        result = await outlook_tool._read_email(5)
        assert "Error" in result
        assert "Invalid email_index" in result

    @pytest.mark.asyncio
    async def test_read_email_negative_index(self, outlook_tool: OutlookTool):
        """read_email returns error for negative index."""
        outlook_tool._last_search_results = [{"index": 0}]
        result = await outlook_tool._read_email(-1)
        assert "Error" in result


class TestSentFolderSupport:
    """Test sent folder shortcut in _get_folder."""

    def test_folder_path_recognizes_sent(self, outlook_tool: OutlookTool):
        """'sent' in folder path should be recognized."""
        # We can't test actual COM calls without Outlook,
        # but we can verify the _get_folder logic path structure
        # by checking the parameter schema
        params = outlook_tool.parameters
        folder_prop = params["properties"]["criteria"]["properties"]["folder"]
        assert "sent" in folder_prop.get("description", "").lower()

    def test_to_email_in_parameters(self, outlook_tool: OutlookTool):
        """to_email should be in criteria parameters."""
        params = outlook_tool.parameters
        criteria_props = params["properties"]["criteria"]["properties"]
        assert "to_email" in criteria_props


class TestToolDescription:
    """Test that tool description includes new features."""

    def test_description_mentions_read_email(self, outlook_tool: OutlookTool):
        assert "read_email" in outlook_tool.description

    def test_description_mentions_sent(self, outlook_tool: OutlookTool):
        assert "sent" in outlook_tool.description.lower()

    def test_description_mentions_to_email(self, outlook_tool: OutlookTool):
        assert "to_email" in outlook_tool.description

    def test_action_enum_includes_read_email(self, outlook_tool: OutlookTool):
        params = outlook_tool.parameters
        action_enum = params["properties"]["action"]["enum"]
        assert "read_email" in action_enum


class TestExecuteRouting:
    """Test that execute routes to _read_email correctly."""

    @pytest.mark.asyncio
    async def test_execute_read_email_no_results(self, outlook_tool: OutlookTool):
        """Execute with action=read_email routes correctly."""
        result = await outlook_tool.execute(action="read_email", email_index=0)
        assert "Error" in result
        assert "No search results" in result

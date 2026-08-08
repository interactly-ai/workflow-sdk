"""Wire-level coverage for surface that Phases 2–5 added but no test pinned.

Everything here asserts *what goes on the wire* and *what comes back off it*, using the real response
shapes captured from dev. That bias is deliberate and hard-won: every bug these phases fixed was a
mismatch between what the SDK sent or expected and what the server actually does, and a mock encoding
a shape the server never produces will keep a broken method green indefinitely.

Three tests below pin corrections to documented behaviour that turned out to be false when finally
run against a server — they are marked in place.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest
import respx

from interactly import AsyncWorkflowClient, WorkflowClient
from interactly.types.global_variables.global_variable import GlobalVariable
from interactly.types.runs.run import FeedbackUser, Run, RunComment, RunFeedbackResponse

TEST_BASE_URL = "http://localhost:8611"


@pytest.fixture
def client() -> WorkflowClient:
    return WorkflowClient(
        api_key="test-api-key",
        team_id="test-team-id",
        user_id="test-user-id",
        base_url=TEST_BASE_URL,
        max_retries=0,
    )


@pytest.fixture
def aclient() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(
        api_key="test-api-key",
        team_id="test-team-id",
        user_id="test-user-id",
        base_url=TEST_BASE_URL,
        max_retries=0,
    )


def _captured(store: Dict[str, Any], payload: Any, status: int = 200):
    """respx side_effect that records the outgoing request and answers with ``payload``."""

    def _handler(request: httpx.Request) -> httpx.Response:
        store["url"] = str(request.url)
        store["method"] = request.method
        store["content"] = request.content.decode() or ""
        return httpx.Response(status, json=payload)

    return _handler


# =========================================================================== #
# Tool export / import                                                        #
# =========================================================================== #

# The bundle shape a real export returns (key set captured from dev).
_BUNDLE = {
    "export_format": 1,
    "exported_at": "2026-08-07T00:00:00Z",
    "source_tool_id": "tool-1",
    "source_tool_name": "lookup_capital",
    "tool_type": "inline_python",
    "tool_config": {"name": "lookup_capital", "type": "inline_python"},
    "redactions": ["api_headers.Authorization"],
    "warnings": [],
}


class TestToolExport:
    @respx.mock
    def test_exports_a_bundle_and_reports_what_was_redacted(self, client: WorkflowClient):
        seen: Dict[str, Any] = {}
        respx.get(f"{TEST_BASE_URL}/v1/tools/tool-1/export").mock(side_effect=_captured(seen, _BUNDLE))

        bundle = client.tools.export("tool-1")

        assert seen["method"] == "GET"
        # `redactions` is the contract that makes a round trip possible: it names the fields the
        # importer has to re-supply, which is otherwise unknowable from the bundle alone.
        assert bundle["redactions"] == ["api_headers.Authorization"]
        assert bundle["tool_type"] == "inline_python"


class TestToolImport:
    @respx.mock
    def test_sends_the_bundle_with_its_import_options(self, client: WorkflowClient):
        seen: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/tools/import").mock(
            side_effect=_captured(seen, {"_id": "tool-2", "name": "Imported"})
        )

        tool = client.tools.import_bundle(
            _BUNDLE,
            name_override="Imported",
            secret_overrides={"api_headers.Authorization": "Bearer x"},
            confirm_executable=True,
        )

        # Parse rather than substring-match: whitespace in the serialised body is not a contract.
        body = json.loads(seen["content"])
        assert body["bundle"]["source_tool_id"] == "tool-1"
        assert body["name_override"] == "Imported"
        assert body["secret_overrides"] == {"api_headers.Authorization": "Bearer x"}
        # Both flags must be sent explicitly rather than left to a server default: one governs whether
        # executable code runs in the importing team, the other whether foreign references survive.
        assert body["confirm_executable"] is True
        assert body["clear_unresolved_refs"] is True
        assert tool.id == "tool-2"

    @respx.mock
    def test_confirm_executable_defaults_to_false(self, client: WorkflowClient):
        """An `inline_python` bundle carries code that will run in your team's context.

        The server refuses it unless the caller says so explicitly, so the SDK must not quietly
        default the flag on.
        """
        seen: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/tools/import").mock(
            side_effect=_captured(seen, {"_id": "tool-3", "name": "x"})
        )

        client.tools.import_bundle(_BUNDLE)

        assert json.loads(seen["content"])["confirm_executable"] is False

    @respx.mock
    def test_optional_fields_are_omitted_when_not_given(self, client: WorkflowClient):
        seen: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/tools/import").mock(
            side_effect=_captured(seen, {"_id": "tool-4", "name": "x"})
        )

        client.tools.import_bundle(_BUNDLE)

        body = json.loads(seen["content"])
        assert "name_override" not in body
        assert "secret_overrides" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_variant_sends_the_same_body(self, aclient: AsyncWorkflowClient):
        seen: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/tools/import").mock(
            side_effect=_captured(seen, {"_id": "tool-5", "name": "x"})
        )

        await aclient.tools.import_bundle(_BUNDLE, confirm_executable=True)
        await aclient.close()

        assert json.loads(seen["content"])["confirm_executable"] is True


# =========================================================================== #
# System-provided global variables                                            #
# =========================================================================== #


class TestSystemGlobalVariables:
    """``is_system`` rows are provided to every team and are read-only.

    Response shape captured from dev: a synthetic ``system:<name>`` id, category ``"System"``, and a
    masked value for the credential.
    """

    _ROWS = {
        "variables": [
            {
                "_id": "system:interactly_api_base_url",
                "name": "interactly_api_base_url",
                "value": "https://api-dev.interactly.ai",
                "category": "System",
                "is_secret": False,
                "is_system": True,
            },
            {
                "_id": "system:interactly_api_token",
                "name": "interactly_api_token",
                "value": "********",
                "category": "System",
                "is_secret": True,
                "is_system": True,
            },
            {
                "_id": "6a76",
                "name": "api_key_openai",
                "value": "sk-…",
                "category": "credentials",
                "is_secret": True,
                "is_system": False,
            },
        ],
        "total": 3,
    }

    @respx.mock
    def test_system_rows_are_flagged_and_separable(self, client: WorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/global-variables").mock(
            return_value=httpx.Response(200, json=self._ROWS)
        )

        page = client.global_variables.list()
        system = [v for v in page.items if v.is_system]
        mine = [v for v in page.items if not v.is_system]

        assert {v.name for v in system} == {"interactly_api_base_url", "interactly_api_token"}
        assert [v.name for v in mine] == ["api_key_openai"]
        # Filtering them out is the whole point: rendering one in an editable list gets the user an
        # error when they try to save it.
        assert all(v.category == "System" for v in system)

    @respx.mock
    def test_the_system_token_arrives_masked(self, client: WorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/global-variables").mock(
            return_value=httpx.Response(200, json=self._ROWS)
        )

        token = next(v for v in client.global_variables.list().items if v.name == "interactly_api_token")

        assert token.value == "********"
        assert token.is_secret is True

    def test_is_system_defaults_to_false(self):
        """A row from a server that predates the field must not read as system-provided."""
        assert GlobalVariable.model_validate({"name": "x", "value": "1"}).is_system is False


# =========================================================================== #
# Run feedback response shapes                                                #
# =========================================================================== #


class TestFeedbackResponseShapes:
    _FEEDBACK = {
        "ratings": [{"logical_id": "r1", "value": "up", "createdBy": "user-1"}],
        "comments": [],
        "feedback_users": {
            "user-1": {"id": "user-1", "firstName": "Shiva", "lastName": "C", "email": "s@example.com"}
        },
    }

    @respx.mock
    def test_a_rating_write_returns_the_whole_list_plus_authors(self, client: WorkflowClient):
        seen: Dict[str, Any] = {}
        respx.put(f"{TEST_BASE_URL}/v1/workflow-runs/run-1/turns/0/rating").mock(
            side_effect=_captured(seen, self._FEEDBACK)
        )

        result = client.runs.set_turn_rating("run-1", 0, "up")

        assert isinstance(result, RunFeedbackResponse)
        # Returning everyone's ratings, not just the caller's, is what lets a UI render aggregate
        # counts and author names without a refetch.
        author = result.feedback_users[result.ratings[0]["createdBy"]]
        assert isinstance(author, FeedbackUser)
        assert author.email == "s@example.com"

    def test_feedback_user_exposes_only_four_fields(self):
        """A run response must not become an access path to the user directory."""
        assert set(FeedbackUser.model_fields) == {"id", "firstName", "lastName", "email"}

    def test_an_unresolvable_author_is_absent_rather_than_null(self):
        """Ids that no longer resolve are simply missing from the map, so `.get()` is the safe read."""
        result = RunFeedbackResponse.model_validate(
            {
                "ratings": [{"logical_id": "r1", "value": "up", "createdBy": "deleted-user"}],
                "comments": [],
                "feedback_users": {},
            }
        )
        assert result.feedback_users.get("deleted-user") is None

    @respx.mock
    def test_run_level_comment_returns_a_single_comment_not_the_list(self, client: WorkflowClient):
        """CORRECTION pinned: the docs claimed every feedback write returns the full list.

        ``add_comment`` and ``add_event_comment`` predate ``RunFeedbackResponse`` and return one
        ``RunComment``. Only the rating endpoints and ``add_turn_comment`` return the list.
        """
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/run-1/comments").mock(
            return_value=httpx.Response(200, json={"logical_id": "c1", "content": "Reviewed"})
        )

        result = client.runs.add_comment("run-1", content="Reviewed")

        assert isinstance(result, RunComment)
        assert not isinstance(result, RunFeedbackResponse)
        assert result.content == "Reviewed"

    def test_a_fetched_run_tolerates_an_empty_feedback_users_map(self):
        """CORRECTION pinned: ``client.runs.get()`` returns ``feedback_users`` EMPTY on the server
        today, even when the run carries ratings and comments.

        It defaults to ``{}`` rather than raising, so the failure is silent — which is exactly why it
        went unnoticed until a notebook tried to read a name out of it. Resolve authors from the write
        response instead.
        """
        run = Run.model_validate({"id": "run-1", "workflow_id": "wf-1", "status": "completed"})
        assert run.feedback_users == {}


# =========================================================================== #
# Run lineage filters                                                         #
# =========================================================================== #


class TestRerunLineageFilters:
    @respx.mock
    def test_source_run_and_turn_are_sent_as_query_params(self, client: WorkflowClient):
        seen: Dict[str, Any] = {}
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs").mock(
            side_effect=_captured(seen, {"workflow_runs": [], "total": 0})
        )

        client.runs.list(source_workflow_run_id="run-abc", source_turn_index=3)

        assert "source_workflow_run_id=run-abc" in seen["url"]
        assert "source_turn_index=3" in seen["url"]

    @respx.mock
    def test_a_turn_index_alone_is_still_sent_but_means_nothing_without_the_run(
        self, client: WorkflowClient
    ):
        """The server ignores it on its own — a turn index is meaningless without its run.

        Pinned so the SDK's behaviour (pass it through, do not silently drop it) stays deliberate.
        """
        seen: Dict[str, Any] = {}
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs").mock(
            side_effect=_captured(seen, {"workflow_runs": [], "total": 0})
        )

        client.runs.list(source_turn_index=3)

        assert "source_turn_index=3" in seen["url"]
        assert "source_workflow_run_id" not in seen["url"]

"""End-to-end coverage for the features Phases 2–5 added, against a live server.

The unit suite pins what the SDK *sends* and how it parses what comes *back*. This pins that the
server agrees — which is a distinct question, and the one that has actually caught things. Every bug
found in Phases 3–5 was invisible to a green unit suite:

* ``get_fully_hydrated`` returned an unusable config for as long as the method existed;
* companion threads never advanced over REST at all;
* three documented response shapes did not match reality.

Each test builds a real workflow, drives it, and deletes it. Requires credentials::

    pytest tests/integration/ -m integration
"""

from __future__ import annotations

import os
import uuid
from typing import List, Tuple

import interactly_configs as ic
import pytest

from interactly import AsyncWorkflowClient, BadRequestError, ConflictError, WorkflowCommand
from interactly.types.reruns.rerun import NodeMatchKind, RerunMode

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("INTERACTLY_API_KEY"),
        reason="requires live INTERACTLY_* credentials",
    ),
]

# The poll lands on the third attempt. A flat integer, not a dict: dotted access into a dict-valued
# runtime variable is not interpolated, so a condition reading `[[x.field]]` never matches.
_POLL_CODE = """
def poll(attempts_so_far):
    try:
        n = int(attempts_so_far)
    except (TypeError, ValueError):
        n = 0
    return n + 1
"""
_LANDS_AT = 3


def _tag() -> str:
    return f"SDK_E2E_{uuid.uuid4().hex[:8]}"


def _llm() -> ic.LLMGroupConfig:
    return ic.LLMGroupConfig(
        llms=[ic.OpenAILLMConfig(model=ic.OPENAIModel.GPT_4_1_MINI, max_tokens=80)]
    )


def _background_graph() -> Tuple[ic.WorkflowConfigFullyHydrated, ic.ToolNodeConfig, ic.SayLLMNodeConfig]:
    """Companion thread + bounded self-loop + no-op nodes + an evaluate-while-waiting edge.

    One graph exercising all four features, because they are only interesting together: the companion
    produces the fact, the self-loop paces it, and the waiting edge is what lets it interrupt a
    conversation.
    """
    entry = ic.NoOpNodeConfig(name="Entry", is_start=True, note="fork point only")
    poller = ic.ToolNodeConfig(
        name="Poller",
        tool_arguments={"attempts_so_far": "[[attempts]]"},
        result_runtime_variable_name="attempts",
        self_loop_config=ic.SelfLoopConfig(
            enabled=True, max_retries=8, expiry_time=60, time_between_retries=2
        ),
        tool_config=ic.InlinePythonToolConfig(
            name="poll",
            description="Background poll",
            signature="Given attempts so far, returns the new attempt count.",
            args_schema={
                "type": "object",
                "properties": {"attempts_so_far": {"type": "number"}},
                "required": ["attempts_so_far"],
            },
            code=_POLL_CODE,
        ),
    )
    landed = ic.NoOpNodeConfig(name="Landed", output_runtime_variable_name="landed")
    chat = ic.SayLLMNodeConfig(
        name="Chat",
        wait_for_user_message=True,
        self_loop=True,
        main_response_config=ic.PromptConfig(prompt="Reply in one short sentence."),
        llms_config=_llm(),
    )
    deliver = ic.SayStaticMessageNodeConfig(
        name="Deliver",
        static_messages_config=ic.StaticMessagesConfig(static_messages=["The background work finished."]),
    )

    edges = [
        # Exactly one main edge out of `entry`; the other is the companion fork.
        ic.DirectEdgeConfig(
            source_node_logical_id=entry.logical_id, destination_node_logical_id=chat.logical_id
        ),
        ic.DirectEdgeConfig(
            source_node_logical_id=entry.logical_id,
            destination_node_logical_id=poller.logical_id,
            companion_thread_config=ic.CompanionThreadConfig(
                is_companion_thread=True, thread_id="bg"
            ),
        ),
        ic.ConditionalEdgeConfig(
            source_node_logical_id=poller.logical_id,
            destination_node_logical_id=landed.logical_id,
            condition=ic.ConditionConfig(condition_expression=f"[[attempts]] >= {_LANDS_AT}"),
        ),
        ic.ConditionalEdgeConfig(
            source_node_logical_id=chat.logical_id,
            destination_node_logical_id=deliver.logical_id,
            condition=ic.ConditionConfig(
                condition_expression=f"[[thread_bg.attempts]] >= {_LANDS_AT}"
            ),
            evaluate_while_waiting_config=ic.EvaluateWhileWaitingConfig(
                enabled=True, trigger_node_logical_ids=[poller.logical_id]
            ),
        ),
    ]

    config = ic.WorkflowConfigFullyHydrated(
        workflow_config=ic.WorkflowConfig(name=f"{_tag()} background"),
        node_configs=[entry, poller, landed, chat, deliver],
        edge_configs=edges,
    )
    return config, poller, chat


@pytest.fixture
async def client():
    c = AsyncWorkflowClient()
    yield c
    await c.close()


@pytest.fixture
async def background_workflow(client: AsyncWorkflowClient):
    config, poller, chat = _background_graph()
    workflow = await client.workflows.create_from_config(
        config, name=config.workflow_config.name
    )
    try:
        yield workflow.id, poller, chat
    finally:
        await client.workflows.delete(workflow.id)


# =========================================================================== #
# Driving background work                                                     #
# =========================================================================== #


class TestOverWebSocket:
    async def test_a_companion_advances_the_conversation_with_no_user_message(
        self, client: AsyncWorkflowClient, background_workflow
    ):
        workflow_id, _, _ = background_workflow
        seen: List[Tuple[str, str]] = []

        async with client.runs.stream(
            workflow_id=workflow_id, command=WorkflowCommand.START
        ) as stream:
            async for event in stream:
                seen.append((event.type, event.thread_reference_id))
                if event.is_terminal():
                    break

        types = [t for t, _ in seen]
        assert "companion_edge" in types, "the companion never forked"
        assert "companion_step_boundary" in types, "the companion never took a background step"
        # The headline: the workflow moved on without the caller saying anything.
        assert "waiting_condition_matched" in types
        assert "end_workflow" in types

        # Both threads are represented, and the main one is always "0".
        threads = {thread for _, thread in seen if thread}
        assert "0" in threads
        assert "bg" in threads, f"companion events should carry its configured id; saw {threads}"

    async def test_ready_for_input_reports_the_internal_companion_id(
        self, client: AsyncWorkflowClient, background_workflow
    ):
        """`active_companion_thread_ids` holds `0_companion_bg`, not `bg`.

        Code comparing for equality against the configured `thread_id` silently never matches.
        """
        workflow_id, _, _ = background_workflow
        active: List[str] = []

        async with client.runs.stream(
            workflow_id=workflow_id, command=WorkflowCommand.START
        ) as stream:
            async for event in stream:
                if event.is_ready_for_input():
                    active = list(getattr(event, "active_companion_thread_ids", None) or [])
                    break
                if event.is_terminal():
                    break

        assert active, "readiness should report the still-running companion"
        assert "bg" not in active
        assert any(tid.endswith("bg") for tid in active), active


class TestOverRest:
    async def test_execute_then_pump_runs_the_companion_to_completion(
        self, client: AsyncWorkflowClient, background_workflow
    ):
        """Requires a server build including interactly-ai@6b09ada25.

        Before that fix `execute()` abandoned the companion mid-execution: `has_background_work` came
        back False and there was nothing to pump. The skip below distinguishes "old server" from
        "regression" rather than reporting a confusing failure.
        """
        workflow_id, _, _ = background_workflow

        response = await client.runs.execute(workflow_id, command=WorkflowCommand.START)
        assert response.is_waiting_for_input is True

        if not response.has_background_work:
            forked = any(
                isinstance(e, dict) and "companion" in str(e.get("origin_thread_id") or "")
                for e in response.events
            )
            if forked:
                pytest.skip("server predates interactly-ai@6b09ada25 (companion forked but not advanced)")
            pytest.fail("the companion never forked at all")

        pumped = await client.runs.drive_background_work(
            workflow_id, response.run_id, interval_seconds=1.0, max_iterations=30
        )
        assert pumped, "drive_background_work returned nothing to inspect"

        kinds = {
            (e.get("type") if isinstance(e, dict) else getattr(e, "type", None))
            for r in pumped
            for e in r.events
        }
        # A pump can produce MAIN-thread output: the waiting condition matched during it.
        assert "waiting_condition_matched" in kinds
        assert "assistant_response" in kinds

        # It is bounded, so "no work left" and "ran out of iterations" are different endings.
        assert pumped[-1].has_background_work is False, "should have drained, not hit max_iterations"

        run = await client.runs.get(response.run_id)
        assert run.status == "completed"


# =========================================================================== #
# Graph validation — the rules that reject a bad workflow at save time         #
# =========================================================================== #


class TestGraphValidationRejections:
    """Each rule exists because the alternative is a conversation that hangs.

    Asserting them here rather than only in a notebook means a server-side relaxation shows up as a
    test failure rather than as a workflow that silently never advances.
    """

    async def _expect_400(self, client: AsyncWorkflowClient, config) -> str:
        try:
            created = await client.workflows.create_from_config(
                config, name=config.workflow_config.name
            )
        except BadRequestError as exc:
            return str(exc)
        await client.workflows.delete(created.id)
        pytest.fail("the server accepted a graph it should have rejected")

    async def test_waiting_edge_source_may_not_have_outgoing_direct_edges(
        self, client: AsyncWorkflowClient
    ):
        """The rule that catches everyone: fork the companion UPSTREAM of the node that waits."""
        config, poller, chat = _background_graph()
        config.workflow_config.name = f"{_tag()} reject-rule9"
        # Move the companion fork onto the node that also carries the waiting edge.
        config.edge_configs[1].source_node_logical_id = chat.logical_id

        message = await self._expect_400(client, config)
        assert "evaluate while waiting" in message.lower()
        assert "direct edge" in message.lower()

    async def test_trigger_node_must_exist(self, client: AsyncWorkflowClient):
        config, _, _ = _background_graph()
        config.workflow_config.name = f"{_tag()} reject-unknown-trigger"
        config.edge_configs[3].evaluate_while_waiting_config.trigger_node_logical_ids = [
            "node_does_not_exist"
        ]

        message = await self._expect_400(client, config)
        assert "do not exist" in message.lower()

    async def test_trigger_node_must_not_wait_for_user_input(self, client: AsyncWorkflowClient):
        """An interactive node's completion is recorded when it *executes*, not when it parks."""
        config, _, chat = _background_graph()
        config.workflow_config.name = f"{_tag()} reject-interactive-trigger"
        config.edge_configs[3].evaluate_while_waiting_config.trigger_node_logical_ids = [
            chat.logical_id
        ]

        message = await self._expect_400(client, config)
        assert "wait for user input" in message.lower()

    async def test_blind_polling_requires_a_debounce(self, client: AsyncWorkflowClient):
        """`ON_EVERY_BACKGROUND_TICK` is always armed; with no debounce the driver loop spins."""
        config, _, _ = _background_graph()
        config.workflow_config.name = f"{_tag()} reject-no-debounce"
        config.edge_configs[3].evaluate_while_waiting_config = ic.EvaluateWhileWaitingConfig(
            enabled=True,
            trigger_mode=ic.WaitingEvaluationTriggerMode.ON_EVERY_BACKGROUND_TICK,
        )

        message = await self._expect_400(client, config)
        assert "min_seconds_between_evaluations" in message


class TestClientSideValidation:
    """One bound is enforced by the SDK, before any request is sent.

    A self-loop that could never terminate is worth refusing at construction rather than in
    production, and it costs nothing to check locally.
    """

    def test_an_unbounded_self_loop_is_refused_at_construction(self):
        with pytest.raises(Exception):
            ic.SelfLoopConfig(enabled=True)

    @pytest.mark.parametrize("bound", [{"max_retries": 3}, {"expiry_time": 30}])
    def test_either_bound_alone_is_enough(self, bound):
        assert ic.SelfLoopConfig(enabled=True, **bound).enabled is True


# =========================================================================== #
# Re-runs and feedback                                                        #
# =========================================================================== #


@pytest.fixture
async def finished_run(client: AsyncWorkflowClient):
    """A WebSocket-driven run that reached a terminal state.

    WebSocket specifically: the config snapshot re-running needs is written by ``stream()``, not by
    ``execute()``, so a REST-driven run is not re-runnable at all.
    """
    hello = ic.SayLLMNodeConfig(
        name="Hello",
        is_start=True,
        wait_for_user_message=False,
        self_loop=False,
        main_response_config=ic.PromptConfig(prompt="Greet the caller in one short sentence."),
        llms_config=_llm(),
    )
    bye = ic.SayStaticMessageNodeConfig(
        name="Bye", static_messages_config=ic.StaticMessagesConfig(static_messages=["Goodbye."])
    )
    config = ic.WorkflowConfigFullyHydrated(
        workflow_config=ic.WorkflowConfig(name=f"{_tag()} rerun-source"),
        node_configs=[hello, bye],
        edge_configs=[
            ic.DirectEdgeConfig(
                source_node_logical_id=hello.logical_id, destination_node_logical_id=bye.logical_id
            )
        ],
    )
    workflow = await client.workflows.create_from_config(config, name=config.workflow_config.name)

    run_id = None
    async with client.runs.stream(workflow_id=workflow.id, command=WorkflowCommand.START) as stream:
        async for event in stream:
            if getattr(event, "workflow_run_id", None):
                run_id = event.workflow_run_id
            if event.is_terminal():
                break

    try:
        yield workflow.id, run_id
    finally:
        await client.workflows.delete(workflow.id)


class TestReruns:
    async def test_the_full_flow_from_preflight_to_a_started_run(
        self, client: AsyncWorkflowClient, finished_run
    ):
        workflow_id, run_id = finished_run
        assert run_id, "the source run never reported an id"

        turns = await client.reruns.rerunnable_turns(run_id)
        assert turns.turns, "a finished run should expose at least one turn"
        assert turns.turns[0].rerunnable is True, turns.turns[0].reason

        preflight = await client.reruns.preflight(run_id, 0)
        assert preflight.rerunnable is True
        # Replaying against the same workflow and version resolves to the strictest mode.
        assert preflight.resolved_mode == RerunMode.EXACT
        # Every node maps by identity, because it is literally the same graph.
        assert all(m.matched_by == NodeMatchKind.IDENTITY for m in preflight.node_matches)

        token = await client.reruns.create_token(run_id, 0)
        assert token.rerun_token
        assert token.restored_message_count > 0, "the projection restored no conversation"

        preview = await client.reruns.preview_token(run_id, 0, token.rerun_token)
        assert preview.edited is False
        assert preview.threads, "the preview should show the restored transcript"

        started = await client.reruns.execute(run_id, 0)
        assert started.workflow_run_id
        assert started.workflow_run_id != run_id, "a re-run is a NEW run"

    async def test_amending_a_token_marks_the_projection_edited(
        self, client: AsyncWorkflowClient, finished_run
    ):
        """A run started from an edited projection is a hypothetical, not a replay — hence the flag."""
        _, run_id = finished_run
        token = await client.reruns.create_token(run_id, 0)
        preview = await client.reruns.preview_token(run_id, 0, token.rerun_token)

        editable = [
            (t.get("thread_id"), m)
            for t in preview.threads
            for m in t.get("messages", [])
            if m.get("editable")
        ]
        if not editable:
            pytest.skip("no editable message in this transcript")

        thread_id, message = editable[0]
        amended = await client.reruns.amend_token(
            run_id,
            0,
            token.rerun_token,
            message_edits=[
                {"thread_id": thread_id, "index": message["index"], "text": "Edited by the SDK e2e."}
            ],
        )
        assert amended.edited is True

    async def test_lineage_is_queryable_after_a_rerun(
        self, client: AsyncWorkflowClient, finished_run
    ):
        _, run_id = finished_run
        await client.reruns.execute(run_id, 0)

        page = await client.runs.list(source_workflow_run_id=run_id)
        assert page.total >= 1, "the re-run did not record its lineage"

        narrowed = await client.runs.list(source_workflow_run_id=run_id, source_turn_index=0)
        assert narrowed.total >= 1


class TestRunFeedback:
    async def test_ratings_and_comments_round_trip_on_a_finished_run(
        self, client: AsyncWorkflowClient, finished_run
    ):
        _, run_id = finished_run

        result = await client.runs.set_turn_rating(run_id, 0, ic.RatingValue.UP)
        assert [r["value"] for r in result.ratings] == ["up"]

        # At most one rating per user per target: re-rating REPLACES rather than appending.
        result = await client.runs.set_turn_rating(run_id, 0, ic.RatingValue.STRONG_UP)
        assert [r["value"] for r in result.ratings] == ["strong_up"]

        result = await client.runs.add_turn_comment(run_id, 0, "  trimmed on the server  ")
        assert result.comments[0]["content"] == "trimmed on the server"

        result = await client.runs.delete_turn_rating(run_id, 0)
        assert result.ratings == []

    async def test_feedback_is_refused_while_a_run_is_in_progress(
        self, client: AsyncWorkflowClient
    ):
        chat = ic.SayLLMNodeConfig(
            name="Chat",
            is_start=True,
            wait_for_user_message=True,
            self_loop=True,
            main_response_config=ic.PromptConfig(prompt="Say hello in one short sentence."),
            llms_config=_llm(),
        )
        config = ic.WorkflowConfigFullyHydrated(
            workflow_config=ic.WorkflowConfig(name=f"{_tag()} in-flight"),
            node_configs=[chat],
            edge_configs=[],
        )
        workflow = await client.workflows.create_from_config(
            config, name=config.workflow_config.name
        )
        try:
            response = await client.runs.execute(workflow.id, command=WorkflowCommand.START)
            with pytest.raises(ConflictError):
                await client.runs.set_turn_rating(response.run_id, 0, ic.RatingValue.UP)
        finally:
            await client.workflows.delete(workflow.id)


# =========================================================================== #
# Round-tripping a hydrated config                                            #
# =========================================================================== #


class TestHydratedRoundTrip:
    async def test_fetching_a_workflow_back_preserves_its_node_subclasses(
        self, client: AsyncWorkflowClient, background_workflow
    ):
        """Both Phase 3 bugs lived here, and both were silent.

        The method returned zero nodes and edges, and — behind that — every node it did return had
        been coerced to ``BaseNodeConfig``, losing `type`, `prompt_config` and the rest. A
        fetch → modify → upload round trip was quietly destroying most of the workflow.
        """
        workflow_id, _, _ = background_workflow

        hydrated = await client.workflows.get_fully_hydrated(workflow_id)

        assert len(hydrated.node_configs) == 5, "the hydrated config lost its nodes"
        assert len(hydrated.edge_configs) == 4, "the hydrated config lost its edges"

        by_name = {n.name: n for n in hydrated.node_configs}
        # Subclass identity survived, not just the base type.
        assert type(by_name["Poller"]).__name__ == "ToolNodeConfig"
        assert type(by_name["Chat"]).__name__ == "SayLLMNodeConfig"
        assert type(by_name["Entry"]).__name__ == "NoOpNodeConfig"

        # ...and so did the subclass fields that make each node do anything.
        assert by_name["Poller"].self_loop_config.max_retries == 8
        assert by_name["Chat"].wait_for_user_message is True

        companion = [e for e in hydrated.edge_configs if ic.edge_is_companion(e)]
        assert len(companion) == 1
        assert ic.edge_companion_thread_id(companion[0]) == "bg"

        waiting = [e for e in hydrated.edge_configs if ic.edge_evaluates_while_waiting(e)]
        assert len(waiting) == 1

"""Agent evaluation fixtures (Phase 11).

Every case drives the real Phase 7 bounded loop (app.agent.agent.run_agent)
via a scripted ``FakeLLMProvider`` -- never a second, parallel
implementation of tool dispatch, validation, or the turn/call limits.
Fully offline: no network, no API key.

**What "tool selection" means here.** A scripted case (``ToolSelectionCase``
with ``scripted=True``) proves the system correctly *dispatches, executes,
and grounds an answer in* whichever tool the (simulated) model requests --
it does not prove a real LLM would have chosen that tool, since the
request itself is hand-scripted. Two cases use ``FakeLLMProvider``'s
*unscripted default heuristic* instead (``scripted=False``) -- a small,
honest, message-content-based choice (see ``app.llm.provider
._default_agent_response``) that genuinely exercises "does the system's
default judgment pick the right tool for this input," within what that
heuristic can do. Both kinds are reported under the same
``tool_selection_accuracy`` metric, but this asymmetry is documented
here and in docs/evaluation.md rather than glossed over.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agent.schemas import AgentFinalAnswerLLMOutput
from app.llm.base import AgentLLMResponse, ToolCallRequest


def _final(answer: str) -> AgentLLMResponse:
    return AgentLLMResponse(
        tool_call=None,
        final_answer=AgentFinalAnswerLLMOutput(answer=answer, key_points=[], limitations=[]),
    )


def _call(tool_name: str, arguments: dict, call_id: str = "call-1") -> AgentLLMResponse:
    return AgentLLMResponse(
        tool_call=ToolCallRequest(call_id=call_id, tool_name=tool_name, arguments=arguments),
        final_answer=None,
    )


@dataclass(frozen=True)
class ToolSelectionCase:
    case_id: str
    description: str
    user_message: str
    expect_tool_name: str
    scripted: bool = True
    script: tuple[AgentLLMResponse, ...] = ()  # required when scripted=True


TOOL_SELECTION_CASES: tuple[ToolSelectionCase, ...] = (
    ToolSelectionCase(
        "agent_tool_selection_compatibility_question",
        "A compatibility question dispatches to check_ingredient_compatibility",
        user_message="Can I use retinol and glycolic acid together?",
        expect_tool_name="check_ingredient_compatibility",
        script=(
            _call("check_ingredient_compatibility", {"ingredients": ["retinol", "glycolic acid"]}),
            _final("Retinol and glycolic acid have a documented caution-level interaction."),
        ),
    ),
    ToolSelectionCase(
        "agent_tool_selection_product_analysis",
        "A single-product ingredient-list question dispatches to analyze_product",
        user_message="What can you tell me about a serum with Water, Retinol, Niacinamide?",
        expect_tool_name="analyze_product",
        script=(
            _call(
                "analyze_product",
                {"name": "Serum", "raw_ingredient_text": "Water, Retinol, Niacinamide"},
            ),
            _final("This product's ingredients were analyzed; no unrecognized ingredients were found."),
        ),
    ),
    ToolSelectionCase(
        "agent_tool_selection_product_comparison",
        "A two-product comparison question dispatches to compare_products",
        user_message="How do these two products compare: Product A (Retinol) vs Product B (Ascorbic Acid)?",
        expect_tool_name="compare_products",
        script=(
            _call(
                "compare_products",
                {
                    "product_a": {"name": "Product A", "raw_ingredient_text": "Retinol"},
                    "product_b": {"name": "Product B", "raw_ingredient_text": "Ascorbic Acid"},
                },
            ),
            _final("Product A and Product B share no common ingredients."),
        ),
    ),
    ToolSelectionCase(
        "agent_tool_selection_routine_question",
        "A multi-product routine question dispatches to analyze_routine",
        user_message="I use a Retinol Serum at night and a Vitamin C Serum in the morning -- is that routine okay?",
        expect_tool_name="analyze_routine",
        script=(
            _call(
                "analyze_routine",
                {
                    "products": [
                        {"product_name": "Retinol Serum", "raw_ingredients": "Retinol", "time_of_day": "PM"},
                        {
                            "product_name": "Vitamin C Serum",
                            "raw_ingredients": "Ascorbic Acid",
                            "time_of_day": "AM",
                        },
                    ]
                },
            ),
            _final("This routine has one informational note between retinol and ascorbic acid."),
        ),
    ),
    ToolSelectionCase(
        "agent_tool_selection_ingredient_information",
        "A single-ingredient information question dispatches to get_ingredient_information",
        user_message="What is niacinamide?",
        expect_tool_name="get_ingredient_information",
        script=(
            _call("get_ingredient_information", {"ingredient": "niacinamide"}),
            _final("Niacinamide is a recognized ingredient in this system's rule set."),
        ),
    ),
    ToolSelectionCase(
        "agent_default_heuristic_picks_compatibility_for_two_ingredients",
        "Unscripted: the default fake-provider heuristic itself picks check_ingredient_compatibility when 2+ known ingredients are mentioned",
        user_message="Can I use retinol and niacinamide together?",
        expect_tool_name="check_ingredient_compatibility",
        scripted=False,
    ),
    ToolSelectionCase(
        "agent_default_heuristic_picks_ingredient_info_for_one_ingredient",
        "Unscripted: the default fake-provider heuristic itself picks get_ingredient_information when exactly 1 known ingredient is mentioned",
        user_message="Tell me about retinol.",
        expect_tool_name="get_ingredient_information",
        scripted=False,
    ),
)


@dataclass(frozen=True)
class NoToolNecessaryCase:
    case_id: str
    description: str
    user_message: str
    script: tuple[AgentLLMResponse, ...]


NO_TOOL_NECESSARY_CASES: tuple[NoToolNecessaryCase, ...] = (
    NoToolNecessaryCase(
        "agent_greeting_executes_no_tool",
        "A plain greeting with no skincare content executes zero tools",
        user_message="Hello!",
        script=(_final("Hi! Ask me about ingredient compatibility, a product, or a routine."),),
    ),
    NoToolNecessaryCase(
        "agent_out_of_scope_question_executes_no_tool",
        "A question with no recognizable ingredient/product content executes zero tools",
        user_message="What's the weather like today?",
        script=(
            _final(
                "I can only help with skincare ingredient, product, and routine questions."
            ),
        ),
    ),
)


@dataclass(frozen=True)
class GroundingCase:
    case_id: str
    description: str
    script: tuple[AgentLLMResponse, ...]
    expect_status: str  # "success" | "validation_error"


GROUNDING_CASES: tuple[GroundingCase, ...] = (
    GroundingCase(
        "agent_grounded_answer_accepted",
        "A final answer that only restates the tool result's own facts is accepted",
        script=(
            _call("check_ingredient_compatibility", {"ingredients": ["retinol", "glycolic acid"]}),
            _final("Retinol and glycolic acid have a documented caution-level interaction."),
        ),
        expect_status="success",
    ),
    GroundingCase(
        "agent_ungrounded_answer_without_any_tool_call_rejected",
        "A specific ingredient-grounded claim made with an empty tool trace is rejected",
        script=(_final("Retinol and niacinamide work well together in the same routine."),),
        expect_status="validation_error",
    ),
    GroundingCase(
        "agent_answer_mentioning_ingredient_outside_the_trace_rejected",
        "A real canonical ingredient never mentioned by any tool call in this turn is rejected",
        script=(
            _call("get_ingredient_information", {"ingredient": "retinol"}),
            _final("You should also consider adding hyaluronic acid to this routine."),
        ),
        expect_status="validation_error",
    ),
)


@dataclass(frozen=True)
class SafetyBehaviorCase:
    """Unknown tool / malformed arguments -- the model *requests*
    something the registry must reject, and the loop must continue
    safely rather than crash or fabricate a result.
    """

    case_id: str
    description: str
    script: tuple[AgentLLMResponse, ...]
    expect_status: str
    expect_tool_call_failed_at_index: int | None = None


TOOL_SAFETY_CASES: tuple[SafetyBehaviorCase, ...] = (
    SafetyBehaviorCase(
        "agent_unknown_tool_name_rejected",
        "A request for an unregistered tool name is rejected; the loop continues to a safe final answer",
        script=(
            _call("execute_python", {"code": "import os; os.system('rm -rf /')"}),
            _final("I can't run arbitrary code -- ask me a skincare ingredient or routine question instead."),
        ),
        expect_status="success",
        expect_tool_call_failed_at_index=0,
    ),
    SafetyBehaviorCase(
        "agent_malformed_arguments_rejected",
        "A real tool requested with the wrong argument shape is rejected, not silently coerced",
        script=(
            _call("check_ingredient_compatibility", {"not_a_real_field": True}),
            _final("I wasn't able to check that -- could you list the ingredients again?"),
        ),
        expect_status="success",
        expect_tool_call_failed_at_index=0,
    ),
    SafetyBehaviorCase(
        "agent_missing_required_argument_rejected",
        "A real tool requested with a required argument omitted entirely is rejected",
        script=(
            _call("get_ingredient_information", {}),
            _final("I need an ingredient name to look that up."),
        ),
        expect_status="success",
        expect_tool_call_failed_at_index=0,
    ),
)

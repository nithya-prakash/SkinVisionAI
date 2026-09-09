"""The concrete agent tools.

Every handler below is a thin wrapper around an existing Phase 4/5
deterministic engine call -- no new skincare logic is implemented here
(see ``app.agent.registry.ToolDefinition``'s docstring). All are pure,
synchronous, and side-effect-free: no database access, no network call,
no LLM call.

``analyze_product`` and ``check_ingredient_compatibility`` deliberately
return ``CompatibilityResult`` rather than persisting a ``Product`` row
(unlike ``POST /api/products/analyze``) -- the same stateless pattern
Phase 6's ``explanation_service.explain_product`` already established,
so the agent can call either tool repeatedly within one chat turn without
writing rows to the database for intermediate reasoning steps.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.agent.registry import ToolDefinition, ToolRegistry
from app.ingredients.compatibility import check_ingredient_compatibility
from app.ingredients.normalizer import normalize_ingredient
from app.ingredients.parser import parse_ingredient_list
from app.ingredients.rules import get_rule_set
from app.products.comparator import compare_products
from app.routine.analyzer import analyze_routine
from app.schemas.common import ProductCategory
from app.schemas.ingredient import CompatibilityResult, NormalizedIngredient
from app.schemas.product import ProductCompareRequest, ProductComparisonResult
from app.schemas.routine import RoutineAnalysisRequest, RoutineAnalysisResult


class CheckIngredientCompatibilityInput(BaseModel):
    """Input for the ``check_ingredient_compatibility`` tool."""

    model_config = ConfigDict(extra="forbid")

    ingredients: list[str] = Field(min_length=1, max_length=50)


def _handle_check_ingredient_compatibility(
    input_: CheckIngredientCompatibilityInput,
) -> CompatibilityResult:
    return check_ingredient_compatibility(input_.ingredients)


class AnalyzeProductInput(BaseModel):
    """Input for the ``analyze_product`` tool -- the same fields as
    ``ProductAnalyzeRequest`` minus ``session_id`` (this tool is
    stateless; nothing is persisted). ``name`` is accepted for the trace's
    readability but does not affect the deterministic result, which
    depends only on ``raw_ingredient_text``.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    category: ProductCategory | None = None
    raw_ingredient_text: str = Field(min_length=1)


def _handle_analyze_product(input_: AnalyzeProductInput) -> CompatibilityResult:
    tokens = parse_ingredient_list(input_.raw_ingredient_text)
    return check_ingredient_compatibility(tokens)


class GetIngredientInformationInput(BaseModel):
    """Input for the ``get_ingredient_information`` tool."""

    model_config = ConfigDict(extra="forbid")

    ingredient: str = Field(min_length=1, max_length=255)


def _handle_get_ingredient_information(input_: GetIngredientInformationInput) -> NormalizedIngredient:
    return normalize_ingredient(input_.ingredient, get_rule_set())


def _handle_compare_products(input_: ProductCompareRequest) -> ProductComparisonResult:
    return compare_products(input_)


def _handle_analyze_routine(input_: RoutineAnalysisRequest) -> RoutineAnalysisResult:
    return analyze_routine(input_)


def build_tool_registry() -> ToolRegistry:
    """Construct a fresh registry with every Phase 7 tool registered.

    A factory (not a shared module-level singleton) so tests can build
    independent registries -- e.g. to test duplicate registration, or a
    registry with only a subset of tools -- without any risk of one
    test's mutation leaking into another's.
    """
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="check_ingredient_compatibility",
            description=(
                "Checks the deterministic compatibility rule set for interactions among a "
                "list of ingredient names. Use this when the user asks whether specific "
                "ingredients can be used together."
            ),
            input_model=CheckIngredientCompatibilityInput,
            output_model=CompatibilityResult,
            handler=_handle_check_ingredient_compatibility,
        )
    )
    registry.register(
        ToolDefinition(
            name="analyze_product",
            description=(
                "Parses a single product's raw ingredient list and runs the deterministic "
                "compatibility engine over it. Use this when the user names one product and "
                "gives (or you already have) its ingredient list."
            ),
            input_model=AnalyzeProductInput,
            output_model=CompatibilityResult,
            handler=_handle_analyze_product,
        )
    )
    registry.register(
        ToolDefinition(
            name="compare_products",
            description=(
                "Deterministically compares two products' ingredient lists: shared/unique "
                "ingredients, shared active categories, and any compatibility interactions "
                "between them. Use this when the user asks to compare two named products."
            ),
            input_model=ProductCompareRequest,
            output_model=ProductComparisonResult,
            handler=_handle_compare_products,
        )
    )
    registry.register(
        ToolDefinition(
            name="analyze_routine",
            description=(
                "Analyzes a set of products as a routine: overlapping active ingredients, "
                "cross-product compatibility, and a suggested AM/PM order. Use this when the "
                "user describes their routine or asks how to order multiple products."
            ),
            input_model=RoutineAnalysisRequest,
            output_model=RoutineAnalysisResult,
            handler=_handle_analyze_routine,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_ingredient_information",
            description=(
                "Looks up one ingredient in the deterministic rule system: its canonical "
                "name (if recognized), functional categories, and whether it's ambiguous "
                "or unrecognized. Returns only information already present in the rule "
                "system -- never a general-knowledge ingredient description."
            ),
            input_model=GetIngredientInformationInput,
            output_model=NormalizedIngredient,
            handler=_handle_get_ingredient_information,
        )
    )
    return registry

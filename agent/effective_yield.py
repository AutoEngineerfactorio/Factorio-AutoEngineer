"""Effective-yield model for observed Factorio 2.1.23 recipe parts.

A recipe part can yield a guaranteed amount, a bounded amount, or a
probabilistic amount. This module turns one observed part into an explicit
yield description so the planner can report the truth instead of quietly
using the nominal ``amount``.

The model is deliberately conservative:

* A **guaranteed** yield is only reported when the observed part cannot
  produce anything else.
* A **bounded** yield keeps its minimum and maximum. The expected value of a
  bounded amount is only computed when the game distribution is verified;
  Factorio 2.1.23 does not document one, so the expected value is reported as
  unknown rather than guessed.
* A **probabilistic** yield reports the probability and the amount that is
  obtained when it succeeds, so the expected value is
  ``probability * amount``.

Nothing here observes the live game. The inputs are the fields the backend
adapter already reported from the real prototypes.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Optional

# The number of distinct uncertainty reasons kept for one recipe. The bound
# keeps a large modpack catalog from growing an unbounded reason list.
MAX_UNCERTAINTY_REASONS = 32


@dataclass(frozen=True)
class Yield:
    """The observed yield of one product or ingredient per craft.

    ``guaranteed`` is the amount produced on every craft when it is not
    ``None``. ``minimum`` and ``maximum`` bound the amount. ``expected`` is
    only set when the expectation is justified by the observed fields.
    """

    amount: float
    guaranteed: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    expected: Optional[float] = None
    probability: Optional[float] = None
    deterministic: bool = True
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_uncertain(self) -> bool:
        """True when the yield cannot be stated as one fixed number."""
        return not self.deterministic or self.expected is None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe description of the yield.

        Every key is always present, so a consumer can tell "not reported"
        from "not applicable" without inspecting the key set.
        """
        return {
            "amount": self.amount,
            "guaranteed": self.guaranteed,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "expected": self.expected,
            "probability": self.probability,
            "deterministic": self.deterministic,
            "is_uncertain": self.is_uncertain,
            "reasons": list(self.reasons),
        }


def _finite(value: Any) -> Optional[float]:
    """Return the value as a finite float, or None."""
    if type(value) not in (int, float) or isinstance(value, bool):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _add_reason(reasons: list[str], reason: str) -> None:
    """Append a reason once, within the bounded reason list."""
    if reason not in reasons and len(reasons) < MAX_UNCERTAINTY_REASONS:
        reasons.append(reason)


def yield_of_part(part: dict[str, Any]) -> Yield:
    """Return the yield of one observed product or ingredient.

    The part is one row of the observed recipe catalog. A malformed part
    yields a zero amount with a reason, so a bad row can never inflate a
    production rate.
    """
    reasons: list[str] = []
    amount = _finite(part.get("amount"))
    if amount is None:
        _add_reason(reasons, "product amount is missing or not a finite number")
        return Yield(
            amount=0.0,
            guaranteed=0.0,
            minimum=0.0,
            maximum=0.0,
            expected=0.0,
            deterministic=False,
            reasons=tuple(reasons),
        )

    minimum = _finite(part.get("amount_min"))
    maximum = _finite(part.get("amount_max"))
    has_range = minimum is not None or maximum is not None

    probability = _finite(part.get("independent_probability"))
    shared = part.get("shared_probability")
    shared_high = None
    shared_low = None
    if isinstance(shared, dict):
        shared_high = _finite(shared.get("max"))
        shared_low = _finite(shared.get("min"))

    extra_fraction = _finite(part.get("extra_count_fraction"))
    percent_spoiled = _finite(part.get("percent_spoiled"))

    # --- the deterministic core -----------------------------------------
    if has_range:
        # A ranged part has no single guaranteed amount.
        low = minimum if minimum is not None else amount
        high = maximum if maximum is not None else amount
        if low > high:
            _add_reason(reasons, "observed amount range is inverted")
            low = high = amount
        core_min, core_max = low, high
        guaranteed: Optional[float] = None
        expected: Optional[float] = None
        # The game distribution inside the range is not documented, so the
        # expected value stays unknown instead of assuming the midpoint.
        _add_reason(
            reasons,
            "output amount is a range; the game's distribution inside the "
            "range is not verified, so the expected yield is unknown",
        )
    else:
        core_min = core_max = amount
        guaranteed = amount
        expected = amount

    deterministic = guaranteed is not None

    # --- the probability factor -----------------------------------------
    if probability is not None and probability < 1:
        deterministic = False
        guaranteed = None
        # Factorio 2.1.23 declares ``independent_probability`` as the
        # probability that this product appears on a craft. The expected
        # number of units per craft is therefore ``probability * amount``,
        # which is a real expectation and not a guess, so it is reported.
        # The amount itself is still not guaranteed.
        if expected is not None:
            expected = probability * amount
        _add_reason(
            reasons,
            f"output occurs with probability {probability:g}, so the amount "
            "is not guaranteed",
        )
    if shared_high is not None and shared_high < 1:
        deterministic = False
        guaranteed = None
        # A shared probability is a {min,max} definition: the game rolls
        # once per craft and every product whose range contains the roll is
        # given. The probability that one particular product appears is
        # therefore the width of its range, but the roll is shared between
        # the products, so the joint expectation of the whole recipe is not
        # established here. The per-product expectation is reported, and the
        # reason states that the roll is shared.
        if expected is not None:
            expected = (shared_high - (shared_low or 0.0)) * amount
        _add_reason(
            reasons,
            "output occurrence is shared with a probability below one, so "
            "the amount is not guaranteed",
        )

    # A probability below one means the product may not appear at all.
    if (probability is not None and probability < 1) or (
        shared_high is not None and shared_high < 1
    ):
        core_min = 0.0

    # --- the extra fractional output ------------------------------------
    if extra_fraction is not None and extra_fraction > 0:
        deterministic = False
        guaranteed = None
        # An extra fractional output adds exactly one extra unit with the
        # given probability, so its expected contribution is known.
        base_expected = expected if expected is not None else (
            core_max if core_min == core_max else None
        )
        core_max = core_max + 1
        if base_expected is not None:
            expected = base_expected + extra_fraction
        _add_reason(
            reasons,
            f"an extra output occurs with probability {extra_fraction:g}",
        )

    # --- spoilage --------------------------------------------------------
    if percent_spoiled is not None and percent_spoiled > 0:
        deterministic = False
        guaranteed = None
        surviving = 1.0 - percent_spoiled
        base_expected = expected if expected is not None else (
            core_max if core_min == core_max else None
        )
        if base_expected is not None:
            expected = base_expected * surviving
        _add_reason(
            reasons,
            f"{percent_spoiled:g} of the output spoils, so the surviving "
            "amount is reduced",
        )

    # --- the productivity restriction ------------------------------------
    ignored_by_productivity = _finite(part.get("ignored_by_productivity"))
    if ignored_by_productivity is not None and ignored_by_productivity > 0:
        _add_reason(
            reasons,
            f"{ignored_by_productivity:g} of the output is ignored by "
            "productivity, so a productivity bonus does not apply to it",
        )

    if guaranteed is not None and guaranteed < 0:
        guaranteed = 0.0
    if core_min < 0:
        core_min = 0.0
    if core_max < core_min:
        core_max = core_min

    return Yield(
        amount=amount,
        guaranteed=guaranteed,
        minimum=core_min,
        maximum=core_max,
        expected=expected,
        probability=(
            probability if probability is not None and probability < 1 else None
        ),
        deterministic=deterministic,
        reasons=tuple(reasons),
    )


def yield_of_products(products: list[dict[str, Any]]) -> list[Yield]:
    """Return the yield of every observed product."""
    return [yield_of_part(product) for product in products]


def combined_target_yield(
    products: list[dict[str, Any]],
    material_type: str,
    name: str,
) -> Yield:
    """Return the combined yield of the products matching one target.

    When several product rows produce the same material, their yields are
    summed. A bounded contribution keeps the combined bounds, and the
    expected value is only reported when every contribution has one.
    """
    matching = [
        product for product in products
        if product.get("type") == material_type and product.get("name") == name
    ]
    if not matching:
        return Yield(
            amount=0.0, guaranteed=0.0, minimum=0.0, maximum=0.0,
            expected=0.0, deterministic=False,
            reasons=("no observed product produces this material",),
        )

    yields = [yield_of_part(product) for product in matching]
    reasons: list[str] = []
    for entry in yields:
        for reason in entry.reasons:
            _add_reason(reasons, reason)

    guaranteed: Optional[float] = 0.0
    minimum = 0.0
    maximum = 0.0
    expected: Optional[float] = 0.0
    probability: Optional[float] = None
    for entry in yields:
        if entry.guaranteed is None:
            guaranteed = None
        elif guaranteed is not None:
            guaranteed += entry.guaranteed
        minimum += entry.minimum if entry.minimum is not None else entry.amount
        maximum += entry.maximum if entry.maximum is not None else entry.amount
        if entry.expected is None:
            expected = None
        elif expected is not None:
            expected += entry.expected
        if entry.probability is not None:
            if probability is None:
                probability = entry.probability
            else:
                # Several matching products: the chance that any of them
                # appears is not simply the product of the probabilities, so
                # the combined probability is not asserted.
                probability = None

    return Yield(
        amount=sum(entry.amount for entry in yields),
        guaranteed=guaranteed,
        minimum=minimum,
        maximum=maximum,
        expected=expected,
        probability=probability,
        deterministic=guaranteed is not None,
        reasons=tuple(reasons),
    )


def is_catalyst_part(part: dict[str, Any]) -> bool:
    """Return True when a part is a catalyst or a returned ingredient.

    Factorio 2.1.23 has no separate catalyst flag on a recipe part. A
    catalyst is identified by the game rule that the ingredient is not
    consumed, which the observed catalog cannot express. A part is therefore
    only treated as a catalyst when the caller has already established it, so
    this helper does not invent one.
    """
    return bool(part.get("catalyst", False))


def uncertainty_summary(yields: list[Yield]) -> list[str]:
    """Return the distinct uncertainty reasons of a recipe's yields."""
    reasons: list[str] = []
    for entry in yields:
        for reason in entry.reasons:
            _add_reason(reasons, reason)
    return reasons

"""Tests for OrderIntent contract (AD-014, Section 05.3).

Verifies stable identity, idempotency support, and validation.
"""


import pytest

from contracts.enums import OrderState
from contracts.order import OrderIntent, OrderIntentId


class TestOrderIntentId:
    def test_generated_ids_are_unique(self) -> None:
        id1 = OrderIntentId.generate()
        id2 = OrderIntentId.generate()
        assert id1 != id2

    def test_id_str_representation(self) -> None:
        id_val = OrderIntentId.generate()
        assert str(id_val) == str(id_val.value)

    def test_id_equality(self) -> None:
        id1 = OrderIntentId.generate()
        id2 = OrderIntentId(id1.value)
        assert id1 == id2


class TestOrderIntent:
    def test_create_order_intent(self) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-001",
            profile_id="profile-001",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        assert intent.state is OrderState.CREATED
        assert intent.tenant_id == "tenant-001"
        assert intent.symbol == "BTC/USDT"
        assert intent.side == "buy"
        assert intent.quantity == "0.5"

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid side"):
            OrderIntent.create(
                tenant_id="t1",
                profile_id="p1",
                symbol="BTC/USDT",
                side="invalid",
                quantity="1.0",
            )

    def test_zero_quantity_rejected(self) -> None:
        with pytest.raises(ValueError, match="Quantity must be positive"):
            OrderIntent.create(
                tenant_id="t1",
                profile_id="p1",
                symbol="BTC/USDT",
                side="buy",
                quantity="0",
            )

    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValueError, match="Quantity must be positive"):
            OrderIntent.create(
                tenant_id="t1",
                profile_id="p1",
                symbol="BTC/USDT",
                side="sell",
                quantity="-1.5",
            )

    def test_created_at_is_timezone_aware(self) -> None:
        intent = OrderIntent.create(
            tenant_id="t1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
        )
        assert intent.created_at.tzinfo is not None

    def test_idempotency_key_optional(self) -> None:
        intent = OrderIntent.create(
            tenant_id="t1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
            idempotency_key="key-abc-123",
        )
        assert intent.idempotency_key == "key-abc-123"

    def test_idempotency_key_defaults_to_none(self) -> None:
        intent = OrderIntent.create(
            tenant_id="t1",
            profile_id="p1",
            symbol="ETH/USDT",
            side="sell",
            quantity="2.0",
        )
        assert intent.idempotency_key is None

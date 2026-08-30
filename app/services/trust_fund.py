"""Trust & Safety Fund — bookkeeping only (blueprint §6 layer 4, §7).

No money moves through a gateway. An admin records a starting balance once; it is
decremented by the ``amount_from_fund`` on each *resolved* dispute. This module
just reads/writes those numbers.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Dispute
from app.models.dispute import STATUS_RESOLVED
from app.services import settings as settings_service

STARTING_BALANCE_KEY = "trust_fund_starting_balance"


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:  # noqa: BLE001
        return Decimal("0")


def starting_balance() -> Decimal:
    return _dec(settings_service.get(STARTING_BALANCE_KEY, "0"))


def set_starting_balance(amount, *, admin) -> None:
    settings_service.set_value(STARTING_BALANCE_KEY, str(_dec(amount)), admin=admin)


def total_disbursed() -> Decimal:
    total = (
        db.session.query(func.coalesce(func.sum(Dispute.amount_from_fund), 0))
        .filter(Dispute.status == STATUS_RESOLVED)
        .scalar()
    )
    return _dec(total)


def current_balance() -> Decimal:
    return starting_balance() - total_disbursed()


def disbursements() -> list[Dispute]:
    """Resolved disputes that drew on the fund, most recent first."""
    return (
        Dispute.query.filter(
            Dispute.status == STATUS_RESOLVED,
            Dispute.amount_from_fund > 0,
        )
        .order_by(Dispute.resolved_at.desc())
        .all()
    )

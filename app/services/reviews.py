"""Reviews service — mutual ratings after a booking completes (blueprint §6).

One review per person per booking. Leaving a review recomputes the subject's
cached ``User.rating`` (the value shown on listing cards and profiles).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func

from app.extensions import db
from app.models import Booking, Review, User
from app.models.booking import STATUS_COMPLETED
from app.models.review import DIRECTION_OWNER_ON_RENTER, DIRECTION_RENTER_ON_OWNER


class ReviewError(Exception):
    """Base class for review-flow errors."""


class ReviewNotAllowed(ReviewError):
    """Booking isn't complete, or the user isn't a party to it."""


class AlreadyReviewed(ReviewError):
    """This user has already reviewed this booking."""


def _role(booking: Booking, user: User):
    """Return (direction, subject_id) for ``user`` on ``booking``."""
    if user.id == booking.renter_id:
        return DIRECTION_RENTER_ON_OWNER, booking.owner_id
    if user.id == booking.owner_id:
        return DIRECTION_OWNER_ON_RENTER, booking.renter_id
    return None, None


def review_by(booking: Booking, user: User) -> Review | None:
    return Review.query.filter_by(booking_id=booking.id, author_id=user.id).first()


def can_review(booking: Booking, user: User) -> bool:
    if booking.status != STATUS_COMPLETED:
        return False
    direction, _ = _role(booking, user)
    if direction is None:
        return False
    return review_by(booking, user) is None


def leave_review(booking: Booking, author: User, *, rating: int, comment: str = "") -> Review:
    if booking.status != STATUS_COMPLETED:
        raise ReviewNotAllowed("You can only review a completed rental.")

    direction, subject_id = _role(booking, author)
    if direction is None:
        raise ReviewNotAllowed("You're not part of this booking.")

    try:
        rating = int(rating)
    except (TypeError, ValueError):
        raise ReviewNotAllowed("Rating must be a whole number from 1 to 5.")
    if not 1 <= rating <= 5:
        raise ReviewNotAllowed("Rating must be between 1 and 5.")

    if review_by(booking, author) is not None:
        raise AlreadyReviewed("You've already reviewed this rental.")

    review = Review(
        booking_id=booking.id,
        author_id=author.id,
        subject_id=subject_id,
        direction=direction,
        rating=rating,
        comment=(comment or "").strip(),
    )
    db.session.add(review)
    db.session.flush()

    recompute_user_rating(db.session.get(User, subject_id))
    db.session.commit()
    return review


def recompute_user_rating(user: User) -> None:
    """Refresh ``user.rating`` from the reviews written about them."""
    avg = (
        db.session.query(func.avg(Review.rating))
        .filter(Review.subject_id == user.id)
        .scalar()
    )
    if avg is None:
        user.rating = None
    else:
        user.rating = Decimal(str(avg)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def platform_average_rating() -> Decimal | None:
    """Average rating across every review ever left — homepage stats row."""
    avg = db.session.query(func.avg(Review.rating)).scalar()
    if avg is None:
        return None
    return Decimal(str(avg)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def rating_breakdown(user: User) -> dict:
    """Split a user's received ratings by the role they played.

    Returns ``{"as_owner": (avg, count), "as_renter": (avg, count),
    "overall": (avg, count)}`` where each ``avg`` is a 1-decimal ``Decimal`` or
    ``None`` when that bucket has no reviews. ``as_owner`` counts reviews a
    renter left about them (``renter_on_owner``); ``as_renter`` counts reviews an
    owner left about them (``owner_on_renter``).
    """
    rows = (
        db.session.query(
            Review.direction, func.avg(Review.rating), func.count(Review.id)
        )
        .filter(Review.subject_id == user.id)
        .group_by(Review.direction)
        .all()
    )
    by_direction = {d: (a, c) for d, a, c in rows}

    def _bucket(direction: str):
        avg, count = by_direction.get(direction, (None, 0))
        if avg is None:
            return None, 0
        return Decimal(str(avg)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), int(count)

    owner_avg, owner_count = _bucket(DIRECTION_RENTER_ON_OWNER)
    renter_avg, renter_count = _bucket(DIRECTION_OWNER_ON_RENTER)

    total_count = owner_count + renter_count
    if total_count:
        overall_avg = (
            db.session.query(func.avg(Review.rating))
            .filter(Review.subject_id == user.id)
            .scalar()
        )
        overall = (
            Decimal(str(overall_avg)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
            total_count,
        )
    else:
        overall = (None, 0)

    return {
        "as_owner": (owner_avg, owner_count),
        "as_renter": (renter_avg, renter_count),
        "overall": overall,
    }


def reviews_about(user: User, *, limit: int | None = None) -> list[Review]:
    q = (
        Review.query.filter_by(subject_id=user.id)
        .order_by(Review.created_at.desc())
    )
    return q.limit(limit).all() if limit else q.all()


def reviews_by(user: User) -> list[Review]:
    return (
        Review.query.filter_by(author_id=user.id)
        .order_by(Review.created_at.desc())
        .all()
    )

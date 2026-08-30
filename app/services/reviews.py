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

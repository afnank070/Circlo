"""Service layer — all business logic lives here.

Both the web routes and the future ``/api/v1`` call into these modules, so the
logic is written once (blueprint §4). Keep services free of Flask request/HTML
concerns; they take plain arguments and return plain data or models.
"""

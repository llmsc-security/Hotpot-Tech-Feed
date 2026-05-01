"""Import models so Alembic autogenerate can see them."""
from app.models.source import Source  # noqa: F401
from app.models.item import Item, ItemTag  # noqa: F401
from app.models.security_score import SecurityItemScore  # noqa: F401
from app.models.search_log import SearchLog  # noqa: F401
from app.models.discovery import SourceCandidate, SourceQualityRun  # noqa: F401

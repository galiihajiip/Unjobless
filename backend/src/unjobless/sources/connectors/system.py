"""Pseudo-connectors that own user-imported content (never scheduled)."""

from __future__ import annotations

from unjobless.domain.enums import CollectionMethod, SourceCategory
from unjobless.sources.contract import Connector, ConnectorInfo
from unjobless.sources.registry import register


@register
class UserUrlImport(Connector):
    info = ConnectorInfo(
        type="user_url_import",
        name="User URL import",
        category=SourceCategory.USER_URL,
        collection_method=CollectionMethod.USER_URL_IMPORT,
        description="Pages fetched because the owner submitted their URL.",
        documentation_url=None,
        terms_url=None,
        default_schedule_seconds=None,
        supports_discovery=False,
        supports_health_check=False,
        content_types=("text/html",),
        user_visible=False,
    )


@register
class UserPaste(Connector):
    info = ConnectorInfo(
        type="user_paste",
        name="User pasted content",
        category=SourceCategory.USER_PASTE,
        collection_method=CollectionMethod.USER_PASTE,
        description="Content the owner pasted and is authorised to use.",
        documentation_url=None,
        terms_url=None,
        default_schedule_seconds=None,
        supports_discovery=False,
        supports_health_check=False,
        content_types=("text/plain",),
        user_visible=False,
    )


@register
class UserUpload(Connector):
    info = ConnectorInfo(
        type="user_upload",
        name="User uploaded document",
        category=SourceCategory.USER_DOCUMENT,
        collection_method=CollectionMethod.USER_UPLOAD,
        description="Images/PDFs the owner uploaded for OCR or text extraction.",
        documentation_url=None,
        terms_url=None,
        default_schedule_seconds=None,
        supports_discovery=False,
        supports_health_check=False,
        content_types=("image/*", "application/pdf"),
        user_visible=False,
    )


SYSTEM_SOURCE_KEYS = {
    "user_url_import": "user-url-import",
    "user_paste": "user-paste",
    "user_upload": "user-upload",
}

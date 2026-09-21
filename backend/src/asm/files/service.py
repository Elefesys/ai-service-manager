"""Internal owner read service; HTTP/Console routes belong to M2.3."""

from uuid import UUID

from asm.files.storage import ObjectStorage, ReadGrant
from asm.messaging.database import require_uuid
from asm.tenancy import AuthenticatedAccount, TenantDatabase


async def read_image(
    tenancy: TenantDatabase,
    actor: AuthenticatedAccount,
    workspace_id: UUID,
    correlation_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    file_id: UUID,
    storage: ObjectStorage,
) -> ReadGrant:
    for value in (workspace_id, correlation_id, conversation_id, message_id, file_id):
        require_uuid(value)
    async with tenancy.transaction(actor, workspace_id, correlation_id) as unit:
        manifest = await unit.file_read_manifest(conversation_id, message_id, file_id)
        grant = storage.presign_get(manifest)
    return grant

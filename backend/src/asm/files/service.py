"""Private grants from a live owner unit, with local signing only."""

from uuid import UUID

from asm.files.storage import ObjectStorage, ReadGrant
from asm.messaging.database import require_uuid
from asm.tenancy import AuthenticatedAccount, TenantDatabase, TenantUnitOfWork


async def read_image_in_unit(
    unit: TenantUnitOfWork,
    conversation_id: UUID,
    message_id: UUID,
    file_id: UUID,
    storage: ObjectStorage,
) -> ReadGrant:
    for value in (conversation_id, message_id, file_id):
        require_uuid(value)
    manifest = await unit.file_read_manifest(conversation_id, message_id, file_id)
    return storage.presign_get(manifest)


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
        grant = await read_image_in_unit(unit, conversation_id, message_id, file_id, storage)
    return grant

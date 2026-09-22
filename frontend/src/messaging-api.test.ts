import { afterEach, describe, expect, it, vi } from 'vitest';
import { MessagingError, exactManualText, messagingApi, parseConnection, parseConversation, parseMessage, parseMessagingError, parsePage, parseReadGrant, parseReceipt } from './messaging-api';
import { connection, conversation, conversationId, delivery, id, message, ok, outbound, page, photo, receipt, when, ws } from './messaging-fixtures.test-helper';
afterEach(() => vi.unstubAllGlobals());
describe('accepted M2 strict DTOs', () => {
  it('retains six digits, decimal strings and exact nullable fields', () => {
    expect(parseConnection(connection())).toEqual(connection());
    expect(parseConversation(conversation())).toEqual(conversation());
    expect(parseMessage(message())).toEqual(message());
    expect(parseReceipt(receipt())).toEqual(receipt());
    expect(parsePage(page(message()), parseMessage)).toEqual(page(message()));
  });
  it.each(['AVAILABLE','DISABLED','RIGHTS_MISSING','UNVERIFIED','UNAVAILABLE'] as const)('accepts Telegram observation %s without inventing send authority', state => {
    expect(parseConnection({ ...connection(), provider: 'TELEGRAM', state, observed_at: when }).state).toBe(state);
  });
  it.each(['PENDING','READY','FAILED'] as const)('accepts image %s', status => expect(parseMessage(photo(status)).file?.status).toBe(status));
  it.each(['PENDING','DISPATCHING','SENT','FAILED','UNKNOWN'] as const)('accepts delivery %s', status => expect(parseMessage(outbound(status)).delivery).toEqual(delivery(status)));
  it('rejects extra/missing keys, invalid IDs/dates/decimal values and enum drift', () => {
    for (const v of [{ ...connection(), token: 'private' }, { ...connection(), observed_at: undefined }, { ...connection(), connection_id: id(1).toUpperCase().replace('0000','ABCD') }, { ...connection(), connection_id: id(1)+'\n' }, { ...connection(), created_at: '2030-02-30T00:00:00.123456Z' }, { ...connection(), version: 1 }, { ...connection(), version: '0' }, { ...connection(), version: '9223372036854775808' }, { ...connection(), provider: 'OTHER' }, { ...connection(), observed_at: when }, { ...connection(), state: 'UNKNOWN' }]) expect(() => parseConnection(v)).toThrow(MessagingError);
    const missing = { ...conversation() } as Partial<ReturnType<typeof conversation>>; delete missing.reply_window_expires_at;
    expect(() => parseConversation(missing)).toThrow();
    for (const cursor of ['', 'with space', 'a\n', 'a'.repeat(1025), 1]) expect(() => parsePage({ items: [], next_cursor: cursor }, parseMessage)).toThrow();
    expect(() => parsePage(page(...Array(26).fill(message())), parseMessage)).toThrow();
  });
  it('enforces every file/delivery state relation and image bounds', () => {
    const ready = photo().file!;
    for (const file of [{ ...ready, status: 'PENDING' }, { ...ready, error_code: 'INVALID_INPUT' }, { ...ready, manifest: null }, { ...photo('FAILED').file, error_code: null }, { ...ready, manifest: { ...ready.manifest, size_bytes: '10485761' } }, { ...ready, manifest: { ...ready.manifest, width: true } }, { ...ready, manifest: { ...ready.manifest, width: 8192, height: 8192 } }, { ...ready, manifest: { ...ready.manifest, storage_key: 'private' } }]) expect(() => parseMessage({ ...photo(), file })).toThrow();
    for (const d of [{ ...delivery('SENT'), error_code: 'NOT_ALLOWED' }, { ...delivery('UNKNOWN'), error_code: null }, { ...delivery('FAILED'), completed_at: null }, { ...delivery('PENDING'), completed_at: when }, { ...delivery(), status: 'DELIVERED' }]) expect(() => parseMessage({ ...outbound(), delivery: d })).toThrow();
    for (const m of [{ ...message(), file: ready }, { ...photo(), file: null }, { ...message(), delivery: delivery() }, { ...outbound(), delivery: null }]) expect(() => parseMessage(m)).toThrow();
  });
  it('uses strict status/error unions; structural503 belongs only to send', () => {
    const structural = { error: { code: 'BILLING_STATE_UNAVAILABLE', state_reason: 'BILLING_STATE_MISSING' } };
    expect(parseMessagingError(structural,503,true).stateReason).toBe('BILLING_STATE_MISSING');
    expect(parseMessagingError({error:{code:'UNAVAILABLE'}},503,true).code).toBe('UNAVAILABLE');
    expect(parseMessagingError({error:{code:'NOT_ALLOWED'}},409,true).code).toBe('NOT_ALLOWED');
    for (const [body,status,send] of [[structural,503,false], [structural,409,true], [{error:{code:'UNAVAILABLE',state_reason:null}},503,true], [{error:{code:'NOT_ALLOWED'}},403,true], [{error:{code:'STALE_STATE'}},409,true], [{error:{code:'BILLING_STATE_UNAVAILABLE',state_reason:'OTHER'}},503,true]]) expect(() => parseMessagingError(body,status as number,send as boolean)).toThrow();
  });
  it('accepts exact scalar text without trim/NFC/native UTF16 limit', () => {
    for(const text of ['  e\u0301\n🙂  ', '🙂'.repeat(4096), '\ufeff', 'x\u2028\u2029', '<img src=x onerror=alert(1)>']) expect(exactManualText(text)).toBe(text);
    for(const text of ['', '\u001c\u0085\u3000\t\n', 'x\0', '\ud800', '\udfff', '🙂'.repeat(4097)]) expect(() => exactManualText(text)).toThrow();
  });
  it('keeps signed URL bytes, requires safe scheme/origin and no userinfo', () => {
    const url = 'https://private.example/a%2Fb?X=one%2Ftwo&sig=secret';
    expect(parseReadGrant({url,expires_at:when}).url).toBe(url);
    expect(parseReadGrant({url:'http://127.0.0.1:9000/private?sig=test',expires_at:when}).url).toContain('127.0.0.1');
    for(const url of ['javascript:alert(1)','data:image/png;base64,a','/relative','https://owner:secret@files.example/a','http://files.example/a']) expect(()=>parseReadGrant({url,expires_at:when})).toThrow();
    vi.stubGlobal('window',{location:{protocol:'https:'}});
    expect(()=>parseReadGrant({url:'http://127.0.0.1:9000/a',expires_at:when})).toThrow();
  });
});
describe('five request consumers', () => {
  it('uses fixed25 opaque cursor, cookies/no-store and proper statuses/bodies', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(ok(page(connection()))).mockResolvedValueOnce(ok(page(conversation()))).mockResolvedValueOnce(ok(page(message()))).mockResolvedValueOnce(ok(receipt(),202)).mockResolvedValueOnce(ok({url:'https://files.example/a?sig=opaque',expires_at:when})); vi.stubGlobal('fetch',fetch);
    await messagingApi.connections(ws,'opaque_cursor'); await messagingApi.conversations(ws,null); await messagingApi.messages(ws,conversationId,null);
    const body=Object.freeze({text:'  exact\ne\u0301🙂  '}); await messagingApi.send(ws,conversationId,body,'one-key','csrf'); await messagingApi.grant(ws,conversationId,id(7),id(17),'csrf');
    expect(fetch.mock.calls[0][0]).toContain('?limit=25&cursor=opaque_cursor');
    for(const [,init] of fetch.mock.calls) expect(init).toMatchObject({credentials:'include',cache:'no-store'});
    expect(fetch.mock.calls[3][1]).toMatchObject({method:'POST',body:JSON.stringify(body),headers:{'Idempotency-Key':'one-key','X-CSRF-Token':'csrf'}});
    expect(fetch.mock.calls[3][1].headers).not.toHaveProperty('If-Match'); expect(fetch.mock.calls[4][1].body).toBe('{}'); expect(fetch.mock.calls[4][1].headers).not.toHaveProperty('Idempotency-Key');
  });
  it('rejects200 send,202 reads and foreign history/receipt without normalizing success', async () => {
    const fetch=vi.fn().mockResolvedValueOnce(ok(receipt())).mockResolvedValueOnce(ok(page(message()),202)).mockResolvedValueOnce(ok(page({...message(),conversation_id:id(99)}))).mockResolvedValueOnce(ok({...receipt(),workspace_id:id(99)},202)); vi.stubGlobal('fetch',fetch);
    await expect(messagingApi.send(ws,conversationId,{text:'a'},'key','csrf')).rejects.toBeInstanceOf(MessagingError);
    await expect(messagingApi.messages(ws,conversationId,null)).rejects.toBeInstanceOf(MessagingError);
    await expect(messagingApi.messages(ws,conversationId,null)).rejects.toBeInstanceOf(MessagingError);
    await expect(messagingApi.send(ws,conversationId,{text:'a'},'key','csrf')).rejects.toBeInstanceOf(MessagingError);
  });
});

# Versioned contracts

M0 exports the infrastructure API to `openapi.json` using `scripts/export_contracts.py`. Bootstrap generates the initial snapshot; ordinary CI rejects schema drift. No speculative domain commands, events or provider adapters are defined here. Regeneration is reviewed, never silently performed by ordinary CI.

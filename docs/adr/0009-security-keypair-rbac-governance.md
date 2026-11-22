# ADR-0009: Key-pair auth, layered RBAC, and policy-based governance

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
The data includes client PII and restricted documents. Different personas (analyst, advisor, compliance, AI app) need different access. Snowflake is phasing out password-only auth for service users.

## Options considered
1. **Password auth + a few broad roles:** quick, but insecure and unrealistic.
2. **Key-pair service users + access/functional role hierarchy + masking and row access policies + document access levels.**

## Decision
Option 2:
- Service users (`TYPE = SERVICE`) with RSA key-pair auth; humans use MFA
- Access roles (privileges on objects) granted to functional roles
- Persona roles: `ANALYST_RESTRICTED`, `ADVISOR`, `PORTFOLIO_ADMIN`, `COMPLIANCE_OFFICER`
- Tag-based dynamic masking for PII (unmasked / partial / fully masked by persona); a row access policy for advisor-to-client visibility
- `access_tier` on documents and chunks, enforced as a retrieval pre-filter in RAG
- The AI agent runs queries under the user's persona role (ADR-0011)
- AWS: least-privilege IAM roles; storage integration instead of AWS keys in Snowflake; GitHub OIDC instead of static AWS keys in CI

## Consequences
- More Terraform up front, but it's the most transferable enterprise skill in the project.
- Key rotation procedure is documented in the runbook.
- The Streamlit role switcher demonstrates the policies working.

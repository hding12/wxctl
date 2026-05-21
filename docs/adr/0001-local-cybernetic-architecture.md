# ADR-0001: Local Cybernetic Architecture for Encrypted Chat Interaction Control

## Status
Accepted

## Context

The system must deliver a stable, agent-readable export interface over unstable and partially knowable local chat data sources. The upstream tools are useful but unreliable as standalone products:

- key capture is manual and stateful
- decrypted database coverage may be partial
- contact database access may be missing
- message types evolve over time
- media payloads require message-type-specific decoding

## Decision

We separate the system into two loops:

1. `sync` loop: touches upstream state, collects and normalizes messages into a local warehouse
2. `dump` loop: serves stable JSONL output from the warehouse and never reads upstream data directly

We preserve raw payloads and decoded structures side by side.

## Rationale

This follows core engineering cybernetics principles:

- prefer closed-loop feedback over open-loop batch assumptions
- treat uncertainty as a first-class design input
- use imperfect components to build a more reliable whole
- maintain observability so drift and failure become actionable
- isolate disturbance: upstream volatility should not leak into agent interfaces

## Consequences

Positive:

- agent-facing interface remains deterministic
- re-decoding is possible without re-capturing keys
- partial upstream failure degrades gracefully
- sync coverage and decode coverage become measurable

Negative:

- higher initial complexity than one-shot CSV export
- local warehouse and raw archive need lifecycle management
- media decoding remains incremental work

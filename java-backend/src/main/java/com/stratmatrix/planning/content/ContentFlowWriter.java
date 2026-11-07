package com.stratmatrix.planning.content;

/**
 * Host-owned content-flow write boundary. Implement with the host's table/service.
 * Enforce one active flow per planningItemId, monotonic resultVersion and atomic
 * idempotence. A newer version may update a waiting flow, never a producing/completed flow.
 * Retrying an accepted write must return the original receipt and frozen production time.
 */
public interface ContentFlowWriter {
  ContentFlowReceipt upsert(ContentFlowEntry entry);
}

package com.stratmatrix.planning.content;

/**
 * Host-owned content-flow write boundary. Implement with the host's table/service.
 * Enforce one active flow per planningItemId, monotonic resultVersion and atomic
 * idempotence. A newer version may update a waiting flow, never a producing/completed flow.
 * Retrying an accepted write must return the original receipt and frozen production time.
 */
public interface ContentFlowWriter {
  enum TransactionMode {
    /** Same DataSource and REQUIRED transaction as the planning receipt. Never performs HTTP. */
    SAME_TRANSACTION,
    /** Remote/other storage: return a durable idempotent receipt; no planning row lock during I/O. */
    INDEPENDENT
  }

  default TransactionMode transactionMode() { return TransactionMode.INDEPENDENT; }

  ContentFlowReceipt upsert(ContentFlowEntry entry);
}

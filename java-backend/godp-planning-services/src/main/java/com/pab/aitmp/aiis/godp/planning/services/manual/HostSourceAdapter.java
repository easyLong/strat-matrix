package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Assembles host-owned data capabilities without putting bank SQL or SDK calls in business services.
 * The host supplies each dependency and registers this adapter as ManualPorts.Source.
 */
public final class HostSourceAdapter implements ManualPorts.Source {
  private final ManualPorts.AccountFacts accounts;
  private final ManualPorts.TopicFacts topics;
  private final ManualPorts.SnapshotFacts snapshots;
  private final ManualPorts.HistoricalEligibility history;

  public HostSourceAdapter(ManualPorts.AccountFacts accounts, ManualPorts.TopicFacts topics,
      ManualPorts.SnapshotFacts snapshots, ManualPorts.HistoricalEligibility history) {
    this.accounts = Objects.requireNonNull(accounts, "account facts");
    this.topics = Objects.requireNonNull(topics, "topic facts");
    this.snapshots = Objects.requireNonNull(snapshots, "snapshot facts");
    this.history = Objects.requireNonNull(history, "historical eligibility");
  }

  @Override
  public List<Map<String, Object>> accountOptions(int limit, boolean includeDisabled) {
    return accounts.accountOptions(limit, includeDisabled);
  }

  @Override
  public Map<String, Object> sourceAccounts(List<String> accountIds) {
    return accounts.sourceAccounts(accountIds);
  }

  @Override
  public List<Map<String, Object>> topicCandidates(int limit) {
    return topics.topicCandidates(limit);
  }

  @Override
  public Map<String, Object> topicDetail(String topicId, String topicType) {
    return topics.topicDetail(topicId, topicType);
  }

  @Override
  public Map<String, Object> snapshot(List<String> accountIds, List<String> topicIds) {
    return snapshots.snapshot(accountIds, topicIds);
  }

  @Override
  public Set<String> historicalPlanned(String publishDate) {
    return history.historicalPlanned(publishDate);
  }

  @Override
  public Set<String> historicalReserved(String publishDate) {
    return history.historicalReserved(publishDate);
  }
}

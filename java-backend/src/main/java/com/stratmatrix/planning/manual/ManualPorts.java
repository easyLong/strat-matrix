package com.stratmatrix.planning.manual;

import java.util.*;

public final class ManualPorts {
  private ManualPorts() {}

  /** Current account facts supplied by the host's account service. */
  public interface AccountFacts {
    /** Page catalog: current bank account facts, including disabled accounts when requested. */
    List<Map<String, Object>> accountOptions(int limit, boolean includeDisabled);
    /** Current account facts used when a historical result has no frozen account snapshot. */
    Map<String, Object> sourceAccounts(List<String> accountIds);
  }

  /** Current topic facts supplied by the host's topic service. */
  public interface TopicFacts {
    /** Current selectable topics for a newly generated item; final validation uses snapshot(). */
    List<Map<String, Object>> topicCandidates(int limit);
    /** Page detail may include a topic no longer selectable; it is not an allocation check. */
    Map<String, Object> topicDetail(String topicId, String topicType);
  }

  /** Freezes the selected facts and the algorithm version for a single calculation. */
  public interface SnapshotFacts {
    Map<String, Object> snapshot(List<String> accounts, List<String> topics);
  }

  /** Old planning facts only; new Java tasks are checked against the business repository. */
  public interface HistoricalEligibility {
    Set<String> historicalPlanned(String publishDate);
    Set<String> historicalReserved(String publishDate);
  }

  /** Stable boundary consumed by business services; the host may assemble it from smaller ports. */
  public interface Source extends AccountFacts, TopicFacts, SnapshotFacts, HistoricalEligibility {
  }

  public interface Computer {
    Map<String, Object> submit(Map<String, Object> frozenInput);
  }

  public interface Actor {
    String current();
  }

  /** Temporary bridge for business capabilities not yet migrated from the old service. */
  public interface Transition {
    Map<String, Object> queryPage(String view, Map<String, Object> query);
    long resultWatermark();
    List<Map<String, Object>> latestOperations(List<Long> itemIds);
    List<Map<String, Object>> periodContext(Map<String, Object> query);
    List<Map<String, Object>> batches(int limit, String planType);
    Object batch(long id);
    Object replaceTopic(long id, Map<String, Object> request);
    List<Map<String, Object>> adjustments(long id);
    List<Map<String, Object>> replacementCandidates(long id);
    default List<Map<String, Object>> marketingTasks(int limit, int offset) {
      return Collections.emptyList();
    }
    default Object marketingTaskDetails(String taskCode) {
      throw new BusinessException(404, "历史营销任务不存在");
    }
  }

  /** Host content system reports aggregate demand status; no allocation is initiated here. */
  public interface MarketingStatusSource {
    List<MarketingObservation> query(List<String> taskCodes);
  }

  public static final class MarketingObservation {
    public final String taskCode;
    public final String status;
    public final int accountCount;
    public final int completedCount;
    public final int failedCount;
    public final long updatedAtMillis;

    public MarketingObservation(String taskCode, String status, int accountCount,
        int completedCount, int failedCount, long updatedAtMillis) {
      this.taskCode = taskCode;
      this.status = status;
      this.accountCount = accountCount;
      this.completedCount = completedCount;
      this.failedCount = failedCount;
      this.updatedAtMillis = updatedAtMillis;
    }
  }

  /** The host reads content-owned facts; this module never starts content production. */
  public interface ContentStatusSource {
    List<ContentObservation> query(List<ContentCandidate> candidates);
  }

  public static final class ContentCandidate {
    public final long itemId;
    public final String slotId;
    public final int version;
    public final String topicId;

    public ContentCandidate(long itemId, String slotId, int version, String topicId) {
      this.itemId = itemId;
      this.slotId = slotId;
      this.version = version;
      this.topicId = topicId;
    }
  }

  public static final class ContentObservation {
    public final long itemId;
    public final int version;
    public final String status;
    public final String contentId;
    public final long updatedAtMillis;
    public final String productionTaskId;
    public final String error;

    public ContentObservation(long itemId, int version, String status, String contentId,
        long updatedAtMillis, String productionTaskId, String error) {
      this.itemId = itemId;
      this.version = version;
      this.status = status;
      this.contentId = contentId;
      this.updatedAtMillis = updatedAtMillis;
      this.productionTaskId = productionTaskId;
      this.error = error;
    }
  }
}

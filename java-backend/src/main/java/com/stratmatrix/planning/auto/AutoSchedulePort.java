package com.stratmatrix.planning.auto;

import java.time.LocalDate;
import java.util.Map;

/** Internal algorithm request; Python chooses its approved policy and account scope. */
public interface AutoSchedulePort {
  Map<String, Object> start(
      LocalDate cycleStart, int businessConfigVersion, Map<String, Object> frozenBusinessConfig);

  Map<String, Object> status(long pipelineId);
  /** Read-only algorithm proposal; Java must validate and commit it in the business database. */
  Map<String, Object> proposal(
      long pipelineId, int businessConfigVersion, Map<String, Object> frozenBusinessConfig);

  Map<String, Object> acknowledge(long pipelineId, String proposalHash, long businessBatchId);
}

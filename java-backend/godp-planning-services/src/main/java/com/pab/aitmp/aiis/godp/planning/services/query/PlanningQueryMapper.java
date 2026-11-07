package com.pab.aitmp.aiis.godp.planning.services.query;

import com.pab.aitmp.aiis.godp.planning.entity.entity.*;
import com.pab.aitmp.aiis.godp.planning.entity.row.*;
import com.pab.aitmp.aiis.godp.planning.entity.command.*;

import java.util.*;

public interface PlanningQueryMapper {
  List<PlanningItemReadRow> records(PlanningQueryCriteria p);

  List<PlanGroupRow> groupKeys(PlanningQueryCriteria p);

  long groupCount(PlanningQueryCriteria p);

  PlanSummaryRow summary(PlanningQueryCriteria p);

  List<ContentTypeCountRow> distribution(PlanningQueryCriteria p);

  List<AccountGroupRow> accountGroups(PlanningQueryCriteria p);

  long accountCount(PlanningQueryCriteria p);

  List<PlanningItemReadRow> accountSnapshots(PlanningQueryCriteria p);

  List<AccountFacetRow> facets(PlanningQueryCriteria p);

  List<PeriodKeyRow> periodKeys(PlanningQueryCriteria p);

  long periodCount(PlanningQueryCriteria p);

  List<PlanningBatchReadRow> periodBatches(PlanningQueryCriteria p);

  List<PeriodAccountCountRow> periodAccounts(PlanningQueryCriteria p);

  List<PlanningTaskReadRow> tasks(PlanningQueryCriteria p);

  long taskCount(PlanningQueryCriteria p);

  List<PlanningAdjustmentEntity> latestOperations(PlanningQueryCriteria p);

  List<PayloadRow> failures(PlanningQueryCriteria p);

  PayloadRow archivedTask(PlanningQueryCriteria p);
}

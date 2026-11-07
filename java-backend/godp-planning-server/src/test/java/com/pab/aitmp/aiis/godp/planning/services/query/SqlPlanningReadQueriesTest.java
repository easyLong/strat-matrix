package com.pab.aitmp.aiis.godp.planning.services.query;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Test;

class SqlPlanningReadQueriesTest {
  @Test
  void sqlPagesGroupsAndKeepsStatisticsForWholeFilteredScope() throws Exception {
    ReadDatabaseFixture f = new ReadDatabaseFixture();
    f.batch(1, "auto", "2026-11-02");
    f.batch(2, "manual", "2026-11-04");
    for (String a : Arrays.asList("A", "B"))
      for (String d : Arrays.asList("2026-11-02", "2026-11-04", "2026-11-06"))
        f.item(1, a, d, "planned", "regular", "T" + d);
    f.item(2, "A", "2026-11-04", "planned", "manual_extra", "M1");
    Map<String, Object> first = f.reads.plans(map("mode", "batch", "batch_id", 1, "page_size", 1));
    Map<String, Object> second =
        f.reads.plans(map("mode", "batch", "batch_id", 1, "page_size", 1, "page", 2));
    assertEquals(2, number(first, "total"));
    assertEquals(3, rows(first.get("items")).size());
    assertEquals(first.get("summary"), second.get("summary"));
    assertEquals(first.get("distribution"), second.get("distribution"));
    assertNotEquals(
        rows(first.get("items")).get(0).get("account_id"),
        rows(second.get("items")).get(0).get("account_id"));
    Map<String, Object> accounts =
        f.reads.accounts(map("page_size", 1, "filters", map("umNo", "UMA")));
    assertEquals(1, number(accounts, "total"));
    assertEquals("A", rows(accounts.get("items")).get(0).get("account_id"));
    Map<String, Object> period = rows(f.reads.periods(map("page_size", 1)).get("items")).get(0);
    assertEquals(2, number(period, "accountCount"));
    assertEquals(1, rows(period.get("autoBatches")).size());
    assertEquals(1, rows(period.get("manualBatches")).size());
    assertEquals(7, f.reads.records(map("mode", "all")).size());
    assertEquals(2, rows(f.reads.context(map("batch_id", 2)).get(0).get("batches")).size());
    assertEquals(
        1,
        rows(f.reads
                .plans(map("mode", "batch", "batch_id", 1, "unit", "records", "page_size", 1))
                .get("items"))
            .size());
  }

  @Test
  void archiveTaskPagingAndLatestOperationQueriesAreLocal() throws Exception {
    ReadDatabaseFixture f = new ReadDatabaseFixture();
    f.batch(1, "auto", "2026-11-02");
    long id = f.item(1, "A", "2026-11-02", "planned", "regular", "T1");
    f.repo.saveAdjustment(id, write(map("item_id", id, "reason", "旧操作")));
    f.repo.saveAdjustment(id, write(map("item_id", id, "reason", "最新操作")));
    assertEquals(
        "最新操作",
        f.reads
            .latestOperations(Collections.singletonList(id))
            .get(String.valueOf(id))
            .get("reason"));
    f.jdbc.update(
        "INSERT INTO godp_planning_task_archive(archive_key,source_id,payload,created_at) VALUES(?,?,?,?)",
        "legacy:1",
        1,
        write(
            map(
                "task_name",
                "历史任务",
                "task_code",
                "OLD-1",
                "batch_code",
                "OLD-1",
                "created_by",
                "UM1",
                "content_status",
                "已完成",
                "publish_date",
                "2026-11-02")),
        1000);
    assertEquals(
        1,
        number(
            f.reads.tasks(
                map("filters", map("creator", "UM1", "batch", "OLD", "contentStatus", "已完成"))),
            "total"));
    f.jdbc.update(
        "INSERT INTO godp_planning_failure(batch_id,account_key,payload) VALUES(?,?,?)",
        1,
        "A",
        write(map("batch_code", "B1", "account_id", "A", "um_no", "UMA", "reason", "测试失败原因")));
    assertEquals(
        1,
        f.reads
            .failures(map("mode", "cycle", "cycle_start", "2026-11-02", "cycle_end", "2026-11-08"))
            .size());
    assertEquals(0, f.reads.failures(map("mode", "batch", "batch_id", 2)).size());
    assertEquals("OLD-1", object(f.reads.archivedTask("OLD-1").get("task")).get("task_code"));
    assertThrows(
        com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException.class,
        () -> f.reads.records(map("mode", "account")));
  }
}

package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.PlanningQueryCriteria;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row.PlanningTaskReadRow;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.persistence.SqlRows;
import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import org.junit.jupiter.api.Test;

/** Exercise actual Mapper SQL on a zero-view database using a DML-only application user. */
class ViewFreeQueryTest {
  @Test
  void publishedResultsScansAndExportsShareOneBoundaryWithoutViews() throws Exception {
    ReadDatabaseFixture f = new ReadDatabaseFixture(true);
    f.batch(1, "auto", "2026-11-02");
    f.batch(2, "manual", "2026-11-03");
    f.batch(3, "auto", "2026-11-04");
    f.item(1, "A", "2026-11-05", "planned", "regular", "T1");
    f.item(1, "A", "2026-11-05", "unassigned", "hotspot", "");
    f.item(1, "B", "2026-11-05", "awaiting_market", "marketing", "");
    long marketing = f.item(1, "A", "2026-11-05", "generated", "marketing", "M1");
    Map<String,Object> content = read(f.jdbc.queryForObject(
        "SELECT payload FROM godp_planning_item WHERE id=?", String.class, marketing));
    content.put("topic_type", "营销");
    f.jdbc.update("UPDATE godp_planning_item SET payload=? WHERE id=?", write(content), marketing);
    f.item(2, "HIDDEN", "2026-11-05", "unassigned", "hotspot", "");
    f.item(2, "HIDDEN", "2026-11-05", "awaiting_market", "marketing", "");
    f.item(3, "DELETED", "2026-11-05", "planned", "regular", "T2");
    f.jdbc.update("UPDATE godp_planning_batch SET write_state='staging' WHERE id=2");
    f.jdbc.update("UPDATE godp_planning_batch SET del_flag='Y' WHERE id=3");
    assertEquals(0, f.jdbc.queryForObject(
        "SELECT COUNT(*) FROM information_schema.views WHERE table_schema='public'", Integer.class));
    assertThrows(org.springframework.dao.DataAccessException.class,
        () -> f.jdbc.execute("CREATE TABLE forbidden_ddl_probe(id BIGINT)"));
    assertEquals(4, f.reads.records(map("mode", "all")).size());
    assertEquals(2, number(f.reads.accounts(map()), "total"));
    assertEquals(1, number(f.reads.periods(map()), "total"));
    assertEquals(0, number(f.reads.plans(map("mode", "batch", "batch_id", 2)), "total"));
    assertEquals(1, f.slots.hotspotsOnDate("2026-11-05", 0, 20).size());
    assertEquals(1, f.slots.marketingSlots(0, 20).size());
    assertEquals(1, f.slots.contentLinks("A", "2026-11-02", "2026-11-08"));
    f.jdbc.update("UPDATE godp_planning_batch SET write_state='ready' WHERE id=2");
    assertEquals(6, f.reads.records(map("mode", "all")).size());
    assertEquals(2, f.slots.hotspotsOnDate("2026-11-05", 0, 20).size());
    assertEquals(2, f.slots.marketingSlots(0, 20).size());
  }

  @Test
  void threeTaskBranchesKeepGlobalPaginationAndNullPublicationDates() throws Exception {
    ReadDatabaseFixture f = new ReadDatabaseFixture(true);
    f.batch(2, "manual", "2026-11-04");
    f.jdbc.update("INSERT INTO godp_manual_task(id,preview_code,task_code,status,payload,created_at,updated_at) "
        + "VALUES(2,'P2','TASK2','completed',?,1000,1000)",
        write(map("task_name","普通任务","publish_date","2026-11-04","created_by","UM1")));
    f.jdbc.update("INSERT INTO godp_manual_marketing_task(task_code,request_id,request_hash,task_name,topic_id,"
        + "allocation_count,topic_snapshot_json,created_at,updated_at) VALUES('MARKET','R1',?,'营销任务','T1',2,'{}',2000,2000)",
        String.join("", Collections.nCopies(64,"a")));
    f.jdbc.update("INSERT INTO godp_planning_task_archive(archive_key,source_id,payload,created_at) VALUES('archive:1',1,?,3000)",
        write(map("task_name","历史任务","publish_date","2026-11-05","created_by","UM1")));
    PlanningQueryCriteria p = SqlRows.criteria(map("limit",1,"offset",0));
    assertEquals(3, f.queries.taskCount(p));
    assertEquals("archive", f.queries.tasks(p).get(0).kind);
    p.offset=1L;
    PlanningTaskReadRow marketing=f.queries.tasks(p).get(0);
    assertEquals("marketing", marketing.kind);
    assertNull(marketing.publishDate);
    p.offset=2L;
    assertEquals("manual", f.queries.tasks(p).get(0).kind);
    p=SqlRows.criteria(map("limit",20,"offset",0,"dateStart","2026-11-04","dateEnd","2026-11-05"));
    assertEquals(2, f.queries.taskCount(p));
    assertEquals(2, f.queries.tasks(p).size());
    p.creator="UM1";
    assertEquals(2, f.queries.taskCount(p));
  }
}

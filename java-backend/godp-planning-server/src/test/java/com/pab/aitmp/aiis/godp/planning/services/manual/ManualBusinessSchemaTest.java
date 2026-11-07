package com.pab.aitmp.aiis.godp.planning.services.manual;

import static org.junit.jupiter.api.Assertions.*;

import com.pab.aitmp.aiis.godp.planning.server.dev.LocalManualBusinessSchema;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

class ManualBusinessSchemaTest {
  @Test
  void initializesOnlyBusinessTablesAndPreservesDataOnRestart() {
    DriverManagerDataSource source =
        new DriverManagerDataSource(
            "jdbc:h2:mem:"
                + UUID.randomUUID()
                + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
            "sa",
            "");
    LocalManualBusinessSchema.initialize(source);
    JdbcTemplate db = new JdbcTemplate(source);
    db.update(
        "INSERT INTO godp_manual_preview "
            + "(preview_code,payload,expires_at,created_by,created_at) VALUES(?,?,?,?,?)",
        "keep-preview",
        "{}",
        100L,
        "test",
        1L);
    LocalManualBusinessSchema.initialize(source);
    assertEquals(1, db.queryForObject("SELECT COUNT(*) FROM godp_manual_preview", Integer.class));
    Set<String> tables =
        new HashSet<>(
            db.queryForList(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'",
                String.class));
    assertEquals(14, tables.size());
    Set<String> auditFields =
        new HashSet<>(
            Arrays.asList(
                "id", "del_flag", "created_by", "updated_by", "created_time", "updated_time"));
    for (String table : tables) {
      Set<String> columns =
          new HashSet<>(
              db.queryForList(
                  "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
                  String.class,
                  table));
      assertTrue(columns.containsAll(auditFields), table);
    }
    assertEquals(
        new HashSet<>(
            Arrays.asList(
                "godp_manual_preview",
                "godp_manual_task",
                "godp_manual_reservation",
                "godp_manual_marketing_task",
                "godp_planning_batch",
                "godp_planning_item",
                "godp_planning_adjustment",
                "godp_business_planning_config",
                "godp_business_planning_config_version",
                "godp_auto_planning_task",
                "godp_planning_config_release",
                "godp_planning_task_archive",
                "godp_planning_resource_claim",
                "godp_planning_failure")),
        tables);
    assertFalse(tables.contains("godp_manual_compute"));
  }
}

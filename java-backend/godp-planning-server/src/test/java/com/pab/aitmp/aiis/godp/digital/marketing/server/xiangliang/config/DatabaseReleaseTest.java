package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.config;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import java.nio.charset.StandardCharsets;
import java.io.IOException;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.util.StreamUtils;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

/** View-free DBA delivery rehearsal; multi-action ALTER needs H2 dialect compatibility. */
class DatabaseReleaseTest {
  @Test
  void newInstallAndV8UpgradePreserveExistingDataAndCompatibleRollback() {
    DriverManagerDataSource ds = new DriverManagerDataSource("jdbc:h2:mem:release-" + UUID.randomUUID()
        + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1", "sa", "");
    JdbcTemplate sql = new JdbcTemplate(ds);
    apply(ds, "ddl/01-new-install.sql");
    assertEquals(14, sql.queryForObject("SELECT COUNT(*) FROM information_schema.tables "
        + "WHERE table_schema='public' AND table_type='BASE TABLE'", Integer.class));
    assertEquals(84, sql.queryForObject("SELECT COUNT(*) FROM information_schema.columns "
        + "WHERE table_schema='public' AND table_name NOT LIKE '%_read' "
        + "AND column_name IN ('id','del_flag','created_by','updated_by','created_time','updated_time')", Integer.class));
    sql.update("INSERT INTO godp_planning_batch(id,payload,created_at) VALUES(7,'{}',123)");
    apply(ds, "rollback/02-compatible-rollback.sql");
    assertEquals("ready", sql.queryForObject("SELECT write_state FROM godp_planning_batch WHERE id=7", String.class));
    assertEquals(1, sql.queryForObject("SELECT COUNT(*) FROM godp_planning_batch", Integer.class));
    assertEquals(0, sql.queryForObject("SELECT COUNT(*) FROM information_schema.views WHERE table_schema='public'", Integer.class));
    // Reconstruct V8 on the isolated database; the DBA upgrade then adds V9 defaults.
    sql.execute("ALTER TABLE godp_planning_batch DROP COLUMN write_state");
    sql.execute("ALTER TABLE godp_planning_batch DROP COLUMN write_cursor");
    apply(ds, "ddl/02-upgrade-v8-to-v10.sql");
    assertEquals("{}", sql.queryForObject("SELECT payload FROM godp_planning_batch WHERE id=7", String.class));
    assertEquals("ready", sql.queryForObject("SELECT write_state FROM godp_planning_batch WHERE id=7", String.class));
    assertEquals(0, sql.queryForObject("SELECT write_cursor FROM godp_planning_batch WHERE id=7", Integer.class));
    apply(ds, "ddl/03-upgrade-v9-to-v10.sql");
    assertEquals(1, sql.queryForObject("SELECT COUNT(*) FROM godp_planning_batch", Integer.class));
    assertEquals(0, sql.queryForObject("SELECT COUNT(*) FROM information_schema.views WHERE table_schema='public'", Integer.class));
  }

  private static void apply(DriverManagerDataSource ds, String relative) {
    Resource resource = new ClassPathResource("db/release/20261110-v10/" + relative);
    if (relative.equals("ddl/02-upgrade-v8-to-v10.sql")) {
      // MySQL supports multiple ADD COLUMN in one ALTER; H2 requires two ALTERs.
      try (java.io.InputStream input = resource.getInputStream()) {
        String sql = StreamUtils.copyToString(input, StandardCharsets.UTF_8)
            .replaceAll(",\\s*ADD COLUMN write_cursor", ";\nALTER TABLE godp_planning_batch ADD COLUMN write_cursor");
        resource = new ByteArrayResource(sql.getBytes(StandardCharsets.UTF_8));
      } catch (IOException error) { throw new IllegalStateException(error); }
    }
    ResourceDatabasePopulator script = new ResourceDatabasePopulator(resource);
    script.setSqlScriptEncoding("UTF-8");
    script.execute(ds);
  }
}

package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank;

import static org.junit.jupiter.api.Assertions.*;
import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.BankSourceMapper;
import java.nio.charset.StandardCharsets;
import java.time.ZoneId;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

class BankSourceSqlAdapterTest {
  private DriverManagerDataSource database() {
    return new DriverManagerDataSource("jdbc:h2:mem:source-assembly-" + UUID.randomUUID()
        + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
  }

  @Test void explicitXmlConnectsPagesAndBatchInteractionsWithoutWritingSourceData() throws Exception {
    DriverManagerDataSource ds = database();
    JdbcTemplate db = new JdbcTemplate(ds);
    db.execute("CREATE TABLE fixture_source_accounts(id VARCHAR(64),nickname VARCHAR(64))");
    db.update("INSERT INTO fixture_source_accounts VALUES (?,?)", "A1", "account one");
    Map<String,String> statements = new HashMap<>();
    statements.put("countAccounts", "SELECT COUNT(*) FROM fixture_source_accounts");
    statements.put("accounts", "SELECT id AS \"account_id\",nickname AS \"nickname\",TRUE AS \"eligible\","
        + "'2026-11-11T00:00:00Z' AS \"updated_at\" FROM fixture_source_accounts ORDER BY id "
        + "LIMIT #{query.pageSize} OFFSET #{query.offset}");
    statements.put("accountInteractions", "SELECT 'A1' AS \"account_id\",'C1' AS \"content_id\","
        + "'2026-11-10T00:00:00Z' AS \"published_at\" WHERE 'A1' IN "
        + "<foreach collection=\"query.accountIds\" item=\"id\" open=\"(\" separator=\",\" close=\")\">#{id}</foreach>");
    StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        + "<!DOCTYPE mapper PUBLIC \"-//mybatis.org//DTD Mapper 3.0//EN\" \"https://mybatis.org/dtd/mybatis-3-mapper.dtd\">"
        + "<mapper namespace=\"" + BankSourceMapper.class.getName() + "\">");
    for (java.lang.reflect.Method method : BankSourceMapper.class.getDeclaredMethods()) {
      xml.append("<select id=\"").append(method.getName()).append("\" resultType=\"")
          .append(method.getReturnType() == Long.class ? "long" : "map").append("\">")
          .append(statements.getOrDefault(method.getName(), "SELECT 1")).append("</select>");
    }
    xml.append("</mapper>");
    BankSourceFacts facts = BankSourceSqlAdapter.create(ds, new DataSourceTransactionManager(ds),
        new ByteArrayResource(xml.toString().getBytes(StandardCharsets.UTF_8)), ZoneId.of("Asia/Shanghai"));
    Map<String,Object> page = facts.accounts(map("page_size", 1));
    assertEquals(1, number(page, "total"));
    Map<String,Object> account = rows(page.get("items")).get(0);
    assertEquals("A1", account.get("account_id"));
    assertEquals("C1", rows(account.get("interactions")).get(0).get("content_id"));
    assertTrue(rows(facts.accounts(map("page_size",1,"page_no",2)).get("items")).isEmpty());
    assertTrue(rows(facts.accounts(map("account_ids",Collections.emptyList())).get("items")).isEmpty());
    assertEquals(1, db.queryForObject("SELECT COUNT(*) FROM fixture_source_accounts", Integer.class));
  }

  @Test void missingAndUnfilledXmlFailBeforeReceivingQueries() {
    DriverManagerDataSource ds = database();
    DataSourceTransactionManager tx = new DataSourceTransactionManager(ds);
    assertThrows(IllegalStateException.class, () -> BankSourceSqlAdapter.create(ds, tx,
        new ClassPathResource("absent-private-source.xml"), ZoneId.of("Asia/Shanghai")));
    assertThrows(IllegalStateException.class, () -> BankSourceSqlAdapter.create(ds, tx,
        new ClassPathResource("mapper/xiangliang/source/BankSourceMapper.xml"), ZoneId.of("Asia/Shanghai")));
  }
}

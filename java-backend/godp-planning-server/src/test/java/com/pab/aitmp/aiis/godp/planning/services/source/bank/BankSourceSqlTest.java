package com.pab.aitmp.aiis.godp.planning.services.source.bank;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import java.time.Instant;
import java.util.*;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionSynchronizationManager;

class BankSourceSqlTest {
  @Test
  void optionalInteractionBatchUsesSameReadOnlyTransactionAndExistingMapping() {
    DriverManagerDataSource ds = datasource();
    BankSourceMapper mapper = mock(BankSourceMapper.class);
    when(mapper.countAccounts(any())).thenReturn(1L);
    Map<String, Object> account = BankSourceFactsTest.account();
    account.remove("近三个月内容互动明细");
    when(mapper.accounts(any())).thenReturn(Collections.singletonList(account));
    BankSourceMapping mapping = new BankSourceMapping();
    MapperBankSourceQueries reader =
        new MapperBankSourceQueries(
            mapper,
            new DataSourceTransactionManager(ds),
            mapping,
            ids -> {
              assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
              assertTrue(TransactionSynchronizationManager.isCurrentTransactionReadOnly());
              assertEquals(Collections.singletonList("A1"), ids);
              return Collections.singletonList(
                  map(
                      "account_id",
                      "A1",
                      "content_id",
                      "CI",
                      "published_at",
                      "2026-11-03T08:00:00Z"));
            });
    Map<String, Object> response = new BankSourceFacts(reader, mapping).accounts(map());
    assertEquals(
        "CI",
        rows(rows(response.get("items")).get(0).get("interactions")).get(0).get("content_id"));
    assertFalse(account.containsKey("interactions"));
    assertFalse(TransactionSynchronizationManager.isActualTransactionActive());
  }

  private DriverManagerDataSource datasource() {
    return new DriverManagerDataSource(
        "jdbc:h2:mem:bank-source-"
            + UUID.randomUUID()
            + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
        "sa",
        "");
  }

  private BankSourceMapper mapper(DriverManagerDataSource ds, String xml) throws Exception {
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(new ClassPathResource(xml));
    return new SqlSessionTemplate(factory.getObject()).getMapper(BankSourceMapper.class);
  }

  @Test
  void realMyBatisPagesEligibleRowsWithStableIdentityAndBoundParameters() throws Exception {
    DriverManagerDataSource ds = datasource();
    JdbcTemplate jdbc = new JdbcTemplate(ds);
    jdbc.execute(
        "CREATE TABLE fixture_accounts(account_id VARCHAR(64) PRIMARY KEY,nickname VARCHAR(80),eligible BOOLEAN,updated_at VARCHAR(40),updated_epoch BIGINT)");
    long time = Instant.parse("2026-11-03T08:00:00Z").toEpochMilli();
    for (String id : Arrays.asList("A3", "A1", "A2"))
      jdbc.update(
          "INSERT INTO fixture_accounts VALUES(?,?,?,?,?)",
          id,
          id,
          !id.equals("A1"),
          "2026-11-03T08:00:00Z",
          time);
    BankSourceFacts facts =
        new BankSourceFacts(
            new MapperBankSourceQueries(
                mapper(ds, "bank-source/sample-account-mapper.xml"),
                new DataSourceTransactionManager(ds)));
    Map<String, Object> page = facts.accounts(map("page_size", 1));
    assertEquals(2, number(page, "total"));
    assertEquals("A2", rows(page.get("items")).get(0).get("account_id"));
    assertEquals(
        "A3",
        rows(facts.accounts(map("page_size", 1, "page_no", 2)).get("items"))
            .get(0)
            .get("account_id"));
    assertTrue(rows(facts.accounts(map("page_size", 1, "page_no", 3)).get("items")).isEmpty());
    assertEquals(2, number(facts.accounts(map("updated_from", "2026-11-03T08:00:00Z")), "total"));
    assertEquals(0, number(facts.accounts(map("updated_to", "2026-11-03T08:00:00Z")), "total"));
    assertEquals(
        1, number(facts.accounts(map("account_ids", Collections.singletonList("A3"))), "total"));
    assertEquals(
        0,
        number(
            facts.accounts(map("account_ids", Collections.singletonList("A3') OR 1=1 --"))),
            "total"));
    assertEquals(3, jdbc.queryForObject("SELECT COUNT(*) FROM fixture_accounts", Integer.class));
  }

  @Test
  void allTenUnfilledSqlStatementsFailClosedAndNeverPretendNoData() throws Exception {
    DriverManagerDataSource ds = datasource();
    BankSourceMapper mapper = mapper(ds, "bank-source/BankSourceMapper.xml");
    List<Supplier<?>> statements =
        Arrays.asList(
            () -> mapper.countAccounts(new BankSourceContracts.Accounts(map())),
            () -> mapper.accounts(new BankSourceContracts.Accounts(map())),
            () -> mapper.countTopics(new BankSourceContracts.Topics(map())),
            () -> mapper.topics(new BankSourceContracts.Topics(map())),
            () ->
                mapper.countMarketingContents(
                    new BankSourceContracts.Marketing(map("account_id", "A1"))),
            () ->
                mapper.marketingContents(
                    new BankSourceContracts.Marketing(map("account_id", "A1"))),
            () ->
                mapper.effectiveMarketing(
                    new BankSourceContracts.Placement(
                        map("account_id", "A1", "publish_date", "2026-11-04"))),
            () ->
                mapper.productionStatus(
                    new BankSourceContracts.Production(
                        map("slot_ids", Collections.singletonList("S1")))),
            () ->
                mapper.marketingStatus(
                    new BankSourceContracts.MarketingStatus(
                        map("task_codes", Collections.singletonList("M1")))),
            () ->
                mapper.approvedDemandContents(
                    new BankSourceContracts.ApprovedDemand(map("task_code", "M1"))));
    for (Supplier<?> statement : statements) {
      Throwable failure = assertThrows(RuntimeException.class, statement::get);
      while (!(failure instanceof BusinessException) && failure.getCause() != null)
        failure = failure.getCause();
      assertTrue(failure instanceof BusinessException, failure.toString());
      assertEquals(503, ((BusinessException) failure).status);
    }
    BankSourceFacts facts =
        new BankSourceFacts(
            new MapperBankSourceQueries(mapper, new DataSourceTransactionManager(ds)));
    assertEquals(503, assertThrows(BusinessException.class, () -> facts.accounts(map())).status);
  }

  @Test
  void countAndRowsShareReadOnlyTransactionAndDatabaseErrorsStayPrivate() {
    DriverManagerDataSource ds = datasource();
    BankSourceMapper mapper = mock(BankSourceMapper.class);
    Object[] transactionResource = new Object[1];
    when(mapper.countAccounts(any()))
        .thenAnswer(
            call -> {
              assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
              assertTrue(TransactionSynchronizationManager.isCurrentTransactionReadOnly());
              transactionResource[0] = TransactionSynchronizationManager.getResource(ds);
              return 1L;
            });
    when(mapper.accounts(any()))
        .thenAnswer(
            call -> {
              assertSame(transactionResource[0], TransactionSynchronizationManager.getResource(ds));
              BankSourceContracts.Accounts q = call.getArgument(0);
              assertEquals(6, q.offset);
              assertEquals(Instant.parse("2026-11-03T08:00:00Z"), q.updatedFrom);
              return Collections.singletonList(BankSourceFactsTest.account());
            });
    MapperBankSourceQueries reader =
        new MapperBankSourceQueries(mapper, new DataSourceTransactionManager(ds));
    reader.accounts(
        new BankSourceContracts.Accounts(
            map("page_no", 3, "page_size", 3, "updated_from", "2026-11-03T08:00:00Z")));
    assertFalse(TransactionSynchronizationManager.isActualTransactionActive());
    doThrow(
            new IllegalStateException(
                "SELECT secret_column FROM private_bank_table password=never-send"))
        .when(mapper)
        .accounts(any());
    BusinessException failure =
        assertThrows(
            BusinessException.class,
            () -> reader.accounts(new BankSourceContracts.Accounts(map())));
    assertEquals(503, failure.status);
    assertFalse(failure.getMessage().contains("private_bank_table"));
    assertNull(failure.getCause());
    assertFalse(TransactionSynchronizationManager.isActualTransactionActive());
  }
}

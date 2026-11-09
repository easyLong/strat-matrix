package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.config;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.persistence.BusinessMapperSupport;
import java.io.InputStream;
import java.sql.Connection;
import javax.sql.DataSource;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.ExecutorType;
import org.apache.ibatis.session.defaults.DefaultSqlSessionFactory;
import org.apache.ibatis.transaction.TransactionFactory;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.transaction.SpringManagedTransactionFactory;
import org.springframework.core.io.Resource;
import org.springframework.jdbc.datasource.AbstractDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.TransactionAwareDataSourceProxy;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

class BusinessMapperSupportTest {
  private static DataSource disconnected() {
    return new AbstractDataSource() {
      public Connection getConnection() { throw new AssertionError("preflight must not open a connection"); }
      public Connection getConnection(String user, String password) { return getConnection(); }
    };
  }

  private static SqlSessionTemplate sessions(DataSource dataSource, TransactionFactory transactions,
      ExecutorType executor, boolean loadAll) throws Exception {
    Configuration configuration = new Configuration(new Environment("test", transactions, dataSource));
    if (loadAll) {
      for (Resource xml : BusinessMapperSupport.businessXml()) {
        try (InputStream stream = xml.getInputStream()) {
          new XMLMapperBuilder(stream, configuration, xml.getDescription(), configuration.getSqlFragments()).parse();
        }
      }
    }
    return new SqlSessionTemplate(new DefaultSqlSessionFactory(configuration), executor);
  }

  @Test
  void completeVendorResourcesAndSameJdbcResourceNeedNoConnection() throws Exception {
    DataSource database = disconnected();
    SqlSessionTemplate sessions = sessions(database, new SpringManagedTransactionFactory(), ExecutorType.SIMPLE, true);
    assertTrue(BusinessMapperSupport.verify(sessions, new DataSourceTransactionManager(database)));
    assertEquals(6, BusinessMapperSupport.businessXml().length);
    assertEquals("BankSourceMapper.xml", BusinessMapperSupport.sourceXml().getFilename());
  }

  @Test
  void appendingVendorXmlPreservesExistingHostResources() {
    Resource host = new org.springframework.core.io.ClassPathResource("other-vendor/ManualMapper.xml");
    Resource[] original = {host};
    Resource[] combined = BusinessMapperSupport.appendBusinessXml(original);
    assertEquals(7, combined.length);
    assertSame(host, combined[0]);
    assertEquals(1, original.length);
    assertFalse(java.util.Arrays.stream(combined).anyMatch(
        r -> r.getFilename().equals("BankSourceMapper.xml")));
  }

  @Test
  void missingMapperFailsWithAnActionableMessage() throws Exception {
    DataSource database = disconnected();
    SqlSessionTemplate sessions = sessions(database, new SpringManagedTransactionFactory(), ExecutorType.SIMPLE, false);
    assertTrue(assertThrows(IllegalStateException.class,
        () -> BusinessMapperSupport.verify(sessions, new DataSourceTransactionManager(database)))
        .getMessage().contains("ManualMapper.xml"));
  }

  @Test
  void registeredInterfaceWithoutItsXmlDoesNotPass() throws Exception {
    DataSource database = disconnected();
    SqlSessionTemplate sessions = sessions(database, new SpringManagedTransactionFactory(), ExecutorType.SIMPLE, false);
    sessions.getConfiguration().addMapper(ManualMapper.class);
    assertTrue(assertThrows(IllegalStateException.class,
        () -> BusinessMapperSupport.verify(sessions, new DataSourceTransactionManager(database)))
        .getMessage().contains("缺少SQL映射：ManualMapper."));
  }

  @Test
  void differentDatabaseFailsBeforeAnyBusinessWrite() throws Exception {
    DataSource database = disconnected();
    SqlSessionTemplate sessions = sessions(database, new SpringManagedTransactionFactory(), ExecutorType.SIMPLE, true);
    assertTrue(assertThrows(IllegalStateException.class,
        () -> BusinessMapperSupport.verify(sessions, new DataSourceTransactionManager(disconnected())))
        .getMessage().contains("同一DataSource"));
  }

  @Test
  void springTransactionAwareWrapperSharesTheUnderlyingResource() throws Exception {
    DataSource database = disconnected();
    SqlSessionTemplate sessions = sessions(new TransactionAwareDataSourceProxy(database),
        new SpringManagedTransactionFactory(), ExecutorType.REUSE, true);
    assertTrue(BusinessMapperSupport.verify(sessions, new DataSourceTransactionManager(database)));
  }

  @Test
  void batchExecutorIsRejectedBecauseRowCountsAreDeferred() throws Exception {
    DataSource database = disconnected();
    SqlSessionTemplate sessions = sessions(database, new SpringManagedTransactionFactory(), ExecutorType.BATCH, true);
    assertTrue(assertThrows(IllegalStateException.class,
        () -> BusinessMapperSupport.verify(sessions, new DataSourceTransactionManager(database)))
        .getMessage().contains("BATCH"));
  }

  @Test
  void nonSpringTransactionFactoryCannotParticipateInHostTransactions() throws Exception {
    DataSource database = disconnected();
    SqlSessionTemplate sessions = sessions(database, new JdbcTransactionFactory(), ExecutorType.SIMPLE, true);
    assertTrue(assertThrows(IllegalStateException.class,
        () -> BusinessMapperSupport.verify(sessions, new DataSourceTransactionManager(database)))
        .getMessage().contains("SpringManagedTransactionFactory"));
  }

  @Test
  void customHostManagerReportsUnverifiedIdentityInsteadOfPretendingSuccess() throws Exception {
    DataSource database = disconnected();
    SqlSessionTemplate sessions = sessions(database, new SpringManagedTransactionFactory(), ExecutorType.SIMPLE, true);
    assertFalse(BusinessMapperSupport.verify(sessions, mock(PlatformTransactionManager.class)));
  }
}

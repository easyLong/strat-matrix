package com.pab.aitmp.aiis.godp.planning.server.dev;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.api.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.planning.client.python.AlgorithmConfigPythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.ManualComputePythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.PythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.PythonExecutionClient;
import com.pab.aitmp.aiis.godp.planning.services.content.SlotCompletionMapper;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualMapper;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualNewInstallTransition;
import com.pab.aitmp.aiis.godp.planning.services.source.SourceCatalogAdapter;

import com.pab.aitmp.aiis.godp.planning.server.dev.legacy.LegacyPythonProperties;
import com.pab.aitmp.aiis.godp.planning.server.dev.local.FixtureContentObservations;
import com.pab.aitmp.aiis.godp.planning.server.dev.local.FixtureSourceFacts;
import com.pab.aitmp.aiis.godp.planning.server.dev.local.LocalPlanningContentAdapter;
import com.pab.aitmp.aiis.godp.planning.server.dev.local.LocalPythonAdapter;
import com.pab.aitmp.aiis.godp.planning.client.python.AutoSchedulePythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.CatalogProjectionPythonClient;
import com.pab.aitmp.aiis.godp.planning.services.auto.AutoScheduleMapper;
import com.pab.aitmp.aiis.godp.planning.api.port.AutoSchedulePort;
import com.pab.aitmp.aiis.godp.planning.api.port.AlgorithmConfigPort;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessConfigDatabase;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.planning.services.config.ConfigReleaseMapper;
import com.pab.aitmp.aiis.godp.planning.services.query.PlanningQueryMapper;
import com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts;
import com.zaxxer.hikari.*;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.web.client.RestTemplate;

/** Local adapters only; ManualModuleConfiguration wires the reusable services. */
@Configuration
@Profile("local & !inside")
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
public class LocalManualBusinessConfiguration {
  @Bean(destroyMethod = "close")
  public HikariDataSource manualBusinessDataSource(Environment env) {
    HikariConfig c = new HikariConfig();
    c.setJdbcUrl(env.getRequiredProperty("planning.manual.jdbc-url"));
    c.setUsername(env.getRequiredProperty("planning.manual.username"));
    c.setPassword(env.getRequiredProperty("planning.manual.password"));
    c.setMaximumPoolSize(4);
    c.setMinimumIdle(1);
    c.setConnectionTimeout(5000);
    c.setPoolName("manual-business");
    return new HikariDataSource(c);
  }

  @Bean
  public ManualMapper localManualMapper(
      @Qualifier("manualBusinessDataSource") DataSource ds, Environment env) throws Exception {
    if (env.getProperty("planning.manual.initialize-schema", Boolean.class, true)) {
      LocalManualBusinessSchema.initialize(ds);
      if ("business_only".equals(env.getProperty("planning.history.mode"))) {
        org.springframework.jdbc.datasource.init.ResourceDatabasePopulator views =
            new org.springframework.jdbc.datasource.init.ResourceDatabasePopulator(
                new ClassPathResource("db/planning-query-views.sql"));
        views.setSqlScriptEncoding("UTF-8");
        views.execute(ds);
      }
    }
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(new ClassPathResource("mapper/ManualMapper.xml"));
    SqlSessionFactory sessions = factory.getObject();
    return new SqlSessionTemplate(sessions).getMapper(ManualMapper.class);
  }

  @Bean("planningBusinessTransactions")
  public PlatformTransactionManager localBusinessTransactions(
      @Qualifier("manualBusinessDataSource") DataSource ds) {
    return new DataSourceTransactionManager(ds);
  }

  @Bean
  @DependsOn("localManualMapper")
  public BusinessPlanningConfigMapper localBusinessPlanningConfigMapper(
      @Qualifier("manualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(new ClassPathResource("mapper/BusinessPlanningConfigMapper.xml"));
    return new SqlSessionTemplate(factory.getObject())
        .getMapper(BusinessPlanningConfigMapper.class);
  }

  @Bean
  public BusinessConfigDatabase localBusinessConfigDatabase(
      BusinessPlanningConfigMapper mapper, @Qualifier("manualBusinessDataSource") DataSource ds) {
    return new BusinessConfigDatabase(mapper, new DataSourceTransactionManager(ds));
  }

  @Bean
  @DependsOn("localManualMapper")
  public ConfigReleaseMapper localConfigReleaseMapper(
      @Qualifier("manualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(new ClassPathResource("mapper/ConfigReleaseMapper.xml"));
    return new SqlSessionTemplate(factory.getObject()).getMapper(ConfigReleaseMapper.class);
  }

  @Bean
  public PythonClient localPythonClient(LegacyPythonProperties p) {
    return new PythonClient(
        p.baseUri(),
        p.getIntegrationToken(),
        PythonClient.boundedHttp(p.getConnectTimeoutMs(), p.getReadTimeoutMs()));
  }

  @Bean
  public PythonExecutionClient pythonExecutionClient(PythonClient python) {
    return new PythonExecutionClient(python);
  }

  @Bean
  public AlgorithmConfigPort localAlgorithmConfigPort(PythonClient python) {
    return new AlgorithmConfigPythonClient(python);
  }

  @Bean
  @DependsOn("localManualMapper")
  public SlotCompletionMapper localSlotCompletionMapper(
      @Qualifier("manualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean f = new SqlSessionFactoryBean();
    f.setDataSource(ds);
    f.setMapperLocations(new ClassPathResource("mapper/SlotCompletionMapper.xml"));
    return new SqlSessionTemplate(f.getObject()).getMapper(SlotCompletionMapper.class);
  }

  @Bean
  public PlanningContentPort localPlanningContentPort(SourceFacts facts) {
    return new LocalPlanningContentAdapter(facts);
  }

  @Bean
  public SourceFacts outsideSourceFacts(Environment env) {
    return new FixtureSourceFacts(
        java.nio.file.Paths.get(env.getRequiredProperty("planning.source.fixture")));
  }

  @Bean
  public ManualPorts.Source outsideManualSource(SourceFacts facts, PythonClient python) {
    return new com.pab.aitmp.aiis.godp.planning.services.source.SourceCatalogAdapter(
        facts, new CatalogProjectionPythonClient(python));
  }

  @Bean
  @DependsOn("localManualMapper")
  public AutoScheduleMapper localAutoScheduleMapper(
      @Qualifier("manualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(new ClassPathResource("mapper/AutoScheduleMapper.xml"));
    return new SqlSessionTemplate(factory.getObject()).getMapper(AutoScheduleMapper.class);
  }

  @Bean
  public AutoSchedulePort localAutoSchedulePort(PythonClient python) {
    return new AutoSchedulePythonClient(python);
  }

  @Bean
  public ManualPorts.Computer localManualComputer(PythonClient python) {
    return new ManualComputePythonClient(python);
  }

  @Bean
  public LocalPythonAdapter manualPythonAdapter(
      @Qualifier("legacyPythonHttp") RestTemplate client, LegacyPythonProperties p) {
    return new LocalPythonAdapter(client, p);
  }

  @Bean
  @Primary
  @ConditionalOnProperty(name = "planning.history.mode", havingValue = "business_only")
  public ManualPorts.Transition migratedHistory() {
    return new ManualNewInstallTransition();
  }

  @Bean
  @DependsOn("localManualMapper")
  public PlanningQueryMapper localPlanningQueryMapper(
      @Qualifier("manualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean f = new SqlSessionFactoryBean();
    f.setDataSource(ds);
    f.setMapperLocations(new ClassPathResource("mapper/PlanningQueryMapper.xml"));
    return new SqlSessionTemplate(f.getObject()).getMapper(PlanningQueryMapper.class);
  }

  @Bean
  public ManualPorts.Actor localManualActor(LegacyPythonProperties p) {
    return p::getOperatorId;
  }

  @Bean
  public ManualPorts.ContentStatusSource localContentStatusSource(SourceFacts facts) {
    return new FixtureContentObservations(facts)::content;
  }

  @Bean
  public ManualPorts.MarketingStatusSource localMarketingStatusSource(SourceFacts facts) {
    return new FixtureContentObservations(facts)::marketing;
  }
}

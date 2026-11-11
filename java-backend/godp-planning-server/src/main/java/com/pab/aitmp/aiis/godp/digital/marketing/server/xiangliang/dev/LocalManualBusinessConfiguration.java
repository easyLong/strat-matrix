package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.AlgorithmConfigPythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.ManualComputePythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.PythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.PythonExecutionClient;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.SlotCompletionMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualNewInstallTransition;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.SourceCatalogAdapter;

import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.legacy.LegacyPythonProperties;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local.FixtureContentObservations;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local.FixtureSourceFacts;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local.LocalPlanningContentAdapter;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local.LocalPythonAdapter;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.AutoSchedulePythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.CatalogProjectionPythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.AutoScheduleMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.AutoSchedulePort;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.AlgorithmConfigPort;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessConfigDatabase;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ConfigReleaseMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.PlanningQueryMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;
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
@Configuration("xiangliangLocalManualBusinessConfiguration")
@Profile("local & !inside")
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
public class LocalManualBusinessConfiguration {
  @Bean(name="xiangliangManualBusinessDataSource", destroyMethod = "close")
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

  @Bean(name="xiangliangLocalManualMapper")
  public ManualMapper localManualMapper(
      @Qualifier("xiangliangManualBusinessDataSource") DataSource ds, Environment env) throws Exception {
    if (env.getProperty("planning.manual.initialize-schema", Boolean.class, true)) {
      LocalManualBusinessSchema.initialize(ds);
    }
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(new ClassPathResource("mapper/xiangliang/ManualMapper.xml"));
    SqlSessionFactory sessions = factory.getObject();
    return new SqlSessionTemplate(sessions).getMapper(ManualMapper.class);
  }

  @Bean("xiangliangBusinessTransactions")
  public PlatformTransactionManager localBusinessTransactions(
      @Qualifier("xiangliangManualBusinessDataSource") DataSource ds) {
    return new DataSourceTransactionManager(ds);
  }

  @Bean(name="xiangliangLocalBusinessPlanningConfigMapper")
  @DependsOn("xiangliangLocalManualMapper")
  public BusinessPlanningConfigMapper localBusinessPlanningConfigMapper(
      @Qualifier("xiangliangManualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(new ClassPathResource("mapper/xiangliang/BusinessPlanningConfigMapper.xml"));
    return new SqlSessionTemplate(factory.getObject())
        .getMapper(BusinessPlanningConfigMapper.class);
  }

  @Bean(name="xiangliangLocalBusinessConfigDatabase")
  public BusinessConfigDatabase localBusinessConfigDatabase(
      BusinessPlanningConfigMapper mapper, @Qualifier("xiangliangManualBusinessDataSource") DataSource ds) {
    return new BusinessConfigDatabase(mapper, new DataSourceTransactionManager(ds));
  }

  @Bean(name="xiangliangLocalConfigReleaseMapper")
  @DependsOn("xiangliangLocalManualMapper")
  public ConfigReleaseMapper localConfigReleaseMapper(
      @Qualifier("xiangliangManualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(new ClassPathResource("mapper/xiangliang/ConfigReleaseMapper.xml"));
    return new SqlSessionTemplate(factory.getObject()).getMapper(ConfigReleaseMapper.class);
  }

  @Bean(name="xiangliangLocalPythonClient")
  public PythonClient localPythonClient(LegacyPythonProperties p) {
    return new PythonClient(
        p.baseUri(),
        p.getIntegrationToken(),
        PythonClient.boundedHttp(p.getConnectTimeoutMs(), p.getReadTimeoutMs()));
  }

  @Bean(name="xiangliangPythonExecutionClient")
  public PythonExecutionClient pythonExecutionClient(PythonClient python) {
    return new PythonExecutionClient(python);
  }

  @Bean(name="xiangliangLocalAlgorithmConfigPort")
  public AlgorithmConfigPort localAlgorithmConfigPort(PythonClient python) {
    return new AlgorithmConfigPythonClient(python);
  }

  @Bean(name="xiangliangLocalSlotCompletionMapper")
  @DependsOn("xiangliangLocalManualMapper")
  public SlotCompletionMapper localSlotCompletionMapper(
      @Qualifier("xiangliangManualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean f = new SqlSessionFactoryBean();
    f.setDataSource(ds);
    f.setMapperLocations(new ClassPathResource("mapper/xiangliang/SlotCompletionMapper.xml"),
        new ClassPathResource("mapper/xiangliang/PlanningQueryMapper.xml"));
    return new SqlSessionTemplate(f.getObject()).getMapper(SlotCompletionMapper.class);
  }

  @Bean(name="xiangliangLocalPlanningContentPort")
  public PlanningContentPort localPlanningContentPort(SourceFacts facts) {
    return new LocalPlanningContentAdapter(facts);
  }

  @Bean(name="xiangliangOutsideSourceFacts")
  @ConditionalOnProperty(name="planning.source.mode", havingValue="fixture", matchIfMissing=true)
  public SourceFacts outsideSourceFacts(Environment env) {
    return new FixtureSourceFacts(
        java.nio.file.Paths.get(env.getRequiredProperty("planning.source.fixture")));
  }

  @Bean(name="xiangliangSqlSourceFacts")
  @ConditionalOnProperty(name="planning.source.mode", havingValue="sql")
  public SourceFacts sqlSourceFacts(
      @Qualifier("xiangliangManualBusinessDataSource") DataSource ds, Environment env) throws Exception {
    return com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank.BankSourceSqlAdapter.create(
        ds, new DataSourceTransactionManager(ds),
        new org.springframework.core.io.DefaultResourceLoader().getResource(
            env.getRequiredProperty("planning.source.mapper-location")),
        java.time.ZoneId.of(env.getProperty("planning.source.storage-zone", "Asia/Shanghai")));
  }

  @Bean(name="xiangliangOutsideManualSource")
  public ManualPorts.Source outsideManualSource(SourceFacts facts, PythonClient python) {
    return new com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.SourceCatalogAdapter(
        facts, new CatalogProjectionPythonClient(python));
  }

  @Bean(name="xiangliangLocalAutoScheduleMapper")
  @DependsOn("xiangliangLocalManualMapper")
  public AutoScheduleMapper localAutoScheduleMapper(
      @Qualifier("xiangliangManualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(new ClassPathResource("mapper/xiangliang/AutoScheduleMapper.xml"));
    return new SqlSessionTemplate(factory.getObject()).getMapper(AutoScheduleMapper.class);
  }

  @Bean(name="xiangliangLocalAutoSchedulePort")
  public AutoSchedulePort localAutoSchedulePort(PythonClient python) {
    return new AutoSchedulePythonClient(python);
  }

  @Bean(name="xiangliangLocalManualComputer")
  public ManualPorts.Computer localManualComputer(PythonClient python) {
    return new ManualComputePythonClient(python);
  }

  @Bean(name="xiangliangManualPythonAdapter")
  public LocalPythonAdapter manualPythonAdapter(
      @Qualifier("xiangliangLegacyPythonHttp") RestTemplate client, LegacyPythonProperties p) {
    return new LocalPythonAdapter(client, p);
  }

  @Bean(name="xiangliangMigratedHistory")
  @Primary
  @ConditionalOnProperty(name = "planning.history.mode", havingValue = "business_only")
  public ManualPorts.Transition migratedHistory() {
    return new ManualNewInstallTransition();
  }

  @Bean(name="xiangliangLocalPlanningQueryMapper")
  @DependsOn("xiangliangLocalManualMapper")
  public PlanningQueryMapper localPlanningQueryMapper(
      @Qualifier("xiangliangManualBusinessDataSource") DataSource ds) throws Exception {
    SqlSessionFactoryBean f = new SqlSessionFactoryBean();
    f.setDataSource(ds);
    f.setMapperLocations(new ClassPathResource("mapper/xiangliang/PlanningQueryMapper.xml"));
    return new SqlSessionTemplate(f.getObject()).getMapper(PlanningQueryMapper.class);
  }

  @Bean(name="xiangliangLocalManualActor")
  public ManualPorts.Actor localManualActor(LegacyPythonProperties p) {
    return p::getOperatorId;
  }

  @Bean(name="xiangliangLocalContentStatusSource")
  public ManualPorts.ContentStatusSource localContentStatusSource(SourceFacts facts) {
    return new FixtureContentObservations(facts)::content;
  }

  @Bean(name="xiangliangLocalMarketingStatusSource")
  public ManualPorts.MarketingStatusSource localMarketingStatusSource(SourceFacts facts) {
    return new FixtureContentObservations(facts)::marketing;
  }
}

package com.stratmatrix.standalone;

import com.stratmatrix.planning.adapter.legacy.LegacyPythonProperties;
import com.stratmatrix.planning.adapter.local.LocalPlanningContentAdapter;
import com.stratmatrix.planning.adapter.local.LocalPythonAdapter;
import com.stratmatrix.planning.adapter.python.AlgorithmConfigPythonClient;
import com.stratmatrix.planning.adapter.python.AutoSchedulePythonClient;
import com.stratmatrix.planning.auto.AutoScheduleMapper;
import com.stratmatrix.planning.auto.AutoSchedulePort;
import com.stratmatrix.planning.config.AlgorithmConfigPort;
import com.stratmatrix.planning.config.BusinessConfigDatabase;
import com.stratmatrix.planning.config.BusinessPlanningConfigMapper;
import com.stratmatrix.planning.config.ConfigReleaseMapper;
import com.stratmatrix.planning.content.*;
import com.stratmatrix.planning.manual.*;
import com.stratmatrix.planning.query.PlanningQueryMapper;
import com.zaxxer.hikari.*;
import java.util.Collections;
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
@Profile("local")
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

  @Bean
  public ManualDatabase localManualDatabase(
      ManualMapper mapper, @Qualifier("manualBusinessDataSource") DataSource ds) {
    PlatformTransactionManager transactions = new DataSourceTransactionManager(ds);
    return new ManualDatabase(mapper, transactions);
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
  public AlgorithmConfigPort localAlgorithmConfigPort(
      @Qualifier("legacyPythonHttp") RestTemplate client, LegacyPythonProperties p) {
    return new AlgorithmConfigPythonClient(p.baseUri(), p.getIntegrationToken(), client);
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
  public PlanningContentPort localPlanningContentPort(LocalPythonAdapter local) {
    return new LocalPlanningContentAdapter(local);
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
  public AutoSchedulePort localAutoSchedulePort(
      @Qualifier("legacyPythonHttp") RestTemplate client, LegacyPythonProperties properties) {
    return new AutoSchedulePythonClient(
        properties.baseUri(), properties.getIntegrationToken(), client);
  }

  @Bean
  public LocalPythonAdapter manualPythonAdapter(
      @Qualifier("legacyPythonHttp") RestTemplate client,
      LegacyPythonProperties p,
      Environment env) {
    return new LocalPythonAdapter(
        client, p, !"business_only".equals(env.getProperty("planning.history.mode")));
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
  public ManualPorts.ContentStatusSource localContentStatusSource() {
    // No content-side provider exists outside the bank. Missing observations never imply success.
    return candidates -> Collections.emptyList();
  }

  @Bean
  public ManualPorts.MarketingStatusSource localMarketingStatusSource() {
    // Content-side marketing allocation is unavailable in the external development environment.
    return codes -> Collections.emptyList();
  }
}

package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.persistence;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.*;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import javax.sql.DataSource;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.ExecutorType;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.transaction.SpringManagedTransactionFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.jdbc.datasource.TransactionAwareDataSourceProxy;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.ResourceTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationUtils;

/** Vendor-owned resources and metadata checks; never opens a connection or creates a factory. */
public final class BusinessMapperSupport {
  private static final Logger LOG = LoggerFactory.getLogger(BusinessMapperSupport.class);
  private static final Class<?>[] MAPPERS = {
    ManualMapper.class, BusinessPlanningConfigMapper.class, ConfigReleaseMapper.class,
    AutoScheduleMapper.class, PlanningQueryMapper.class, SlotCompletionMapper.class
  };

  private BusinessMapperSupport() {}

  /** Append these to the host's existing mapper locations; keep its plugins and configuration. */
  public static Resource[] businessXml() {
    Resource[] resources = new Resource[MAPPERS.length];
    for (int i = 0; i < MAPPERS.length; i++) {
      resources[i] = new ClassPathResource("mapper/xiangliang/" + MAPPERS[i].getSimpleName() + ".xml");
    }
    return resources;
  }

  /** Adds only our six business files, keeping the host's existing resources and their order. */
  public static Resource[] appendBusinessXml(Resource... hostResources) {
    Resource[] vendor = businessXml();
    Resource[] combined = java.util.Arrays.copyOf(hostResources, hostResources.length + vendor.length);
    System.arraycopy(vendor, 0, combined, hostResources.length, vendor.length);
    return combined;
  }

  /** Source SQL belongs to the original-facts session, not implicitly to the business session. */
  public static Resource sourceXml() {
    return new ClassPathResource("mapper/xiangliang/source/BankSourceMapper.xml");
  }

  /**
   * Fails before page traffic for missing statements, batch execution or broken JDBC wiring.
   * Returns false only when a custom host transaction manager cannot expose its resource.
   * Such managers need host-side verification; do not pretend JDBC identity was checked.
   */
  public static boolean verify(SqlSessionTemplate sessions, PlatformTransactionManager transactions) {
    if (sessions == null || transactions == null) {
      throw invalid("请绑定xiangliangBusinessSessions和xiangliangBusinessTransactions");
    }
    if (sessions.getExecutorType() == ExecutorType.BATCH) {
      throw invalid("业务会话须使用SIMPLE或REUSE，BATCH不能即时返回写入行数");
    }
    Configuration configuration = sessions.getConfiguration();
    Environment environment = configuration.getEnvironment();
    if (environment == null || environment.getDataSource() == null) {
      throw invalid("业务SqlSessionFactory缺少DataSource");
    }
    if (!(environment.getTransactionFactory() instanceof SpringManagedTransactionFactory)) {
      throw invalid("业务SqlSessionFactory须使用SpringManagedTransactionFactory");
    }
    for (Class<?> mapper : MAPPERS) {
      if (!configuration.hasMapper(mapper)) {
        throw invalid("未加载" + mapper.getSimpleName() + ".xml");
      }
      for (Method method : mapper.getMethods()) {
        if (!method.isDefault() && !Modifier.isStatic(method.getModifiers())
            && !configuration.hasStatement(mapper.getName() + "." + method.getName(), false)) {
          throw invalid("缺少SQL映射：" + mapper.getSimpleName() + "." + method.getName());
        }
      }
    }
    if (transactions instanceof ResourceTransactionManager) {
      Object resource = ((ResourceTransactionManager) transactions).getResourceFactory();
      if (resource instanceof DataSource) {
        Object expected = unwrap(resource);
        Object actual = unwrap(environment.getDataSource());
        if (actual != expected) {
          throw invalid("业务MyBatis会话与事务管理器必须绑定同一DataSource");
        }
        return true;
      }
    }
    LOG.warn("xiangliang业务SQL映射已检查；宿主事务管理器未暴露JDBC资源，同库事务须由宿主验证");
    return false;
  }

  private static Object unwrap(Object resource) {
    Object result = TransactionSynchronizationUtils.unwrapResourceIfNecessary(resource);
    // Spring's JDBC transaction manager unwraps this proxy when binding a DataSource too.
    while (result instanceof TransactionAwareDataSourceProxy) {
      result = TransactionSynchronizationUtils.unwrapResourceIfNecessary(
          ((TransactionAwareDataSourceProxy) result).getTargetDataSource());
    }
    return result;
  }

  private static IllegalStateException invalid(String reason) {
    return new IllegalStateException("xiangliang业务持久化未就绪：" + reason);
  }
}

package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.BankSourceMapper;
import java.time.ZoneId;
import java.util.Collections;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.core.io.Resource;
import org.springframework.transaction.PlatformTransactionManager;

/** Explicit assembly using the host's source datasource and private, supplier-owned XML. */
public final class BankSourceSqlAdapter {
  private BankSourceSqlAdapter() {}

  public static BankSourceFacts create(
      DataSource sourceDataSource,
      PlatformTransactionManager sourceTransactions,
      Resource mapperXml,
      ZoneId storageZone) throws Exception {
    if (mapperXml == null || !mapperXml.exists())
      throw new IllegalStateException("资料查询映射文件不存在");
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(sourceDataSource);
    factory.setMapperLocations(mapperXml);
    SqlSessionFactory sessions = factory.getObject();
    BankSourceMapper mapper = new SqlSessionTemplate(sessions).getMapper(BankSourceMapper.class);
    BankSourceMapping mapping = new BankSourceMapping(storageZone);
    MapperBankSourceQueries queries = new MapperBankSourceQueries(
        mapper, sourceTransactions, mapping,
        ids -> mapper.accountInteractions(new BankSourceContracts.Accounts(
            Collections.<String, Object>singletonMap("account_ids", ids))))
        .verifyWith(sessions);
    queries.verifyReady();
    return new BankSourceFacts(queries, mapping);
  }
}

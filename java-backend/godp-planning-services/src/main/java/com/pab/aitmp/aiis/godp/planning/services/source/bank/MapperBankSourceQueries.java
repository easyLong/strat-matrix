package com.pab.aitmp.aiis.godp.planning.services.source.bank;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import java.util.*;
import java.util.function.Function;
import java.util.function.Supplier;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Optional SQL reader. Counts and rows share a read-only transaction on the source datasource. */
public final class MapperBankSourceQueries implements BankSourceQueries {
  private final BankSourceMapper mapper;
  private final TransactionTemplate read;
  private final BankSourceMapping mapping;
  private final Function<List<String>, List<Map<String, Object>>> interactions;
  private org.apache.ibatis.session.SqlSessionFactory sqlFactory;

  /** Mandatory for the host SQL adapter; resolving SQL does not execute it. */
  public MapperBankSourceQueries verifyWith(org.apache.ibatis.session.SqlSessionFactory factory) {
    this.sqlFactory=Objects.requireNonNull(factory);
    return this;
  }

  @Override public void verifyReady() {
    if (sqlFactory==null) throw new IllegalStateException("请给资料SQL读取器绑定SqlSessionFactory用于启动检查");
    BankSourcePreflight.verify(sqlFactory);
  }

  public MapperBankSourceQueries(
      BankSourceMapper mapper, PlatformTransactionManager sourceTransactions) {
    this(mapper, sourceTransactions, new BankSourceMapping(), null);
  }

  /** Optional batch reader runs in the same read-only transaction as account count/page queries. */
  public MapperBankSourceQueries(
      BankSourceMapper mapper,
      PlatformTransactionManager sourceTransactions,
      BankSourceMapping mapping,
      Function<List<String>, List<Map<String, Object>>> interactions) {
    this.mapper = Objects.requireNonNull(mapper);
    this.mapping = Objects.requireNonNull(mapping);
    this.interactions = interactions;
    read = new TransactionTemplate(Objects.requireNonNull(sourceTransactions));
    read.setReadOnly(true);
  }

  private <T> T query(Supplier<T> action) {
    try {
      return read.execute(tx -> action.get());
    } catch (RuntimeException error) {
      Throwable cause = error;
      for (int i = 0; cause != null && i < 20; i++, cause = cause.getCause())
        if (cause instanceof BusinessException) throw (BusinessException) cause;
      // SQL text, source table names and connection details stay inside the host.
      throw new BusinessException(503, "行内资料查询暂不可用，请检查资料接入配置");
    }
  }

  private static BankSourceContracts.PageRows page(Long count, List<Map<String, Object>> rows) {
    if (count == null) throw BankSourceValues.invalid(502, "资料总数缺失");
    return new BankSourceContracts.PageRows(count, rows);
  }

  public BankSourceContracts.PageRows accounts(BankSourceContracts.Accounts q) {
    return query(
        () -> {
          BankSourceContracts.PageRows page = page(mapper.countAccounts(q), mapper.accounts(q));
          return interactions == null
              ? page
              : BankSourceInteractions.attach(page, interactions, mapping);
        });
  }

  public BankSourceContracts.PageRows topics(BankSourceContracts.Topics q) {
    return query(() -> page(mapper.countTopics(q), mapper.topics(q)));
  }

  public BankSourceContracts.PageRows marketingContents(BankSourceContracts.Marketing q) {
    return query(() -> page(mapper.countMarketingContents(q), mapper.marketingContents(q)));
  }

  public List<Map<String, Object>> effectiveMarketing(BankSourceContracts.Placement q) {
    return query(() -> mapper.effectiveMarketing(q));
  }

  public List<Map<String, Object>> productionStatus(BankSourceContracts.Production q) {
    return query(() -> mapper.productionStatus(q));
  }

  public List<Map<String, Object>> marketingStatus(BankSourceContracts.MarketingStatus q) {
    return query(() -> mapper.marketingStatus(q));
  }

  public List<Map<String, Object>> approvedDemandContents(BankSourceContracts.ApprovedDemand q) {
    return query(() -> mapper.approvedDemandContents(q));
  }
}

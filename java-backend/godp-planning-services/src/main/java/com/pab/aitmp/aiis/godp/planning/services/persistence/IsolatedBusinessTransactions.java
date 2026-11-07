package com.pab.aitmp.aiis.godp.planning.services.persistence;
import com.pab.aitmp.aiis.godp.planning.api.port.BusinessTransactions;
import java.util.function.Supplier;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Non-Spring test/standalone construction only. Production wiring uses the declarative proxy. */
public final class IsolatedBusinessTransactions implements BusinessTransactions {
  private final TransactionTemplate tx;
  public IsolatedBusinessTransactions(PlatformTransactionManager manager) { tx=new TransactionTemplate(manager); }
  public <T> T required(Supplier<T> work) { return tx.execute(status -> work.get()); }
}

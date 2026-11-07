package com.pab.aitmp.aiis.godp.planning.services.persistence;
import com.pab.aitmp.aiis.godp.planning.api.port.BusinessTransactions;
import java.util.function.Supplier;
import org.springframework.transaction.annotation.Transactional;

/** Separate Spring proxy prevents self-invocation from bypassing the transaction boundary. */
public class DeclarativeBusinessTransactions implements BusinessTransactions {
  @Transactional(transactionManager="planningBusinessTransactions", rollbackFor=Exception.class)
  public <T> T required(Supplier<T> work) { return work.get(); }
}
